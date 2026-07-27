# Prompt Library

All prompts follow **Caveman Prompting** — minimal, task-focused, no fluff.

## Rules (All Prompts)

1. No "You are an expert..." preambles
2. Structure: Task → Input → Rules → Output Format
3. Stored as YAML in `prompts/` directory
4. Versioned: `prompts/analyzer.yaml`, version field inside
5. Temperature: 0, deterministic output
6. Response must be Markdown or JSON only — no conversational text

---

## Prompt File Format

```yaml
# prompts/analyzer.yaml
name: analyzer
version: "1.0"
expected_format: markdown
max_output_tokens: 4096
system: ""  # empty — no system prompt fluff
template: |
  TASK: Analyze AWS Glue ETL job. Produce Understanding.md.

  INPUT:
  Job: {{job_name}}
  File: {{file_path}}
  Complexity: {{complexity_score}}

  AST Summary:
  {{ast_summary}}

  Code Sections:
  {{code_sections}}

  Dependencies:
  {{dependencies}}

  Similar Patterns:
  {{knowledge_patterns}}

  RULES:
  - Document ALL Glue API usage
  - Identify ALL transformations (joins, filters, aggregations, mappings)
  - Flag bookmarks, catalog usage, error handling
  - Assess migration complexity and risks
  - Confidence score 0.0-1.0
  - Do NOT suggest Synapse code

  OUTPUT FORMAT: Markdown matching Understanding.md schema exactly.
  Sections: Metadata, Business Purpose, Input Sources, Output Targets,
  Glue Context, Dynamic Frames, Transformations, Bookmarks, Catalog Usage,
  Error Handling, Dependencies, Migration Complexity, Risks, Confidence.
```

---

## Analyzer Prompt

```yaml
name: analyzer
version: "1.0"
expected_format: markdown
template: |
  TASK: Analyze AWS Glue ETL job.

  INPUT:
  Job: {{job_name}}
  File: {{file_path}}
  AST: {{ast_summary}}
  Code: {{code_sections}}
  Deps: {{dependencies}}
  Patterns: {{knowledge_patterns}}

  RULES:
  - All Glue APIs, transforms, joins, filters, aggregations
  - Bookmarks, catalog, error handling
  - Complexity + risks + confidence (0.0-1.0)
  - No Synapse suggestions

  OUTPUT: Understanding.md schema. Markdown only.
```

---

## Planner Prompt

```yaml
name: planner
version: "1.0"
expected_format: markdown
template: |
  TASK: Create migration plan Glue → Azure Synapse Spark.

  INPUT:
  {{understanding_md}}

  RULES:
  - Step-by-step migration plan
  - Glue API → Synapse API mapping table
  - Library changes (remove/add)
  - Expected challenges with severity
  - Complexity: LOW|MEDIUM|HIGH|CRITICAL
  - Estimate tokens, cost, time
  - developer_approval_required: true
  - Use Synapse Spark Python (pyspark + mssparkutils)

  OUTPUT: MigrationPlan.md schema. Markdown only.
```

---

## Implementer Prompt (Full Mode)

```yaml
name: implementer_full
version: "1.0"
expected_format: markdown
template: |
  TASK: Convert Glue job to Azure Synapse Spark Python.

  INPUT:
  Understanding: {{understanding_md}}
  Plan: {{migration_plan_md}}
  Standards: {{coding_standards}}
  Patterns: {{knowledge_patterns}}

  RULES:
  - Python 3.12, type hints, PEP8
  - pyspark.sql instead of DynamicFrame
  - mssparkutils for filesystem
  - Preserve ALL business logic exactly
  - Structured logging
  - Error handling with specific exceptions
  - No hardcoded credentials

  OUTPUT: Three sections separated by ---ARTIFACT_BOUNDARY---
  Section 1: Complete Python code (```python block)
  Section 2: ConversionNotes.md
  Section 3: MigrationSummary.md
```

---

## Implementer Prompt (Delta Mode)

```yaml
name: implementer_delta
version: "1.0"
expected_format: markdown
template: |
  TASK: Fix failed sections in Synapse conversion.

  INPUT:
  Failed Sections: {{failed_sections_json}}
  Surrounding Code: {{delta_code_context}}
  Plan Excerpt: {{plan_excerpt}}

  RULES:
  - Fix ONLY the failed sections
  - Preserve all other code unchanged
  - Match original business logic

  OUTPUT: Fixed code sections as JSON array:
  [{"line_start": N, "line_end": N, "fixed_code": "..."}]
