"""Deterministic training executor (dispatcher).

Takes an approved plan + methodology spec and routes it to the right data source
and task runner in ``app.ml.pipeline``. All behavior downstream is hand-written and
reproducible — the LLM only chose the plan, it never defines what happens here.

The monolithic load/train/evaluate body that used to live in this module now lives
behind the ``DataSource`` / ``TaskRunner`` contracts so new data shapes and task
families plug in without editing the dispatcher.
"""

from typing import Callable

from .pipeline import RunOutcome, get_runner, get_source
from .registry.loader import get_spec

ProgressCb = Callable[[str, int, str], None]


def run_plan(path: str, plan: dict, progress: ProgressCb) -> RunOutcome:
    """Resolve the spec's data shape + task family, then load and run."""
    spec = get_spec(plan["methodology_id"])
    # Defaults hold until the YAML specs gain data_shape/task_family (schema v2).
    data_shape = spec.get("data_shape", "tabular")
    task_family = spec.get("task_family", "supervised")

    source = get_source(data_shape)
    runner = get_runner(task_family)
    if data_shape not in runner.compatible_shapes:
        raise ValueError(
            f"Task family '{task_family}' is not compatible with data shape "
            f"'{data_shape}' (accepts: {', '.join(runner.compatible_shapes)})"
        )

    data = source.load(path, plan, progress)
    return runner.run(data, spec, plan, progress)
