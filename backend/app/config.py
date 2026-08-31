import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", str(REPO_ROOT / "data")))
UPLOADS_DIR = DATA_DIR / "uploads"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
PREDICTIONS_DIR = DATA_DIR / "predictions"
DB_PATH = DATA_DIR / "app.db"

for _d in (UPLOADS_DIR, ARTIFACTS_DIR, PREDICTIONS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# Orchestrator LLM. "anthropic" uses the native SDK (keeps explicit prompt-cache
# breakpoints); "openai" uses the OpenAI-compatible /v1/chat/completions shape,
# which covers DeepSeek, Ollama, vLLM, LM Studio, Together and Groq via LLM_BASE_URL.
# The ANTHROPIC_* fallbacks keep an existing .env working with no edits.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LLM_MODEL") or ANTHROPIC_MODEL
LLM_API_KEY = os.getenv("LLM_API_KEY") or ANTHROPIC_API_KEY
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or None
# DeepSeek caps output at 8192; the Anthropic default is 16000.
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "16000"))

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
