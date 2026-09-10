"""Declarative preprocessing / feature-engineering recipes (Phase 1).

A *recipe* is a list of small, named steps (``{"op", "columns", "params",
"description"}``) that together describe how raw tabular columns become the
matrix a model trains on. Two recipes matter structurally:

- :func:`legacy_recipe` reproduces today's hard-coded
  ``pipeline/supervised.py`` behavior (``select_features`` + ``build_pipeline``)
  exactly, step for step. It is what runs when a plan's ``preprocessing`` is
  ``None`` — the golden path that must never change results.
- :func:`default_recipe` is the "senior engineer baseline": the legacy steps
  plus a handful of profile-driven upgrades (datetime expansion, high-
  cardinality encoding, skew correction, class balancing). It is what
  ``propose_plan`` stores on a plan for the user/LLM to edit.

Everything else (:func:`resolve_recipe`, :func:`compile_recipe`,
:func:`preprocessing_applied`, :func:`preview_recipe`) turns a recipe into a
fitted-and-inspectable sklearn ``Pipeline``.

Portability constraint: this module is copied verbatim into every training
bundle (see ``ml/artifacts.py``) and must import standalone there (no ``app.*``
imports) — it depends only on sklearn / numpy / pandas / imblearn / pydantic.
"""

from __future__ import annotations

import importlib
import inspect
import itertools
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    LabelEncoder,
    OneHotEncoder,
    OrdinalEncoder,
    PowerTransformer,
    StandardScaler,
)

# A bundle's copy of this module is imported as top-level `recipe`, but the
# classes pickled into model.joblib were pickled under `app.ml.recipe`
# (joblib/pickle store the qualified module path of each class). Aliasing
# ourselves under that name — without clobbering the real package inside the
# service, where `app.ml.recipe` already refers to this exact module object —
# lets joblib.load resolve those classes from a plain `python train.py` run in
# an extracted bundle with no `app` package on sys.path at all.
sys.modules.setdefault("app.ml.recipe", sys.modules[__name__])


def _import_class(path: str):
    """Standalone class resolver — deliberately does not depend on
    ``registry.loader.resolve_model_class`` so this module has no app.* import."""
    module_path, class_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), class_name)


# Friendly metric name -> sklearn scoring string. Mirrors
# ``pipeline/supervised.METRIC_SCORING`` (kept in sync manually; small and stable).
METRIC_SCORING = {
    "roc_auc": "roc_auc",
    "pr_auc": "average_precision",
    "f1": "f1",
    "f1_macro": "f1_macro",
    "accuracy": "accuracy",
    "balanced_accuracy": "balanced_accuracy",
    "r2": "r2",
    "mae": "neg_mean_absolute_error",
    "rmse": "neg_root_mean_squared_error",
}

AUTO_DROP_KINDS = {"id_like", "text", "datetime"}


# --------------------------------------------------------------------------- #
# Custom, picklable, DataFrame-level transformers                             #
# --------------------------------------------------------------------------- #


class DatetimeExpandTransformer(BaseEstimator, TransformerMixin):
    """Expands datetime-kind columns into calendar features. ``elapsed_days``
    is relative to each column's fit-time minimum (serve-safe: no leakage of
    future dates, just a fixed offset learned at fit time)."""

    def __init__(self, columns: list[str], features: list[str]):
        self.columns = columns
        self.features = features

    def fit(self, X, y=None):
        self.mins_ = {}
        for c in self.columns:
            s = pd.to_datetime(X[c], errors="coerce")
            self.mins_[c] = s.min()
        return self

    def transform(self, X):
        X = X.copy()
        for c in self.columns:
            s = pd.to_datetime(X[c], errors="coerce")
            if "year" in self.features:
                X[f"{c}_year"] = s.dt.year.astype("float64")
            if "month" in self.features:
                X[f"{c}_month"] = s.dt.month.astype("float64")
            if "day" in self.features:
                X[f"{c}_day"] = s.dt.day.astype("float64")
            if "dayofweek" in self.features:
                X[f"{c}_dayofweek"] = s.dt.dayofweek.astype("float64")
            if "hour" in self.features:
                X[f"{c}_hour"] = s.dt.hour.astype("float64")
            if "is_weekend" in self.features:
                X[f"{c}_is_weekend"] = (s.dt.dayofweek >= 5).astype("float64")
            if "elapsed_days" in self.features:
                base = self.mins_.get(c)
                X[f"{c}_elapsed_days"] = (s - base).dt.days.astype("float64")
        return X

    @staticmethod
    def output_names(columns: list[str], features: list[str]) -> list[str]:
        return [f"{c}_{f}" for c in columns for f in features]


class ArithmeticTransformer(BaseEstimator, TransformerMixin):
    """Bounded arithmetic combination of two columns: ratio/diff/product/sum."""

    def __init__(self, expression: str, left: str, right: str, name: str):
        self.expression = expression
        self.left = left
        self.right = right
        self.name = name

    def fit(self, X, y=None):
        self.fitted_ = True
        return self

    def transform(self, X):
        X = X.copy()
        a = pd.to_numeric(X[self.left], errors="coerce")
        b = pd.to_numeric(X[self.right], errors="coerce")
        if self.expression == "ratio":
            safe_b = b.replace(0, np.nan)
            val = a / safe_b
        elif self.expression == "diff":
            val = a - b
        elif self.expression == "product":
            val = a * b
        elif self.expression == "sum":
            val = a + b
        else:
            raise ValueError(f"Unknown arithmetic expression '{self.expression}'")
        X[self.name] = val.astype("float64")
        return X


