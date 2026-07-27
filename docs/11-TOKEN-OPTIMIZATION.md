# Token Optimization Strategy

Token efficiency is a **primary design requirement**. Target: ≤ 50K tokens per single-job migration.

---

## Strategy Overview

| # | Technique | Savings | Module |
|---|-----------|---------|--------|
| 1 | Caveman prompting | 30-40% | gateway |
| 2 | Context compression | 50-70% | gateway |
| 3 | Delta context (review loop) | 60-80% on retries | orchestrator |
| 4 | Prompt templates (no rebuild) | 10-15% | gateway |
| 5 | Artifact passing (not chat) | 40-50% | all agents |
| 6 | Smart cache (file hash) | 100% on cache hit | gateway |
| 7 | AST extraction (not raw source) | 60-80% | parser |
| 8 | Top-K retrieval (not all knowledge) | 90%+ | knowledge |
| 9 | Deterministic output (no fluff) | 20-30% | all agents |
| 10 | Claude params (temp=0, top_p=0.1) | 10-15% | gateway |

---

## 1. Caveman Prompting

### Bad (wasteful)
```
You are an expert AWS Glue and Azure Synapse migration specialist with
20 years of experience. Please carefully analyze the following AWS Glue
ETL job and provide a comprehensive understanding document that covers
all aspects of the job including its business purpose, technical
implementation, and migration considerations...
```

### Good (caveman)
```
TASK: Analyze AWS Glue ETL job.
INPUT: Job: customer_etl, AST: {...}, Code: {...}
RULES: All APIs, transforms, risks. No Synapse suggestions.
OUTPUT: Understanding.md schema. Markdown only.
```

**Implementation:** All prompts in `prompts/*.yaml` follow caveman format.

---

## 2. Context Compression

### Algorithm
```python
def compress_context(context: str, max_tokens: int) -> str:
    current_tokens = count_tokens(context)
    if current_tokens <= max_tokens:
        return context

    # Priority order for compression:
    # 1. Replace raw code with AST summary
    # 2. Truncate long code sections (keep first/last N lines)
    # 3. Summarize dependency lists
    # 4. Remove comments and docstrings from code
    # 5. Truncate knowledge patterns to title + first line

    compressed = replace_code_with_ast(context)
    if count_tokens(compressed) <= max_tokens:
        return compressed

    compressed = truncate_sections(compressed, max_tokens)
    return compressed
```

### Token Budget Allocation
| Content Type | Max Tokens | Method |
|-------------|------------|--------|
| AST summary | 1,500 | Always send |
| Code sections | 3,000 | Relevant functions only |
| Dependencies | 500 | File names only |
| Knowledge patterns | 1,000 | Top-5 titles + snippets |
| Prior artifacts | 4,000 | Latest version only |

---

## 3. Delta Context

On review failure, send ONLY failed sections:

```python
def build_delta_context(failed_sections: list[FailedSection], full_code: str) -> str:
    lines = full_code.split("\n")
    delta_parts = []
    for section in failed_sections:
        margin = 10
        start = max(0, section.line_start - margin)
        end = min(len(lines), section.line_end + margin)
        delta_parts.append({
            "issue": section.issue,
            "suggestion": section.suggestion,
            "code": "\n".join(lines[start:end])
        })
    return json.dumps(delta_parts)
```

**Savings:** Full code ~3000 tokens → delta ~500 tokens per retry.

---

## 4. Smart Cache

```python
def cache_key(template: str, variables: dict, context: str) -> str:
    payload = f"{template}|{json.dumps(variables, sort_keys=True)}|{context}"
    return hashlib.sha256(payload.encode()).hexdigest()

def should_cache(agent_name: str, source_hash: str) -> bool:
    """Analyzer cache keyed on source file hash."""
    if agent_name == "analyzer":
        return cache_exists(f"analyzer:{source_hash}")
    return False
```

### Cache Invalidation
- Source file hash changes → invalidate analyzer cache
- Prompt version changes → invalidate all caches for that template
- TTL expiry (default 24h)

---

## 5. AST Extraction

Instead of sending 500-line Glue job, send:

```json
{
  "file": "customer_etl.py",
  "lines": 125,
  "imports": ["awsglue.context", "pyspark.sql.functions"],
  "functions": [
    {"name": "main", "lines": "25-120", "calls": ["GlueContext", "ApplyMapping", "write_dynamic_frame"]}
  ],
  "glue_apis": [
    {"api": "create_dynamic_frame.from_catalog", "line": 45, "args": "database=analytics, table=customers"},
    {"api": "ApplyMapping", "line": 55, "args": "mappings=[...]"}
  ]
}
```

**~200 tokens vs ~3000 tokens for raw source.**

Only include actual code for:
- Functions with Glue API calls
- Functions flagged as complex by scanner
- Sections referenced in failed review

---

## 6. Retrieval (Top-K)

```python
# Never send entire knowledge base
patterns = knowledge_engine.retrieve(
    query=f"Glue {api_name} migration Synapse",
    collection="glue_patterns",
    top_k=5  # NOT all patterns
)
```

Each pattern snippet: max 200 tokens. Total knowledge context: max 1000 tokens.

---

## 7. Token Estimation (Pre-flight)

Before workflow starts, estimate total cost:

```python
def estimate_workflow_cost(jobs: list[GlueJob]) -> CostEstimate:
    per_job = {
        "analyze": (3000, 2000),
        "plan": (4000, 3000),
        "implement": (12000, 8000),
        "review": (8000, 3000),
        "validate": (5000, 1000),
        "test": (4000, 4000),
        "document": (3000, 2000),
    }
    # Adjust by complexity score
    for job in jobs:
        multiplier = 1.0 + (job.complexity_score / 100)
        ...
```

Display to developer before approval. Developer can cancel if too expensive.

---

## 8. Monitoring Token Usage

Every LLM call logged to `llm_calls` table:
- Track actual vs estimated
- Alert if actual > estimate × 1.5
- Dashboard shows token trends

---

## Token Budget per Job Complexity

| Complexity | Target Tokens | Target Cost |
|------------|--------------|-------------|
| LOW (0-30) | 15,000-25,000 | $0.05-0.10 |
| MEDIUM (31-60) | 25,000-40,000 | $0.10-0.20 |
| HIGH (61-80) | 40,000-60,000 | $0.20-0.35 |
| CRITICAL (81-100) | 60,000-100,000 | $0.35-0.60 |

If actual exceeds 1.5× target, orchestrator logs warning and suggests manual review.
