"""Shared Pydantic models for artifacts and agent communication."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ArtifactRef(BaseModel):
    project_id: str
    job_id: str
    artifact_type: str
    version: int
    path: str
    content_hash: str
    created_at: datetime


class FailedSection(BaseModel):
    check: str
    line_start: int
    line_end: int
    issue: str
    severity: str
    suggestion: str


class AgentContext(BaseModel):
    workflow_id: str
    project_id: str
    job_id: str
    job_name: str
    stage: str
    iteration: int = 1
    artifacts: dict[str, ArtifactRef] = Field(default_factory=dict)
    delta_sections: Optional[list[FailedSection]] = None
    metadata: dict = Field(default_factory=dict)


class AgentResult(BaseModel):
    success: bool
    artifacts_created: list[ArtifactRef] = Field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


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
    progress_pct: float
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
    event_type: str
    message: str
    metadata: dict = Field(default_factory=dict)
