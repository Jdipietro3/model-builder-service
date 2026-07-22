"""Batch scoring: run new data through a trained run's fitted pipeline."""

import io
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


def read_csv_bytes(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(content))
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(content), encoding="latin-1")


@lru_cache(maxsize=8)
def _load_bundle(path_str: str, mtime_ns: int) -> dict:
    return joblib.load(path_str)


def load_model(run) -> tuple[Any, dict]:
    """Load the fitted pipeline + metadata from the run's artifact bundle.

    Cached in-process keyed on (path, mtime_ns): a rebuilt bundle gets a fresh
    cache entry (new mtime) and the stale one is LRU-evicted, so invalidation
    is automatic. Callers must treat the returned pipeline/meta as READ-ONLY —
    the same objects are shared across concurrent requests.
    """
    path = Path(run.artifact_path).parent / "bundle" / "model.joblib"
    if not path.exists():
        raise FileNotFoundError(f"Model bundle not found for run {run.id}")
    mtime_ns = path.stat().st_mtime_ns
    bundle = _load_bundle(str(path), mtime_ns)
    return bundle["pipeline"], bundle["meta"]


def _finalize_scored(
    df: pd.DataFrame,
    preds: np.ndarray,
    proba: np.ndarray | None,
    meta: dict,
    is_classification: bool,
    label_classes: list[str] | None,
) -> tuple[pd.DataFrame, dict]:
    """Append prediction (+ probability) columns and build the summary/preview
    block. Shared tail for both the single-pipeline and ensemble scoring paths —
    everything upstream of this (getting ``preds``/``proba``) is family-specific."""
    preds = np.asarray(preds)
    scored = df.copy()
    if is_classification and label_classes:
        scored["prediction"] = [label_classes[int(p)] for p in preds]
    else:
        scored["prediction"] = preds.round(2)

    summary: dict[str, Any] = {"n_rows": int(len(scored)), "task_type": meta["task_type"]}

    if is_classification:
        if proba is not None and label_classes:
            for j, cls in enumerate(label_classes):
                scored[f"prob_{cls}"] = np.asarray(proba)[:, j].round(4)
        counts = scored["prediction"].value_counts()
        summary["class_counts"] = {str(k): int(v) for k, v in counts.items()}
    else:
        s = scored["prediction"].astype(float)
        summary["stats"] = {
            "mean": round(float(s.mean()), 4),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
        }

    preview = scored.head(10)
    summary["preview"] = {
        "columns": [str(c) for c in preview.columns],
        "rows": [
            ["" if pd.isna(v) else str(v) for v in row]
            for row in preview.itertuples(index=False)
        ],
    }
    return scored, summary


def _ensemble_combined(
    artifact: dict, meta: dict, df: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray | None]:
    """Validate feature columns, run each base pipeline, and combine via the
    stored blend weights or stacking meta-model (mirrors
    ``ml.pipeline.ensemble._EnsemblePredictor`` / the generated standalone
    serve.py). Returns (preds, proba) — proba is None for regression."""
    is_classification = meta["task_type"] != "regression"

    all_feature_cols = sorted(
        {c for base in artifact["base"].values() for c in base["feature_columns"]}
    )
    missing = [c for c in all_feature_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Uploaded CSV is missing feature column(s) the ensemble needs: {', '.join(missing)}"
        )

    run_ids = list(artifact["base"].keys())
    base_outs = []
    for run_id in run_ids:
        base = artifact["base"][run_id]
        X = df[base["feature_columns"]]
        if is_classification:
            base_outs.append(base["pipeline"].predict_proba(X))
        else:
            base_outs.append(np.asarray(base["pipeline"].predict(X), dtype=float))

    if artifact["ensemble_type"] == "blend":
        weights = [artifact["weights"][rid] for rid in run_ids]
        combined = np.zeros_like(base_outs[0], dtype=float)
        for w, p in zip(weights, base_outs):
            combined += w * p
        if is_classification:
            row_sums = combined.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1.0
            combined = combined / row_sums
    else:
        if is_classification:
            combined = artifact["meta_model"].predict_proba(np.hstack(base_outs))
        else:
            combined = artifact["meta_model"].predict(np.column_stack(base_outs))

    if is_classification:
        preds, proba = np.argmax(combined, axis=1), combined
    else:
        preds, proba = combined, None

    return preds, proba


