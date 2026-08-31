from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, owned_project
from ..db import get_db
from ..models import Dataset, Message, Prediction, Project, Run, User
from ..schemas import ProjectCreate, ProjectDetail, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project(
    body: ProjectCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    project = Project(name=body.name, user_id=user.id)
    db.add(project)
    db.commit()
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
    ).all()


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    messages = db.scalars(
        select(Message).where(Message.project_id == project.id).order_by(Message.created_at)
    ).all()
    datasets = db.scalars(
        select(Dataset).where(Dataset.project_id == project.id).order_by(Dataset.created_at)
    ).all()
    runs = db.scalars(
        select(Run).where(Run.project_id == project.id).order_by(Run.created_at)
    ).all()
    predictions = db.scalars(
        select(Prediction)
        .where(Prediction.project_id == project.id)
        .order_by(Prediction.created_at)
    ).all()
    return ProjectDetail(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        recommended_run_id=project.recommended_run_id,
        recommendation_reason=project.recommendation_reason,
        messages=messages,
        datasets=datasets,
        runs=runs,
        predictions=predictions,
    )
