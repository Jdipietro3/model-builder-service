"""Train-serve parity: the product's core claim is that the training-time
pipeline *is* the serving pipeline, so the batch path (`score_dataframe`,
used by CSV re-upload scoring) and the live path (`predict_records`, whose
output shape mirrors the generated standalone `serve.py`) must agree on the
same rows. Both are exercised directly against a `RunOutcome.artifact` /
`.meta` pair — no DB, no `build_bundle`, no server.

Training happens once per task type via module-scoped fixtures (marked
`slow` at module level, since every test here either trains or consumes an
already-trained fixture).
"""

import pandas as pd
import pytest

from helpers import build_plan

from app.ml.scoring import predict_records, score_dataframe
from app.ml.training import run_plan

pytestmark = pytest.mark.slow

N_RECORDS = 20


@pytest.fixture(scope="module")
def churn_outcome(churn_csv):
    plan = build_plan(
        methodology_id="classification.logistic_baseline",
        target_column="churned",
        excluded_columns=["customer_id"],
        task_type="binary_classification",
        strategy="stratified_kfold",
        primary_metric="roc_auc",
    )
    return run_plan(churn_csv, plan, lambda *a: None)


@pytest.fixture(scope="module")
def house_outcome(house_csv):
    plan = build_plan(
        methodology_id="regression.linear_baseline",
        target_column="price",
        excluded_columns=["listing_id"],
        task_type="regression",
        strategy="kfold",
        primary_metric="rmse",
    )
    return run_plan(house_csv, plan, lambda *a: None)


@pytest.fixture(scope="module")
def churn_slice(churn_csv) -> pd.DataFrame:
    # Real rows from the training distribution, not synthesized values that
    # could fall outside what the fitted preprocessing/model has seen.
    return pd.read_csv(churn_csv).head(N_RECORDS).reset_index(drop=True)


@pytest.fixture(scope="module")
def house_slice(house_csv) -> pd.DataFrame:
    return pd.read_csv(house_csv).head(N_RECORDS).reset_index(drop=True)


def _records(df: pd.DataFrame) -> list[dict]:
    return df.to_dict(orient="records")


# --- 1. batch vs live agreement -------------------------------------------------


def test_classification_predict_matches_score(churn_outcome, churn_slice):
    scored_df, _ = score_dataframe(churn_outcome.artifact, churn_outcome.meta, churn_slice)
    live = predict_records(churn_outcome.artifact, churn_outcome.meta, _records(churn_slice))

    assert live["predictions"] == scored_df["prediction"].tolist()

    label_classes = churn_outcome.meta["label_classes"]
    for i, row_proba in enumerate(live["probabilities"]):
        for cls in label_classes:
            batch_val = scored_df.iloc[i][f"prob_{cls}"]
            # Both paths round to 4dp (_finalize_scored and predict_records agree
            # on precision here, unlike the regression prediction column below), so
            # this should be an exact match; approx guards only against float repr noise.
            assert row_proba[cls] == pytest.approx(batch_val, abs=1e-9)


def test_regression_predict_matches_score(house_outcome, house_slice):
    scored_df, _ = score_dataframe(house_outcome.artifact, house_outcome.meta, house_slice)
    live = predict_records(house_outcome.artifact, house_outcome.meta, _records(house_slice))

    # _finalize_scored rounds regression predictions to 2dp for display
    # (`preds.round(2)`), while predict_records returns full float precision for
    # the live path — they are not expected to be bit-identical. The tolerance
    # below is exactly that rounding step, not slack for floating-point noise.
    for live_v, batch_v in zip(live["predictions"], scored_df["prediction"].tolist()):
        assert live_v == pytest.approx(batch_v, abs=0.005)


# --- 2. classification label mapping + probabilities ----------------------------


def test_classification_labels_are_original_values(churn_outcome, churn_slice):
    live = predict_records(churn_outcome.artifact, churn_outcome.meta, _records(churn_slice))
    label_classes = set(churn_outcome.meta["label_classes"])

    # Predictions must come back as the original label values (e.g. "0"/"1" as
    # they appeared in the CSV), never as raw encoded integers.
    assert all(isinstance(p, str) for p in live["predictions"])
    assert set(live["predictions"]) <= label_classes


def test_classification_probabilities_present_and_sum_to_one(churn_outcome, churn_slice):
    live = predict_records(churn_outcome.artifact, churn_outcome.meta, _records(churn_slice))
    assert "probabilities" in live
    assert len(live["probabilities"]) == len(churn_slice)
    for row in live["probabilities"]:
        assert sum(row.values()) == pytest.approx(1.0, abs=1e-3)


# --- 3. missing / extra columns --------------------------------------------------


def test_missing_feature_column_raises_on_both_paths(churn_outcome, churn_slice):
    feature_cols = churn_outcome.meta["feature_columns"]
    missing_col = feature_cols[0]
    df_missing = churn_slice.drop(columns=[missing_col])

    with pytest.raises(ValueError, match=missing_col):
        score_dataframe(churn_outcome.artifact, churn_outcome.meta, df_missing)
    with pytest.raises(ValueError, match=missing_col):
        predict_records(churn_outcome.artifact, churn_outcome.meta, _records(df_missing))


def test_extra_unknown_columns_pass_through_harmlessly(churn_outcome, churn_slice):
    df_extra = churn_slice.copy()
    df_extra["totally_unknown_column"] = "unrecognized value"

    scored_df, _ = score_dataframe(churn_outcome.artifact, churn_outcome.meta, df_extra)
    assert "totally_unknown_column" in scored_df.columns
    assert len(scored_df) == len(df_extra)

    live = predict_records(churn_outcome.artifact, churn_outcome.meta, _records(df_extra))
    assert len(live["predictions"]) == len(df_extra)


# --- 4. empty input ---------------------------------------------------------------


def test_score_dataframe_raises_on_empty_dataframe(churn_outcome, churn_csv):
    empty_df = pd.read_csv(churn_csv).head(0)
    with pytest.raises(ValueError, match="no rows"):
        score_dataframe(churn_outcome.artifact, churn_outcome.meta, empty_df)
