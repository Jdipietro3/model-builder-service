"""Plan validation shared by the orchestrator's propose_plan tool and the
run-approval endpoint (user edits are re-validated the same way)."""

from typing import Any

from pydantic import ValidationError

from ..schemas import Plan
from .registry.loader import get_spec


def validate_plan(plan_data: dict[str, Any], profile: dict[str, Any]) -> tuple[dict | None, list[str]]:
    """Returns (normalized_plan, errors). normalized_plan is None if invalid."""
    errors: list[str] = []
    try:
        plan = Plan(**plan_data)
    except ValidationError as e:
        return None, [str(err["msg"]) + f" ({'.'.join(str(x) for x in err['loc'])})" for err in e.errors()]

    try:
        spec = get_spec(plan.methodology_id)
    except KeyError as e:
        return None, [str(e)]

    if plan.task_type not in spec["task_types"]:
        errors.append(
            f"Methodology '{plan.methodology_id}' does not support task type '{plan.task_type}' "
            f"(supports: {', '.join(spec['task_types'])})"
        )

    column_names = {c["name"] for c in profile["columns"]}
    if plan.target_column not in column_names:
        errors.append(f"Target column '{plan.target_column}' not found in dataset")
    unknown_excluded = set(plan.excluded_columns) - column_names
    if unknown_excluded:
        errors.append(f"Excluded columns not in dataset: {', '.join(sorted(unknown_excluded))}")

    if plan.task_type in spec["metrics"]:
        supported = spec["metrics"][plan.task_type]["supported"]
        if plan.primary_metric not in supported:
            errors.append(
                f"Metric '{plan.primary_metric}' not supported for {plan.task_type} "
                f"with this methodology (supported: {', '.join(supported)})"
            )

    if errors:
        return None, errors
    return plan.model_dump(), []
