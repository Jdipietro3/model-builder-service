"""Phase 2: hyperparameter search for the supervised pipeline.

``tune()`` is the single entry point ``pipeline/supervised.py`` calls. It
dispatches on ``plan.tuning.strategy``:

- ``grid`` (default): today's ``GridSearchCV`` over the spec's grid, verbatim
  — this is the golden path pinned by ``tests/test_golden.py``. No fits are
  re-run to build the ``tuning`` envelope; it is assembled from
  ``search.cv_results_``.
- ``none``: fit once with default+pinned params, ``cross_val_score`` for the
  cv summary.
- ``random`` / ``bayesian``: an Optuna study over the spec's
  ``model.search_space``, with manual per-fold cross-validation so trials can
  be pruned mid-fold.

See ``pipeline/base.py``'s module docstring for the ``tuning`` results-envelope
shape.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from sklearn.base import clone
from sklearn.metrics import get_scorer
from sklearn.model_selection import GridSearchCV, cross_val_score

from .. import config

ProgressCb = Callable[[str, int, str], None]

MAX_TRIALS_IN_ENVELOPE = 200

__all__ = ["TuneResult", "resolve_budget", "tune"]


@dataclass
class TuneResult:
    fitted: Any
    best_params: dict
    cv_summary: dict
    tuning: dict


def resolve_budget(tuning: dict | None, n_rows: int) -> dict:
    """Normalize a plan's (possibly absent/partial) ``tuning`` block into
    concrete values. Absent/None -> grid strategy, matching today's behavior.
    """
    tuning = tuning or {}
    strategy = tuning.get("strategy") or "grid"

    n_trials = tuning.get("n_trials")
    if n_trials is None:
        n_trials = 10 if n_rows < 2000 else 20

    time_budget_s = tuning.get("time_budget_s")
    if time_budget_s is None:
        time_budget_s = config.TUNING_DEFAULT_TIME_S
    time_budget_s = min(int(time_budget_s), config.TUNING_MAX_TIME_S)

    cv_splits = tuning.get("cv_splits")

    return {
        "strategy": strategy,
        "n_trials": int(n_trials),
        "time_budget_s": time_budget_s,
        "cv_splits": cv_splits,
    }


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _jsonify(obj: Any) -> Any:
    """Recursively cast numpy scalars to native Python types so the tuning
    envelope is plain-JSON-serialisable."""
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _cap_trials(trials: list[dict], cap: int = MAX_TRIALS_IN_ENVELOPE) -> tuple[list[dict], str | None]:
    """Cap ``trials`` at ``cap`` entries, keeping the best-scoring ones plus
    the first few (so the search's starting point is still visible)."""
    if len(trials) <= cap:
        return trials, None

    keep_first_n = 10
    first = trials[:keep_first_n]
    scored = [t for t in trials if t.get("score") is not None]
    best = sorted(scored, key=lambda t: t["score"], reverse=True)[: cap - keep_first_n]

    kept_ids = {id(t) for t in first} | {id(t) for t in best}
    kept = [t for t in trials if id(t) in kept_ids]
    kept.sort(key=lambda t: t["number"])
    note = f"trials truncated to {len(kept)} of {len(trials)} (best-scoring plus the first {keep_first_n})"
    return kept, note


def _fit_default(pipeline, X_train, y_train, *, cv, scoring, primary_metric, n_splits, pinned):
    """Fit the pipeline once with its (already pinned-merged) default params;
    cv summary via ``cross_val_score``. Shared by the ``none`` strategy and
    the Optuna "no trial completed" fallback."""
    scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring=scoring, n_jobs=-1)
    fitted = clone(pipeline).fit(X_train, y_train)
    cv_summary = {
        "metric": primary_metric,
        "mean": round(float(scores.mean()), 4),
        "std": round(float(scores.std()), 4),
        "n_splits": n_splits,
        "n_candidates": 1,
    }
    best_params = _jsonify(dict(pinned))
    return fitted, cv_summary, best_params, scores


# --------------------------------------------------------------------------- #
# Grid strategy (golden path)                                                 #
# --------------------------------------------------------------------------- #


