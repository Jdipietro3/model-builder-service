import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..auth import owned_project
from ..db import SessionLocal
from ..models import Project
from ..orchestrator.agent import run_turn
from ..schemas import ChatRequest

router = APIRouter(prefix="/projects/{project_id}", tags=["chat"])


@router.post("/chat")
async def chat(project_id: str, body: ChatRequest, project: Project = Depends(owned_project)):
    async def gen():
        # The session must outlive the request-scope dependency, so manage it here.
        db = SessionLocal()
        try:
            async for event in run_turn(
                db, project_id, body.content, hidden=(body.kind == "system_event")
            ):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
