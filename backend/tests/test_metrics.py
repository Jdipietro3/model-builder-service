"""Unit tests for app.ml.evaluation.compute_metrics.

Fast, hand-checked: every "exact value" assertion below is computed by hand in
a comment rather than by calling the same sklearn function compute_metrics
calls, so a wrong *metric definition* (e.g. accuracy computed as recall, or a
transposed confusion matrix) would actually be caught instead of the test
just re-deriving the bug.
"""

import json
import warnings

import numpy as np
import pytest

from app.ml.evaluation import compute_metrics

# ---------------------------------------------------------------------------
# Hand-built classification fixture.
#
# index: 0  1  2  3  4  5  6  7
# true:  0  0  0  1  1  1  1  1
# pred:  0  1  0  1  0  1  1  1
#
# Confusion counts: TP=4 (idx 3,5,6,7), FN=1 (idx 4), FP=1 (idx 1), TN=2 (idx 0,2)
#
# accuracy           = (TP+TN)/n = 6/8            = 0.75
# precision          = TP/(TP+FP) = 4/5            = 0.8
# recall (sens.)     = TP/(TP+FN) = 4/5            = 0.8
# f1                 = 2PR/(P+R) = 2*.8*.8/1.6      = 0.8
# specificity        = TN/(TN+FP) = 2/3             = 0.666667
# balanced_accuracy  = (recall+specificity)/2       = (.8+.666667)/2 = 0.733333 -> 0.7333
#
# y_proba[:,1] chosen consistent with the 0.5-threshold predictions above:
PROBA_1 = [0.1, 0.6, 0.2, 0.9, 0.4, 0.8, 0.7, 0.95]
#
# roc_auc by the Mann-Whitney definition (fraction of (pos, neg) pairs ranked
# correctly, ties count 0.5): positives = proba at idx 3,4,5,6,7 = [.9,.4,.8,.7,.95];
# negatives = proba at idx 0,1,2 = [.1,.6,.2]. Counting each positive against every
# negative (15 pairs total):
#   .9  > .1,.6,.2                -> 3
#   .4  > .1,.2  (not > .6)       -> 2
#   .8  > .1,.6,.2                -> 3
#   .7  > .1,.6,.2                -> 3
#   .95 > .1,.6,.2                -> 3
# sum = 14 -> AUC = 14/15 = 0.933333 -> 0.9333


@pytest.fixture
def clf_fixture():
    y_true = np.array([0, 0, 0, 1, 1, 1, 1, 1])
    y_pred = np.array([0, 1, 0, 1, 0, 1, 1, 1])
    y_proba = np.array([[1 - p, p] for p in PROBA_1])
    return y_true, y_pred, y_proba


def test_classification_metrics_match_hand_computed_values(clf_fixture):
    y_true, y_pred, y_proba = clf_fixture
    out = compute_metrics(["accuracy", "f1", "balanced_accuracy", "roc_auc"], y_true, y_pred, y_proba)
    assert out == {
        "accuracy": 0.75,
        "f1": 0.8,
        "balanced_accuracy": 0.7333,
        "roc_auc": 0.9333,
    }


# ---------------------------------------------------------------------------
# Hand-built regression fixture — this is sklearn's own canonical r2_score
# doctest example, picked because its by-hand arithmetic is easy to verify
# independently of sklearn:
#   y_true = [3.0, -0.5, 2.0, 7.0], y_pred = [2.5, 0.0, 2.0, 8.0]
#   errors:        0.5, -0.5,  0.0, -1.0
#   abs errors:    0.5,  0.5,  0.0,  1.0  -> MAE = 2.0/4 = 0.5
#   sq errors:    0.25,  0.25, 0.0,  1.0  -> mean sq err = 1.5/4 = 0.375
#                                          -> RMSE = sqrt(0.375) = 0.612372... -> 0.6124
#   mean(y_true) = 2.875
#   SS_tot = (3-2.875)^2 + (-0.5-2.875)^2 + (2-2.875)^2 + (7-2.875)^2
#          = 0.015625 + 11.390625 + 0.765625 + 17.015625 = 29.1875
#   SS_res = sum(sq errors) = 1.5
#   R2 = 1 - SS_res/SS_tot = 1 - 1.5/29.1875 = 0.948608... -> 0.9486
def test_regression_metrics_match_hand_computed_values():
    y_true = np.array([3.0, -0.5, 2.0, 7.0])
    y_pred = np.array([2.5, 0.0, 2.0, 8.0])
    out = compute_metrics(["r2", "mae", "rmse"], y_true, y_pred)
    assert out == {"r2": 0.9486, "mae": 0.5, "rmse": 0.6124}


