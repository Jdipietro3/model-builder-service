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
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SPECS_DIR = Path(__file__).resolve().parent / "specs"

logger = logging.getLogger(__name__)


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
    task_family: Literal["supervised", "forecasting", "clustering", "anomaly", "ensemble"]
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
        elif self.data_shape == "timeseries":
            # Forecasting specs frame the series one of two ways; extra keys
            # (lags, rolling_windows, calendar_features) ride alongside framing.
            ts = self.preprocessing.get("timeseries")
            if not isinstance(ts, dict) or ts.get("framing") not in ("prophet", "lag_features"):
                raise ValueError(
                    "preprocessing.timeseries.framing must be 'prophet' or 'lag_features' "
                    "for timeseries data_shape"
                )
        # Reserved preprocessing sub-shapes for future data_shapes (not yet enforced —
        # no specs exist for them). Planned keys:
        #   text:  tokenizer, max_length, vectorizer
        #   image: resize, normalize, augmentation

        if self.task_family == "supervised":
            # Each declared task_type must have a metrics entry.
            for tt in self.task_types:
                if tt not in self.metrics:
                    raise ValueError(f"metrics missing entry for supervised task_type '{tt}'")
        # Label-free families (forecasting/clustering/anomaly) may use a flat
        # {default, supported} metrics block — no per-task_type keys required.
        return self


_module_available_cache: dict[str, bool] = {}


def _module_available(module_name: str) -> bool:
    if module_name not in _module_available_cache:
        try:
            importlib.import_module(module_name)
            _module_available_cache[module_name] = True
        except Exception:
            # Deliberately broad. A library can be installed yet unusable, and
            # it does not always fail as ImportError: xgboost raises
            # XGBoostError (a ValueError) when it cannot load xgboost.dll, which
            # is what happens on Windows machines with Smart App Control
            # enabled ("[WinError 4551] An Application Control policy has
            # blocked this file"). Catching only ImportError let that escape
            # and took the whole registry down at import time, rather than
            # swapping in the sklearn fallback the spec already declares.
            _module_available_cache[module_name] = False
    return _module_available_cache[module_name]


@lru_cache(maxsize=1)
def load_registry() -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for path in sorted(SPECS_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        try:
            spec = MethodologySpec(**(raw or {})).model_dump()
        except (ValidationError, TypeError) as e:
            raise ValueError(f"Invalid spec {path.name}: {e}") from e
        module_name = spec["model"]["class"].split(".")[0]
        if not _module_available(module_name):
            if "fallback" in spec["model"]:
                # Library missing but a sklearn fallback is declared: swap it in
                # so the methodology slot still works.
                fb = spec["model"]["fallback"]
                spec["model"] = {"class": fb["class"], "params": fb.get("params", {}), "grid": fb.get("grid", {})}
                spec["display_name"] += " (sklearn fallback)"
            else:
                # No fallback: the spec is unusable on this machine — drop it.
                logger.warning(
                    "Excluding spec '%s': required module '%s' is not installed",
                    spec["id"],
                    module_name,
                )
                continue
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
