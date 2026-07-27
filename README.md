# AI-SDLC Framework

Enterprise AI-powered SDLC framework for migrating AWS Glue ETL jobs to Azure Synapse Spark Python.

## Quick Start

1. Clone the repo and install: `pip install -e .`
2. **Demo (no API key):** `streamlit run frontend/app.py` → use **Run Demo Pipeline (0 tokens)**
3. **Live migration:** copy `config/.env.example` to `.env` and set `ANTHROPIC_API_KEY`
4. Run tests: `pytest tests/ -v`

See [Demo Deployment](docs/DEMO-DEPLOYMENT.md) for what is committed to Git vs kept local.

The API key from `.env` is loaded automatically and used by `gateway/` for all Claude API calls.

## Documentation

| Document | Description |
|----------|-------------|
| [Implementation Guide](docs/01-CURSOR-IMPLEMENTATION-GUIDE.md) | Phased build plan with Cursor prompts |
| [Architecture](docs/02-ARCHITECTURE.md) | System design and data flow |
| [Module Specs](docs/03-MODULE-SPECIFICATIONS.md) | Per-module responsibilities |
| [Interfaces](docs/04-INTERFACES-AND-CONTRACTS.md) | Python ABCs and Pydantic models |
| [Artifacts](docs/05-ARTIFACT-SPECIFICATIONS.md) | Output schemas |
| [Prompts](docs/06-PROMPT-LIBRARY.md) | LLM prompt templates |
| [Glue→Synapse](docs/13-GLUE-TO-SYNAPSE-MAPPING.md) | API mapping reference |

## Tech Stack

Python 3.12 · Streamlit · Claude API · ChromaDB · SQLite · Langfuse

## Status

**Implementation complete (Phases 1–6).** Observability (Phase 7) deferred. Run `pytest tests/ -v` to verify. Start UI with `streamlit run frontend/app.py`.
