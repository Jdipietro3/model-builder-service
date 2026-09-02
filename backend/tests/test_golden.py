"""Golden-file regression test for `app.ml.training.run_plan`.

This is the tripwire for the upcoming recipe-compiler (Phase 1) and
Optuna-tuning (Phase 2) work described in the roadmap: both phases carry a
hard requirement that a plan omitting the new fields must produce identical
results to today. This file pins "today" down as a committed fixture so that
requirement is a runnable check instead of a promise.

Training here is deterministic (every model/estimator in the registry specs
pins `random_state=42`, and permutation importance / single-feature leakage
checks do the same) — two consecutive runs of the same plan produce
byte-identical `results` envelopes modulo wall-clock keys. So this test
compares for *exact* equality after stripping `training_seconds`, rather than
tolerating drift.

To regenerate after an *intended* results change (e.g. a deliberate metric
rounding change, a new caveat, an intentional preprocessing tweak), run from
`backend/`:

    venv/Scripts/python.exe -m pytest tests/test_golden.py --regen-golden -q

then inspect the resulting git diff of `tests/fixtures/golden_supervised.json`
before committing it — a large or unexpected diff usually means the change
wasn't as scoped as intended.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from helpers import GOLDEN_PLANS, build_plan

from app.ml.training import run_plan

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_supervised.json"

# Keys stripped before comparison because they are genuinely non-deterministic
# (wall-clock timing). Nothing else in the results envelope varies run-to-run:
# every estimator and diagnostic in the supervised path is seeded (random_state=42).
NON_DETERMINISTIC_KEYS = {"training_seconds"}

MAX_REPORTED_DIFFS = 20


def _strip_keys(obj: Any, keys: set[str]) -> Any:
    """Recursively drop any dict key in `keys`, anywhere in the structure."""
    if isinstance(obj, dict):
        return {k: _strip_keys(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip_keys(v, keys) for v in obj]
    return obj


def _json_roundtrip(obj: Any) -> Any:
    """Normalize to exactly what would be read back from the committed
    fixture (tuples -> lists, etc.) so comparison isn't tripped up by
    in-memory-only type differences."""
    return json.loads(json.dumps(obj, sort_keys=True))


def _diff(expected: Any, actual: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """Recursively collect (dotted_path, expected, actual) for every leaf
    where the two structures disagree."""
    diffs: list[tuple[str, Any, Any]] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = sorted(set(expected) | set(actual))
        for k in keys:
            sub_path = f"{path}.{k}" if path else k
            if k not in expected:
                diffs.append((sub_path, "<missing>", actual[k]))
            elif k not in actual:
                diffs.append((sub_path, expected[k], "<missing>"))
            else:
                diffs.extend(_diff(expected[k], actual[k], sub_path))
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            diffs.append((f"{path} (length)", len(expected), len(actual)))
        for i, (e, a) in enumerate(zip(expected, actual)):
            diffs.extend(_diff(e, a, f"{path}[{i}]"))
    else:
        if expected != actual:
            diffs.append((path, expected, actual))
    return diffs


def _format_diffs(diffs: list[tuple[str, Any, Any]]) -> str:
    shown = diffs[:MAX_REPORTED_DIFFS]
    lines = [f"  {path}: expected {expected!r}, got {actual!r}" for path, expected, actual in shown]
    remaining = len(diffs) - len(shown)
    if remaining > 0:
        lines.append(f"  ... and {remaining} more difference(s)")
    return "\n".join(lines)


def _load_golden() -> dict[str, Any]:
    if not FIXTURE_PATH.exists():
        pytest.fail(
            f"Golden fixture missing at {FIXTURE_PATH}. Generate it with:\n"
            "    python -m pytest tests/test_golden.py --regen-golden"
        )
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.slow
@pytest.mark.parametrize(
    "name,csv_fixture,methodology_id,target,excluded,task_type,strategy,metric",
    GOLDEN_PLANS,
    ids=[p[0] for p in GOLDEN_PLANS],
)
def test_golden_supervised(
    request,
    name,
    csv_fixture,
    methodology_id,
    target,
    excluded,
    task_type,
    strategy,
    metric,
):
    csv_path = request.getfixturevalue(csv_fixture)
    plan = build_plan(
        methodology_id=methodology_id,
        target_column=target,
        excluded_columns=excluded,
        task_type=task_type,
        strategy=strategy,
        primary_metric=metric,
    )

    outcome = run_plan(csv_path, plan, lambda *a: None)
    actual = _json_roundtrip(_strip_keys(outcome.results, NON_DETERMINISTIC_KEYS))

    if request.config.getoption("--regen-golden"):
        all_golden = _load_golden() if FIXTURE_PATH.exists() else {}
        all_golden[name] = actual
        FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FIXTURE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_golden, f, indent=2, sort_keys=True)
            f.write("\n")
        pytest.skip(f"--regen-golden: wrote fixture entry '{name}'")

    golden = _load_golden()
    if name not in golden:
        pytest.fail(
            f"No golden entry '{name}' in {FIXTURE_PATH}. Regenerate with:\n"
            "    python -m pytest tests/test_golden.py --regen-golden"
        )
    expected = _strip_keys(golden[name], NON_DETERMINISTIC_KEYS)

    diffs = _diff(expected, actual)
    if diffs:
        pytest.fail(
            f"Golden mismatch for plan '{name}' ({len(diffs)} difference(s)). "
            "If this is an intended results change, regenerate with "
            "`python -m pytest tests/test_golden.py --regen-golden` and review the diff:\n"
            + _format_diffs(diffs)
        )
