"""Plan validation shared by the orchestrator's propose_plan tool and the
run-approval endpoint (user edits are re-validated the same way).

Validation is family-aware: the two axes (``data_shape``, ``task_family``) are
properties of the chosen methodology, so they are normalized to the spec's values
(the spec wins) before a per-family validator runs. Only ``supervised`` is runnable
in this build; the other families validate to a "not yet runnable" error until their
runners land.
"""

from typing import Any, Callable

from pydantic import ValidationError

from ..schemas import Plan
from .pipeline import get_runner
from .registry.loader import get_spec

# Signature of a per-family validator: it appends any problems to `errors`.
FamilyValidator = Callable[[Plan, dict[str, Any], dict[str, Any], list[str]], None]


def _validate_supervised(
    plan: Plan, spec: dict[str, Any], profile: dict[str, Any], errors: list[str]
) -> None:
    """Supervised checks (moved verbatim from the pre-family validator)."""
    if plan.task_type not in spec["task_types"]:
        errors.append(
            f"Methodology '{plan.methodology_id}' does not support task type '{plan.task_type}' "
            f"(supports: {', '.join(spec['task_types'])})"
        )

    column_names = {c["name"] for c in profile["columns"]}
    if not plan.target_column:
        errors.append("target_column is required for supervised task_family")
    elif plan.target_column not in column_names:
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


