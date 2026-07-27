# Database Schema

SQLite database at `history/aisdlc.db`. Managed via SQLAlchemy.

---

## Tables

### projects

```sql
CREATE TABLE projects (
    project_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    repo_path       TEXT NOT NULL,
    repo_hash       TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    developer       TEXT,
    status          TEXT DEFAULT 'active'  -- active, archived
);
```

### workflows

```sql
CREATE TABLE workflows (
    workflow_id     TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(project_id),
    stage           TEXT NOT NULL DEFAULT 'IDLE',
    progress_pct    REAL DEFAULT 0.0,
    current_agent   TEXT,
    current_file    TEXT,
    iteration       INTEGER DEFAULT 1,
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP,
    elapsed_seconds INTEGER DEFAULT 0,
    tokens_used     INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    status          TEXT DEFAULT 'running',  -- running, complete, failed, cancelled
    error           TEXT,
    checkpoint      TEXT  -- JSON blob for resume
);
```

### migrations (one per job per workflow)

```sql
CREATE TABLE migrations (
    migration_id    TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL REFERENCES workflows(workflow_id),
    project_id      TEXT NOT NULL REFERENCES projects(project_id),
    job_id          TEXT NOT NULL,
    job_name        TEXT NOT NULL,
    source_file     TEXT NOT NULL,
    complexity_score REAL,
    review_score    REAL,
    validation_score REAL,
    iterations_impl INTEGER DEFAULT 0,
    iterations_review INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'pending',
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP
);
```

### artifacts

```sql
CREATE TABLE artifacts (
    artifact_id     TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    migration_id    TEXT REFERENCES migrations(migration_id),
    artifact_type   TEXT NOT NULL,
    version         INTEGER NOT NULL,
    file_path       TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    size_bytes      INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by      TEXT,  -- agent name
    UNIQUE(project_id, job_id, artifact_type, version)
);
```

### llm_calls

```sql
CREATE TABLE llm_calls (
    call_id         TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    migration_id    TEXT,
    agent_name      TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    model           TEXT NOT NULL,
    tokens_input    INTEGER NOT NULL,
    tokens_output   INTEGER NOT NULL,
    cost_usd        REAL NOT NULL,
    latency_ms      INTEGER NOT NULL,
    cached          BOOLEAN DEFAULT FALSE,
    success         BOOLEAN DEFAULT TRUE,
    error           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### approvals

```sql
CREATE TABLE approvals (
    approval_id     TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL REFERENCES workflows(workflow_id),
    migration_id    TEXT,
    developer       TEXT NOT NULL,
    approved        BOOLEAN NOT NULL,
    comments        TEXT,
    plan_version    INTEGER,
    estimated_cost  REAL,
    estimated_tokens INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### knowledge_entries

```sql
CREATE TABLE knowledge_entries (
    entry_id        TEXT PRIMARY KEY,
    project_id      TEXT,
    job_id          TEXT,
    collection      TEXT NOT NULL,  -- glue_patterns, synapse_patterns, corrections, business_rules
    content         TEXT NOT NULL,
    embedding_id    TEXT,  -- ChromaDB ID
    confidence      REAL,
    source          TEXT,  -- migration, developer_correction, manual
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### metrics_daily

```sql
CREATE TABLE metrics_daily (
    date            TEXT PRIMARY KEY,  -- YYYY-MM-DD
    total_jobs      INTEGER DEFAULT 0,
    completed_jobs  INTEGER DEFAULT 0,
    failed_jobs     INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    total_cost_usd  REAL DEFAULT 0.0,
    avg_review_score REAL,
    avg_validation_score REAL,
    avg_iterations  REAL,
    avg_duration_seconds REAL,
    cache_hits      INTEGER DEFAULT 0,
    knowledge_hits  INTEGER DEFAULT 0
);
```

---

## SQLAlchemy Models

```python
# history/models.py

from sqlalchemy import Column, String, Integer, Float, Boolean, Text, TIMESTAMP, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    project_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    repo_path = Column(String, nullable=False)
    repo_hash = Column(String, nullable=False)
    developer = Column(String)
    status = Column(String, default="active")
    workflows = relationship("Workflow", back_populates="project")

class Workflow(Base):
    __tablename__ = "workflows"
    workflow_id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.project_id"))
    stage = Column(String, default="IDLE")
    progress_pct = Column(Float, default=0.0)
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    status = Column(String, default="running")
    checkpoint = Column(Text)
    project = relationship("Project", back_populates="workflows")
    migrations = relationship("Migration", back_populates="workflow")

# ... similar for Migration, Artifact, LLMCall, Approval, KnowledgeEntry, MetricsDaily
```

---

## Key Queries

### Dashboard Metrics
```sql
SELECT
    COUNT(*) as total_jobs,
    SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    AVG(review_score) as avg_review,
    SUM(tokens_used) as total_tokens,
    SUM(cost_usd) as total_cost
FROM migrations m
JOIN workflows w ON m.workflow_id = w.workflow_id
WHERE w.started_at >= date('now', '-30 days');
```

### Migration History
```sql
SELECT m.job_name, m.status, m.review_score, m.validation_score,
       w.tokens_used, w.cost_usd, w.elapsed_seconds, w.completed_at
FROM migrations m
JOIN workflows w ON m.workflow_id = w.workflow_id
WHERE m.project_id = ?
ORDER BY w.started_at DESC;
```

### Token Usage by Stage
```sql
SELECT agent_name, SUM(tokens_input) as input, SUM(tokens_output) as output,
       SUM(cost_usd) as cost, COUNT(*) as calls,
       SUM(CASE WHEN cached THEN 1 ELSE 0 END) as cache_hits
FROM llm_calls
WHERE workflow_id = ?
GROUP BY agent_name;
```

---

## Migration Script

```python
# history/db.py

def init_db(database_url: str) -> None:
    """Create all tables if not exist."""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
```

Run on app startup: `init_db(config.database_url)`
