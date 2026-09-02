"""Unit tests for app.ml.plans: validate_plan / diagnose_plan.

Profiles come from the real sample CSVs via app.ml.profiling.profile_path
(session-scoped fixtures below) rather than hand-written dicts, so these
tests can't drift from the real profile shape. profile_path on a few-
thousand-row CSV is fast (no model training), so this stays in the fast tier.
"""

import copy

import pytest

from app.ml.plans import _not_yet_runnable, _validate_ensemble, diagnose_plan, validate_plan
from app.ml.profiling import profile_path

# ---------------------------------------------------------------------------
# Session-scoped real profiles.


@pytest.fixture(scope="session")
def churn_profile(churn_csv):
    return profile_path(churn_csv)


@pytest.fixture(scope="session")
def house_profile(house_csv):
    return profile_path(house_csv)


def _base_supervised_plan(**overrides):
    plan = dict(
        task_type="binary_classification",
        methodology_id="classification.logistic_baseline",
        target_column="churned",
        excluded_columns=["customer_id"],
        primary_metric="roc_auc",
        reasoning="test plan",
    )
    plan.update(overrides)
    return plan


# ---------------------------------------------------------------------------
# Valid plan + axis normalization


def test_valid_supervised_plan_validates_cleanly(churn_profile):
    plan, errors = validate_plan(_base_supervised_plan(), churn_profile)
    assert errors == []
    assert isinstance(plan, dict)
    assert plan["target_column"] == "churned"


def test_data_shape_and_task_family_are_normalized_to_the_spec(churn_profile):
    """validate_plan overwrites data_shape/task_family with the methodology
    spec's own values rather than erroring on a mismatch — the axes are a
    property of the chosen methodology, not a free LLM choice (see the
    "Consistency" comment in validate_plan)."""
    plan_data = _base_supervised_plan(data_shape="timeseries", task_family="forecasting")
    plan, errors = validate_plan(plan_data, churn_profile)
    assert errors == []
    assert plan["data_shape"] == "tabular"
    assert plan["task_family"] == "supervised"


# ---------------------------------------------------------------------------
# Supervised error paths (parametrized: one deliberate violation each).


@pytest.mark.parametrize(
    "overrides,expected_substring",
    [
        ({"target_column": "not_a_column"}, "Target column 'not_a_column' not found"),
        ({"excluded_columns": ["not_a_column"]}, "Excluded columns not in dataset: not_a_column"),
        # logistic_baseline's binary_classification metrics don't include 'mae'.
        ({"primary_metric": "mae"}, "not supported for binary_classification"),
        # logistic_baseline only supports binary/multiclass classification.
        ({"task_type": "regression"}, "does not support task type 'regression'"),
    ],
)
def test_supervised_validation_errors(churn_profile, overrides, expected_substring):
    plan_data = _base_supervised_plan(**overrides)
    plan, errors = validate_plan(plan_data, churn_profile)
    assert plan is None
    assert any(expected_substring in e for e in errors), errors


