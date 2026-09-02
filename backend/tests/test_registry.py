"""Unit tests for app.ml.registry.loader: the YAML methodology registry.

load_registry() is @lru_cache'd, so these tests only ever read it — never
load_registry.cache_clear() — and build negative-path specs by instantiating
MethodologySpec directly rather than writing YAML into the real specs/ dir
(the loader would cache whatever it saw on the first call in this process).
"""

import pytest
from pydantic import ValidationError

from app.ml.registry.loader import (
    MethodologySpec,
    _validate_search_space,
    get_spec,
    list_methodologies,
    load_registry,
)

# The 12 specs checked into app/ml/registry/specs/ at the time this test was
# written (backend/app/ml/registry/specs/*.yaml, one id per file). A spec
# drops out of load_registry() only if its model's library isn't importable
# on this machine and it has no sklearn `fallback` — see loader._module_available.
EXPECTED_IDS = {
    "classification.lightgbm",
    "classification.logistic_baseline",
    "classification.random_forest",
    "classification.xgboost",
    "ensemble.blend",
    "ensemble.stacking",
    "forecasting.lightgbm_lags",
    "forecasting.prophet",
    "regression.lightgbm",
    "regression.linear_baseline",
    "regression.random_forest",
    "regression.xgboost",
}

MINIMAL_TABULAR_PREPROCESSING = {
    "numeric": {"impute": "median"},
    "categorical": {"impute": "most_frequent"},
}
MINIMAL_MODEL = {"class": "sklearn.linear_model.Ridge"}


