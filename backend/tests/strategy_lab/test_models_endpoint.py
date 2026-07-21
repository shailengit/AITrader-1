"""Tests for the Ollama manifest scanner."""
import json
import os
import tempfile

import pytest

from app.services.strategy_lab_models import list_ollama_models


def test_list_ollama_models_with_cloud_and_local(tmp_path, monkeypatch):
    # Build a fake manifest directory
    lib = tmp_path / "library"
    lib.mkdir()

    # Model 1: cloud-only (layers=null)
    (lib / "model1").mkdir()
    (lib / "model1" / "cloud").write_text(json.dumps({"layers": None}))

    # Model 2: local-only
    (lib / "model2").mkdir()
    (lib / "model2" / "13b").write_text(json.dumps({
        "layers": [{"mediaType": "ollama.image.model", "size": 1000}]
    }))

    # Model 3: both
    (lib / "model3").mkdir()
    (lib / "model3" / "cloud").write_text(json.dumps({"layers": None}))
    (lib / "model3" / "7b").write_text(json.dumps({
        "layers": [{"mediaType": "ollama.image.model", "size": 500}]
    }))

    models = list_ollama_models(manifest_root=str(lib))
    by_id = {m["id"]: m for m in models}

    assert set(by_id.keys()) == {"model1", "model2", "model3"}

    # model1: cloud only
    assert len(by_id["model1"]["variants"]) == 1
    assert by_id["model1"]["variants"][0]["type"] == "cloud"
    assert by_id["model1"]["variants"][0]["name"] == "cloud"

    # model2: local only
    assert len(by_id["model2"]["variants"]) == 1
    assert by_id["model2"]["variants"][0]["type"] == "local"
    assert by_id["model2"]["variants"][0]["name"] == "13b"
    assert by_id["model2"]["variants"][0]["size_bytes"] == 1000

    # model3: both
    m3_by_type = {v["type"]: v for v in by_id["model3"]["variants"]}
    assert len(m3_by_type) == 2
    assert m3_by_type["cloud"]["name"] == "cloud"
    assert m3_by_type["local"]["name"] == "7b"


def test_list_ollama_models_skips_non_dirs(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    # A stray file in the library should be ignored
    (lib / "stray.txt").write_text("ignore me")
    (lib / "good_model").mkdir()
    (lib / "good_model" / "cloud").write_text(json.dumps({"layers": None}))

    models = list_ollama_models(manifest_root=str(lib))
    assert len(models) == 1
    assert models[0]["id"] == "good_model"


def test_list_ollama_models_missing_root():
    """Missing root returns empty list (not exception)."""
    models = list_ollama_models(manifest_root="/nonexistent/path/that/does/not/exist")
    assert models == []
