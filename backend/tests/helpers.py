"""Shared plan-building helpers for test_golden.py and test_train_serve.py.

Kept separate so both modules build plans the same way — a divergence here
would make the two suites test subtly different things without either
noticing.
"""

from typing import Any


def build_plan(
    *,
    methodology_id: str,
    target_column: str,
    excluded_columns: list[str],
    task_type: str,
    strategy: str,
    primary_metric: str,
    n_splits: int = 5,
) -> dict[str, Any]:
    """A plan dict shaped the way `run_plan` expects — the same fields the
    orchestrator's `propose_plan` tool would emit, passed straight to
    `run_plan` without going through `app.schemas.Plan`/`app.ml.plans`
    validation (run_plan itself doesn't require it)."""
    return {
        "methodology_id": methodology_id,
        "data_shape": "tabular",
        "task_family": "supervised",
        "task_type": task_type,
        "target_column": target_column,
        "excluded_columns": excluded_columns,
        "primary_metric": primary_metric,
        "validation": {"strategy": strategy, "n_splits": n_splits},
    }


# (name, csv fixture name, methodology_id, target, excluded, task_type, strategy, metric)
GOLDEN_PLANS = [
    (
        "churn_logistic",
        "churn_csv",
        "classification.logistic_baseline",
        "churned",
        ["customer_id"],
        "binary_classification",
        "stratified_kfold",
        "roc_auc",
    ),
    (
        "churn_rf",
        "churn_csv",
        "classification.random_forest",
        "churned",
        ["customer_id"],
        "binary_classification",
        "stratified_kfold",
        "roc_auc",
    ),
    (
        "house_linear",
        "house_csv",
        "regression.linear_baseline",
        "price",
        ["listing_id"],
        "regression",
        "kfold",
        "rmse",
    ),
    (
        "house_rf",
        "house_csv",
        "regression.random_forest",
        "price",
        ["listing_id"],
        "regression",
        "kfold",
        "rmse",
    ),
]
