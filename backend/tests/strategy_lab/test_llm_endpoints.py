"""Tests for the Phase 2 LLM endpoints (plan, generate-code, refine-code)."""
import os
import sys
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.strategy_lab import StrategySession


@pytest.fixture
def client():
    import uuid as _uuid
    c = TestClient(app)
    c.headers["X-Forwarded-For"] = f"127.0.0.{_uuid.uuid4().int % 254 + 1}"
    return c


@pytest.fixture
def cleanup():
    created = []
    yield created
    if created:
        with SessionLocal() as s:
            for sid in created:
                obj = s.get(StrategySession, sid)
                if obj:
                    s.delete(obj)
            s.commit()


def _create_session(client) -> str:
    res = client.post("/api/strategy-lab/sessions", json={
        "name": f"phase2-{uuid.uuid4().hex[:8]}",
        "prompt": "Buy stocks where EMA20 crosses above EMA200, rank by angle, hold 5",
        "model_id": "deepseek-v4-flash:cloud",
    })
    assert res.status_code == 201
    return res.json()["id"]


def test_post_plan_persists_to_session(client, cleanup):
    """POST /plan should call LLM and persist plan_text."""
    sid = _create_session(client)
    cleanup.append(sid)
    # Use the cheapest model for testing
    res = client.post(
        f"/api/strategy-lab/sessions/{sid}/plan",
        json={"model": "deepseek-v4-flash:cloud"},
    )
    # If LLM is unavailable, skip
    if res.status_code == 502:
        pytest.skip("LLM unavailable in this environment")
    assert res.status_code == 200
    body = res.json()
    assert "plan_text" in body
    assert len(body["plan_text"]) > 50
    # Verify it was persisted
    res2 = client.get(f"/api/strategy-lab/sessions/{sid}")
    assert res2.json()["plan_text"] == body["plan_text"]


def test_post_generate_code_requires_plan(client, cleanup):
    sid = _create_session(client)
    cleanup.append(sid)
    # No plan_text set
    res = client.post(
        f"/api/strategy-lab/sessions/{sid}/generate-code",
        json={"model": "deepseek-v4-flash:cloud"},
    )
    assert res.status_code == 400
    assert "no plan_text" in res.json()["detail"].lower()


def test_refine_code_returns_diff(client, cleanup):
    sid = _create_session(client)
    cleanup.append(sid)
    # Set a fake code_text directly via PATCH
    res = client.patch(
        f"/api/strategy-lab/sessions/{sid}",
        json={"code_text": "def foo():\n    return 1\n"},
    )
    assert res.status_code == 200

    res2 = client.post(
        f"/api/strategy-lab/sessions/{sid}/refine-code",
        json={
            "model": "deepseek-v4-flash:cloud",
            "instruction": "Change foo to return 2 instead of 1",
        },
    )
    if res2.status_code == 502:
        pytest.skip("LLM unavailable in this environment")
    assert res2.status_code == 200
    body = res2.json()
    assert "diff" in body
    assert body["diff"].count("+") >= 1 or body["diff"].count("-") >= 1


def test_apply_diff_updates_code(client, cleanup):
    sid = _create_session(client)
    cleanup.append(sid)
    # Set initial code
    res = client.patch(
        f"/api/strategy-lab/sessions/{sid}",
        json={"code_text": "def foo():\n    return 1\n"},
    )
    assert res.status_code == 200
    # Apply a simple modification diff
    diff = "@@ -1,2 +1,2 @@\n def foo():\n-    return 1\n+    return 99\n"
    res2 = client.post(
        f"/api/strategy-lab/sessions/{sid}/apply-diff",
        json={"instruction": diff},
    )
    assert res2.status_code == 200
    assert "return 99" in res2.json()["code"]
    # Verify it was persisted
    res3 = client.get(f"/api/strategy-lab/sessions/{sid}")
    assert "return 99" in res3.json()["code_text"]


def test_apply_diff_rejects_invalid(client, cleanup):
    sid = _create_session(client)
    cleanup.append(sid)
    client.patch(
        f"/api/strategy-lab/sessions/{sid}",
        json={"code_text": "def foo():\n    return 1\n"},
    )
    # Mismatched diff
    diff = "@@ -1,2 +1,2 @@\n something else\n-blah\n+NEW\n"
    res = client.post(
        f"/api/strategy-lab/sessions/{sid}/apply-diff",
        json={"instruction": diff},
    )
    assert res.status_code == 400
    assert "diff_apply_failed" in str(res.json()["detail"])
