"""Ensemble task runner: auto-builds a weighted blend or a stacked meta-model
from a tournament's completed supervised candidates.

``ensemble.*`` methodologies are never proposed directly by the LLM (guarded in
``orchestrator/tools.py``); this runner only ever executes via the tournament
promotion path in ``jobs.py``, which enriches the plan in-memory with each base
run's fitted pipeline + stored results (``plan["base_runs"]``) before calling
``run_plan`` — see ``jobs._execute``.

The whole approach hinges on split determinism (see ``supervised.py``): every
candidate's holdout split depends only on row count + stratify label values, not
on feature columns, so re-running the identical ``dropna`` + ``train_test_split``
here reproduces the exact holdout every base candidate used — the ensemble's
holdout metrics are directly comparable to each base's.
"""

import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict, train_test_split
from sklearn.preprocessing import LabelEncoder

from scipy.optimize import nnls  # transitive dep of scikit-learn; verified importable

from .. import evaluation
from ..registry.loader import get_spec
from .base import LoadedData, ProgressCb, RunOutcome, register_runner


def _load_bundle(artifact_path: str) -> dict:
    bundle_path = Path(artifact_path).parent / "bundle" / "model.joblib"
    if not bundle_path.exists():
        raise ValueError(f"Base model bundle not found at {bundle_path}")
    return joblib.load(bundle_path)


class _EnsemblePredictor:
    """Wraps N base pipelines + blend weights or a stacking meta-model behind
    ``.predict()``/``.predict_proba()`` over a full feature DataFrame, so
    ``evaluation.evaluate_holdout`` can treat the ensemble exactly like any
    other fitted pipeline (it only needs those two methods). Training-time only
    — never persisted; the artifact bundle stores the raw dict form instead
    (see ``EnsembleRunner.run``) so scoring/serve reconstruct combination logic
    without importing this class.
    """

    def __init__(
        self,
        ensemble_type: str,
        bases: list[dict[str, Any]],
        is_classification: bool,
        weights: np.ndarray | None = None,
        meta_model: Any | None = None,
    ):
        self.ensemble_type = ensemble_type
        self.bases = bases  # [{"pipeline", "feature_columns"}, ...]
        self.is_classification = is_classification
        self.weights = weights
        self.meta_model = meta_model

    def _base_outputs(self, df) -> list[np.ndarray]:
        outs = []
        for base in self.bases:
            X = df[base["feature_columns"]]
            if self.is_classification:
                outs.append(base["pipeline"].predict_proba(X))
            else:
                outs.append(np.asarray(base["pipeline"].predict(X), dtype=float))
        return outs

    def predict_proba(self, df) -> np.ndarray:
        base_outs = self._base_outputs(df)
        if self.ensemble_type == "blend":
            combined = np.zeros_like(base_outs[0], dtype=float)
            for w, p in zip(self.weights, base_outs):
                combined += w * p
            row_sums = combined.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1.0  # defensive: never divide by zero
            return combined / row_sums
        meta_X = np.hstack(base_outs)
        return self.meta_model.predict_proba(meta_X)

    def predict(self, df) -> np.ndarray:
        if self.is_classification:
            return np.argmax(self.predict_proba(df), axis=1)
        base_outs = self._base_outputs(df)
        if self.ensemble_type == "blend":
            combined = np.zeros_like(base_outs[0], dtype=float)
            for w, p in zip(self.weights, base_outs):
                combined += w * p
            return combined
        meta_X = np.column_stack(base_outs)
        return self.meta_model.predict(meta_X)


def _combine_oof(
    ensemble_type: str,
    oof_preds: list[np.ndarray],
    weights: np.ndarray | None,
    meta_model: Any | None,
    is_classification: bool,
) -> np.ndarray:
    """Same combination logic as ``_EnsemblePredictor`` but over already-computed
    out-of-fold arrays (used only to summarize a CV metric for the results card)."""
    if ensemble_type == "blend":
        combined = np.zeros_like(oof_preds[0], dtype=float)
        for w, p in zip(weights, oof_preds):
            combined += w * p
        if is_classification:
            row_sums = combined.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1.0
            combined = combined / row_sums
        return combined
    if is_classification:
        meta_X = np.hstack(oof_preds)
        return meta_model.predict_proba(meta_X)
    meta_X = np.column_stack(oof_preds)
    return meta_model.predict(meta_X)


