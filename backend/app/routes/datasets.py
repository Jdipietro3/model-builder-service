from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import MAX_UPLOAD_MB, UPLOADS_DIR
from ..db import get_db
from ..ml.profiling import profile_path
from ..models import Dataset, Message, Project
from ..schemas import DatasetOut

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["datasets"])


@router.post("", response_model=DatasetOut)
async def upload_dataset(project_id: str, file: UploadFile, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported in v1")

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_UPLOAD_MB} MB limit")

    dataset = Dataset(project_id=project_id, filename=file.filename, path="")
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
            project_id=project_id,
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
