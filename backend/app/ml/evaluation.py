"""Holdout evaluation: metrics vs a naive baseline, importances, and
plain-language caveats. This is the substance behind the ReportCard."""

from typing import Any

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)

# Direction of improvement per metric ("higher" unless noted).
LOWER_IS_BETTER = {"mae", "rmse"}


def compute_metrics(
    metric_names: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray | None = None,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in metric_names:
        try:
            if name == "roc_auc":
                out[name] = roc_auc_score(y_true, y_proba[:, 1])
            elif name == "pr_auc":
                out[name] = average_precision_score(y_true, y_proba[:, 1])
            elif name == "f1":
                out[name] = f1_score(y_true, y_pred)
            elif name == "f1_macro":
                out[name] = f1_score(y_true, y_pred, average="macro")
            elif name == "accuracy":
                out[name] = accuracy_score(y_true, y_pred)
            elif name == "balanced_accuracy":
                out[name] = balanced_accuracy_score(y_true, y_pred)
            elif name == "r2":
                out[name] = r2_score(y_true, y_pred)
            elif name == "mae":
                out[name] = mean_absolute_error(y_true, y_pred)
            elif name == "rmse":
                out[name] = root_mean_squared_error(y_true, y_pred)
        except (ValueError, TypeError):
            continue  # metric undefined for this data (e.g. single-class fold)
    return {k: round(float(v), 4) for k, v in out.items()}


def evaluate_holdout(
    pipeline,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    y_train: np.ndarray,
    task_type: str,
    metric_names: list[str],
    label_classes: list[str] | None,
) -> dict[str, Any]:
    is_classification = task_type != "regression"
    y_pred = pipeline.predict(X_test)
    y_proba = None
    if is_classification and hasattr(pipeline, "predict_proba"):
        y_proba = pipeline.predict_proba(X_test)

    metrics = compute_metrics(metric_names, y_test, y_pred, y_proba)

    # Naive baseline: majority class / mean prediction. "Does the model add
    # anything over the dumbest possible strategy?"
    X_dummy = np.zeros((len(y_train), 1))
    if is_classification:
        dummy = DummyClassifier(strategy="prior").fit(X_dummy, y_train)
        majority = label_classes[int(np.bincount(y_train).argmax())]
        baseline_description = f"always predicting the majority class ('{majority}')"
    else:
        dummy = DummyRegressor(strategy="mean").fit(X_dummy, y_train)
        baseline_description = "always predicting the training-set mean"
    X_dummy_test = np.zeros((len(y_test), 1))
    base_pred = dummy.predict(X_dummy_test)
    base_proba = dummy.predict_proba(X_dummy_test) if is_classification else None
    baseline_metrics = compute_metrics(metric_names, y_test, base_pred, base_proba)

    holdout: dict[str, Any] = {
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "baseline_description": baseline_description,
    }

    if is_classification:
        cm = confusion_matrix(y_test, y_pred)
        holdout["confusion_matrix"] = {"labels": label_classes, "matrix": cm.tolist()}
    else:
        residuals = y_test - y_pred
        holdout["residuals"] = {
            "mean": round(float(residuals.mean()), 4),
            "p10": round(float(np.percentile(residuals, 10)), 4),
            "p90": round(float(np.percentile(residuals, 90)), 4),
            "target_mean": round(float(y_test.mean()), 4),
            "target_std": round(float(y_test.std()), 4),
        }
    return holdout


def permutation_importances(
    pipeline, X_test: pd.DataFrame, y_test: np.ndarray, scoring: str, top_k: int = 15
) -> list[dict[str, Any]]:
    """Importances on original columns (the pipeline owns the encoding, so
    permuting raw columns aggregates one-hot children automatically)."""
    result = permutation_importance(
        pipeline, X_test, y_test, scoring=scoring, n_repeats=5, random_state=42
    )
    order = np.argsort(-result.importances_mean)[:top_k]
    return [
        {
            "feature": X_test.columns[i],
            "importance": round(float(result.importances_mean[i]), 4),
            "std": round(float(result.importances_std[i]), 4),
        }
        for i in order
    ]


def build_caveats(
    task_type: str,
    primary_metric: str,
    holdout: dict,
    importances: list[dict],
    profile: dict,
    plan: dict,
    n_test: int,
) -> list[str]:
    """Plain-language warnings an ML engineer would flag in review."""
    caveats: list[str] = []

    # Dominant feature -> possible leakage
    positive = [imp for imp in importances if imp["importance"] > 0]
    total = sum(imp["importance"] for imp in positive)
    if positive and total > 0 and positive[0]["importance"] / total > 0.5:
        caveats.append(
            f"The model leans heavily on '{positive[0]['feature']}' "
            f"({positive[0]['importance'] / total:.0%} of total importance). Verify this column is "
            "genuinely available at prediction time and isn't leaking the answer."
        )

    # Barely beats baseline
    model_v = holdout["metrics"].get(primary_metric)
    base_v = holdout["baseline_metrics"].get(primary_metric)
    if model_v is not None and base_v is not None:
        better = model_v < base_v if primary_metric in LOWER_IS_BETTER else model_v > base_v
        if not better:
            caveats.append(
                f"The model does not beat the naive baseline on {primary_metric} — "
                "the features may carry little signal for this target."
            )

    # Class imbalance
    if task_type == "binary_classification" and "confusion_matrix" in holdout:
        row_totals = [sum(r) for r in holdout["confusion_matrix"]["matrix"]]
        if sum(row_totals) > 0:
            minority_frac = min(row_totals) / sum(row_totals)
            if minority_frac < 0.15:
                caveats.append(
                    f"Classes are imbalanced (minority class is {minority_frac:.0%} of the test set). "
                    "Accuracy is misleading here; focus on PR-AUC / F1."
                )

    if n_test < 200:
        caveats.append(
            f"The held-out test set is small ({n_test} rows), so reported metrics have wide error bars."
        )

    # High-missingness features that made it into the model
    used = set(plan.get("features_used", [])) or {c["name"] for c in profile["columns"]}
    high_missing = [
        c["name"] for c in profile["columns"] if c["pct_missing"] > 30 and c["name"] in used
    ]
    if high_missing:
        caveats.append(
            f"Features with >30% missing values were imputed: {', '.join(high_missing)}. "
            "Check whether missingness itself is meaningful in your domain."
        )

    return caveats
