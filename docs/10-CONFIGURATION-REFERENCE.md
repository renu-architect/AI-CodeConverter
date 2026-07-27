# Configuration Reference

## File Hierarchy

```
config/
├── default.yaml          # Committed defaults
├── user.yaml             # User overrides (gitignored)
└── .env.example          # Environment variable template
```

Load order: `default.yaml` → `user.yaml` → environment variables (highest priority).

---

## default.yaml

```yaml
app:
  name: "AI-SDLC Framework"
  version: "1.0.0"
  log_level: "INFO"
  output_dir: "outputs/"
  artifacts_dir: "artifacts/"

claude:
  model: "claude-sonnet-4-20250514"
  temperature: 0.0
  top_p: 0.1
  max_retries: 3
  timeout_seconds: 120
  # API key from env: ANTHROPIC_API_KEY

agents:
  max_context_tokens: 8000
  max_output_tokens: 4096
  prompt_version: "1.0"
  validation_threshold: 85
  max_implement_iterations: 3
  max_review_iterations: 3

cache:
  enabled: true
  directory: "cache/"
  ttl_seconds: 86400  # 24 hours

knowledge:
  embedding_model: "all-MiniLM-L6-v2"
  chroma_persist_dir: "knowledge/vector_db/"
  top_k: 5
  collections:
    - glue_patterns
    - synapse_patterns
    - corrections
    - business_rules

database:
  url: "sqlite:///history/aisdlc.db"

scanner:
  max_file_size_mb: 10
  ignore_patterns:
    - "__pycache__"
    - ".git"
    - "node_modules"
    - "*.pyc"
    - ".venv"

observability:
  langfuse:
    enabled: false
    # Keys from env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
    host: "https://cloud.langfuse.com"
  opentelemetry:
    enabled: false
    service_name: "ai-sdlc"
    endpoint: "http://localhost:4317"

coding_standards:
  python_version: "3.12"
  style: "PEP8"
  type_hints: true
  logging_module: "logging"
  error_handling: true

cost_estimation:
  # Per-million-token pricing (USD)
  input_price_per_million: 3.0
  output_price_per_million: 15.0
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | No | Langfuse secret key |
| `AI_SDLC_CONFIG` | No | Override config file path |
| `AI_SDLC_LOG_LEVEL` | No | Override log level |
| `AI_SDLC_DB_URL` | No | Override database URL |

---

## .env.example

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional — Observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# Optional — Overrides
AI_SDLC_LOG_LEVEL=DEBUG
AI_SDLC_DB_URL=sqlite:///history/aisdlc.db
```

---

## Config Loader

```python
# utils/config_loader.py

import os
import yaml
from pathlib import Path
from utils.config_models import AppConfig

def load_config() -> AppConfig:
    config_dir = Path(os.getenv("AI_SDLC_CONFIG", "config"))

    with open(config_dir / "default.yaml") as f:
        config = yaml.safe_load(f)

    user_config = config_dir / "user.yaml"
    if user_config.exists():
        with open(user_config) as f:
            user = yaml.safe_load(f)
            config = deep_merge(config, user)

    # Env overrides
    if os.getenv("ANTHROPIC_API_KEY"):
        config.setdefault("claude", {})["api_key"] = os.environ["ANTHROPIC_API_KEY"]
    if os.getenv("AI_SDLC_LOG_LEVEL"):
        config["app"]["log_level"] = os.environ["AI_SDLC_LOG_LEVEL"]
    if os.getenv("AI_SDLC_DB_URL"):
        config["database"]["url"] = os.environ["AI_SDLC_DB_URL"]

    return AppConfig(**flatten_config(config))
```

---

## Coding Standards Config

Passed to Implementer agent as `{{coding_standards}}`:

```yaml
coding_standards:
  python_version: "3.12"
  style: "PEP8"
  type_hints: true
  rules:
    - "Use pyspark.sql functions, not RDD API"
    - "Use mssparkutils for filesystem operations"
    - "Structured logging with logging module"
    - "Specific exception types, not bare except"
    - "No hardcoded credentials or connection strings"
    - "Docstrings on public functions"
    - "Constants in UPPER_CASE at module level"
```

---

## Gitignore Entries

```gitignore
# Config secrets
config/user.yaml
.env

# Runtime data
cache/
artifacts/
outputs/
logs/
knowledge/vector_db/
history/aisdlc.db

# Python
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
```
