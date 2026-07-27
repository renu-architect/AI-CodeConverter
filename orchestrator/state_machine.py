"""Workflow state machine transitions."""

from utils.enums import WorkflowStage

# Valid state transitions: current_stage -> list of valid next stages
TRANSITIONS: dict[WorkflowStage, list[WorkflowStage]] = {
    WorkflowStage.IDLE: [WorkflowStage.SCANNING],
    WorkflowStage.SCANNING: [WorkflowStage.ANALYZING, WorkflowStage.FAILED],
    WorkflowStage.ANALYZING: [WorkflowStage.PLANNING, WorkflowStage.FAILED],
    WorkflowStage.PLANNING: [WorkflowStage.AWAITING_APPROVAL, WorkflowStage.FAILED],
    WorkflowStage.AWAITING_APPROVAL: [
        WorkflowStage.IMPLEMENTING,
        WorkflowStage.CANCELLED,
    ],
    WorkflowStage.IMPLEMENTING: [
        WorkflowStage.REVIEWING,
        WorkflowStage.FAILED,
    ],
    WorkflowStage.REVIEWING: [
        WorkflowStage.IMPLEMENTING,
        WorkflowStage.VALIDATING,
        WorkflowStage.FAILED,
    ],
    WorkflowStage.VALIDATING: [
        WorkflowStage.IMPLEMENTING,
        WorkflowStage.TESTING,
        WorkflowStage.FAILED,
    ],
    WorkflowStage.TESTING: [WorkflowStage.DOCUMENTING, WorkflowStage.FAILED],
    WorkflowStage.DOCUMENTING: [WorkflowStage.COMPLETE, WorkflowStage.FAILED],
    WorkflowStage.COMPLETE: [WorkflowStage.IDLE],
    WorkflowStage.FAILED: [WorkflowStage.IDLE],
    WorkflowStage.CANCELLED: [WorkflowStage.IDLE],
}

STAGE_PROGRESS: dict[WorkflowStage, float] = {
    WorkflowStage.IDLE: 0.0,
    WorkflowStage.SCANNING: 5.0,
    WorkflowStage.ANALYZING: 15.0,
    WorkflowStage.PLANNING: 25.0,
    WorkflowStage.AWAITING_APPROVAL: 30.0,
    WorkflowStage.IMPLEMENTING: 45.0,
    WorkflowStage.REVIEWING: 60.0,
    WorkflowStage.VALIDATING: 70.0,
    WorkflowStage.TESTING: 80.0,
    WorkflowStage.DOCUMENTING: 90.0,
    WorkflowStage.COMPLETE: 100.0,
    WorkflowStage.FAILED: 0.0,
    WorkflowStage.CANCELLED: 0.0,
}

STAGE_AGENT_MAP: dict[WorkflowStage, str] = {
    WorkflowStage.ANALYZING: "ANALYZING",
    WorkflowStage.PLANNING: "PLANNING",
    WorkflowStage.IMPLEMENTING: "IMPLEMENTING",
    WorkflowStage.REVIEWING: "REVIEWING",
    WorkflowStage.VALIDATING: "VALIDATING",
    WorkflowStage.TESTING: "TESTING",
    WorkflowStage.DOCUMENTING: "DOCUMENTING",
}

MAX_RETRIES: dict[WorkflowStage, int] = {
    WorkflowStage.SCANNING: 1,
    WorkflowStage.ANALYZING: 2,
    WorkflowStage.PLANNING: 2,
    WorkflowStage.IMPLEMENTING: 3,
    WorkflowStage.REVIEWING: 3,
    WorkflowStage.VALIDATING: 2,
    WorkflowStage.TESTING: 2,
    WorkflowStage.DOCUMENTING: 2,
}


class StateMachine:
    """Manages workflow stage transitions."""

    def __init__(self, initial_stage: WorkflowStage = WorkflowStage.IDLE) -> None:
        self._stage = initial_stage

    @property
    def stage(self) -> WorkflowStage:
        return self._stage

    @property
    def progress_pct(self) -> float:
        return STAGE_PROGRESS.get(self._stage, 0.0)

    def can_transition(self, target: WorkflowStage) -> bool:
        allowed = TRANSITIONS.get(self._stage, [])
        return target in allowed

    def transition(self, target: WorkflowStage) -> WorkflowStage:
        if not self.can_transition(target):
            raise ValueError(
                f"Invalid transition: {self._stage.value} -> {target.value}"
            )
        self._stage = target
        return self._stage

    def reset(self) -> None:
        self._stage = WorkflowStage.IDLE
