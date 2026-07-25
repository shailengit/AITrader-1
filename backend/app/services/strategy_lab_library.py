"""Strategy Library — saves and loads strategy code to/from disk.

Each strategy gets a folder under strategies/library/<name>/ with numbered
versions (v1/, v2/, ...). Each version contains:
  - strategy.py — the complete strategy code
  - meta.json — metadata (prompt, plan, KPIs, change description)
"""
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

LIBRARY_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "strategies" / "library"


def _strategy_dir(name: str) -> Path:
    """Get the directory for a strategy, creating it if needed."""
    safe_name = name.lower().replace(" ", "-").replace("_", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-.")
    if not safe_name:
        safe_name = "unnamed"
    d = LIBRARY_ROOT / safe_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_version(name: str) -> int:
    """Return the next version number for a strategy."""
    d = _strategy_dir(name)
    existing = [p for p in d.iterdir() if p.is_dir() and p.name.startswith("v")]
    if not existing:
        return 1
    versions = []
    for p in existing:
        try:
            versions.append(int(p.name[1:]))
        except ValueError:
            continue
    return max(versions) + 1 if versions else 1


def save_strategy(
    name: str,
    code: str,
    prompt: str = "",
    plan: str = "",
    kpis: Optional[Dict[str, Any]] = None,
    change_description: str = "",
    model_id: str = "",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Save a strategy version to the library. Returns metadata dict."""
    version = _next_version(name)
    d = _strategy_dir(name) / f"v{version}"
    d.mkdir(parents=True, exist_ok=True)

    # Write code
    (d / "strategy.py").write_text(code)

    # Write metadata
    meta = {
        "version": version,
        "strategy_name": name,
        "prompt": prompt,
        "plan": plan,
        "created_at": datetime.now().isoformat(),
        "backtest_kpis": kpis or {},
        "change_description": change_description or f"Version {version}",
        "model_id": model_id,
        "session_id": session_id or "",
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2, default=str))

    logger.info("Saved strategy %s v%d to %s", name, version, d)
    return meta


def list_strategies() -> List[Dict[str, Any]]:
    """List all saved strategies with their latest version info."""
    if not LIBRARY_ROOT.exists():
        return []
    strategies = []
    for d in sorted(LIBRARY_ROOT.iterdir()):
        if not d.is_dir():
            continue
        versions = []
        for vd in sorted(d.iterdir()):
            if not vd.is_dir() or not vd.name.startswith("v"):
                continue
            meta_path = vd / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    meta["folder"] = str(vd.relative_to(LIBRARY_ROOT.parent))
                    versions.append(meta)
                except (json.JSONDecodeError, OSError):
                    continue
        if versions:
            versions.sort(key=lambda v: v.get("version", 0))
            strategies.append({
                "name": d.name,
                "display_name": versions[-1].get("strategy_name", d.name),
                "versions": versions,
                "latest_version": versions[-1],
                "version_count": len(versions),
            })
    strategies.sort(key=lambda s: s["latest_version"].get("created_at", ""), reverse=True)
    return strategies


def get_strategy(name: str) -> Optional[Dict[str, Any]]:
    """Get full details for a strategy by folder name."""
    d = LIBRARY_ROOT / name
    if not d.exists():
        return None
    versions = []
    for vd in sorted(d.iterdir()):
        if not vd.is_dir() or not vd.name.startswith("v"):
            continue
        meta_path = vd / "meta.json"
        code_path = vd / "strategy.py"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                meta["folder"] = str(vd.relative_to(LIBRARY_ROOT.parent))
                if code_path.exists():
                    meta["code"] = code_path.read_text()
                versions.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
    if not versions:
        return None
    versions.sort(key=lambda v: v.get("version", 0))
    return {
        "name": d.name,
        "display_name": versions[-1].get("strategy_name", d.name),
        "versions": versions,
    }
