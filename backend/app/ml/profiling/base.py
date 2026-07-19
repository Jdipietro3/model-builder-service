"""Profiler interface and registry.

A profiler turns an uploaded file into the structured, token-compact summary
the orchestrator (and the user) sees before any framing decision is made.
Profilers are registered per data shape; new data types (images, time series...)
plug in by implementing Profiler and calling register().
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Profiler(Protocol):
    data_shape: str  # "tabular"; future: "image", "timeseries", ...
    extensions: tuple[str, ...]  # file suffixes this profiler handles, e.g. (".csv",)

    def profile(self, path: str) -> dict[str, Any]: ...


_REGISTRY: list[Profiler] = []


def register(profiler: Profiler) -> Profiler:
    _REGISTRY.append(profiler)
    return profiler


def get_profiler(path: str) -> Profiler:
    suffix = Path(path).suffix.lower()
    for profiler in _REGISTRY:
        if suffix in profiler.extensions:
            return profiler
    supported = sorted({ext for p in _REGISTRY for ext in p.extensions})
    raise ValueError(f"Unsupported file type '{suffix}'. Supported: {', '.join(supported)}")