```

---

## Reviewer Prompt

```yaml
name: reviewer
version: "1.0"
expected_format: markdown
template: |
  TASK: Review converted code against original Glue job.

  INPUT:
  Original: {{original_code_summary}}
  Understanding: {{understanding_md}}
  Plan: {{migration_plan_md}}
  Converted: {{converted_code}}

  CHECKS:
  - Business logic preserved
  - Input sources correct
  - Output targets correct (schema, paths, partitions)
  - Transformations match (joins, filters, aggregations, mappings)
  - Error handling adequate
  - Performance acceptable
  - No security issues (hardcoded secrets)

  RULES:
  - Score each check 0-100
  - Status: PASSED if all checks >= 70
  - On failure: return ONLY failed_sections with line ranges
  - NEVER return entire file in failed_sections

  OUTPUT: Review.md schema with embedded failed_sections JSON.
```

---

## Validator Prompt

```yaml
name: validator
version: "1.0"
expected_format: markdown
template: |
  TASK: Semantic validation of migration.

  INPUT:
  Understanding: {{understanding_md}}
  Plan: {{migration_plan_md}}
  Converted: {{converted_code}}
  Review: {{review_md}}

  CATEGORIES:
  - Business intent (30%)
  - Transformation accuracy (25%)
  - Schema accuracy (20%)
  - Migration completeness (15%)
  - Performance impact (10%)

  RULES:
  - Score each category 0-100
  - Overall = weighted average
  - PASSED if overall >= 85

  OUTPUT: Validation.md schema. Markdown only.
```

---

## Tester Prompt

```yaml
name: tester
version: "1.0"
expected_format: markdown
template: |
  TASK: Generate tests for migrated Synapse job.

  INPUT:
  Understanding: {{understanding_md}}
  Converted: {{converted_code}}

  RULES:
  - pytest format
  - Mock SparkSession (no real cluster)
  - Unit tests for each transformation
  - Integration test stub for end-to-end
  - Edge cases: nulls, empty, schema mismatch
  - Include conftest.py with fixtures

  OUTPUT: Two sections separated by ---ARTIFACT_BOUNDARY---
  Section 1: TestCases.md (test plan)
  Section 2: Python test code (```python block)
```

---

## Documentation Prompt

```yaml
name: documentation
version: "1.0"
expected_format: markdown
template: |
  TASK: Generate migration documentation package.

  INPUT:
  Understanding: {{understanding_md}}
  Plan: {{migration_plan_md}}
  Review: {{review_md}}
  Validation: {{validation_md}}
  Tests: {{test_cases_md}}
  Metrics: {{metrics_json}}

  RULES:
  - README: overview, prerequisites, how to run
  - Architecture: component diagram (mermaid), data flow
  - MigrationSummary: what changed, key decisions
  - KnownIssues: unresolved items
  - Assumptions: what was assumed during migration
  - DeploymentGuide: Synapse workspace setup, pool config

  OUTPUT: Six sections separated by ---DOC_BOUNDARY---
  Each section: # {DocName}\n\n{content}
```

---

## Context Compression Templates

Used by Gateway before sending to Claude:

```python
# AST compression — send this instead of raw source
AST_TEMPLATE = """
File: {file_path} ({line_count} lines)
Imports: {imports}
Functions: {function_summary}
Glue APIs: {glue_calls}
Key Variables: {variables}
"""

# Code section extraction — only relevant lines
CODE_SECTION_TEMPLATE = """
--- Section: {section_name} (lines {start}-{end}) ---
{code}
"""
```

---

## Token Budget per Stage

| Stage | Max Input | Max Output | Template |
|-------|-----------|------------|----------|
| Analyze | 6,000 | 4,000 | analyzer |
| Plan | 8,000 | 4,000 | planner |
| Implement (full) | 12,000 | 8,000 | implementer_full |
| Implement (delta) | 3,000 | 2,000 | implementer_delta |
| Review | 10,000 | 3,000 | reviewer |
| Validate | 8,000 | 2,000 | validator |
| Test | 8,000 | 6,000 | tester |
| Document | 10,000 | 4,000 | documentation |
