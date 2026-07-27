# Observability

## Components

| Tool | Purpose | Scope |
|------|---------|-------|
| Structured Logging | All actions | Every module |
| Langfuse | LLM call tracing | Gateway only |
| OpenTelemetry | Workflow spans | Orchestrator + agents |
| SQLite | Metrics persistence | History DB |
| Metrics.json | Per-migration summary | Output package |

---

## Structured Logging

### Format
```json
{
  "timestamp": "2026-07-25T10:22:15.123Z",
  "level": "INFO",
  "module": "agents.reviewer",
  "workflow_id": "wf_xyz789",
  "agent": "reviewer",
  "action": "execute",
  "duration_ms": 3200,
  "tokens": 5200,
  "cost_usd": 0.031,
  "message": "Review completed: FAILED (2 sections)",
  "metadata": {
    "iteration": 2,
    "failed_checks": ["output_targets", "transformations"]
  }
}
```

### Implementation
```python
# utils/logging.py

import logging
import json
from datetime import datetime, timezone

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, "workflow_id"):
            log_entry["workflow_id"] = record.workflow_id
        if hasattr(record, "metadata"):
            log_entry["metadata"] = record.metadata
        return json.dumps(log_entry)
```

### Log Files
```
logs/
├── app.log              # All logs (rotated daily)
├── gateway.log          # LLM calls only
├── orchestrator.log     # Workflow events
└── errors.log           # ERROR and above only
```

---

## Langfuse Integration

### Setup
```python
# gateway/langfuse_client.py

from langfuse import Langfuse

class LangfuseTracer:
    def __init__(self, config: ObservabilityConfig):
        self.enabled = config.langfuse.enabled
        if self.enabled:
            self.client = Langfuse(
                public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                host=config.langfuse.host
            )

    def trace_llm_call(
        self,
        name: str,
        input_prompt: str,
        output: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
        latency_ms: int,
        metadata: dict
    ) -> None:
        if not self.enabled:
            return
        trace = self.client.trace(name=name, metadata=metadata)
        trace.generation(
            name=name,
            model=model,
            input=input_prompt,
            output=output,
            usage={
                "input": tokens_input,
                "output": tokens_output
            },
            metadata={"latency_ms": latency_ms}
        )
```

### What Gets Traced
- Every `gateway.complete()` call
- Prompt template name and version
- Input/output tokens and cost
- Cache hit/miss
- Agent name and workflow ID

---

## OpenTelemetry Integration

### Setup
```python
# utils/telemetry.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def init_telemetry(config: ObservabilityConfig) -> trace.Tracer:
    if not config.opentelemetry.enabled:
        return trace.get_tracer("ai-sdlc")
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=config.opentelemetry.endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(config.opentelemetry.service_name)
```

### Span Hierarchy
```
workflow (orchestrator)
├── scan (parser)
├── analyze (analyzer agent)
│   └── llm_call (gateway)
├── plan (planner agent)
│   └── llm_call (gateway)
├── implement (implementer agent)
│   └── llm_call (gateway)
├── review (reviewer agent)
│   └── llm_call (gateway)
├── validate (validator agent)
│   └── llm_call (gateway)
├── test (tester agent)
│   └── llm_call (gateway)
└── document (documentation agent)
    └── llm_call (gateway)
```

### Usage in Orchestrator
```python
async def _execute_stage(self, stage: str, context: AgentContext):
    with self.tracer.start_as_current_span(f"stage.{stage.lower()}") as span:
        span.set_attribute("workflow_id", context.workflow_id)
        span.set_attribute("job_name", context.job_name)
        span.set_attribute("iteration", context.iteration)
        result = await self.registry.get(stage).execute(context)
        span.set_attribute("tokens_used", result.tokens_used)
        span.set_attribute("success", result.success)
        return result
```

---

## Metrics Dashboard Data

Queried from SQLite for Streamlit Dashboard:

```python
class MetricsService:
    def get_dashboard_metrics(self, days: int = 30) -> dict:
        return {
            "total_jobs": ...,
            "completed_jobs": ...,
            "failed_jobs": ...,
            "success_rate": ...,
            "avg_cost_usd": ...,
            "avg_tokens": ...,
            "avg_review_score": ...,
            "avg_duration_minutes": ...,
            "pattern_reuse_count": ...,
            "knowledge_hits": ...,
            "developer_overrides": ...,
            "hours_saved_estimate": ...,  # avg_duration × completed_jobs
            "cache_hit_rate": ...,
        }
```

---

## Error Tracking

All errors logged with full context:

```python
logger.error(
    "Agent execution failed",
    extra={
        "workflow_id": context.workflow_id,
        "agent": self.name,
        "error": str(e),
        "metadata": {
            "stage": context.stage,
            "iteration": context.iteration,
            "retry_count": retry_count
        }
    }
)
```

Errors also stored in `workflows.error` column for UI display.
