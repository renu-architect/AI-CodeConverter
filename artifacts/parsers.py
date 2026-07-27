"""Shared parsers for artifact content assessment."""

import json
import re

from artifacts.models import FailedSection


def extract_failed_sections(content: str, *, poc_mode: bool = False) -> list[FailedSection]:
    """Extract failed sections from Review.md JSON block."""
    from artifacts.quality_gates import filter_blocking_failures

    failed: list[FailedSection] = []

    json_match = re.search(r"```json\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            sections: list[dict] = []
            if isinstance(data, list):
                sections = data
            elif isinstance(data, dict):
                raw = data.get("failed_sections", [])
                if isinstance(raw, list):
                    sections = raw

            for section in sections:
                if isinstance(section, dict):
                    failed.append(_normalize_failed_section(section))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    if not failed and not poc_mode and _content_indicates_failure(content):
        failed.append(
            FailedSection(
                check="review_summary",
                line_start=0,
                line_end=0,
                issue="Review reported failures but structured failed_sections JSON was missing",
                severity="HIGH",
                suggestion="Re-run review or inspect Review.md manually",
            )
        )

    return filter_blocking_failures(failed, poc_mode=poc_mode)


def extract_validation_score(content: str) -> float:
    """Extract overall validation score from Validation.md."""
    patterns = [
        r"Overall Score:\s*(\d+(?:\.\d+)?)",
        r"Overall Score.*?(\d+(?:\.\d+)?)/100",
        r"\*\*Overall Score:\*\*\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return 0.0


def _normalize_failed_section(raw: dict) -> FailedSection:
    check = (
        raw.get("check")
        or raw.get("category")
        or f"check_{raw.get('check_id', 'unknown')}"
    )
    line_start = raw.get("line_start")
    line_end = raw.get("line_end")

    return FailedSection(
        check=str(check),
        line_start=int(line_start) if line_start is not None else 0,
        line_end=int(line_end) if line_end is not None else 0,
        issue=str(raw.get("issue", "")),
        severity=str(raw.get("severity", "MEDIUM")),
        suggestion=str(raw.get("suggestion", "")),
    )


def _content_indicates_failure(content: str) -> bool:
    upper = content.upper()
    if "OVERALL STATUS" in upper and "PASS" in upper and "FAIL" not in upper:
        if "❌" in content or re.search(r"\|\s*❌\s*FAIL", content):
            return True
    if re.search(r"STATUS.*\|\s*⚠️\s*CONDITIONAL", content, re.IGNORECASE):
        return "❌" in content or "FAIL" in upper
    return bool(re.search(r"❌\s*FAIL|\|\s*FAIL\s*\|", content))
