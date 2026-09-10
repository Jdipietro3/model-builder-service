"""Tests for the Phase 1 recipe compiler (``app.ml.recipe``).

Golden equivalence itself (legacy_recipe producing byte-identical results to
pre-Phase-1 behavior) is covered by ``test_golden.py`` — this file exercises
the op registry, resolve/compile mechanics, default_recipe's profile-driven
choices, preview_recipe, and the standalone-bundle import path.
"""

import subprocess
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from helpers import GOLDEN_PLANS, build_plan

from app.ml import recipe
from app.ml.profiling.tabular import profile_dataframe
from app.ml.registry.loader import get_spec
from app.ml.scoring import predict_records, score_dataframe


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _logistic_spec():
    return get_spec("classification.logistic_baseline")


def _rf_regression_spec():
    return get_spec("regression.random_forest")


def _tiny_classification_df(n=60, seed=0) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    df = pd.DataFrame(
        {
            "num1": rng.normal(10, 3, n),
            "num2": rng.uniform(0, 100, n),
            "cat1": rng.choice(["a", "b", "c"], n),
        }
    )
    df["target"] = ((df["num1"] + df["num2"] / 10 + rng.normal(0, 2, n)) > 15).astype(int).astype(str)
    return df


def _fit_and_roundtrip(pipeline, X, y, tmp_path, name):
    pipeline.fit(X, y)
    preds_before = pipeline.predict(X)
    path = tmp_path / f"{name}.joblib"
    joblib.dump(pipeline, path)
    loaded = joblib.load(path)
    preds_after = loaded.predict(X)
    np.testing.assert_array_equal(np.asarray(preds_before, dtype=str), np.asarray(preds_after, dtype=str))
    return loaded


# --------------------------------------------------------------------------- #
# legacy_recipe compiles for every golden plan                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name,csv_fixture,methodology_id,target,excluded,task_type,strategy,metric",
    GOLDEN_PLANS,
    ids=[p[0] for p in GOLDEN_PLANS],
)
def test_legacy_recipe_compiles_for_golden_plans(
    request, name, csv_fixture, methodology_id, target, excluded, task_type, strategy, metric
):
    csv_path = request.getfixturevalue(csv_fixture)
    df = pd.read_csv(csv_path)
    profile = profile_dataframe(df)
    spec = get_spec(methodology_id)
    plan = build_plan(
        methodology_id=methodology_id,
        target_column=target,
        excluded_columns=excluded,
        task_type=task_type,
        strategy=strategy,
        primary_metric=metric,
    )

    steps = recipe.legacy_recipe(profile, spec, plan)
    pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
    assert info.feature_columns
    assert info.model_param_prefix == "model__"

    rows = df.dropna(subset=[target])
    X = rows[info.feature_columns]
    y = rows[target] if task_type == "regression" else rows[target].astype(str)
    pipeline.fit(X.head(100), y.head(100))
    pipeline.predict(X.head(5))


# --------------------------------------------------------------------------- #
# Per-op smoke tests: compile + fit + transform + joblib round-trip           #
# --------------------------------------------------------------------------- #


def _base_profile_and_spec():
    df = _tiny_classification_df()
    profile = profile_dataframe(df)
    spec = _logistic_spec()
    plan = {"target_column": "target", "task_type": "binary_classification", "excluded_columns": []}
    return df, profile, spec, plan


def test_op_impute_scale_encode_legacy():
    df, profile, spec, plan = _base_profile_and_spec()
    steps = recipe.legacy_recipe(profile, spec, plan)
    pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
    X, y = df[info.feature_columns], df["target"]
    pipeline.fit(X, y)
    pipeline.predict(X)


def test_op_datetime_expand(tmp_path):
    df = _tiny_classification_df()
    df["signup_date"] = pd.date_range("2023-01-01", periods=len(df), freq="D")
    profile = profile_dataframe(df)
    spec = _logistic_spec()
    plan = {"target_column": "target", "task_type": "binary_classification", "excluded_columns": []}
    steps = [
        {"op": "datetime_expand", "columns": ["signup_date"], "params": {}},
        {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": "median"}},
        {"op": "scale", "columns": [], "params": {"method": "standard"}},
        {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": "most_frequent"}},
        {"op": "encode", "columns": [], "params": {"method": "onehot", "max_categories": 30}},
    ]
    pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
    assert "signup_date" in info.feature_columns
    X, y = df[info.feature_columns], df["target"]
    _fit_and_roundtrip(pipeline, X, y, tmp_path, "datetime_expand")


def test_op_log_transform_and_power_and_clip(tmp_path):
    df, profile, spec, plan = _base_profile_and_spec()
    for op in ["log_transform", "power", "clip_outliers"]:
        params = {} if op == "log_transform" else ({"method": "yeo-johnson"} if op == "power" else {"lower_q": 0.05, "upper_q": 0.95})
        steps = [
            {"op": op, "columns": ["num1", "num2"], "params": params},
            {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": "median"}},
            {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": "most_frequent"}},
            {"op": "encode", "columns": [], "params": {"method": "onehot", "max_categories": 30}},
        ]
        pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
        X, y = df[info.feature_columns], df["target"]
        _fit_and_roundtrip(pipeline, X, y, tmp_path, f"op_{op}")


def test_op_bin_ordinal_and_onehot(tmp_path):
    df, profile, spec, plan = _base_profile_and_spec()
    for enc in ["ordinal", "onehot"]:
        steps = [
            {"op": "bin", "columns": ["num1"], "params": {"n_bins": 4, "strategy": "quantile", "encode": enc}},
            {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": "median"}},
            {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": "most_frequent"}},
            {"op": "encode", "columns": [], "params": {"method": "onehot", "max_categories": 30}},
        ]
        pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
        X, y = df[info.feature_columns], df["target"]
        _fit_and_roundtrip(pipeline, X, y, tmp_path, f"bin_{enc}")


def test_op_arithmetic_and_group_aggregate_and_interactions(tmp_path):
    df, profile, spec, plan = _base_profile_and_spec()
    steps = [
        {"op": "arithmetic", "columns": [], "params": {"expression": "ratio", "left": "num1", "right": "num2", "name": "ratio1"}},
        {"op": "group_aggregate", "columns": [], "params": {"key": "cat1", "column": "num1", "agg": "mean", "name": "num1_mean_by_cat1"}},
        {"op": "interactions", "columns": ["num1", "num2"], "params": {"degree": 2}},
        {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": "median"}},
        {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": "most_frequent"}},
        {"op": "encode", "columns": [], "params": {"method": "onehot", "max_categories": 30}},
    ]
    pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
    X, y = df[info.feature_columns], df["target"]
    fitted = _fit_and_roundtrip(pipeline, X, y, tmp_path, "arith_group_interactions")
    names = fitted.named_steps["preprocess"].get_feature_names_out()
    assert any("ratio1" in n for n in names)
    assert any("num1_mean_by_cat1" in n for n in names)
    assert any("num1_x_num2" in n for n in names)


def test_op_select_variance_kbest_from_model(tmp_path):
    df, profile, spec, plan = _base_profile_and_spec()
    for method, params in [("variance", {}), ("kbest", {"k": 3}), ("from_model", {})]:
        steps = [
            {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": "median"}},
            {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": "most_frequent"}},
            {"op": "encode", "columns": [], "params": {"method": "onehot", "max_categories": 30}},
            {"op": "select", "columns": [], "params": {"method": method, **params}},
        ]
        pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
        X, y = df[info.feature_columns], df["target"]
        _fit_and_roundtrip(pipeline, X, y, tmp_path, f"select_{method}")


def test_op_encode_target_and_frequency(tmp_path):
    df, profile, spec, plan = _base_profile_and_spec()
    for method in ["target", "frequency", "ordinal"]:
        steps = [
            {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": "median"}},
            {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": "most_frequent"}},
            {"op": "encode", "columns": ["cat1"], "params": {"method": method}},
        ]
        pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
        X, y = df[info.feature_columns], df["target"]
        _fit_and_roundtrip(pipeline, X, y, tmp_path, f"encode_{method}")


def test_op_class_balance_class_weight_and_smote(tmp_path):
    df, profile, spec, plan = _base_profile_and_spec()
    for method in ["class_weight", "smote"]:
        steps = recipe.legacy_recipe(profile, spec, plan) + [
            {"op": "class_balance", "columns": [], "params": {"method": method}}
        ]
        pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
        assert info.uses_imblearn == (method == "smote")
        X, y = df[info.feature_columns], df["target"]
        _fit_and_roundtrip(pipeline, X, y, tmp_path, f"class_balance_{method}")


def test_op_target_transform_regression(tmp_path):
    rng = np.random.RandomState(0)
    n = 60
    df = pd.DataFrame({"num1": rng.uniform(1, 50, n), "cat1": rng.choice(["x", "y"], n)})
    df["target"] = df["num1"] * 2 + rng.normal(0, 1, n) + 1
    profile = profile_dataframe(df)
    spec = _rf_regression_spec()
    plan = {"target_column": "target", "task_type": "regression", "excluded_columns": []}
    steps = recipe.legacy_recipe(profile, spec, plan) + [{"op": "target_transform", "columns": [], "params": {"method": "log1p"}}]
    pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
    assert info.model_param_prefix == "model__regressor__"
    X, y = df[info.feature_columns], df["target"]
    pipeline.fit(X, y)
    path = tmp_path / "target_transform.joblib"
    joblib.dump(pipeline, path)
    loaded = joblib.load(path)
    preds = loaded.predict(X)
    assert len(preds) == len(X)


# --------------------------------------------------------------------------- #
# default_recipe                                                              #
# --------------------------------------------------------------------------- #


def test_default_recipe_profile_driven_ops():
    rng = np.random.RandomState(1)
    n = 400
    df = pd.DataFrame(
        {
            "signup_date": pd.date_range("2022-01-01", periods=n, freq="D"),
            "zone": [f"zone_{i % 45}" for i in range(n)],  # high-cardinality categorical
            "amount": rng.exponential(scale=2.0, size=n) ** 2,  # heavily right-skewed, min >= 0
            # i % (n // 2): enough repeats to stay below the id_like threshold
            # (n_unique < 0.98 * n_rows) while remaining high-cardinality/wordy
            # enough to classify as text (cardinality_ratio > 0.5, avg_tokens > 3).
            "notes": [f"customer left a fairly long note about their order number {i % 250} today" for i in range(n)],
            "stable_num": rng.normal(0, 1, n),
        }
    )
    # Imbalanced binary target: ~10% minority.
    df["target"] = (rng.uniform(size=n) < 0.1).astype(int).astype(str)

    profile = profile_dataframe(df)
    spec = _logistic_spec()  # scale=true -> non-tree, log_transform eligible
    plan = {"target_column": "target", "task_type": "binary_classification", "excluded_columns": []}

    steps = recipe.default_recipe(profile, spec, plan)
    ops = [s["op"] for s in steps]

    assert "datetime_expand" in ops
    assert any(s["op"] == "log_transform" and "amount" in s["columns"] for s in steps)
    assert any(s["op"] == "drop" and "text column" in (s["params"].get("reason") or "") for s in steps)
    assert any(s["op"] == "encode" and s["columns"] and "zone" in s["columns"] for s in steps)
    assert "class_balance" in ops

    resolved = recipe.resolve_recipe({**plan, "preprocessing": None}, profile, spec)
    assert all(s["description"] for s in resolved)
    pipeline, info = recipe.compile_recipe(resolved, profile, spec, plan)
    X, y = df[info.feature_columns], df["target"]
    pipeline.fit(X.head(200), y.head(200))
    pipeline.predict(X.head(5))


# --------------------------------------------------------------------------- #
# resolve_recipe validation                                                   #
# --------------------------------------------------------------------------- #


def test_resolve_recipe_rejects_unknown_op():
    df, profile, spec, plan = _base_profile_and_spec()
    plan = {**plan, "preprocessing": [{"op": "not_a_real_op", "columns": [], "params": {}}]}
    with pytest.raises(ValueError, match="Unknown preprocessing op"):
        recipe.resolve_recipe(plan, profile, spec)


def test_resolve_recipe_rejects_unknown_column():
    df, profile, spec, plan = _base_profile_and_spec()
    plan = {**plan, "preprocessing": [{"op": "scale", "columns": ["not_a_real_column"], "params": {}}]}
    with pytest.raises(ValueError, match="not in the dataset"):
        recipe.resolve_recipe(plan, profile, spec)


def test_resolve_recipe_rejects_op_not_in_feature_ops_allowed():
    df, profile, spec, plan = _base_profile_and_spec()
    tree_spec = get_spec("classification.random_forest")
    assert tree_spec.get("feature_ops_allowed") is not None
    plan = {**plan, "preprocessing": [{"op": "scale", "columns": [], "params": {}}]}
    with pytest.raises(ValueError, match="not allowed"):
        recipe.resolve_recipe(plan, profile, tree_spec)


def test_resolve_recipe_rejects_class_balance_on_regression():
    df, profile, spec, plan = _base_profile_and_spec()
    reg_spec = _rf_regression_spec()
    plan = {**plan, "task_type": "regression", "preprocessing": [{"op": "class_balance", "columns": [], "params": {}}]}
    with pytest.raises(ValueError, match="task type"):
        recipe.resolve_recipe(plan, profile, reg_spec)


def test_resolve_recipe_rejects_empty_preprocessing_list():
    df, profile, spec, plan = _base_profile_and_spec()
    plan = {**plan, "preprocessing": []}
    with pytest.raises(ValueError, match="use null"):
        recipe.resolve_recipe(plan, profile, spec)


# --------------------------------------------------------------------------- #
# predict_records vs score_dataframe parity through a non-trivial recipe      #
# --------------------------------------------------------------------------- #


def test_predict_records_matches_score_dataframe_with_recipe(tmp_path):
    rng = np.random.RandomState(2)
    n = 200
    df = pd.DataFrame(
        {
            "signup_date": pd.date_range("2021-06-01", periods=n, freq="D"),
            "amount": rng.exponential(scale=3.0, size=n),
            "cat1": rng.choice(["p", "q", "r"], n),
        }
    )
    df["target"] = ((df["amount"] > df["amount"].median()) & (rng.uniform(size=n) > 0.1)).astype(int).astype(str)
    csv_path = tmp_path / "synthetic.csv"
    df.to_csv(csv_path, index=False)

    profile = profile_dataframe(df)
    spec = _logistic_spec()
    plan = {
        "target_column": "target",
        "task_type": "binary_classification",
        "excluded_columns": [],
        "primary_metric": "roc_auc",
        "preprocessing": [
            {"op": "datetime_expand", "columns": ["signup_date"], "params": {}},
            {"op": "log_transform", "columns": ["amount"], "params": {}},
            {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": "median"}},
            {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": "most_frequent"}},
            {"op": "encode", "columns": ["cat1"], "params": {"method": "target"}},
        ],
    }
    resolved = recipe.resolve_recipe(plan, profile, spec)
    pipeline, info = recipe.compile_recipe(resolved, profile, spec, plan)
    X, y = df[info.feature_columns], df["target"]
    pipeline.fit(X, y)

    meta = {
        "feature_columns": info.feature_columns,
        "task_type": "binary_classification",
        "task_family": "supervised",
        "label_classes": sorted(df["target"].unique()),
    }
    slice_df = pd.read_csv(csv_path).head(20)
    scored_df, _ = score_dataframe(pipeline, meta, slice_df)
    live = predict_records(pipeline, meta, slice_df.to_dict(orient="records"))
    assert live["predictions"] == scored_df["prediction"].tolist()


# --------------------------------------------------------------------------- #
# preview_recipe                                                              #
# --------------------------------------------------------------------------- #


def test_preview_recipe_shape_and_speed():
    rng = np.random.RandomState(3)
    n = 5000
    df = pd.DataFrame(
        {
            "num1": rng.normal(0, 1, n),
            "num2": rng.uniform(0, 10, n),
            "cat1": rng.choice(["a", "b", "c", "d"], n),
        }
    )
    df["target"] = ((df["num1"] + df["num2"]) > df["num1"].median()).astype(int).astype(str)
    profile = profile_dataframe(df)
    spec = _logistic_spec()
    plan = {
        "target_column": "target",
        "task_type": "binary_classification",
        "excluded_columns": [],
        "primary_metric": "roc_auc",
        "preprocessing": None,
    }

    t0 = time.time()
    result = recipe.preview_recipe(df, plan, spec, profile, max_rows=5000)
    elapsed = time.time() - t0

    for key in ("steps", "n_features_in", "n_features_out", "derived_columns", "dropped_columns", "cv", "n_rows_used"):
        assert key in result
    assert result["cv"] is not None
    assert result["cv"]["n_splits"] == 3
    assert result["n_rows_used"] == n
    assert elapsed < 10.0


def test_preview_recipe_never_raises_on_bad_metric():
    df, profile, spec, plan = _base_profile_and_spec()
    plan = {**plan, "primary_metric": "not_a_real_metric", "preprocessing": None}
    result = recipe.preview_recipe(df, plan, spec, profile)
    assert result["cv"] is None
    assert "error" in result


# --------------------------------------------------------------------------- #
# Bundle import: recipe.py + model.joblib load standalone in a clean process  #
# --------------------------------------------------------------------------- #


def test_bundle_recipe_and_model_importable_standalone(tmp_path):
    df, profile, spec, plan = _base_profile_and_spec()
    steps = recipe.legacy_recipe(profile, spec, plan)
    pipeline, info = recipe.compile_recipe(steps, profile, spec, plan)
    X, y = df[info.feature_columns], df["target"]
    pipeline.fit(X, y)

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    recipe_src = Path(recipe.__file__)
    (bundle_dir / "recipe.py").write_bytes(recipe_src.read_bytes())
    joblib.dump({"pipeline": pipeline, "meta": {"feature_columns": info.feature_columns}}, bundle_dir / "model.joblib")
    df.to_csv(bundle_dir / "data.csv", index=False)

    script = (
        "import sys, json\n"
        "sys.path.insert(0, '.')\n"
        "import joblib\n"
        "import recipe  # noqa: F401 -- registers the app.ml.recipe alias\n"
        "bundle = joblib.load('model.joblib')\n"
        "pipeline, meta = bundle['pipeline'], bundle['meta']\n"
        "import pandas as pd\n"
        "df = pd.read_csv('data.csv')\n"
        "preds = pipeline.predict(df[meta['feature_columns']])\n"
        "print(json.dumps({'n_preds': len(preds)}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(bundle_dir),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert '"n_preds"' in proc.stdout
