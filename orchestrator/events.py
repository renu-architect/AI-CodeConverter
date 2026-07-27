"""Workflow event types for UI consumption."""

from datetime import datetime, timezone
from typing import Callable

from artifacts.models import WorkflowEvent


class EventBus:
    """Simple in-memory event bus for workflow events."""

    def __init__(self) -> None:
        self._listeners: list[Callable[[WorkflowEvent], None]] = []

    def subscribe(self, listener: Callable[[WorkflowEvent], None]) -> None:
        self._listeners.append(listener)

    def emit(
        self,
        workflow_id: str,
        stage: str,
        event_type: str,
        message: str,
        metadata: dict | None = None,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            workflow_id=workflow_id,
            timestamp=datetime.now(timezone.utc),
            stage=stage,
            event_type=event_type,
            message=message,
            metadata=metadata or {},
        )
        for listener in self._listeners:
            listener(event)
        return event

    def clear(self) -> None:
        self._listeners.clear()
