import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TaskType = Literal["binary_classification", "multiclass_classification", "regression", "forecasting"]
DataShape = Literal["tabular", "timeseries", "text", "image"]
TaskFamily = Literal["supervised", "forecasting", "clustering", "anomaly", "ensemble"]

# Deliberately simple — good enough to catch typos, not a full RFC 5322 parser.
# No EmailStr here: that needs the email-validator package, and this project
# adds zero new dependencies (see auth.py).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignupRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def _valid_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    # Same floor as signup — a change flow that accepts a weaker password than
    # registration would is a hole, not a convenience.
    new_password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreateOut(BaseModel):
    """Returned only from the create-key endpoint — the one time the full
    plaintext key is ever available; only its hash is stored server-side."""

    id: str
    prefix: str
    key: str
    created_at: datetime


class ApiKeyOut(BaseModel):
    id: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    recommended_run_id: str | None = None
    recommendation_reason: str | None = None

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


class RecipeStep(BaseModel):
    """One declarative preprocessing/feature-engineering step. ``op`` is a plain
    str in Phase 0 — the curated op enum lands with ml/recipe.py in Phase 1, once
    there's an actual set of ops to enumerate."""

    op: str
    columns: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


class TuningSpec(BaseModel):
    """How a run's hyperparameters are chosen. Defaults reproduce today's
    behavior exactly (GridSearchCV over the spec's grid) so an absent/default
    `tuning` on a plan changes nothing until Phase 2 wires up random/bayesian
    search."""

    strategy: Literal["none", "grid", "random", "bayesian"] = "grid"
    n_trials: int = Field(default=20, ge=1, le=500)
    time_budget_s: int | None = Field(default=None, ge=10, le=7200)
    cv_splits: int | None = Field(default=None, ge=2, le=10)


class PlanWarning(BaseModel):
    """Non-blocking pre-approval warning surfaced on a proposed plan (diagnose_plan
    in ml/plans.py). Purely informational — flagged plans stay approvable."""

    category: Literal["leakage", "target_high_missingness", "near_constant_feature"]
    severity: Literal["high", "medium"]
    message: str
    columns: list[str] = Field(default_factory=list)


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
    # Non-blocking pre-approval warnings from diagnose_plan (leakage, target
    # missingness, near-constant features). None/absent for plans proposed before
    # this field existed or when diagnose_plan found nothing to flag.
    warnings: list[PlanWarning] | None = None
    # Absent means "use the default recipe derived from the profile + spec" (Phase 1).
    preprocessing: list[RecipeStep] | None = None
    # Pinned model params, applied after/instead of search.
    hyperparameters: dict[str, Any] | None = None
    # Absent means the spec's grid — today's behavior.
    tuning: TuningSpec | None = None
    # Set when this plan is an LLM-proposed revision of an earlier run's plan on the
    # same data (distinct from Run.parent_run_id, which means "retrained on newer data").
    revision_of_run_id: str | None = None


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
    revision_of_run_id: str | None = None
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


class DeploymentCreate(BaseModel):
    run_id: str
    name: str | None = None


class DeploymentOut(BaseModel):
    id: str
    project_id: str
    run_id: str
    name: str
    status: str
    version: int
    contract: dict[str, Any] | None = None
    training_distribution: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PredictRequest(BaseModel):
    records: list[dict[str, Any]]


class PromoteRequest(BaseModel):
    run_id: str


class DeploymentStatusUpdate(BaseModel):
    status: Literal["active", "disabled"]


class ProjectDetail(ProjectOut):
    messages: list[MessageOut]
    datasets: list[DatasetOut]
    runs: list[RunOut]
    predictions: list[PredictionOut]