def test_unknown_methodology_id_errors(churn_profile):
    plan_data = _base_supervised_plan(methodology_id="not.a.real.methodology")
    plan, errors = validate_plan(plan_data, churn_profile)
    assert plan is None
    assert any("not.a.real.methodology" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Forecasting (isolated errors — churn.csv has no datetime column, so a fully
# valid forecasting plan can't be built from it; each case below pins one
# specific error message rather than a full pass).


def _base_forecasting_plan(**overrides):
    plan = dict(
        task_type="forecasting",
        methodology_id="forecasting.prophet",
        target_column="monthly_charges",  # numeric column -> valid target kind
        time_column="tenure_months",  # numeric, not datetime -> deliberately wrong
        horizon=10,
        primary_metric="mase",
        reasoning="test forecasting plan",
    )
    plan.update(overrides)
    return plan


def test_forecasting_missing_time_column_errors(churn_profile):
    plan_data = _base_forecasting_plan(time_column=None)
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("time_column is required" in e for e in errors), errors


def test_forecasting_non_datetime_time_column_errors(churn_profile):
    plan_data = _base_forecasting_plan(time_column="contract_type")  # categorical, not datetime
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("was not recognized as dates" in e for e in errors), errors


def test_forecasting_non_numeric_target_errors(churn_profile):
    # 'churned' is a 0/1 column with only 2 distinct values, so the profiler
    # classifies it as kind='boolean', not 'numeric'.
    plan_data = _base_forecasting_plan(target_column="churned")
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("must be a numeric series to forecast" in e for e in errors), errors


def test_forecasting_horizon_out_of_range_errors(churn_profile):
    max_horizon = churn_profile["n_rows"] // 3
    plan_data = _base_forecasting_plan(horizon=max_horizon + 500)
    _, errors = validate_plan(plan_data, churn_profile)
    assert any(f"horizon must be between 1 and {max_horizon}" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Ensemble


def _base_ensemble_plan(**overrides):
    plan = dict(
        task_type="binary_classification",
        methodology_id="ensemble.blend",
        target_column="churned",
        primary_metric="roc_auc",
        reasoning="test ensemble plan",
        base_run_ids=["run-a", "run-b"],
    )
    plan.update(overrides)
    return plan


def test_ensemble_plan_with_two_base_runs_validates(churn_profile):
    plan, errors = validate_plan(_base_ensemble_plan(), churn_profile)
    assert errors == []
    assert plan["task_family"] == "ensemble"


def test_ensemble_requires_at_least_two_base_run_ids(churn_profile):
    plan_data = _base_ensemble_plan(base_run_ids=["only-one"])
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("at least 2 base_run_ids" in e for e in errors), errors


def test_ensemble_requires_target_column(churn_profile):
    plan_data = _base_ensemble_plan(target_column=None)
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("target_column is required for ensemble" in e for e in errors), errors


def test_validate_ensemble_unit_metric_not_supported(churn_profile):
    """Direct unit exercise of _validate_ensemble (not just through
    validate_plan) for the metric-support branch."""
    from app.ml.registry.loader import get_spec
    from app.schemas import Plan

    spec = get_spec("ensemble.blend")
    plan = Plan(**_base_ensemble_plan(primary_metric="mae"))  # 'mae' isn't in binary_classification's supported list
    errors: list[str] = []
    _validate_ensemble(plan, spec, churn_profile, errors)
    assert any("not supported for binary_classification" in e for e in errors), errors


# ---------------------------------------------------------------------------
# clustering / anomaly: no runnable spec exists in the registry to exercise
# these end-to-end through validate_plan, so _not_yet_runnable is tested
# directly as the unit it is.


@pytest.mark.parametrize("family", ["clustering", "anomaly"])
def test_not_yet_runnable_families_report_unrunnable(family):
    errors: list[str] = []
    _not_yet_runnable(family)(None, None, None, errors)
    assert errors == [f"task_family '{family}' methodologies are not yet runnable in this build"]


# ---------------------------------------------------------------------------
# Phase 0 field validation (_validate_new_fields, exercised through
# validate_plan since that's the only public entry point).


def test_preprocessing_step_unknown_column_errors(churn_profile):
    plan_data = _base_supervised_plan(
        preprocessing=[{"op": "scale", "columns": ["not_a_real_column"]}]
    )
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("references columns not in dataset" in e for e in errors), errors


def test_preprocessing_step_empty_columns_is_not_an_error(churn_profile):
    # Empty columns means "applies to the auto-selected group" — not a typo.
    plan_data = _base_supervised_plan(preprocessing=[{"op": "scale", "columns": []}])
    plan, errors = validate_plan(plan_data, churn_profile)
    assert errors == []
    assert plan is not None


def test_nested_hyperparameters_errors(churn_profile):
    plan_data = _base_supervised_plan(hyperparameters={"C": {"low": 0.1, "high": 10}})
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("nested dict" in e for e in errors), errors


def test_whitespace_only_revision_of_run_id_errors(churn_profile):
    plan_data = _base_supervised_plan(revision_of_run_id="   ")
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("revision_of_run_id must be a non-empty string" in e for e in errors), errors


def test_all_four_phase0_fields_set_validly_passes(churn_profile):
    plan_data = _base_supervised_plan(
        preprocessing=[{"op": "scale", "columns": ["tenure_months"]}],
        hyperparameters={"C": 1.0},
        tuning={"strategy": "random", "n_trials": 10},
        revision_of_run_id="run_abc123",
    )
    plan, errors = validate_plan(plan_data, churn_profile)
    assert errors == []
    assert plan["hyperparameters"] == {"C": 1.0}
    assert plan["tuning"]["strategy"] == "random"
    assert plan["revision_of_run_id"] == "run_abc123"


# ---------------------------------------------------------------------------
# diagnose_plan: non-blocking. None of the sample CSVs naturally produce a
# high target_associations score (churn.csv's max is ~0.45, well under the
# 0.75/0.9 thresholds), so a high-leakage-score profile is constructed by
# mutating a deep copy of the real profile's target_associations, per the
# task instructions — never by writing a new CSV into samples/.


def test_diagnose_plan_is_non_blocking_on_high_leakage_signal(churn_profile):
    plan_data = _base_supervised_plan()
    plan, errors = validate_plan(plan_data, churn_profile)
    assert errors == []

    leaky_profile = copy.deepcopy(churn_profile)
    assocs = leaky_profile["target_associations"].setdefault("churned", [])
    assocs.insert(0, {"feature": "tenure_months", "score": 0.97, "method": "correlation_ratio"})

    warnings = diagnose_plan(plan, leaky_profile)
    leakage_warnings = [w for w in warnings if w["category"] == "leakage"]
    assert leakage_warnings, "expected a leakage warning from the injected 0.97 association score"
    assert leakage_warnings[0]["severity"] == "high"
    assert "tenure_months" in leakage_warnings[0]["columns"]

    # The high-score association is purely a diagnose_plan (advisory) signal —
    # validate_plan doesn't consult target_associations at all, so the same
    # plan against the same (now-leaky) profile still validates cleanly.
    plan2, errors2 = validate_plan(plan_data, leaky_profile)
    assert errors2 == []
    assert plan2 is not None


def test_diagnose_plan_no_warnings_on_ordinary_profile(churn_profile):
    plan_data = _base_supervised_plan()
    plan, _ = validate_plan(plan_data, churn_profile)
    warnings = diagnose_plan(plan, churn_profile)
    assert warnings == []


def test_diagnose_plan_no_target_is_a_graceful_noop():
    assert diagnose_plan({"target_column": None}, {"columns": []}) == []
