"""Tests for reviewer agent failed_sections extraction."""

from artifacts.parsers import extract_failed_sections


def test_extract_failed_sections_from_list_json():
    """Review.md uses a JSON array — not wrapped in failed_sections."""
    content = """
## Failed Sections
```json
[
  {
    "check_id": 5,
    "category": "Business Logic",
    "severity": "CRITICAL",
    "line_start": null,
    "line_end": null,
    "issue": "apply_mapping not implemented",
    "suggestion": "Use struct()"
  }
]
```
"""
    sections = extract_failed_sections(content)
    assert len(sections) == 1
    assert sections[0].check == "Business Logic"
    assert sections[0].severity == "CRITICAL"
    assert sections[0].line_start == 0


def test_extract_failed_sections_from_wrapped_json():
    content = """
```json
{
  "failed_sections": [
    {
      "check": "transformations",
      "line_start": 45,
      "line_end": 67,
      "issue": "Join type differs",
      "severity": "HIGH",
      "suggestion": "Use left join"
    }
  ]
}
```
"""
    sections = extract_failed_sections(content)
    assert len(sections) == 1
    assert sections[0].check == "transformations"
    assert sections[0].line_start == 45


def test_no_failures_returns_empty():
    content = "# Review\nAll checks passed."
    assert extract_failed_sections(content) == []
