"""Clustering task runner (scaffold).

Contract this will lock in when implemented:
- Unsupervised: there is no target column; the model is fit on all rows.
- Works over ``tabular`` or ``text`` payloads (text is vectorized in-runner).
- Evaluation uses intrinsic metrics (silhouette, Davies-Bouldin) since there is no
  ground truth; ``RunOutcome.results`` carries the common spine plus a ``clusters``
  block (per-cluster sizes/centroids) and the cluster-assignment output.
- ``artifact`` is the fitted clusterer (must support assigning new rows).
"""

from .base import LoadedData, ProgressCb, RunOutcome, register_runner


class ClusteringRunner:
    task_family = "clustering"
    compatible_shapes = ("tabular", "text")

    def run(self, data: LoadedData, spec: dict, plan: dict, progress: ProgressCb) -> RunOutcome:
        raise NotImplementedError("clustering runner not yet implemented")


register_runner(ClusteringRunner())
