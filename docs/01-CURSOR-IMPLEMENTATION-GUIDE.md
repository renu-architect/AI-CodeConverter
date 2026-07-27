# Cursor Implementation Guide

This is the **primary execution document** for building AI-SDLC with Cursor Desktop. Follow phases in order. Complete acceptance criteria before advancing.

---

## General Cursor Rules for This Project

1. **One module per Cursor session** — do not ask Cursor to build multiple agents at once.
2. **Always provide context files** — attach the relevant doc sections and interface contracts.
3. **Run tests after each module** — `pytest tests/<module>/ -v`.
4. **Use this prompt prefix** for every implementation session:

```
You are implementing the AI-SDLC Framework for AWS Glue → Azure Synapse migration.
Follow docs/04-INTERFACES-AND-CONTRACTS.md exactly.
Use YAML config from config/. No hardcoded values.
Temperature 0 for all LLM calls via gateway only.
Output structured artifacts per docs/05-ARTIFACT-SPECIFICATIONS.md.
Include unit tests and logging.
```

---

## Phase 1: Project Skeleton & Foundation

### Session 1.1 — Project Setup

**Cursor prompt:**
```
Create the AI-SDLC project skeleton per docs/README.md folder structure.
Add pyproject.toml with Python 3.12, dependencies: streamlit, anthropic, chromadb,
sentence-transformers, diskcache, pyyaml, pydantic, langfuse, opentelemetry-api,
opentelemetry-sdk, sqlalchemy, pytest, pytest-asyncio, pytest-mock.
Add config/default.yaml with all keys from docs/10-CONFIGURATION-REFERENCE.md.
Add config/.env.example. Add utils/logging.py with structured JSON logging.
Add utils/exceptions.py with AISDLCError hierarchy.
Do NOT implement agents yet.
```

**Files to create:**
- `pyproject.toml`
- `config/default.yaml`
- `config/.env.example`
- `utils/__init__.py`, `utils/logging.py`, `utils/exceptions.py`, `utils/config_loader.py`
- `tests/conftest.py`

**Acceptance criteria:**
- [ ] `pip install -e .` succeeds
- [ ] `from utils.config_loader import load_config` returns valid dict
- [ ] `pytest tests/` runs (even if empty)

---

### Session 1.2 — AI Gateway

**Cursor prompt:**
```
Implement gateway/ per docs/03-MODULE-SPECIFICATIONS.md § Gateway and
docs/04-INTERFACES-AND-CONTRACTS.md § AIGateway.
This is the ONLY module that calls Claude API.
Include: prompt building, context compression, template loading from prompts/,
DiskCache caching (hash prompt+context), retries (3x exponential backoff),
token counting, cost estimation, response parsing to structured output.
Temperature=0, top_p=0.1. Log every call via utils/logging.py.
```

**Files:**
- `gateway/__init__.py`
- `gateway/gateway.py`
- `gateway/token_counter.py`
- `gateway/cost_estimator.py`
- `gateway/cache.py`
- `gateway/response_parser.py`
- `tests/gateway/test_gateway.py`

**Acceptance criteria:**
- [ ] Mocked Claude call returns parsed JSON/Markdown
- [ ] Cache hit on identical prompt hash
- [ ] Token count and cost estimate logged
- [ ] No Anthropic import outside `gateway/`

---

### Session 1.3 — Repository Scanner

**Cursor prompt:**
```
Implement parser/ (repository scanner) per docs/03-MODULE-SPECIFICATIONS.md § Scanner.
NO LLM calls. Parse Python AST, detect Glue jobs (GlueContext, DynamicFrame,
getResolvedOptions, Job), build dependency graph, score complexity.
Output project.json per docs/05-ARTIFACT-SPECIFICATIONS.md § project.json.
```

**Files:**
- `parser/__init__.py`
- `parser/scanner.py`
- `parser/ast_extractor.py`
- `parser/glue_detector.py`
- `parser/dependency_graph.py`
- `parser/complexity_scorer.py`
- `tests/parser/test_scanner.py`
- `tests/fixtures/sample_glue_job.py`

**Acceptance criteria:**
- [ ] Scans fixture repo and produces valid `project.json`
- [ ] Detects Glue imports and API calls
- [ ] Dependency graph has correct edges
- [ ] Complexity score is 0–100

---

## Phase 2: Orchestrator & Early Agents

### Session 2.1 — Artifact Store

