"""Background training jobs. A thread pool is plenty for a local prototype;
swap for Celery/RQ when this needs to scale."""

import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, text

from .db import SessionLocal
from .ml.artifacts import build_bundle
from .ml.registry.loader import get_spec
from .ml.training import run_plan
from .models import Dataset, Run
from .orchestrator.agent import run_turn

# Terminal Run statuses (as opposed to pending_approval/queued/running/waiting/claimed).
_TERMINAL_STATUSES = ("completed", "failed")

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

        # Ensemble runs need their completed base candidates' fitted pipelines +
        # results at training time. This enrichment is in-memory only — the
        # persisted Run.plan stays lean (just base_run_ids) so it round-trips
        # through validate_plan/the tournament card unchanged.
        exec_plan = run.plan
        if run.plan.get("task_family") == "ensemble":
            base_runs = []
            for base_id in run.plan.get("base_run_ids") or []:
                base_run = db.get(Run, base_id)
                if base_run is not None and base_run.status == "completed":
                    base_runs.append(
                        {
                            "run_id": base_run.id,
                            "methodology_id": base_run.plan.get("methodology_id"),
                            "artifact_path": base_run.artifact_path,
                            "results": base_run.results,
                        }
                    )
            exec_plan = {**run.plan, "base_runs": base_runs}

        outcome = run_plan(dataset.path, exec_plan, progress)

        progress("artifacts", 92, "Building artifact bundle")
        zip_path = build_bundle(run.id, outcome, run.plan)

        run.results = outcome.results
        run.artifact_path = zip_path
        run.status = "completed"
        run.progress = {"stage": "done", "pct": 100, "message": "Training complete"}
        db.commit()

        if run.tournament_id:
            _maybe_promote_ensemble(run.tournament_id)
        else:
            _interpret_run(run)
    except Exception:
        db.rollback()
        run = db.get(Run, run_id)
        run.status = "failed"
        run.error = traceback.format_exc(limit=8)
        run.progress = {"stage": "failed", "pct": 100, "message": "Training failed"}
        db.commit()
        if run.tournament_id:
            _maybe_promote_ensemble(run.tournament_id)
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


def _maybe_promote_ensemble(tournament_id: str) -> None:
    """Race-safe promotion/failure decision for a tournament's ensemble run.

    Called after every tournament candidate AND the ensemble run itself reaches a
    terminal state (from both the success and failure paths of ``_execute``), so it
    may run concurrently from multiple worker threads for the same tournament. All
    state transitions go through ``UPDATE ... WHERE status='waiting'`` compare-and-set
    statements so exactly one caller wins each transition (the SQLite engine's WAL +
    busy-timeout serializes the concurrent writers; the loser simply sees rowcount 0).
    """
    with SessionLocal() as db:
        siblings = db.scalars(select(Run).where(Run.tournament_id == tournament_id)).all()
        candidates = [r for r in siblings if r.tournament_role == "candidate"]
        ensemble = next((r for r in siblings if r.tournament_role == "ensemble"), None)

        if any(c.status not in _TERMINAL_STATUSES for c in candidates):
            return  # other candidates are still training

        if ensemble is not None and ensemble.status == "waiting":
            completed = [c for c in candidates if c.status == "completed"]
            if len(completed) >= 2:
                result = db.execute(
                    text("UPDATE runs SET status='claimed' WHERE id=:id AND status='waiting'"),
                    {"id": ensemble.id},
                )
                db.commit()
                if result.rowcount == 1:
                    submit_training(ensemble.id)
            else:
                skip_message = (
                    "Ensemble skipped: fewer than 2 candidate models completed successfully."
                )
                db.execute(
                    text(
                        "UPDATE runs SET status='failed', error=:error "
                        "WHERE id=:id AND status='waiting'"
                    ),
                    {"id": ensemble.id, "error": skip_message},
                )
                db.commit()

        # Re-read fresh: the block above may have just moved the ensemble to
        # 'claimed'/'failed', or this call may BE the ensemble's own completion (in
        # which case its status here is already terminal from _execute).
        db.expire_all()
        siblings = db.scalars(select(Run).where(Run.tournament_id == tournament_id)).all()
        if all(r.status in _TERMINAL_STATUSES for r in siblings):
            _fire_tournament_interpretation_once(tournament_id, siblings)


