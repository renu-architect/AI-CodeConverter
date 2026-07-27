# AI-SDLC Framework — Implementation Documentation

**Version:** 1.0  
**Target IDE:** Cursor Desktop  
**Target LLM:** Claude API (Anthropic)  
**Stack:** Python 3.12 · Streamlit · ChromaDB · SQLite · Langfuse

This documentation set is the authoritative implementation guide for building the AI-SDLC Framework: an enterprise multi-agent system that migrates AWS Glue ETL jobs to Azure Synapse Spark Python.

---

## How to Use This Documentation with Cursor

1. **Read first:** [01-CURSOR-IMPLEMENTATION-GUIDE.md](./01-CURSOR-IMPLEMENTATION-GUIDE.md) — phased build order with acceptance criteria and Cursor prompts.
2. **Follow phases sequentially** — never generate the entire application in one step.
3. **Reference contracts** before implementing any module: [04-INTERFACES-AND-CONTRACTS.md](./04-INTERFACES-AND-CONTRACTS.md).
4. **Copy artifact schemas** exactly: [05-ARTIFACT-SPECIFICATIONS.md](./05-ARTIFACT-SPECIFICATIONS.md).
5. **Use prompt templates** from: [06-PROMPT-LIBRARY.md](./06-PROMPT-LIBRARY.md).
6. **Configure via YAML:** [10-CONFIGURATION-REFERENCE.md](./10-CONFIGURATION-REFERENCE.md).

---

## Document Index

| # | Document | Purpose |
|---|----------|---------|
| 00 | [PRD & Vision Summary](./00-PRD-VISION-SUMMARY.md) | Condensed product requirements |
| 01 | [Cursor Implementation Guide](./01-CURSOR-IMPLEMENTATION-GUIDE.md) | **Start here** — phased build plan |
| 02 | [Architecture](./02-ARCHITECTURE.md) | System design, data flow, component diagram |
| 03 | [Module Specifications](./03-MODULE-SPECIFICATIONS.md) | Per-module responsibilities, I/O, algorithms |
| 04 | [Interfaces & Contracts](./04-INTERFACES-AND-CONTRACTS.md) | Python ABCs, Pydantic models, type contracts |
| 05 | [Artifact Specifications](./05-ARTIFACT-SPECIFICATIONS.md) | Markdown/JSON schemas for all artifacts |
| 06 | [Prompt Library](./06-PROMPT-LIBRARY.md) | Caveman prompts, templates, token rules |
| 07 | [Database Schema](./07-DATABASE-SCHEMA.md) | SQLite tables, migrations, queries |
| 08 | [Streamlit UI Specification](./08-STREAMLIT-UI-SPECIFICATION.md) | Pages, components, state management |
| 09 | [Testing Strategy](./09-TESTING-STRATEGY.md) | Unit, integration, agent test patterns |
| 10 | [Configuration Reference](./10-CONFIGURATION-REFERENCE.md) | YAML config, env vars, secrets |
| 11 | [Token Optimization](./11-TOKEN-OPTIMIZATION.md) | Caching, compression, delta context |
| 12 | [Observability](./12-OBSERVABILITY.md) | Langfuse, OpenTelemetry, logging |
| 13 | [Glue-to-Synapse Mapping](./13-GLUE-TO-SYNAPSE-MAPPING.md) | API replacements, patterns, pitfalls |

---

## Project Folder Structure (Target)

```
AI-SDLC/
├── frontend/                 # Streamlit app
│   ├── app.py
│   ├── pages/
│   └── components/
├── orchestrator/             # Workflow engine
├── agents/
│   ├── analyzer/
│   ├── planner/
│   ├── implementer/
│   ├── reviewer/
│   ├── validator/
│   ├── tester/
│   └── documentation/
├── gateway/                  # Claude API gateway (sole LLM entry point)
├── parser/                   # AST, Glue detection, dependency graph
├── knowledge/                # Knowledge engine + ChromaDB
├── artifacts/                # Artifact store (versioned)
├── cache/                    # DiskCache layer
├── history/                  # Migration history DB access
├── config/                   # YAML configuration
├── prompts/                  # Prompt template files
├── utils/                    # Shared utilities
├── tests/
├── logs/
├── outputs/                  # Final migration packages
├── reports/
└── docs/                     # This documentation
```

---

## Development Phases (Summary)

| Phase | Modules | Est. Sessions |
|-------|---------|---------------|
| 1 | Skeleton, config, gateway, scanner | 2–3 |
| 2 | Orchestrator, artifact store, analyzer, planner | 3–4 |
| 3 | Implementer, reviewer, validator | 3–4 |
| 4 | Knowledge engine, vector DB, history | 2–3 |
| 5 | Tester, documentation agent, metrics | 2–3 |
| 6 | Streamlit UI (all pages) | 3–4 |
| 7 | Observability (Langfuse, OTel) | 1–2 |
| 8 | Enterprise (auth, plugins, multi-LLM) | Future |

---

## Critical Design Rules

1. **Only the Orchestrator invokes agents.** Agents never call each other.
2. **Only the Gateway talks to Claude.** No direct API calls elsewhere.
3. **Agents exchange structured artifacts** (Markdown, JSON, YAML) — never raw chat history.
4. **Temperature = 0**, deterministic output formats only.
5. **Delta context on review failures** — send only failed sections back to implementer.
6. **Every module is independently testable** before moving to the next phase.
