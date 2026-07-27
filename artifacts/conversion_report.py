"""Build partial conversion reports when review/validation exhausts retries."""

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from artifacts.parsers import extract_failed_sections, extract_validation_score
from artifacts.resume import MIGRATION_STATE_TYPE, STAGE_ARTIFACTS
from artifacts.store import ArtifactStore
from utils.exceptions import ArtifactNotFoundError

PIPELINE_STAGES = [stage for stage, _ in STAGE_ARTIFACTS]


class ConversionReport(BaseModel):
    """Summary when implementation/review exhausts retries but partial code exists."""

    job_name: str
    project_id: str
    job_id: str
    source_file: str
    repo_path: str
    failure_stage: str
    attempts_used: int
    max_attempts: int
    success_pct: float
    stage_completion_pct: float
    original_lines: int
    converted_lines: int
    checks_passed: int
    checks_total: int
    validation_score: Optional[float] = None
    completed_stages: list[str] = Field(default_factory=list)
    failed_sections: list[dict] = Field(default_factory=list)
    message: str


def _read_migration_state(store: ArtifactStore, project_id: str, job_id: str) -> dict:
    try:
        return store.read_latest_json(project_id, job_id, MIGRATION_STATE_TYPE)
    except ArtifactNotFoundError:
        return {}


def _parse_review_scores(review_md: str) -> list[tuple[str, int, str]]:
    """Parse check name, score, and status from Review.md table rows."""
    scores: list[tuple[str, int, str]] = []
    for match in re.finditer(
        r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|",
        review_md,
    ):
        name = match.group(1).strip()
        if name.lower() in {"check category", "---", "field"}:
            continue
        scores.append((name, int(match.group(2)), match.group(3).strip()))
    return scores


def build_conversion_report(
    store: ArtifactStore,
    project_id: str,
    job_id: str,
    job_name: str,
    repo_path: str,
    source_file: str,
    failure_stage: str,
    attempts_used: int,
    max_attempts: int,
    failed_sections: list[FailedSection] | list[dict] | None = None,
    validation_score: float | None = None,
) -> ConversionReport:
    """Summarize how much conversion succeeded and where issues remain."""
    from artifacts.models import FailedSection

    source_path = Path(repo_path) / source_file
    original_lines = 0
    if source_path.exists():
        original_lines = len(source_path.read_text(encoding="utf-8").splitlines())

    converted_lines = 0
    try:
        converted = store.read_latest(project_id, job_id, "converted_code")
        converted_lines = len(converted.splitlines())
    except ArtifactNotFoundError:
        converted = ""

    state = _read_migration_state(store, project_id, job_id)
    completed_stages: list[str] = state.get("stages_completed", [])
    if "IMPLEMENTING" not in completed_stages and converted_lines > 0:
        completed_stages = list(dict.fromkeys([*completed_stages, "IMPLEMENTING"]))

    stage_completion_pct = round(
        len(completed_stages) / len(PIPELINE_STAGES) * 100, 1
    )

    sections: list[FailedSection] = []
    if failed_sections:
        for item in failed_sections:
            if isinstance(item, FailedSection):
                sections.append(item)
            elif isinstance(item, dict):
                sections.append(FailedSection(**item))

    if not sections:
        try:
            review_md = store.read_latest(project_id, job_id, "Review.md")
            sections = extract_failed_sections(review_md)
        except ArtifactNotFoundError:
            pass

    checks_passed = 0
    checks_total = 0
    success_pct = stage_completion_pct

    try:
        review_md = store.read_latest(project_id, job_id, "Review.md")
        check_scores = _parse_review_scores(review_md)
        if check_scores:
            checks_total = len(check_scores)
            checks_passed = sum(
                1 for _, _, status in check_scores if "PASS" in status.upper()
            )
            avg_score = sum(score for _, score, _ in check_scores) / checks_total
            success_pct = round(avg_score, 1)
    except ArtifactNotFoundError:
        pass

    if validation_score is not None:
        success_pct = round(validation_score, 1)

    failed_dicts = [s.model_dump() for s in sections]
    issue_count = len(failed_dicts)
    located = sum(1 for s in sections if s.line_start > 0)

    message = (
        f"Conversion for '{job_name}' reached {success_pct:.0f}% after "
        f"{attempts_used}/{max_attempts} {failure_stage.lower()} attempts. "
        f"{converted_lines} lines generated ({original_lines} in original). "
        f"{issue_count} open issue(s)"
        + (f" at {located} location(s) in the converted file." if located else ".")
    )

    return ConversionReport(
        job_name=job_name,
        project_id=project_id,
        job_id=job_id,
        source_file=source_file,
        repo_path=repo_path,
        failure_stage=failure_stage,
        attempts_used=attempts_used,
        max_attempts=max_attempts,
        success_pct=success_pct,
        stage_completion_pct=stage_completion_pct,
        original_lines=original_lines,
        converted_lines=converted_lines,
        checks_passed=checks_passed,
        checks_total=checks_total,
        validation_score=validation_score,
        completed_stages=completed_stages,
        failed_sections=failed_dicts,
        message=message,
    )


def format_code_with_line_numbers(
    code: str,
    highlight_ranges: list[tuple[int, int]] | None = None,
) -> str:
    """Return code with line numbers; prefix issue lines with >>>."""
    lines = code.splitlines()
    if not lines:
        return "(empty file)"

    width = len(str(len(lines)))
    issue_lines: set[int] = set()
    for start, end in highlight_ranges or []:
        if start <= 0:
            continue
        end_line = end if end > 0 else start
        for line_no in range(start, end_line + 1):
            issue_lines.add(line_no)

    formatted: list[str] = []
    for idx, line in enumerate(lines, start=1):
        marker = ">>>" if idx in issue_lines else "   "
        formatted.append(f"{marker} {idx:>{width}} | {line}")
    return "\n".join(formatted)
