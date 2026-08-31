from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth import owned_dataset, owned_project
from ..config import MAX_UPLOAD_MB, UPLOADS_DIR
from ..db import get_db
from ..ml.profiling import load_csv, profile_path
from ..ml.scoring import read_csv_bytes
from ..ml.updates import build_diff, check_schema, merge_append
from ..models import Dataset, Message, Project
from ..schemas import DatasetOut

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["datasets"])
dataset_router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetOut)
async def upload_dataset(
    file: UploadFile, project: Project = Depends(owned_project), db: Session = Depends(get_db)
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported in v1")

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_UPLOAD_MB} MB limit")

    dataset = Dataset(project_id=project.id, filename=file.filename, path="")
    db.add(dataset)
    db.flush()  # id defaults fire at flush; the path prefix needs it
    path = UPLOADS_DIR / f"{dataset.id}_{file.filename}"
    path.write_bytes(content)
    dataset.path = str(path)

    try:
        dataset.profile = profile_path(str(path))
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not parse CSV: {e}")

    db.add(dataset)
    # Pin the profile into chat history as a card.
    db.add(
        Message(
            project_id=project.id,
            role="assistant",
            content="",
            cards=[
                {
                    "type": "profile",
                    "dataset_id": dataset.id,
                    "filename": dataset.filename,
                    "profile": dataset.profile,
                }
            ],
        )
    )
    db.commit()
    return dataset


@dataset_router.post("/{dataset_id}/update")
async def update_dataset(
    file: UploadFile,
    mode: str = Form(...),
    old: Dataset = Depends(owned_dataset),
    db: Session = Depends(get_db),
):
    newer = db.query(Dataset).filter(Dataset.parent_dataset_id == old.id).first()
    if newer:
        raise HTTPException(
            409, "This dataset has a newer version; update the latest version instead."
        )
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported in v1")

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_UPLOAD_MB} MB limit")

    old_df = load_csv(old.path)
    new_df = read_csv_bytes(content)

    schema_error = check_schema(old_df, new_df)
    if schema_error:
        raise HTTPException(400, schema_error)

    time_candidates = (old.profile or {}).get("time_column_candidates") or []
    time_column = time_candidates[0] if time_candidates else None

    if mode == "append":
        result_df = merge_append(old_df, new_df, time_column)
    elif mode == "replace":
        result_df = new_df
    else:
        raise HTTPException(400, "mode must be 'replace' or 'append'")

    diff = build_diff(old_df, result_df, time_column, mode)

    dataset = Dataset(
        project_id=old.project_id,
        filename=file.filename,
        path="",
        version=old.version + 1,
        parent_dataset_id=old.id,
    )
    db.add(dataset)
    db.flush()  # id defaults fire at flush; the path prefix needs it
    path = UPLOADS_DIR / f"{dataset.id}_{file.filename}"
    result_df.to_csv(path, index=False)
    dataset.path = str(path)

    try:
        dataset.profile = profile_path(str(path))
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not parse CSV: {e}")

    db.add(dataset)
    db.add(
        Message(
            project_id=old.project_id,
            role="assistant",
            content="",
            cards=[
                {
                    "type": "dataset_update",
                    "dataset_id": dataset.id,
                    "parent_dataset_id": old.id,
                    "filename": dataset.filename,
                    "version": dataset.version,
                    "diff": diff,
                    "profile": dataset.profile,
                }
            ],
        )
    )
    db.commit()
    db.refresh(dataset)
    return {"dataset": DatasetOut.model_validate(dataset).model_dump(), "diff": diff}