def _spec_kwargs(**overrides):
    base = dict(
        id="test.spec",
        display_name="Test Spec",
        data_shape="tabular",
        task_family="supervised",
        task_types=["regression"],
        when_to_use="testing",
        preprocessing=MINIMAL_TABULAR_PREPROCESSING,
        model=MINIMAL_MODEL,
        metrics={"regression": {"default": "r2", "supported": ["r2"]}},
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# load_registry / get_spec / list_methodologies


def test_load_registry_returns_expected_ids_and_dotted_format():
    registry = load_registry()
    missing = EXPECTED_IDS - set(registry)
    # A spec silently drops out only when its library is missing on this
    # machine (see _module_available) — report which, but don't hard-fail
    # the whole suite over a machine-specific missing optional dependency.
    if missing:
        pytest.fail(
            f"specs missing from load_registry() (library not installed and no "
            f"fallback declared?): {sorted(missing)}. If this is expected on this "
            "machine, narrow EXPECTED_IDS accordingly."
        )
    assert set(registry) == EXPECTED_IDS
    for spec_id in registry:
        assert spec_id.count(".") == 1, f"expected 'family.name' id, got {spec_id!r}"


def test_every_loaded_spec_round_trips_methodologyspec_validation():
    for spec_id, spec in load_registry().items():
        # model_dump() -> MethodologySpec(**dump) must not raise: proves
        # load_registry() didn't hand back something its own validator would
        # reject (e.g. a fallback-swap that broke the model.class shape).
        rebuilt = MethodologySpec(**spec)
        assert rebuilt.id == spec_id


def test_get_spec_unknown_raises_keyerror_listing_available_ids():
    with pytest.raises(KeyError) as exc_info:
        get_spec("not.a.real.methodology")
    message = str(exc_info.value)
    assert "not.a.real.methodology" in message
    # Spot check a couple of real ids are listed rather than asserting every one.
    assert "classification.logistic_baseline" in message
    assert "regression.linear_baseline" in message


@pytest.mark.parametrize(
    "filters,expect_ids_subset,expect_absent",
    [
        ({"task_type": "regression"}, {"regression.linear_baseline"}, "classification.logistic_baseline"),
        ({"data_shape": "timeseries"}, {"forecasting.prophet"}, "regression.linear_baseline"),
        ({"task_family": "ensemble"}, {"ensemble.blend", "ensemble.stacking"}, "regression.linear_baseline"),
    ],
)
def test_list_methodologies_filters_by_each_axis(filters, expect_ids_subset, expect_absent):
    results = list_methodologies(**filters)
    ids = {r["id"] for r in results}
    assert expect_ids_subset <= ids
    assert expect_absent not in ids


def test_list_methodologies_summary_keys():
    results = list_methodologies(task_family="supervised")
    assert results, "expected at least one supervised methodology"
    expected_keys = {
        "id",
        "display_name",
        "data_shape",
        "task_family",
        "task_types",
        "when_to_use",
        "metrics",
    }
    for r in results:
        assert set(r) == expected_keys


# ---------------------------------------------------------------------------
# MethodologySpec shape validation (negative paths — built directly, no YAML).


def test_missing_model_class_rejected():
    with pytest.raises(ValidationError, match="model.class is required"):
        MethodologySpec(**_spec_kwargs(model={}))


def test_tabular_spec_missing_numeric_impute_rejected():
    with pytest.raises(ValidationError, match="preprocessing.numeric.impute"):
        MethodologySpec(**_spec_kwargs(preprocessing={"numeric": {}, "categorical": {"impute": "most_frequent"}}))


def test_timeseries_spec_bad_framing_rejected():
    with pytest.raises(ValidationError, match="framing must be"):
        MethodologySpec(
            **_spec_kwargs(
                data_shape="timeseries",
                task_family="forecasting",
                task_types=["forecasting"],
                preprocessing={"timeseries": {"framing": "bogus"}},
                metrics={"forecasting": {"default": "mase", "supported": ["mase"]}},
            )
        )


def test_supervised_task_type_missing_metrics_entry_rejected():
    with pytest.raises(ValidationError, match="metrics missing entry for supervised task_type 'regression'"):
        MethodologySpec(**_spec_kwargs(task_types=["regression"], metrics={}))


# ---------------------------------------------------------------------------
# model.search_space validation (Phase 0 plumbing, not yet populated by any
# real spec, so exercised directly through _validate_search_space).


def test_search_space_valid_int_float_categorical():
    _validate_search_space(
        {
            "n_estimators": {"type": "int", "low": 10, "high": 200},
            "learning_rate": {"type": "float", "low": 1e-4, "high": 1.0, "log": True},
            "criterion": {"type": "categorical", "choices": ["gini", "entropy"]},
        }
    )  # must not raise


@pytest.mark.parametrize(
    "param,entry",
    [
        ("bad_type", {"type": "quantum", "low": 0, "high": 1}),
        ("inverted", {"type": "int", "low": 10, "high": 1}),
        ("nonnumeric_low", {"type": "float", "low": "zero", "high": 1.0}),
        ("nonnumeric_high", {"type": "float", "low": 0.0, "high": "one"}),
        ("bad_log", {"type": "float", "low": 0.0, "high": 1.0, "log": "yes"}),
        ("empty_choices", {"type": "categorical", "choices": []}),
        ("absent_choices", {"type": "categorical"}),
    ],
)
def test_search_space_invalid_entries_name_the_param(param, entry):
    with pytest.raises(ValueError, match=param) as exc_info:
        _validate_search_space({param: entry})
    assert param in str(exc_info.value)


def test_search_space_wired_through_methodologyspec():
    # model.search_space is validated as part of full spec construction too,
    # not just when called in isolation.
    with pytest.raises(ValidationError, match="low"):
        MethodologySpec(
            **_spec_kwargs(model={"class": "sklearn.linear_model.Ridge", "search_space": {"alpha": {"type": "int", "low": 5, "high": 1}}})
        )


# ---------------------------------------------------------------------------
# feature_ops_allowed


def test_feature_ops_allowed_defaults_to_none():
    spec = MethodologySpec(**_spec_kwargs())
    assert spec.feature_ops_allowed is None
    assert spec.model_dump()["feature_ops_allowed"] is None


def test_feature_ops_allowed_round_trips_a_list():
    ops = ["impute", "scale", "onehot"]
    spec = MethodologySpec(**_spec_kwargs(feature_ops_allowed=ops))
    assert spec.feature_ops_allowed == ops
    dumped = spec.model_dump()
    assert dumped["feature_ops_allowed"] == ops
    # Round trips through re-validation too.
    assert MethodologySpec(**dumped).feature_ops_allowed == ops
