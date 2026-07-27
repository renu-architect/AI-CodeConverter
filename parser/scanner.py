"""Repository scanner — walk directory, detect Glue jobs, build dependency graph."""

import fnmatch
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from parser.ast_extractor import extract_ast
from parser.complexity_scorer import has_error_handling, score_complexity
from parser.dependency_graph import build_dependency_graph
from parser.glue_detector import is_glue_job
from parser.models import GlueJob, ProjectScan
from utils.config_models import ScannerConfig
from utils.exceptions import ScanError
from utils.logging import get_logger

logger = get_logger("parser.scanner")


class RepositoryScanner(ABC):
    """Abstract base class for repository scanner."""

    @abstractmethod
    def scan(
        self,
        repo_path: str,
        job_filter: list[str] | None = None,
        project_id: str | None = None,
        artifacts_dir: str | None = None,
    ) -> ProjectScan:
        """Scan repository and return project scan results."""


class GlueRepositoryScanner(RepositoryScanner):
    """Deterministic repository scanner for AWS Glue jobs."""

    def __init__(self, config: ScannerConfig | None = None) -> None:
        self.config = config or ScannerConfig()

    def scan(
        self,
        repo_path: str,
        job_filter: list[str] | None = None,
        project_id: str | None = None,
        artifacts_dir: str | None = None,
    ) -> ProjectScan:
        """Walk repository, detect Glue jobs, build dependency graph."""
        repo = Path(repo_path)
        if not repo.exists():
            raise ScanError(f"Repository path does not exist: {repo_path}")

        repo_hash = self._compute_repo_hash(repo)
        project_id = project_id or self._resolve_project_id(repo_hash, artifacts_dir)

        python_files: dict[str, Path] = {}
        sql_files: dict[str, Path] = {}
        config_files: dict[str, Path] = {}
        total_lines = 0

        for file_path in self._walk_repo(repo):
            rel_path = str(file_path.relative_to(repo)).replace("\\", "/")
            if file_path.suffix == ".py":
                python_files[rel_path] = file_path
                total_lines += len(
                    file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                )
            elif file_path.suffix == ".sql":
                sql_files[rel_path] = file_path
            elif file_path.suffix in (".json", ".yaml", ".yml"):
                config_files[rel_path] = file_path

        file_imports: dict[str, list[str]] = {}
        glue_jobs: list[GlueJob] = []

        for rel_path, file_path in python_files.items():
            try:
                ast_summary = extract_ast(file_path)
            except SyntaxError as e:
                logger.warning(f"Skipping unparseable file: {rel_path}: {e}")
                continue

            file_imports[rel_path] = ast_summary.imports

            if is_glue_job(ast_summary.imports, ast_summary.glue_api_calls):
                job_name = Path(rel_path).stem
                if job_filter and job_name not in job_filter:
                    continue

                related_sql = [
                    s for s in sql_files if job_name in s or Path(s).stem in job_name
                ]
                related_config = [
                    c for c in config_files if job_name in c
                ]

                complexity = score_complexity(
                    ast_summary,
                    sql_file_count=len(related_sql),
                    has_error_handling=has_error_handling(ast_summary),
                )

                entry_point = self._detect_entry_point(ast_summary)

                glue_jobs.append(
                    GlueJob(
                        name=job_name,
                        file_path=rel_path,
                        entry_point=entry_point,
                        ast_summary=ast_summary,
                        complexity_score=complexity,
                        dependencies=[],
                        sql_files=related_sql,
                        config_files=related_config,
                    )
                )

        glue_job_paths = [job.file_path for job in glue_jobs]
        dep_graph = build_dependency_graph(file_imports, glue_job_paths)

        # Resolve dependencies for each glue job
        dep_map = {node.file_path: node.imports for node in dep_graph.nodes}
        for job in glue_jobs:
            job.dependencies = dep_map.get(job.file_path, [])

        shared_libs = self._find_shared_libraries(dep_graph, glue_job_paths)
        overall_complexity = (
            sum(j.complexity_score for j in glue_jobs) / len(glue_jobs)
            if glue_jobs
            else 0.0
        )

        logger.info(
            "Repository scan complete",
            extra={
                "project_id": project_id,
                "glue_jobs": len(glue_jobs),
                "total_files": len(python_files) + len(sql_files) + len(config_files),
            },
        )

        return ProjectScan(
            project_id=project_id,
            repo_path=str(repo.resolve()),
            repo_hash=repo_hash,
            scanned_at=datetime.now(timezone.utc),
            glue_jobs=glue_jobs,
            dependency_graph=dep_graph,
            shared_libraries=shared_libs,
            total_files=len(python_files) + len(sql_files) + len(config_files),
            total_lines=total_lines,
            overall_complexity=round(overall_complexity, 1),
        )

    def _walk_repo(self, repo: Path):
        """Walk repository respecting ignore patterns."""
        max_bytes = self.config.max_file_size_mb * 1024 * 1024
        for file_path in repo.rglob("*"):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(repo))
            if self._should_ignore(rel):
                continue
            if file_path.stat().st_size > max_bytes:
                logger.warning(f"Skipping oversized file: {rel}")
                continue
            yield file_path

    def _should_ignore(self, rel_path: str) -> bool:
        for pattern in self.config.ignore_patterns:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
                Path(rel_path).name, pattern
            ):
                return True
            if pattern in rel_path.split("/"):
                return True
        return False

    @staticmethod
    def _detect_entry_point(ast_summary) -> str:
        for func in ast_summary.functions:
            if func["name"] in ("main", "__main__"):
                return func["name"]
        if ast_summary.functions:
            return ast_summary.functions[0]["name"]
        return "__main__"

    @staticmethod
    def _find_shared_libraries(dep_graph, glue_job_paths: list[str]) -> list[str]:
        shared: set[str] = set()
        for node in dep_graph.nodes:
            if node.file_path not in glue_job_paths and node.imported_by:
                importers_in_glue = [ib for ib in node.imported_by if ib in glue_job_paths]
                if importers_in_glue:
                    shared.add(node.file_path)
        return sorted(shared)

    @staticmethod
    def _resolve_project_id(
        repo_hash: str, artifacts_dir: str | None
    ) -> str:
        """Reuse existing project_id for the same repo hash, or create a new one."""
        if artifacts_dir:
            from artifacts.resume import find_project_by_repo_hash

            existing = find_project_by_repo_hash(artifacts_dir, repo_hash)
            if existing:
                return existing
        return f"proj_{uuid4().hex[:12]}"

    @staticmethod
    def _compute_repo_hash(repo: Path) -> str:
        hasher = hashlib.sha256()
        for file_path in sorted(repo.rglob("*")):
            if file_path.is_file() and file_path.suffix in (".py", ".sql", ".json", ".yaml"):
                hasher.update(file_path.read_bytes())
        return f"sha256:{hasher.hexdigest()}"
