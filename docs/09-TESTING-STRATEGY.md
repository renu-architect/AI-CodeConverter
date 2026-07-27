# Testing Strategy

## Test Structure

```
tests/
├── conftest.py               # Shared fixtures
├── fixtures/
│   ├── sample_glue_job.py    # Simple Glue ETL job
│   ├── complex_glue_job.py   # Multi-transform job
│   ├── sample_repo/          # Mini repo for scanner
│   └── mock_responses/       # Canned Claude responses
├── gateway/
│   └── test_gateway.py
├── parser/
│   └── test_scanner.py
├── orchestrator/
│   └── test_orchestrator.py
├── artifacts/
│   └── test_store.py
├── agents/
│   ├── test_analyzer.py
│   ├── test_planner.py
│   ├── test_implementer.py
│   ├── test_reviewer.py
│   ├── test_validator.py
│   ├── test_tester.py
│   └── test_documentation.py
├── knowledge/
│   └── test_engine.py
├── history/
│   └── test_db.py
└── test_architecture.py      # Import boundary enforcement
```

---

## conftest.py

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_glue_job():
    return (FIXTURES_DIR / "sample_glue_job.py").read_text()

@pytest.fixture
def mock_gateway():
    gateway = AsyncMock()
    gateway.complete.return_value = GatewayResponse(
        content="# Understanding\ntest content",
        parsed="# Understanding\ntest content",
        tokens_input=100,
        tokens_output=200,
        cost_usd=0.001,
        latency_ms=500,
        cached=False,
        model="claude-sonnet-4-20250514"
    )
    gateway.estimate_tokens.return_value = 1000
    gateway.estimate_cost.return_value = 0.05
    return gateway

@pytest.fixture
def temp_artifact_store(tmp_path):
    return ArtifactStore(base_dir=tmp_path / "artifacts")

@pytest.fixture
def temp_db(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    init_db(db_url)
    return db_url

@pytest.fixture
def sample_project_scan():
    return ProjectScan(...)  # from fixture JSON
```

---

## Test Categories

### Unit Tests (per module)
- Test in isolation with mocked dependencies
- No real Claude API calls
- No real ChromaDB (use temp directory)

### Integration Tests
- Orchestrator + agents with mock gateway
- Scanner + artifact store with real filesystem
- Full workflow with canned responses

### Architecture Tests
```python
# tests/test_architecture.py

FORBIDDEN_IMPORTS = {
    "agents": ["anthropic", "agents."],
    "parser": ["gateway", "anthropic"],
    "frontend": ["gateway", "agents."],
}

def test_no_direct_anthropic_in_agents():
    """Agents must not import anthropic directly."""
    for agent_file in Path("agents").rglob("*.py"):
        content = agent_file.read_text()
        assert "import anthropic" not in content
        assert "from anthropic" not in content

def test_no_agent_to_agent_imports():
    """Agents must not import other agents."""
    for agent_file in Path("agents").rglob("*.py"):
        if agent_file.name == "base_agent.py":
            continue
        content = agent_file.read_text()
        for other in ["analyzer", "planner", "implementer", "reviewer", "validator", "tester", "documentation"]:
            agent_name = agent_file.parent.name
            if agent_name != other:
                assert f"from agents.{other}" not in content
                assert f"import agents.{other}" not in content
```

---

## Agent Test Pattern

```python
# tests/agents/test_analyzer.py

import pytest
from agents.analyzer.agent import AnalyzerAgent

@pytest.mark.asyncio
async def test_analyzer_produces_understanding(mock_gateway, temp_artifact_store, sample_glue_job):
    agent = AnalyzerAgent(
        gateway=mock_gateway,
        artifact_store=temp_artifact_store,
        config=AgentConfig()
    )
    context = AgentContext(
        workflow_id="test-wf",
        project_id="test-proj",
        job_id="test-job",
        job_name="sample_etl",
        stage="ANALYZING"
    )

    result = await agent.execute(context)

    assert result.success
    assert len(result.artifacts_created) == 1
    assert result.artifacts_created[0].artifact_type == "Understanding.md"
    mock_gateway.complete.assert_called_once()

@pytest.mark.asyncio
async def test_analyzer_uses_cache(mock_gateway, temp_artifact_store):
    """Second call with same input should hit cache."""
    # ... setup with cache enabled
    # First call
    await agent.execute(context)
    # Second call — gateway should report cached=True
    mock_gateway.complete.return_value.cached = True
    result = await agent.execute(context)
    assert result.metadata.get("cached") is True
```

---

## Scanner Test Pattern

```python
# tests/parser/test_scanner.py

def test_detect_glue_jobs(sample_repo_path):
    scanner = RepositoryScanner()
    result = scanner.scan(sample_repo_path)

    assert len(result.glue_jobs) >= 1
    assert result.glue_jobs[0].name == "sample_etl"
    assert "GlueContext" in str(result.glue_jobs[0].ast_summary.glue_api_calls)

def test_complexity_score_range(sample_repo_path):
    scanner = RepositoryScanner()
    result = scanner.scan(sample_repo_path)
    assert 0 <= result.glue_jobs[0].complexity_score <= 100

def test_dependency_graph(sample_repo_path):
    scanner = RepositoryScanner()
    result = scanner.scan(sample_repo_path)
    assert len(result.dependency_graph.nodes) > 0
```

---

## Orchestrator Integration Test

```python
# tests/orchestrator/test_orchestrator.py

@pytest.mark.asyncio
async def test_full_workflow_happy_path(mock_gateway, temp_artifact_store, temp_db, sample_repo_path):
    """End-to-end workflow with mocked LLM responses."""
    orch = WorkflowOrchestrator(
        gateway=mock_gateway,
        artifact_store=temp_artifact_store,
        scanner=RepositoryScanner(),
        registry=build_test_registry(mock_gateway, temp_artifact_store),
        db_url=temp_db
    )

    workflow_id = await orch.start_workflow(
        project_id="test",
        repo_path=sample_repo_path,
        job_names=["sample_etl"],
        developer="tester"
    )

    # Simulate approval
    await orch.approve_plan(workflow_id, approved=True)

    # Wait for completion (with timeout)
    status = await wait_for_stage(orch, workflow_id, "COMPLETE", timeout=30)
    assert status.stage == "COMPLETE"
    assert status.tokens_used > 0

@pytest.mark.asyncio
async def test_review_retry_loop(mock_gateway, ...):
    """Reviewer fails → implementer delta fix → reviewer passes."""
    # Configure mock: first review FAIL, second review PASS
    ...
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Single module
pytest tests/gateway/ -v

# With coverage
pytest tests/ -v --cov=. --cov-report=term-missing

# Architecture tests only
pytest tests/test_architecture.py -v
```

---

## CI Configuration (Future)

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --cov=. --cov-fail-under=80
```

---

## Coverage Targets

| Module | Min Coverage |
|--------|-------------|
| gateway | 90% |
| parser | 85% |
| orchestrator | 80% |
| agents (each) | 80% |
| artifacts | 90% |
| knowledge | 75% |
| utils | 85% |
| **Overall** | **80%** |
