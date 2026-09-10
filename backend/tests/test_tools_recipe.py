"""Unit tests for the Phase 1 recipe wiring in app.orchestrator.tools:
propose_plan / propose_tournament storing a resolved recipe, and the new
preview_recipe tool. No LLM, no network — these call the tool handlers
directly against a real (temp) DB session and the real churn.csv sample.
"""

import uuid

import pytest

from app.db import SessionLocal, init_db
from app.ml.profiling import profile_path
from app.models import Dataset, Project, User
from app.orchestrator import tools
from app.orchestrator.tools import (
    _SCHEMA_LIST_KEYS,
    _SCHEMA_MAP_KEYS,
    _SCHEMA_VALUE_KEYS,
    PreviewRecipeInput,
    ProposePlanInput,
    RecipeStepInput,
    _clean_schema,
)


def _iter_schema_nodes(node):
    if not isinstance(node, dict):
        return
    yield node
    for key in _SCHEMA_VALUE_KEYS:
        if isinstance(node.get(key), dict):
            yield from _iter_schema_nodes(node[key])
    for key in _SCHEMA_LIST_KEYS:
        if isinstance(node.get(key), list):
            for b in node[key]:
                yield from _iter_schema_nodes(b)
    for key in _SCHEMA_MAP_KEYS:
        if isinstance(node.get(key), dict):
            for v in node[key].values():
                yield from _iter_schema_nodes(v)


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    init_db()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def churn_dataset(db, churn_csv):
    """A Project + Dataset row pointing at the real churn.csv sample, with a
    real profile (never a hand-written dict, so it can't drift from the real
    shape)."""
    user = User(email=f"tools-recipe-{uuid.uuid4().hex}@test.local", password_hash="x")
    db.add(user)
    db.flush()
    project = Project(user_id=user.id, name="recipe tools test")
    db.add(project)
    db.flush()
    dataset = Dataset(
        project_id=project.id,
        filename="churn.csv",
        path=churn_csv,
        profile=profile_path(churn_csv),
    )
    db.add(dataset)
    db.commit()
    return project, dataset


PLAN_KWARGS = dict(
    task_type="binary_classification",
    methodology_id="classification.logistic_baseline",
    target_column="churned",
    excluded_columns=["customer_id"],
    primary_metric="roc_auc",
    reasoning="test",
)


# ---------------------------------------------------------------------------
# propose_plan


def test_propose_plan_without_preprocessing_stores_resolved_default_recipe(db, churn_dataset):
    project, dataset = churn_dataset
    args = ProposePlanInput(dataset_id=dataset.id, **PLAN_KWARGS)
    result, card = tools.propose_plan(db, project.id, args)

    assert "error" not in result
    steps = result["plan"]["preprocessing"]
    assert isinstance(steps, list) and len(steps) > 0
    for step in steps:
        assert step["description"]  # every resolved step has a description filled in
    assert result["recipe_summary"] == [s["description"] for s in steps]
    assert card["plan"]["preprocessing"] == steps


def test_propose_plan_with_explicit_valid_recipe_stores_it_with_descriptions(db, churn_dataset):
    project, dataset = churn_dataset
    explicit = [
        RecipeStepInput(op="impute", columns=[], params={"group": "numeric", "strategy": "mean"}),
        RecipeStepInput(op="encode", columns=[], params={"method": "onehot"}),
    ]
    args = ProposePlanInput(dataset_id=dataset.id, preprocessing=explicit, **PLAN_KWARGS)
    result, card = tools.propose_plan(db, project.id, args)

    assert "error" not in result
    steps = result["plan"]["preprocessing"]
    assert len(steps) == 2
    assert steps[0]["op"] == "impute"
    assert steps[0]["params"]["strategy"] == "mean"
    assert steps[0]["description"]
    assert steps[1]["op"] == "encode"
    assert steps[1]["description"]


def test_propose_plan_with_invalid_op_returns_error_envelope(db, churn_dataset):
    """An unknown op is rejected at the tool-schema boundary (RecipeOp is a
    Literal) — going through dispatch(), as the orchestrator loop does,
    exercises that path and confirms it comes back as an error envelope, not
    a raised exception."""
    project, dataset = churn_dataset
    tool_input = ProposePlanInput(dataset_id=dataset.id, **PLAN_KWARGS).model_dump()
    tool_input["preprocessing"] = [{"op": "not_a_real_op", "columns": [], "params": {}}]

    result_json, card = tools.dispatch(db, project.id, "propose_plan", tool_input)

    import json

    result = json.loads(result_json)
    assert "error" in result
    assert card is None


def test_propose_plan_with_unknown_column_returns_error_envelope(db, churn_dataset):
    project, dataset = churn_dataset
    explicit = [RecipeStepInput(op="drop", columns=["not_a_real_column"], params={})]
    args = ProposePlanInput(dataset_id=dataset.id, preprocessing=explicit, **PLAN_KWARGS)
    result, card = tools.propose_plan(db, project.id, args)

    assert "error" in result
    assert card is None


# ---------------------------------------------------------------------------
# preview_recipe


def test_preview_recipe_returns_documented_keys_and_numeric_cv_mean(db, churn_dataset):
    project, dataset = churn_dataset
    args = PreviewRecipeInput(
        dataset_id=dataset.id,
        target_column="churned",
        task_type="binary_classification",
        methodology_id="classification.logistic_baseline",
        primary_metric="roc_auc",
        excluded_columns=["customer_id"],
    )
    result, card = tools.preview_recipe_tool(db, project.id, args)

    assert card is None
    for key in ("steps", "n_features_in", "n_features_out", "derived_columns", "dropped_columns", "cv", "n_rows_used"):
        assert key in result
    assert result["cv"] is not None
    assert isinstance(result["cv"]["mean"], float)
    assert result["n_rows_used"] > 0


def test_preview_recipe_with_bad_recipe_returns_error_string_not_exception(db, churn_dataset):
    project, dataset = churn_dataset
    bad = [RecipeStepInput(op="drop", columns=["not_a_real_column"], params={})]
    args = PreviewRecipeInput(
        dataset_id=dataset.id,
        target_column="churned",
        task_type="binary_classification",
        methodology_id="classification.logistic_baseline",
        primary_metric="roc_auc",
        excluded_columns=["customer_id"],
        preprocessing=bad,
    )
    result, card = tools.preview_recipe_tool(db, project.id, args)

    # validate_plan catches this before recipe.preview_recipe is even called;
    # either way it must come back as an error envelope, never raise.
    assert "error" in result


def test_preview_recipe_rejects_forecasting_methodology(db, churn_dataset):
    project, dataset = churn_dataset
    args = PreviewRecipeInput(
        dataset_id=dataset.id,
        target_column="churned",
        task_type="forecasting",
        methodology_id="forecasting.prophet",
        primary_metric="mape",
    )
    result, card = tools.preview_recipe_tool(db, project.id, args)
    assert "error" in result


# ---------------------------------------------------------------------------
# _clean_schema on the new inputs: no leftover $defs (nested RecipeStepInput
# lists must inline cleanly, same guarantee as every other tool).


@pytest.mark.parametrize("model", [ProposePlanInput, PreviewRecipeInput])
def test_new_inputs_clean_schema_has_no_defs(model):
    schema = _clean_schema(model.model_json_schema())
    assert "$defs" not in schema
    for node in _iter_schema_nodes(schema):
        assert "$ref" not in node
        assert "$defs" not in node
