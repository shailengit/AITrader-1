"""Unit tests for cli-anything-tradecraft core modules.

Uses synthetic data and mocks. No external dependencies required.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

from cli_anything.tradecraft.core.config import (
    load_config,
    save_config,
    get_backend_url,
    set_backend_url,
    get_output_format,
    set_output_format,
    DEFAULT_CONFIG,
)
from cli_anything.tradecraft.core.session import Session
from cli_anything.tradecraft.core.project import Project
from cli_anything.tradecraft.core.export import render_json, render_csv, render_table
from cli_anything.tradecraft.utils.api_client import APIError, _request


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmpdir.name) / ".config" / "cli-anything-tradecraft"
        self.config_file = self.config_dir / "config.json"
        self.patch_dir = patch(
            "cli_anything.tradecraft.core.config.CONFIG_DIR",
            self.config_dir,
        )
        self.patch_file = patch(
            "cli_anything.tradecraft.core.config.CONFIG_FILE",
            self.config_file,
        )
        self.patch_dir.start()
        self.patch_file.start()

    def tearDown(self):
        self.patch_dir.stop()
        self.patch_file.stop()
        self.tmpdir.cleanup()

    def test_load_default_config(self):
        cfg = load_config()
        self.assertEqual(cfg["backend_url"], DEFAULT_CONFIG["backend_url"])
        self.assertEqual(cfg["output_format"], "table")

    def test_save_and_load_config(self):
        cfg = {"backend_url": "http://test:9999", "output_format": "json"}
        save_config(cfg)
        loaded = load_config()
        self.assertEqual(loaded["backend_url"], "http://test:9999")
        self.assertEqual(loaded["output_format"], "json")

    def test_set_backend_url(self):
        set_backend_url("http://api:9000")
        self.assertEqual(get_backend_url(), "http://api:9000")

    def test_env_backend_url(self):
        os.environ["TRADECRAFT_BACKEND_URL"] = "http://env:8000"
        self.assertEqual(get_backend_url(), "http://env:8000")
        del os.environ["TRADECRAFT_BACKEND_URL"]

    def test_set_output_format(self):
        set_output_format("csv")
        self.assertEqual(get_output_format(), "csv")


class TestSession(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.session_file = Path(self.tmpdir.name) / "session.json"
        self.patch_file = patch(
            "cli_anything.tradecraft.core.session.SESSION_FILE",
            self.session_file,
        )
        self.patch_file.start()

    def tearDown(self):
        self.patch_file.stop()
        self.tmpdir.cleanup()

    def test_add_scan(self):
        s = Session()
        s.add_scan("abc-123", "dormant_giant", True)
        scans = s.get_scans()
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]["scan_id"], "abc-123")

    def test_dry_run_no_save(self):
        s = Session(dry_run=True)
        s.add_scan("xyz-789", "quant_strategy", False)
        self.assertFalse(self.session_file.exists())

    def test_update_scan_status(self):
        s = Session()
        s.add_scan("abc-123", "dormant_giant", True)
        s.update_scan_status("abc-123", "completed")
        self.assertEqual(s.get_scans()[0]["status"], "completed")

    def test_remove_scan(self):
        s = Session()
        s.add_scan("abc-123", "dormant_giant", True)
        s.remove_scan("abc-123")
        self.assertEqual(len(s.get_scans()), 0)

    def test_add_strategy(self):
        s = Session()
        s.add_strategy("sma_cross", "/tmp/sma.py")
        strategies = s.get_strategies()
        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0]["name"], "sma_cross")

    def test_clear(self):
        s = Session()
        s.add_scan("abc", "mode", False)
        s.clear()
        self.assertEqual(len(s.get_scans()), 0)


class TestProject(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.tmpdir.name) / "projects"
        self.patch_dir = patch(
            "cli_anything.tradecraft.core.project.PROJECTS_DIR",
            self.projects_dir,
        )
        self.patch_dir.start()

    def tearDown(self):
        self.patch_dir.stop()
        self.tmpdir.cleanup()

    def test_create_and_list(self):
        p = Project("momentum")
        p.save()
        self.assertIn("momentum", Project.list_all())

    def test_add_scan(self):
        p = Project("momentum")
        p.add_scan("scan-1")
        self.assertIn("scan-1", p.list_scans())

    def test_add_strategy(self):
        p = Project("momentum")
        p.add_strategy("sma_cross")
        self.assertIn("sma_cross", p.list_strategies())

    def test_set_notes(self):
        p = Project("momentum")
        p.set_notes("Q1 research")
        self.assertEqual(p._data["notes"], "Q1 research")

    def test_get_notes(self):
        p = Project("momentum")
        p.set_notes("Q2 research")
        self.assertEqual(p.get_notes(), "Q2 research")
        p2 = Project("new_proj")
        self.assertEqual(p2.get_notes(), "")

    def test_delete(self):
        p = Project("momentum")
        p.save()
        self.assertTrue(Project.delete("momentum"))
        self.assertFalse(Project.delete("momentum"))


class TestExport(unittest.TestCase):
    def test_render_json(self):
        data = {"a": 1, "b": [2, 3]}
        out = render_json(data)
        self.assertIn('"a": 1', out)

    def test_render_csv(self):
        rows = [{"ticker": "AAPL", "price": 150}, {"ticker": "MSFT", "price": 300}]
        out = render_csv(rows)
        lines = out.strip().split("\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("AAPL", out)

    def test_render_table(self):
        rows = [{"ticker": "AAPL", "price": 150}]
        out = render_table(rows, title="Test")
        self.assertIn("AAPL", out)
        self.assertIn("Test", out)

    def test_render_empty_table(self):
        out = render_table([], title="Empty")
        self.assertIn("No data", out)


class TestAPIClient(unittest.TestCase):
    # Note: patch decorators are applied bottom-up.
    # Inner decorator (get_backend_url) mock comes first in args.
    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url")
    def test_get_success(self, mock_get_backend_url, mock_urlopen):
        mock_get_backend_url.return_value = "http://test"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status":"ok"}'
        mock_urlopen.return_value = mock_resp
        result = _request("GET", "/api/health")
        self.assertEqual(result["status"], "ok")

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url")
    def test_post_success(self, mock_get_backend_url, mock_urlopen):
        mock_get_backend_url.return_value = "http://test"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id":"123"}'
        mock_urlopen.return_value = mock_resp
        result = _request("POST", "/api/scan", body={"mode": "test"})
        self.assertEqual(result["id"], "123")

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url")
    def test_api_error(self, mock_get_backend_url, mock_urlopen):
        mock_get_backend_url.return_value = "http://test"
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "http://test/api", 404, "Not Found", {}, None
        )
        with self.assertRaises(APIError) as ctx:
            _request("GET", "/api/missing")
        self.assertEqual(ctx.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
