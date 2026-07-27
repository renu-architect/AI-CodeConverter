"""Tests for repository scanner."""

import json
from pathlib import Path

import pytest

from parser.scanner import GlueRepositoryScanner
from utils.exceptions import ScanError


def test_scan_fixture_repo(sample_glue_job_path):
    scanner = GlueRepositoryScanner()
    result = scanner.scan(str(sample_glue_job_path))

    assert result.total_files >= 1
    assert len(result.glue_jobs) >= 1
    assert result.glue_jobs[0].name == "customer_etl"


def test_detects_glue_imports(sample_glue_job_path):
    scanner = GlueRepositoryScanner()
    result = scanner.scan(str(sample_glue_job_path))
    job = result.glue_jobs[0]

    glue_imports = [i for i in job.ast_summary.imports if "awsglue" in i]
    assert len(glue_imports) > 0


def test_detects_glue_api_calls(sample_glue_job_path):
    scanner = GlueRepositoryScanner()
    result = scanner.scan(str(sample_glue_job_path))
    job = result.glue_jobs[0]

    assert len(job.ast_summary.glue_api_calls) > 0


def test_complexity_score_range(sample_glue_job_path):
    scanner = GlueRepositoryScanner()
    result = scanner.scan(str(sample_glue_job_path))
    job = result.glue_jobs[0]

    assert 0 <= job.complexity_score <= 100


def test_dependency_graph(sample_glue_job_path):
    scanner = GlueRepositoryScanner()
    result = scanner.scan(str(sample_glue_job_path))

    assert len(result.dependency_graph.nodes) >= 1
    assert len(result.dependency_graph.glue_jobs) >= 1


def test_scan_nonexistent_path():
    scanner = GlueRepositoryScanner()
    with pytest.raises(ScanError):
        scanner.scan("/nonexistent/path")


def test_project_json_serializable(sample_glue_job_path):
    scanner = GlueRepositoryScanner()
    result = scanner.scan(str(sample_glue_job_path))
    data = result.model_dump(mode="json")
    json_str = json.dumps(data)
    assert len(json_str) > 0
