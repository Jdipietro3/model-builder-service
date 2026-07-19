"""Background training jobs. A thread pool is plenty for a local prototype;
swap for Celery/RQ when this needs to scale."""

import traceback
from concurrent.futures import ThreadPoolExecutor

from .db import SessionLocal
from .ml.artifacts import build_bundle
from .ml.registry.loader import get_spec
from .ml.training import run_plan
from .models import Dataset, Run

# CPU worker pool. A GPU-backed executor slots in via _select_executor once real
# GPU methodologies exist; the dispatch structure is here so that swap is local.
_executor = ThreadPoolExecutor(max_workers=2)


def _select_executor(compute: dict):
    """ComputeRouter: pick the executor for a methodology's compute requirements.

    Today only CPU is available. GPU-backed methodologies are rejected upstream in
    submit_training (before queuing); this function is the seam where a real GPU
    executor will be returned instead of the CPU pool.
    """
    if compute.get("device") == "gpu" or compute.get("requires_gpu"):
        raise RuntimeError("GPU-backed methodologies are not yet available on this deployment")
    return _executor


def submit_training(run_id: str) -> None:
    with SessionLocal() as db:
        run = db.get(Run, run_id)

        # Route by the methodology's declared compute. Reject GPU work by failing the
        # run cleanly (rather than raising) so the approve route returns a normal
        # response instead of a 500.
        spec = get_spec(run.plan["methodology_id"])
        compute = spec.get("compute", {"device": "cpu"})
        try:
            executor = _select_executor(compute)
        except RuntimeError as e:
            run.status = "failed"
            run.error = str(e)
            run.progress = {"stage": "failed", "pct": 100, "message": str(e)}
            db.commit()
            return

        run.status = "queued"
        run.progress = {"stage": "queued", "pct": 0, "message": "Waiting for a worker"}
        db.commit()
    executor.submit(_execute, run_id)


def _execute(run_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)

        def progress(stage: str, pct: int, message: str) -> None:
            run.progress = {"stage": stage, "pct": pct, "message": message}
            db.commit()

        run.status = "running"
        progress("preparing", 5, "Starting training job")

        dataset = db.get(Dataset, run.dataset_id)
        outcome = run_plan(dataset.path, run.plan, progress)

        progress("artifacts", 92, "Building artifact bundle")
        zip_path = build_bundle(run.id, outcome, run.plan)

        run.results = outcome.results
        run.artifact_path = zip_path
        run.status = "completed"
        run.progress = {"stage": "done", "pct": 100, "message": "Training complete"}
        db.commit()
    except Exception:
        db.rollback()
        run = db.get(Run, run_id)
        run.status = "failed"
        run.error = traceback.format_exc(limit=8)
        run.progress = {"stage": "failed", "pct": 100, "message": "Training failed"}
        db.commit()
    finally:
        db.close()
