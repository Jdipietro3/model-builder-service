"""Background training jobs. A thread pool is plenty for a local prototype;
swap for Celery/RQ when this needs to scale."""

import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

from .db import SessionLocal
from .ml.artifacts import build_bundle
from .ml.registry.loader import get_spec
from .ml.training import run_plan
from .models import Dataset, Run
from .orchestrator.agent import run_turn

logger = logging.getLogger("jobs")

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

        _interpret_run(run)
    except Exception:
        db.rollback()
        run = db.get(Run, run_id)
        run.status = "failed"
        run.error = traceback.format_exc(limit=8)
        run.progress = {"stage": "failed", "pct": 100, "message": "Training failed"}
        db.commit()
    finally:
        db.close()


def _build_interpretation_notification(run_id: str, plan: dict, parent_run_id: str | None = None) -> str:
    """Build the hidden system-notification text that kicks off the results
    interpretation turn. Family-aware: forecasting runs get a baseline-vs-seasonal-
    naive framing, other (supervised) runs get the naive-baseline framing that the
    frontend used to send verbatim before this became a server-side trigger.

    Retrains (parent_run_id set) get a comparison framing instead, regardless of
    family — get_results gives the LLM everything it needs for both runs.
    """
    if parent_run_id:
        return (
            f"[system notification] Training run {run_id} has completed. This is a RETRAIN "
            f"of run {parent_run_id} on an updated version of the dataset. Call get_results "
            "for BOTH runs and compare them for the user: did the data update improve the "
            "headline metric, which metrics moved notably, and should they prefer the new "
            "model? Include any caveats."
        )
    if plan.get("task_family") == "forecasting":
        return (
            f"[system notification] Training run {run_id} has completed. Call get_results and "
            "give the user a plain-language interpretation: the headline metric vs the "
            "seasonal-naive baseline and whether the model beats it, what the forecast shows "
            "over the horizon, and any caveats."
        )
    return (
        f"[system notification] Training run {run_id} has completed. Call get_results and give "
        "the user a plain-language interpretation: headline metric vs the naive baseline, what "
        "drives predictions, and any caveats."
    )


async def _drain_interpretation_turn(project_id: str, notification: str) -> None:
    """Run the orchestrator turn to completion against a fresh session, collecting
    any error events for logging. run_turn persists the hidden user message and the
    final assistant message itself."""
    errors: list[str] = []
    with SessionLocal() as db:
        async for event in run_turn(db, project_id, notification, hidden=True):
            if event.get("type") == "error":
                errors.append(event.get("message", ""))
    if errors:
        logger.warning(
            "Results interpretation turn for project %s reported errors: %s", project_id, errors
        )


def _interpret_run(run: Run) -> None:
    """Server-side results-interpretation turn for a completed run.

    This replaces the old client-side trigger (the frontend used to open an
    EventSource on run events and fire this notification itself), so the
    interpretation lands even if no client is around when training finishes.

    Best-effort only: any failure (missing API key, network error, LLM error, ...)
    is logged and swallowed. The run row is already committed as "completed" by the
    caller before this runs, and must not be touched here regardless of outcome.
    """
    notification = _build_interpretation_notification(run.id, run.plan, run.parent_run_id)
    try:
        asyncio.run(_drain_interpretation_turn(run.project_id, notification))
    except Exception:
        logger.warning("Results interpretation failed for run %s", run.id, exc_info=True)
