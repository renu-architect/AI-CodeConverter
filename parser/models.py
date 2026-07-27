"""Pydantic models for repository scanner output."""

from datetime import datetime

from pydantic import BaseModel


class ASTSummary(BaseModel):
    imports: list[str]
    functions: list[dict]
    classes: list[dict]
    variables: list[str]
    glue_api_calls: list[dict]
    line_count: int


class GlueJob(BaseModel):
    name: str
    file_path: str
    entry_point: str
    ast_summary: ASTSummary
    complexity_score: float
    dependencies: list[str]
    sql_files: list[str]
    config_files: list[str]


class DependencyNode(BaseModel):
    file_path: str
    imports: list[str]
    imported_by: list[str]


class DependencyGraph(BaseModel):
    nodes: list[DependencyNode]
    glue_jobs: list[str]


class ProjectScan(BaseModel):
    project_id: str
    repo_path: str
    repo_hash: str
    scanned_at: datetime
    glue_jobs: list[GlueJob]
    dependency_graph: DependencyGraph
    shared_libraries: list[str]
    total_files: int
    total_lines: int
    overall_complexity: float
