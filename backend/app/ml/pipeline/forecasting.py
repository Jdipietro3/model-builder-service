"""Forecasting task runner: rolling-origin backtest + holdout evaluation over a
timeseries payload.

Time-ordered throughout — NO shuffling. We train on the past and evaluate on the most
recent tail; model selection is a rolling-origin backtest (grid search by mean primary
metric across folds). Two framings plug in behind one flow:

- ``prophet``: an additive model fit on (ds, y); intervals come from Prophet directly.
- ``lag_features``: a gradient-boosting regressor over lag / rolling / calendar
  features, forecast recursively; intervals from empirical backtest-residual quantiles.

All forecasting metrics are lower-is-better; the seasonal-naive forecast is the
baseline every run is measured against. Metric helpers are self-contained here (the
supervised ``evaluation`` module is classification/regression specific).
"""

import itertools
import logging
import time
import warnings

import numpy as np
import pandas as pd

from ..registry.loader import resolve_model_class
from .base import LoadedData, ProgressCb, RunOutcome, register_runner

# LightGBM/sklearn emit this when predicting on a bare numpy array (recursive
# forecasting has no column names); it floods the backtest loop.
warnings.filterwarnings("ignore", message="X does not have valid feature names")

# Prophet + its cmdstanpy backend log INFO-level chatter on every fit; silence to
# WARNING so a multi-fold backtest doesn't drown the progress beats.
for _name in ("prophet", "cmdstanpy", "cmdstanpy.model", "cmdstanpy.utils"):
    logging.getLogger(_name).setLevel(logging.WARNING)


# --------------------------------------------------------------------------- #
# Metrics (self-contained, all lower-is-better, rounded to 4 like supervised)  #
# --------------------------------------------------------------------------- #
def _seasonal_period(freq: str | None) -> int:
    """Seasonal period m implied by a pandas freq string."""
    if not freq:
        return 1
    head = freq[0].upper()
    return {"H": 24, "D": 7, "W": 52, "M": 12, "Q": 4}.get(head, 1)


def _mae(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - pred)))


def _rmse(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - pred) ** 2)))


def _mape(actual: np.ndarray, pred: np.ndarray) -> float | None:
    mask = actual != 0  # undefined on zero-actual points; skip them
    if not mask.any():
        return None
    return float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])) * 100.0)


def _smape(actual: np.ndarray, pred: np.ndarray) -> float | None:
    denom = (np.abs(actual) + np.abs(pred)) / 2.0
    mask = denom != 0
    if not mask.any():
        return None
    return float(np.mean(np.abs(actual[mask] - pred[mask]) / denom[mask]) * 100.0)


def _mase(actual: np.ndarray, pred: np.ndarray, train: np.ndarray, m: int) -> float | None:
    """MASE: forecast MAE over the in-sample MAE of a seasonal-naive forecast on the
    TRAINING series. m falls back to 1 if the series is shorter than one season."""
    if m >= len(train):
        m = 1
    if len(train) <= m:
        return None
    denom = float(np.mean(np.abs(train[m:] - train[:-m])))
    if denom == 0:
        return None
    return float(_mae(actual, pred) / denom)


def _compute_metrics(
    actual: np.ndarray, pred: np.ndarray, train: np.ndarray, m: int
) -> dict[str, float | None]:
    """The forecasting metric set for one (actual, pred) window."""
    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    raw = {
        "mae": _mae(actual, pred),
        "rmse": _rmse(actual, pred),
        "mape": _mape(actual, pred),
        "smape": _smape(actual, pred),
        "mase": _mase(actual, pred, np.asarray(train, dtype=float), m),
    }
    return {k: (round(v, 4) if v is not None else None) for k, v in raw.items()}


def _seasonal_naive_forecast(train: np.ndarray, horizon: int, m: int) -> np.ndarray:
    """Repeat the last season forward: y[t] = y[t - m]."""
    m = m if m < len(train) else 1
    last = train[-m:]
    return np.array([last[i % m] for i in range(horizon)], dtype=float)


# --------------------------------------------------------------------------- #
# Lag-feature framing helpers                                                  #
# --------------------------------------------------------------------------- #
def _lag_feature_names(lags: list[int], rolling: list[int], calendar: bool) -> list[str]:
    names = [f"lag_{l}" for l in lags] + [f"rollmean_{w}" for w in rolling]
    if calendar:
        names += ["dayofweek", "day", "month"]
    return names


