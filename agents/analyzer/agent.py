"""Analyzer agent — produces Understanding.md from Glue job source."""

import hashlib
import json
import time
from pathlib import Path

from agents.base_agent import BaseAgent
from artifacts.models import AgentContext, AgentResult
from utils.logging import get_logger

logger = get_logger("agents.analyzer")


class AnalyzerAgent(BaseAgent):
    """Analyzes AWS Glue ETL jobs and produces Understanding.md."""

    name = "analyzer"

    async def execute(self, context: AgentContext) -> AgentResult:
        start = time.time()
        artifacts_created = []
        total_tokens = 0
        total_cost = 0.0

        try:
            project_scan = context.metadata.get("project_scan", {})
            job_name = context.job_name
            repo_path = context.metadata.get("repo_path", "")

            glue_job = None
            for job in project_scan.get("glue_jobs", []):
                if job["name"] == job_name:
                    glue_job = job
                    break

            if not glue_job:
                return AgentResult(
                    success=False,
                    error=f"Glue job not found: {job_name}",
                    duration_ms=int((time.time() - start) * 1000),
                )

            file_path = Path(repo_path) / glue_job["file_path"]
            source_code = file_path.read_text(encoding="utf-8")
            code_sections = self._extract_code_sections(source_code, glue_job)

            response = await self.call_gateway(
                template_name="analyzer",
                variables={
                    "job_name": job_name,
                    "file_path": glue_job["file_path"],
                    "complexity_score": str(glue_job.get("complexity_score", 0)),
                    "ast_summary": json.dumps(glue_job.get("ast_summary", {}), indent=2),
                    "code_sections": code_sections,
                    "dependencies": json.dumps(glue_job.get("dependencies", [])),
                    "knowledge_patterns": context.metadata.get("knowledge_patterns", "None"),
                },
                expected_format="markdown",
            )

            total_tokens = response.tokens_input + response.tokens_output
            total_cost = response.cost_usd

            ref = self.save_artifact(response.content, "Understanding.md", context)
            artifacts_created.append(ref)

            result = AgentResult(
                success=True,
                artifacts_created=artifacts_created,
                tokens_used=total_tokens,
                cost_usd=total_cost,
                duration_ms=int((time.time() - start) * 1000),
            )
            self.log_execution(result)
            return result

        except Exception as e:
            logger.error(f"Analyzer failed: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )

    def _extract_code_sections(self, source: str, glue_job: dict) -> str:
        """Extract relevant code sections, truncating if too large."""
        lines = source.splitlines()
        max_lines = 200
        if len(lines) <= max_lines:
            return source

        sections = []
        for func in glue_job.get("ast_summary", {}).get("functions", []):
            start = max(0, func.get("line_start", 1) - 1)
            end = min(len(lines), func.get("line_end", len(lines)))
            sections.append(f"# Function: {func['name']}")
            sections.extend(lines[start:end])
            sections.append("")

        result = "\n".join(sections)
        if len(result.splitlines()) > max_lines:
            return "\n".join(result.splitlines()[:max_lines]) + "\n# ... truncated ..."
        return result

    @staticmethod
    def cache_key(source_code: str, prompt_version: str) -> str:
        return hashlib.sha256(f"{source_code}{prompt_version}".encode()).hexdigest()
