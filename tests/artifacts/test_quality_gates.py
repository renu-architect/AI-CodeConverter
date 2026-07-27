"""Tests for POC vs strict quality gate logic."""

from artifacts.models import FailedSection
from artifacts.parsers import extract_failed_sections
from artifacts.quality_gates import (
    assess_validation_pass,
    filter_blocking_failures,
)


def test_poc_filters_non_critical_review_failures():
    sections = [
        FailedSection(
            check="style",
            line_start=1,
            line_end=2,
            issue="minor",
            severity="HIGH",
            suggestion="fix",
        ),
        FailedSection(
            check="empty",
            line_start=0,
            line_end=0,
            issue="no code",
            severity="CRITICAL",
            suggestion="implement",
        ),
    ]
    blocking = filter_blocking_failures(sections, poc_mode=True)
    assert len(blocking) == 1
    assert blocking[0].severity == "CRITICAL"


def test_strict_mode_keeps_all_review_failures():
    sections = [
        FailedSection(
            check="style",
            line_start=1,
            line_end=2,
            issue="minor",
            severity="MEDIUM",
            suggestion="fix",
        ),
    ]
    assert len(filter_blocking_failures(sections, poc_mode=False)) == 1


def test_extract_failed_sections_poc_ignores_high_severity_json():
    content = """
```json
{
  "failed_sections": [
    {
      "check": "transformations",
      "line_start": 10,
      "line_end": 12,
      "issue": "ordering",
      "severity": "HIGH",
      "suggestion": "reorder"
    }
  ]
}
```
"""
    assert extract_failed_sections(content, poc_mode=True) == []
    assert len(extract_failed_sections(content, poc_mode=False)) == 1


def test_poc_validation_passes_with_converted_code():
    score, passed = assess_validation_pass(
        0, 85, poc_mode=True, has_converted_code=True
    )
    assert passed is True
    assert score == 85.0


def test_strict_validation_requires_threshold():
    score, passed = assess_validation_pass(
        70, 85, poc_mode=False, has_converted_code=True
    )
    assert score == 70
    assert passed is False
