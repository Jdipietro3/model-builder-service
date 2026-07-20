import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routes import chat, datasets, projects, runs

# uvicorn only configures its own loggers; give app loggers (e.g. the
# orchestrator's token-usage lines) a root handler at INFO.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     [%(name)s] %(message)s")

app = FastAPI(title="Model Builder Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.include_router(projects.router)
app.include_router(datasets.router)
app.include_router(datasets.dataset_router)
app.include_router(chat.router)
app.include_router(runs.router)
app.include_router(runs.predictions_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/methodologies")
def methodologies(
    task_type: str | None = None,
    data_shape: str | None = None,
    task_family: str | None = None,
) -> list[dict]:
    from .ml.registry.loader import list_methodologies

    return list_methodologies(task_type, data_shape, task_family)
