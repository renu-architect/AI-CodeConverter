# Module Specifications

Detailed specifications for every module. Implement exactly as described.

---

## 1. AI Gateway (`gateway/`)

### Purpose
Sole module authorized to communicate with Claude API.

### Responsibilities
| Function | Description |
|----------|-------------|
| `complete()` | Send prompt, return parsed response |
| `estimate_tokens()` | Pre-flight token count |
| `estimate_cost()` | Pre-flight cost in USD |
| `build_prompt()` | Assemble from template + variables |
| `compress_context()` | Truncate/summarize input to token budget |
| `cache_lookup()` | Hash-based DiskCache check |
| `parse_response()` | Extract JSON/Markdown from response |

### Algorithm: `complete()`
```
1. template = load_prompt(template_name)
2. prompt = build_prompt(template, variables)
3. context = compress_context(context, max_tokens=config.max_context_tokens)
4. cache_key = sha256(prompt + context)
5. if cache_hit(cache_key): return cached
6. tokens_in = count_tokens(prompt + context)
7. if tokens_in > limit: raise ContextTooLargeError
8. response = anthropic.messages.create(
     model=config.model,
     temperature=0,
     top_p=0.1,
     max_tokens=dynamic_max(tokens_in),
     messages=[{role: "user", content: prompt + context}]
   )
9. parsed = parse_response(response, expected_format)
10. cache_store(cache_key, parsed)
11. log_to_langfuse(prompt, response, tokens, cost, latency)
12. return GatewayResponse(parsed, tokens_in, tokens_out, cost, latency)
```

### Retry Policy
- Max retries: 3
- Backoff: 1s, 2s, 4s
- Retry on: 429, 500, 502, 503, timeout
- No retry on: 400, 401, context too large

---

## 2. Repository Scanner (`parser/`)

### Purpose
Deterministic repository analysis. **No LLM.**

### Responsibilities
| Function | Description |
|----------|-------------|
| `scan()` | Walk directory, classify files |
| `extract_ast()` | Parse Python AST → summary |
| `detect_glue_jobs()` | Find Glue entry points |
| `build_dependency_graph()` | Import/call graph |
| `score_complexity()` | 0–100 score |

### Glue Detection Signals
```python
GLUE_IMPORTS = [
    "awsglue.transforms",
    "awsglue.utils",
    "awsglue.context",
    "awsglue.job",
    "awsglue.dynamicframe",
]
GLUE_CALLS = [
    "GlueContext", "DynamicFrame", "ApplyMapping",
    "ResolveChoice", "DropNullFields", "getResolvedOptions",
    "Job.init", "Job.commit", "create_dynamic_frame",
    "write_dynamic_frame", "from_catalog", "from_options",
]
```

### Complexity Scoring
| Factor | Weight | Scoring |
|--------|--------|---------|
| Lines of code | 20% | 0-500=low, 500-1500=med, 1500+=high |
| Glue API count | 25% | count unique APIs × 5 |
| Transform count | 20% | joins + aggregations + mappings |
| External deps | 15% | import count |
| SQL files | 10% | presence + count |
| Error handling | 10% | try/except blocks |

### Output
`project.json` — see [05-ARTIFACT-SPECIFICATIONS.md](./05-ARTIFACT-SPECIFICATIONS.md)

---

## 3. Workflow Orchestrator (`orchestrator/`)

### Purpose
Central coordinator. Only module that invokes agents.

### Responsibilities
- Manage workflow state machine
- Invoke agents in sequence
- Handle retries and failures
- Store artifacts after each stage
- Estimate costs before execution
- Emit events for UI
- Checkpoint for resume
- Generate final output package (ZIP)

### Key Methods
```python
async def start_workflow(project_id, repo_path, job_names, developer) -> WorkflowRun
async def approve_plan(workflow_id, approved: bool, comments: str) -> None
async def resume_workflow(workflow_id) -> WorkflowRun
async def abort_workflow(workflow_id) -> None
def get_status(workflow_id) -> WorkflowStatus
def estimate_cost(repo_path, job_names) -> CostEstimate
```

### Retry Logic
| Stage | Max Retries | On Failure |
|-------|-------------|------------|
| SCAN | 1 | Abort |
| ANALYZE | 2 | Abort |
| PLAN | 2 | Abort |
| IMPLEMENT | 3 | Return to PLAN if structural |
| REVIEW | 3 | Delta loop to IMPLEMENT |
| VALIDATE | 2 | Delta loop to IMPLEMENT |
| TEST | 2 | Continue with warning |
| DOCUMENT | 2 | Continue with warning |

### Checkpoint
Save to SQLite after each stage completion:
```json
{
  "workflow_id": "uuid",
  "stage": "REVIEWING",
  "artifacts": {"understanding": "path/v2.md", ...},
  "iteration": 2,
  "timestamp": "ISO8601"
}
```

---

## 4. Analyzer Agent (`agents/analyzer/`)

### Input
| Artifact | Required |
|----------|----------|
| Glue job `.py` file | Yes |
| `project.json` dependency summary | Yes |
| Top-5 knowledge patterns | Optional |

### Context Sent to LLM
- Job name, file path
- AST summary (imports, functions, calls, variables)
- Relevant code sections (not full file if > 2000 tokens)
- Dependency list from project.json
- Similar migration patterns from knowledge base

### Output
`Understanding.md` — see artifact spec

