"""Phase 2 tuning tests.

`resolve_budget` and plans.py's rejections are fast unit tests. The
strategy-comparison tests (none/random/bayesian) train real models on
`samples/churn.csv` and are marked `slow`, same tier as `test_golden.py`.
"""

import copy

import pytest

from app.config import TUNING_DEFAULT_TIME_S, TUNING_MAX_TIME_S
from app.ml import tuning
from app.ml.plans import validate_plan
from app.ml.profiling import profile_path
from app.ml.training import run_plan
from helpers import build_plan

# ---------------------------------------------------------------------------
# resolve_budget


def test_resolve_budget_defaults_absent():
    budget = tuning.resolve_budget(None, n_rows=5000)
    assert budget == {
        "strategy": "grid",
        "n_trials": 20,
        "time_budget_s": TUNING_DEFAULT_TIME_S,
        "cv_splits": None,
    }


def test_resolve_budget_small_dataset_defaults_to_fewer_trials():
    budget = tuning.resolve_budget({"strategy": "random"}, n_rows=1500)
    assert budget["n_trials"] == 10


def test_resolve_budget_large_dataset_defaults_to_more_trials():
    budget = tuning.resolve_budget({"strategy": "random"}, n_rows=5000)
    assert budget["n_trials"] == 20


def test_resolve_budget_time_budget_capped():
    budget = tuning.resolve_budget({"time_budget_s": TUNING_MAX_TIME_S + 5000}, n_rows=5000)
    assert budget["time_budget_s"] == TUNING_MAX_TIME_S


def test_resolve_budget_explicit_values_pass_through():
    budget = tuning.resolve_budget(
        {"strategy": "bayesian", "n_trials": 7, "time_budget_s": 42, "cv_splits": 3}, n_rows=5000
    )
    assert budget == {"strategy": "bayesian", "n_trials": 7, "time_budget_s": 42, "cv_splits": 3}


# ---------------------------------------------------------------------------
# plans.py rejections


@pytest.fixture(scope="session")
def churn_profile(churn_csv):
    return profile_path(churn_csv)


def _base_plan(**overrides):
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


def test_bayesian_on_spec_without_search_space_errors(churn_profile, monkeypatch):
    from app.ml import plans as plans_mod

    fake_spec = {
        "id": "fake.no_search_space",
        "task_types": ["binary_classification"],
        "data_shape": "tabular",
        "task_family": "supervised",
        "model": {"class": "sklearn.linear_model.LogisticRegression", "params": {}, "grid": {}},
        "metrics": {"binary_classification": {"default": "roc_auc", "supported": ["roc_auc"]}},
    }
    monkeypatch.setattr(plans_mod, "get_spec", lambda mid: fake_spec)

    plan_data = _base_plan(methodology_id="fake.no_search_space", tuning={"strategy": "bayesian"})
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("search_space" in e for e in errors), errors


def test_random_on_spec_without_search_space_errors(churn_profile, monkeypatch):
    from app.ml import plans as plans_mod

    fake_spec = {
        "id": "fake.no_search_space",
        "task_types": ["binary_classification"],
        "data_shape": "tabular",
        "task_family": "supervised",
        "model": {"class": "sklearn.linear_model.LogisticRegression", "params": {}, "grid": {}},
        "metrics": {"binary_classification": {"default": "roc_auc", "supported": ["roc_auc"]}},
    }
    monkeypatch.setattr(plans_mod, "get_spec", lambda mid: fake_spec)

    plan_data = _base_plan(methodology_id="fake.no_search_space", tuning={"strategy": "random"})
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("search_space" in e for e in errors), errors


def test_unknown_pinned_hyperparameter_key_errors(churn_profile):
    plan_data = _base_plan(hyperparameters={"not_a_real_param": 1.0})
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("not a known parameter" in e for e in errors), errors


def test_known_pinned_hyperparameter_key_passes(churn_profile):
    plan_data = _base_plan(hyperparameters={"C": 1.0})
    plan, errors = validate_plan(plan_data, churn_profile)
    assert errors == []
    assert plan["hyperparameters"] == {"C": 1.0}


def test_time_budget_above_cap_errors(churn_profile):
    plan_data = _base_plan(tuning={"strategy": "grid", "time_budget_s": TUNING_MAX_TIME_S + 1})
    _, errors = validate_plan(plan_data, churn_profile)
    assert any("exceeds the cap" in e for e in errors), errors


def test_time_budget_at_cap_passes(churn_profile):
    plan_data = _base_plan(tuning={"strategy": "grid", "time_budget_s": TUNING_MAX_TIME_S})
    _, errors = validate_plan(plan_data, churn_profile)
    assert errors == []


# ---------------------------------------------------------------------------
# End-to-end strategy runs on samples/churn.csv, classification.logistic_baseline.


def _churn_plan(**overrides):
    plan = build_plan(
        methodology_id="classification.logistic_baseline",
        target_column="churned",
        excluded_columns=["customer_id"],
        task_type="binary_classification",
        strategy="stratified_kfold",
        primary_metric="roc_auc",
    )
    plan.update(overrides)
    return plan


