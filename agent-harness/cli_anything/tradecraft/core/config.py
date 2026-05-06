"""Configuration management for cli-anything-tradecraft.

Stores backend URL and user preferences in ~/.config/cli-anything-tradecraft/config.json.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


CONFIG_DIR = Path.home() / ".config" / "cli-anything-tradecraft"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "backend_url": "http://localhost:8000",
    "output_format": "table",  # table | json | csv
    "timeout": 120,
    "auto_save": True,
}


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(config: Dict[str, Any]) -> None:
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_backend_url() -> str:
    env_url = os.environ.get("TRADECRAFT_BACKEND_URL")
    if env_url:
        return env_url.rstrip("/")
    url = load_config().get("backend_url", DEFAULT_CONFIG["backend_url"])
    return url.rstrip("/")


def set_backend_url(url: str) -> None:
    config = load_config()
    config["backend_url"] = url.rstrip("/")
    save_config(config)


def get_timeout() -> int:
    return load_config().get("timeout", DEFAULT_CONFIG["timeout"])


def get_output_format() -> str:
    return load_config().get("output_format", DEFAULT_CONFIG["output_format"])


def set_output_format(fmt: str) -> None:
    config = load_config()
    config["output_format"] = fmt
    save_config(config)
