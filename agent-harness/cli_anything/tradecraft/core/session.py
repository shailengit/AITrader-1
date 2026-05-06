"""Session state management for cli-anything-tradecraft.

Tracks active scans, strategy jobs, and transient state.
Auto-saves after one-shot mutations unless --dry-run is set.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from cli_anything.tradecraft.core.config import ensure_config_dir

SESSION_FILE = Path.home() / ".config" / "cli-anything-tradecraft" / "session.json"


def _load_raw() -> Dict[str, Any]:
    ensure_config_dir()
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_raw(data: Dict[str, Any]) -> None:
    ensure_config_dir()
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


class Session:
    """In-memory session with optional auto-save."""

    def __init__(self, dry_run: bool = False):
        self._data = _load_raw()
        self.dry_run = dry_run

    def _touch(self) -> None:
        self._data["last_activity"] = datetime.now().isoformat()
        if not self.dry_run:
            _save_raw(self._data)

    def get_scans(self) -> List[Dict[str, Any]]:
        return self._data.get("scans", [])

    def add_scan(self, scan_id: str, mode: str, use_ai: bool) -> None:
        scans = self._data.setdefault("scans", [])
        scans.insert(0, {
            "scan_id": scan_id,
            "mode": mode,
            "use_ai": use_ai,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        })
        self._touch()

    def update_scan_status(self, scan_id: str, status: str) -> None:
        scans = self._data.get("scans", [])
        for s in scans:
            if s.get("scan_id") == scan_id:
                s["status"] = status
                break
        self._touch()

    def remove_scan(self, scan_id: str) -> None:
        scans = self._data.get("scans", [])
        self._data["scans"] = [s for s in scans if s.get("scan_id") != scan_id]
        self._touch()

    def get_strategies(self) -> List[Dict[str, Any]]:
        return self._data.get("strategies", [])

    def add_strategy(self, name: str, path: str) -> None:
        strategies = self._data.setdefault("strategies", [])
        strategies.insert(0, {
            "name": name,
            "path": path,
            "created_at": datetime.now().isoformat()
        })
        self._touch()

    def remove_strategy(self, name: str) -> None:
        strategies = self._data.get("strategies", [])
        self._data["strategies"] = [s for s in strategies if s.get("name") != name]
        self._touch()

    def clear(self) -> None:
        self._data = {}
        if not self.dry_run:
            _save_raw(self._data)