def _tune_grid(pipeline, X_train, y_train, *, spec, cv, scoring, param_prefix, primary_metric, n_splits, pinned, progress: ProgressCb) -> TuneResult:
    grid_raw = spec["model"].get("grid", {})
    grid = {f"{param_prefix}{k}": v for k, v in grid_raw.items()}

    n_candidates = 1
    for values in grid_raw.values():
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
    best_params = {k.removeprefix(param_prefix): v for k, v in search.best_params_.items()}
    fitted = search.best_estimator_

    trials = []
    cvr = search.cv_results_
    for i, params in enumerate(cvr["params"]):
        mean_score = cvr["mean_test_score"][i]
        score_ok = mean_score is not None and not np.isnan(mean_score)
        duration = float(cvr["mean_fit_time"][i] + cvr["mean_score_time"][i]) * n_splits
        trials.append(
            {
                "number": i,
                "params": _jsonify({k.removeprefix(param_prefix): v for k, v in params.items()}),
                "score": round(float(mean_score), 4) if score_ok else None,
                "duration_s": round(duration, 2),
                "state": "complete" if score_ok else "failed",
            }
        )
    trials, note = _cap_trials(trials)

    tuning_envelope = {
        "strategy": "grid",
        "n_trials": n_candidates,
        "n_pruned": 0,
        "n_failed": sum(1 for t in trials if t["state"] == "failed"),
        "time_budget_s": None,
        "elapsed_s": round(float(cvr["mean_fit_time"].sum() + cvr["mean_score_time"].sum()) * n_splits, 1),
        "best_params": _jsonify(best_params),
        "search_space": None,
        "pinned": _jsonify(pinned),
        "trials": trials,
        "importance": None,
        "note": note,
    }

    return TuneResult(fitted=fitted, best_params=best_params, cv_summary=cv_summary, tuning=tuning_envelope)


# --------------------------------------------------------------------------- #
# None strategy                                                               #
# --------------------------------------------------------------------------- #


def _tune_none(pipeline, X_train, y_train, *, cv, scoring, primary_metric, n_splits, pinned, progress: ProgressCb, t_start: float) -> TuneResult:
    progress("cross_validation", 25, f"Cross-validating 1 configuration(s) x {n_splits} folds")
    fitted, cv_summary, best_params, scores = _fit_default(
        pipeline, X_train, y_train, cv=cv, scoring=scoring, primary_metric=primary_metric, n_splits=n_splits, pinned=pinned
    )
    elapsed = round(time.time() - t_start, 1)
    trials = [
        {
            "number": 0,
            "params": _jsonify(dict(pinned)),
            "score": cv_summary["mean"],
            "duration_s": elapsed,
            "state": "complete",
        }
    ]
    tuning_envelope = {
        "strategy": "none",
        "n_trials": 1,
        "n_pruned": 0,
        "n_failed": 0,
        "time_budget_s": None,
        "elapsed_s": elapsed,
        "best_params": best_params,
        "search_space": None,
        "pinned": _jsonify(pinned),
        "trials": trials,
        "importance": None,
        "note": None,
    }
    return TuneResult(fitted=fitted, best_params=best_params, cv_summary=cv_summary, tuning=tuning_envelope)


# --------------------------------------------------------------------------- #
# Random / bayesian strategies (Optuna)                                       #
# --------------------------------------------------------------------------- #


