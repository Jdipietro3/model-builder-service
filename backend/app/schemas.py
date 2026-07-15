from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskType = Literal["binary_classification", "multiclass_classification", "regression"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    cards: list[dict[str, Any]] | None = None
    hidden: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetOut(BaseModel):
    id: str
    filename: str
    profile: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationSpec(BaseModel):
    strategy: Literal["kfold", "stratified_kfold"] = "stratified_kfold"
    n_splits: int = Field(default=5, ge=2, le=10)


class Plan(BaseModel):
    """The structured training plan the orchestrator proposes and the user approves."""

    task_type: TaskType
    target_column: str
    methodology_id: str
    excluded_columns: list[str] = Field(default_factory=list)
    validation: ValidationSpec = Field(default_factory=ValidationSpec)
    primary_metric: str
    reasoning: str = ""


class RunOut(BaseModel):
    id: str
    project_id: str
    dataset_id: str
    status: str
    plan: dict[str, Any]
    progress: dict[str, Any] | None = None
    results: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    content: str
    # "user" for typed messages; "system_event" for synthetic notifications
    # (e.g. training completed) that are hidden from the chat UI.
    kind: Literal["user", "system_event"] = "user"


class ApproveRequest(BaseModel):
    # Optional field overrides made in the PlanCard before approval.
    plan_overrides: dict[str, Any] | None = None


class ProjectDetail(ProjectOut):
    messages: list[MessageOut]
    datasets: list[DatasetOut]
    runs: list[RunOut]
