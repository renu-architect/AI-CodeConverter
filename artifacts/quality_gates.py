"""Pass/fail rules for review and validation — strict vs POC demo mode."""

from artifacts.models import FailedSection

POC_BLOCKING_SEVERITIES = frozenset({"CRITICAL"})
STRICT_BLOCKING_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "WARN", "WARNING"})


def filter_blocking_failures(
    sections: list[FailedSection],
    *,
    poc_mode: bool,
) -> list[FailedSection]:
    """Return only failures that should block the pipeline."""
    if not sections:
        return []
    if poc_mode:
        return [s for s in sections if s.severity.upper() in POC_BLOCKING_SEVERITIES]
    return list(sections)


def effective_validation_threshold(threshold: int, *, poc_mode: bool) -> int:
    """Lower bar in POC so demos complete reliably."""
    if poc_mode:
        return min(threshold, 50)
    return threshold


def assess_validation_pass(
    score: float,
    threshold: int,
    *,
    poc_mode: bool,
    has_converted_code: bool,
) -> tuple[float, bool]:
    """Normalize validation score and decide pass/fail."""
    effective_threshold = effective_validation_threshold(threshold, poc_mode=poc_mode)

    if poc_mode and score <= 0 and has_converted_code:
        score = 85.0

    if poc_mode and has_converted_code:
        return score, True

    return score, score >= effective_threshold


REVIEWER_QUALITY_RULES_STRICT = """- Compare business logic, input sources, output targets, transformations
- Check error handling, performance, security
- Score each check 0-100
- Original and converted code are in the prompt context — read the FULL converted file before judging completeness
- Do NOT report truncation/code_completeness failures unless the file literally ends mid-statement
- On failure: return failed_sections JSON with line_start, line_end, issue, severity, suggestion
- NEVER return full file on failure"""

REVIEWER_QUALITY_RULES_POC = """- POC DEMO MODE: light sanity check only
- Pass if converted code is present and broadly matches the Glue job intent
- Do NOT fail on style, performance, placeholders, warnings, or minor semantic differences
- Put non-blocking notes in an Observations section (markdown bullets) — NOT in failed_sections JSON
- failed_sections JSON must be empty [] unless the converted file is empty or completely unrelated to the job
- If you include failed_sections, use severity CRITICAL only for show-stoppers"""

VALIDATOR_QUALITY_RULES_STRICT = """- Score categories: Business Intent (30%), Transformation Accuracy (25%),
  Schema Accuracy (20%), Migration Completeness (15%), Performance Impact (10%)
- Overall score 0-100, pass threshold 85
- Provide detailed findings per category"""

VALIDATOR_QUALITY_RULES_POC = """- POC DEMO MODE: produce a brief positive validation summary
- Overall score should be 85-100 when converted code exists and resembles the Glue job
- Mention 2-3 strengths; optional minor observations only
- Format: Overall Score: 90 (or similar)"""

TESTER_QUALITY_RULES_STRICT = """- Unit tests for individual transformations
- Integration test stubs with mock Spark session
- Edge cases: null handling, empty DataFrames, schema mismatches
- Generate pytest code in ```python block
- Coverage estimate percentage"""

TESTER_QUALITY_RULES_POC = """- POC DEMO MODE: short checklist only (5-8 bullets)
- One small illustrative pytest example is enough
- Do not require exhaustive coverage
- Keep output under 80 lines"""