class GroupAggregateTransformer(BaseEstimator, TransformerMixin):
    """Fits per-group aggregate stats on train, merges them in on transform.
    A missing group at serve time falls back to the global aggregate (serve-safe:
    never raises on an unseen key)."""

    def __init__(self, key: str, column: str, agg: str, name: str):
        self.key = key
        self.column = column
        self.agg = agg
        self.name = name

    def fit(self, X, y=None):
        if self.agg == "count":
            stat = X.groupby(self.key)[self.column].count()
            self.global_ = float(X[self.column].count())
        else:
            values = pd.to_numeric(X[self.column], errors="coerce")
            tmp = pd.DataFrame({self.key: X[self.key], "_v": values})
            stat = tmp.groupby(self.key)["_v"].agg(self.agg)
            self.global_ = float(values.agg(self.agg))
        self.map_ = stat.to_dict()
        return self

    def transform(self, X):
        X = X.copy()
        mapped = X[self.key].map(self.map_)
        X[self.name] = pd.to_numeric(mapped, errors="coerce").fillna(self.global_).astype("float64")
        return X


class LogTransformTransformer(BaseEstimator, TransformerMixin):
    """np.log1p on non-negative numerics (clipped at 0 first), in place."""

    def __init__(self, columns: list[str]):
        self.columns = columns

    def fit(self, X, y=None):
        self.fitted_ = True
        return self

    def transform(self, X):
        X = X.copy()
        for c in self.columns:
            v = pd.to_numeric(X[c], errors="coerce").clip(lower=0)
            X[c] = np.log1p(v)
        return X


