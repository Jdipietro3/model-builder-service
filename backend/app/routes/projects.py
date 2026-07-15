from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Dataset, Message, Project, Run
from ..schemas import ProjectCreate, ProjectDetail, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name)
    db.add(project)
    db.commit()
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.created_at.desc())).all()


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    messages = db.scalars(
        select(Message).where(Message.project_id == project_id).order_by(Message.created_at)
    ).all()
    datasets = db.scalars(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at)
    ).all()
    runs = db.scalars(
        select(Run).where(Run.project_id == project_id).order_by(Run.created_at)
    ).all()
    return ProjectDetail(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        messages=messages,
        datasets=datasets,
        runs=runs,
    )
