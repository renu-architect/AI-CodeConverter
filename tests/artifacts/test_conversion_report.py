"""Tests for conversion report builder."""

from artifacts.conversion_report import (
    build_conversion_report,
    format_code_with_line_numbers,
)
from artifacts.store import FileArtifactStore


def test_format_code_with_line_numbers_highlights_ranges():
    code = "a\nb\nc\nd\ne"
    result = format_code_with_line_numbers(code, highlight_ranges=[(2, 3)])
    assert ">>>" in result
    assert "| b" in result
    assert "| c" in result


def test_build_conversion_report_from_artifacts(tmp_path, sample_glue_job_path):
    store = FileArtifactStore(base_dir=tmp_path / "artifacts")
    project_id = "proj_test"
    job_id = "job_customer_etl"
    source_file = "jobs/customer_etl.py"

    store.write(project_id, job_id, "converted_code", "print('synapse')\nprint('done')\n")
    store.write(
        project_id,
        job_id,
        "Review.md",
        """
| 1 | Business Logic | 80 | ✅ PASS |
| 2 | Output Targets | 40 | ❌ FAIL |
```json
{"failed_sections": [{"check": "output", "line_start": 2, "line_end": 2,
"issue": "missing write", "severity": "HIGH", "suggestion": "add write"}]}
```
""",
    )

    report = build_conversion_report(
        store,
        project_id,
        job_id,
        "customer_etl",
        str(sample_glue_job_path),
        source_file,
        failure_stage="REVIEWING",
        attempts_used=3,
        max_attempts=3,
    )

    assert report.converted_lines == 2
    assert report.original_lines > 0
    assert report.success_pct == 60.0  # avg of 80 and 40
    assert len(report.failed_sections) == 1
    assert "customer_etl" in report.message
