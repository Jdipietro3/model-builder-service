"""Tabular (CSV) profiling."""

import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from .base import register

SAMPLE_ROWS = 5
TOP_VALUES = 5
MAX_SAMPLE_COLS = 30  # cap sample_rows width for very wide datasets
MAX_CELL_CHARS = 40  # keep the profile token-compact
DATE_SAMPLE = 200  # non-null values sniffed when guessing a string date column
DATE_PARSE_THRESHOLD = 0.9  # fraction that must parse to call a column datetime

# Leakage-aware association scoring (item 1). Dependency-light: scipy.stats /
# numpy / pandas only, no model fits.
ASSOCIATION_ROW_CAP = 5000  # sample cap for speed on wide/tall datasets
ASSOCIATION_SKIP_KINDS = {"id_like", "text", "datetime"}
ASSOCIATION_LEAK_THRESHOLD = 0.9  # score at/above this surfaces a profile-level warning


def load_csv(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def _trunc(value: Any) -> str:
    s = str(value)
    return s if len(s) <= MAX_CELL_CHARS else s[: MAX_CELL_CHARS - 1] + "…"


def _looks_like_datetime(s: pd.Series) -> bool:
    """Cheap sniff for object columns that hold string dates (e.g. "2024-06-01").

    ``load_csv`` is a plain ``read_csv``, so date columns arrive as object dtype and
    would otherwise fall through to categorical/text/id_like and never reach the
    timeseries routing signal. We parse a small non-null sample and accept the column
    as datetime only if most values parse AND they are not plain numbers — a column of
    "1" / "2.5" must stay numeric-looking, not become a timestamp.
    """
    sample = s.dropna().head(DATE_SAMPLE)
    if sample.empty:
        return False
    # Guard: values that parse as plain numbers are not dates.
    numeric = pd.to_numeric(sample, errors="coerce")
    if numeric.notna().mean() >= DATE_PARSE_THRESHOLD:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return parsed.notna().mean() >= DATE_PARSE_THRESHOLD


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
    # String dates ("2024-06-01") classify as datetime before the categorical/
    # id_like/text fallthrough, so they surface in time_column_candidates.
    if _looks_like_datetime(s):
        return "datetime"
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


def _assoc_group(kind: str) -> str:
    """Coarse group used to pick an association method: numeric vs everything else
    (categorical/boolean are treated identically for association purposes)."""
    return "numeric" if kind == "numeric" else "categorical"


def _pearson_score(a: pd.Series, b: pd.Series) -> float:
    """|Pearson r| between two numeric series, guarding zero variance / tiny n."""
    try:
        paired = pd.DataFrame({"a": pd.to_numeric(a, errors="coerce"), "b": pd.to_numeric(b, errors="coerce")}).dropna()
        if len(paired) < 3 or paired["a"].std() == 0 or paired["b"].std() == 0:
            return 0.0
        r = paired["a"].corr(paired["b"])
        if pd.isna(r):
            return 0.0
        return float(min(abs(r), 1.0))
    except Exception:
        return 0.0


def _cramers_v_score(a: pd.Series, b: pd.Series) -> float:
    """Cramér's V between two categorical-like series via scipy's chi-square test."""
    try:
        paired = pd.DataFrame({"a": a, "b": b}).dropna()
        ct = pd.crosstab(paired["a"], paired["b"])
        if ct.shape[0] < 2 or ct.shape[1] < 2:
            return 0.0
        n = int(ct.to_numpy().sum())
        if n == 0:
            return 0.0
        chi2, _, _, _ = scipy_stats.chi2_contingency(ct)
        phi2 = chi2 / n
        denom = min(ct.shape[0] - 1, ct.shape[1] - 1)
        if denom <= 0:
            return 0.0
        v = (phi2 / denom) ** 0.5
        if not np.isfinite(v):
            return 0.0
        return float(min(v, 1.0))
    except Exception:
        return 0.0


def _correlation_ratio_score(categories: pd.Series, values: pd.Series) -> float:
    """Correlation ratio (eta): how much of numeric `values`'s variance is explained
    by grouping on `categories`. Used for numeric-vs-categorical associations
    regardless of which side is the target."""
    try:
        numeric_values = pd.to_numeric(values, errors="coerce")
        paired = pd.DataFrame({"cat": categories, "val": numeric_values}).dropna()
        if paired["cat"].nunique() < 2 or len(paired) < 3:
            return 0.0
        overall_mean = paired["val"].mean()
        ss_total = ((paired["val"] - overall_mean) ** 2).sum()
        if ss_total == 0:
            return 0.0
        ss_between = 0.0
        for _, group in paired.groupby("cat")["val"]:
            if len(group) == 0:
                continue
            ss_between += len(group) * (group.mean() - overall_mean) ** 2
        eta2 = max(ss_between / ss_total, 0.0)
        eta = eta2**0.5
        if not np.isfinite(eta):
            return 0.0
        return float(min(eta, 1.0))
    except Exception:
        return 0.0


def _target_associations(
    df: pd.DataFrame, columns: list[dict[str, Any]], target_candidates: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Model-free association of every usable feature against each of the top
    candidate targets — the earliest leakage signal in the pipeline. Row-sampled
    (<=ASSOCIATION_ROW_CAP) for speed; skips the target column itself and
    id_like/text/datetime features on either side."""
    if df.empty:
        return {}
    col_by_name = {c["name"]: c for c in columns}
    if len(df) > ASSOCIATION_ROW_CAP:
        sample = df.sample(n=ASSOCIATION_ROW_CAP, random_state=42)
    else:
        sample = df

    out: dict[str, list[dict[str, Any]]] = {}
    for target in target_candidates[:5]:
        target_info = col_by_name.get(target)
        if target_info is None or target_info["kind"] in ASSOCIATION_SKIP_KINDS:
            continue
        target_series = sample[target]
        target_group = _assoc_group(target_info["kind"])

        scored: list[dict[str, Any]] = []
        for c in columns:
            fname = c["name"]
            if fname == target or c["kind"] in ASSOCIATION_SKIP_KINDS:
                continue
            feature_series = sample[fname]
            feature_group = _assoc_group(c["kind"])
            if feature_group == "numeric" and target_group == "numeric":
                score, method = _pearson_score(feature_series, target_series), "pearson"
            elif feature_group == "categorical" and target_group == "categorical":
                score, method = _cramers_v_score(feature_series, target_series), "cramers_v"
            elif feature_group == "numeric" and target_group == "categorical":
                score, method = (
                    _correlation_ratio_score(target_series, feature_series),
                    "correlation_ratio",
                )
            else:  # feature categorical, target numeric
                score, method = (
                    _correlation_ratio_score(feature_series, target_series),
                    "correlation_ratio",
                )
            scored.append({"feature": fname, "score": round(float(score), 4), "method": method})

        scored.sort(key=lambda d: -d["score"])
        out[target] = scored
    return out


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
    # Names of datetime columns — a reserved selection signal for future
    # timeseries routing (e.g. the forecasting runner's time_column).
    time_column_candidates = [c["name"] for c in columns if c["kind"] == "datetime"]
    target_associations = _target_associations(df, columns, target_candidates)

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
    for target, assocs in target_associations.items():
        for a in assocs:
            if a["score"] >= ASSOCIATION_LEAK_THRESHOLD:
                warnings.append(
                    f"'{a['feature']}' is near-perfectly associated with candidate target "
                    f"'{target}' (score {a['score']:.2f}, {a['method']}) — possible leakage."
                )

    return {
        "data_shape": "tabular",
        "n_rows": int(n_rows),
        "n_cols": int(n_cols),
        "sample_rows": _sample_rows(df),
        "columns": columns,
        "target_candidates": target_candidates,
        "time_column_candidates": time_column_candidates,
        "target_associations": target_associations,
        "warnings": warnings,
    }


def profile_csv(path: str) -> dict[str, Any]:
    return profile_dataframe(load_csv(path))


class TabularProfiler:
    data_shape = "tabular"
    extensions = (".csv",)

    def profile(self, path: str) -> dict[str, Any]:
        return profile_csv(path)


register(TabularProfiler())
