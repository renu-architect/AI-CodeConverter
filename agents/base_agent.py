"""Base agent class for all AI-SDLC agents."""

import time
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from artifacts.models import AgentContext, AgentResult, ArtifactRef, GatewayRequest
from artifacts.store import ArtifactStore
from gateway.gateway import AIGateway
from utils.config_models import AgentConfig
from utils.logging import get_logger

logger = get_logger("agents.base")


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    name: str = "base"

    def __init__(
        self,
        gateway: AIGateway,
        artifact_store: ArtifactStore,
        config: AgentConfig,
        prompts_dir: str = "prompts",
    ) -> None:
        self.gateway = gateway
        self.artifact_store = artifact_store
        self.config = config
        self.prompts_dir = Path(prompts_dir)

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute agent logic. Must not call other agents."""

    def load_prompt(self, template_name: str) -> dict:
        """Load prompt template from YAML file."""
        path = self.prompts_dir / f"{template_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        with open(path) as f:
            return yaml.safe_load(f)

    def save_artifact(
        self, content: str, artifact_type: str, context: AgentContext
    ) -> ArtifactRef:
        """Save artifact to versioned store."""
        ref = self.artifact_store.write(
            context.project_id, context.job_id, artifact_type, content
        )
        logger.info(
            f"Agent {self.name} saved artifact",
            extra={
                "artifact_type": artifact_type,
                "version": ref.version,
                "job_id": context.job_id,
            },
        )
        return ref

    async def call_gateway(
        self,
        template_name: str,
        variables: dict[str, str],
        context_text: str = "",
        expected_format: str = "markdown",
        max_output_tokens: int | None = None,
    ):
        """Convenience method to call gateway."""
        request = GatewayRequest(
            template_name=template_name,
            variables=variables,
            context=context_text,
            expected_format=expected_format,
            max_output_tokens=max_output_tokens,
        )
        return await self.gateway.complete(request)

    def log_execution(self, result: AgentResult) -> None:
        logger.info(
            f"Agent {self.name} execution complete",
            extra={
                "success": result.success,
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
                "duration_ms": result.duration_ms,
            },
        )
