# Interfaces & Contracts

All Python interfaces, Pydantic models, and type contracts. Implement these exactly.

---

## Enums

```python
# utils/enums.py

from enum import Enum

class WorkflowStage(str, Enum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    REVIEWING = "REVIEWING"
    VALIDATING = "VALIDATING"
    TESTING = "TESTING"
    DOCUMENTING = "DOCUMENTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ArtifactType(str, Enum):
    PROJECT_JSON = "project.json"
    UNDERSTANDING = "Understanding.md"
    MIGRATION_PLAN = "MigrationPlan.md"
    CONVERTED_CODE = "converted_code"
    CONVERSION_NOTES = "ConversionNotes.md"
    MIGRATION_SUMMARY = "MigrationSummary.md"
    REVIEW = "Review.md"
    VALIDATION = "Validation.md"
    TEST_CASES = "TestCases.md"
    README = "README.md"
    METRICS = "Metrics.json"
    APPROVAL = "approval_record.json"

class ReviewStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"

class ComplexityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
```

---

## Core Models

```python
# artifacts/models.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ArtifactRef(BaseModel):
    project_id: str
    job_id: str
    artifact_type: str
    version: int
    path: str
    content_hash: str
    created_at: datetime

class AgentContext(BaseModel):
    workflow_id: str
    project_id: str
    job_id: str
    job_name: str
    stage: str
    iteration: int = 1
    artifacts: dict[str, ArtifactRef] = Field(default_factory=dict)
    delta_sections: Optional[list["FailedSection"]] = None
    metadata: dict = Field(default_factory=dict)

class AgentResult(BaseModel):
    success: bool
    artifacts_created: list[ArtifactRef] = Field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

class FailedSection(BaseModel):
    check: str
    line_start: int
    line_end: int
    issue: str
    severity: str
    suggestion: str

class GatewayRequest(BaseModel):
    template_name: str
    variables: dict[str, str]
    context: str
    expected_format: str  # "markdown" | "json"
    max_output_tokens: Optional[int] = None

class GatewayResponse(BaseModel):
    content: str
    parsed: dict | str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    latency_ms: int
    cached: bool = False
    model: str

class CostEstimate(BaseModel):
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    estimated_duration_seconds: int
    estimated_api_calls: int
    per_stage: dict[str, dict] = Field(default_factory=dict)

class WorkflowStatus(BaseModel):
    workflow_id: str
    project_id: str
    stage: str
    progress_pct: float  # 0.0 - 100.0
    current_agent: Optional[str] = None
    current_file: Optional[str] = None
    iteration: int = 1
    elapsed_seconds: int = 0
    estimated_remaining_seconds: Optional[int] = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None

class WorkflowEvent(BaseModel):
    workflow_id: str
    timestamp: datetime
    stage: str
    event_type: str  # "stage_start" | "stage_complete" | "error" | "approval_needed"
    message: str
    metadata: dict = Field(default_factory=dict)
```

---

## Scanner Models

```python
# parser/models.py

class ASTSummary(BaseModel):
    imports: list[str]
    functions: list[dict]  # {name, line_start, line_end, calls: []}
    classes: list[dict]
    variables: list[str]
    glue_api_calls: list[dict]  # {api, line, args_summary}
    line_count: int

class GlueJob(BaseModel):
    name: str
    file_path: str
    entry_point: str  # function or __main__
    ast_summary: ASTSummary
    complexity_score: float
    dependencies: list[str]  # file paths
    sql_files: list[str]
    config_files: list[str]

class DependencyNode(BaseModel):
    file_path: str
    imports: list[str]
    imported_by: list[str]

class DependencyGraph(BaseModel):
    nodes: list[DependencyNode]
    glue_jobs: list[str]  # file paths

class ProjectScan(BaseModel):
    project_id: str
    repo_path: str
    repo_hash: str
    scanned_at: datetime
    glue_jobs: list[GlueJob]
    dependency_graph: DependencyGraph
    shared_libraries: list[str]
    total_files: int
    total_lines: int
    overall_complexity: float
```

---

## Abstract Base Classes