### Cache Key
`sha256(job_file_content + prompt_version)`

---

## 5. Planner Agent (`agents/planner/`)

### Input
- `Understanding.md`

### Output
- `MigrationPlan.md`

### Must Include
- Step-by-step migration plan
- Glue API → Synapse API mapping table
- Library replacements (e.g., `awsglue` → `pyspark` + `mssparkutils`)
- Expected challenges
- Complexity estimate (LOW/MEDIUM/HIGH/CRITICAL)
- Token and cost estimates
- `developer_approval_required: true`

---

## 6. Implementer Agent (`agents/implementer/`)

### Input
| Mode | Context |
|------|---------|
| Full | Understanding + Plan + coding standards + top-5 patterns |
| Delta | Failed sections only + 10-line margin + plan excerpt |

### Output
| File | Description |
|------|-------------|
| `{job_name}_synapse.py` | Converted Python |
| `ConversionNotes.md` | API replacements, decisions |
| `MigrationSummary.md` | High-level summary |

### Coding Standards (from config)
- Python 3.12, type hints, PEP8
- Use `pyspark.sql` instead of DynamicFrame
- Use `mssparkutils` for filesystem operations
- Synapse pool configuration via spark.conf
- Structured logging with `logging` module
- Error handling with specific exceptions

---

## 7. Reviewer Agent (`agents/reviewer/`)

### Comparison Matrix
| Check | Weight | Method |
|-------|--------|--------|
| Business logic | 25% | LLM semantic compare |
| Input sources | 15% | Schema + path compare |
| Output targets | 15% | Schema + path compare |
| Transformations | 20% | Mapping chain compare |
| Error handling | 10% | Pattern compare |
| Performance | 10% | Heuristic check |
| Security | 5% | Credential/secret scan |

### Output on Failure
```json
{
  "status": "FAILED",
  "failed_sections": [
    {
      "check": "transformations",
      "line_start": 45,
      "line_end": 67,
      "issue": "Join logic differs: Glue uses left join, Synapse uses inner",
      "severity": "HIGH",
      "suggestion": "Change join type to left"
    }
  ]
}
```

**CRITICAL:** Never return the entire converted file on failure.

---

## 8. Validator Agent (`agents/validator/`)

### Scoring
| Category | Weight | Pass Threshold |
|----------|--------|----------------|
| Business intent | 30% | ≥ 80% |
| Transformation accuracy | 25% | ≥ 85% |
| Schema accuracy | 20% | ≥ 90% |
| Migration completeness | 15% | ≥ 95% |
| Performance impact | 10% | ≥ 70% |

**Overall pass:** weighted score ≥ 85

### Output
`Validation.md` with per-category scores and overall score.

---

## 9. Tester Agent (`agents/tester/`)

### Output
| Artifact | Description |
|----------|-------------|
| `TestCases.md` | Test plan document |
| `test_{job_name}.py` | Generated pytest file |
| `conftest.py` | Fixtures and mocks |
| `mock_data/` | Sample input data |

### Test Categories
1. Unit tests — individual transformations
2. Integration tests — end-to-end with mock Spark session
3. Edge cases — null handling, empty DataFrames, schema mismatches
4. Performance tests — row count benchmarks (stub)

---

## 10. Documentation Agent (`agents/documentation/`)

### Output Package
```
outputs/{project_id}/{job_id}/
├── converted/
│   └── {job_name}_synapse.py
├── tests/
│   ├── test_{job_name}.py
│   └── conftest.py
├── docs/
│   ├── README.md
│   ├── Architecture.md
│   ├── MigrationSummary.md
│   ├── KnownIssues.md
│   ├── Assumptions.md
│   └── DeploymentGuide.md
├── artifacts/
│   ├── Understanding.md
│   ├── MigrationPlan.md
│   ├── Review.md
│   ├── Validation.md
│   └── TestCases.md
└── Metrics.json
```

---

## 11. Knowledge Engine (`knowledge/`)

### ChromaDB Collections
| Collection | Contents |
|------------|----------|
| `glue_patterns` | Glue API usage patterns |
| `synapse_patterns` | Synapse equivalent patterns |
| `corrections` | Developer manual fixes |
| `business_rules` | Extracted business logic rules |

### Retrieval
```python
def retrieve(query: str, collection: str, top_k: int = 5) -> list[KnowledgeMatch]
```

### Storage (post-migration)
```python
def store_migration(
    understanding: str,
    plan: str,
    converted_code: str,
    review: str,
    developer_corrections: list[str] | None,
    confidence: float
) -> None
```

---

## 12. Artifact Store (`artifacts/`)

### Versioning
- Every write increments version: `v1`, `v2`, `v3`...
- Content hash (SHA-256) stored in metadata
- Immutable — never overwrite, always append version

### Path Pattern
```
artifacts/{project_id}/{job_id}/{artifact_type}/v{N}.{ext}
```

---

## 13. Base Agent (`agents/base_agent.py`)

All agents inherit from `BaseAgent`:

```python
class BaseAgent(ABC):
    name: str
    gateway: AIGateway
    artifact_store: ArtifactStore
    config: AgentConfig

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult: ...

    def load_prompt(self, template_name: str) -> str: ...
    def save_artifact(self, content: str, artifact_type: str) -> ArtifactRef: ...
    def log_execution(self, result: AgentResult) -> None: ...
```
