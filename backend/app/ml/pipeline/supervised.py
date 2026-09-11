"""Supervised task runner: cross-validated grid search + holdout evaluation
over a tabular payload.

Preprocessing/feature engineering is delegated to ``ml/recipe.py`` (Phase 1):
a plan with no ``preprocessing`` resolves to ``recipe.legacy_recipe``, which
reproduces the pre-Phase-1 hard-coded pipeline exactly (same feature
selection, same preprocessing, same progress beats, same rounding) — this is
the golden path pinned by ``tests/test_golden.py``. A plan with an explicit
``preprocessing`` list uses those steps instead.
"""

import copy
import time
import warnings

# Benign sklearn/LightGBM interplay warning that floods logs during
# grid search and permutation importance.
warnings.filterwarnings("ignore", message="X does not have valid feature names")

from sklearn.model_selection import KFold, StratifiedKFold, train_test_split
from sklearn.preprocessing import LabelEncoder

from .. import evaluation
from .. import tuning as tuning_mod
from ..recipe import METRIC_SCORING, compile_recipe, legacy_recipe, preprocessing_applied, resolve_recipe
from .base import LoadedData, ProgressCb, RunOutcome, register_runner

__all__ = ["METRIC_SCORING", "SupervisedRunner"]


class SupervisedRunner:
    task_family = "supervised"
    compatible_shapes = ("tabular",)

    def run(self, data: LoadedData, spec: dict, plan: dict, progress: ProgressCb) -> RunOutcome:
        """Execute the full train/evaluate sequence over a profiled DataFrame."""
        t0 = time.time()
        task_type = plan["task_type"]
        is_classification = task_type != "regression"

        df = data.payload
        profile = data.profile
        if plan["target_column"] not in df.columns:
            raise ValueError(f"Target column '{plan['target_column']}' not found in dataset")

        # Pinned hyperparameters are applied to the model's constructor params
        # BEFORE the grid, and removed from the grid so the search doesn't
        # re-explore them. Done via an effective spec copy so compile_recipe's
        # contract (model = resolve_model_class(spec.model.class)(**spec.model.params))
        # stays literally true.
        pinned = plan.get("hyperparameters") or {}
        effective_spec = copy.deepcopy(spec)
        if pinned:
            effective_spec["model"]["params"] = {**effective_spec["model"].get("params", {}), **pinned}
            effective_spec["model"]["grid"] = {
                k: v for k, v in effective_spec["model"].get("grid", {}).items() if k not in pinned
            }
            if "search_space" in effective_spec["model"]:
                effective_spec["model"]["search_space"] = {
                    k: v for k, v in effective_spec["model"]["search_space"].items() if k not in pinned
                }

        if plan.get("preprocessing") is None:
            recipe = legacy_recipe(profile, effective_spec, plan)
        else:
            recipe = resolve_recipe(plan, profile, effective_spec)

        pipeline, info = compile_recipe(recipe, profile, effective_spec, plan)
        feature_cols = info.feature_columns
        if not feature_cols:
            raise ValueError("No usable feature columns after exclusions")

        rows = df.dropna(subset=[plan["target_column"]])
        X, y_raw = rows[feature_cols], rows[plan["target_column"]]

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
        prefix = info.model_param_prefix

        tune_result = tuning_mod.tune(
            pipeline,
            X_train,
            y_train,
            spec=effective_spec,
            plan=plan,
            cv=cv,
            scoring=scoring,
            param_prefix=prefix,
            primary_metric=primary_metric,
            is_classification=is_classification,
            progress=progress,
        )
        cv_summary = tune_result.cv_summary
        best_params = tune_result.best_params
        fitted = tune_result.fitted

        progress("evaluating", 70, "Evaluating on held-out test data")
        metric_names = spec["metrics"][task_type]["supported"]
        holdout = evaluation.evaluate_holdout(
            fitted, X_test, y_test, y_train, task_type, metric_names, label_classes
        )
        progress("evaluating", 82, "Computing feature importances")
        importances = evaluation.permutation_importances(fitted, X_test, y_test, scoring)

        progress("evaluating", 88, "Running trust diagnostics")
        diagnostics: dict = {"segments": [], "calibration": None, "single_feature": []}
        try:
            y_pred_test = fitted.predict(X_test)
            y_proba_test = (
                fitted.predict_proba(X_test)
                if is_classification and hasattr(fitted, "predict_proba")
                else None
            )
        except Exception:
            y_pred_test, y_proba_test = None, None

        if y_pred_test is not None:
            try:
                diagnostics["segments"] = evaluation.segment_metrics(
                    X_test, y_test, y_pred_test, y_proba_test, task_type, primary_metric, importances
                )
            except Exception:
                diagnostics["segments"] = []

            try:
                diagnostics["calibration"] = evaluation.calibration_bins(y_test, y_proba_test)
            except Exception:
                diagnostics["calibration"] = None

            try:
                full_score = holdout["metrics"].get(primary_metric)
                diagnostics["single_feature"] = evaluation.single_feature_leakage(
                    X_train, y_train, X_test, y_test, task_type, primary_metric, importances, full_score
                )
            except Exception:
                diagnostics["single_feature"] = []

        caveats = evaluation.build_caveats(
            task_type,
            primary_metric,
            holdout,
            importances,
            profile,
            plan,
            len(y_test),
            segments=diagnostics["segments"],
            calibration=diagnostics["calibration"],
            single_feature=diagnostics["single_feature"],
        )

        applied = preprocessing_applied(fitted, recipe, info, X_train.head(5))

        results = {
            "methodology": {"id": spec["id"], "display_name": spec["display_name"]},
            "task_type": task_type,
            # Cross-family tags: which data shape / task family produced this envelope.
            "data_shape": "tabular",
            "task_family": "supervised",
            "target_column": plan["target_column"],
            "primary_metric": primary_metric,
            "best_params": best_params,
            "cv": cv_summary,
            "holdout": holdout,
            "feature_importances": importances,
            "features_used": feature_cols,
            "features_dropped": info.dropped,
            "caveats": caveats,
            "diagnostics": diagnostics,
            "tuning": tune_result.tuning,
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "training_seconds": round(time.time() - t0, 1),
            "preprocessing_applied": applied,
        }

        meta = {
            "spec": spec,
            "feature_columns": feature_cols,
            "numeric_columns": info.numeric_columns,
            "categorical_columns": info.categorical_columns,
            "recipe": recipe,
            "profile": profile,
            "uses_imblearn": info.uses_imblearn,
            "label_classes": label_classes,
            "best_params": best_params,
            "data_shape": "tabular",
            "task_family": "supervised",
            "target_column": plan["target_column"],
            "task_type": task_type,
        }
        return RunOutcome(results=results, artifact=fitted, meta=meta)


register_runner(SupervisedRunner())
