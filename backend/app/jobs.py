"""Background training jobs. A thread pool is plenty for a local prototype;
swap for Celery/RQ when this needs to scale."""

import traceback
from concurrent.futures import ThreadPoolExecutor

from .db import SessionLocal
from .ml.artifacts import build_bundle
from .ml.training import run_plan
from .models import Dataset, Message, Run

_executor = ThreadPoolExecutor(max_workers=2)


def submit_training(run_id: str) -> None:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        run.status = "queued"
        run.progress = {"stage": "queued", "pct": 0, "message": "Waiting for a worker"}
        db.commit()
    _executor.submit(_execute, run_id)


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

        run.results = outcome["results"]
        run.artifact_path = zip_path
        run.status = "completed"
        run.progress = {"stage": "done", "pct": 100, "message": "Training complete"}
        # Persist the report as a chat message so it survives page reloads.
        db.add(
            Message(
                project_id=run.project_id,
                role="assistant",
                content="",
                cards=[{"type": "report", "run_id": run.id, "results": run.results}],
            )
        )
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