def _validate_forecasting(
    plan: Plan, spec: dict[str, Any], profile: dict[str, Any], errors: list[str]
) -> None:
    """Forecasting checks: a datetime time axis, a numeric target, and a sane horizon."""
    if plan.task_type not in spec["task_types"]:
        errors.append(
            f"Methodology '{plan.methodology_id}' does not support task type '{plan.task_type}' "
            f"(supports: {', '.join(spec['task_types'])})"
        )

    columns = {c["name"]: c for c in profile["columns"]}
    if not plan.time_column:
        errors.append("time_column is required for forecasting task_family")
    elif plan.time_column not in columns:
        errors.append(f"Time column '{plan.time_column}' not found in dataset")
    elif columns[plan.time_column]["kind"] != "datetime":
        errors.append(
            f"Time column '{plan.time_column}' was not recognized as dates "
            f"(kind '{columns[plan.time_column]['kind']}'); it must hold parseable timestamps"
        )

    if not plan.target_column:
        errors.append("target_column is required for forecasting task_family")
    elif plan.target_column not in columns:
        errors.append(f"Target column '{plan.target_column}' not found in dataset")
    elif columns[plan.target_column]["kind"] != "numeric":
        errors.append(
            f"Target column '{plan.target_column}' must be a numeric series to forecast "
            f"(kind '{columns[plan.target_column]['kind']}')"
        )

    max_horizon = max(1, profile["n_rows"] // 3)
    if plan.horizon is None:
        errors.append("horizon is required for forecasting task_family")
    elif not (1 <= plan.horizon <= max_horizon):
        errors.append(
            f"horizon must be between 1 and {max_horizon} for a dataset with "
            f"{profile['n_rows']} rows (got {plan.horizon})"
        )

    supported = spec["metrics"]["forecasting"]["supported"]
    if plan.primary_metric not in supported:
        errors.append(
            f"Metric '{plan.primary_metric}' not supported for forecasting "
            f"with this methodology (supported: {', '.join(supported)})"
        )


def _validate_ensemble(
    plan: Plan, spec: dict[str, Any], profile: dict[str, Any], errors: list[str]
) -> None:
    """Ensemble checks: a target column (evaluation needs it), at least two base
    candidates to combine, and a primary_metric the spec supports for this task_type.
    Everything else (base run existence/status/family-compatibility) is validated by
    propose_tournament before an ensemble plan is even built."""
    column_names = {c["name"] for c in profile["columns"]}
    if not plan.target_column:
        errors.append("target_column is required for ensemble task_family")
    elif plan.target_column not in column_names:
        errors.append(f"Target column '{plan.target_column}' not found in dataset")

    if not plan.base_run_ids or len(plan.base_run_ids) < 2:
        errors.append("An ensemble plan requires at least 2 base_run_ids")

    if plan.task_type in spec["metrics"]:
        supported = spec["metrics"][plan.task_type]["supported"]
        if plan.primary_metric not in supported:
            errors.append(
                f"Metric '{plan.primary_metric}' not supported for {plan.task_type} "
                f"with this methodology (supported: {', '.join(supported)})"
            )


def _not_yet_runnable(family: str) -> FamilyValidator:
    """Stub validator for families whose runners are scaffolds.

    The real validators land with their runners:
    - clustering / anomaly: no target_column; validate intrinsic metric choice.
    """

    def _validate(
        plan: Plan, spec: dict[str, Any], profile: dict[str, Any], errors: list[str]
    ) -> None:
        errors.append(
            f"task_family '{family}' methodologies are not yet runnable in this build"
        )

    return _validate


_FAMILY_VALIDATORS: dict[str, FamilyValidator] = {
    "supervised": _validate_supervised,
    "forecasting": _validate_forecasting,
    "clustering": _not_yet_runnable("clustering"),
    "anomaly": _not_yet_runnable("anomaly"),
    "ensemble": _validate_ensemble,
}


def validate_plan(
    plan_data: dict[str, Any], profile: dict[str, Any]
) -> tuple[dict | None, list[str]]:
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

    # Consistency: the axes belong to the methodology. Spec wins — overwrite the
    # plan's values (no error) so callers can't override a methodology's shape/family.
    plan.data_shape = spec["data_shape"]
    plan.task_family = spec["task_family"]

    # Compatibility: the runner for this family must accept this data_shape.
    try:
        runner = get_runner(plan.task_family)
        if plan.data_shape not in runner.compatible_shapes:
            errors.append(
                f"data_shape '{plan.data_shape}' is not compatible with the "
                f"'{plan.task_family}' task runner (accepts: {', '.join(runner.compatible_shapes)})"
            )
    except ValueError:
        # No runner registered for this family; the family validator reports it.
        pass

    validator = _FAMILY_VALIDATORS.get(plan.task_family)
    if validator is None:
        errors.append(f"Unknown task_family '{plan.task_family}'")
    else:
        validator(plan, spec, profile, errors)

    if errors:
        return None, errors
    return plan.model_dump(), []


# Leakage-warning thresholds mirror the profile-level warning in
# ml/profiling/tabular.py (ASSOCIATION_LEAK_THRESHOLD = 0.9).
_LEAKAGE_HIGH_THRESHOLD = 0.9
_LEAKAGE_MEDIUM_THRESHOLD = 0.75
_TARGET_MISSINGNESS_THRESHOLD = 20
_NEAR_CONSTANT_PCT_THRESHOLD = 99


def diagnose_plan(plan: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Non-blocking pre-approval warnings for a validated plan (warn, don't block —
    flagged plans stay approvable). Never touches validate_plan's error path; a
    missing/absent `target_associations` (e.g. a dataset profiled before item 1
    landed) is treated as a graceful no-op, not an error.
    """
    warnings: list[dict[str, Any]] = []
    target = plan.get("target_column")
    if not target:
        return warnings
    excluded = set(plan.get("excluded_columns") or [])
    columns = profile.get("columns") or []
    columns_by_name = {c["name"]: c for c in columns}

    # (a) leakage: included features strongly associated with the target.
    associations = (profile.get("target_associations") or {}).get(target) or []
    high_cols = [
        a["feature"]
        for a in associations
        if a.get("feature") not in excluded and (a.get("score") or 0) >= _LEAKAGE_HIGH_THRESHOLD
    ]
    medium_cols = [
        a["feature"]
        for a in associations
        if a.get("feature") not in excluded
        and _LEAKAGE_MEDIUM_THRESHOLD <= (a.get("score") or 0) < _LEAKAGE_HIGH_THRESHOLD
    ]
    if high_cols:
        verb = "is" if len(high_cols) == 1 else "are"
        warnings.append(
            {
                "category": "leakage",
                "severity": "high",
                "message": (
                    f"{', '.join(high_cols)} {verb} near-perfectly associated with target "
                    f"'{target}' — likely leakage (verify these are genuinely available at "
                    "prediction time)."
                ),
                "columns": high_cols,
            }
        )
    if medium_cols:
        verb = "is" if len(medium_cols) == 1 else "are"
        warnings.append(
            {
                "category": "leakage",
                "severity": "medium",
                "message": (
                    f"{', '.join(medium_cols)} {verb} strongly associated with target "
                    f"'{target}' — worth checking for leakage."
                ),
                "columns": medium_cols,
            }
        )

    # (b) target_high_missingness
    target_info = columns_by_name.get(target)
    if target_info is not None and (target_info.get("pct_missing") or 0) > _TARGET_MISSINGNESS_THRESHOLD:
        warnings.append(
            {
                "category": "target_high_missingness",
                "severity": "medium",
                "message": (
                    f"Target '{target}' is missing in {target_info['pct_missing']}% of rows; "
                    "those rows are dropped before training, shrinking the effective dataset."
                ),
                "columns": [target],
            }
        )

    # (c) near_constant_feature: an included feature whose top value covers >99%.
    near_constant: list[str] = []
    for c in columns:
        name = c.get("name")
        if name == target or name in excluded:
            continue
        top_values = c.get("top_values")
        if top_values and (top_values[0].get("pct") or 0) > _NEAR_CONSTANT_PCT_THRESHOLD:
            near_constant.append(name)
    if near_constant:
        verb = "is" if len(near_constant) == 1 else "are"
        warnings.append(
            {
                "category": "near_constant_feature",
                "severity": "medium",
                "message": (
                    f"{', '.join(near_constant)} {verb} nearly constant (one value covers "
                    f">{_NEAR_CONSTANT_PCT_THRESHOLD}% of rows) — unlikely to carry signal."
                ),
                "columns": near_constant,
            }
        )

    return warnings
