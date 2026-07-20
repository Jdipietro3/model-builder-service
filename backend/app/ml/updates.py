"""Pure logic for the dataset-update flow (replace/append a new CSV onto an
existing dataset). Kept free of DB/FastAPI concerns so it's directly testable.
"""

from typing import Any

import pandas as pd


def check_schema(old_df: pd.DataFrame, new_df: pd.DataFrame) -> str | None:
    """Column NAMES must match exactly (order-insensitive). Returns an error
    string naming the missing/extra columns, or None if the schemas match."""
    old_cols = set(old_df.columns)
    new_cols = set(new_df.columns)
    if old_cols == new_cols:
        return None
    missing = sorted(old_cols - new_cols)
    extra = sorted(new_cols - old_cols)
    parts = []
    if missing:
        parts.append(f"missing columns: {', '.join(missing)}")
    if extra:
        parts.append(f"extra columns: {', '.join(extra)}")
    return "New file's columns don't match the existing dataset (" + "; ".join(parts) + ")"


def merge_append(old_df: pd.DataFrame, new_df: pd.DataFrame, time_column: str | None) -> pd.DataFrame:
    """Concatenate old + new. With a time_column, dedupe on it keeping the LAST
    occurrence (the new upload wins on overlapping timestamps) and sort ascending
    by parsed timestamp. Without one, drop exact duplicate rows."""
    merged = pd.concat([old_df, new_df], ignore_index=True)
    if time_column:
        merged = merged.drop_duplicates(subset=[time_column], keep="last")
        order = pd.to_datetime(merged[time_column], errors="coerce")
        merged = merged.iloc[order.argsort(kind="stable")].reset_index(drop=True)
    else:
        merged = merged.drop_duplicates(keep="last").reset_index(drop=True)
    return merged


def build_diff(
    old_df: pd.DataFrame, new_df_merged: pd.DataFrame, time_column: str | None, mode: str
) -> dict[str, Any]:
    rows_before = len(old_df)
    rows_after = len(new_df_merged)
    time_range_before = None
    time_range_after = None
    if time_column:
        old_ts = pd.to_datetime(old_df[time_column], errors="coerce").dropna()
        new_ts = pd.to_datetime(new_df_merged[time_column], errors="coerce").dropna()
        if not old_ts.empty:
            time_range_before = [old_ts.min().date().isoformat(), old_ts.max().date().isoformat()]
        if not new_ts.empty:
            time_range_after = [new_ts.min().date().isoformat(), new_ts.max().date().isoformat()]
    return {
        "mode": mode,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_added": rows_after - rows_before,
        "time_range_before": time_range_before,
        "time_range_after": time_range_after,
    }
