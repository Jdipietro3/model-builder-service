# Metis (prototype)

Chat-driven ML model training for engineers who can code but don't have deep ML
expertise. Upload a CSV, describe your goal in plain language, review the proposed
training plan, and get a trained model with an honest evaluation and deployable code.

See [CLAUDE.md](CLAUDE.md) for the full product brief.

## Architecture

- **The LLM decides, deterministic code executes.** A Claude orchestrator (tool use)
  reads the data profile and conversation, then selects and parameterizes an entry
  from a curated methodology registry ([backend/app/ml/registry/specs](backend/app/ml/registry/specs)).
  All training runs through hand-written sklearn/LightGBM code — the LLM never
  generates training code.
- **Backend**: FastAPI + SQLite + SSE streaming (`backend/`)
- **Frontend**: Next.js chat UI with structured cards for profiles, plans, and
  results (`frontend/`)
- **Artifacts**: every completed run produces a downloadable bundle — fitted model,
  a standalone `train.py` that reproduces training (glass box), and a FastAPI
  inference stub.

## Setup

```powershell
# Python (3.12+)
python -m venv venv
venv\Scripts\pip install -r backend\requirements.txt

# Node
cd frontend && npm install && cd ..

# API key (required for the chat orchestrator)
copy backend\.env.example backend\.env
# ...then edit backend/.env and set ANTHROPIC_API_KEY

# Demo data
venv\Scripts\python samples\make_sample_data.py
```

## Run

```powershell
# Terminal 1 — backend on :8000
venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000

# Terminal 2 — frontend on :3000
cd frontend && npm run dev
```

Open http://localhost:3000, create a project, upload `samples/churn.csv`, and type
"predict which customers will churn".

## Accounts

Signup is open and self-serve. There is **no self-serve password reset** — that
needs mail infrastructure this prototype doesn't have — so a forgotten password
is recovered by an operator with shell access:

```powershell
venv\Scripts\python.exe backend\scripts\reset_password.py --list
venv\Scripts\python.exe backend\scripts\reset_password.py user@example.com
venv\Scripts\python.exe backend\scripts\reset_password.py user@example.com --generate
```

Without `--generate` it prompts twice without echoing. The password is never
taken as a command-line argument, because arguments land in shell history and
the process list.

A reset signs out every existing session for that account and clears its failed
login attempts — otherwise the rate limiting that the user just tripped would
keep them locked out after the reset.

## v1 scope

Tabular CSV only; binary/multiclass classification and regression; six
methodologies (logistic/ridge baselines, random forest, LightGBM). Local files.
Training runs in-process on a thread pool. Multi-user as of the auth work below —
every project is scoped to the account that created it.
