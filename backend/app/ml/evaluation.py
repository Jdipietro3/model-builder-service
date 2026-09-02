"""Holdout evaluation: metrics vs a naive baseline, importances, and
plain-language caveats. This is the substance behind the ReportCard."""

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

# Direction of improvement per metric ("higher" unless noted).
LOWER_IS_BETTER = {"mae", "rmse"}

# Honest post-training diagnostics (item 3): segment metrics, calibration, and a
# single-feature leakage sanity check. All three are wrapped by their callers
# (SupervisedRunner.run) so a diagnostics failure degrades to None/[] and never
# fails the run.
MAX_SEGMENT_COLUMNS = 2
MIN_SEGMENT_CARDINALITY = 2
MAX_SEGMENT_CARDINALITY = 10
MIN_SEGMENT_SIZE = 5  # guard against tiny, noisy segments
CALIBRATION_BINS = 10
TOP_LEAKAGE_FEATURES = 3


def _positive_class_proba(y_proba: np.ndarray | None) -> np.ndarray:
    """The positive-class column of a binary `predict_proba` output.

    Validated in one place so a malformed y_proba fails the way every other
    "this metric doesn't apply here" case does — as a ValueError caught by
    compute_metrics, dropping the one metric — rather than as an IndexError
    that escapes and takes the whole metrics dict down with it. No estimator
    in the current registry can produce a bad shape here, but hand-rolled
    predict_proba implementations (the Phase 6 neural-net estimators) can.
    """
    if y_proba is None:
        raise ValueError("metric requires y_proba, none was supplied")
    arr = np.asarray(y_proba)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError(
            "metric requires a two-column (n_samples, n_classes) y_proba, "
            f"got shape {arr.shape}"
        )
    return arr[:, 1]


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
                out[name] = roc_auc_score(y_true, _positive_class_proba(y_proba))
            elif name == "pr_auc":
                out[name] = average_precision_score(y_true, _positive_class_proba(y_proba))
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
            continue  # metric undefined for this data (e.g. roc_auc with no y_proba)
    # sklearn >= 1.3 prefers returning nan over raising for some undefined
    # cases (roc_auc_score on a single-class fold, which segment_metrics hits
    # routinely). nan survives round(float(...)) and json.dumps emits a bare
    # NaN, which is invalid JSON and breaks the frontend's parse — so treat a
    # non-finite score as "undefined", same as the raising cases above.
    return {k: round(float(v), 4) for k, v in out.items() if np.isfinite(v)}


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


def _seg_labels(s: pd.Series) -> pd.Series:
    """Stringify segment values while preserving real missingness as NaN (plain
    astype(str) would turn NaN into the literal string 'nan')."""
    return s.map(lambda v: str(v) if pd.notna(v) else np.nan)


def _pick_segment_columns(
    X_test: pd.DataFrame, importances: list[dict[str, Any]]
) -> list[tuple[str, pd.Series]]:
    """Up to MAX_SEGMENT_COLUMNS (column_name, stringified_segment_series) pairs:
    categorical/boolean columns used as-is, numeric columns quantile-binned; both
    kept to a 2-10 segment cardinality. Higher-importance columns are preferred."""
    ranked = [imp["feature"] for imp in importances if imp["feature"] in X_test.columns]
    remaining = [c for c in X_test.columns if c not in ranked]
    candidates = ranked + remaining

    picked: list[tuple[str, pd.Series]] = []
    for col in candidates:
        if len(picked) >= MAX_SEGMENT_COLUMNS:
            break
        s = X_test[col]
        try:
            if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
                nunique = s.nunique(dropna=True)
                if nunique < MIN_SEGMENT_CARDINALITY:
                    continue
                if nunique > MAX_SEGMENT_CARDINALITY:
                    binned = pd.qcut(s, q=4, duplicates="drop")
                    if binned.nunique(dropna=True) < MIN_SEGMENT_CARDINALITY:
                        continue
                    picked.append((col, _seg_labels(binned)))
                else:
                    picked.append((col, _seg_labels(s)))
            else:
                nunique = s.nunique(dropna=True)
                if MIN_SEGMENT_CARDINALITY <= nunique <= MAX_SEGMENT_CARDINALITY:
                    picked.append((col, _seg_labels(s)))
        except Exception:
            continue
    return picked