**Cursor prompt:**
```
Implement artifacts/ store per docs/05-ARTIFACT-SPECIFICATIONS.md.
Versioned storage: each write creates artifacts/{project_id}/{job_id}/{artifact_type}/v{N}.md.
Support read latest, read version, list versions, compute content hash.
Use pathlib. SQLite metadata in history/ per docs/07-DATABASE-SCHEMA.md.
```

**Files:**
- `artifacts/__init__.py`
- `artifacts/store.py`
- `artifacts/models.py`
- `history/db.py`
- `history/models.py`
- `tests/artifacts/test_store.py`

**Acceptance criteria:**
- [ ] Write v1, write v2, read latest returns v2
- [ ] Content hash stored in SQLite
- [ ] All artifact types from spec supported

---

### Session 2.2 — Workflow Orchestrator

**Cursor prompt:**
```
Implement orchestrator/ per docs/03-MODULE-SPECIFICATIONS.md § Orchestrator and
docs/02-ARCHITECTURE.md § Orchestrator State Machine.
Manage workflow stages, retries, failures, checkpoints, cost estimation.
ONLY the orchestrator invokes agents via AgentRegistry.
Agents cannot invoke each other. Store state in SQLite.
Emit events for Streamlit UI consumption.
```

**Files:**
- `orchestrator/__init__.py`
- `orchestrator/orchestrator.py`
- `orchestrator/state_machine.py`
- `orchestrator/events.py`
- `orchestrator/registry.py`
- `tests/orchestrator/test_orchestrator.py`

**Acceptance criteria:**
- [ ] State transitions: SCAN → ANALYZE → PLAN → APPROVE → IMPLEMENT → REVIEW → VALIDATE → TEST → DOCUMENT → COMPLETE
- [ ] Checkpoint save/restore works
- [ ] Retry logic on agent failure (max 3)
- [ ] Only orchestrator imports agent modules

---

### Session 2.3 — Analyzer Agent

**Cursor prompt:**
```
Implement agents/analyzer/ per docs/03-MODULE-SPECIFICATIONS.md § Analyzer.
Input: Glue job source + project.json dependency summary.
Use gateway for LLM. Use prompt from prompts/analyzer.yaml.
Output: Understanding.md per docs/05-ARTIFACT-SPECIFICATIONS.md.
Send AST summary + relevant code sections only (not full file if > 2000 tokens).
Check cache by source file hash before calling LLM.
```

**Files:**
- `agents/analyzer/__init__.py`
- `agents/analyzer/agent.py`
- `agents/base_agent.py`
- `prompts/analyzer.yaml`
- `tests/agents/test_analyzer.py`

**Acceptance criteria:**
- [ ] Produces valid Understanding.md from fixture Glue job
- [ ] Cache reuse on unchanged file
- [ ] All required sections present in output

---

### Session 2.4 — Planner Agent

**Cursor prompt:**
```
Implement agents/planner/ per docs/03-MODULE-SPECIFICATIONS.md § Planner.
Input: Understanding.md. Output: MigrationPlan.md.
Include Glue→Synapse API mapping from docs/13-GLUE-TO-SYNAPSE-MAPPING.md.
Estimate tokens and cost. Flag developer_approval_required: true.
```

**Files:**
- `agents/planner/__init__.py`
- `agents/planner/agent.py`
- `prompts/planner.yaml`
- `tests/agents/test_planner.py`

**Acceptance criteria:**
- [ ] MigrationPlan.md has all required sections
- [ ] Token/cost estimates are numeric
- [ ] API replacement table included

---

## Phase 3: Conversion Pipeline

### Session 3.1 — Implementer Agent

**Cursor prompt:**
```
Implement agents/implementer/ per docs/03-MODULE-SPECIFICATIONS.md § Implementer.
Input: Understanding.md, MigrationPlan.md, coding standards from config.
Output: converted .py file, ConversionNotes.md, MigrationSummary.md.
Retrieve top-5 similar patterns from knowledge/ (stub if not built yet).
On reviewer delta input: send ONLY failed sections + surrounding 10 lines context.
```

**Acceptance criteria:**
- [ ] Produces syntactically valid Python
- [ ] Delta mode sends < 500 lines context
- [ ] ConversionNotes document all API replacements

---

### Session 3.2 — Reviewer Agent

**Cursor prompt:**
```
Implement agents/reviewer/ per docs/03-MODULE-SPECIFICATIONS.md § Reviewer.
Compare original Glue, Understanding, Plan, converted code.
Output: Review.md with pass/fail per section.
On failure: return ONLY failed_sections array with line ranges — never full file.
```

