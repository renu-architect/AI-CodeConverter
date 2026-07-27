"""Migration history and metrics service."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from history.models import (
    Approval,
    LLMCall,
    MetricsDaily,
    Migration,
    Project,
    Workflow,
)


class MetricsService:
    """Service for recording and querying migration metrics."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def create_project(
        self,
        project_id: str,
        name: str,
        repo_path: str,
        repo_hash: str,
        developer: str = "",
    ) -> Project:
        with self.session_factory() as session:
            project = Project(
                project_id=project_id,
                name=name,
                repo_path=repo_path,
                repo_hash=repo_hash,
                developer=developer,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(project)
            session.commit()
            return project

    def create_workflow(self, workflow_id: str, project_id: str) -> Workflow:
        with self.session_factory() as session:
            workflow = Workflow(
                workflow_id=workflow_id,
                project_id=project_id,
                stage="IDLE",
                started_at=datetime.now(timezone.utc),
            )
            session.add(workflow)
            session.commit()
            return workflow

    def update_workflow(
        self,
        workflow_id: str,
        stage: str | None = None,
        progress_pct: float | None = None,
        tokens_used: int | None = None,
        cost_usd: float | None = None,
        status: str | None = None,
        error: str | None = None,
        checkpoint: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            workflow = session.get(Workflow, workflow_id)
            if not workflow:
                return
            if stage is not None:
                workflow.stage = stage
            if progress_pct is not None:
                workflow.progress_pct = progress_pct
            if tokens_used is not None:
                workflow.tokens_used = tokens_used
            if cost_usd is not None:
                workflow.cost_usd = cost_usd
            if status is not None:
                workflow.status = status
            if error is not None:
                workflow.error = error
            if checkpoint is not None:
                workflow.checkpoint = checkpoint
            session.commit()

    def create_migration(
        self,
        workflow_id: str,
        project_id: str,
        job_id: str,
        job_name: str,
        source_file: str,
        complexity_score: float = 0.0,
    ) -> Migration:
        with self.session_factory() as session:
            migration = Migration(
                migration_id=f"mig_{uuid4().hex[:12]}",
                workflow_id=workflow_id,
                project_id=project_id,
                job_id=job_id,
                job_name=job_name,
                source_file=source_file,
                complexity_score=complexity_score,
                started_at=datetime.now(timezone.utc),
            )
            session.add(migration)
            session.commit()
            return migration

    def record_llm_call(
        self,
        workflow_id: str,
        agent_name: str,
        prompt_template: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        latency_ms: int,
        cached: bool = False,
        migration_id: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            call = LLMCall(
                call_id=f"call_{uuid4().hex[:12]}",
                workflow_id=workflow_id,
                migration_id=migration_id,
                agent_name=agent_name,
                prompt_template=prompt_template,
                prompt_version="1.0",
                model=model,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                cached=cached,
                created_at=datetime.now(timezone.utc),
            )
            session.add(call)
            session.commit()

    def record_approval(
        self,
        workflow_id: str,
        developer: str,
        approved: bool,
        comments: str = "",
        plan_version: int = 1,
        estimated_cost: float = 0.0,
        estimated_tokens: int = 0,
    ) -> None:
        with self.session_factory() as session:
            approval = Approval(
                approval_id=f"appr_{uuid4().hex[:12]}",
                workflow_id=workflow_id,
                developer=developer,
                approved=approved,
                comments=comments,
                plan_version=plan_version,
                estimated_cost=estimated_cost,
                estimated_tokens=estimated_tokens,
                created_at=datetime.now(timezone.utc),
            )
            session.add(approval)
            session.commit()

    def get_dashboard_metrics(self, days: int = 30) -> dict[str, Any]:
        with self.session_factory() as session:
            migrations = session.query(Migration).all()
            workflows = {w.workflow_id: w for w in session.query(Workflow).all()}

            total = len(migrations)
            completed = sum(1 for m in migrations if m.status == "complete")
            failed = sum(1 for m in migrations if m.status == "failed")
            total_tokens = sum(w.tokens_used for w in workflows.values())
            total_cost = sum(w.cost_usd for w in workflows.values())

            review_scores = [m.review_score for m in migrations if m.review_score]
            validation_scores = [m.validation_score for m in migrations if m.validation_score]

            return {
                "total_jobs": total,
                "completed_jobs": completed,
                "failed_jobs": failed,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 4),
                "avg_review_score": (
                    sum(review_scores) / len(review_scores) if review_scores else 0.0
                ),
                "avg_validation_score": (
                    sum(validation_scores) / len(validation_scores) if validation_scores else 0.0
                ),
            }

    def get_migration_history(self, project_id: str | None = None) -> list[dict]:
        with self.session_factory() as session:
            query = session.query(Migration)
            if project_id:
                query = query.filter(Migration.project_id == project_id)
            migrations = query.order_by(Migration.started_at.desc()).all()
            workflows = {w.workflow_id: w for w in session.query(Workflow).all()}

            return [
                {
                    "job_name": m.job_name,
                    "status": m.status,
                    "review_score": m.review_score,
                    "validation_score": m.validation_score,
                    "tokens_used": workflows.get(m.workflow_id, Workflow()).tokens_used or 0,
                    "cost_usd": workflows.get(m.workflow_id, Workflow()).cost_usd or 0.0,
                    "started_at": str(m.started_at),
                    "completed_at": str(m.completed_at),
                }
                for m in migrations
            ]

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        with self.session_factory() as session:
            return session.get(Workflow, workflow_id)