@pytest.mark.parametrize(
    "bad_proba",
    [
        pytest.param(lambda p: p[:, [1]], id="single_column_2d"),
        pytest.param(lambda p: p[:, 1], id="one_dimensional"),
    ],
)
def test_malformed_proba_drops_only_the_proba_metrics(clf_fixture, bad_proba):
    """roc_auc/pr_auc need a two-column (n_samples, n_classes) proba. A
    malformed one is validated up front and reported as ValueError, which
    compute_metrics catches — so those two metrics are dropped and every other
    requested metric still comes back. Previously the raw `y_proba[:, 1]`
    raised IndexError, which is not in the caught tuple, so one bad proba took
    down the whole call and lost accuracy/f1 along with it."""
    y_true, y_pred, y_proba = clf_fixture
    out = compute_metrics(
        ["roc_auc", "pr_auc", "accuracy", "f1"], y_true, y_pred, bad_proba(y_proba)
    )
    assert out == {"accuracy": 0.75, "f1": 0.8}


def test_nan_metric_is_omitted_not_serialized(clf_fixture):
    """sklearn 1.9's roc_auc_score returns nan (with an UndefinedMetricWarning)
    for a single-class y_true instead of raising ValueError, so the "metric
    undefined for this data" case no longer reaches the except clause. nan
    survives round(float(...)) untouched and json.dumps writes a bare `NaN`,
    which is invalid JSON and breaks the frontend's parse of the results
    envelope — segment_metrics hits single-class slices routinely. Pin that a
    non-finite score is dropped like any other undefined metric."""
    _, y_pred, y_proba = clf_fixture
    single_class = np.zeros(8, dtype=int)  # every row the same class

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # UndefinedMetricWarning is expected here
        out = compute_metrics(["roc_auc", "accuracy"], single_class, y_pred, y_proba)

    assert "roc_auc" not in out
    # pred has 3 of 8 rows equal to 0 (idx 0, 2, 4) -> accuracy = 3/8 = 0.375
    assert out == {"accuracy": 0.375}
    assert json.dumps(out) == '{"accuracy": 0.375}'  # no bare NaN


def test_metric_needing_proba_is_omitted_not_raised_when_proba_missing():
    """A caller can ask for a proba-based metric without supplying y_proba
    (e.g. a model with no predict_proba). That is rejected as a ValueError,
    which IS in compute_metrics' except clause, so the metric is silently
    dropped from the result instead of blowing up the whole call. Do not let a
    refactor turn this back into a raise: the caller (evaluate_holdout et al.)
    relies on partial results surviving one bad metric."""
    y_true = np.array([0, 1, 1])
    y_pred = np.array([0, 1, 0])
    out = compute_metrics(["roc_auc", "accuracy"], y_true, y_pred, y_proba=None)
    assert "roc_auc" not in out
    assert out == {"accuracy": pytest.approx(0.6667)}


def test_unknown_metric_name_is_ignored():
    y_true = np.array([0, 1, 1, 0])
    y_pred = np.array([0, 1, 0, 0])
    out = compute_metrics(["totally_not_a_metric"], y_true, y_pred)
    assert out == {}


def test_values_are_rounded_plain_python_floats(clf_fixture):
    """Results get JSON-serialized straight into a DB column — a numpy
    scalar (np.float64) surviving here would still json.dumps() fine today,
    but has bitten other codebases (numpy scalars aren't valid JSON per the
    stdlib's strict mode, and some ORMs choke on them), so pin the plain-float
    contract explicitly."""
    y_true, y_pred, y_proba = clf_fixture
    out = compute_metrics(["accuracy", "roc_auc"], y_true, y_pred, y_proba)
    for name, value in out.items():
        assert type(value) is float, f"{name} is {type(value)}, not float"
    assert out["roc_auc"] == round(14 / 15, 4)
