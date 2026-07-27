"""Tests for workflow orchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from artifacts.models import AgentResult, ArtifactRef
from artifacts.store import FileArtifactStore
from datetime import datetime, timezone
from orchestrator.events import EventBus
from orchestrator.orchestrator import MigrationOrchestrator
from orchestrator.registry import AgentRegistry
from orchestrator.state_machine import StateMachine
from utils.enums import WorkflowStage


def test_state_machine_transitions():
    sm = StateMachine()
    assert sm.stage == WorkflowStage.IDLE

    sm.transition(WorkflowStage.SCANNING)
    assert sm.stage == WorkflowStage.SCANNING

    sm.transition(WorkflowStage.ANALYZING)
    assert sm.stage == WorkflowStage.ANALYZING


def test_state_machine_invalid_transition():
    sm = StateMachine()
    with pytest.raises(ValueError):
        sm.transition(WorkflowStage.COMPLETE)


def test_state_machine_progress():
    sm = StateMachine()
    sm.transition(WorkflowStage.SCANNING)
    assert sm.progress_pct == 5.0


def test_agent_registry():
    registry = AgentRegistry()
    mock_agent = MagicMock()
    mock_agent.name = "test"
    registry.register("ANALYZING", mock_agent)

    assert registry.has("ANALYZING")
    assert registry.get("ANALYZING") == mock_agent


def test_agent_registry_missing():
    registry = AgentRegistry()
    with pytest.raises(KeyError):
        registry.get("NONEXISTENT")


def test_event_bus():
    bus = EventBus()
    events = []
    bus.subscribe(lambda e: events.append(e))

    bus.emit("wf1", "SCANNING", "stage_start", "Scanning repo")
    assert len(events) == 1
    assert events[0].workflow_id == "wf1"


def test_estimate_cost(config, sample_glue_job_path):
    registry = AgentRegistry()
    orchestrator = MigrationOrchestrator(
        config=config,
        registry=registry,
        artifact_store=FileArtifactStore(base_dir=str(sample_glue_job_path / "artifacts")),
    )
    estimate = orchestrator.estimate_cost(str(sample_glue_job_path), None)
    assert estimate.estimated_input_tokens > 0
    assert estimate.estimated_cost_usd > 0