def _build_lag_matrix(
    y: np.ndarray, ts: pd.DatetimeIndex, lags: list[int], rolling: list[int], calendar: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Design matrix for supervised lag regression. Rolling means are trailing (shifted
    by one step) so a row never sees its own target — no leakage."""
    start = max([max(lags) if lags else 0] + [max(rolling) if rolling else 0])
    rows, targets = [], []
    for i in range(start, len(y)):
        feats = [y[i - l] for l in lags]
        feats += [float(np.mean(y[i - w:i])) for w in rolling]
        if calendar:
            t = ts[i]
            feats += [t.dayofweek, t.day, t.month]
        rows.append(feats)
        targets.append(y[i])
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _recursive_forecast(
    model,
    hist_y: np.ndarray,
    future_ts: pd.DatetimeIndex,
    lags: list[int],
    rolling: list[int],
    calendar: bool,
) -> np.ndarray:
    """Multi-step forecast: predict one step, append it, rebuild features, repeat.
    Error compounds over the horizon (flagged in caveats)."""
    work = list(hist_y)
    preds = []
    for t in future_ts:
        i = len(work)
        feats = [work[i - l] for l in lags]
        feats += [float(np.mean(work[i - w:i])) for w in rolling]
        if calendar:
            feats += [t.dayofweek, t.day, t.month]
        p = float(model.predict(np.asarray([feats], dtype=float))[0])
        preds.append(p)
        work.append(p)
    return np.asarray(preds, dtype=float)


# --------------------------------------------------------------------------- #
# Framing dispatch: fit a fresh model and forecast a window                    #
# --------------------------------------------------------------------------- #
def _make_model(spec: dict, params: dict):
    cls = resolve_model_class(spec["model"]["class"])
    return cls(**{**spec["model"].get("params", {}), **params})


def _fit_and_forecast(
    framing: str,
    spec: dict,
    params: dict,
    train_y: np.ndarray,
    train_ts: pd.DatetimeIndex,
    future_ts: pd.DatetimeIndex,
    config: dict,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, object, list[str]]:
    """Fit on (train_ts, train_y) and forecast len(future_ts) steps.

    Returns (point, lower, upper, fitted_model, feature_names). lower/upper are native
    intervals for prophet and None for lag_features (those get residual intervals at
    the call site). A fresh model is built every call — Prophet cannot be refit.
    """
    if framing == "prophet":
        model = _make_model(spec, params)
        model.fit(pd.DataFrame({"ds": np.asarray(train_ts), "y": np.asarray(train_y, dtype=float)}))
        fc = model.predict(pd.DataFrame({"ds": np.asarray(future_ts)}))
        return (
            fc["yhat"].to_numpy(),
            fc["yhat_lower"].to_numpy(),
            fc["yhat_upper"].to_numpy(),
            model,
            [],
        )

    # lag_features
    lags = [l for l in config["lags"] if l < len(train_y)]
    rolling = [w for w in config["rolling_windows"] if w < len(train_y)]
    calendar = config["calendar_features"]
    feat_names = _lag_feature_names(lags, rolling, calendar)
    X, y = _build_lag_matrix(np.asarray(train_y, dtype=float), pd.DatetimeIndex(train_ts), lags, rolling, calendar)
    model = _make_model(spec, params)
    model.fit(X, y)
    point = _recursive_forecast(
        model, np.asarray(train_y, dtype=float), pd.DatetimeIndex(future_ts), lags, rolling, calendar
    )
    return point, None, None, model, feat_names


def _future_timestamps(all_ts: pd.DatetimeIndex, horizon: int, freq: str | None) -> pd.DatetimeIndex:
    """Continue the timeline `horizon` steps past the last observed timestamp."""
    last = all_ts[-1]
    if freq:
        try:
            return pd.date_range(start=last, periods=horizon + 1, freq=freq)[1:]
        except (ValueError, TypeError):
            pass  # freq was a raw timedelta description, not a real alias
    step = pd.to_timedelta(np.median(np.diff(all_ts.asi8)), unit="ns")
    return pd.DatetimeIndex([last + step * (i + 1) for i in range(horizon)])


# --------------------------------------------------------------------------- #
# Serialisation helpers                                                        #
# --------------------------------------------------------------------------- #
def _round_list(values) -> list[float]:
    return [round(float(v), 4) for v in values]


def _iso_list(index: pd.DatetimeIndex) -> list[str]:
    return [pd.Timestamp(t).isoformat() for t in index]


def _residual_interval(point: np.ndarray, residuals: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """Empirical ~80% interval from backtest residuals (actual - predicted)."""
    if not residuals:
        return point, point
    lo = float(np.percentile(residuals, 10))
    hi = float(np.percentile(residuals, 90))
    return point + lo, point + hi


def _build_caveats(
    framing: str,
    primary_metric: str,
    holdout_metrics: dict,
    baseline_metrics: dict,
    n_train: int,
    n_gaps: int | None,
    n_dropped: int,
    freq: str | None,
) -> list[str]:
    """Plain-language warnings, in the spirit of supervised's build_caveats."""
    caveats: list[str] = [
        "Univariate forecast: only the target's own history is used — all other "
        "columns in the dataset are ignored."
    ]
    if n_gaps:
        caveats.append(
            f"The series has {n_gaps} missing period(s) at the inferred '{freq}' "
            "frequency; gaps were not filled and may bias the forecast."
        )
    mv, bv = holdout_metrics.get(primary_metric), baseline_metrics.get(primary_metric)
    if mv is not None and bv is not None and mv >= bv:
        caveats.append(
            f"The model does not beat the seasonal-naive baseline on {primary_metric} "
            f"({mv} vs {bv}) — the series may be dominated by simple seasonality or noise."
        )
    if n_train < 100:
        caveats.append(
            f"Short history ({n_train} training points): forecasts and intervals have "
            "wide error bars; collect more data if possible."
        )
    if framing == "lag_features":
        caveats.append(
            "Prediction intervals are approximate — empirical backtest-residual "
            "quantiles (~80% nominal), and they do not widen with horizon."
        )
    if n_dropped:
        caveats.append(
            f"{n_dropped} row(s) with unparseable timestamps were dropped before training."
        )
    return caveats


# --------------------------------------------------------------------------- #
# Runner                                                                       #
# --------------------------------------------------------------------------- #
class ForecastingRunner:
    task_family = "forecasting"
    compatible_shapes = ("timeseries",)

    def run(self, data: LoadedData, spec: dict, plan: dict, progress: ProgressCb) -> RunOutcome:
        t0 = time.time()
        df = data.payload
        ts_profile = data.profile["timeseries"]

        time_col = plan["time_column"]
        target_col = plan["target_column"]
        horizon = int(plan["horizon"])
        primary_metric = plan["primary_metric"]
        n_splits_req = plan.get("validation", {}).get("n_splits", 3)
        freq = ts_profile["freq"]
        framing = spec["preprocessing"]["timeseries"]["framing"]

        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in dataset")

        # Clean tail: drop NaN-target rows before splitting (note how many).
        work = df[[time_col, target_col]].copy()
        n_dropped_target = int(work[target_col].isna().sum())
        work = work.dropna(subset=[target_col]).reset_index(drop=True)
        timestamps = pd.DatetimeIndex(pd.to_datetime(work[time_col]))
        y = work[target_col].astype(float).to_numpy()
        n = len(y)

        # 1. Holdout = last `horizon` rows; train = everything before.
        n_train = n - horizon
        if n_train < max(2 * horizon, 20):
            raise ValueError(
                f"Not enough history: {n_train} training rows for horizon {horizon}; "
                f"need at least {max(2 * horizon, 20)}. Reduce the horizon or add data."
            )
        train_y, holdout_y = y[:n_train], y[n_train:]
        train_ts, holdout_ts = timestamps[:n_train], timestamps[n_train:]
        m = _seasonal_period(freq)

        config = {
            "lags": spec["preprocessing"]["timeseries"].get("lags", [1, 2, 3, 7, 14]),
            "rolling_windows": spec["preprocessing"]["timeseries"].get("rolling_windows", [7]),
            "calendar_features": spec["preprocessing"]["timeseries"].get("calendar_features", True),
        }

        # 2. Rolling-origin backtest fold cutoffs within train. Each fold forecasts the
        #    next `horizon` rows; the last fold's window ends at the end of train.
        min_fold_train = 2 * horizon
        folds = n_splits_req
        while folds > 1 and (n_train - horizon - (folds - 1) * horizon) < min_fold_train:
            folds -= 1
        cutoffs = [n_train - horizon - (folds - 1 - k) * horizon for k in range(folds)]

        # Grid = cartesian product of the spec grid (empty grid -> single param-only candidate).
        grid = spec["model"].get("grid", {})
        keys = list(grid)
        combos = list(itertools.product(*(grid[k] for k in keys))) if keys else [()]
        candidates = [dict(zip(keys, combo)) for combo in combos]

        progress(
            "cross_validation",
            25,
            f"Backtesting {len(candidates)} configuration(s) x {folds} folds",
        )

        def backtest(params: dict) -> tuple[float, list, list]:
            fold_scores, residuals = [], []
            for cutoff in cutoffs:
                tr_y, tr_ts = train_y[:cutoff], train_ts[:cutoff]
                ev_y, ev_ts = train_y[cutoff:cutoff + horizon], train_ts[cutoff:cutoff + horizon]
                point, _lo, _hi, _model, _feat = _fit_and_forecast(
                    framing, spec, params, tr_y, tr_ts, ev_ts, config
                )
                fold_scores.append(_compute_metrics(ev_y, point, tr_y, m).get(primary_metric))
                residuals.extend((ev_y - point).tolist())
            valid = [s for s in fold_scores if s is not None]
            mean_score = float(np.mean(valid)) if valid else float("inf")
            return mean_score, fold_scores, residuals

        best = None  # (mean_score, params, fold_scores, residuals)
        for params in candidates:
            mean_score, fold_scores, residuals = backtest(params)
            if best is None or mean_score < best[0]:
                best = (mean_score, params, fold_scores, residuals)
        _best_score, best_params, best_fold_scores, best_residuals = best

        valid_scores = [s for s in best_fold_scores if s is not None]
        cv_summary = {
            "metric": primary_metric,
            "mean": round(float(np.mean(valid_scores)), 4) if valid_scores else None,
            "std": round(float(np.std(valid_scores)), 4) if valid_scores else None,
            "n_splits": folds,
        }

        # 3. Refit best on train, forecast the holdout window + seasonal-naive baseline.
        progress("evaluating", 70, "Evaluating on held-out recent data")
        h_point, h_lo, h_hi, _model, _feat = _fit_and_forecast(
            framing, spec, best_params, train_y, train_ts, holdout_ts, config
        )
        if h_lo is None:  # lag framing: residual-quantile interval
            h_lo, h_hi = _residual_interval(h_point, best_residuals)
        holdout_metrics = _compute_metrics(holdout_y, h_point, train_y, m)
        eff_m = m if m < len(train_y) else 1
        baseline_pred = _seasonal_naive_forecast(train_y, horizon, m)
        baseline_metrics = _compute_metrics(holdout_y, baseline_pred, train_y, m)
        baseline_description = (
            f"Seasonal-naive baseline (repeat value from m periods earlier, m={eff_m})"
        )

        # 4. Refit best on ALL rows, forecast the future horizon.
        progress("evaluating", 82, "Fitting final model and forecasting future horizon")
        future_ts = _future_timestamps(timestamps, horizon, freq)
        f_point, f_lo, f_hi, fitted_model, feature_names = _fit_and_forecast(
            framing, spec, best_params, y, timestamps, future_ts, config
        )
        if f_lo is None:
            f_lo, f_hi = _residual_interval(f_point, best_residuals)

        # History tail for plotting: last min(3*horizon, n) actual rows.
        tail_n = min(3 * horizon, n)
        history_tail = {
            "timestamps": _iso_list(timestamps[-tail_n:]),
            "actual": _round_list(y[-tail_n:]),
        }

        caveats = _build_caveats(
            framing,
            primary_metric,
            holdout_metrics,
            baseline_metrics,
            n_train,
            ts_profile.get("n_gaps"),
            ts_profile.get("n_dropped_bad_timestamps", 0),
            freq,
        )

        results = {
            "methodology": {"id": spec["id"], "display_name": spec["display_name"]},
            "task_type": "forecasting",
            "data_shape": "timeseries",
            "task_family": "forecasting",
            "target_column": target_col,
            "time_column": time_col,
            "horizon": horizon,
            "freq": freq,
            "primary_metric": primary_metric,
            "best_params": best_params,
            "cv": cv_summary,
            "holdout": {
                "metrics": holdout_metrics,
                "baseline_metrics": baseline_metrics,
                "baseline_description": baseline_description,
            },
            "holdout_series": {
                "timestamps": _iso_list(holdout_ts),
                "actual": _round_list(holdout_y),
                "predicted": _round_list(h_point),
                "lower": _round_list(h_lo),
                "upper": _round_list(h_hi),
            },
            "forecast": {
                "timestamps": _iso_list(future_ts),
                "yhat": _round_list(f_point),
                "lower": _round_list(f_lo),
                "upper": _round_list(f_hi),
            },
            "history_tail": history_tail,
            "caveats": caveats,
            "n_train": int(n_train),
            "n_test": int(horizon),
            "training_seconds": round(time.time() - t0, 1),
        }

        # Artifact: for lag framing, bundle everything needed to rebuild features at
        # score time; for prophet, the fitted model is self-contained.
        if framing == "prophet":
            artifact = fitted_model
        else:
            lags = [l for l in config["lags"] if l < len(y)]
            rolling = [w for w in config["rolling_windows"] if w < len(y)]
            tail_len = (max(lags + rolling) if (lags + rolling) else 0) + 1
            artifact = {
                "model": fitted_model,
                "lags": lags,
                "rolling_windows": rolling,
                "calendar_features": config["calendar_features"],
                "history_tail": pd.DataFrame(
                    {time_col: timestamps[-tail_len:], target_col: y[-tail_len:]}
                ).reset_index(drop=True),
            }

        meta = {
            "spec": spec,
            "data_shape": "timeseries",
            "task_family": "forecasting",
            "task_type": "forecasting",
            "target_column": target_col,
            "time_column": time_col,
            "horizon": horizon,
            "freq": freq,
            "framing": framing,
            "best_params": best_params,
            "feature_columns": feature_names,
            "label_classes": None,
        }
        return RunOutcome(results=results, artifact=artifact, meta=meta)


register_runner(ForecastingRunner())
