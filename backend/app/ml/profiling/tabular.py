"""Tabular (CSV) profiling."""

from typing import Any

import pandas as pd

from .base import register

SAMPLE_ROWS = 5
TOP_VALUES = 5
MAX_SAMPLE_COLS = 30  # cap sample_rows width for very wide datasets
MAX_CELL_CHARS = 40  # keep the profile token-compact


def load_csv(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def _trunc(value: Any) -> str:
    s = str(value)
    return s if len(s) <= MAX_CELL_CHARS else s[: MAX_CELL_CHARS - 1] + "…"


def _classify_column(s: pd.Series, n_rows: int) -> str:
    n_unique = s.nunique(dropna=True)
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_numeric_dtype(s):
        # Integer column where every non-null value is distinct -> likely an ID.
        if pd.api.types.is_integer_dtype(s) and n_rows > 0 and n_unique >= 0.98 * s.notna().sum():
            return "id_like"
        if n_unique <= 2:
            return "boolean"
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    # Object/string columns
    if n_rows > 0 and n_unique >= 0.98 * s.notna().sum():
        return "id_like"
    if n_unique <= max(30, int(0.05 * n_rows)):
        return "categorical"
    return "text"


def _top_values(s: pd.Series, n_rows: int) -> list[dict[str, Any]]:
    counts = s.value_counts(dropna=True).head(TOP_VALUES)
    return [
        {
            "value": _trunc(v),
            "count": int(c),
            "pct": round(100.0 * c / n_rows, 2) if n_rows else 0.0,
        }
        for v, c in counts.items()
    ]


def _sample_rows(df: pd.DataFrame) -> dict[str, Any]:
    sample = df.head(SAMPLE_ROWS)
    truncated_cols = df.shape[1] > MAX_SAMPLE_COLS
    if truncated_cols:
        sample = sample.iloc[:, :MAX_SAMPLE_COLS]
    out: dict[str, Any] = {
        "columns": [str(c) for c in sample.columns],
        "rows": [
            ["" if pd.isna(v) else _trunc(v) for v in row]
            for row in sample.itertuples(index=False)
        ],
    }
    if truncated_cols:
        out["truncated_cols"] = True
    return out


def _target_candidates(df: pd.DataFrame, col_info: list[dict]) -> list[str]:
    name_hints = ("target", "label", "churn", "outcome", "price", "class", "result", "y")
    candidates: list[tuple[int, str]] = []
    for info in col_info:
        name = info["name"]
        kind = info["kind"]
        score = 0
        if any(h in name.lower() for h in name_hints):
            score += 2
        if kind == "boolean":
            score += 2
        elif kind == "categorical" and info["n_unique"] <= 20:
            score += 1
        elif kind == "numeric":
            score += 1
        if info["pct_missing"] > 20:
            score -= 2
        if kind in ("id_like", "text", "datetime"):
            score -= 3
        if score > 0:
            candidates.append((score, name))
    candidates.sort(key=lambda t: -t[0])
    return [name for _, name in candidates[:5]]


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    n_rows, n_cols = df.shape
    columns: list[dict[str, Any]] = []
    for name in df.columns:
        s = df[name]
        kind = _classify_column(s, n_rows)
        n_unique = int(s.nunique(dropna=True))
        n_missing = int(s.isna().sum())
        info: dict[str, Any] = {
            "name": str(name),
            "dtype": str(s.dtype),
            "kind": kind,
            "n_unique": n_unique,
            "n_missing": n_missing,
            "pct_missing": round(100.0 * n_missing / n_rows, 2) if n_rows else 0.0,
            "sample_values": [_trunc(v) for v in s.dropna().unique()[:5]],
        }
        if kind == "numeric":
            info["stats"] = {
                "mean": round(float(s.mean()), 4),
                "std": round(float(s.std()), 4),
                "min": round(float(s.min()), 4),
                "p25": round(float(s.quantile(0.25)), 4),
                "median": round(float(s.quantile(0.5)), 4),
                "p75": round(float(s.quantile(0.75)), 4),
                "max": round(float(s.max()), 4),
            }
        # Value distribution (class balance) for low-cardinality columns.
        if kind in ("categorical", "boolean") or (kind == "numeric" and n_unique <= 20):
            info["top_values"] = _top_values(s, n_rows)
        columns.append(info)

    target_candidates = _target_candidates(df, columns)

    warnings: list[str] = []
    constant = [c["name"] for c in columns if c["n_unique"] <= 1]
    if constant:
        warnings.append(f"Constant columns (no signal): {', '.join(constant)}")
    id_like = [c["name"] for c in columns if c["kind"] == "id_like"]
    if id_like:
        warnings.append(
            f"ID-like columns (unique per row, will be excluded from features): {', '.join(id_like)}"
        )
    if n_rows < 500:
        warnings.append(f"Small dataset ({n_rows} rows): expect high metric variance.")
    for c in columns:
        if c["name"] in target_candidates and c.get("top_values"):
            majority = c["top_values"][0]
            if majority["pct"] > 90:
                warnings.append(
                    f"Class imbalance: '{c['name']}' majority value "
                    f"'{majority['value']}' covers {majority['pct']}% of rows."
                )

    return {
        "modality": "tabular",
        "n_rows": int(n_rows),
        "n_cols": int(n_cols),
        "sample_rows": _sample_rows(df),
        "columns": columns,
        "target_candidates": target_candidates,
        "warnings": warnings,
    }


def profile_csv(path: str) -> dict[str, Any]:
    return profile_dataframe(load_csv(path))


class TabularProfiler:
    modality = "tabular"
    extensions = (".csv",)

    def profile(self, path: str) -> dict[str, Any]:
        return profile_csv(path)


register(TabularProfiler())
