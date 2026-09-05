import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .db import init_db
from .routes import auth, chat, datasets, deployments, projects, runs, tournaments

# uvicorn only configures its own loggers; give app loggers (e.g. the
# orchestrator's token-usage lines) a root handler at INFO.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     [%(name)s] %(message)s")

app = FastAPI(title="Metis", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # Session expiry is otherwise only enforced when someone presents that exact
    # token, so abandoned rows accumulate forever. No scheduler in this
    # prototype, so startup is the sweep.
    from .auth import purge_expired_sessions
    from .db import SessionLocal

    db = SessionLocal()
    try:
        removed = purge_expired_sessions(db)
        if removed:
            logging.getLogger("auth").info("purged %d expired session/attempt rows", removed)
    finally:
        db.close()


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(datasets.router)
app.include_router(datasets.dataset_router)
app.include_router(chat.router)
app.include_router(runs.router)
app.include_router(runs.predictions_router)
app.include_router(tournaments.router)
app.include_router(deployments.router)
app.include_router(deployments.deployment_router)


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
