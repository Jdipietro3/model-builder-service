"""Loads the curated methodology library from YAML specs.

Each spec declares preprocessing, model class, default params, and a small
tuning grid. The orchestrator LLM chooses *among* these specs; it never
defines training logic itself.
"""

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SPECS_DIR = Path(__file__).resolve().parent / "specs"

REQUIRED_FIELDS = {"id", "display_name", "task_types", "when_to_use", "preprocessing", "model", "metrics"}


def _lightgbm_available() -> bool:
    try:
        importlib.import_module("lightgbm")
        return True
    except ImportError:
        return False


@lru_cache(maxsize=1)
def load_registry() -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    use_fallback = not _lightgbm_available()
    for path in sorted(SPECS_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        missing = REQUIRED_FIELDS - set(spec)
        if missing:
            raise ValueError(f"Spec {path.name} missing fields: {missing}")
        # If LightGBM isn't installed, transparently swap in the declared
        # sklearn fallback so the methodology slot still works.
        if use_fallback and "fallback" in spec["model"]:
            fb = spec["model"]["fallback"]
            spec["model"] = {"class": fb["class"], "params": fb.get("params", {}), "grid": fb.get("grid", {})}
            spec["display_name"] += " (sklearn fallback)"
        registry[spec["id"]] = spec
    return registry


def get_spec(methodology_id: str) -> dict[str, Any]:
    registry = load_registry()
    if methodology_id not in registry:
        raise KeyError(
            f"Unknown methodology '{methodology_id}'. Available: {', '.join(sorted(registry))}"
        )
    return registry[methodology_id]


def list_methodologies(task_type: str | None = None) -> list[dict[str, Any]]:
    """Summaries the orchestrator reads when choosing an approach."""
    out = []
    for spec in load_registry().values():
        if task_type and task_type not in spec["task_types"]:
            continue
        out.append(
            {
                "id": spec["id"],
                "display_name": spec["display_name"],
                "task_types": spec["task_types"],
                "when_to_use": spec["when_to_use"].strip(),
                "metrics": spec["metrics"],
            }
        )
    return out


def resolve_model_class(class_path: str):
    module_path, class_name = class_path.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), class_name)
