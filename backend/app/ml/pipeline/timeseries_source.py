"""Timeseries data source: CSV on disk -> time-ordered, profiled pandas DataFrame.

Contract locked in by this implementation:
- The plan must name a timestamp column (``plan["time_column"]``); ``load`` parses it
  and returns rows in ascending time order (no shuffling anywhere downstream — order
  is signal).
- Frequency is inferred from the timestamp spacing (hourly/daily/weekly/monthly) and
  recorded in the profile so the runner can continue future timestamps and pick a
  seasonal period.
- ``payload`` is a time-sorted DataFrame with the timestamp kept as a regular column;
  gaps are surfaced in the profile (``n_gaps``) rather than silently filled.
"""

import numpy as np
import pandas as pd

from ..profiling import load_csv, profile_dataframe
from .base import LoadedData, ProgressCb, register_source

# Candidate pandas freq strings and their nominal period in seconds. Used to snap a
# median timestamp spacing to the nearest regular frequency when pandas can't infer
# one exactly (irregular but roughly-periodic series).
_FREQ_SECONDS = {
    "h": 3600.0,
    "D": 86400.0,
    "W": 604800.0,
    "MS": 2629800.0,  # ~30.44 days, an average calendar month
}
_FREQ_TOLERANCE = 0.3  # max relative distance to accept a snapped frequency


def _infer_frequency(index: pd.DatetimeIndex) -> tuple[str | None, float | None]:
    """Return (freq_string, median_seconds).

    Prefers pandas' exact ``infer_freq``; falls back to snapping the median spacing to
    the nearest of hourly/daily/weekly/monthly. If nothing fits (highly irregular),
    the freq string is the raw median timedelta description and the runner treats the
    frequency as unknown for seasonality purposes.
    """
    if len(index) < 3:
        return None, None
    inferred = pd.infer_freq(index)
    diffs = np.diff(index.asi8)  # nanoseconds between consecutive stamps
    median_seconds = float(np.median(diffs)) / 1e9 if len(diffs) else None
    if inferred:
        return inferred, median_seconds
    if median_seconds is None or median_seconds <= 0:
        return None, median_seconds
    # Snap to the nearest known frequency by relative distance.
    best_freq, best_rel = None, None
    for freq, seconds in _FREQ_SECONDS.items():
        rel = abs(median_seconds - seconds) / seconds
        if best_rel is None or rel < best_rel:
            best_freq, best_rel = freq, rel
    if best_rel is not None and best_rel <= _FREQ_TOLERANCE:
        return best_freq, median_seconds
    # Nothing regular enough: describe the raw spacing (freq unknown to the runner).
    return str(pd.to_timedelta(median_seconds, unit="s")), median_seconds


def _count_gaps(index: pd.DatetimeIndex, freq: str | None) -> int | None:
    """Missing expected periods between start and end given a pandas freq string.

    Returns None when the frequency is unknown (no pandas-recognisable freq)."""
    if not freq:
        return None
    try:
        expected = pd.date_range(start=index[0], end=index[-1], freq=freq)
    except (ValueError, TypeError):
        return None  # e.g. a raw timedelta description, not a real freq alias
    return max(0, len(expected) - len(index))


class TimeseriesDataSource:
    data_shape = "timeseries"

    def load(self, path: str, plan: dict, progress: ProgressCb) -> LoadedData:
        # Same opening beat the tabular source emits before touching data.
        progress("preparing", 10, "Loading and preparing data")
        df = load_csv(path)

        time_col = plan.get("time_column")
        if not time_col or time_col not in df.columns:
            raise ValueError(
                f"time_column '{time_col}' is required and must be a column in the "
                f"dataset (found: {', '.join(map(str, df.columns))})"
            )

        # Parse timestamps; drop rows we can't place on the timeline.
        parsed = pd.to_datetime(df[time_col], errors="coerce")
        n_bad = int(parsed.isna().sum())
        df = df.assign(**{time_col: parsed}).dropna(subset=[time_col])
        if len(df) < 10:
            raise ValueError(
                f"Only {len(df)} rows have a parseable '{time_col}' timestamp; "
                "need at least 10 to fit a forecast."
            )

        # Duplicate timestamps make a single ordered series ambiguous.
        if df[time_col].duplicated().any():
            raise ValueError(
                f"Column '{time_col}' has duplicate timestamps. Aggregate to one row "
                "per period (e.g. sum/mean per day) before forecasting."
            )

        # Sort ascending; keep the timestamp as a regular column.
        df = df.sort_values(time_col).reset_index(drop=True)

        index = pd.DatetimeIndex(df[time_col])
        freq, _median_seconds = _infer_frequency(index)
        n_gaps = _count_gaps(index, freq)

        profile = profile_dataframe(df)
        profile["timeseries"] = {
            "time_column": time_col,
            "freq": freq,
            "start": index[0].isoformat(),
            "end": index[-1].isoformat(),
            "n_gaps": n_gaps,
            "n_dropped_bad_timestamps": n_bad,
        }
        return LoadedData(data_shape="timeseries", profile=profile, payload=df)


register_source(TimeseriesDataSource())
