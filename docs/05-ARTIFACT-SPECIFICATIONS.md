# Artifact Specifications

Every artifact has a defined schema. Agents must produce output matching these exactly.

---

## project.json

Produced by: Repository Scanner  
Format: JSON

```json
{
  "project_id": "proj_abc123",
  "repo_path": "/path/to/repo",
  "repo_hash": "sha256:...",
  "scanned_at": "2026-07-25T10:00:00Z",
  "total_files": 42,
  "total_lines": 8500,
  "overall_complexity": 67.5,
  "glue_jobs": [
    {
      "name": "customer_etl",
      "file_path": "jobs/customer_etl.py",
      "entry_point": "main",
      "complexity_score": 72.0,
      "dependencies": ["libs/transforms.py", "libs/utils.py"],
      "sql_files": ["sql/customer_merge.sql"],
      "config_files": ["config/job_params.json"],
      "ast_summary": {
        "imports": ["awsglue.context", "pyspark.sql"],
        "functions": [
          {
            "name": "main",
            "line_start": 25,
            "line_end": 120,
            "calls": ["GlueContext", "ApplyMapping", "write_dynamic_frame"]
          }
        ],
        "glue_api_calls": [
          {"api": "GlueContext", "line": 30, "args_summary": "spark_context"},
          {"api": "create_dynamic_frame.from_catalog", "line": 45, "args_summary": "database=analytics, table=customers"}
        ],
        "line_count": 125
      }
    }
  ],
  "dependency_graph": {
    "nodes": [
      {
        "file_path": "jobs/customer_etl.py",
        "imports": ["libs/transforms.py"],
        "imported_by": []
      }
    ],
    "glue_jobs": ["jobs/customer_etl.py"]
  },
  "shared_libraries": ["libs/transforms.py", "libs/utils.py"]
}
```

---

## Understanding.md

Produced by: Analyzer Agent  
Format: Markdown

```markdown
# Understanding: {job_name}

## Metadata
- **Job Name:** customer_etl
- **Source File:** jobs/customer_etl.py
- **Complexity Score:** 72.0
- **Confidence:** 0.92
- **Generated:** 2026-07-25T10:05:00Z
- **Agent Version:** analyzer/1.0

## Business Purpose
Extract customer data from Glue catalog, apply deduplication and enrichment,
write to S3 parquet partitioned by date.

## Input Sources
| Source | Type | Database/Table | Format |
|--------|------|----------------|--------|
| customers | Glue Catalog | analytics.customers | Parquet |
| orders | Glue Catalog | analytics.orders | Parquet |

## Output Targets
| Target | Type | Path/Table | Format | Partition |
|--------|------|------------|--------|-----------|
| enriched_customers | S3 | s3://bucket/enriched/customers/ | Parquet | dt |

## Glue Context
- **Glue Version:** 4.0
- **Worker Type:** G.1X
- **Worker Count:** 10
- **Job Parameters:** --dt, --database

## Dynamic Frames
| Name | Source | Transformation |
|------|--------|----------------|
| dyf_customers | from_catalog(analytics.customers) | none |
| dyf_enriched | ApplyMapping + ResolveChoice | field mapping |

## Transformations
1. **ApplyMapping** (line 55): Rename id→customer_id, cast amount→decimal
2. **ResolveChoice** (line 62): Resolve ambiguous schema for address field
3. **Join** (line 78): Left join customers with orders on customer_id
4. **Filter** (line 85): WHERE dt = job parameter
5. **Aggregate** (line 90): GROUP BY customer_id, SUM(order_total)

## Bookmarks
- Enabled on: analytics.orders
- Bookmark key: dt

## Catalog Usage
- Database: analytics
- Tables read: customers, orders
- Tables written: none (S3 direct)

## Error Handling
- try/except around catalog read (line 40)
- No retry logic
- Logs errors to CloudWatch

## Dependencies
- libs/transforms.py: custom_mapping()
- libs/utils.py: get_job_params()
- sql/customer_merge.sql: referenced but not executed

## Migration Complexity
- **Level:** HIGH
- **Factors:** DynamicFrame usage, bookmarks, catalog reads, custom UDFs

## Risks
| Risk | Severity | Description |
|------|----------|-------------|
| Bookmark migration | HIGH | No direct Synapse equivalent |
| DynamicFrame mapping | MEDIUM | Manual DataFrame column mapping needed |
| Catalog access | MEDIUM | Switch to Synapse dedicated pool tables |

## Confidence
- **Overall:** 0.92
- **Business Logic:** 0.95
- **Technical Details:** 0.89
```

