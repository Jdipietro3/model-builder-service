"""Tool definitions and dispatch for the orchestrator.

Each tool maps to deterministic code in app.ml. Tool inputs are pydantic models:
the tool schema is generated from the model (per-provider dialect via
ToolSpec.to_anthropic / to_openai), and incoming tool_input is validated against
it before the handler runs (validation errors go back to the LLM as the
tool_result so it can self-correct).

The dispatcher returns (result_json, card): result_json goes back to the LLM as
the tool_result; card, when present, is a structured payload streamed to the UI.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..ml.plans import diagnose_plan, validate_plan
from ..ml.profiling import profile_path
from ..ml.registry.loader import get_spec, list_methodologies
from ..models import Dataset, Project, Run
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


class SetRecommendationInput(ToolInput):
    run_id: str
    reason: str


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

    def to_openai(self) -> dict[str, Any]:
        """Same schema in OpenAI function-calling shape (DeepSeek, vLLM, Ollama...)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _clean_schema(self.input_model.model_json_schema()),
            },
        }


# JSON Schema keywords whose values are themselves schemas, so the walkers below
# know where to recurse. Everything not listed here is literal data (`enum`,
# `const`, `required`, ...) and is passed through untouched. This distinction
# matters: `properties` is a *map of field name -> schema*, so a model with a
# field literally named "title", "default" or "anyOf" would otherwise have that
# field silently mangled or deleted by the cleanups.
_SCHEMA_VALUE_KEYS = ("items", "additionalProperties", "not", "propertyNames", "contains")
_SCHEMA_LIST_KEYS = ("anyOf", "oneOf", "allOf", "prefixItems")
_SCHEMA_MAP_KEYS = ("properties", "patternProperties", "$defs", "definitions")


def _walk_schema(node: Any, fn: Callable[[dict], dict]) -> Any:
    """Apply `fn` to every schema node in `node`, bottom-up.

    Recurses only through the keywords above, so field names inside
    `properties` are never mistaken for schema keywords.
    """
    if not isinstance(node, dict):
        return node
    out = dict(node)
    for key in _SCHEMA_VALUE_KEYS:
        if isinstance(out.get(key), dict):
            out[key] = _walk_schema(out[key], fn)
    for key in _SCHEMA_LIST_KEYS:
        if isinstance(out.get(key), list):
            out[key] = [_walk_schema(b, fn) for b in out[key]]
    for key in _SCHEMA_MAP_KEYS:
        if isinstance(out.get(key), dict):
            out[key] = {k: _walk_schema(v, fn) for k, v in out[key].items()}
    return fn(out)


def _inline_refs(node: Any, defs: dict[str, Any], chain: tuple[str, ...] = ()) -> Any:
    """Recursively resolve `$ref` against `defs`, substituting the definition inline.

    `chain` tracks the ref names currently being expanded on this path, so a
    self-referential (or mutually-recursive) model raises a clear ValueError
    instead of recursing until the stack overflows. No current model is
    recursive; this guard is so a future one fails loudly at import time
    rather than hanging or crashing obscurely.
    """
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in chain:
            raise ValueError(
                f"Recursive model in tool input schema: {' -> '.join((*chain, name))}. "
                "Recursive/self-referential models can't be inlined into a flat tool schema."
            )
        if name not in defs:
            raise ValueError(f"Unresolved $ref '{ref}': no matching entry in $defs")
        resolved = _inline_refs(defs[name], defs, chain + (name,))
        # A $ref sibling (e.g. pydantic's {"$ref": ..., "description": ...})
        # carries extra keys that must survive, with the resolved def merged
        # underneath so the sibling keys win on conflict. `resolved` is a fresh
        # dict per call, so two refs to the same def never alias.
        merged = dict(resolved)
        merged.update({k: _inline_refs(v, defs, chain) for k, v in node.items() if k != "$ref"})
        return merged

    out = dict(node)
    for key in _SCHEMA_VALUE_KEYS:
        if isinstance(out.get(key), dict):
            out[key] = _inline_refs(out[key], defs, chain)
    for key in _SCHEMA_LIST_KEYS:
        if isinstance(out.get(key), list):
            out[key] = [_inline_refs(b, defs, chain) for b in out[key]]
    for key in _SCHEMA_MAP_KEYS:
        if isinstance(out.get(key), dict):
            out[key] = {k: _inline_refs(v, defs, chain) for k, v in out[key].items()}
    return out


def _strip_node(node: dict) -> dict:
    """The per-node cleanups: drop `title` (noise for an LLM) and `default`
    (some providers read it as a value the model needn't supply), and collapse
    Optional[X]'s `anyOf: [X, null]` down to X - optionality is already conveyed
    by absence from `required`. `enum`, `description`, `type`, `items` and the
    constraint keywords are left untouched."""
    node.pop("title", None)
    node.pop("default", None)
    if "anyOf" in node:
        branches = [b for b in node["anyOf"] if isinstance(b, dict) and b.get("type") != "null"]
        if len(branches) == 1:
            node.pop("anyOf")
            node.update(branches[0])
    return node


def _clean_schema(schema: dict) -> dict:
    """Trim pydantic's JSON schema down to what LLM tool schemas expect.

    Builds and returns a new dict; the argument (a fresh model_json_schema())
    is not mutated.

    Nested models make pydantic emit `$defs`/`$ref` rather than an inline
    schema. Anthropic handles `$ref` poorly and smaller open models handle it
    worse, and every provider adapter here (see
    app/orchestrator/providers/anthropic_provider.py and openai_provider.py)
    passes the schema straight through to the model with no ref-resolution of
    its own — so instead of asserting tool inputs stay flat, we recursively
    inline every `$ref` against `$defs` (deep-copying each substitution so two
    refs to the same def don't alias) and then drop `$defs` entirely. The
    title/default/anyOf-optional cleanups are then applied recursively at
    every level of the resulting tree, not just top-level properties.
    """
    defs = schema.get("$defs", {})
    inlined = _inline_refs(schema, defs)
    inlined.pop("$defs", None)
    return _walk_schema(inlined, _strip_node)


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
    # Non-blocking pre-approval warnings (leakage, target missingness, near-constant
    # features) ride on the plan so both the LLM and the plan card see them.
    warnings = diagnose_plan(plan, dataset.profile or {})
    plan["warnings"] = warnings
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
    return {"run_id": run.id, "status": "pending_approval", "plan": plan, "warnings": warnings}, card


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


@tool("set_recommendation",
    "Record which trained run is the recommended model for this project, with a one-sentence reason. "
    "Call this whenever you recommend a best model or change your recommendation (after a tournament, "
    "after training/retraining, or when the user gives a reason to switch). Overwrites any prior recommendation.")
def set_recommendation(db: Session, project_id: str, args: SetRecommendationInput):
    run = db.get(Run, args.run_id)
    if not run or run.project_id != project_id:
        return {"error": "Run not found in this project"}, None
    if run.status != "completed":
        return {"error": f"Run is '{run.status}' — only completed runs can be recommended"}, None
    project = db.get(Project, project_id)
    project.recommended_run_id = args.run_id
    project.recommendation_reason = args.reason
    db.commit()
    result = {"ok": True, "run_id": args.run_id, "reason": args.reason}
    card = {"type": "recommendation", "project_id": project_id, "run_id": args.run_id, "reason": args.reason}
    return result, card


# ---------------------------------------------------------------------------

# Providers serialize these per dialect (to_anthropic / to_openai), so the
# specs are exported rather than one pre-rendered schema list.
TOOL_SPECS: list[ToolSpec] = list(_REGISTRY.values())


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
