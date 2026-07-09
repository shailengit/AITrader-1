"""End-to-end tests for cli-anything-tradecraft.

Tests the full CLI pipeline using Click's CliRunner.
Uses monkey-patching for the HTTP backend to avoid requiring a live server.
Includes subprocess tests when CLI_ANYTHING_FORCE_INSTALLED=1.
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from cli_anything.tradecraft.main import cli
from cli_anything.tradecraft.core.config import load_config


class MockResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body


def _mock_urlopen_factory(response_map: dict):
    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        for prefix, body in response_map.items():
            if prefix in url:
                return MockResponse(json.dumps(body).encode())
        return MockResponse(json.dumps({"status": "ok"}).encode())
    return mock_urlopen


class TestE2EWorkflows(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmpdir.name) / ".config" / "cli-anything-tradecraft"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.patch_config_dir = patch(
            "cli_anything.tradecraft.core.config.CONFIG_DIR", self.config_dir
        )
        self.patch_config_file = patch(
            "cli_anything.tradecraft.core.config.CONFIG_FILE", self.config_dir / "config.json"
        )
        self.patch_session_file = patch(
            "cli_anything.tradecraft.core.session.SESSION_FILE", self.config_dir / "session.json"
        )
        self.patch_projects_dir = patch(
            "cli_anything.tradecraft.core.project.PROJECTS_DIR", self.config_dir / "projects"
        )
        self.patch_config_dir.start()
        self.patch_config_file.start()
        self.patch_session_file.start()
        self.patch_projects_dir.start()

    def tearDown(self):
        self.patch_config_dir.stop()
        self.patch_config_file.stop()
        self.patch_session_file.stop()
        self.patch_projects_dir.stop()
        self.tmpdir.cleanup()

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url", return_value="http://test")
    def test_health(self, mock_backend, mock_urlopen):
        mock_urlopen.return_value = MockResponse(json.dumps({"status": "healthy"}).encode())
        result = self.runner.invoke(cli, ["health"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("healthy", result.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url", return_value="http://test")
    def test_sectors_list(self, mock_backend, mock_urlopen):
        sectors = [
            {"ticker": "XLK", "name": "Technology", "perf_3m": 0.12, "perf_6m": 0.08, "spread": 0.04}
        ]
        mock_urlopen.return_value = MockResponse(json.dumps(sectors).encode())
        result = self.runner.invoke(cli, ["sectors", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("XLK", result.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url", return_value="http://test")
    def test_screener_scan_and_status(self, mock_backend, mock_urlopen):
        def urlopen_side_effect(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
            if "/screener/scan" in url:
                return MockResponse(json.dumps({"scan_id": "scan-abc", "status": "pending"}).encode())
            if "/screener/status/scan-abc" in url:
                return MockResponse(json.dumps({"scan_id": "scan-abc", "status": "completed", "progress": 100}).encode())
            return MockResponse(json.dumps({}).encode())
        mock_urlopen.side_effect = urlopen_side_effect

        result = self.runner.invoke(cli, ["screener", "scan", "--mode", "dormant_giant", "--no-ai"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("scan-abc", result.output)

        result2 = self.runner.invoke(cli, ["screener", "status", "scan-abc"])
        self.assertEqual(result2.exit_code, 0)
        self.assertIn("completed", result2.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url", return_value="http://test")
    def test_quantgen_generate(self, mock_backend, mock_urlopen):
        mock_urlopen.return_value = MockResponse(json.dumps({
            "success": True,
            "data": {"code": "import vectorbt as vbt\n", "output": "ok"},
            "attempts": 1,
        }).encode())
        result = self.runner.invoke(cli, [
            "quantgen", "generate",
            "--prompt", "SMA crossover",
            "--tickers", "AAPL,MSFT",
        ])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("success", result.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url", return_value="http://test")
    def test_strategies_list(self, mock_backend, mock_urlopen):
        mock_urlopen.return_value = MockResponse(json.dumps({
            "success": True,
            "data": {"strategies": ["sma.py", "ema.py"], "count": 2}
        }).encode())
        result = self.runner.invoke(cli, ["strategies", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("sma.py", result.output)

    def test_project_create_and_show(self):
        result = self.runner.invoke(cli, ["projects", "create", "test-proj"])
        self.assertEqual(result.exit_code, 0)

        result2 = self.runner.invoke(cli, ["projects", "show", "test-proj"])
        self.assertEqual(result2.exit_code, 0)
        self.assertIn("test-proj", result2.output)

    def test_config_set_and_show(self):
        result = self.runner.invoke(cli, ["config", "set-url", "http://new:9000"])
        self.assertEqual(result.exit_code, 0)

        result2 = self.runner.invoke(cli, ["--json", "config", "show"])
        self.assertEqual(result2.exit_code, 0)
        cfg = json.loads(result2.output)
        self.assertEqual(cfg["backend_url"], "http://new:9000")

    def test_json_output_flag(self):
        result = self.runner.invoke(cli, ["--json", "config", "show"])
        self.assertEqual(result.exit_code, 0)
        parsed = json.loads(result.output)
        self.assertIn("backend_url", parsed)

    def test_repl_exit(self):
        result = self.runner.invoke(cli, ["repl"], input="exit\n")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("REPL", result.output)

    def test_screener_list_empty(self):
        result = self.runner.invoke(cli, ["screener", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No tracked scans", result.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url")
    def test_screener_ai_report(self, mock_backend, mock_urlopen):
        mock_backend.return_value = "http://test"
        mock_urlopen.return_value = MockResponse(json.dumps({
            "scan_id": "abc-123",
            "ai_report": "Report text here"
        }).encode())
        result = self.runner.invoke(cli, ["screener", "ai-report", "abc-123"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Report text here", result.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url")
    def test_screener_health(self, mock_backend, mock_urlopen):
        mock_backend.return_value = "http://test"
        mock_urlopen.return_value = MockResponse(json.dumps({
            "status": "healthy",
            "active_scans": 2,
            "modes_available": ["dormant_giant", "quant_strategy"]
        }).encode())
        result = self.runner.invoke(cli, ["screener", "health"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("healthy", result.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url")
    def test_quantgen_true_wfo(self, mock_backend, mock_urlopen):
        mock_backend.return_value = "http://test"
        mock_urlopen.return_value = MockResponse(json.dumps({
            "success": True,
            "data": {"output": "WFO complete"}
        }).encode())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import vectorbt as vbt\n")
            tmp = f.name
        try:
            result = self.runner.invoke(cli, ["quantgen", "true-wfo", "--file", tmp])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("WFO complete", result.output)
        finally:
            os.unlink(tmp)

    def test_projects_notes(self):
        self.runner.invoke(cli, ["projects", "create", "notes-test"])
        result = self.runner.invoke(cli, ["projects", "notes", "notes-test", "--set", "Q1 notes"])
        self.assertEqual(result.exit_code, 0)
        result2 = self.runner.invoke(cli, ["projects", "notes", "notes-test"])
        self.assertEqual(result2.exit_code, 0)
        self.assertIn("Q1 notes", result2.output)

    def test_projects_add_scan(self):
        self.runner.invoke(cli, ["projects", "create", "scan-test"])
        result = self.runner.invoke(cli, ["projects", "add-scan", "scan-test", "scan-xyz"])
        self.assertEqual(result.exit_code, 0)
        result2 = self.runner.invoke(cli, ["projects", "show", "scan-test"])
        self.assertIn("scan-xyz", result2.output)

    def test_projects_add_strategy(self):
        self.runner.invoke(cli, ["projects", "create", "strat-test"])
        result = self.runner.invoke(cli, ["projects", "add-strategy", "strat-test", "sma_cross"])
        self.assertEqual(result.exit_code, 0)
        result2 = self.runner.invoke(cli, ["projects", "show", "strat-test"])
        self.assertIn("sma_cross", result2.output)

    @patch("cli_anything.tradecraft.utils.api_client.urllib.request.urlopen")
    @patch("cli_anything.tradecraft.utils.api_client.get_backend_url")
    def test_screener_scan_with_filters(self, mock_backend, mock_urlopen):
        mock_backend.return_value = "http://test"
        mock_urlopen.return_value = MockResponse(json.dumps({
            "scan_id": "scan-filt", "status": "pending"
        }).encode())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"min_price": 10.0}, f)
            tmp = f.name
        try:
            result = self.runner.invoke(cli, [
                "screener", "scan", "--mode", "dormant_giant",
                "--filters", tmp, "--no-ai"
            ])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("scan-filt", result.output)
        finally:
            os.unlink(tmp)


class TestCLISubprocess(unittest.TestCase):
    """Test the installed CLI via subprocess."""

    @staticmethod
    def _resolve_cli(name: str) -> str:
        """Resolve CLI command path, preferring installed version."""
        force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "")
        if force in ("1", "true", "yes"):
            return name
        # Prefer installed binary
        result = subprocess.run(["which", name], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # Fallback to Python module execution
        return f"{sys.executable} -m cli_anything.tradecraft.tradecraft_cli"

    def setUp(self):
        self.cli_cmd = self._resolve_cli("cli-anything-tradecraft")

    def _run(self, args: str) -> subprocess.CompletedProcess:
        cmd = shlex.split(self.cli_cmd) + shlex.split(args)
        return subprocess.run(cmd, capture_output=True, text=True)

    @unittest.skipIf(
        os.environ.get("CLI_ANYTHING_FORCE_INSTALLED") not in ("1", "true", "yes"),
        "CLI_ANYTHING_FORCE_INSTALLED not set",
    )
    def test_installed_help(self):
        result = self._run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("TradeCraft CLI", result.stdout)

    @unittest.skipIf(
        os.environ.get("CLI_ANYTHING_FORCE_INSTALLED") not in ("1", "true", "yes"),
        "CLI_ANYTHING_FORCE_INSTALLED not set",
    )
    def test_installed_sectors_list(self):
        result = self._run("--json sectors list")
        self.assertIn(result.returncode, [0, 1])  # 0 if backend up, 1 if down


if __name__ == "__main__":
    unittest.main()
