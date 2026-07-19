"""Pipeline execution contracts: data sources, task runners, and their registries.

The training executor is split along two axes so that new problem types plug in
without touching the dispatcher:

- **Data shape** (how bytes on disk become an in-memory payload): tabular today;
  timeseries / text / image later. A ``DataSource`` owns loading + profiling for
  one shape and hands back a ``LoadedData``.
- **Task family** (what we *do* with that payload): supervised today; forecasting,
  clustering, anomaly detection later. A ``TaskRunner`` consumes a ``LoadedData``
  plus a methodology spec and produces a ``RunOutcome``.

A methodology spec names one ``data_shape`` and one ``task_family``; the dispatcher
looks each up here and checks the runner declares the shape as compatible before
executing. Registries mirror the ergonomics of ``profiling/base.py`` — a miss raises
``ValueError`` listing the supported keys.

Results-envelope contract (cross-family)
----------------------------------------
Every ``RunOutcome.results`` dict is what gets stored on the ``Run`` row and rendered
by the frontend. To stay renderable across families, all families share a common
spine of keys::

    {
        "methodology":   {"id": ..., "display_name": ...},
        "data_shape":    "tabular" | "timeseries" | ...,
        "task_family":   "supervised" | "forecasting" | ...,
        "primary_metric": "<friendly metric name>",
        ...
    }

Family-specific detail keys (e.g. ``holdout`` / ``confusion_matrix`` for supervised,
``clusters`` for clustering) are allowed alongside the common spine. The frontend
keys off ``task_family`` to decide which detail keys to expect.

Forecasting envelope (``task_family == "forecasting"``, ``data_shape == "timeseries"``)::

    {
        "methodology":   {"id": ..., "display_name": ...},
        "task_type":     "forecasting",
        "data_shape":    "timeseries",
        "task_family":   "forecasting",
        "target_column": ..., "time_column": ...,
        "horizon":       <int future periods>,
        "freq":          <pandas freq string or None>,
        "primary_metric": <friendly metric name; all forecasting metrics lower-is-better>,
        "best_params":   {...},
        "cv":            {"metric", "mean", "std", "n_splits"},   # rolling-origin backtest
        "holdout": {
            "metrics":            {mase, mape, smape, rmse, mae},
            "baseline_metrics":   {...},                          # seasonal-naive
            "baseline_description": "Seasonal-naive baseline (... m=<period>)",
        },
        "holdout_series": {"timestamps", "actual", "predicted", "lower", "upper"},
        "forecast":       {"timestamps", "yhat", "lower", "upper"},   # future horizon
        "history_tail":   {"timestamps", "actual"},                  # last min(3*horizon, n) rows
        "caveats":        [...],
        "n_train":        <int>, "n_test": <int == horizon>,
        "training_seconds": <float>,
    }

All timestamps are ISO strings and all series are plain lists of rounded floats, so the
whole dict is JSON-serialisable (it is stored in a JSON column). The frontend keys off
``task_family`` to decide which detail keys to expect.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

ProgressCb = Callable[[str, int, str], None]


@dataclass
class LoadedData:
    """The output of a ``DataSource.load`` — a profiled, in-memory payload.

    ``payload`` is intentionally untyped: a pandas ``DataFrame`` for the tabular
    shape today, but a file manifest / DataLoader-style object / torch ``Dataset``
    for image and text shapes tomorrow. Runners narrow it per ``data_shape``.
    """

    data_shape: str
    profile: dict
    payload: Any


@dataclass
class RunOutcome:
    """Everything a completed run produces, decoupled from how it's stored.

    ``results`` is the frontend-facing envelope (see module docstring); ``artifact``
    is whatever the bundler serializes (a fitted sklearn pipeline for supervised, a
    model payload for other families); ``meta`` carries the side-channel the bundler
    needs (feature columns, label classes, best params, task tags, ...).
    """

    results: dict
    artifact: Any
    meta: dict = field(default_factory=dict)


@runtime_checkable
class DataSource(Protocol):
    data_shape: str  # "tabular"; future: "timeseries", "text", "image"

    def load(self, path: str, plan: dict, progress: ProgressCb) -> LoadedData: ...


@runtime_checkable
class TaskRunner(Protocol):
    task_family: str  # "supervised"; future: "forecasting", "clustering", "anomaly"
    compatible_shapes: tuple[str, ...]  # data_shapes this runner accepts

    def run(self, data: LoadedData, spec: dict, plan: dict, progress: ProgressCb) -> RunOutcome: ...


_SOURCES: dict[str, DataSource] = {}
_RUNNERS: dict[str, TaskRunner] = {}


def register_source(source: DataSource) -> DataSource:
    """Register a data source under its ``data_shape``. Pass an instance."""
    _SOURCES[source.data_shape] = source
    return source


def register_runner(runner: TaskRunner) -> TaskRunner:
    """Register a task runner under its ``task_family``. Pass an instance."""
    _RUNNERS[runner.task_family] = runner
    return runner


def get_source(data_shape: str) -> DataSource:
    try:
        return _SOURCES[data_shape]
    except KeyError:
        supported = ", ".join(sorted(_SOURCES)) or "(none registered)"
        raise ValueError(f"No data source for shape '{data_shape}'. Supported: {supported}")


def get_runner(task_family: str) -> TaskRunner:
    try:
        return _RUNNERS[task_family]
    except KeyError:
        supported = ", ".join(sorted(_RUNNERS)) or "(none registered)"
        raise ValueError(f"No task runner for family '{task_family}'. Supported: {supported}")
