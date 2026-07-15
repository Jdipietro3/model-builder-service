"""Tool definitions and dispatch for the orchestrator.

Each tool maps to deterministic code in app.ml. The dispatcher returns
(result, card): result goes back to the LLM as the tool_result; card, when
present, is a structured payload streamed to the UI.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from ..ml.plans import validate_plan
from ..ml.profiling import profile_csv
from ..ml.registry.loader import list_methodologies
from ..models import Dataset, Run

TOOLS: list[dict[str, Any]] = [
    {
        "name": "profile_dataset",
        "description": (
            "Get the structured profile of an uploaded dataset: row/column counts, "
            "per-column type/kind, missingness, unique counts, sample values, "
            "candidate target columns, and data-quality warnings. Always call this "
            "before proposing a plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"dataset_id": {"type": "string"}},
            "required": ["dataset_id"],
        },
    },
    {
        "name": "list_methodologies",
        "description": (
            "List the curated methodology library, optionally filtered by task type. "
            "Returns each methodology's id, when-to-use guidance, and supported metrics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": ["binary_classification", "multiclass_classification", "regression"],
                }
            },
        },
    },
    {
        "name": "propose_plan",
        "description": (
            "Propose a training plan for user approval. Validates the plan against the "
            "registry and dataset, persists it as a pending run, and shows the user an "
            "editable plan card. Training does NOT start until the user approves the card."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "task_type": {
                    "type": "string",
                    "enum": ["binary_classification", "multiclass_classification", "regression"],
                },
                "target_column": {"type": "string"},
                "methodology_id": {"type": "string"},
                "excluded_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Columns to exclude from features (IDs, leakage risks, etc.)",
                },
                "n_splits": {"type": "integer", "minimum": 2, "maximum": 10},
                "primary_metric": {"type": "string"},
                "reasoning": {
                    "type": "string",
                    "description": "Why this framing and methodology fit, citing data characteristics.",
                },
            },
            "required": ["dataset_id", "task_type", "target_column", "methodology_id", "primary_metric", "reasoning"],
        },
    },
    {
        "name": "get_run_status",
        "description": "Get the current status and progress of a training run.",
        "input_schema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "get_results",
        "description": (
            "Get the full results of a completed training run: CV and holdout metrics, "
            "baseline comparison, confusion matrix or residuals, feature importances, "
            "dropped features, and caveats."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
]


def dispatch(db: Session, project_id: str, name: str, tool_input: dict) -> tuple[str, dict | None]:
    """Execute a tool call. Returns (result_json, card_or_none). Raises nothing:
    errors are returned as strings so the LLM can adjust."""
    try:
        if name == "profile_dataset":
            dataset = db.get(Dataset, tool_input["dataset_id"])
            if not dataset or dataset.project_id != project_id:
                return json.dumps({"error": "Dataset not found in this project"}), None
            if dataset.profile is None:
                dataset.profile = profile_csv(dataset.path)
                db.commit()
            return json.dumps(dataset.profile), None

        if name == "list_methodologies":
            return json.dumps(list_methodologies(tool_input.get("task_type"))), None

        if name == "propose_plan":
            dataset = db.get(Dataset, tool_input["dataset_id"])
            if not dataset or dataset.project_id != project_id:
                return json.dumps({"error": "Dataset not found in this project"}), None
            plan_data = {
                "task_type": tool_input["task_type"],
                "target_column": tool_input["target_column"],
                "methodology_id": tool_input["methodology_id"],
                "excluded_columns": tool_input.get("excluded_columns", []),
                "validation": {"n_splits": tool_input.get("n_splits", 5)},
                "primary_metric": tool_input["primary_metric"],
                "reasoning": tool_input["reasoning"],
            }
            plan, errors = validate_plan(plan_data, dataset.profile)
            if errors:
                return json.dumps({"error": "Plan validation failed", "details": errors}), None
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
            return json.dumps({"run_id": run.id, "status": "pending_approval", "plan": plan}), card

        if name == "get_run_status":
            run = db.get(Run, tool_input["run_id"])
            if not run or run.project_id != project_id:
                return json.dumps({"error": "Run not found in this project"}), None
            return json.dumps({"run_id": run.id, "status": run.status, "progress": run.progress}), None

        if name == "get_results":
            run = db.get(Run, tool_input["run_id"])
            if not run or run.project_id != project_id:
                return json.dumps({"error": "Run not found in this project"}), None
            if run.status != "completed":
                return json.dumps({"error": f"Run is '{run.status}', results not available"}), None
            return json.dumps(run.results), None

        return json.dumps({"error": f"Unknown tool: {name}"}), None
    except Exception as e:  # surface tool bugs to the LLM instead of crashing the turn
        db.rollback()
        return json.dumps({"error": f"Tool execution failed: {e}"}), None