def segment_metrics(
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray | None,
    task_type: str,
    primary_metric: str,
    importances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recompute the primary metric per-segment for up to MAX_SEGMENT_COLUMNS
    segmenting columns, so a model that looks good overall but collapses on one
    slice of the data doesn't go unnoticed. Returns the `segments` contract."""
    X_reset = X_test.reset_index(drop=True)
    lower_is_better = primary_metric in LOWER_IS_BETTER
    overall = compute_metrics([primary_metric], y_test, y_pred, y_proba).get(primary_metric)
    if overall is None:
        return []

    out: list[dict[str, Any]] = []
    for col, seg_series in _pick_segment_columns(X_reset, importances):
        rows: list[dict[str, Any]] = []
        for value in sorted(seg_series.dropna().unique()):
            idx = np.where(seg_series.to_numpy() == value)[0]
            if len(idx) < MIN_SEGMENT_SIZE:
                continue
            seg_y_true = y_test[idx]
            seg_y_pred = y_pred[idx]
            seg_y_proba = y_proba[idx] if y_proba is not None else None
            seg_metrics = compute_metrics([primary_metric], seg_y_true, seg_y_pred, seg_y_proba)
            score = seg_metrics.get(primary_metric)
            if score is None:
                continue
            rows.append({"value": str(value), "n": int(len(idx)), "metrics": seg_metrics, "score": score})

        if len(rows) < 2:
            continue

        worst = max(rows, key=lambda r: r["score"]) if lower_is_better else min(rows, key=lambda r: r["score"])
        out.append(
            {
                "column": col,
                "metric": primary_metric,
                "overall": overall,
                "segments": [{"value": r["value"], "n": r["n"], "metrics": r["metrics"]} for r in rows],
                "worst": {"value": worst["value"], "n": worst["n"], "score": worst["score"]},
            }
        )
    return out


def calibration_bins(y_test: np.ndarray, y_proba: np.ndarray | None) -> dict[str, Any] | None:
    """Reliability curve + Brier score for binary classifiers with predict_proba.
    Returns None for multiclass, regression, or a model with no predict_proba."""
    if y_proba is None or y_proba.ndim != 2 or y_proba.shape[1] != 2:
        return None
    if len(np.unique(y_test)) != 2:
        return None

    p = y_proba[:, 1]
    brier = brier_score_loss(y_test, p)
    edges = np.linspace(0.0, 1.0, CALIBRATION_BINS + 1)
    bins: list[dict[str, Any]] = []
    for i in range(CALIBRATION_BINS):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p <= hi) if i == CALIBRATION_BINS - 1 else (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        bins.append(
            {
                "p_pred": round(float(p[mask].mean()), 4),
                "p_true": round(float(np.asarray(y_test)[mask].mean()), 4),
                "n": n,
            }
        )
    return {"metric": "brier", "brier": round(float(brier), 4), "bins": bins}


def _single_feature_pipeline(feat: str, dtype, task_type: str) -> Pipeline:
    """Minimal ColumnTransformer mirroring the runner's encoding (numeric
    impute-only, categorical impute + one-hot) around a shallow decision tree,
    selecting the single feature `feat` by name."""
    is_numeric = pd.api.types.is_numeric_dtype(dtype) and not pd.api.types.is_bool_dtype(dtype)
    if is_numeric:
        pre = ColumnTransformer([("num", SimpleImputer(strategy="median"), [feat])])
    else:
        pre = ColumnTransformer(
            [
                (
                    "cat",
                    Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    [feat],
                )
            ]
        )
    model = (
        DecisionTreeClassifier(max_depth=3, random_state=42)
        if task_type != "regression"
        else DecisionTreeRegressor(max_depth=3, random_state=42)
    )
    return Pipeline([("preprocess", pre), ("model", model)])


def single_feature_leakage(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    task_type: str,
    primary_metric: str,
    importances: list[dict[str, Any]],
    full_score: float | None,
) -> list[dict[str, Any]]:
    """For the top TOP_LEAKAGE_FEATURES importance features, fit a cheap
    single-column model and compare its holdout score to the full model's — a
    feature that alone nearly matches full-model performance is a strong leakage
    signal. Returns [{feature, solo_score, full_score, ratio}]."""
    if full_score is None:
        return []
    is_classification = task_type != "regression"
    out: list[dict[str, Any]] = []
    for imp in importances[:TOP_LEAKAGE_FEATURES]:
        feat = imp["feature"]
        if feat not in X_train.columns or feat not in X_test.columns:
            continue
        try:
            pipe = _single_feature_pipeline(feat, X_train[feat].dtype, task_type)
            pipe.fit(X_train[[feat]], y_train)

            y_pred = pipe.predict(X_test[[feat]])
            y_proba = None
            if is_classification and hasattr(pipe, "predict_proba"):
                y_proba = pipe.predict_proba(X_test[[feat]])
            solo_metrics = compute_metrics([primary_metric], y_test, y_pred, y_proba)
            solo_score = solo_metrics.get(primary_metric)
            if solo_score is None:
                continue

            if primary_metric in LOWER_IS_BETTER:
                if solo_score == 0:
                    ratio = 1.0 if full_score == 0 else 0.0
                else:
                    ratio = full_score / solo_score
            else:
                ratio = 0.0 if full_score == 0 else solo_score / full_score

            out.append(
                {
                    "feature": feat,
                    "solo_score": round(float(solo_score), 4),
                    "full_score": round(float(full_score), 4),
                    "ratio": round(float(max(0.0, ratio)), 4),
                }
            )
        except Exception:
            continue
    return out


def build_caveats(
    task_type: str,
    primary_metric: str,
    holdout: dict,
    importances: list[dict],
    profile: dict,
    plan: dict,
    n_test: int,
    segments: list[dict] | None = None,
    calibration: dict | None = None,
    single_feature: list[dict] | None = None,
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

    # --- Honest post-training diagnostics (item 3) — additions only, the four
    # categories above are unchanged for golden non-regression. ---

    # Weakest data segment: the biggest overall-vs-worst-segment gap across every
    # segmenting column, if the model underperforms notably on any slice.
    if segments:
        lower_is_better = primary_metric in LOWER_IS_BETTER
        weakest: tuple[float, dict, dict] | None = None
        for seg in segments:
            worst = seg.get("worst") or {}
            score = worst.get("score")
            overall = seg.get("overall")
            if score is None or overall is None:
                continue
            gap = (score - overall) if lower_is_better else (overall - score)
            if gap > 0 and (weakest is None or gap > weakest[0]):
                weakest = (gap, seg, worst)
        if weakest is not None:
            _, seg, worst = weakest
            caveats.append(
                f"The model underperforms on {seg['column']}='{worst['value']}' "
                f"({seg['metric']} {worst['score']} vs {seg['overall']} overall, n={worst['n']}). "
                "Check whether this segment is well represented in training data."
            )

    # Single-feature leakage: one feature alone nearly matches full-model
    # performance.
    if single_feature:
        leaky = [sf for sf in single_feature if (sf.get("ratio") or 0) >= 0.95]
        if leaky:
            top = max(leaky, key=lambda sf: sf["ratio"])
            caveats.append(
                f"'{top['feature']}' alone reaches {top['ratio']:.0%} of full-model performance "
                f"(solo {top['solo_score']} vs full {top['full_score']} on {primary_metric}) — "
                "likely leakage; verify this feature is genuinely available at prediction time."
            )

    # Poor probability calibration (binary classifiers with predict_proba only).
    if calibration and calibration.get("brier") is not None and calibration["brier"] > 0.25:
        caveats.append(
            f"Predicted probabilities are poorly calibrated (Brier score {calibration['brier']}, "
            "vs ~0.25 for an uninformative 50/50 guess). Treat probability outputs as a ranking "
            "signal, not a literal likelihood, unless recalibrated."
        )

    return caveats