def _summarize_lr_coefficients(model: LogisticRegression, bundles: list[dict]) -> dict | None:
    """Rough per-base "influence" summary for display only — never used for
    inference. Sums absolute meta-model coefficient magnitude across each base's
    coefficient block (the OOF proba columns were hstacked in base order, so each
    base occupies an equal-width column chunk). Returns None if the coefficient
    shape doesn't divide evenly across bases (e.g. an unexpected sklearn layout) —
    the caller drops the field rather than show something misleading."""
    try:
        coef = np.atleast_2d(model.coef_)  # (n_out, n_bases * n_classes)
        n_bases = len(bundles)
        if n_bases == 0 or coef.shape[1] % n_bases != 0:
            return None
        block = coef.shape[1] // n_bases
        return {
            b["run_id"]: round(float(np.abs(coef[:, i * block : (i + 1) * block]).sum()), 4)
            for i, b in enumerate(bundles)
        }
    except Exception:
        return None


class EnsembleRunner:
    task_family = "ensemble"
    compatible_shapes = ("tabular",)

    def run(self, data: LoadedData, spec: dict, plan: dict, progress: ProgressCb) -> RunOutcome:
        t0 = time.time()
        task_type = plan["task_type"]
        is_classification = task_type != "regression"
        ensemble_type = plan["methodology_id"].split(".", 1)[1]  # "blend" | "stacking"

        base_runs = plan.get("base_runs") or []
        if len(base_runs) < 2:
            raise ValueError(
                f"Ensemble requires at least 2 completed base runs, got {len(base_runs)}"
            )

        df = data.payload
        profile = data.profile
        target = plan["target_column"]
        if target not in df.columns:
            raise ValueError(f"Target column '{target}' not found in dataset")

        progress("preparing", 10, "Loading base model bundles")
        bundles: list[dict[str, Any]] = []
        for base in base_runs:
            if not base.get("artifact_path"):
                raise ValueError(f"Base run {base['run_id']} has no artifact bundle")
            bundle = _load_bundle(base["artifact_path"])
            bundles.append(
                {
                    **base,
                    "pipeline": bundle["pipeline"],
                    "feature_columns": bundle["meta"]["feature_columns"],
                    "base_meta": bundle["meta"],
                }
            )

        rows = df.dropna(subset=[target])

        label_classes: list[str] | None = None
        if is_classification:
            le = LabelEncoder()
            y = le.fit_transform(rows[target].astype(str))
            label_classes = [str(c) for c in le.classes_]
            for b in bundles:
                base_classes = b["base_meta"].get("label_classes")
                if base_classes != label_classes:
                    raise ValueError(
                        f"Label classes for base run {b['run_id']} ({base_classes}) don't match "
                        f"the ensemble's ({label_classes}); the base model may have been trained "
                        "on a different dataset or target."
                    )
        else:
            y = rows[target].astype(float).to_numpy()

        rows_train, rows_test, y_train, y_test = train_test_split(
            rows, y, test_size=0.2, random_state=42, stratify=y if is_classification else None
        )

        n_splits = plan.get("validation", {}).get("n_splits", 5)
        cv = (
            StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
            if is_classification
            else KFold(n_splits=n_splits, shuffle=True, random_state=42)
        )

        progress(
            "cross_validation",
            30,
            f"Computing out-of-fold predictions for {len(bundles)} base model(s)",
        )
        oof_preds: list[np.ndarray] = []
        for b in bundles:
            X_train_b = rows_train[b["feature_columns"]]
            oof = cross_val_predict(
                clone(b["pipeline"]),
                X_train_b,
                y_train,
                cv=cv,
                method="predict_proba" if is_classification else "predict",
                n_jobs=-1,
            )
            oof_preds.append(np.asarray(oof, dtype=float))

        n_bases = len(bundles)
        weights: np.ndarray | None = None
        meta_model: Any | None = None
        meta_model_summary: dict | None = None

        if ensemble_type == "blend":
            progress("training", 55, "Fitting blend weights (NNLS)")
            if is_classification:
                n_classes = len(label_classes)
                y_onehot = np.zeros((len(y_train), n_classes))
                y_onehot[np.arange(len(y_train)), y_train] = 1
                design = np.column_stack([oof.reshape(-1) for oof in oof_preds])
                target_vec = y_onehot.reshape(-1)
            else:
                design = np.column_stack(oof_preds)
                target_vec = y_train
            raw_weights, _ = nnls(design, target_vec)
            total = float(raw_weights.sum())
            weights = raw_weights / total if total > 1e-9 else np.full(n_bases, 1.0 / n_bases)
        else:  # stacking
            progress("training", 55, "Fitting stacking meta-model")
            if is_classification:
                meta_X = np.hstack(oof_preds)
                meta_model = LogisticRegression(max_iter=2000)
                meta_model.fit(meta_X, y_train)
                meta_model_summary = {
                    "class": "LogisticRegression",
                    "coefficients": _summarize_lr_coefficients(meta_model, bundles),
                }
            else:
                meta_X = np.column_stack(oof_preds)
                meta_model = Ridge(alpha=1.0)
                meta_model.fit(meta_X, y_train)
                meta_model_summary = {
                    "class": "Ridge",
                    "coefficients": {
                        b["run_id"]: round(float(c), 4)
                        for b, c in zip(bundles, np.atleast_1d(meta_model.coef_))
                    },
                }

        predictor = _EnsemblePredictor(
            ensemble_type=ensemble_type,
            bases=[{"pipeline": b["pipeline"], "feature_columns": b["feature_columns"]} for b in bundles],
            is_classification=is_classification,
            weights=weights,
            meta_model=meta_model,
        )

        progress("evaluating", 75, "Evaluating on held-out test data")
        metric_names = spec["metrics"][task_type]["supported"]
        holdout = evaluation.evaluate_holdout(
            predictor, rows_test, y_test, y_train, task_type, metric_names, label_classes
        )
        primary_metric = plan["primary_metric"]
        caveats = evaluation.build_caveats(
            task_type, primary_metric, holdout, [], profile, plan, len(y_test)
        )
        caveats.append(
            "This is an auto-built ensemble, not an independently-trained model: it combines "
            "the tournament's base candidates. See results.ensemble for the base models and how "
            "they're combined."
        )

        progress("evaluating", 90, "Summarizing cross-validated performance")
        oof_combined = _combine_oof(ensemble_type, oof_preds, weights, meta_model, is_classification)
        if is_classification:
            oof_pred_labels = np.argmax(oof_combined, axis=1)
            cv_metrics = evaluation.compute_metrics(metric_names, y_train, oof_pred_labels, oof_combined)
        else:
            cv_metrics = evaluation.compute_metrics(metric_names, y_train, oof_combined)
        cv_summary = {
            "metric": primary_metric,
            "mean": cv_metrics.get(primary_metric),
            "std": 0.0,
            "n_splits": n_splits,
            "n_candidates": n_bases,
        }

        base_summaries = []
        for i, b in enumerate(bundles):
            base_results = b.get("results") or {}
            summary = {
                "run_id": b["run_id"],
                "methodology_id": b["methodology_id"],
                "display_name": base_results.get("methodology", {}).get(
                    "display_name", b["methodology_id"]
                ),
                "holdout_metrics": (base_results.get("holdout") or {}).get("metrics", {}),
            }
            if ensemble_type == "blend":
                summary["weight"] = round(float(weights[i]), 4)
            base_summaries.append(summary)

        ensemble_block: dict[str, Any] = {"type": ensemble_type, "base": base_summaries}
        if ensemble_type == "blend":
            ensemble_block["weights"] = {
                b["run_id"]: round(float(w), 4) for b, w in zip(bundles, weights)
            }
        else:
            ensemble_block["meta_model"] = meta_model_summary

        union_feature_columns = sorted({c for b in bundles for c in b["feature_columns"]})
        base_feature_columns = {b["run_id"]: b["feature_columns"] for b in bundles}
        extra_requirement_modules = sorted(
            {get_spec(b["methodology_id"])["model"]["class"].split(".")[0] for b in bundles}
        )

        results = {
            "methodology": {"id": plan["methodology_id"], "display_name": spec["display_name"]},
            "task_type": task_type,
            "data_shape": "tabular",
            "task_family": "ensemble",
            "target_column": target,
            "primary_metric": primary_metric,
            "best_params": {},
            "cv": cv_summary,
            "holdout": holdout,
            "features_used": union_feature_columns,
            "features_dropped": [],
            "caveats": caveats,
            "n_train": int(len(rows_train)),
            "n_test": int(len(rows_test)),
            "training_seconds": round(time.time() - t0, 1),
            "ensemble": ensemble_block,
        }

        artifact: dict[str, Any] = {
            "ensemble_type": ensemble_type,
            "base": {
                b["run_id"]: {"pipeline": b["pipeline"], "feature_columns": b["feature_columns"]}
                for b in bundles
            },
        }
        if ensemble_type == "blend":
            artifact["weights"] = {b["run_id"]: float(w) for b, w in zip(bundles, weights)}
        else:
            artifact["meta_model"] = meta_model

        meta = {
            "spec": spec,
            "feature_columns": union_feature_columns,
            "label_classes": label_classes,
            "best_params": {},
            "data_shape": "tabular",
            "task_family": "ensemble",
            "target_column": target,
            "task_type": task_type,
            "methodology_id": plan["methodology_id"],
            "ensemble_type": ensemble_type,
            "base_run_ids": [b["run_id"] for b in bundles],
            "base_feature_columns": base_feature_columns,
            "extra_requirement_modules": extra_requirement_modules,
        }
        return RunOutcome(results=results, artifact=artifact, meta=meta)


register_runner(EnsembleRunner())
