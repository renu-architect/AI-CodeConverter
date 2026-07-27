"""Documentation agent — generates migration documentation package."""

import json
import time
from pathlib import Path

from agents.base_agent import BaseAgent
from artifacts.models import AgentContext, AgentResult
from utils.logging import get_logger

logger = get_logger("agents.documentation")

DOC_TYPES = [
    "README.md",
    "Architecture.md",
    "MigrationSummary.md",
    "KnownIssues.md",
    "Assumptions.md",
    "DeploymentGuide.md",
]


class DocumentationAgent(BaseAgent):
    """Generates comprehensive migration documentation."""

    name = "documentation"

    async def execute(self, context: AgentContext) -> AgentResult:
        start = time.time()
        artifacts_created = []

        try:
            artifacts_content = {}
            for artifact_type in [
                "Understanding.md",
                "MigrationPlan.md",
                "ConversionNotes.md",
                "Review.md",
                "Validation.md",
                "TestCases.md",
            ]:
                try:
                    artifacts_content[artifact_type] = self.artifact_store.read_latest(
                        context.project_id, context.job_id, artifact_type
                    )
                except Exception:
                    artifacts_content[artifact_type] = ""

            try:
                artifacts_content["converted_code"] = self.artifact_store.read_latest(
                    context.project_id, context.job_id, "converted_code"
                )
            except Exception:
                artifacts_content["converted_code"] = ""

            response = await self.call_gateway(
                template_name="documentation",
                variables={
                    "job_name": context.job_name,
                    "artifacts_summary": json.dumps(
                        {k: v[:1000] for k, v in artifacts_content.items()}, indent=2
                    ),
                },
                expected_format="markdown",
            )

            output_dir = Path(context.metadata.get("output_dir", "outputs"))
            docs_dir = output_dir / context.project_id / context.job_id / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            readme_ref = self.save_artifact(response.content, "README.md", context)
            artifacts_created.append(readme_ref)

            docs_file = docs_dir / "README.md"
            docs_file.write_text(response.content, encoding="utf-8")

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
            logger.error(f"Documentation agent failed: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )
