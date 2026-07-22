import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deployments import (
    build_contract,
    create_deployment,
    dataset_profile_for_run,
    serving_stats,
    training_distribution,
)
from ..ml.scoring import load_model, predict_records, served_summary
from ..models import Deployment, InferenceLog, Project, Run
from ..schemas import (
    DeploymentCreate,
    DeploymentOut,
    DeploymentStatusUpdate,
    PredictRequest,
    PromoteRequest,
)

router = APIRouter(prefix="/projects/{project_id}/deployments", tags=["deployments"])
deployment_router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.post("", response_model=DeploymentOut)
def create_deployment_route(
    project_id: str, body: DeploymentCreate, db: Session = Depends(get_db)
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    try:
        return create_deployment(db, project_id, body.run_id, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[DeploymentOut])
def list_deployments(project_id: str, db: Session = Depends(get_db)):
    return db.scalars(
        select(Deployment)
        .where(Deployment.project_id == project_id)
        .order_by(Deployment.created_at)
    ).all()


@deployment_router.get("/{deployment_id}", response_model=DeploymentOut)
def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    deployment = db.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(404, "Deployment not found")
    return deployment


@deployment_router.get("/{deployment_id}/stats")
def get_deployment_stats(deployment_id: str, db: Session = Depends(get_db)):
    deployment = db.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(404, "Deployment not found")
    return serving_stats(db, deployment)


@deployment_router.post("/{deployment_id}/predict")
def predict(deployment_id: str, body: PredictRequest, db: Session = Depends(get_db)):
    deployment = db.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(404, "Deployment not found")
    if deployment.status == "disabled":
        raise HTTPException(409, "Deployment is disabled")

    run = db.get(Run, deployment.run_id)
    if not run:
        raise HTTPException(404, "Run backing this deployment no longer exists")

    start = time.perf_counter()
    try:
        pipeline, meta = load_model(run)
        result = predict_records(pipeline, meta, body.records)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    latency_ms = (time.perf_counter() - start) * 1000

    summary = served_summary(result["predictions"], result.get("probabilities"), meta)
    db.add(
        InferenceLog(
            deployment_id=deployment.id,
            n_rows=len(body.records),
            latency_ms=latency_ms,
            summary=summary,
        )
    )
    db.commit()
    return result


@deployment_router.post("/{deployment_id}/promote", response_model=DeploymentOut)
def promote(deployment_id: str, body: PromoteRequest, db: Session = Depends(get_db)):
    deployment = db.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(404, "Deployment not found")

    new_run = db.get(Run, body.run_id)
    if not new_run or new_run.project_id != deployment.project_id:
        raise HTTPException(400, "Run not found in this project")
    if new_run.status != "completed":
        raise HTTPException(400, f"Run is '{new_run.status}' — only completed runs can be promoted")

    if new_run.id == deployment.run_id:
        raise HTTPException(400, "that run is already serving this deployment")

    _, new_meta = load_model(new_run)
    if new_meta.get("task_family", "supervised") not in ("supervised", "ensemble"):
        raise HTTPException(400, "forecasting runs can't back a row-prediction deployment")
    if (
        deployment.contract["target_column"] != new_meta.get("target_column")
        or deployment.contract["task_type"] != new_meta.get("task_type")
    ):
        raise HTTPException(
            400,
            "cannot promote: target/task differ from the current deployment (would change the endpoint contract)",
        )

    try:
        dataset_profile = dataset_profile_for_run(db, new_run)
        contract = build_contract(new_run, dataset_profile)
        dist = training_distribution(new_run, dataset_profile)
    except ValueError as e:
        raise HTTPException(400, str(e))

    contract["endpoint"] = f"/deployments/{deployment.id}/predict"
    deployment.run_id = new_run.id
    deployment.version += 1
    deployment.contract = contract
    deployment.training_distribution = dist
    db.commit()
    db.refresh(deployment)
    return deployment


@deployment_router.patch("/{deployment_id}", response_model=DeploymentOut)
def update_status(deployment_id: str, body: DeploymentStatusUpdate, db: Session = Depends(get_db)):
    deployment = db.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(404, "Deployment not found")
    deployment.status = body.status
    db.commit()
    db.refresh(deployment)
    return deployment
