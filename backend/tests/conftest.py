"""Shared test setup.

The most important thing here happens at *import* time, before any `app.*`
module is imported: `config.py` derives DATA_DIR (and DATABASE_URL, and the
uploads/artifacts/predictions directories it mkdirs on import) from the
environment exactly once, so redirecting it afterwards is impossible. Tests
must never touch the developer's live `data/` directory or `app.db`, so we
point DATA_DIR at a per-session temp directory here and only then let anything
import `app`.

`load_dotenv` in config.py does not override variables already set in the
environment, so this wins over a DATA_DIR in backend/.env.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

# Importable as `app.*` no matter which directory pytest was invoked from.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must precede every `app` import — see module docstring.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="mbs-tests-"))
# Keep the orchestrator from finding a real key: no test may reach the network.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LLM_API_KEY"] = ""

import pytest  # noqa: E402

SAMPLES_DIR = REPO_ROOT / "samples"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption(
        "--regen-golden",
        action="store_true",
        default=False,
        help="Rewrite the golden fixtures from this run instead of comparing "
        "against them. Use only when a results change is intended, and review "
        "the resulting diff.",
    )


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES_DIR


@pytest.fixture(scope="session")
def churn_csv() -> str:
    return str(SAMPLES_DIR / "churn.csv")


@pytest.fixture(scope="session")
def house_csv() -> str:
    return str(SAMPLES_DIR / "house_prices.csv")


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """The temp DATA_DIR this session redirected `app.config` to."""
    return Path(os.environ["DATA_DIR"])
