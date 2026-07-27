"""Validator agent — semantic validation with 0-100 score."""

import time

from agents.base_agent import BaseAgent
from artifacts.models import AgentContext, AgentResult
from artifacts.parsers import extract_validation_score
from artifacts.quality_gates import (
    VALIDATOR_QUALITY_RULES_POC,
    VALIDATOR_QUALITY_RULES_STRICT,
    assess_validation_pass,
)
from utils.code_context import build_code_context
from utils.logging import get_logger

logger = get_logger("agents.validator")


class ValidatorAgent(BaseAgent):
    """Validates converted code against business intent and migration completeness."""

    name = "validator"

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

            try:
                review_md = self.artifact_store.read_latest(
                    context.project_id, context.job_id, "Review.md"
                )
            except Exception:
                review_md = ""

            poc_mode = bool(context.metadata.get("poc_mode", False))
            quality_rules = (
                VALIDATOR_QUALITY_RULES_POC if poc_mode else VALIDATOR_QUALITY_RULES_STRICT
            )

            response = await self.call_gateway(
                template_name="validator",
                variables={
                    "job_name": context.job_name,
                    "understanding_md": understanding_md[:4000],
                    "plan_md": plan_md[:3000],
                    "converted_code": "(see context — full converted code)",
                    "review_md": review_md[:3000],
                    "quality_rules": quality_rules,
                },
                context_text=build_code_context(converted_code=converted_code),
                expected_format="markdown",
            )

            ref = self.save_artifact(response.content, "Validation.md", context)
            artifacts_created.append(ref)

            score = extract_validation_score(response.content)
            threshold = int(context.metadata.get("validation_threshold", 85))
            score, passed = assess_validation_pass(
                score,
                threshold,
                poc_mode=poc_mode,
                has_converted_code=bool(converted_code.strip()),
            )

            result = AgentResult(
                success=passed,
                artifacts_created=artifacts_created,
                tokens_used=response.tokens_input + response.tokens_output,
                cost_usd=response.cost_usd,
                duration_ms=int((time.time() - start) * 1000),
                metadata={
                    "validation_score": score,
                    "threshold": threshold,
                    "poc_mode": poc_mode,
                },
            )
            self.log_execution(result)
            return result

        except Exception as e:
            logger.error(f"Validator failed: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )
