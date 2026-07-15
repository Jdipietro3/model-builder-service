# Model Builder (prototype)

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

## v1 scope

Tabular CSV only; binary/multiclass classification and regression; six
methodologies (logistic/ridge baselines, random forest, LightGBM). Single user, no
auth, local files. Training runs in-process on a thread pool.
