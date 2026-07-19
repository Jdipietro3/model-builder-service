"""Loads the curated methodology library from YAML specs.

Each spec declares preprocessing, model class, default params, and a small
tuning grid. The orchestrator LLM chooses *among* these specs; it never
defines training logic itself.

Specs are validated on load against the typed ``MethodologySpec`` (pydantic v2),
but ``load_registry()`` returns plain ``dict``s (via ``model_dump()``) because
every downstream consumer indexes the spec as a mapping
(``spec["model"]["class"]``, ``spec["metrics"][task_type]["supported"]``, ...).
"""

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SPECS_DIR = Path(__file__).resolve().parent / "specs"


class ComputeSpec(BaseModel):
    device: Literal["cpu", "gpu"] = "cpu"
    requires_gpu: bool = False


class MethodologySpec(BaseModel):
    """Typed view of one YAML spec. Validated on load; dumped back to a dict."""

    # `model` is a legitimate field here; opt out of pydantic's model_ namespace guard.
    model_config = ConfigDict(protected_namespaces=())

    id: str
    display_name: str
    data_shape: Literal["tabular", "timeseries", "text", "image"]
    task_family: Literal["supervised", "forecasting", "clustering", "anomaly"]
    task_types: list[str] = Field(default_factory=list)  # meaningful only for supervised
    when_to_use: str
    compute: ComputeSpec = Field(default_factory=ComputeSpec)
    # Kept loose (plain dicts) on purpose: build_pipeline / the fallback-swap logic
    # operate on these as mappings. Shape is enforced per data_shape below.
    preprocessing: dict[str, Any]
    model: dict[str, Any]
    metrics: dict[str, Any]

    @model_validator(mode="after")
    def _validate_shapes(self) -> "MethodologySpec":
        if "class" not in self.model:
            raise ValueError("model.class is required")

        if self.data_shape == "tabular":
            # build_pipeline consumes numeric.impute / categorical.impute.
            for group in ("numeric", "categorical"):
                sub = self.preprocessing.get(group)
                if not isinstance(sub, dict) or not isinstance(sub.get("impute"), str):
                    raise ValueError(
                        f"preprocessing.{group}.impute (str) is required for tabular data_shape"
                    )
        # Reserved preprocessing sub-shapes for future data_shapes (not yet enforced —
        # no specs exist for them). Planned keys:
        #   timeseries: window, horizon, freq, scaling
        #   text:       tokenizer, max_length, vectorizer
        #   image:      resize, normalize, augmentation

        if self.task_family == "supervised":
            # Each declared task_type must have a metrics entry.
            for tt in self.task_types:
                if tt not in self.metrics:
                    raise ValueError(f"metrics missing entry for supervised task_type '{tt}'")
        # Label-free families (forecasting/clustering/anomaly) may use a flat
        # {default, supported} metrics block — no per-task_type keys required.
        return self


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
            raw = yaml.safe_load(f)
        try:
            spec = MethodologySpec(**(raw or {})).model_dump()
        except (ValidationError, TypeError) as e:
            raise ValueError(f"Invalid spec {path.name}: {e}") from e
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


def list_methodologies(
    task_type: str | None = None,
    data_shape: str | None = None,
    task_family: str | None = None,
) -> list[dict[str, Any]]:
    """Summaries the orchestrator reads when choosing an approach.

    Filters by any provided axis (task_type matches against a spec's task_types).
    """
    out = []
    for spec in load_registry().values():
        if task_type and task_type not in spec["task_types"]:
            continue
        if data_shape and spec["data_shape"] != data_shape:
            continue
        if task_family and spec["task_family"] != task_family:
            continue
        out.append(
            {
                "id": spec["id"],
                "display_name": spec["display_name"],
                "data_shape": spec["data_shape"],
                "task_family": spec["task_family"],
                "task_types": spec["task_types"],
                "when_to_use": spec["when_to_use"].strip(),
                "metrics": spec["metrics"],
            }
        )
    return out


def resolve_model_class(class_path: str):
    module_path, class_name = class_path.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), class_name)
