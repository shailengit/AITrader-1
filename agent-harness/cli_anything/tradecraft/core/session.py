"""Session state for tradecraft CLI."""
import json
from pathlib import Path
from typing import Dict, Any, Optional

from cli_anything.tradecraft.core.config import CONFIG_DIR

SESSION_FILE = CONFIG_DIR / "session.json"

def _ensure() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_session() -> Dict[str, Any]:
    _ensure()
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_session(data: Dict[str, Any]) -> None:
    _ensure()
    SESSION_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

def get(key: str, default: Any = None) -> Any:
    return load_session().get(key, default)

def set_key(key: str, value: Any) -> None:
    data = load_session()
    data[key] = value
    save_session(data)
