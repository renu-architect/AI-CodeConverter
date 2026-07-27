"""Implementer agent — converts Glue code to Synapse Spark Python."""

import json
import time
from pathlib import Path

from agents.base_agent import BaseAgent
from artifacts.models import AgentContext, AgentResult
from utils.code_context import format_code_for_prompt
from utils.logging import get_logger

logger = get_logger("agents.implementer")


class ImplementerAgent(BaseAgent):
    """Converts Glue ETL jobs to Azure Synapse Spark Python."""

    name = "implementer"

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

            coding_standards = context.metadata.get("coding_standards", "")
            knowledge_patterns = context.metadata.get("knowledge_patterns", "None")

            if context.delta_sections:
                template = "implementer_delta"
                converted_code = self.artifact_store.read_latest(
                    context.project_id, context.job_id, "converted_code"
                )
                delta_json = json.dumps(
                    [s.model_dump() for s in context.delta_sections], indent=2
                )
                variables = {
                    "failed_sections": delta_json,
                    "current_code": format_code_for_prompt(
                        converted_code, label="Current Converted Code"
                    ),
                    "plan_excerpt": plan_md[:3000],
                    "coding_standards": coding_standards,
                }
            else:
                template = "implementer_full"
                repo_path = context.metadata.get("repo_path", "")
                source_file = context.metadata.get("source_file", "")
                source_code = ""
                if repo_path and source_file:
                    source_path = Path(repo_path) / source_file
                    if source_path.exists():
                        source_code = source_path.read_text(encoding="utf-8")

                variables = {
                    "understanding_md": understanding_md,
                    "plan_md": plan_md,
                    "source_code": source_code,
                    "coding_standards": coding_standards,
                    "knowledge_patterns": knowledge_patterns,
                    "job_name": context.job_name,
                }

            response = await self.call_gateway(
                template_name=template,
                variables=variables,
                expected_format="markdown",
            )

            content = response.content
            code, notes, summary = self._parse_implementer_output(content)

            if code:
                code_ref = self.save_artifact(code, "converted_code", context)
                artifacts_created.append(code_ref)

            if notes:
                notes_ref = self.save_artifact(notes, "ConversionNotes.md", context)
                artifacts_created.append(notes_ref)

            if summary:
                summary_ref = self.save_artifact(summary, "MigrationSummary.md", context)
                artifacts_created.append(summary_ref)

            if not code and content:
                code_ref = self.save_artifact(content, "converted_code", context)
                artifacts_created.append(code_ref)

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
            logger.error(f"Implementer failed: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )

    def _parse_implementer_output(self, content: str) -> tuple[str, str, str]:
        """Parse implementer output into code, notes, and summary sections."""
        code = ""
        notes = ""
        summary = ""

        if "```python" in content:
            parts = content.split("```python", 1)
            if len(parts) > 1:
                code_part = parts[1].split("```", 1)
                code = code_part[0].strip()
                remaining = code_part[1] if len(code_part) > 1 else ""
            else:
                remaining = content
        else:
            remaining = content

        if "## Conversion Notes" in remaining:
            sections = remaining.split("## Conversion Notes", 1)
            notes = "## Conversion Notes" + sections[1].split("## Migration Summary", 1)[0]
            if "## Migration Summary" in sections[1]:
                summary = "## Migration Summary" + sections[1].split("## Migration Summary", 1)[1]

        return code, notes.strip(), summary.strip()
