"""Tests for workflow orchestrator fail-fast and approval."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from artifacts.models import AgentResult
from artifacts.store import FileArtifactStore
from orchestrator.orchestrator import MigrationOrchestrator
from orchestrator.registry import AgentRegistry


@pytest.fixture
def orchestrator(config, sample_glue_job_path):
    registry = AgentRegistry()
    return MigrationOrchestrator(
        config=config,
        registry=registry,
        artifact_store=FileArtifactStore(base_dir=str(sample_glue_job_path / "artifacts")),
    )


def _mock_agent(name: str, success: bool = True, error: str | None = None) -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.execute = AsyncMock(
        return_value=AgentResult(
            success=success,
            error=error,
            tokens_used=10,
            cost_usd=0.001,
        )
    )
    return agent


@pytest.mark.asyncio
async def test_analyzer_failure_stops_pipeline(orchestrator, sample_glue_job_path):
    orchestrator.registry.register(
        "ANALYZING",
        _mock_agent("analyzer", success=False, error="Claude API error: model not found"),
    )
    orchestrator.registry.register("PLANNING", _mock_agent("planner"))

    workflow_id = await orchestrator.start_workflow(
        project_id="proj_test",
        repo_path=str(sample_glue_job_path),
        job_names=["customer_etl"],
        developer="tester",
        pre_approved=True,
    )

    status = orchestrator.get_status(workflow_id)
    assert status.stage == "FAILED"
    assert status.error is not None

    planner = orchestrator.registry.get("PLANNING")
    planner.execute.assert_not_called()


@pytest.mark.asyncio
async def test_planner_failure_stops_before_implement(orchestrator, sample_glue_job_path):
    orchestrator.registry.register("ANALYZING", _mock_agent("analyzer", success=True))
    orchestrator.registry.register(
        "PLANNING",
        _mock_agent("planner", success=False, error="No Understanding.md"),
    )
    orchestrator.registry.register("IMPLEMENTING", _mock_agent("implementer"))

    workflow_id = await orchestrator.start_workflow(
        project_id="proj_test",
        repo_path=str(sample_glue_job_path),
        job_names=["customer_etl"],
        developer="tester",
        pre_approved=True,
    )

    status = orchestrator.get_status(workflow_id)
    assert status.stage == "FAILED"

    implementer = orchestrator.registry.get("IMPLEMENTING")
    implementer.execute.assert_not_called()


@pytest.mark.asyncio
async def test_review_failure_retries_implementer(orchestrator, sample_glue_job_path):
    """When reviewer fails with failed_sections, implementer is called again in delta mode."""
    implementer = _mock_agent("implementer", success=True)
    implementer.execute = AsyncMock(
        side_effect=[
            AgentResult(success=True, tokens_used=10, cost_usd=0.001),  # first pass
            AgentResult(success=True, tokens_used=10, cost_usd=0.001),  # delta retry
        ]
    )

    reviewer_fail = _mock_agent("reviewer", success=False)

    async def review_side_effect(context):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return AgentResult(
                success=False,
                tokens_used=10,
                cost_usd=0.001,
                metadata={
                    "failed_sections": [
                        {
                            "check": "transformations",
                            "line_start": 10,
                            "line_end": 20,
                            "issue": "missing struct",
                            "severity": "HIGH",
                            "suggestion": "add struct()",
                        }
                    ]
                },
            )
        return AgentResult(success=True, tokens_used=10, cost_usd=0.001)

    call_count = {"n": 0}
    reviewer_fail.execute = AsyncMock(side_effect=review_side_effect)

    orchestrator.registry.register("ANALYZING", _mock_agent("analyzer", success=True))
    orchestrator.registry.register("PLANNING", _mock_agent("planner", success=True))
    orchestrator.registry.register("IMPLEMENTING", implementer)
    orchestrator.registry.register("REVIEWING", reviewer_fail)
    orchestrator.registry.register("VALIDATING", _mock_agent("validator", success=True))
    orchestrator.registry.register("TESTING", _mock_agent("tester", success=True))
    orchestrator.registry.register("DOCUMENTING", _mock_agent("documentation", success=True))

    workflow_id = await orchestrator.start_workflow(
        project_id="proj_test",
        repo_path=str(sample_glue_job_path),
        job_names=["customer_etl"],
        developer="tester",
        pre_approved=True,
    )

    status = orchestrator.get_status(workflow_id)
    assert status.stage == "COMPLETE"
    assert implementer.execute.call_count == 2


@pytest.mark.asyncio
async def test_artifact_reuse_skips_analyzer_and_planner(orchestrator, sample_glue_job_path):
    """Reusing artifacts must still advance the state machine through skipped stages."""
    store = orchestrator.artifact_store
    project_id = "proj_reuse_test"
    job_id = "job_customer_etl"

    store.write(project_id, job_id, "Understanding.md", "# Understanding")
    store.write(project_id, job_id, "MigrationPlan.md", "# Plan")

    analyzer = _mock_agent("analyzer", success=True)
    planner = _mock_agent("planner", success=True)
    orchestrator.registry.register("ANALYZING", analyzer)
    orchestrator.registry.register("PLANNING", planner)

    for stage, name in [
        ("IMPLEMENTING", "implementer"),
        ("REVIEWING", "reviewer"),
        ("VALIDATING", "validator"),
        ("TESTING", "tester"),
        ("DOCUMENTING", "documentation"),
    ]:
        orchestrator.registry.register(stage, _mock_agent(name, success=True))

    workflow_id = await orchestrator.start_workflow(
        project_id=project_id,
        repo_path=str(sample_glue_job_path),
        job_names=["customer_etl"],
        developer="tester",
        pre_approved=True,
    )

    status = orchestrator.get_status(workflow_id)
    assert status.stage == "COMPLETE"

    analyzer.execute.assert_not_called()
    planner.execute.assert_not_called()
    orchestrator.registry.get("IMPLEMENTING").execute.assert_called()


@pytest.mark.asyncio
async def test_fully_complete_artifacts_reaches_complete(orchestrator, sample_glue_job_path):
    """When all pipeline artifacts exist, workflow must reach COMPLETE without invalid transitions."""
    store = orchestrator.artifact_store
    project_id = "proj_full_reuse"
    job_id = "job_customer_etl"

    for artifact_type, content in [
        ("Understanding.md", "# Understanding"),
        ("MigrationPlan.md", "# Plan"),
        ("converted_code", "print('ok')"),
        ("Review.md", "# Review\nAll checks passed."),
        ("Validation.md", "Overall Score: 95"),
        ("TestCases.md", "# Tests"),
        ("README.md", "# README"),
    ]:
        store.write(project_id, job_id, artifact_type, content)

    workflow_id = await orchestrator.start_workflow(
        project_id=project_id,
        repo_path=str(sample_glue_job_path),
        job_names=["customer_etl"],
        developer="tester",
        pre_approved=True,
    )

    status = orchestrator.get_status(workflow_id)
    assert status.stage == "COMPLETE"


@pytest.mark.asyncio
async def test_pre_approved_skips_approval_wait(orchestrator, sample_glue_job_path):
    for stage, name in [
        ("ANALYZING", "analyzer"),
        ("PLANNING", "planner"),
        ("IMPLEMENTING", "implementer"),
        ("REVIEWING", "reviewer"),
        ("VALIDATING", "validator"),
        ("TESTING", "tester"),
        ("DOCUMENTING", "documentation"),
    ]:
        orchestrator.registry.register(stage, _mock_agent(name, success=True))

    events = []
    orchestrator.event_bus.subscribe(lambda e: events.append(e.event_type))

    workflow_id = await orchestrator.start_workflow(
        project_id="proj_test",
        repo_path=str(sample_glue_job_path),
        job_names=["customer_etl"],
        developer="tester",
        pre_approved=True,
    )

    status = orchestrator.get_status(workflow_id)
    assert status.stage == "COMPLETE"
    assert "approval_needed" not in events
