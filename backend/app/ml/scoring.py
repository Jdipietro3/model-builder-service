"""Batch scoring: run new data through a trained run's fitted pipeline."""

import io
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


def load_model(run) -> tuple[Any, dict]:
    """Load the fitted pipeline + metadata from the run's artifact bundle."""
    path = Path(run.artifact_path).parent / "bundle" / "model.joblib"
    if not path.exists():
        raise FileNotFoundError(f"Model bundle not found for run {run.id}")
    bundle = joblib.load(path)
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


def _score_ensemble(artifact: dict, meta: dict, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Score through an ensemble bundle's dict artifact: per-base predict/proba,
    then combine via the stored blend weights or stacking meta-model (mirrors
    ``ml.pipeline.ensemble._EnsemblePredictor`` / the generated standalone serve.py)."""
    is_classification = meta["task_type"] != "regression"
    label_classes = meta.get("label_classes")

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
