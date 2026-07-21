from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskType = Literal["binary_classification", "multiclass_classification", "regression", "forecasting"]
DataShape = Literal["tabular", "timeseries", "text", "image"]
TaskFamily = Literal["supervised", "forecasting", "clustering", "anomaly", "ensemble"]


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
    version: int = 1
    parent_dataset_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationSpec(BaseModel):
    strategy: Literal["kfold", "stratified_kfold", "time_ordered"] = "stratified_kfold"
    n_splits: int = Field(default=5, ge=2, le=10)


class Plan(BaseModel):
    """The structured training plan the orchestrator proposes and the user approves."""

    task_type: TaskType
    data_shape: DataShape = "tabular"
    task_family: TaskFamily = "supervised"
    # Unsupervised families have no target; supervised validation still requires it
    # (see ml/plans.py).
    target_column: str | None = None
    time_column: str | None = None  # forecasting-only: the timestamp axis
    horizon: int | None = None  # forecasting-only: number of future periods to predict
    methodology_id: str
    excluded_columns: list[str] = Field(default_factory=list)
    validation: ValidationSpec = Field(default_factory=ValidationSpec)
    primary_metric: str
    reasoning: str = ""
    # Ensemble-only: the tournament candidate run ids this ensemble blends/stacks.
    base_run_ids: list[str] | None = None


class RunOut(BaseModel):
    id: str
    project_id: str
    dataset_id: str
    status: str
    plan: dict[str, Any]
    progress: dict[str, Any] | None = None
    results: dict[str, Any] | None = None
    error: str | None = None
    parent_run_id: str | None = None
    tournament_id: str | None = None
    tournament_role: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PredictionOut(BaseModel):
    id: str
    run_id: str
    filename: str
    n_rows: int
    summary: dict[str, Any]
    created_at: datetime

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
    predictions: list[PredictionOut]
