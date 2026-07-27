# PRD & Vision Summary

## Vision

Build an enterprise-grade AI-powered SDLC framework that automatically converts AWS Glue ETL jobs into Azure Synapse Spark Python jobs using an intelligent multi-agent architecture.

The system functions as an **AI Software Factory** — not a chatbot. Each agent has a single responsibility, communicates through structured artifacts, and minimizes LLM token usage.

## Primary Objectives

| Objective | Success Criteria |
|-----------|------------------|
| Accurate conversion | Business logic preserved; validator score ≥ 85% |
| Enterprise quality | PEP8, type hints, error handling, logging |
| Token efficiency | ≤ 50K tokens per single-job migration (typical) |
| Learning | Knowledge base improves with each migration |
| Human-in-the-loop | Developer approval before implementation |
| Observability | Full trace: tokens, cost, time, agent logs |
| Extensibility | Plugin-ready architecture for future targets |

## Scope — v1.0

| Dimension | Supported |
|-----------|-----------|
| Source | AWS Glue Python jobs |
| Target | Azure Synapse Spark Python |
| File types | `.py`, `.sql`, `.json`, `.yaml`, `.txt` (requirements) |

## Future Scope

Databricks, Microsoft Fabric, Snowflake, EMR, Azure Data Factory, Spark Standalone.

## Workflow (End-to-End)

```
Developer → Streamlit UI → Orchestrator
  → Repository Scanner (no LLM)
  → Analyzer → Understanding.md
  → Planner → MigrationPlan.md
  → Developer Approval
  → Implementer → converted .py
  → Reviewer → Review.md (delta on failure)
  → Validator → Validation.md
  → Tester → TestCases.md
  → Documentation Agent → README, reports
  → Knowledge Engine update
  → Output Package download
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12 |
| Frontend | Streamlit |
| LLM | Claude API (Anthropic) |
| Embeddings | sentence-transformers |
| Vector DB | ChromaDB |
| Relational DB | SQLite |
| Cache | DiskCache |
| Observability | Langfuse, OpenTelemetry |
| AST | Python `ast` module |
| Config | YAML |

## Non-Functional Requirements

- **Modularity:** Each agent is a standalone Python package with clear I/O contracts.
- **Auditability:** Every artifact versioned; every LLM call logged.
- **Security:** API keys via env vars only; never persisted.
- **Resilience:** Retry, checkpoint, resume workflow.
- **Determinism:** Temperature 0; structured output only.

## Out of Scope (v1.0)

- Azure AD authentication
- Multi-LLM support (GPT, Gemini)
- GitHub/Azure DevOps integration
- Batch scheduling
- MCP integration
