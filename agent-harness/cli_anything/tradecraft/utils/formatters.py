"""Text formatting utilities.
"""

from typing import Any, Dict, List


def flatten_dict(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested dict for tabular display."""
    result: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            result.update(flatten_dict(v, key + "."))
        else:
            result[key] = v
    return result
