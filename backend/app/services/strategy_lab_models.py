"""Ollama manifest scanner for the AI Strategy Builder.

Reads ~/.ollama/models/manifests/registry.ollama.ai/library/ and returns
a structured list of available models + their variants.

Each model has one or more variants. A variant is either:
  - "cloud" if its manifest has `"layers": null` (no local weights)
  - "local" if its manifest has populated `"layers"` (model is downloaded)

Manifest files are JSON blobs in `{model_root}/{model_name}/{variant}`.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional


DEFAULT_MANIFEST_ROOT = os.path.expanduser(
    "~/.ollama/models/manifests/registry.ollama.ai/library"
)


def list_ollama_models(manifest_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all Ollama models and their variants.

    Args:
        manifest_root: Path to the library directory. Defaults to
            ~/.ollama/models/manifests/registry.ollama.ai/library.
            Can be overridden via STRATEGY_LAB_OLLAMA_ROOT env var.

    Returns:
        List of {"id": "model-name", "variants": [{"name": "cloud"|"7b", "type": "cloud"|"local", "size_bytes": int?}]}
        Returns [] if the root doesn't exist.
    """
    root_str = (
        manifest_root
        or os.environ.get("STRATEGY_LAB_OLLAMA_ROOT")
        or DEFAULT_MANIFEST_ROOT
    )
    root = Path(root_str)
    if not root.exists() or not root.is_dir():
        return []

    models: List[Dict[str, Any]] = []
    for model_dir in sorted(root.iterdir()):
        if not model_dir.is_dir():
            continue
        variants: List[Dict[str, Any]] = []
        for variant_file in sorted(model_dir.iterdir()):
            if not variant_file.is_file():
                continue
            try:
                data = json.loads(variant_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            variant = _parse_variant(variant_file.name, data)
            if variant is not None:
                variants.append(variant)
        if variants:
            models.append({"id": model_dir.name, "variants": variants})
    return models


def _parse_variant(name: str, manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn a manifest file into a {name, type, size_bytes?} dict."""
    layers = manifest.get("layers")
    if layers is None:
        return {"name": name, "type": "cloud"}
    # Sum model-weight layers only (filter out system/license/params)
    size = sum(
        layer.get("size", 0)
        for layer in layers
        if layer.get("mediaType", "").endswith("ollama.image.model")
    )
    return {"name": name, "type": "local", "size_bytes": size}
