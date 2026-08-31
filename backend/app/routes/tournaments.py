from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..jobs import submit_training
from ..models import Project, Run, User
from ..schemas import RunOut

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.post("/{tournament_id}/approve", response_model=list[RunOut])
def approve_tournament(
    tournament_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    runs = db.scalars(
        select(Run).where(Run.tournament_id == tournament_id).order_by(Run.created_at)
    ).all()
    if not runs:
        raise HTTPException(404, "Tournament not found")

    # A tournament has no id of its own to hang an owned_* dependency off —
    # it's just the shared tournament_id on a set of runs — so ownership is
    # checked through the project those runs belong to (they all share one).
    # 404, not 403: see auth.py's owned_* helpers for why.
    project = db.get(Project, runs[0].project_id)
    if project is None or project.user_id != user.id:
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
