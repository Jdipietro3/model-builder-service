"""Batch scoring: run new data through a trained run's fitted pipeline."""

import io
from pathlib import Path
from typing import Any

import joblib
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


def score_dataframe(pipeline, meta: dict, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Append prediction (+ probability) columns to df. Returns (scored_df, summary).

    All training-time feature columns must be present — a silently-imputed
    all-NaN column would produce garbage predictions. Extra columns pass through.
    """
    feature_cols = meta["feature_columns"]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Uploaded CSV is missing feature column(s) the model needs: {', '.join(missing)}"
        )
    if len(df) == 0:
        raise ValueError("Uploaded CSV has no rows")

    X = df[feature_cols]
    preds = pipeline.predict(X)
    is_classification = meta["task_type"] != "regression"
    label_classes = meta.get("label_classes")

    scored = df.copy()
    if is_classification and label_classes:
        scored["prediction"] = [label_classes[int(p)] for p in preds]
    else:
        scored["prediction"] = preds.round(2)

    summary: dict[str, Any] = {"n_rows": int(len(scored)), "task_type": meta["task_type"]}

    if is_classification:
        if hasattr(pipeline, "predict_proba") and label_classes:
            proba = pipeline.predict_proba(X)
            for j, cls in enumerate(label_classes):
                scored[f"prob_{cls}"] = proba[:, j].round(4)
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
