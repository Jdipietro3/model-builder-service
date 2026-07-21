"""Tool definitions and dispatch for the orchestrator.

Each tool maps to deterministic code in app.ml. Tool inputs are pydantic models:
the Anthropic input_schema is generated from the model, and incoming tool_input
is validated against it before the handler runs (validation errors go back to
the LLM as the tool_result so it can self-correct).

The dispatcher returns (result_json, card): result_json goes back to the LLM as
the tool_result; card, when present, is a structured payload streamed to the UI.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..ml.plans import validate_plan
from ..ml.profiling import profile_path
from ..ml.registry.loader import get_spec, list_methodologies
from ..models import Dataset, Run
from ..retrain import NoNewerDataError, retrain_run
from ..schemas import DataShape, TaskFamily, TaskType

# ---------------------------------------------------------------------------
# Tool input models


class ToolInput(BaseModel):
    # extra="forbid" so hallucinated parameters fail validation loudly instead
    # of being silently dropped.
    model_config = ConfigDict(extra="forbid")


class ProfileDatasetInput(ToolInput):
    dataset_id: str


class ListMethodologiesInput(ToolInput):
    task_type: TaskType | None = Field(default=None, description="Filter by task type")
    data_shape: DataShape | None = Field(
        default=None, description="Filter by data shape (tabular, timeseries, text, image)"
    )
    task_family: TaskFamily | None = Field(
        default=None,
        description="Filter by task family (supervised, forecasting, clustering, anomaly)",
    )


class ProposePlanInput(ToolInput):
    dataset_id: str
    task_type: TaskType
    target_column: str | None = Field(
        default=None,
        description="Target/label column. Required for supervised tasks; omit for unsupervised.",
    )
    time_column: str | None = Field(
        default=None,
        description="For forecasting plans: the timestamp column that defines the time axis.",
    )
    horizon: int | None = Field(
        default=None,
        ge=1,
        description="For forecasting plans: the number of future periods to predict.",
    )
    methodology_id: str
    excluded_columns: list[str] = Field(
        default_factory=list,
        description="Columns to exclude from features (IDs, leakage risks, etc.)",
    )
    n_splits: int = Field(default=5, ge=2, le=10)
    primary_metric: str
    data_shape: DataShape | None = Field(
        default=None,
        description="Usually omitted — derived from the chosen methodology.",
    )
    task_family: TaskFamily | None = Field(
        default=None,
        description="Usually omitted — derived from the chosen methodology.",
    )
    reasoning: str = Field(
        description="Why this framing and methodology fit, citing data characteristics."
    )


class ProposeTournamentInput(ToolInput):
    dataset_id: str
    task_type: TaskType
    target_column: str | None = Field(
        default=None,
        description="Target/label column. Required for supervised tasks; omit for unsupervised.",
    )
    time_column: str | None = Field(
        default=None,
        description="For forecasting plans: the timestamp column that defines the time axis.",
    )
    horizon: int | None = Field(
        default=None,
        ge=1,
        description="For forecasting plans: the number of future periods to predict.",
    )
    methodology_ids: list[str] = Field(
        description="2-3 distinct methodology ids to run as tournament candidates."
    )
    excluded_columns: list[str] = Field(
        default_factory=list,
        description="Columns to exclude from features (IDs, leakage risks, etc.)",
    )
    n_splits: int = Field(default=5, ge=2, le=10)
    primary_metric: str
    ensemble: Literal["blend", "stacking", "none"] = Field(
        description="Whether to auto-build a weighted blend or a stacked meta-model from the "
        "completed candidates once they finish. Only valid for supervised tournaments — use "
        "'none' for forecasting tournaments (no ensemble support in v1)."
    )
    reasoning: str = Field(
        description="Why these candidates (and this ensemble choice) fit, citing data characteristics."
    )


class GetRunStatusInput(ToolInput):
    run_id: str


class GetResultsInput(ToolInput):
    run_id: str


class RetrainRunInput(ToolInput):
    run_id: str


# ---------------------------------------------------------------------------
# Registry

Handler = Callable[[Session, str, Any], tuple[Any, dict | None]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Handler

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": _clean_schema(self.input_model.model_json_schema()),
        }


def _clean_schema(schema: dict) -> dict:
    """Trim pydantic's JSON schema down to what Anthropic tool schemas expect."""
    # Nested models would emit $defs/$ref, which Anthropic handles poorly.
    # Keep tool inputs flat.
    assert "$defs" not in schema, f"nested models not supported in tool inputs: {schema}"
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
        # Optional[X] emits anyOf [X, null]; collapse to X — optionality is
        # already conveyed by absence from `required`.
        if "anyOf" in prop:
            branches = [b for b in prop["anyOf"] if b.get("type") != "null"]
            if len(branches) == 1:
                prop.pop("anyOf")
                prop.update(branches[0])
        prop.pop("default", None)
    return schema


