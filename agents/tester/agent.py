"""Tester agent — generates test cases and pytest files."""

import time
from pathlib import Path

from agents.base_agent import BaseAgent
from artifacts.models import AgentContext, AgentResult
from artifacts.quality_gates import TESTER_QUALITY_RULES_POC, TESTER_QUALITY_RULES_STRICT
from utils.logging import get_logger

logger = get_logger("agents.tester")


class TesterAgent(BaseAgent):
    """Generates unit tests, integration test stubs, and mock data."""

    name = "tester"

    async def execute(self, context: AgentContext) -> AgentResult:
        start = time.time()
        artifacts_created = []

        try:
            understanding_md = self.artifact_store.read_latest(
                context.project_id, context.job_id, "Understanding.md"
            )
            converted_code = self.artifact_store.read_latest(
                context.project_id, context.job_id, "converted_code"
            )

            poc_mode = bool(context.metadata.get("poc_mode", False))
            quality_rules = (
                TESTER_QUALITY_RULES_POC if poc_mode else TESTER_QUALITY_RULES_STRICT
            )

            response = await self.call_gateway(
                template_name="tester",
                variables={
                    "job_name": context.job_name,
                    "understanding_md": understanding_md[:3000],
                    "converted_code": converted_code[:5000],
                    "quality_rules": quality_rules,
                },
                expected_format="markdown",
            )

            ref = self.save_artifact(response.content, "TestCases.md", context)
            artifacts_created.append(ref)

            test_code = self._extract_test_code(response.content)
            if test_code:
                output_dir = Path(context.metadata.get("output_dir", "outputs"))
                test_dir = output_dir / context.project_id / context.job_id / "tests"
                test_dir.mkdir(parents=True, exist_ok=True)
                test_file = test_dir / f"test_{context.job_name}.py"
                test_file.write_text(test_code, encoding="utf-8")

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
            logger.error(f"Tester failed: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )

    def _extract_test_code(self, content: str) -> str:
        if "```python" in content:
            parts = content.split("```python", 1)
            if len(parts) > 1:
                return parts[1].split("```", 1)[0].strip()
        return ""
