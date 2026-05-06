"""Project context for cli-anything-tradecraft.

A project groups related scans, strategies, and settings.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from cli_anything.tradecraft.core.config import ensure_config_dir

PROJECTS_DIR = Path.home() / ".config" / "cli-anything-tradecraft" / "projects"


def _project_path(name: str) -> Path:
    safe = Path(name).name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECTS_DIR / f"{safe}.json"


class Project:
    """A project encapsulates a trading research context."""

    def __init__(self, name: str):
        self.name = name
        self._path = _project_path(name)
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "name": self.name,
            "scans": [],
            "strategies": [],
            "notes": ""
        }

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)

    def add_scan(self, scan_id: str) -> None:
        scans = self._data.setdefault("scans", [])
        if scan_id not in scans:
            scans.append(scan_id)
        self.save()

    def add_strategy(self, name: str) -> None:
        strategies = self._data.setdefault("strategies", [])
        if name not in strategies:
            strategies.append(name)
        self.save()

    def list_scans(self) -> List[str]:
        return self._data.get("scans", [])

    def list_strategies(self) -> List[str]:
        return self._data.get("strategies", [])

    def set_notes(self, notes: str) -> None:
        self._data["notes"] = notes
        self.save()

    def get_notes(self) -> str:
        return self._data.get("notes", "")

    @staticmethod
    def list_all() -> List[str]:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        names = []
        for p in PROJECTS_DIR.glob("*.json"):
            names.append(p.stem)
        return sorted(names)

    @staticmethod
    def delete(name: str) -> bool:
        path = _project_path(name)
        if path.exists():
            path.unlink()
            return True
        return False
