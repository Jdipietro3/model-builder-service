"""Live in-service deployment logic: turn a completed run into a row-level
prediction endpoint with a machine-readable request/response contract and
basic training-vs-served distribution drift comparison.

Kept separate from routes/deployments.py (thin HTTP layer) so it can be unit
tested directly. REST-only — no chat tool wraps this; see CLAUDE.md.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ml.scoring import load_model
from .models import Dataset, Deployment, InferenceLog, Run


def _col_by_name(dataset_profile: dict) -> dict[str, dict]:
    return {c["name"]: c for c in dataset_profile.get("columns", [])}


def _coerce_to_dtype(value: Any, dtype: str | None) -> Any:
    """Cast a profile display value back to the column's real dtype.

    The profiler stores ``top_values`` and ``sample_values`` as STRINGS, because
    they exist to be rendered. Copying them straight into example_record shipped
    an example that contradicted the dtype we advertise beside it: a low
    -cardinality int64 column came out as "0" while a high-cardinality one came
    out as 10.9659, because only the latter falls through to the numeric mean.

    That is not cosmetic. sklearn's ColumnTransformer routes a string down the
    categorical branch instead of the numeric one, so a caller who pasted the
    documented example got a confident prediction computed from garbage — no
    error, just a different answer. Measured on the phishing model, the same
    record scored "phishing 87.7%" as strings and "legitimate 72.7%" as numbers.
    """
    if not isinstance(value, str) or not dtype:
        return value
    d = str(dtype).lower()
    try:
        if d.startswith(("int", "uint")):
            return int(float(value))
        if d.startswith("float"):
            return float(value)
        if d.startswith("bool"):
            return value.strip().lower() in ("true", "1")
    except ValueError:
        # Genuinely non-numeric text in a column we believed was numeric —
        # hand back the original rather than inventing a value.
        return value
    return value


def _example_value(col_info: dict | None) -> Any:
    """A representative value for a feature column, for the contract's
    example_record: the most common value for low-cardinality columns, the
    mean for numeric columns, else the first sample value seen. Always cast to
    the column's own dtype, so the example is something the model can actually
    consume (see _coerce_to_dtype)."""
    if not col_info:
        return None
    dtype = col_info.get("dtype")
    top_values = col_info.get("top_values")
    if top_values:
        return _coerce_to_dtype(top_values[0]["value"], dtype)
    stats = col_info.get("stats")
    if stats:
        return stats["mean"]
    sample_values = col_info.get("sample_values")
    if sample_values:
        return _coerce_to_dtype(sample_values[0], dtype)
    return None


def _feature_columns(meta: dict) -> list[str]:
    if meta.get("task_family") == "ensemble":
        return sorted({c for cols in meta["base_feature_columns"].values() for c in cols})
    return list(meta["feature_columns"])


def build_contract(run: Run, dataset_profile: dict) -> dict:
    """Request/response contract for a deployment: the feature columns the
    endpoint expects, an example record, and target/task metadata. The target
    column is excluded from feature_columns (it's a serving output, not an
    input). ``endpoint`` uses a placeholder id — the caller (create_deployment
    /promote) fills in the real deployment id once it's known."""
    _, meta = load_model(run)
    target_column = meta.get("target_column")
    col_info = _col_by_name(dataset_profile)

    feature_names = [c for c in _feature_columns(meta) if c != target_column]
    feature_columns = []
    example_record: dict[str, Any] = {}
    for name in feature_names:
        info = col_info.get(name)
        dtype = info["kind"] if info else "unknown"
        example = _example_value(info)
        feature_columns.append({"name": name, "dtype": dtype, "example": example})
        example_record[name] = example

    return {
        "feature_columns": feature_columns,
        "example_record": example_record,
        "target_column": target_column,
        "task_type": meta.get("task_type"),
        "endpoint": "/deployments/{id}/predict",
    }


def training_distribution(run: Run, dataset_profile: dict) -> dict:
    """Reference distribution captured at training time, in the same shape
    ``serving_stats`` produces for the served distribution so the UI can
    compare them directly."""
    _, meta = load_model(run)
    target_column = meta.get("target_column")
    col_info = _col_by_name(dataset_profile).get(target_column) or {}
    is_classification = meta.get("task_type") != "regression"

    if is_classification:
        top_values = col_info.get("top_values") or []
        total = sum(v["count"] for v in top_values)
        proportions = {
            str(v["value"]): round(v["count"] / total, 4) if total else 0.0 for v in top_values
        }
        return {"kind": "class_counts", "proportions": proportions}

    stats = col_info.get("stats") or {}
    return {
        "kind": "stats",
        "mean": stats.get("mean"),
        "min": stats.get("min"),
        "max": stats.get("max"),
    }


