"""Planner agent — produces MigrationPlan.md from Understanding.md."""

import time

from agents.base_agent import BaseAgent
from artifacts.models import AgentContext, AgentResult
from utils.logging import get_logger

logger = get_logger("agents.planner")


class PlannerAgent(BaseAgent):
    """Creates migration plan from Understanding.md."""

    name = "planner"

    async def execute(self, context: AgentContext) -> AgentResult:
        start = time.time()
        artifacts_created = []

        try:
            understanding_md = self.artifact_store.read_latest(
                context.project_id, context.job_id, "Understanding.md"
            )

            response = await self.call_gateway(
                template_name="planner",
                variables={"understanding_md": understanding_md},
                expected_format="markdown",
            )

            ref = self.save_artifact(response.content, "MigrationPlan.md", context)
            artifacts_created.append(ref)

            result = AgentResult(
                success=True,
                artifacts_created=artifacts_created,
                tokens_used=response.tokens_input + response.tokens_output,
                cost_usd=response.cost_usd,
                duration_ms=int((time.time() - start) * 1000),
            )
            self.log_execution(result)
            return result

        except Exception as e:
            logger.error(f"Planner failed: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )
