"""Deterministic training executor.

Takes an approved plan + methodology spec and produces a fitted pipeline plus
a results payload. All behavior here is hand-written and reproducible — the
LLM only chose the plan, it never defines what happens in this module.
"""

import time
import warnings
from typing import Any, Callable

# Benign sklearn/LightGBM interplay warning that floods logs during
# grid search and permutation importance.
warnings.filterwarnings("ignore", message="X does not have valid feature names")

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GridSearchCV, KFold, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler

from . import evaluation
from .profiling import load_csv, profile_dataframe
from .registry.loader import get_spec, resolve_model_class

ProgressCb = Callable[[str, int, str], None]

# Friendly metric name -> sklearn scoring string (used for CV / grid search).
METRIC_SCORING = {
    "roc_auc": "roc_auc",
    "pr_auc": "average_precision",
    "f1": "f1",
    "f1_macro": "f1_macro",
    "accuracy": "accuracy",
    "balanced_accuracy": "balanced_accuracy",
    "r2": "r2",
    "mae": "neg_mean_absolute_error",
    "rmse": "neg_root_mean_squared_error",
}

# Column kinds that are never used as features in v1.
AUTO_DROP_KINDS = {"id_like", "text", "datetime"}


def select_features(profile: dict, plan: dict) -> tuple[list[str], list[str], list[dict]]:
    """Partition usable columns into numeric/categorical; record what was dropped and why."""
    numeric, categorical, dropped = [], [], []
    excluded = set(plan.get("excluded_columns", []))
    for col in profile["columns"]:
        name, kind = col["name"], col["kind"]
        if name == plan["target_column"]:
            continue
        if name in excluded:
            dropped.append({"name": name, "reason": "excluded in plan"})
        elif col["n_unique"] <= 1:
            dropped.append({"name": name, "reason": "constant column"})
        elif kind in AUTO_DROP_KINDS:
            dropped.append({"name": name, "reason": f"{kind} column (unsupported in v1)"})
        elif kind == "numeric":
            numeric.append(name)
        else:  # categorical, boolean
            categorical.append(name)
    return numeric, categorical, dropped


def build_pipeline(spec: dict, numeric_cols: list[str], categorical_cols: list[str]) -> Pipeline:
    pre_cfg = spec["preprocessing"]
    transformers = []
    if numeric_cols:
        num_steps: list = [("impute", SimpleImputer(strategy=pre_cfg["numeric"]["impute"]))]
        if pre_cfg["numeric"].get("scale"):
            num_steps.append(("scale", StandardScaler()))
        transformers.append(("num", Pipeline(num_steps), numeric_cols))
    if categorical_cols:
        cat_steps = [
            ("impute", SimpleImputer(strategy=pre_cfg["categorical"]["impute"])),
            ("onehot", OneHotEncoder(handle_unknown="ignore", max_categories=30)),
        ]
        transformers.append(("cat", Pipeline(cat_steps), categorical_cols))

    model_cls = resolve_model_class(spec["model"]["class"])
    model = model_cls(**spec["model"].get("params", {}))
    return Pipeline(
        [
            ("preprocess", ColumnTransformer(transformers, remainder="drop")),
            ("model", model),
        ]
    )


def run_plan(csv_path: str, plan: dict, progress: ProgressCb) -> dict[str, Any]:
    """Execute the full train/evaluate sequence. Returns results + fitted pipeline
    + context needed by the artifact bundler."""
    t0 = time.time()
    spec = get_spec(plan["methodology_id"])
    task_type = plan["task_type"]
    is_classification = task_type != "regression"

    progress("preparing", 10, "Loading and preparing data")
    df = load_csv(csv_path)
    profile = profile_dataframe(df)
    if plan["target_column"] not in df.columns:
        raise ValueError(f"Target column '{plan['target_column']}' not found in dataset")

    numeric_cols, categorical_cols, dropped = select_features(profile, plan)
    feature_cols = numeric_cols + categorical_cols
    if not feature_cols:
        raise ValueError("No usable feature columns after exclusions")

    data = df.dropna(subset=[plan["target_column"]])
    X, y_raw = data[feature_cols], data[plan["target_column"]]

    label_classes: list[str] | None = None
    if is_classification:
        le = LabelEncoder()
        y = le.fit_transform(y_raw.astype(str))
        label_classes = [str(c) for c in le.classes_]
    else:
        y = y_raw.astype(float).to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if is_classification else None
    )

    # Cross-validated grid search on the training split
    n_splits = plan.get("validation", {}).get("n_splits", 5)
    strategy = plan.get("validation", {}).get("strategy", "stratified_kfold")
    if is_classification and strategy == "stratified_kfold":
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    else:
        cv = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    primary_metric = plan["primary_metric"]
    scoring = METRIC_SCORING[primary_metric]
    pipeline = build_pipeline(spec, numeric_cols, categorical_cols)
    grid = {f"model__{k}": v for k, v in spec["model"].get("grid", {}).items()}

    n_candidates = 1
    for values in spec["model"].get("grid", {}).values():
        n_candidates *= len(values)
    progress(
        "cross_validation",
        25,
        f"Cross-validating {n_candidates} configuration(s) x {n_splits} folds",
    )
    search = GridSearchCV(pipeline, grid, cv=cv, scoring=scoring, n_jobs=-1, refit=True)
    search.fit(X_train, y_train)

    best_idx = search.best_index_
    cv_summary = {
        "metric": primary_metric,
        "mean": round(float(search.cv_results_["mean_test_score"][best_idx]), 4),
        "std": round(float(search.cv_results_["std_test_score"][best_idx]), 4),
        "n_splits": n_splits,
        "n_candidates": n_candidates,
    }
    best_params = {k.removeprefix("model__"): v for k, v in search.best_params_.items()}
    fitted = search.best_estimator_

    progress("evaluating", 70, "Evaluating on held-out test data")
    metric_names = spec["metrics"][task_type]["supported"]
    holdout = evaluation.evaluate_holdout(
        fitted, X_test, y_test, y_train, task_type, metric_names, label_classes
    )
    progress("evaluating", 82, "Computing feature importances")
    importances = evaluation.permutation_importances(fitted, X_test, y_test, scoring)
    caveats = evaluation.build_caveats(
        task_type, primary_metric, holdout, importances, profile, plan, len(y_test)
    )

    results = {
        "methodology": {"id": spec["id"], "display_name": spec["display_name"]},
        "task_type": task_type,
        "target_column": plan["target_column"],
        "primary_metric": primary_metric,
        "best_params": best_params,
        "cv": cv_summary,
        "holdout": holdout,
        "feature_importances": importances,
        "features_used": feature_cols,
        "features_dropped": dropped,
        "caveats": caveats,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "training_seconds": round(time.time() - t0, 1),
    }
    return {
        "results": results,
        "pipeline": fitted,
        "spec": spec,
        "feature_columns": feature_cols,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "label_classes": label_classes,
        "best_params": best_params,
    }
