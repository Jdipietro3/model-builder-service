import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..jobs import submit_training
from ..ml.plans import validate_plan
from ..models import Dataset, Run
from ..schemas import ApproveRequest, RunOut

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.post("/{run_id}/approve", response_model=RunOut)
def approve_run(run_id: str, body: ApproveRequest, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "pending_approval":
        raise HTTPException(409, f"Run is '{run.status}', not pending approval")

    if body.plan_overrides:
        dataset = db.get(Dataset, run.dataset_id)
        merged = {**run.plan, **body.plan_overrides}
        plan, errors = validate_plan(merged, dataset.profile)
        if errors:
            raise HTTPException(400, "; ".join(errors))
        run.plan = plan
        db.commit()

    submit_training(run_id)
    db.refresh(run)
    return run


@router.get("/{run_id}/events")
async def run_events(run_id: str):
    """SSE stream of run progress; polls the DB until the run reaches a
    terminal state. Simple and robust for a local prototype."""

    with SessionLocal() as db:
        if not db.get(Run, run_id):
            raise HTTPException(404, "Run not found")

    async def gen():
        last: str | None = None
        while True:
            with SessionLocal() as db:
                run = db.get(Run, run_id)
                payload = {
                    "run_id": run.id,
                    "status": run.status,
                    "progress": run.progress,
                }
                if run.status == "completed":
                    payload["results"] = run.results
                if run.status == "failed":
                    payload["error"] = run.error
            snapshot = json.dumps(payload, sort_keys=True)
            if snapshot != last:
                yield f"data: {snapshot}\n\n"
                last = snapshot
            if payload["status"] in ("completed", "failed"):
                return
            await asyncio.sleep(1)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/artifact")
def download_artifact(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if not run.artifact_path or not Path(run.artifact_path).exists():
        raise HTTPException(404, "No artifact bundle for this run")
    return FileResponse(
        run.artifact_path, filename=f"model_bundle_{run_id[:8]}.zip", media_type="application/zip"
    )