def _build_tournament_interpretation_notification(tournament_id: str, siblings: list[Run]) -> str:
    """Hidden system-notification text for the single tournament-completion
    interpretation turn: lists every completed run so the LLM can get_results on
    each and crown a winner, with variants for ensemble completed/failed/skipped
    and for the all-candidates-failed case."""
    candidates = [r for r in siblings if r.tournament_role == "candidate"]
    ensemble = next((r for r in siblings if r.tournament_role == "ensemble"), None)
    completed_candidates = [r for r in candidates if r.status == "completed"]
    failed_candidates = [r for r in candidates if r.status == "failed"]

    if not completed_candidates:
        ids = ", ".join(r.id for r in failed_candidates) or "none"
        return (
            f"[system notification] Tournament {tournament_id} has finished, but ALL "
            f"{len(candidates)} candidate model(s) failed to train (run ids: {ids}). There is no "
            "winner to crown — tell the user the tournament failed, and suggest calling "
            "get_run_status on a candidate if they want the error detail."
        )

    lines = [
        f"[system notification] Tournament {tournament_id} has finished. "
        f"{len(completed_candidates)} of {len(candidates)} candidate model(s) completed "
        f"successfully (run ids: {', '.join(r.id for r in completed_candidates)})."
    ]
    if failed_candidates:
        lines.append(
            f"{len(failed_candidates)} candidate(s) failed and are excluded from comparison "
            f"(run ids: {', '.join(r.id for r in failed_candidates)})."
        )
    if ensemble is not None:
        if ensemble.status == "completed":
            lines.append(
                f"An ensemble ({ensemble.plan.get('methodology_id')}, run id {ensemble.id}) was "
                "auto-built from the completed candidates and also finished training — include "
                "it as a contender alongside the candidates."
            )
        elif (ensemble.error or "").startswith("Ensemble skipped"):
            lines.append(
                "The ensemble was skipped (fewer than 2 candidates completed successfully) — do "
                "not treat it as a contender."
            )
        else:
            lines.append(
                f"The ensemble (run id {ensemble.id}) failed to train — mention this in passing "
                "but do not treat it as a contender."
            )
    lines.append(
        "Call get_results for every completed run listed above (including the ensemble if it "
        "completed) and crown a winner for the user: name it explicitly, justify the choice with "
        "the primary metric and any caveats worth flagging, and give a clear recommendation."
    )
    return "\n".join(lines)


def _fire_tournament_interpretation_once(tournament_id: str, siblings: list[Run]) -> None:
    """Second compare-and-set (independent of the promotion one above) so the
    single tournament-completion interpretation fires exactly once, regardless of
    which sibling run's completion triggers the check. Lock row is the ensemble run
    when the tournament has one, else the lexicographically-smallest candidate id
    (any single row all callers agree on works as the mutex)."""
    candidates = [r for r in siblings if r.tournament_role == "candidate"]
    ensemble = next((r for r in siblings if r.tournament_role == "ensemble"), None)
    lock_id = ensemble.id if ensemble is not None else min(c.id for c in candidates)

    with SessionLocal() as db:
        result = db.execute(
            text("UPDATE runs SET tournament_interpreted=1 WHERE id=:id AND tournament_interpreted=0"),
            {"id": lock_id},
        )
        db.commit()
        if result.rowcount != 1:
            return  # a concurrent finisher already fired the tournament interpretation

    notification = _build_tournament_interpretation_notification(tournament_id, siblings)
    project_id = siblings[0].project_id
    try:
        asyncio.run(_drain_interpretation_turn(project_id, notification))
    except Exception:
        logger.warning(
            "Tournament interpretation failed for tournament %s", tournament_id, exc_info=True
        )