def _tune_optuna(pipeline, X_train, y_train, *, spec, cv, scoring, param_prefix, primary_metric, budget, pinned, progress: ProgressCb, t_start: float) -> TuneResult:
    import optuna
    from optuna.pruners import MedianPruner
    from optuna.samplers import RandomSampler, TPESampler

    # `spec` is the caller's effective_spec: pinned keys are already stripped
    # out of `search_space` (mirroring what it does to `grid`), so an absent/
    # None key means the methodology never declared one at all (a real
    # error), while a present-but-empty dict means every declared param
    # happens to be pinned (nothing left to search, not an error).
    search_space_full = spec["model"].get("search_space")
    if search_space_full is None:
        raise ValueError(
            f"methodology {spec.get('id', '<unknown>')} has no search_space; use strategy grid or none"
        )
    search_space = search_space_full

    strategy = budget["strategy"]
    n_trials = budget["n_trials"]
    time_budget_s = budget["time_budget_s"]
    n_splits = cv.get_n_splits()

    if not search_space:
        # Every search_space param is pinned: nothing left to search. Same
        # shape as the "no trial completed" fallback below, minus the study.
        progress("cross_validation", 25, f"Cross-validating 1 configuration(s) x {n_splits} folds")
        fitted, cv_summary, best_params, _ = _fit_default(
            pipeline, X_train, y_train, cv=cv, scoring=scoring, primary_metric=primary_metric, n_splits=n_splits, pinned=pinned
        )
        elapsed_s = round(time.time() - t_start, 1)
        tuning_envelope = {
            "strategy": strategy,
            "n_trials": 1,
            "n_pruned": 0,
            "n_failed": 0,
            "time_budget_s": time_budget_s,
            "elapsed_s": elapsed_s,
            "best_params": best_params,
            "search_space": {},
            "pinned": _jsonify(pinned),
            "trials": [
                {"number": 0, "params": _jsonify(dict(pinned)), "score": cv_summary["mean"], "duration_s": elapsed_s, "state": "complete"}
            ],
            "importance": None,
            "note": "every search_space parameter is pinned; nothing left to search",
        }
        return TuneResult(fitted=fitted, best_params=best_params, cv_summary=cv_summary, tuning=tuning_envelope)

    scorer = get_scorer(scoring)
    splits = list(cv.split(X_train, y_train))
    n_splits = len(splits)

    if strategy == "random":
        sampler = RandomSampler(seed=42)
    else:
        sampler = TPESampler(seed=42, n_startup_trials=min(5, max(1, n_trials // 2)))
    pruner = MedianPruner(n_startup_trials=3, n_warmup_steps=1)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize", sampler=sampler, pruner=pruner)

    last_beat = [0.0]

    def objective(trial):
        params = {}
        for name, entry in search_space.items():
            if entry["type"] == "int":
                params[name] = trial.suggest_int(name, int(entry["low"]), int(entry["high"]), log=bool(entry.get("log", False)))
            elif entry["type"] == "float":
                params[name] = trial.suggest_float(name, float(entry["low"]), float(entry["high"]), log=bool(entry.get("log", False)))
            else:
                params[name] = trial.suggest_categorical(name, entry["choices"])

        est_base = clone(pipeline).set_params(**{f"{param_prefix}{k}": v for k, v in params.items()})

        fold_scores = []
        trial_t0 = time.time()
        for fold_idx, (train_idx, val_idx) in enumerate(splits):
            X_tr, X_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
            y_tr, y_val = y_train[train_idx], y_train[val_idx]
            est_fold = clone(est_base)
            est_fold.fit(X_tr, y_tr)
            score = scorer(est_fold, X_val, y_val)
            fold_scores.append(float(score))
            running_mean = sum(fold_scores) / len(fold_scores)
            trial.report(running_mean, step=fold_idx)
            if trial.should_prune():
                raise optuna.TrialPruned()

        duration = time.time() - trial_t0
        mean_score = sum(fold_scores) / len(fold_scores)
        std_score = float(np.std(fold_scores))
        trial.set_user_attr("mean", mean_score)
        trial.set_user_attr("std", std_score)
        trial.set_user_attr("duration_s", duration)

        now = time.time()
        if now - last_beat[0] >= 1.0:
            done = sum(1 for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE)
            best = max(mean_score, study.best_value) if done else mean_score
            progress(
                "tuning",
                25 + int(45 * (done + 1) / max(1, n_trials)),
                f"Trial {done + 1}/{n_trials} · best {primary_metric} {best:.4f}",
            )
            last_beat[0] = now
        return mean_score

    study.optimize(
        objective,
        n_trials=n_trials,
        timeout=time_budget_s,
        n_jobs=1,
        gc_after_trial=False,
        catch=(Exception,),
    )

    TrialState = optuna.trial.TrialState
    completed = [t for t in study.trials if t.state == TrialState.COMPLETE]
    n_pruned = sum(1 for t in study.trials if t.state == TrialState.PRUNED)
    n_failed = sum(1 for t in study.trials if t.state == TrialState.FAIL)
    elapsed_s = round(time.time() - t_start, 1)

    note = None
    if not completed:
        # No trial completed: fall back to a single default+pinned fit.
        progress("cross_validation", 60, "No tuning trial completed; falling back to default parameters")
        fitted, cv_summary, best_params, _ = _fit_default(
            pipeline, X_train, y_train, cv=cv, scoring=scoring, primary_metric=primary_metric, n_splits=n_splits, pinned=pinned
        )
        note = f"no {strategy} trial completed (all pruned/failed or budget exhausted); fell back to default+pinned parameters"
        trials = [
            {
                "number": t.number,
                "params": _jsonify(t.params),
                "score": round(float(t.value), 4) if t.value is not None else None,
                "duration_s": round(float(t.user_attrs.get("duration_s", 0.0)), 2),
                "state": "pruned" if t.state == TrialState.PRUNED else "failed",
            }
            for t in study.trials
        ]
        trials, trunc_note = _cap_trials(trials)
        if trunc_note:
            note = f"{note}; {trunc_note}"
        tuning_envelope = {
            "strategy": strategy,
            "n_trials": 0,
            "n_pruned": n_pruned,
            "n_failed": n_failed,
            "time_budget_s": time_budget_s,
            "elapsed_s": elapsed_s,
            "best_params": best_params,
            "search_space": _jsonify(search_space),
            "pinned": _jsonify(pinned),
            "trials": trials,
            "importance": None,
            "note": note,
        }
        return TuneResult(fitted=fitted, best_params=best_params, cv_summary=cv_summary, tuning=tuning_envelope)

    best_trial = study.best_trial
    best_params_sampled = dict(best_trial.params)
    best_params = _jsonify({**pinned, **best_params_sampled})

    fitted = clone(pipeline).set_params(**{f"{param_prefix}{k}": v for k, v in best_params_sampled.items()})
    fitted.fit(X_train, y_train)

    mean = best_trial.user_attrs.get("mean", best_trial.value)
    std = best_trial.user_attrs.get("std", 0.0)
    cv_summary = {
        "metric": primary_metric,
        "mean": round(float(mean), 4),
        "std": round(float(std), 4),
        "n_splits": n_splits,
        "n_candidates": len(completed),
    }

    trials = []
    for t in study.trials:
        state = "complete" if t.state == TrialState.COMPLETE else ("pruned" if t.state == TrialState.PRUNED else "failed")
        score = t.value if t.state == TrialState.COMPLETE else None
        trials.append(
            {
                "number": t.number,
                "params": _jsonify(t.params),
                "score": round(float(score), 4) if score is not None else None,
                "duration_s": round(float(t.user_attrs.get("duration_s", 0.0)), 2),
                "state": state,
            }
        )
    trials, trunc_note = _cap_trials(trials)
    note = trunc_note

    try:
        importance = optuna.importance.get_param_importances(study)
        importance = {k: round(float(v), 4) for k, v in importance.items()}
    except Exception:
        importance = None

    tuning_envelope = {
        "strategy": strategy,
        "n_trials": len(completed),
        "n_pruned": n_pruned,
        "n_failed": n_failed,
        "time_budget_s": time_budget_s,
        "elapsed_s": elapsed_s,
        "best_params": best_params,
        "search_space": _jsonify(search_space),
        "pinned": _jsonify(pinned),
        "trials": trials,
        "importance": importance,
        "note": note,
    }

    return TuneResult(fitted=fitted, best_params=best_params, cv_summary=cv_summary, tuning=tuning_envelope)


# --------------------------------------------------------------------------- #
# Dispatcher                                                                   #
# --------------------------------------------------------------------------- #


def tune(
    pipeline,
    X_train,
    y_train,
    *,
    spec: dict,
    plan: dict,
    cv,
    scoring: str,
    param_prefix: str,
    primary_metric: str,
    is_classification: bool,
    progress: ProgressCb,
) -> TuneResult:
    """Choose and run a hyperparameter search strategy per ``plan['tuning']``.

    ``spec`` is expected to already carry pinned hyperparameters merged into
    ``model.params`` and stripped from ``model.grid``/``model.search_space``
    (the caller's job, so this contract stays identical to the pre-Phase-2
    grid-search block).
    """
    t_start = time.time()
    budget = resolve_budget(plan.get("tuning"), n_rows=len(X_train))
    pinned = plan.get("hyperparameters") or {}

    if budget["cv_splits"] and budget["cv_splits"] != cv.get_n_splits():
        cv = cv.__class__(n_splits=budget["cv_splits"], shuffle=True, random_state=42)
    n_splits = cv.get_n_splits()

    strategy = budget["strategy"]
    if strategy == "grid":
        return _tune_grid(
            pipeline, X_train, y_train, spec=spec, cv=cv, scoring=scoring, param_prefix=param_prefix,
            primary_metric=primary_metric, n_splits=n_splits, pinned=pinned, progress=progress,
        )
    if strategy == "none":
        return _tune_none(
            pipeline, X_train, y_train, cv=cv, scoring=scoring, primary_metric=primary_metric,
            n_splits=n_splits, pinned=pinned, progress=progress, t_start=t_start,
        )
    return _tune_optuna(
        pipeline, X_train, y_train, spec=spec, cv=cv, scoring=scoring, param_prefix=param_prefix,
        primary_metric=primary_metric, budget=budget, pinned=pinned, progress=progress, t_start=t_start,
    )
