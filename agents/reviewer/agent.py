"""Reviewer agent — compares original and converted code."""

import time

from agents.base_agent import BaseAgent
from artifacts.models import AgentContext, AgentResult
from artifacts.parsers import extract_failed_sections
from artifacts.quality_gates import REVIEWER_QUALITY_RULES_POC, REVIEWER_QUALITY_RULES_STRICT
from utils.code_context import build_code_context
from utils.logging import get_logger

logger = get_logger("agents.reviewer")


class ReviewerAgent(BaseAgent):
    """Reviews converted code against original Glue job."""

    name = "reviewer"

    async def execute(self, context: AgentContext) -> AgentResult:
        start = time.time()
        artifacts_created = []

        try:
            understanding_md = self.artifact_store.read_latest(
                context.project_id, context.job_id, "Understanding.md"
            )
            plan_md = self.artifact_store.read_latest(
                context.project_id, context.job_id, "MigrationPlan.md"
            )
            converted_code = self.artifact_store.read_latest(
                context.project_id, context.job_id, "converted_code"
            )

            repo_path = context.metadata.get("repo_path", "")
            source_file = context.metadata.get("source_file", "")
            original_code = ""
            if repo_path and source_file:
                from pathlib import Path

                source_path = Path(repo_path) / source_file
                if source_path.exists():
                    original_code = source_path.read_text(encoding="utf-8")

            code_context = build_code_context(
                original_code=original_code,
                converted_code=converted_code,
            )

            poc_mode = bool(context.metadata.get("poc_mode", False))
            quality_rules = (
                REVIEWER_QUALITY_RULES_POC if poc_mode else REVIEWER_QUALITY_RULES_STRICT
            )

            response = await self.call_gateway(
                template_name="reviewer",
                variables={
                    "job_name": context.job_name,
                    "original_code": "(see context — full original Glue code)",
                    "understanding_md": understanding_md[:4000],
                    "plan_md": plan_md[:3000],
                    "converted_code": "(see context — full converted Synapse code)",
                    "iteration": str(context.iteration),
                    "quality_rules": quality_rules,
                },
                context_text=code_context,
                expected_format="markdown",
            )

            ref = self.save_artifact(response.content, "Review.md", context)
            artifacts_created.append(ref)

            failed_sections = extract_failed_sections(response.content, poc_mode=poc_mode)
            status = "FAILED" if failed_sections else "PASSED"

            result = AgentResult(
                success=status == "PASSED",
                artifacts_created=artifacts_created,
                tokens_used=response.tokens_input + response.tokens_output,
                cost_usd=response.cost_usd,
                duration_ms=int((time.time() - start) * 1000),
                metadata={
                    "status": status,
                    "failed_sections": [s.model_dump() for s in failed_sections],
                },
            )
            self.log_execution(result)
            return result

        except Exception as e:
            logger.error(f"Reviewer failed: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )
