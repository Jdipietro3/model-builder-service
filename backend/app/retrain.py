"""Retrain a completed run's approved plan on the latest version of its dataset."""

from sqlalchemy.orm import Session

from .ml.plans import validate_plan
from .models import Dataset, Run


class NoNewerDataError(Exception):
    """Raised when the run's dataset has no newer version to retrain on."""


def retrain_run(db: Session, run: Run) -> Run:
    # Deferred: jobs imports orchestrator.agent, which imports orchestrator.tools,
    # which imports this module — a top-level import here would be circular.
    from .jobs import submit_training

    if run.status != "completed":
        raise ValueError("Only completed runs can be retrained")

    latest = db.get(Dataset, run.dataset_id)
    while True:
        newer = db.query(Dataset).filter(Dataset.parent_dataset_id == latest.id).first()
        if not newer:
            break
        latest = newer
    if latest.id == run.dataset_id:
        raise NoNewerDataError("The dataset has no updated version to retrain on.")

    validated_plan, errors = validate_plan(run.plan, latest.profile)
    if errors:
        raise ValueError("Plan is no longer valid for the updated data: " + "; ".join(errors))

    new_run = Run(
        project_id=run.project_id,
        dataset_id=latest.id,
        plan=validated_plan,
        parent_run_id=run.id,
    )
    db.add(new_run)
    db.commit()
    submit_training(new_run.id)
    db.refresh(new_run)
    return new_run