```python
# agents/base_agent.py

from abc import ABC, abstractmethod

class BaseAgent(ABC):
    name: str

    def __init__(
        self,
        gateway: "AIGateway",
        artifact_store: "ArtifactStore",
        config: "AgentConfig",
    ) -> None: ...

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute agent logic. Must not call other agents."""
        ...

    def load_prompt(self, template_name: str) -> str: ...
    def save_artifact(self, content: str, artifact_type: str, context: AgentContext) -> ArtifactRef: ...


# gateway/gateway.py

class AIGateway(ABC):
    @abstractmethod
    async def complete(self, request: GatewayRequest) -> GatewayResponse: ...

    @abstractmethod
    def estimate_tokens(self, text: str) -> int: ...

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float: ...


# orchestrator/orchestrator.py

class WorkflowOrchestrator(ABC):
    @abstractmethod
    async def start_workflow(
        self, project_id: str, repo_path: str, job_names: list[str], developer: str
    ) -> str: ...  # returns workflow_id

    @abstractmethod
    async def approve_plan(self, workflow_id: str, approved: bool, comments: str = "") -> None: ...

    @abstractmethod
    async def resume_workflow(self, workflow_id: str) -> WorkflowStatus: ...

    @abstractmethod
    async def abort_workflow(self, workflow_id: str) -> None: ...

    @abstractmethod
    def get_status(self, workflow_id: str) -> WorkflowStatus: ...

    @abstractmethod
    def estimate_cost(self, repo_path: str, job_names: list[str]) -> CostEstimate: ...


# parser/scanner.py

class RepositoryScanner(ABC):
    @abstractmethod
    def scan(self, repo_path: str, job_filter: list[str] | None = None) -> ProjectScan: ...


# artifacts/store.py

class ArtifactStore(ABC):
    @abstractmethod
    def write(self, project_id: str, job_id: str, artifact_type: str, content: str) -> ArtifactRef: ...

    @abstractmethod
    def read_latest(self, project_id: str, job_id: str, artifact_type: str) -> str: ...

    @abstractmethod
    def read_version(self, project_id: str, job_id: str, artifact_type: str, version: int) -> str: ...

    @abstractmethod
    def list_versions(self, project_id: str, job_id: str, artifact_type: str) -> list[ArtifactRef]: ...


# knowledge/engine.py

class KnowledgeEngine(ABC):
    @abstractmethod
    def retrieve(self, query: str, collection: str, top_k: int = 5) -> list[dict]: ...

    @abstractmethod
    def store_migration(self, project_id: str, job_id: str, artifacts: dict[str, str], confidence: float) -> None: ...

    @abstractmethod
    def store_correction(self, pattern: str, correction: str, context: str) -> None: ...
```

---

## Agent Registry

```python
# orchestrator/registry.py

class AgentRegistry:
    """Maps stage names to agent instances. Only orchestrator uses this."""

    _agents: dict[str, BaseAgent]

    def register(self, stage: str, agent: BaseAgent) -> None: ...
    def get(self, stage: str) -> BaseAgent: ...
    def list_stages(self) -> list[str]: ...

# Registration (in orchestrator init):
# registry.register("ANALYZING", AnalyzerAgent(...))
# registry.register("PLANNING", PlannerAgent(...))
# registry.register("IMPLEMENTING", ImplementerAgent(...))
# registry.register("REVIEWING", ReviewerAgent(...))
# registry.register("VALIDATING", ValidatorAgent(...))
# registry.register("TESTING", TesterAgent(...))
# registry.register("DOCUMENTING", DocumentationAgent(...))
```

---

## Configuration Models

```python
# utils/config_models.py

class ClaudeConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.0
    top_p: float = 0.1
    max_retries: int = 3
    timeout_seconds: int = 120

class CacheConfig(BaseModel):
    enabled: bool = True
    directory: str = "cache/"
    ttl_seconds: int = 86400

class KnowledgeConfig(BaseModel):
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_persist_dir: str = "knowledge/vector_db/"
    top_k: int = 5

class AgentConfig(BaseModel):
    max_context_tokens: int = 8000
    max_output_tokens: int = 4096
    prompt_version: str = "1.0"

class AppConfig(BaseModel):
    claude: ClaudeConfig
    cache: CacheConfig
    knowledge: KnowledgeConfig
    agents: AgentConfig
    database_url: str = "sqlite:///history/aisdlc.db"
    log_level: str = "INFO"
    output_dir: str = "outputs/"
    artifacts_dir: str = "artifacts/"
```

---

## Exception Hierarchy

```python
# utils/exceptions.py

class AISDLCError(Exception):
    """Base exception."""

class GatewayError(AISDLCError):
    """Claude API errors."""

class ContextTooLargeError(GatewayError):
    """Input exceeds token budget."""

class AgentExecutionError(AISDLCError):
    """Agent failed during execution."""

class WorkflowError(AISDLCError):
    """Orchestrator workflow errors."""

class ArtifactNotFoundError(AISDLCError):
    """Requested artifact version not found."""

class ScanError(AISDLCError):
    """Repository scan failures."""

class ValidationFailedError(AISDLCError):
    """Validator score below threshold."""
    def __init__(self, score: float, threshold: float): ...
```

---

## Import Rules (Enforced by Architecture)

```
ALLOWED:
  agents/* → gateway, artifacts, knowledge, utils
  orchestrator → agents, artifacts, parser, history, utils
  frontend → orchestrator, history, knowledge, utils
  gateway → cache, utils, langfuse

FORBIDDEN:
  agents/* → agents/* (no agent-to-agent)
  agents/* → anthropic (no direct LLM)
  parser → gateway (scanner is deterministic)
  frontend → gateway (UI goes through orchestrator)
  frontend → agents (UI goes through orchestrator)
```

Add a lint test to enforce:

```python
# tests/test_architecture.py
"""Verify import boundaries are not violated."""
```