def _score_ensemble(artifact: dict, meta: dict, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Score through an ensemble bundle's dict artifact via ``_ensemble_combined``,
    then append prediction columns and build the summary/preview block."""
    is_classification = meta["task_type"] != "regression"
    label_classes = meta.get("label_classes")

    preds, proba = _ensemble_combined(artifact, meta, df)

    return _finalize_scored(df, preds, proba, meta, is_classification, label_classes)


def score_dataframe(pipeline, meta: dict, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Append prediction (+ probability) columns to df. Returns (scored_df, summary).

    All training-time feature columns must be present — a silently-imputed
    all-NaN column would produce garbage predictions. Extra columns pass through.

    ``pipeline`` is family-dependent: a fitted sklearn Pipeline for supervised runs,
    or the ensemble dict artifact (``{"ensemble_type", "base", "weights"|"meta_model"}``)
    for ensemble runs — ``load_model`` is family-agnostic and just unpacks whatever
    ``bundle["pipeline"]`` is, so the branch happens here.
    """
    task_family = meta.get("task_family", "supervised")
    if task_family == "forecasting":
        raise ValueError(
            "Batch scoring is not applicable to forecasting runs — the training results "
            "include the future forecast."
        )
    if len(df) == 0:
        raise ValueError("Uploaded CSV has no rows")

    if task_family == "ensemble":
        return _score_ensemble(pipeline, meta, df)

    feature_cols = meta["feature_columns"]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Uploaded CSV is missing feature column(s) the model needs: {', '.join(missing)}"
        )

    X = df[feature_cols]
    preds = pipeline.predict(X)
    is_classification = meta["task_type"] != "regression"
    label_classes = meta.get("label_classes")
    proba = None
    if is_classification and hasattr(pipeline, "predict_proba"):
        proba = pipeline.predict_proba(X)

    return _finalize_scored(df, preds, proba, meta, is_classification, label_classes)


def predict_records(pipeline, meta: dict, records: list[dict]) -> dict:
    """Score a small batch of JSON records for live in-service deployment.

    Reuses the same missing-feature-column validation as ``score_dataframe``.
    Output shape matches the standalone ``serve.py`` stubs generated by
    ``ml/artifacts.py`` (``_generate_serve_py`` / ``_generate_serve_py_ensemble``):
    classification maps ``label_classes`` and rounds probabilities to 4dp;
    regression returns plain floats with no ``probabilities`` key.
    """
    task_family = meta.get("task_family", "supervised")
    if task_family == "forecasting":
        raise ValueError(
            "Live prediction is not applicable to forecasting runs — the training results "
            "include the future forecast."
        )

    df = pd.DataFrame(records)
    is_classification = meta["task_type"] != "regression"
    label_classes = meta.get("label_classes")

    if task_family == "ensemble":
        # _ensemble_combined validates that all base feature columns are present
        # (same missing-column check ``_score_ensemble`` uses for batch scoring).
        preds, proba = _ensemble_combined(pipeline, meta, df)
    else:
        feature_cols = meta["feature_columns"]
        missing = [c for c in feature_cols if c not in df.columns]
        if missing:
            raise ValueError(
                f"Uploaded CSV is missing feature column(s) the model needs: {', '.join(missing)}"
            )
        X = df[feature_cols]
        preds = pipeline.predict(X)
        proba = None
        if is_classification and hasattr(pipeline, "predict_proba"):
            proba = pipeline.predict_proba(X)

    preds = np.asarray(preds)
    if is_classification:
        out: dict[str, Any] = {
            "predictions": [
                label_classes[int(p)] if label_classes else int(p) for p in preds
            ]
        }
        if proba is not None:
            out["probabilities"] = [
                {
                    label_classes[j] if label_classes else str(j): round(float(p), 4)
                    for j, p in enumerate(row)
                }
                for row in np.asarray(proba)
            ]
    else:
        out = {"predictions": [float(p) for p in preds]}

    return out


def served_summary(preds: list, proba: list | None, meta: dict) -> dict:
    """Compact class-counts/stats summary of a served prediction batch, used for
    the InferenceLog row. Mirrors the ``class_counts``/``stats`` shape
    ``_finalize_scored`` builds for batch scoring so served vs. training
    distributions can be compared directly."""
    is_classification = meta["task_type"] != "regression"
    if is_classification:
        counts: dict[str, int] = {}
        for p in preds:
            key = str(p)
            counts[key] = counts.get(key, 0) + 1
        return {"class_counts": counts}

    values = [float(p) for p in preds]
    if not values:
        return {"stats": {"mean": 0.0, "min": 0.0, "max": 0.0}}
    return {
        "stats": {
            "mean": round(sum(values) / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }
    }
