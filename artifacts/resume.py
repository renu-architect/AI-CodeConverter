"""Artifact resume logic — skip completed stages when source is unchanged."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from artifacts.models import FailedSection
from artifacts.parsers import extract_failed_sections, extract_validation_score
from artifacts.quality_gates import assess_validation_pass
from artifacts.store import ArtifactStore
from utils.exceptions import ArtifactNotFoundError
from utils.logging import get_logger

logger = get_logger("artifacts.resume")

STAGE_ARTIFACTS: list[tuple[str, str]] = [
    ("ANALYZING", "Understanding.md"),
    ("PLANNING", "MigrationPlan.md"),
    ("IMPLEMENTING", "converted_code"),
    ("REVIEWING", "Review.md"),
    ("VALIDATING", "Validation.md"),
    ("TESTING", "TestCases.md"),
    ("DOCUMENTING", "README.md"),
]

MIGRATION_STATE_TYPE = "migration_state.json"


@dataclass
class ResumePlan:
    """Plan for resuming a job pipeline from existing artifacts."""

    source_hash: str
    source_changed: bool = False
    prompt_changed: bool = False
    start_stage: str = "ANALYZING"
    skip_stages: set[str] = field(default_factory=set)
    delta_sections: list[FailedSection] | None = None
    fully_complete: bool = False
    reused_artifacts: list[str] = field(default_factory=list)


def compute_source_hash(file_path: Path) -> str:
    """SHA-256 hash of a Glue job source file."""
    return f"sha256:{hashlib.sha256(file_path.read_bytes()).hexdigest()}"


def build_resume_plan(
    store: ArtifactStore,
    project_id: str,
    job_id: str,
    source_file: Path,
    prompt_version: str,
    reuse_enabled: bool = True,
    validation_threshold: int = 85,
    poc_mode: bool = False,
) -> ResumePlan:
    """Determine which pipeline stages can be skipped based on stored artifacts."""
    source_hash = compute_source_hash(source_file)
    plan = ResumePlan(source_hash=source_hash)

    if not reuse_enabled:
        return plan

    state = _read_migration_state(store, project_id, job_id)
    if state:
        if state.get("source_hash") != source_hash:
            plan.source_changed = True
            logger.info(
                "Source file changed — re-running from analyzer",
                extra={"job_id": job_id},
            )
            return plan
        if state.get("prompt_version") != prompt_version:
            plan.prompt_changed = True
            logger.info(
                "Prompt version changed — re-running from analyzer",
                extra={"job_id": job_id},
            )
            return plan

    for stage, artifact_type in STAGE_ARTIFACTS:
        if not store.has_artifact(project_id, job_id, artifact_type):
            plan.start_stage = stage
            return _finalize_plan(plan, stage)

        plan.reused_artifacts.append(artifact_type)
        plan.skip_stages.add(stage)

        if stage == "REVIEWING":
            review_status = _assess_review(store, project_id, job_id, poc_mode=poc_mode)
            if not review_status.passed:
                plan.start_stage = "IMPLEMENTING"
                plan.delta_sections = review_status.failed_sections
                plan.skip_stages -= {"IMPLEMENTING", "REVIEWING"}
                plan.reused_artifacts = [
                    a for a in plan.reused_artifacts
                    if a not in ("converted_code", "Review.md")
                ]
                return plan

        if stage == "VALIDATING":
            validation_status = _assess_validation(
                store, project_id, job_id, validation_threshold, poc_mode=poc_mode
            )
            if not validation_status.passed:
                plan.start_stage = "IMPLEMENTING"
                plan.skip_stages -= {
                    "IMPLEMENTING",
                    "REVIEWING",
                    "VALIDATING",
                }
                plan.reused_artifacts = [
                    a for a in plan.reused_artifacts
                    if a not in ("converted_code", "Review.md", "Validation.md")
                ]
                return plan

    plan.fully_complete = True
    plan.start_stage = "COMPLETE"
    return plan


def record_stage_complete(
    store: ArtifactStore,
    project_id: str,
    job_id: str,
    job_name: str,
    source_file: str,
    source_hash: str,
    prompt_version: str,
    stage: str,
) -> None:
    """Persist migration state after a stage completes successfully."""
    state = _read_migration_state(store, project_id, job_id) or {
        "job_name": job_name,
        "source_file": source_file,
        "source_hash": source_hash,
        "prompt_version": prompt_version,
        "stages_completed": [],
    }

    state["source_hash"] = source_hash
    state["prompt_version"] = prompt_version
    completed: list[str] = state.get("stages_completed", [])
    if stage not in completed:
        completed.append(stage)
    state["stages_completed"] = completed

    store.write_json(project_id, job_id, MIGRATION_STATE_TYPE, state)


@dataclass
class _ReviewStatus:
    passed: bool
    failed_sections: list[FailedSection] | None = None


@dataclass
class _ValidationStatus:
    passed: bool
    score: float = 0.0


def _assess_review(
    store: ArtifactStore, project_id: str, job_id: str, *, poc_mode: bool = False
) -> _ReviewStatus:
    try:
        content = store.read_latest(project_id, job_id, "Review.md")
    except ArtifactNotFoundError:
        return _ReviewStatus(passed=False)

    failed = extract_failed_sections(content, poc_mode=poc_mode)
    if failed:
        return _ReviewStatus(passed=False, failed_sections=failed)
    return _ReviewStatus(passed=True)


def _assess_validation(
    store: ArtifactStore,
    project_id: str,
    job_id: str,
    threshold: int,
    *,
    poc_mode: bool = False,
) -> _ValidationStatus:
    try:
        content = store.read_latest(project_id, job_id, "Validation.md")
    except ArtifactNotFoundError:
        return _ValidationStatus(passed=False)

    score = extract_validation_score(content)
    if poc_mode:
        try:
            converted = store.read_latest(project_id, job_id, "converted_code")
            has_code = bool(converted.strip())
        except ArtifactNotFoundError:
            has_code = False
        _, passed = assess_validation_pass(
            score, threshold, poc_mode=True, has_converted_code=has_code
        )
        return _ValidationStatus(passed=passed, score=score if score > 0 else 85.0)

    return _ValidationStatus(passed=score >= threshold, score=score)


def _read_migration_state(
    store: ArtifactStore, project_id: str, job_id: str
) -> dict | None:
    try:
        return store.read_latest_json(project_id, job_id, MIGRATION_STATE_TYPE)
    except ArtifactNotFoundError:
        return None


def _finalize_plan(plan: ResumePlan, start_stage: str) -> ResumePlan:
    plan.start_stage = start_stage
    stages_before = {s for s, _ in STAGE_ARTIFACTS}
    stage_order = [s for s, _ in STAGE_ARTIFACTS]
    if start_stage in stage_order:
        idx = stage_order.index(start_stage)
        plan.skip_stages = set(stage_order[:idx])
        plan.reused_artifacts = [
            artifact
            for stage, artifact in STAGE_ARTIFACTS
            if stage in plan.skip_stages
        ]
    return plan


def find_project_by_repo_hash(
    artifacts_dir: str | Path, repo_hash: str
) -> str | None:
    """Find an existing project_id whose project.json matches repo_hash."""
    base = Path(artifacts_dir)
    if not base.exists():
        return None

    for project_dir in base.iterdir():
        if not project_dir.is_dir() or not project_dir.name.startswith("proj_"):
            continue
        project_json_dir = project_dir / "project" / "project.json"
        if not project_json_dir.exists():
            continue
        for version_file in sorted(project_json_dir.glob("v*.json")):
            try:
                data = json.loads(version_file.read_text(encoding="utf-8"))
                if data.get("repo_hash") == repo_hash:
                    return project_dir.name
            except (json.JSONDecodeError, OSError):
                continue
    return None