---

## MigrationPlan.md

Produced by: Planner Agent  
Format: Markdown

```markdown
# Migration Plan: {job_name}

## Metadata
- **Job Name:** customer_etl
- **Plan Version:** 1
- **Complexity:** HIGH
- **Estimated Time:** 45 minutes
- **Estimated Input Tokens:** 12,000
- **Estimated Output Tokens:** 8,000
- **Estimated Cost:** $0.18
- **Developer Approval Required:** true

## Migration Steps
1. Replace GlueContext initialization with SparkSession for Synapse
2. Convert DynamicFrame reads to spark.read / spark.sql
3. Replace ApplyMapping with DataFrame.select/alias
4. Replace ResolveChoice with coalesce/when logic
5. Convert bookmark to Delta Lake MERGE or watermark table
6. Replace write_dynamic_frame with DataFrame.write.parquet
7. Update job parameters to Synapse notebook parameters
8. Replace CloudWatch logging with Synapse logging

## API Replacement Mapping
| Glue API | Synapse Equivalent | Notes |
|----------|-------------------|-------|
| GlueContext | SparkSession.builder.getOrCreate() | Standard Spark |
| create_dynamic_frame.from_catalog | spark.sql("SELECT * FROM ...") | Use dedicated pool tables |
| ApplyMapping | df.select(col(...).alias(...)) | Manual mapping |
| ResolveChoice | F.coalesce(...) | Case-by-case |
| write_dynamic_frame.from_options | df.write.format("parquet").save(...) | Direct write |
| getResolvedOptions | mssparkutils.notebook.run() params | Notebook context |
| Job.init/commit | N/A | Synapse manages lifecycle |

## Library Changes
| Remove | Add |
|--------|-----|
| awsglue.* | pyspark.sql.* |
| awsglue.transforms | pyspark.sql.functions |
| - | com.microsoft.spark.sqlanalytics (if SQL Pool write) |

## Expected Challenges
1. Bookmark → Delta MERGE pattern (HIGH effort)
2. Catalog table references need Synapse table mapping (MEDIUM)
3. S3 paths may need ADLS Gen2 paths (LOW)

## Rollback Strategy
Keep original Glue job unchanged. Synapse job runs in parallel until validated.
```

---

## Review.md

Produced by: Reviewer Agent  
Format: Markdown + embedded JSON for machine parsing

```markdown
# Review: {job_name}

## Metadata
- **Review Version:** 1
- **Iteration:** 1
- **Status:** FAILED
- **Overall Score:** 72/100

## Check Results
| Check | Status | Score | Notes |
|-------|--------|-------|-------|
| Business Logic | PASS | 90 | Core flow preserved |
| Input Sources | PASS | 95 | All sources mapped |
| Output Targets | FAIL | 60 | Partition column missing |
| Transformations | FAIL | 65 | Join type changed |
| Error Handling | PASS | 80 | Adequate coverage |
| Performance | PASS | 75 | No obvious issues |
| Security | PASS | 100 | No hardcoded secrets |

## Failed Sections
```json
{
  "failed_sections": [
    {
      "check": "output_targets",
      "line_start": 110,
      "line_end": 115,
      "issue": "Partition column 'dt' not included in write",
      "severity": "HIGH",
      "suggestion": "Add .partitionBy('dt') to write operation"
    },
    {
      "check": "transformations",
      "line_start": 78,
      "line_end": 82,
      "issue": "Inner join used instead of left join",
      "severity": "HIGH",
      "suggestion": "Change .join(orders_df, 'customer_id', 'left')"
    }
  ]
}
```
```

---

## Validation.md

Produced by: Validator Agent

