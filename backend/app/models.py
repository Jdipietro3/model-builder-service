import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, default="")
    # Structured card payloads rendered by the UI alongside the text:
    # [{"type": "profile"|"plan"|"report", ...}]
    cards: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Hidden messages (e.g. synthetic "training finished" events) are kept for
    # LLM context but not rendered as chat bubbles.
    hidden: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(500))
    profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    # id of the dataset version this one replaces/extends; the newest version of a
    # chain is the row no other row names as parent.
    parent_dataset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    n_rows: Mapped[int] = mapped_column(default=0)
    output_path: Mapped[str] = mapped_column(String(500))
    # n_rows, class counts / stats, and a small preview for the UI card
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    # pending_approval -> queued -> running -> completed | failed
    status: Mapped[str] = mapped_column(String(30), default="pending_approval")
    plan: Mapped[dict] = mapped_column(JSON)
    progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set only on retrains: the run this one was retrained from.
    parent_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Set only on tournament runs: candidates + the auto-built ensemble share a
    # tournament_id; tournament_role distinguishes "candidate" vs "ensemble".
    tournament_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tournament_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Compare-and-set guard so the single tournament-completion interpretation
    # fires exactly once regardless of which candidate/ensemble thread finishes last.
    tournament_interpreted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    name: Mapped[str] = mapped_column(String(200))
    # active | disabled
    status: Mapped[str] = mapped_column(String(20), default="active")
    version: Mapped[int] = mapped_column(default=1)
    # {feature_columns: [{name, dtype, example}], example_record, target_column,
    #  task_type, endpoint} — see deployments.py::build_contract
    contract: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Training-time reference distribution ({"kind": "class_counts"|"stats", ...})
    # for drift comparison against serving_stats' served_distribution.
    training_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    deployment_id: Mapped[str] = mapped_column(ForeignKey("deployments.id"), index=True)
    n_rows: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[float] = mapped_column(default=0.0)
    # class_counts or stats — see ml/scoring.py::served_summary
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
