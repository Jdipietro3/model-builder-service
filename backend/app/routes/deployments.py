import hashlib
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import optional_current_user, owned_deployment, owned_project
from ..db import get_db
from ..deployments import (
    build_contract,
    create_deployment,
    dataset_profile_for_run,
    serving_stats,
    training_distribution,
)
from ..ml.scoring import load_model, predict_records, served_summary
from ..models import ApiKey, Deployment, InferenceLog, Project, Run
from ..schemas import (
    ApiKeyCreateOut,
    ApiKeyOut,
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
    body: DeploymentCreate, project: Project = Depends(owned_project), db: Session = Depends(get_db)
):
    try:
        return create_deployment(db, project.id, body.run_id, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[DeploymentOut])
def list_deployments(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    return db.scalars(
        select(Deployment)
        .where(Deployment.project_id == project.id)
        .order_by(Deployment.created_at)
    ).all()


@deployment_router.get("/{deployment_id}", response_model=DeploymentOut)
def get_deployment(deployment: Deployment = Depends(owned_deployment)):
    return deployment


@deployment_router.get("/{deployment_id}/stats")
def get_deployment_stats(
    deployment: Deployment = Depends(owned_deployment), db: Session = Depends(get_db)
):
    return serving_stats(db, deployment)


@deployment_router.post("/{deployment_id}/keys", response_model=ApiKeyCreateOut, status_code=201)
def create_api_key(deployment: Deployment = Depends(owned_deployment), db: Session = Depends(get_db)):
    """The one and only time the plaintext key is available — only its sha256
    is persisted. A high-entropy random token doesn't need a slow password KDF
    (unlike hash_password/verify_password in auth.py), so a plain digest is fine."""
    key = f"mb_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = ApiKey(deployment_id=deployment.id, key_hash=key_hash, prefix=key[:11])
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return ApiKeyCreateOut(
        id=api_key.id, prefix=api_key.prefix, key=key, created_at=api_key.created_at
    )


@deployment_router.get("/{deployment_id}/keys", response_model=list[ApiKeyOut])
def list_api_keys(deployment: Deployment = Depends(owned_deployment), db: Session = Depends(get_db)):
    return db.scalars(
        select(ApiKey).where(ApiKey.deployment_id == deployment.id).order_by(ApiKey.created_at)
    ).all()


@deployment_router.delete("/{deployment_id}/keys/{key_id}", status_code=204)
def delete_api_key(
    key_id: str, deployment: Deployment = Depends(owned_deployment), db: Session = Depends(get_db)
):
    api_key = db.get(ApiKey, key_id)
    if not api_key or api_key.deployment_id != deployment.id:
        raise HTTPException(404, "API key not found")
    db.delete(api_key)
    db.commit()


@deployment_router.post("/{deployment_id}/predict")
def predict(deployment_id: str, body: PredictRequest, request: Request, db: Session = Depends(get_db)):
    """Accepts either a session belonging to the deployment's owner, or an
    `Authorization: Bearer mb_...` API key scoped to this deployment — the
    only route in this file usable by a deployed application rather than the
    dashboard itself, so it can't require a browser session."""
    deployment = db.get(Deployment, deployment_id)

    user = optional_current_user(request, db)
    session_owns = False
    if user is not None and deployment is not None:
        project = db.get(Project, deployment.project_id)
        session_owns = project is not None and project.user_id == user.id

    api_key_row = None
    if not session_owns:
        auth_header = request.headers.get("authorization", "")
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token.startswith("mb_"):
            key_hash = hashlib.sha256(token.encode()).hexdigest()
            api_key_row = db.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))

        if api_key_row is not None and api_key_row.deployment_id != deployment_id:
            # The key is real but scoped to a different deployment: 404 (not
            # 401/403) so it can't be used to probe whether this deployment
            # id exists.
            raise HTTPException(404, "Deployment not found")

        key_owns = api_key_row is not None and api_key_row.deployment_id == deployment_id
        if not key_owns:
            raise HTTPException(401, "Not authenticated")
        # Record usage now: authentication itself succeeded, independent of
        # whether the prediction below also succeeds. Committed immediately
        # so it isn't lost if load_model/predict_records raises before the
        # commit at the end of this function runs.
        api_key_row.last_used_at = datetime.now(timezone.utc)
        db.add(api_key_row)
        db.commit()

    if deployment is None:
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
def promote(
    body: PromoteRequest, deployment: Deployment = Depends(owned_deployment), db: Session = Depends(get_db)
):
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
def update_status(
    body: DeploymentStatusUpdate,
    deployment: Deployment = Depends(owned_deployment),
    db: Session = Depends(get_db),
):
    deployment.status = body.status
    db.commit()
    db.refresh(deployment)
    return deployment
