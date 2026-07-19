"""Anomaly-detection task runner (scaffold).

Contract this will lock in when implemented:
- Unsupervised (or weakly labelled): no target column; the model learns a notion of
  "normal" from the bulk of the ``tabular`` payload.
- Output is a per-row anomaly score (higher = more anomalous) plus a flagged subset.
- Evaluation uses precision@k against any available labels, or reconstruction-error
  distributions when labels are absent; ``RunOutcome.results`` carries the common
  spine plus a ``scores`` block. ``artifact`` is the fitted detector.
"""

from .base import LoadedData, ProgressCb, RunOutcome, register_runner


class AnomalyRunner:
    task_family = "anomaly"
    compatible_shapes = ("tabular",)

    def run(self, data: LoadedData, spec: dict, plan: dict, progress: ProgressCb) -> RunOutcome:
        raise NotImplementedError("anomaly runner not yet implemented")


register_runner(AnomalyRunner())