class PowerTransformStep(BaseEstimator, TransformerMixin):
    """Wraps sklearn's PowerTransformer over a fixed column subset, in place."""

    def __init__(self, columns: list[str], method: str = "yeo-johnson"):
        self.columns = columns
        self.method = method

    def fit(self, X, y=None):
        self.pt_ = PowerTransformer(method=self.method)
        arr = X[self.columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
        self.pt_.fit(arr)
        return self

    def transform(self, X):
        X = X.copy()
        arr = X[self.columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
        out = self.pt_.transform(arr)
        for i, c in enumerate(self.columns):
            X[c] = out[:, i]
        return X


class ClipOutliersTransformer(BaseEstimator, TransformerMixin):
    """Per-column quantile clipping, bounds learned on train only."""

    def __init__(self, columns: list[str], lower_q: float = 0.01, upper_q: float = 0.99):
        self.columns = columns
        self.lower_q = lower_q
        self.upper_q = upper_q

    def fit(self, X, y=None):
        self.bounds_ = {}
        for c in self.columns:
            v = pd.to_numeric(X[c], errors="coerce")
            self.bounds_[c] = (v.quantile(self.lower_q), v.quantile(self.upper_q))
        return self

    def transform(self, X):
        X = X.copy()
        for c in self.columns:
            lo, hi = self.bounds_[c]
            X[c] = pd.to_numeric(X[c], errors="coerce").clip(lower=lo, upper=hi)
        return X


class BinTransformStep(BaseEstimator, TransformerMixin):
    """KBinsDiscretizer wrapper, in place. ``encode="onehot"`` writes string bin
    labels ("bin0".."binN") so the column naturally routes into the categorical
    ColumnTransformer branch (and gets one-hot encoded there) instead of needing
    fit-time-only derived column names."""

    def __init__(
        self, columns: list[str], n_bins: int = 5, strategy: str = "quantile", encode: str = "ordinal"
    ):
        self.columns = columns
        self.n_bins = n_bins
        self.strategy = strategy
        self.encode = encode

    def fit(self, X, y=None):
        from sklearn.preprocessing import KBinsDiscretizer

        self.kbd_ = KBinsDiscretizer(n_bins=self.n_bins, strategy=self.strategy, encode="ordinal")
        arr = X[self.columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
        self.kbd_.fit(arr)
        return self

    def transform(self, X):
        X = X.copy()
        arr = X[self.columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
        out = self.kbd_.transform(arr)
        for i, c in enumerate(self.columns):
            if self.encode == "onehot":
                X[c] = [f"bin{int(v)}" for v in out[:, i]]
            else:
                X[c] = out[:, i].astype("float64")
        return X


class InteractionsTransformer(BaseEstimator, TransformerMixin):
    """Pairwise products of a bounded numeric column set (interaction_only,
    degree 2). Column names are computed deterministically from ``columns``
    alone (no fit-time dependency), so callers can wire the output names into a
    static ColumnTransformer before the pipeline is ever fit."""

    def __init__(self, columns: list[str], degree: int = 2):
        self.columns = columns
        self.degree = degree

    def fit(self, X, y=None):
        self.fitted_ = True
        return self

    def transform(self, X):
        X = X.copy()
        for a, b in itertools.combinations(self.columns, 2):
            va = pd.to_numeric(X[a], errors="coerce")
            vb = pd.to_numeric(X[b], errors="coerce")
            X[f"{a}_x_{b}"] = va * vb
        return X

    def output_names(self) -> list[str]:
        return [f"{a}_x_{b}" for a, b in itertools.combinations(self.columns, 2)]


class FrequencyEncoder(BaseEstimator, TransformerMixin):
    """Maps each categorical value to its training-set frequency (fraction of
    rows). Unseen values at transform time map to 0.0."""

    def __init__(self, columns: list[str] | None = None):
        self.columns = columns

    def _as_dataframe(self, X) -> pd.DataFrame:
        # Upstream steps in a ColumnTransformer sub-pipeline (e.g. SimpleImputer)
        # commonly return a bare ndarray rather than preserving the DataFrame, so
        # this must tolerate either input shape.
        if isinstance(X, pd.DataFrame):
            return X
        arr = np.asarray(X)
        cols = self.columns if self.columns is not None else [f"col{i}" for i in range(arr.shape[1])]
        return pd.DataFrame(arr, columns=cols)

    def fit(self, X, y=None):
        df = self._as_dataframe(X)
        self._cols_ = self.columns if self.columns is not None else list(df.columns)
        n = len(df)
        self.maps_ = {}
        for c in self._cols_:
            counts = df[c].astype(str).value_counts()
            self.maps_[c] = (counts / n).to_dict() if n else {}
        return self

    def transform(self, X):
        df = self._as_dataframe(X)
        out = np.zeros((len(df), len(self._cols_)))
        for i, c in enumerate(self._cols_):
            vals = df[c].astype(str)
            out[:, i] = vals.map(self.maps_[c]).fillna(0.0).to_numpy()
        return out

    def get_feature_names_out(self, input_features=None):
        return np.array([f"{c}_freq" for c in self._cols_])


# --------------------------------------------------------------------------- #
# Op registry                                                                  #
# --------------------------------------------------------------------------- #


class DropParams(BaseModel):
    reason: str | None = None


class ImputeParams(BaseModel):
    group: Literal["numeric", "categorical"] = "numeric"
    strategy: Literal["mean", "median", "most_frequent", "constant", "iterative", "knn"] = "median"
    add_indicator: bool = False
    fill_value: Any = None


class ScaleParams(BaseModel):
    method: Literal["standard", "robust", "minmax", "quantile"] = "standard"


class EncodeParams(BaseModel):
    method: Literal["onehot", "ordinal", "target", "frequency"] = "onehot"
    max_categories: int = 30


class DatetimeExpandParams(BaseModel):
    features: list[Literal["year", "month", "day", "dayofweek", "hour", "is_weekend", "elapsed_days"]] = (
        Field(default_factory=lambda: ["year", "month", "day", "dayofweek", "hour", "is_weekend", "elapsed_days"])
    )


class LogTransformParams(BaseModel):
    pass


class PowerParams(BaseModel):
    method: Literal["yeo-johnson", "box-cox"] = "yeo-johnson"


class ClipOutliersParams(BaseModel):
    lower_q: float = 0.01
    upper_q: float = 0.99


class BinParams(BaseModel):
    n_bins: int = 5
    strategy: Literal["quantile", "uniform", "kmeans"] = "quantile"
    encode: Literal["ordinal", "onehot"] = "ordinal"


class ArithmeticParams(BaseModel):
    expression: Literal["ratio", "diff", "product", "sum"]
    left: str
    right: str
    name: str | None = None


class InteractionsParams(BaseModel):
    degree: int = 2


class GroupAggregateParams(BaseModel):
    key: str
    column: str
    agg: Literal["mean", "median", "count", "std", "max", "min"] = "mean"
    name: str | None = None


class SelectParams(BaseModel):
    method: Literal["variance", "kbest", "from_model"] = "kbest"
    k: int | None = None
    threshold: float | None = None


class ClassBalanceParams(BaseModel):
    method: Literal["class_weight", "smote"] = "class_weight"


class TargetTransformParams(BaseModel):
    method: Literal["log1p"] = "log1p"


CLASSIFICATION_TASK_TYPES = ("binary_classification", "multiclass_classification")


@dataclass
class OpInfo:
    params_model: type[BaseModel]
    description: str
    stage: str  # "drop" | "feature" | "preprocess" | "select" | "balance" | "target"
    task_types: tuple[str, ...] | None = None  # None = all task types
    needs_target: bool = False


OPS: dict[str, OpInfo] = {
    "drop": OpInfo(DropParams, "Removes columns from the feature set.", "drop"),
    "impute": OpInfo(ImputeParams, "Fills missing values.", "preprocess"),
    "scale": OpInfo(ScaleParams, "Rescales numeric columns.", "preprocess"),
    "encode": OpInfo(EncodeParams, "Encodes categorical columns as numbers.", "preprocess", needs_target=False),
    "datetime_expand": OpInfo(DatetimeExpandParams, "Expands a date/time column into calendar features.", "feature"),
    "log_transform": OpInfo(LogTransformParams, "Applies log1p to reduce right-skew.", "feature"),
    "power": OpInfo(PowerParams, "Applies a power transform to make a distribution more Gaussian-like.", "feature"),
    "clip_outliers": OpInfo(ClipOutliersParams, "Clips extreme values to a quantile range.", "feature"),
    "bin": OpInfo(BinParams, "Buckets a numeric column into discrete bins.", "feature"),
    "arithmetic": OpInfo(ArithmeticParams, "Derives a new column from two others.", "feature"),
    "interactions": OpInfo(InteractionsParams, "Adds pairwise interaction terms.", "feature"),
    "group_aggregate": OpInfo(GroupAggregateParams, "Adds a group-level aggregate statistic as a feature.", "feature"),
    "select": OpInfo(SelectParams, "Selects a subset of the engineered features.", "select"),
    "class_balance": OpInfo(
        ClassBalanceParams, "Corrects for class imbalance.", "balance", task_types=CLASSIFICATION_TASK_TYPES
    ),
    "target_transform": OpInfo(
        TargetTransformParams, "Transforms the regression target before fitting.", "target", task_types=("regression",)
    ),
}


def describe_step(step: dict, profile: dict | None = None) -> str:
    """Plain-English, one-sentence description of a resolved step."""
    op = step.get("op")
    cols = step.get("columns") or []
    params = step.get("params") or {}
    col_txt = ", ".join(cols) if cols else "the auto-selected columns"

    if op == "drop":
        reason = params.get("reason") or "not useful for modeling"
        return f"Drop {col_txt} ({reason})."
    if op == "impute":
        group = params.get("group", "numeric")
        strategy = params.get("strategy", "median")
        target_txt = col_txt if cols else f"{group} columns"
        return f"Fill missing values in {target_txt} using {strategy}."
    if op == "scale":
        return f"Scale numeric columns with {params.get('method', 'standard')} scaling."
    if op == "encode":
        method = params.get("method", "onehot")
        target_txt = col_txt if cols else "categorical columns"
        return f"Encode {target_txt} using {method} encoding."
    if op == "datetime_expand":
        feats = params.get("features") or []
        return f"Expand {col_txt} into calendar features ({', '.join(feats) or 'defaults'})."
    if op == "log_transform":
        return f"Apply log1p to {col_txt} to reduce skew."
    if op == "power":
        return f"Apply a {params.get('method', 'yeo-johnson')} power transform to {col_txt}."
    if op == "clip_outliers":
        return f"Clip {col_txt} to the [{params.get('lower_q', 0.01)}, {params.get('upper_q', 0.99)}] quantile range."
    if op == "bin":
        return f"Bucket {col_txt} into {params.get('n_bins', 5)} bins ({params.get('strategy', 'quantile')})."
    if op == "arithmetic":
        return f"Derive {params.get('name') or 'a new column'} as {params.get('left')} {params.get('expression')} {params.get('right')}."
    if op == "interactions":
        return f"Add pairwise interaction terms among {col_txt}."
    if op == "group_aggregate":
        return (
            f"Add {params.get('agg', 'mean')} of {params.get('column')} grouped by "
            f"{params.get('key')} as {params.get('name') or 'a new column'}."
        )
    if op == "select":
        return f"Select features using {params.get('method', 'kbest')}."
    if op == "class_balance":
        return f"Correct class imbalance using {params.get('method', 'class_weight')}."
    if op == "target_transform":
        return f"Transform the target using {params.get('method', 'log1p')} before fitting."
    return f"Apply {op}."


# --------------------------------------------------------------------------- #
# legacy_recipe / default_recipe                                              #
# --------------------------------------------------------------------------- #


def _drop_groups(profile: dict, plan: dict) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Shared excluded/constant partitioning for legacy_recipe and default_recipe.
    Returns (excluded_cols, constant_cols, kind_cols) where kind_cols groups the
    remaining auto-drop-kind columns by kind (id_like/text/datetime)."""
    target = plan.get("target_column")
    excluded = set(plan.get("excluded_columns") or [])
    excluded_cols, constant_cols = [], []
    kind_cols: dict[str, list[str]] = {}
    for c in profile["columns"]:
        name = c["name"]
        if name == target:
            continue
        if name in excluded:
            excluded_cols.append(name)
        elif c["n_unique"] <= 1:
            constant_cols.append(name)
        elif c["kind"] in AUTO_DROP_KINDS:
            kind_cols.setdefault(c["kind"], []).append(name)
    return excluded_cols, constant_cols, kind_cols


def legacy_recipe(profile: dict, spec: dict, plan: dict) -> list[dict]:
    """Reproduces today's ``select_features`` + ``build_pipeline`` exactly, as
    recipe steps. This is the golden path: a plan with no ``preprocessing`` runs
    this recipe."""
    excluded_cols, constant_cols, kind_cols = _drop_groups(profile, plan)
    steps: list[dict] = []
    if excluded_cols:
        steps.append({"op": "drop", "columns": excluded_cols, "params": {"reason": "excluded in plan"}})
    if constant_cols:
        steps.append({"op": "drop", "columns": constant_cols, "params": {"reason": "constant column"}})
    for kind, cols in kind_cols.items():
        steps.append(
            {"op": "drop", "columns": cols, "params": {"reason": f"{kind} column (unsupported in v1)"}}
        )

    pre = spec["preprocessing"]
    steps.append(
        {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": pre["numeric"]["impute"]}}
    )
    if pre["numeric"].get("scale"):
        steps.append({"op": "scale", "columns": [], "params": {"method": "standard"}})
    steps.append(
        {
            "op": "impute",
            "columns": [],
            "params": {"group": "categorical", "strategy": pre["categorical"]["impute"]},
        }
    )
    steps.append({"op": "encode", "columns": [], "params": {"method": "onehot", "max_categories": 30}})
    return steps


def default_recipe(profile: dict, spec: dict, plan: dict) -> list[dict]:
    """The senior-engineer baseline stored on a proposed plan: legacy steps plus
    profile-driven upgrades. Respects ``spec["feature_ops_allowed"]`` when set."""
    target = plan.get("target_column")
    excluded = set(plan.get("excluded_columns") or [])
    task_type = plan.get("task_type")
    allowed = spec.get("feature_ops_allowed")

    def op_allowed(op: str) -> bool:
        return allowed is None or op in allowed

    excluded_cols, constant_cols, kind_cols = _drop_groups(profile, plan)
    steps: list[dict] = []
    if excluded_cols:
        steps.append({"op": "drop", "columns": excluded_cols, "params": {"reason": "excluded in plan"}})
    if constant_cols:
        steps.append({"op": "drop", "columns": constant_cols, "params": {"reason": "constant column"}})

    id_like_cols = kind_cols.get("id_like", [])
    text_cols = kind_cols.get("text", [])
    datetime_cols = kind_cols.get("datetime", [])
    if id_like_cols:
        steps.append(
            {"op": "drop", "columns": id_like_cols, "params": {"reason": "id_like column (unsupported in v1)"}}
        )
    if text_cols:
        steps.append(
            {"op": "drop", "columns": text_cols, "params": {"reason": "text column (text ops arrive in Phase 5)"}}
        )
    if datetime_cols:
        if op_allowed("datetime_expand"):
            # Date-only columns (no clock component in any sampled value) get no
            # `hour` feature: it would be a constant zero column.
            has_clock = any(
                ":" in str(v)
                for c in profile["columns"]
                if c["name"] in datetime_cols
                for v in (c.get("sample_values") or [])
            )
            feats = ["year", "month", "day", "dayofweek", "is_weekend", "elapsed_days"]
            if has_clock:
                feats.insert(4, "hour")
            steps.append({"op": "datetime_expand", "columns": datetime_cols, "params": {"features": feats}})
        else:
            steps.append(
                {"op": "drop", "columns": datetime_cols, "params": {"reason": "datetime column (unsupported in v1)"}}
            )

    pre = spec["preprocessing"]
    is_non_tree = bool(pre["numeric"].get("scale")) or op_allowed("scale")

    log_cols: list[str] = []
    if op_allowed("log_transform") and is_non_tree:
        for c in profile["columns"]:
            name = c["name"]
            if name == target or name in excluded or c["kind"] != "numeric":
                continue
            stats = c.get("stats") or {}
            skew = stats.get("skewness")
            mn = stats.get("min")
            if skew is not None and abs(skew) > 2 and mn is not None and mn >= 0:
                log_cols.append(name)
    if log_cols:
        steps.append({"op": "log_transform", "columns": log_cols, "params": {}})

    steps.append(
        {"op": "impute", "columns": [], "params": {"group": "numeric", "strategy": pre["numeric"]["impute"]}}
    )
    if pre["numeric"].get("scale"):
        steps.append({"op": "scale", "columns": [], "params": {"method": "standard"}})
    steps.append(
        {"op": "impute", "columns": [], "params": {"group": "categorical", "strategy": pre["categorical"]["impute"]}}
    )

    high_card_cols: list[str] = []
    for c in profile["columns"]:
        name = c["name"]
        if name == target or name in excluded:
            continue
        if c["kind"] in ("categorical", "boolean") and c["n_unique"] > 30:
            high_card_cols.append(name)
    if high_card_cols and op_allowed("encode"):
        method = "target" if task_type in (*CLASSIFICATION_TASK_TYPES, "regression") else "frequency"
        steps.append({"op": "encode", "columns": high_card_cols, "params": {"method": method}})
    steps.append({"op": "encode", "columns": [], "params": {"method": "onehot", "max_categories": 30}})

    if task_type in CLASSIFICATION_TASK_TYPES and op_allowed("class_balance"):
        target_info = next((c for c in profile["columns"] if c["name"] == target), None)
        top_values = (target_info or {}).get("top_values") or []
        if top_values:
            minority_pct = min(tv["pct"] for tv in top_values)
            if minority_pct < 20:
                model_supports_class_weight = True
                try:
                    model_cls = _import_class(spec["model"]["class"])
                    sig = inspect.signature(model_cls.__init__)
                    model_supports_class_weight = "class_weight" in sig.parameters
                except Exception:
                    model_supports_class_weight = True
                if model_supports_class_weight:
                    steps.append({"op": "class_balance", "columns": [], "params": {"method": "class_weight"}})

    return steps


# --------------------------------------------------------------------------- #
# resolve_recipe                                                              #
# --------------------------------------------------------------------------- #


def resolve_recipe(plan: dict, profile: dict, spec: dict) -> list[dict]:
    """Resolves ``plan["preprocessing"]`` (or the default recipe) into a fully
    validated, described list of steps. Raises ValueError with a readable
    message on any problem."""
    raw_steps = plan.get("preprocessing")
    if raw_steps is None:
        raw_steps = default_recipe(profile, spec, plan)
    elif raw_steps == []:
        raise ValueError("preprocessing: [] is invalid; use null for the default recipe")

    allowed = spec.get("feature_ops_allowed")
    column_names = {c["name"] for c in profile["columns"]}
    task_type = plan.get("task_type")

    resolved: list[dict] = []
    for raw in raw_steps:
        step = dict(raw)
        op = step.get("op")
        if op not in OPS:
            raise ValueError(f"Unknown preprocessing op '{op}' (known ops: {', '.join(sorted(OPS))})")
        op_info = OPS[op]

        if allowed is not None and op not in allowed:
            raise ValueError(
                f"Op '{op}' is not allowed for this methodology (allowed: {', '.join(sorted(allowed))})"
            )
        if op_info.task_types is not None and task_type not in op_info.task_types:
            raise ValueError(
                f"Op '{op}' is only valid for task type(s) {', '.join(op_info.task_types)}, got '{task_type}'"
            )

        cols = step.get("columns") or []
        unknown = [c for c in cols if c not in column_names]
        if unknown:
            raise ValueError(f"Step '{op}' references column(s) not in the dataset: {', '.join(unknown)}")

        params_in = step.get("params") or {}
        try:
            parsed = op_info.params_model(**params_in)
        except ValidationError as e:
            raise ValueError(f"Invalid params for op '{op}': {e}") from e
        params = parsed.model_dump()

        # Statically-checkable column references embedded in params (not `columns`).
        if op == "arithmetic":
            for key in ("left", "right"):
                if params[key] not in column_names:
                    raise ValueError(f"Step 'arithmetic' references unknown column '{params[key]}'")
        if op == "group_aggregate":
            for key in ("key", "column"):
                if params[key] not in column_names:
                    raise ValueError(f"Step 'group_aggregate' references unknown column '{params[key]}'")

        desc = step.get("description") or describe_step({"op": op, "columns": cols, "params": params}, profile)
        resolved.append({"op": op, "columns": cols, "params": params, "description": desc})

    return resolved


# --------------------------------------------------------------------------- #
# compile_recipe                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class RecipeInfo:
    feature_columns: list[str]
    numeric_columns: list[str]
    categorical_columns: list[str]
    dropped: list[dict]
    model_param_prefix: str = "model__"
    uses_imblearn: bool = False


def _build_imputer(strategy: str, add_indicator: bool = False, fill_value: Any = None):
    if strategy == "iterative":
        from sklearn.experimental import enable_iterative_imputer  # noqa: F401
        from sklearn.impute import IterativeImputer

        return IterativeImputer(random_state=42, add_indicator=add_indicator)
    if strategy == "knn":
        from sklearn.impute import KNNImputer

        return KNNImputer(add_indicator=add_indicator)
    kwargs: dict[str, Any] = {"strategy": strategy, "add_indicator": add_indicator}
    if strategy == "constant":
        kwargs["fill_value"] = fill_value
    return SimpleImputer(**kwargs)


def _build_scaler(method: str):
    if method == "standard":
        return StandardScaler()
    if method == "robust":
        from sklearn.preprocessing import RobustScaler

        return RobustScaler()
    if method == "minmax":
        from sklearn.preprocessing import MinMaxScaler

        return MinMaxScaler()
    if method == "quantile":
        from sklearn.preprocessing import QuantileTransformer

        return QuantileTransformer(random_state=42)
    raise ValueError(f"Unknown scale method '{method}'")


def _build_encoder(method: str, max_categories: int = 30):
    if method == "onehot":
        return OneHotEncoder(handle_unknown="ignore", max_categories=max_categories)
    if method == "ordinal":
        return OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    if method == "target":
        from sklearn.preprocessing import TargetEncoder

        return TargetEncoder(random_state=42)
    if method == "frequency":
        return FrequencyEncoder()
    raise ValueError(f"Unknown encode method '{method}'")


def _build_selector(params: dict, task_type: str):
    method = params.get("method", "kbest")
    if method == "variance":
        from sklearn.feature_selection import VarianceThreshold

        return VarianceThreshold(threshold=params.get("threshold") or 0.0)
    if method == "kbest":
        from sklearn.feature_selection import SelectKBest, mutual_info_classif, mutual_info_regression

        score_func = mutual_info_regression if task_type == "regression" else mutual_info_classif
        return SelectKBest(score_func=score_func, k=params.get("k") or 10)
    if method == "from_model":
        from sklearn.feature_selection import SelectFromModel

        try:
            if task_type == "regression":
                from lightgbm import LGBMRegressor as _Est
            else:
                from lightgbm import LGBMClassifier as _Est
            est = _Est(n_estimators=100, random_state=42, verbosity=-1)
        except Exception:
            if task_type == "regression":
                from sklearn.ensemble import RandomForestRegressor as _Est
            else:
                from sklearn.ensemble import RandomForestClassifier as _Est
            est = _Est(n_estimators=100, random_state=42)
        return SelectFromModel(est, threshold=params.get("threshold"))
    raise ValueError(f"Unknown select method '{method}'")


_FEATURE_OPS = {
    "datetime_expand",
    "arithmetic",
    "group_aggregate",
    "log_transform",
    "power",
    "clip_outliers",
    "bin",
    "interactions",
}


def compile_recipe(recipe: list[dict], profile: dict, spec: dict, plan: dict) -> tuple[Any, RecipeInfo]:
    """Builds the full sklearn ``Pipeline`` (feature engineering -> preprocess ->
    optional select -> model) for a resolved recipe."""
    col_by_name = {c["name"]: c for c in profile["columns"]}
    target = plan.get("target_column")
    task_type = plan.get("task_type")
    is_classification = task_type != "regression"

    def kind_of(name: str) -> str | None:
        info = col_by_name.get(name)
        return info["kind"] if info else None

    # ---- drop resolution: profile order, first-declaring-step wins per column ----
    drop_reason: dict[str, str] = {}
    for step in recipe:
        if step["op"] == "drop":
            reason = step["params"].get("reason") or "dropped"
            for c in step["columns"]:
                drop_reason.setdefault(c, reason)
    dropped = [
        {"name": c["name"], "reason": drop_reason[c["name"]]}
        for c in profile["columns"]
        if c["name"] in drop_reason
    ]
    dropped_names = set(drop_reason)
    kept = {c["name"] for c in profile["columns"] if c["name"] != target and c["name"] not in dropped_names}

    # ---- feature-stage transformers (sequential, DataFrame -> DataFrame) ----
    feature_steps: list[tuple[str, Any]] = []
    derived_numeric: list[str] = []
    bin_onehot_cols: set[str] = set()

    for i, step in enumerate(recipe):
        op = step["op"]
        if op not in _FEATURE_OPS:
            continue
        params = step["params"]
        cols = step["columns"]
        numeric_kept = [c["name"] for c in profile["columns"] if c["name"] in kept and kind_of(c["name"]) == "numeric"]

        if op == "datetime_expand":
            use_cols = cols or [c["name"] for c in profile["columns"] if c["name"] in kept and kind_of(c["name"]) == "datetime"]
            feats = params.get("features") or [
                "year", "month", "day", "dayofweek", "hour", "is_weekend", "elapsed_days"
            ]
            feature_steps.append((f"datetime_expand_{i}", DatetimeExpandTransformer(use_cols, feats)))
            derived_numeric.extend(DatetimeExpandTransformer.output_names(use_cols, feats))
        elif op == "arithmetic":
            name = params.get("name") or f"{params['left']}_{params['expression']}_{params['right']}"
            feature_steps.append(
                (f"arithmetic_{i}", ArithmeticTransformer(params["expression"], params["left"], params["right"], name))
            )
            derived_numeric.append(name)
        elif op == "group_aggregate":
            name = params.get("name") or f"{params['column']}_{params['agg']}_by_{params['key']}"
            feature_steps.append(
                (f"group_aggregate_{i}", GroupAggregateTransformer(params["key"], params["column"], params["agg"], name))
            )
            derived_numeric.append(name)
        elif op == "log_transform":
            use_cols = cols or numeric_kept
            feature_steps.append((f"log_transform_{i}", LogTransformTransformer(use_cols)))
        elif op == "power":
            use_cols = cols or numeric_kept
            feature_steps.append((f"power_{i}", PowerTransformStep(use_cols, params.get("method", "yeo-johnson"))))
        elif op == "clip_outliers":
            use_cols = cols or numeric_kept
            feature_steps.append(
                (f"clip_outliers_{i}", ClipOutliersTransformer(use_cols, params.get("lower_q", 0.01), params.get("upper_q", 0.99)))
            )
        elif op == "bin":
            use_cols = cols or numeric_kept
            enc = params.get("encode", "ordinal")
            feature_steps.append(
                (f"bin_{i}", BinTransformStep(use_cols, params.get("n_bins", 5), params.get("strategy", "quantile"), enc))
            )
            if enc == "onehot":
                bin_onehot_cols.update(use_cols)
        elif op == "interactions":
            use_cols = (cols or numeric_kept)[:8]
            tr = InteractionsTransformer(use_cols, params.get("degree", 2))
            feature_steps.append((f"interactions_{i}", tr))
            derived_numeric.extend(tr.output_names())

    # ---- explicit + default preprocess-stage steps ----
    numeric_impute_step = next(
        (s for s in recipe if s["op"] == "impute" and s["params"].get("group") == "numeric"), None
    )
    categorical_impute_step = next(
        (s for s in recipe if s["op"] == "impute" and s["params"].get("group") == "categorical"), None
    )
    scale_step = next((s for s in recipe if s["op"] == "scale"), None)
    default_encode_step = next((s for s in recipe if s["op"] == "encode" and not s["columns"]), None)
    explicit_encode_steps = [s for s in recipe if s["op"] == "encode" and s["columns"]]
    explicit_encoded: set[str] = set()
    for s in explicit_encode_steps:
        explicit_encoded.update(s["columns"])

    raw_numeric_cols = [c["name"] for c in profile["columns"] if c["name"] in kept and kind_of(c["name"]) == "numeric"]
    raw_categorical_cols = [
        c["name"] for c in profile["columns"] if c["name"] in kept and kind_of(c["name"]) in ("categorical", "boolean")
    ]
    other_kept = [
        c["name"]
        for c in profile["columns"]
        if c["name"] in kept and kind_of(c["name"]) not in ("numeric", "categorical", "boolean")
    ]
    feature_columns = raw_numeric_cols + raw_categorical_cols + other_kept

    numeric_group = [c for c in raw_numeric_cols if c not in bin_onehot_cols] + derived_numeric
    categorical_group = [c for c in raw_categorical_cols if c not in explicit_encoded] + [
        c for c in bin_onehot_cols if c not in explicit_encoded
    ]

    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric_group:
        strategy = numeric_impute_step["params"]["strategy"] if numeric_impute_step else "median"
        add_ind = bool(numeric_impute_step["params"].get("add_indicator")) if numeric_impute_step else False
        fill_value = numeric_impute_step["params"].get("fill_value") if numeric_impute_step else None
        num_steps: list[tuple[str, Any]] = [("impute", _build_imputer(strategy, add_ind, fill_value))]
        if scale_step:
            num_steps.append(("scale", _build_scaler(scale_step["params"].get("method", "standard"))))
        transformers.append(("num", Pipeline(num_steps), numeric_group))
    if categorical_group:
        strategy = categorical_impute_step["params"]["strategy"] if categorical_impute_step else "most_frequent"
        fill_value = categorical_impute_step["params"].get("fill_value") if categorical_impute_step else None
        cat_imputer = _build_imputer(strategy, False, fill_value)
        method = default_encode_step["params"]["method"] if default_encode_step else "onehot"
        max_cat = default_encode_step["params"].get("max_categories", 30) if default_encode_step else 30
        encoder = _build_encoder(method, max_cat)
        transformers.append(("cat", Pipeline([("impute", cat_imputer), ("encode", encoder)]), categorical_group))
    for i, s in enumerate(explicit_encode_steps):
        method = s["params"].get("method", "onehot")
        max_cat = s["params"].get("max_categories", 30)
        sub = Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("encode", _build_encoder(method, max_cat))])
        transformers.append((f"encode_{i}", sub, s["columns"]))

    if not transformers:
        raise ValueError("No usable feature columns after preprocessing")

    preprocess = ColumnTransformer(transformers, remainder="drop")
    features_stage: Any = Pipeline(feature_steps) if feature_steps else "passthrough"

    pipeline_steps: list[tuple[str, Any]] = [("features", features_stage), ("preprocess", preprocess)]

    select_step = next((s for s in recipe if s["op"] == "select"), None)
    if select_step:
        pipeline_steps.append(("select", _build_selector(select_step["params"], task_type)))

    model_cls = _import_class(spec["model"]["class"])
    model_params = dict(spec["model"].get("params", {}))

    class_balance_step = next((s for s in recipe if s["op"] == "class_balance"), None)
    uses_imblearn = False
    if class_balance_step:
        if not is_classification:
            raise ValueError("class_balance is only valid for classification task types")
        method = class_balance_step["params"].get("method", "class_weight")
        if method == "class_weight":
            try:
                sig = inspect.signature(model_cls.__init__)
                if "class_weight" in sig.parameters:
                    model_params["class_weight"] = "balanced"
            except (TypeError, ValueError):
                pass
        elif method == "smote":
            uses_imblearn = True

    target_transform_step = next((s for s in recipe if s["op"] == "target_transform"), None)
    if target_transform_step and is_classification:
        raise ValueError("target_transform is only valid for regression task types")

    model = model_cls(**model_params)
    model_param_prefix = "model__"
    if target_transform_step:
        model = TransformedTargetRegressor(regressor=model, func=np.log1p, inverse_func=np.expm1)
        model_param_prefix = "model__regressor__"

    if uses_imblearn:
        from imblearn.over_sampling import SMOTE
        from imblearn.pipeline import Pipeline as ImbPipeline

        pipeline_steps.append(("smote", SMOTE(random_state=42)))
        pipeline_steps.append(("model", model))
        pipeline = ImbPipeline(pipeline_steps)
    else:
        pipeline_steps.append(("model", model))
        pipeline = Pipeline(pipeline_steps)

    info = RecipeInfo(
        feature_columns=feature_columns,
        numeric_columns=raw_numeric_cols,
        categorical_columns=raw_categorical_cols,
        dropped=dropped,
        model_param_prefix=model_param_prefix,
        uses_imblearn=uses_imblearn,
    )
    return pipeline, info


# --------------------------------------------------------------------------- #
# preprocessing_applied / preview_recipe                                      #
# --------------------------------------------------------------------------- #


def preprocessing_applied(pipeline, recipe: list[dict], info: RecipeInfo, X_sample) -> dict:
    """After fit: the ``preprocessing_applied`` envelope block (see
    ``pipeline/base.py`` docstring for the reserved shape)."""
    names_out: list[str] = []
    try:
        preprocess = pipeline.named_steps["preprocess"]
        names_out = list(preprocess.get_feature_names_out())
    except Exception:
        names_out = []

    n_features_in = len(info.feature_columns)
    n_features_out = len(names_out) if names_out else n_features_in
    # ColumnTransformer prefixes every output with its transformer name
    # ("num__orders", "cat__region_west"); strip that so a raw column that
    # passed through impute/scale untouched is not reported as "derived".
    raw_names = set(info.feature_columns)
    stripped = [n.split("__", 1)[1] if "__" in n else n for n in names_out]
    derived_columns = [n for n in stripped if n not in raw_names][:200]

    steps_out = [
        {
            "op": step["op"],
            "columns": step.get("columns", []),
            "params": step.get("params", {}),
            "description": step.get("description"),
        }
        for step in recipe
    ]

    return {
        "steps": steps_out,
        "n_features_in": n_features_in,
        "n_features_out": n_features_out,
        "derived_columns": derived_columns,
        "dropped_columns": [d["name"] for d in info.dropped][:200],
    }


def preview_recipe(df: pd.DataFrame, plan: dict, spec: dict, profile: dict, max_rows: int = 5000) -> dict:
    """Cheap sanity fit: resolve + compile the recipe, subsample, 3-fold CV with
    the spec's default params. Never raises — CV failures surface as
    ``{"cv": None, "error": ...}``."""
    try:
        recipe = resolve_recipe(plan, profile, spec)
        pipeline, info = compile_recipe(recipe, profile, spec, plan)
    except Exception as e:
        return {
            "steps": [],
            "n_features_in": 0,
            "n_features_out": 0,
            "derived_columns": [],
            "dropped_columns": [],
            "cv": None,
            "n_rows_used": 0,
            "error": str(e),
        }

    target = plan["target_column"]
    task_type = plan["task_type"]
    is_classification = task_type != "regression"

    rows = df.dropna(subset=[target])
    X_full = rows[info.feature_columns]
    y_raw = rows[target]
    if is_classification:
        le = LabelEncoder()
        y_full = le.fit_transform(y_raw.astype(str))
    else:
        y_full = y_raw.astype(float).to_numpy()

    n = len(X_full)
    if n > max_rows:
        if is_classification:
            X_sample, _, y_sample, _ = train_test_split(
                X_full, y_full, train_size=max_rows, random_state=42, stratify=y_full
            )
        else:
            rng = np.random.RandomState(42)
            idx = rng.choice(n, size=max_rows, replace=False)
            X_sample, y_sample = X_full.iloc[idx], y_full[idx]
    else:
        X_sample, y_sample = X_full, y_full

    applied = preprocessing_applied(pipeline, recipe, info, X_sample.head(5))

    cv_block = None
    error = None
    try:
        primary_metric = plan.get("primary_metric")
        scoring = METRIC_SCORING.get(primary_metric)
        if scoring is None:
            raise ValueError(f"Unknown primary_metric '{primary_metric}'")
        cv = (
            StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
            if is_classification
            else KFold(n_splits=3, shuffle=True, random_state=42)
        )
        # n_jobs=1: this is a small, cheap sanity fit (<=max_rows rows, default
        # params, 3 folds) — process-pool startup overhead (especially on
        # Windows) would dominate the wall time a parallel n_jobs tries to save.
        scores = cross_val_score(pipeline, X_sample, y_sample, cv=cv, scoring=scoring, n_jobs=1)
        cv_block = {
            "metric": primary_metric,
            "mean": round(float(scores.mean()), 4),
            "std": round(float(scores.std()), 4),
            "n_splits": 3,
        }
    except Exception as e:
        error = str(e)

    result = {**applied, "cv": cv_block, "n_rows_used": int(len(X_sample))}
    if error:
        result["error"] = error
    return result
