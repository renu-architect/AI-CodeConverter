"""Custom exception hierarchy for AI-SDLC framework."""


class AISDLCError(Exception):
    """Base exception for all AI-SDLC errors."""


class GatewayError(AISDLCError):
    """Claude API errors."""


class ContextTooLargeError(GatewayError):
    """Input exceeds token budget."""


class AgentExecutionError(AISDLCError):
    """Agent failed during execution."""


class WorkflowError(AISDLCError):
    """Orchestrator workflow errors."""


class ArtifactNotFoundError(AISDLCError):
    """Requested artifact version not found."""


class ScanError(AISDLCError):
    """Repository scan failures."""


class ValidationFailedError(AISDLCError):
    """Validator score below threshold."""

    def __init__(self, score: float, threshold: float) -> None:
        self.score = score
        self.threshold = threshold
        super().__init__(f"Validation score {score} below threshold {threshold}")
