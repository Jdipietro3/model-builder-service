"""Dataset profiling: the structured summary the orchestrator (and the user)
sees before any framing decision is made.

profile_path() dispatches to the right profiler by file type; the tabular
helpers are re-exported for existing callers and for training code that
works with dataframes directly.
"""

from typing import Any

from .base import Profiler, get_profiler, register
from .tabular import TabularProfiler, load_csv, profile_csv, profile_dataframe

__all__ = [
    "Profiler",
    "TabularProfiler",
    "get_profiler",
    "load_csv",
    "profile_csv",
    "profile_dataframe",
    "profile_path",
    "register",
]


def profile_path(path: str) -> dict[str, Any]:
    """Profile any supported file, dispatching on its extension."""
    return get_profiler(path).profile(path)