**Acceptance criteria:**
- [ ] Review.md has per-check pass/fail
- [ ] Failed sections include line_start, line_end, issue, severity
- [ ] Overall status: PASSED or FAILED

---

### Session 3.3 — Validator Agent

**Cursor prompt:**
```
Implement agents/validator/ per docs/03-MODULE-SPECIFICATIONS.md § Validator.
Semantic comparison. Output: Validation.md with score 0-100.
Checks: business intent, transformations, schema, completeness, performance.
```

**Acceptance criteria:**
- [ ] Validation score calculated
- [ ] Score < 85 triggers orchestrator retry loop
- [ ] All check categories scored individually

---

## Phase 4: Knowledge & History

### Session 4.1 — Knowledge Engine + ChromaDB

**Cursor prompt:**
```
Implement knowledge/ per docs/03-MODULE-SPECIFICATIONS.md § Knowledge Engine.
ChromaDB collections: glue_patterns, synapse_patterns, corrections, business_rules.
Embed with sentence-transformers model from config.
Retrieve top-K (default 5). Store after each successful migration.
```

**Acceptance criteria:**
- [ ] Embed and retrieve returns relevant patterns
- [ ] Post-migration storage includes all artifact hashes
- [ ] Search by natural language query works

---

### Session 4.2 — History & Metrics

**Cursor prompt:**
```
Implement history/ metrics queries per docs/07-DATABASE-SCHEMA.md.
Track: projects, migrations, iterations, tokens, cost, review score, runtime.
Expose MetricsService for dashboard consumption.
```

**Acceptance criteria:**
- [ ] Migration record created on workflow start
- [ ] Metrics aggregated for dashboard
- [ ] History searchable by date, project, developer

---

## Phase 5: Testing & Documentation Agents

### Session 5.1 — Tester Agent

**Cursor prompt:**
```
Implement agents/tester/ per docs/03-MODULE-SPECIFICATIONS.md § Tester.
Generate unit tests, integration test stubs, mock data, edge cases.
Output: TestCases.md + actual test files in outputs/{project}/tests/.
```

---

### Session 5.2 — Documentation Agent

**Cursor prompt:**
```
Implement agents/documentation/ per docs/03-MODULE-SPECIFICATIONS.md § Documentation.
Generate: README.md, Architecture.md, MigrationSummary.md, KnownIssues.md,
Assumptions.md, DeploymentGuide.md into output package.
```

---

## Phase 6: Streamlit Frontend

### Session 6.1 — App Shell + Dashboard

**Cursor prompt:**
```
Implement frontend/ per docs/08-STREAMLIT-UI-SPECIFICATION.md.
Start with app.py, navigation, Dashboard page, Settings page.
Wire to orchestrator events. Use st.session_state for workflow state.
```

### Session 6.2 — Repository + Plan + Execution Pages

Implement: Repository Selection, Migration Plan (with approval), Live Execution.

### Session 6.3 — History + Knowledge Pages

Implement: History (with download), Knowledge search.

**Acceptance criteria (all UI):**
- [ ] All 7 pages functional
- [ ] Real-time progress during execution
- [ ] Token/cost estimates shown before approval
- [ ] Download output package as ZIP

---

## Phase 7: Observability

### Session 7.1 — Langfuse + OpenTelemetry

**Cursor prompt:**
```
Implement observability per docs/12-OBSERVABILITY.md.
Trace every gateway call in Langfuse. OTel spans for orchestrator stages.
```

---

## Verification Checklist (Full System)

- [ ] End-to-end migration of sample Glue job completes
- [ ] All artifacts versioned and downloadable
- [ ] Knowledge base updated post-migration
- [ ] Token usage within estimate ± 20%
- [ ] Review loop works (inject failure, verify delta fix)
- [ ] Checkpoint resume after simulated crash
- [ ] No API keys in logs or database
- [ ] `pytest tests/ -v` all pass

---

## Recommended Cursor Session Workflow

```
1. Open relevant doc sections as context (@docs/...)
2. Open interface contracts (@docs/04-INTERFACES-AND-CONTRACTS.md)
3. Paste session prompt from this guide
4. Review generated code — check imports, no LLM outside gateway
5. Run pytest for that module
6. Fix failures in follow-up Cursor messages
7. Mark acceptance criteria complete
8. Git commit (when ready): "feat(<module>): implement <name>"
```
