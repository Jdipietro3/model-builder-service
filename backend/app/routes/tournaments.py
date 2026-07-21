from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import submit_training
from ..models import Run
from ..schemas import RunOut

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.post("/{tournament_id}/approve", response_model=list[RunOut])
def approve_tournament(tournament_id: str, db: Session = Depends(get_db)):
    runs = db.scalars(
        select(Run).where(Run.tournament_id == tournament_id).order_by(Run.created_at)
    ).all()
    if not runs:
        raise HTTPException(404, "Tournament not found")

    pending = [
        r for r in runs if r.tournament_role == "candidate" and r.status == "pending_approval"
    ]
    if not pending:
        raise HTTPException(409, "No pending candidates to approve for this tournament")

    for run in pending:
        submit_training(run.id)  # opens its own session; commits status -> queued

    # Our session's identity map holds pre-submit snapshots of the rows submit_training
    # just mutated in a different session — expire and re-query for a fresh response.
    db.expire_all()
    runs = db.scalars(
        select(Run).where(Run.tournament_id == tournament_id).order_by(Run.created_at)
    ).all()
    return runs
