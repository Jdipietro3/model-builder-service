"""Pipeline package: pluggable data sources + task runners behind a registry.

Importing ``app.ml.pipeline`` is enough to make every source/runner available —
each submodule registers its instance at import time, so we import them all here
for their side effects. See ``base`` for the contracts and the results-envelope
documentation.
"""

from .base import (
    DataSource,
    LoadedData,
    RunOutcome,
    TaskRunner,
    get_runner,
    get_source,
    register_runner,
    register_source,
)

# Import for registration side effects (data shapes).
from . import image_source, tabular_source, text_source, timeseries_source  # noqa: E402,F401

# Import for registration side effects (task families).
from . import anomaly, clustering, forecasting, supervised  # noqa: E402,F401

# deep_learning is shared machinery, not a registered runner — imported so the
# EpochTrainer base is reachable as app.ml.pipeline.deep_learning.
from . import deep_learning  # noqa: E402,F401

__all__ = [
    "DataSource",
    "LoadedData",
    "RunOutcome",
    "TaskRunner",
    "get_runner",
    "get_source",
    "register_runner",
    "register_source",
]