def create_deployment(db: Session, project_id: str, run_id: str, name: str | None) -> Deployment:
    """Validate the run and create a Deployment pointing at it."""
    run = db.get(Run, run_id)
    if not run or run.project_id != project_id:
        raise ValueError("Run not found in this project")
    if run.status != "completed":
        raise ValueError(f"Run is '{run.status}' — only completed runs can be deployed")

    existing = db.query(Deployment).filter(Deployment.project_id == project_id).first()
    if existing:
        raise ValueError(
            "This project already has a deployment — promote it to a different run "
            "instead of deploying a second one."
        )

    _, meta = load_model(run)
    task_family = meta.get("task_family", "supervised")
    if task_family not in ("supervised", "ensemble"):
        raise ValueError(
            f"'{task_family}' runs can't be row-deployed — only supervised/ensemble "
            "runs support live single-record prediction."
        )

    dataset_profile = dataset_profile_for_run(db, run)
    contract = build_contract(run, dataset_profile)
    dist = training_distribution(run, dataset_profile)

    if not name:
        methodology = meta.get("methodology_id", "model")
        name = f"{methodology} · {run_id[:8]}"

    deployment = Deployment(
        project_id=project_id,
        run_id=run_id,
        name=name,
        contract=contract,
        training_distribution=dist,
    )
    db.add(deployment)
    db.flush()  # id default fires at flush; the contract endpoint needs it
    # Assign a NEW dict (not the same object mutated in place): a plain JSON column
    # doesn't track in-place mutation, and reassigning the identical object reference
    # registers no change, so the endpoint fix-up would be dropped on commit.
    deployment.contract = {**contract, "endpoint": f"/deployments/{deployment.id}/predict"}
    db.commit()
    db.refresh(deployment)
    return deployment


def dataset_profile_for_run(db: Session, run: Run) -> dict:
    dataset = db.get(Dataset, run.dataset_id)
    return (dataset.profile if dataset else None) or {}


def serving_stats(db: Session, deployment: Deployment) -> dict:
    """Aggregate a deployment's InferenceLog rows into request/latency counts
    plus a served_distribution comparable to training_distribution."""
    logs = db.scalars(
        select(InferenceLog).where(InferenceLog.deployment_id == deployment.id)
    ).all()

    n_requests = len(logs)
    n_rows = sum(log.n_rows for log in logs)
    avg_latency_ms = round(sum(log.latency_ms for log in logs) / n_requests, 2) if n_requests else 0.0

    served_distribution: dict[str, Any] | None = None
    training_dist = deployment.training_distribution or {}
    kind = training_dist.get("kind")

    if n_requests:
        if kind == "stats" or (kind is None and any("stats" in (log.summary or {}) for log in logs)):
            weighted_sum = 0.0
            mins = []
            maxs = []
            total_rows = 0
            for log in logs:
                stats = (log.summary or {}).get("stats")
                if not stats or not log.n_rows:
                    continue
                weighted_sum += stats["mean"] * log.n_rows
                total_rows += log.n_rows
                mins.append(stats["min"])
                maxs.append(stats["max"])
            if total_rows:
                served_distribution = {
                    "kind": "stats",
                    "mean": round(weighted_sum / total_rows, 4),
                    "min": round(min(mins), 4) if mins else None,
                    "max": round(max(maxs), 4) if maxs else None,
                }
        else:
            totals: dict[str, int] = {}
            for log in logs:
                counts = (log.summary or {}).get("class_counts") or {}
                for label, count in counts.items():
                    totals[label] = totals.get(label, 0) + count
            grand_total = sum(totals.values())
            if grand_total:
                served_distribution = {
                    "kind": "class_counts",
                    "proportions": {k: round(v / grand_total, 4) for k, v in totals.items()},
                }

    return {
        "n_requests": n_requests,
        "n_rows": n_rows,
        "avg_latency_ms": avg_latency_ms,
        "served_distribution": served_distribution,
        "training_distribution": deployment.training_distribution,
        "drift_note": "basic population comparison, not a statistical test",
    }