TUNING_ENVELOPE_KEYS = {
    "strategy",
    "n_trials",
    "n_pruned",
    "n_failed",
    "time_budget_s",
    "elapsed_s",
    "best_params",
    "search_space",
    "pinned",
    "trials",
    "importance",
    "note",
}


@pytest.mark.slow
def test_none_strategy_single_trial(churn_csv):
    plan = _churn_plan(tuning={"strategy": "none"})
    outcome = run_plan(churn_csv, plan, lambda *a: None)
    results = outcome.results

    assert set(results["tuning"]) == TUNING_ENVELOPE_KEYS
    assert results["tuning"]["strategy"] == "none"
    assert len(results["tuning"]["trials"]) == 1
    assert results["cv"]["n_candidates"] == 1


@pytest.mark.slow
def test_random_strategy_six_trials(churn_csv):
    plan = _churn_plan(tuning={"strategy": "random", "n_trials": 6})
    outcome = run_plan(churn_csv, plan, lambda *a: None)
    results = outcome.results

    assert set(results["tuning"]) == TUNING_ENVELOPE_KEYS
    assert results["tuning"]["strategy"] == "random"
    n_completed = results["tuning"]["n_trials"]
    assert n_completed > 0
    assert results["cv"]["n_candidates"] == n_completed
    assert set(results["best_params"]) <= set(results["tuning"]["search_space"] or {}) | set(
        results["tuning"]["pinned"]
    )


@pytest.mark.slow
def test_bayesian_strategy_six_trials(churn_csv):
    plan = _churn_plan(tuning={"strategy": "bayesian", "n_trials": 6})
    outcome = run_plan(churn_csv, plan, lambda *a: None)
    results = outcome.results

    assert set(results["tuning"]) == TUNING_ENVELOPE_KEYS
    assert results["tuning"]["strategy"] == "bayesian"
    n_completed = results["tuning"]["n_trials"]
    assert n_completed > 0
    assert results["cv"]["n_candidates"] == n_completed
    assert set(results["best_params"]) <= set(results["tuning"]["search_space"] or {}) | set(
        results["tuning"]["pinned"]
    )


@pytest.mark.slow
def test_random_strategy_is_deterministic(churn_csv):
    plan = _churn_plan(tuning={"strategy": "random", "n_trials": 6})
    r1 = run_plan(churn_csv, copy.deepcopy(plan), lambda *a: None).results
    r2 = run_plan(churn_csv, copy.deepcopy(plan), lambda *a: None).results
    assert r1["best_params"] == r2["best_params"]
    assert r1["cv"] == r2["cv"]


@pytest.mark.slow
def test_bayesian_strategy_is_deterministic(churn_csv):
    plan = _churn_plan(tuning={"strategy": "bayesian", "n_trials": 6})
    r1 = run_plan(churn_csv, copy.deepcopy(plan), lambda *a: None).results
    r2 = run_plan(churn_csv, copy.deepcopy(plan), lambda *a: None).results
    assert r1["best_params"] == r2["best_params"]
    assert r1["cv"] == r2["cv"]


@pytest.mark.slow
def test_pinned_hyperparameter_never_sampled_by_bayesian(churn_csv):
    # classification.logistic_baseline's only search_space param is C, so
    # pinning C leaves nothing to search — trials degrade to the single
    # pinned+default configuration (never an Optuna-sampled value for C).
    plan = _churn_plan(tuning={"strategy": "bayesian", "n_trials": 6}, hyperparameters={"C": 1.0})
    outcome = run_plan(churn_csv, plan, lambda *a: None)
    results = outcome.results

    for trial in results["tuning"]["trials"]:
        assert trial["params"].get("C") == 1.0
    assert results["best_params"].get("C") == 1.0
    assert "C" not in (results["tuning"]["search_space"] or {})


@pytest.mark.slow
def test_pinned_hyperparameter_never_sampled_by_bayesian_with_other_params(churn_csv):
    # random_forest has multiple search_space params; pinning one (max_depth)
    # must still leave the rest of the space searchable, with max_depth held
    # fixed across every trial.
    plan = build_plan(
        methodology_id="classification.random_forest",
        target_column="churned",
        excluded_columns=["customer_id"],
        task_type="binary_classification",
        strategy="stratified_kfold",
        primary_metric="roc_auc",
    )
    plan["tuning"] = {"strategy": "bayesian", "n_trials": 6}
    plan["hyperparameters"] = {"max_depth": 8}
    outcome = run_plan(churn_csv, plan, lambda *a: None)
    results = outcome.results

    for trial in results["tuning"]["trials"]:
        assert "max_depth" not in trial["params"]
    assert results["best_params"].get("max_depth") == 8
    assert "max_depth" not in (results["tuning"]["search_space"] or {})


@pytest.mark.slow
def test_time_budget_with_many_trials_finishes_quickly(churn_csv):
    import time

    plan = _churn_plan(tuning={"strategy": "random", "n_trials": 500, "time_budget_s": 10})
    t0 = time.time()
    outcome = run_plan(churn_csv, plan, lambda *a: None)
    elapsed = time.time() - t0
    assert elapsed < 60
    assert outcome.results["tuning"]["strategy"] == "random"
