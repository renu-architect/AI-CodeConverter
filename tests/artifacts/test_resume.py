"""Tests for artifact resume logic."""

import json
from pathlib import Path

import pytest

from artifacts.resume import (
    build_resume_plan,
    compute_source_hash,
    find_project_by_repo_hash,
)
from artifacts.store import FileArtifactStore


@pytest.fixture
def artifact_store(tmp_path):
    return FileArtifactStore(base_dir=tmp_path / "artifacts")


def test_compute_source_hash(sample_glue_job_path):
    job_file = sample_glue_job_path / "jobs" / "customer_etl.py"
    h1 = compute_source_hash(job_file)
    h2 = compute_source_hash(job_file)
    assert h1.startswith("sha256:")
    assert h1 == h2


def test_build_resume_plan_starts_at_analyzer_when_empty(
    artifact_store, sample_glue_job_path
):
    job_file = sample_glue_job_path / "jobs" / "customer_etl.py"
    plan = build_resume_plan(
        artifact_store,
        "proj_test",
        "job_customer_etl",
        job_file,
        prompt_version="1.0",
    )
    assert plan.start_stage == "ANALYZING"
    assert not plan.skip_stages
    assert not plan.fully_complete


def test_build_resume_plan_skips_completed_stages(
    artifact_store, sample_glue_job_path
):
    job_file = sample_glue_job_path / "jobs" / "customer_etl.py"
    source_hash = compute_source_hash(job_file)
    project_id = "proj_test"
    job_id = "job_customer_etl"

    artifact_store.write(project_id, job_id, "Understanding.md", "# Understanding")
    artifact_store.write(project_id, job_id, "MigrationPlan.md", "# Plan")
    artifact_store.write_json(
        project_id,
        job_id,
        "migration_state.json",
        {
            "source_hash": source_hash,
            "prompt_version": "1.0",
            "stages_completed": ["ANALYZING", "PLANNING"],
        },
    )

    plan = build_resume_plan(
        artifact_store,
        project_id,
        job_id,
        job_file,
        prompt_version="1.0",
    )
    assert plan.start_stage == "IMPLEMENTING"
    assert "ANALYZING" in plan.skip_stages
    assert "PLANNING" in plan.skip_stages
    assert "Understanding.md" in plan.reused_artifacts


def test_build_resume_plan_resumes_implementer_after_review_failure(
    artifact_store, sample_glue_job_path
):
    job_file = sample_glue_job_path / "jobs" / "customer_etl.py"
    project_id = "proj_test"
    job_id = "job_customer_etl"

    artifact_store.write(project_id, job_id, "Understanding.md", "# Understanding")
    artifact_store.write(project_id, job_id, "MigrationPlan.md", "# Plan")
    artifact_store.write(project_id, job_id, "converted_code", "print('hello')")
    artifact_store.write(
        project_id,
        job_id,
        "Review.md",
        '```json\n[{"category": "logic", "issue": "missing", "severity": "HIGH"}]\n```',
    )

    plan = build_resume_plan(
        artifact_store,
        project_id,
        job_id,
        job_file,
        prompt_version="1.0",
        poc_mode=False,
    )
    assert plan.start_stage == "IMPLEMENTING"
    assert plan.delta_sections is not None
    assert len(plan.delta_sections) == 1
    assert "IMPLEMENTING" not in plan.skip_stages


def test_build_resume_plan_ignores_high_review_failure_in_poc_mode(
    artifact_store, sample_glue_job_path
):
    job_file = sample_glue_job_path / "jobs" / "customer_etl.py"
    project_id = "proj_test"
    job_id = "job_customer_etl"

    artifact_store.write(project_id, job_id, "Understanding.md", "# Understanding")
    artifact_store.write(project_id, job_id, "MigrationPlan.md", "# Plan")
    artifact_store.write(project_id, job_id, "converted_code", "print('hello')")
    artifact_store.write(
        project_id,
        job_id,
        "Review.md",
        '```json\n[{"category": "logic", "issue": "missing", "severity": "HIGH"}]\n```',
    )
    artifact_store.write(project_id, job_id, "Validation.md", "Overall Score: 90")
    artifact_store.write(project_id, job_id, "TestCases.md", "# Tests")
    artifact_store.write(project_id, job_id, "README.md", "# README")

    plan = build_resume_plan(
        artifact_store,
        project_id,
        job_id,
        job_file,
        prompt_version="1.0",
        poc_mode=True,
    )
    assert plan.fully_complete is True


def test_find_project_by_repo_hash(artifact_store, tmp_path):
    project_id = "proj_abc123"
    repo_hash = "sha256:deadbeef"
    artifact_store.write_json(
        project_id,
        "project",
        "project.json",
        {"repo_hash": repo_hash, "project_id": project_id},
    )

    found = find_project_by_repo_hash(artifact_store.base_dir, repo_hash)
    assert found == project_id

    assert find_project_by_repo_hash(artifact_store.base_dir, "sha256:other") is None


def test_source_change_invalidates_resume(artifact_store, sample_glue_job_path):
    job_file = sample_glue_job_path / "jobs" / "customer_etl.py"
    project_id = "proj_test"
    job_id = "job_customer_etl"

    artifact_store.write(project_id, job_id, "Understanding.md", "# Understanding")
    artifact_store.write_json(
        project_id,
        job_id,
        "migration_state.json",
        {
            "source_hash": "sha256:oldhash",
            "prompt_version": "1.0",
            "stages_completed": ["ANALYZING"],
        },
    )

    plan = build_resume_plan(
        artifact_store,
        project_id,
        job_id,
        job_file,
        prompt_version="1.0",
    )
    assert plan.source_changed is True
    assert plan.start_stage == "ANALYZING"
