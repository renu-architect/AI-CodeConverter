"""Shared test fixtures."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from artifacts.models import GatewayResponse
from artifacts.store import FileArtifactStore
from history.db import init_db
from utils.config_loader import load_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def sample_glue_job():
    return (FIXTURES_DIR / "sample_glue_job.py").read_text()


@pytest.fixture
def sample_glue_job_path(tmp_path, sample_glue_job):
    job_dir = tmp_path / "jobs"
    job_dir.mkdir()
    job_file = job_dir / "customer_etl.py"
    job_file.write_text(sample_glue_job)
    return tmp_path


@pytest.fixture
def mock_gateway():
    gateway = AsyncMock()
    gateway.complete.return_value = GatewayResponse(
        content="# Understanding\ntest content",
        parsed="# Understanding\ntest content",
        tokens_input=100,
        tokens_output=200,
        cost_usd=0.001,
        latency_ms=500,
        cached=False,
        model="claude-sonnet-4-6",
    )
    gateway.estimate_tokens.return_value = 1000
    gateway.estimate_cost.return_value = 0.05
    return gateway


@pytest.fixture
def temp_artifact_store(tmp_path):
    return FileArtifactStore(base_dir=tmp_path / "artifacts")


@pytest.fixture
def temp_db(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    init_db(db_url)
    return db_url