_REGISTRY: dict[str, ToolSpec] = {}  # insertion-ordered -> stable TOOLS order


def tool(name: str, description: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        hints = get_type_hints(fn)
        input_model = next(
            v
            for k, v in hints.items()
            if k != "return" and isinstance(v, type) and issubclass(v, ToolInput)
        )
        _REGISTRY[name] = ToolSpec(name, description, input_model, fn)
        return fn

    return deco


# ---------------------------------------------------------------------------
# Tools. Handlers return (result, card): result is any JSON-serializable
# object; the dispatcher serializes it.


@tool(
    "profile_dataset",
    "Get the structured profile of an uploaded dataset: row/column counts, "
    "per-column type/kind, missingness, unique counts, sample values, "
    "candidate target columns, and data-quality warnings. Always call this "
    "before proposing a plan.",
)
def profile_dataset(db: Session, project_id: str, args: ProfileDatasetInput):
    dataset = db.get(Dataset, args.dataset_id)
    if not dataset or dataset.project_id != project_id:
        return {"error": "Dataset not found in this project"}, None
    if dataset.profile is None:
        dataset.profile = profile_path(dataset.path)
        db.commit()
    return dataset.profile, None


@tool(
    "list_methodologies",
    "List the curated methodology library, optionally filtered by task_type, "
    "data_shape, or task_family. Returns each methodology's id, data_shape, "
    "task_family, when-to-use guidance, and supported metrics.",
)
def list_methodologies_tool(db: Session, project_id: str, args: ListMethodologiesInput):
    return list_methodologies(args.task_type, args.data_shape, args.task_family), None


@tool(
    "propose_plan",
    "Propose a training plan for user approval. Validates the plan against the "
    "registry and dataset, persists it as a pending run, and shows the user an "
    "editable plan card. Training does NOT start until the user approves the card.",
)
def propose_plan(db: Session, project_id: str, args: ProposePlanInput):
    dataset = db.get(Dataset, args.dataset_id)
    if not dataset or dataset.project_id != project_id:
        return {"error": "Dataset not found in this project"}, None
    # The axes are properties of the methodology, not free LLM choices: derive them
    # from the chosen spec. If the id is unknown, fall back to the LLM's values (or
    # defaults) and let validate_plan surface the proper unknown-methodology error.
    try:
        spec = get_spec(args.methodology_id)
        data_shape = spec["data_shape"]
        task_family = spec["task_family"]
    except KeyError:
        data_shape = args.data_shape or "tabular"
        task_family = args.task_family or "supervised"
    if task_family == "ensemble":
        return {
            "error": "ensemble.* methodologies are auto-built by the tournament workflow and "
            "cannot be proposed directly. Use propose_tournament instead."
        }, None
    if task_family == "forecasting":
        validation = {"n_splits": args.n_splits, "strategy": "time_ordered"}
    else:
        validation = {"n_splits": args.n_splits}
    plan_data = {
        "task_type": args.task_type,
        "data_shape": data_shape,
        "task_family": task_family,
        "target_column": args.target_column,
        "time_column": args.time_column,
        "horizon": args.horizon,
        "methodology_id": args.methodology_id,
        "excluded_columns": args.excluded_columns,
        "validation": validation,
        "primary_metric": args.primary_metric,
        "reasoning": args.reasoning,
    }
    plan, errors = validate_plan(plan_data, dataset.profile)
    if errors:
        return {"error": "Plan validation failed", "details": errors}, None
    run = Run(project_id=project_id, dataset_id=dataset.id, plan=plan)
    db.add(run)
    db.commit()
    card = {
        "type": "plan",
        "run_id": run.id,
        "dataset_id": dataset.id,
        "dataset_filename": dataset.filename,
        "plan": plan,
    }
    return {"run_id": run.id, "status": "pending_approval", "plan": plan}, card


@tool(
    "propose_tournament",
    "Propose a champion/challenger tournament: 2-3 candidate methodologies trained on the "
    "same target, approved with a single click. For supervised tournaments, optionally "
    "auto-builds a weighted blend or stacked ensemble from whichever candidates complete "
    "successfully. Use this instead of propose_plan when the user wants to compare "
    "approaches or find 'the best' model rather than committing to one methodology up "
    "front. Validates every candidate against the registry and dataset, persists them as "
    "pending runs, and shows the user one approve-all tournament card. Training does NOT "
    "start until the user approves the card.",
)
def propose_tournament(db: Session, project_id: str, args: ProposeTournamentInput):
    dataset = db.get(Dataset, args.dataset_id)
    if not dataset or dataset.project_id != project_id:
        return {"error": "Dataset not found in this project"}, None

    methodology_ids = list(dict.fromkeys(args.methodology_ids))  # de-dupe, preserve order
    if not (2 <= len(methodology_ids) <= 3):
        return {
            "error": "A tournament needs 2-3 distinct methodology_ids "
            f"(got {len(methodology_ids)} after de-duplication)"
        }, None

    # Resolve every candidate's spec up front: reject unknown/ensemble ids and
    # require a single common task_family (mixed-family tournaments aren't supported).
    specs: dict[str, dict[str, Any]] = {}
    for mid in methodology_ids:
        try:
            spec = get_spec(mid)
        except KeyError as e:
            return {"error": str(e)}, None
        if spec["task_family"] == "ensemble":
            return {
                "error": f"'{mid}' is an ensemble.* methodology auto-built by the tournament "
                "workflow; it cannot be a tournament candidate."
            }, None
        specs[mid] = spec

    families = {spec["task_family"] for spec in specs.values()}
    if len(families) > 1:
        return {
            "error": "All tournament candidates must share the same task_family "
            f"(got: {', '.join(sorted(families))})"
        }, None
    family = families.pop()

    if args.ensemble != "none" and family != "supervised":
        return {
            "error": f"ensemble='{args.ensemble}' is only supported for supervised "
            f"tournaments; '{family}' tournaments must use ensemble='none'"
        }, None

    if family == "forecasting":
        validation = {"n_splits": args.n_splits, "strategy": "time_ordered"}
    else:
        validation = {"n_splits": args.n_splits}

    # Validate every candidate plan BEFORE persisting anything — all-or-nothing.
    validated_plans: list[dict] = []
    for mid in methodology_ids:
        spec = specs[mid]
        plan_data = {
            "task_type": args.task_type,
            "data_shape": spec["data_shape"],
            "task_family": spec["task_family"],
            "target_column": args.target_column,
            "time_column": args.time_column,
            "horizon": args.horizon,
            "methodology_id": mid,
            "excluded_columns": args.excluded_columns,
            "validation": validation,
            "primary_metric": args.primary_metric,
            "reasoning": args.reasoning,
        }
        plan, errors = validate_plan(plan_data, dataset.profile)
        if errors:
            return {
                "error": f"Plan validation failed for candidate '{mid}'",
                "details": errors,
            }, None
        validated_plans.append(plan)

    tournament_id = uuid.uuid4().hex
    candidate_runs = [
        Run(
            project_id=project_id,
            dataset_id=dataset.id,
            plan=plan,
            tournament_id=tournament_id,
            tournament_role="candidate",
        )
        for plan in validated_plans
    ]
    for run in candidate_runs:
        db.add(run)
    db.flush()  # id defaults fire at flush; the ensemble plan needs real base_run_ids

    ensemble_run: Run | None = None
    if args.ensemble != "none":
        ensemble_plan_data = {
            "task_type": args.task_type,
            "data_shape": "tabular",
            "task_family": "ensemble",
            "target_column": args.target_column,
            "time_column": None,
            "horizon": None,
            "methodology_id": f"ensemble.{args.ensemble}",
            "excluded_columns": args.excluded_columns,
            "validation": {"n_splits": args.n_splits},
            "primary_metric": args.primary_metric,
            "reasoning": args.reasoning,
            "base_run_ids": [r.id for r in candidate_runs],
        }
        ensemble_plan, errors = validate_plan(ensemble_plan_data, dataset.profile)
        if errors:
            db.rollback()
            return {
                "error": "Ensemble plan validation failed",
                "details": errors,
            }, None
        ensemble_run = Run(
            project_id=project_id,
            dataset_id=dataset.id,
            plan=ensemble_plan,
            tournament_id=tournament_id,
            tournament_role="ensemble",
            status="waiting",
        )
        db.add(ensemble_run)
        db.flush()

    db.commit()

    card = {
        "type": "tournament",
        "tournament_id": tournament_id,
        "dataset_id": dataset.id,
        "dataset_filename": dataset.filename,
        "ensemble": args.ensemble,
        "candidates": [{"run_id": r.id, "plan": r.plan} for r in candidate_runs],
        "ensemble_run": (
            {"run_id": ensemble_run.id, "plan": ensemble_run.plan} if ensemble_run else None
        ),
        "reasoning": args.reasoning,
    }
    result = {
        "tournament_id": tournament_id,
        "candidate_run_ids": [r.id for r in candidate_runs],
        "ensemble_run_id": ensemble_run.id if ensemble_run else None,
        "status": "pending_approval",
    }
    return result, card


@tool("get_run_status", "Get the current status and progress of a training run.")
def get_run_status(db: Session, project_id: str, args: GetRunStatusInput):
    run = db.get(Run, args.run_id)
    if not run or run.project_id != project_id:
        return {"error": "Run not found in this project"}, None
    return {"run_id": run.id, "status": run.status, "progress": run.progress}, None


@tool(
    "get_results",
    "Get the full results of a completed training run: CV and holdout metrics, "
    "baseline comparison, confusion matrix or residuals, feature importances, "
    "dropped features, and caveats.",
)
def get_results(db: Session, project_id: str, args: GetResultsInput):
    run = db.get(Run, args.run_id)
    if not run or run.project_id != project_id:
        return {"error": "Run not found in this project"}, None
    if run.status != "completed":
        return {"error": f"Run is '{run.status}', results not available"}, None
    return run.results, None


@tool(
    "retrain_run",
    "Retrain a completed run's approved plan on the latest version of its dataset. "
    "Use when the user has updated the data and wants the model refreshed. Training "
    "starts immediately (the plan was already approved).",
)
def retrain_run_tool(db: Session, project_id: str, args: RetrainRunInput):
    run = db.get(Run, args.run_id)
    if not run or run.project_id != project_id:
        return {"error": "Run not found in this project"}, None
    try:
        new_run = retrain_run(db, run)
    except (NoNewerDataError, ValueError) as e:
        return {"error": str(e)}, None
    latest = db.get(Dataset, new_run.dataset_id)
    card = {
        "type": "retrain",
        "run_id": new_run.id,
        "parent_run_id": run.id,
        "dataset_id": latest.id,
        "dataset_filename": latest.filename,
        "plan": new_run.plan,
    }
    result = {
        "run_id": new_run.id,
        "status": new_run.status,
        "dataset_version": latest.version,
        "parent_run_id": run.id,
    }
    return result, card


# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [spec.to_anthropic() for spec in _REGISTRY.values()]


def dispatch(db: Session, project_id: str, name: str, tool_input: dict) -> tuple[str, dict | None]:
    """Execute a tool call. Returns (result_json, card_or_none). Raises nothing:
    errors are returned as strings so the LLM can adjust."""
    spec = _REGISTRY.get(name)
    if spec is None:
        return json.dumps({"error": f"Unknown tool: {name}"}), None
    try:
        args = spec.input_model.model_validate(tool_input)
    except ValidationError as e:
        details = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        return json.dumps({"error": "Invalid tool input", "details": details}), None
    try:
        result, card = spec.handler(db, project_id, args)
        return json.dumps(result), card
    except Exception as e:  # surface tool bugs to the LLM instead of crashing the turn
        db.rollback()
        return json.dumps({"error": f"Tool execution failed: {e}"}), None
