# Running on Another Machine (Git Clone)

## What Git includes for a full demo (no API key)

| Path | Purpose |
|------|---------|
| `GlueRepo/` | Sample Glue jobs (`data_cleaning_and_lambda.py`) |
| `demo/fixtures/` | Sample Medicare CSV for output comparison |
| `artifacts/proj_97173259461c/` | Pre-built conversion artifacts (code comparison) |
| `artifacts/*.py` | Artifact store Python package (source code) |
| `frontend/`, `config/`, `prompts/`, etc. | Application source |
| `config/.env.example` | API key template (copy to `.env` for live migration) |

## What stays local (in `.gitignore`)

| Path | Why |
|------|-----|
| `.env` | API keys |
| `.venv/`, `AI-SDLC/` | Virtual environments |
| `cache/`, `outputs/`, `logs/` | Generated at runtime |
| `artifacts/proj_*/` (except demo project) | Other migration runs |
| `history/*.db` | Local SQLite history |

## Setup on a new machine

```powershell
git clone <your-repo-url> AI-SDLC
cd AI-SDLC
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
streamlit run frontend/app.py
```

Demo mode is enabled in `config/default.yaml` — no API key required for **Run Demo Pipeline (0 tokens)**.

For live Claude migration, copy `config/.env.example` to `.env` and set `ANTHROPIC_API_KEY`.