```markdown
# Validation: {job_name}

## Metadata
- **Validation Version:** 1
- **Overall Score:** 88/100
- **Status:** PASSED
- **Threshold:** 85

## Category Scores
| Category | Weight | Score | Status |
|----------|--------|-------|--------|
| Business Intent | 30% | 92 | PASS |
| Transformation Accuracy | 25% | 85 | PASS |
| Schema Accuracy | 20% | 90 | PASS |
| Migration Completeness | 15% | 88 | PASS |
| Performance Impact | 10% | 75 | PASS |

## Detailed Findings
### Business Intent (92/100)
Core ETL flow preserved. Customer enrichment logic matches original.

### Transformation Accuracy (85/100)
All mappings converted. Minor: date format differs (yyyy-MM-dd vs yyyyMMdd).

## Recommendations
- Standardize date format to match downstream consumers
- Add Delta Lake optimization for bookmark replacement
```

---

## TestCases.md

Produced by: Tester Agent

```markdown
# Test Cases: {job_name}

## Coverage Estimate: 78%

## Unit Tests
| ID | Test Name | Description | Input | Expected |
|----|-----------|-------------|-------|----------|
| UT-01 | test_read_customers | Verify catalog read | mock DataFrame | 100 rows |
| UT-02 | test_apply_mapping | Field rename | sample DNF | renamed cols |
| UT-03 | test_join_logic | Left join preserved | 2 DataFrames | left join result |
| UT-04 | test_null_handling | Null in address | DataFrame w/ nulls | coalesced |

## Integration Tests
| ID | Test Name | Description |
|----|-----------|-------------|
| IT-01 | test_end_to_end | Full pipeline with mock data |
| IT-02 | test_partition_write | Verify partition column |

## Edge Cases
- Empty input DataFrame
- All-null partition column
- Schema mismatch between sources
- Duplicate customer_ids

## Generated Files
- tests/test_customer_etl.py
- tests/conftest.py
- tests/mock_data/customers.json
```

---

## Metrics.json

Produced by: Orchestrator (final stage)

```json
{
  "workflow_id": "wf_xyz789",
  "project_id": "proj_abc123",
  "job_id": "job_customer_etl",
  "job_name": "customer_etl",
  "developer": "john.doe",
  "started_at": "2026-07-25T10:00:00Z",
  "completed_at": "2026-07-25T10:45:00Z",
  "duration_seconds": 2700,
  "status": "COMPLETE",
  "iterations": {
    "implement": 2,
    "review": 2,
    "validate": 1
  },
  "tokens": {
    "total_input": 45000,
    "total_output": 22000,
    "by_stage": {
      "analyze": {"input": 3000, "output": 2000},
      "plan": {"input": 4000, "output": 3000},
      "implement": {"input": 20000, "output": 12000},
      "review": {"input": 10000, "output": 3000},
      "validate": {"input": 5000, "output": 1000},
      "test": {"input": 2000, "output": 800},
      "document": {"input": 1000, "output": 200}
    }
  },
  "cost_usd": 0.42,
  "review_score": 92,
  "validation_score": 88,
  "complexity_score": 72.0,
  "knowledge_patterns_used": 3,
  "cache_hits": 1,
  "artifact_versions": {
    "Understanding.md": 1,
    "MigrationPlan.md": 1,
    "Review.md": 2,
    "Validation.md": 1
  }
}
```

---

## approval_record.json

Produced by: Orchestrator (on developer action)

```json
{
  "workflow_id": "wf_xyz789",
  "approved": true,
  "developer": "john.doe",
  "timestamp": "2026-07-25T10:12:00Z",
  "comments": "Plan looks good. Proceed with bookmark → Delta approach.",
  "plan_version": 1,
  "estimated_cost_usd": 0.18,
  "estimated_tokens": 20000
}
```

---

## Versioning Rules

1. Every artifact write creates a new version directory: `v1/`, `v2/`, etc.
2. Version number is monotonically increasing per artifact type per job.
3. Content hash (SHA-256) stored in SQLite metadata.
4. Artifacts are immutable — never modify existing versions.
5. `read_latest()` returns highest version number.
