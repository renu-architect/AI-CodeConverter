"""Workflow orchestrator — central coordinator for migration workflows."""

import asyncio
import json
import time
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from uuid import uuid4

from artifacts.conversion_report import build_conversion_report
from artifacts.models import AgentContext, AgentResult, CostEstimate, FailedSection, WorkflowStatus
from artifacts.resume import ResumePlan, build_resume_plan, record_stage_complete
from artifacts.store import FileArtifactStore
from history.db import init_db
from history.metrics import MetricsService
from orchestrator.events import EventBus
from orchestrator.registry import AgentRegistry
from orchestrator.state_machine import STAGE_PROGRESS, StateMachine
from parser.scanner import GlueRepositoryScanner
from utils.config_models import AppConfig
from utils.enums import WorkflowStage
from utils.exceptions import AgentExecutionError, WorkflowError
from utils.logging import get_logger, setup_logging

logger = get_logger("orchestrator")


PIPELINE_STAGE_ORDER = [
    "ANALYZING",
    "PLANNING",
    "IMPLEMENTING",
    "REVIEWING",
    "VALIDATING",
    "TESTING",
    "DOCUMENTING",
]

WORKFLOW_STAGE_PATH = [
    WorkflowStage.SCANNING,
    WorkflowStage.ANALYZING,
    WorkflowStage.PLANNING,
    WorkflowStage.AWAITING_APPROVAL,
    WorkflowStage.IMPLEMENTING,
    WorkflowStage.REVIEWING,
    WorkflowStage.VALIDATING,
    WorkflowStage.TESTING,
    WorkflowStage.DOCUMENTING,
    WorkflowStage.COMPLETE,
]


class WorkflowOrchestrator(ABC):
    """Abstract base class for workflow orchestrator."""

    @abstractmethod
    async def start_workflow(
        self, project_id: str, repo_path: str, job_names: list[str], developer: str,
        pre_approved: bool = False,
    ) -> str: ...

    @abstractmethod
    async def approve_plan(
        self, workflow_id: str, approved: bool, comments: str = ""
    ) -> None: ...

    @abstractmethod
    async def resume_workflow(self, workflow_id: str) -> WorkflowStatus: ...

    @abstractmethod
    async def abort_workflow(self, workflow_id: str) -> None: ...

    @abstractmethod
    def get_status(self, workflow_id: str) -> WorkflowStatus: ...

    @abstractmethod
    def estimate_cost(self, repo_path: str, job_names: list[str]) -> CostEstimate: ...


class MigrationOrchestrator(WorkflowOrchestrator):
    """Orchestrates the full Glue-to-Synapse migration workflow."""

    def __init__(
        self,
        config: AppConfig,
        registry: AgentRegistry,
        artifact_store: FileArtifactStore | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.artifact_store = artifact_store or FileArtifactStore(config.artifacts_dir)
        self.event_bus = event_bus or EventBus()
        self.scanner = GlueRepositoryScanner(config.scanner)

        setup_logging(config.log_level)
        session_factory = init_db(config.database_url)
        self.metrics = MetricsService(session_factory)

        self._workflows: dict[str, dict] = {}
        self._state_machines: dict[str, StateMachine] = {}
        self._approval_events: dict[str, asyncio.Event] = {}

    async def start_workflow(
        self,
        project_id: str,
        repo_path: str,
        job_names: list[str],
        developer: str,
        pre_approved: bool = False,
    ) -> str:
        workflow_id = f"wf_{uuid4().hex[:12]}"
        state_machine = StateMachine(WorkflowStage.IDLE)
        self._state_machines[workflow_id] = state_machine
        self._approval_events[workflow_id] = asyncio.Event()

        self._workflows[workflow_id] = {
            "project_id": project_id,
            "repo_path": repo_path,
            "job_names": job_names,
            "developer": developer,
            "pre_approved": pre_approved,
            "started_at": time.time(),
            "tokens_used": 0,
            "cost_usd": 0.0,
            "current_job_index": 0,
            "jobs": {},
            "last_error": None,
        }

        self.metrics.create_workflow(workflow_id, project_id)
        self._emit(workflow_id, "IDLE", "stage_start", "Workflow started")

        try:
            await self._run_workflow(workflow_id)
        except (WorkflowError, AgentExecutionError) as e:
            logger.error(f"Workflow failed: {e}")
            if state_machine.stage != WorkflowStage.FAILED:
                try:
                    state_machine.transition(WorkflowStage.FAILED)
                except ValueError:
                    state_machine._stage = WorkflowStage.FAILED  # noqa: SLF001
            wf = self._workflows[workflow_id]
            wf["last_error"] = str(e)
            self.metrics.update_workflow(
                workflow_id, stage="FAILED", status="failed", error=str(e)
            )
            self._emit(workflow_id, "FAILED", "error", str(e))
        except Exception as e:
            logger.error(f"Workflow failed unexpectedly: {e}")
            try:
                state_machine.transition(WorkflowStage.FAILED)
            except ValueError:
                state_machine._stage = WorkflowStage.FAILED  # noqa: SLF001
            self._workflows[workflow_id]["last_error"] = str(e)
            self.metrics.update_workflow(
                workflow_id, stage="FAILED", status="failed", error=str(e)
            )
            self._emit(workflow_id, "FAILED", "error", str(e))

        return workflow_id

    async def _run_workflow(self, workflow_id: str) -> None:
        wf = self._workflows[workflow_id]
        sm = self._state_machines[workflow_id]

        if not wf["job_names"]:
            raise WorkflowError("No Glue jobs selected for migration")

        # SCAN
        sm.transition(WorkflowStage.SCANNING)
        self._emit(workflow_id, "SCANNING", "stage_start", "Scanning repository")
        scan = self.scanner.scan(
            wf["repo_path"],
            wf["job_names"],
            project_id=wf["project_id"],
            artifacts_dir=self.config.artifacts_dir,
        )

        if not scan.glue_jobs:
            raise WorkflowError(
                f"No Glue jobs found for: {', '.join(wf['job_names'])}"
            )

        wf["project_scan"] = scan.model_dump(mode="json")
        wf["project_id"] = scan.project_id
        self._emit(
            workflow_id,
            "SCANNING",
            "stage_complete",
            f"Found {len(scan.glue_jobs)} Glue job(s)",
        )

        self.artifact_store.write_json(
            wf["project_id"], "project", "project.json", wf["project_scan"]
        )

        for job in scan.glue_jobs:
            job_id = f"job_{job.name}"
            wf["jobs"][job.name] = {
                "job_id": job_id,
                "source_file": job.file_path,
                "iteration": 1,
            }

            self.metrics.create_migration(
                workflow_id,
                wf["project_id"],
                job_id,
                job.name,
                job.file_path,
                job.complexity_score,
            )

            await self._run_job_pipeline(workflow_id, wf["project_id"], job_id, job.name)

            if wf.get("last_error"):
                return

        self._advance_stage(sm, WorkflowStage.COMPLETE)
        self.metrics.update_workflow(
            workflow_id, stage="COMPLETE", status="complete", progress_pct=100.0
        )
        self._emit(workflow_id, "COMPLETE", "stage_complete", "Workflow complete")

    async def _run_job_pipeline(
        self, workflow_id: str, project_id: str, job_id: str, job_name: str
    ) -> None:
        wf = self._workflows[workflow_id]
        sm = self._state_machines[workflow_id]
        job_info = wf["jobs"][job_name]
        source_path = Path(wf["repo_path"]) / job_info["source_file"]

        resume = build_resume_plan(
            self.artifact_store,
            project_id,
            job_id,
            source_path,
            self.config.agents.prompt_version,
            reuse_enabled=self.config.agents.reuse_artifacts,
            validation_threshold=self.config.agents.validation_threshold,
            poc_mode=self.config.agents.poc_mode,
        )
        initial_skip = set(resume.skip_stages)

        if resume.fully_complete:
            self._advance_stage(sm, WorkflowStage.COMPLETE)
            self._emit(
                workflow_id,
                "COMPLETE",
                "artifact_reused",
                f"Job {job_name} already migrated — reusing existing artifacts",
                metadata={"reused_artifacts": resume.reused_artifacts},
            )
            return

        if resume.reused_artifacts:
            self._emit(
                workflow_id,
                resume.start_stage,
                "artifact_reused",
                f"Reusing {len(resume.reused_artifacts)} artifact(s) — "
                f"resuming from {resume.start_stage}",
                metadata={"reused_artifacts": resume.reused_artifacts},
            )

        context = AgentContext(
            workflow_id=workflow_id,
            project_id=project_id,
            job_id=job_id,
            job_name=job_name,
            stage="ANALYZING",
            iteration=job_info["iteration"],
            delta_sections=resume.delta_sections,
            metadata={
                "repo_path": wf["repo_path"],
                "source_file": job_info["source_file"],
                "project_scan": wf["project_scan"],
                "output_dir": self.config.output_dir,
                "validation_threshold": self.config.agents.validation_threshold,
                "poc_mode": self.config.agents.poc_mode,
                "coding_standards": json.dumps(self.config.coding_standards.model_dump()),
            },
        )

        # ANALYZE — fail-fast: do not proceed without Understanding.md
        self._advance_stage(sm, WorkflowStage.ANALYZING)
        if self._should_run_stage("ANALYZING", resume):
            result = await self._invoke_agent("ANALYZING", context)
            self._accumulate_cost(workflow_id, result)
            self._require_success(workflow_id, "ANALYZING", result, job_name)
            self._record_job_stage(
                project_id, job_id, job_name, job_info, resume, "ANALYZING"
            )
        else:
            self._emit_stage_reused(workflow_id, "ANALYZING", "Understanding.md")

        # PLAN — fail-fast: do not proceed without MigrationPlan.md
        self._advance_stage(sm, WorkflowStage.PLANNING)
        if self._should_run_stage("PLANNING", resume):
            context.stage = "PLANNING"
            result = await self._invoke_agent("PLANNING", context)
            self._accumulate_cost(workflow_id, result)
            self._require_success(workflow_id, "PLANNING", result, job_name)
            self._record_job_stage(
                project_id, job_id, job_name, job_info, resume, "PLANNING"
            )
        else:
            self._emit_stage_reused(workflow_id, "PLANNING", "MigrationPlan.md")

        # AWAIT APPROVAL (skip if plan already exists or pre-approved)
        self._advance_stage(sm, WorkflowStage.AWAITING_APPROVAL)
        if "PLANNING" in initial_skip or wf.get("pre_approved"):
            self._emit(
                workflow_id,
                "AWAITING_APPROVAL",
                "stage_complete",
                "Plan available — continuing to implementation",
            )
        else:
            self._emit(
                workflow_id,
                "AWAITING_APPROVAL",
                "approval_needed",
                "Plan ready — waiting for developer approval",
            )
            await self._approval_events[workflow_id].wait()
            self._approval_events[workflow_id].clear()

            if wf.get("cancelled"):
                sm.transition(WorkflowStage.CANCELLED)
                self._emit(workflow_id, "CANCELLED", "error", "Migration cancelled by developer")
                return

        # IMPLEMENT → REVIEW → VALIDATE loop
        implement_complete = all(
            s in resume.skip_stages
            for s in ("IMPLEMENTING", "REVIEWING", "VALIDATING")
        )
        if not implement_complete:
            max_impl = self.config.agents.max_implement_iterations
            for impl_iter in range(max_impl):
                self._advance_stage(sm, WorkflowStage.IMPLEMENTING)
                if self._should_run_stage("IMPLEMENTING", resume, impl_iter):
                    context.stage = "IMPLEMENTING"
                    context.iteration = impl_iter + 1
                    result = await self._invoke_agent("IMPLEMENTING", context)
                    self._accumulate_cost(workflow_id, result)
                    self._require_success(workflow_id, "IMPLEMENTING", result, job_name)
                    self._record_job_stage(
                        project_id, job_id, job_name, job_info, resume, "IMPLEMENTING"
                    )
                elif impl_iter == 0:
                    self._emit_stage_reused(workflow_id, "IMPLEMENTING", "converted_code")

                if self._should_run_stage("REVIEWING", resume, impl_iter):
                    self._advance_stage(sm, WorkflowStage.REVIEWING)
                    context.stage = "REVIEWING"
                    result = await self._invoke_agent(
                        "REVIEWING", context, emit_failure=False
                    )
                    self._accumulate_cost(workflow_id, result)

                    if result.success:
                        self._record_job_stage(
                            project_id, job_id, job_name, job_info, resume, "REVIEWING"
                        )
                    else:
                        failed = result.metadata.get("failed_sections", [])
                        if failed and impl_iter < max_impl - 1:
                            context.delta_sections = [
                                FailedSection(**s) for s in failed
                            ]
                            self._emit(
                                workflow_id,
                                "REVIEWING",
                                "retry",
                                f"Review found {len(failed)} issue(s) — "
                                f"sending to implementer (retry {impl_iter + 2}/{max_impl})",
                                metadata={"failed_sections": failed},
                            )
                            sm.transition(WorkflowStage.IMPLEMENTING)
                            continue
                        self._fail_partial_conversion(
                            workflow_id,
                            project_id,
                            job_id,
                            job_name,
                            job_info,
                            wf,
                            failure_stage="REVIEWING",
                            error_msg=result.error or f"REVIEWING failed for {job_name}",
                            failed_sections=failed,
                            attempts_used=impl_iter + 1,
                            max_attempts=max_impl,
                        )
                        return
                elif impl_iter == 0:
                    self._emit_stage_reused(workflow_id, "REVIEWING", "Review.md")

                if self._should_run_stage("VALIDATING", resume, impl_iter):
                    self._advance_stage(sm, WorkflowStage.VALIDATING)
                    context.stage = "VALIDATING"
                    result = await self._invoke_agent(
                        "VALIDATING", context, emit_failure=False
                    )
                    self._accumulate_cost(workflow_id, result)

                    if result.success:
                        self._record_job_stage(
                            project_id, job_id, job_name, job_info, resume, "VALIDATING"
                        )
                        break

                    if impl_iter < max_impl - 1:
                        self._emit(
                            workflow_id,
                            "VALIDATING",
                            "retry",
                            f"Validation below threshold — retry {impl_iter + 2}/{max_impl}",
                        )
                        sm.transition(WorkflowStage.IMPLEMENTING)
                        continue
                    self._fail_partial_conversion(
                        workflow_id,
                        project_id,
                        job_id,
                        job_name,
                        job_info,
                        wf,
                        failure_stage="VALIDATING",
                        error_msg=f"VALIDATING failed for {job_name}: score below threshold",
                        failed_sections=None,
                        attempts_used=impl_iter + 1,
                        max_attempts=max_impl,
                        validation_score=result.metadata.get("validation_score"),
                    )
                    return
                elif impl_iter == 0:
                    self._emit_stage_reused(workflow_id, "VALIDATING", "Validation.md")
                    break

        # TEST
        self._advance_stage(sm, WorkflowStage.TESTING)
        if self._should_run_stage("TESTING", resume):
            context.stage = "TESTING"
            context.delta_sections = None
            result = await self._invoke_agent("TESTING", context)
            self._accumulate_cost(workflow_id, result)
            if not result.success:
                self._emit(
                    workflow_id,
                    "TESTING",
                    "error",
                    result.error or "Tester agent failed — continuing with warning",
                )
            else:
                self._record_job_stage(
                    project_id, job_id, job_name, job_info, resume, "TESTING"
                )
        else:
            self._emit_stage_reused(workflow_id, "TESTING", "TestCases.md")

        # DOCUMENT
        self._advance_stage(sm, WorkflowStage.DOCUMENTING)
        if self._should_run_stage("DOCUMENTING", resume):
            context.stage = "DOCUMENTING"
            result = await self._invoke_agent("DOCUMENTING", context)
            self._accumulate_cost(workflow_id, result)
            if not result.success:
                self._fail_workflow(
                    workflow_id,
                    result.error or f"DOCUMENTING failed for {job_name}",
                )
            else:
                self._record_job_stage(
                    project_id, job_id, job_name, job_info, resume, "DOCUMENTING"
                )
        else:
            self._emit_stage_reused(workflow_id, "DOCUMENTING", "README.md")

    @staticmethod
    def _advance_stage(sm: StateMachine, target: WorkflowStage) -> None:
        """Advance state machine to target, walking through intermediate stages."""
        if sm.stage == target:
            return
        if sm.can_transition(target):
            sm.transition(target)
            return
        try:
            current_idx = WORKFLOW_STAGE_PATH.index(sm.stage)
            target_idx = WORKFLOW_STAGE_PATH.index(target)
        except ValueError:
            sm.transition(target)
            return
        for stage in WORKFLOW_STAGE_PATH[current_idx + 1 : target_idx + 1]:
            sm.transition(stage)

    @staticmethod
    def _should_run_stage(
        stage: str, resume: ResumePlan, impl_iter: int = 0
    ) -> bool:
        """Return whether a pipeline stage should invoke its agent."""
        if impl_iter > 0:
            return True
        if stage in resume.skip_stages:
            return False
        if resume.start_stage == "COMPLETE":
            return False
        try:
            return (
                PIPELINE_STAGE_ORDER.index(stage)
                >= PIPELINE_STAGE_ORDER.index(resume.start_stage)
            )
        except ValueError:
            return True

    def _emit_stage_reused(
        self, workflow_id: str, stage: str, artifact_type: str
    ) -> None:
        self._emit(
            workflow_id,
            stage,
            "artifact_reused",
            f"Reusing existing {artifact_type}",
            metadata={"artifact_type": artifact_type},
        )

    def _record_job_stage(
        self,
        project_id: str,
        job_id: str,
        job_name: str,
        job_info: dict,
        resume: ResumePlan,
        stage: str,
    ) -> None:
        record_stage_complete(
            self.artifact_store,
            project_id,
            job_id,
            job_name,
            job_info["source_file"],
            resume.source_hash,
            self.config.agents.prompt_version,
            stage,
        )

    async def _invoke_agent(
        self,
        stage: str,
        context: AgentContext,
        *,
        emit_failure: bool = True,
    ) -> AgentResult:
        agent = self.registry.get(stage)
        self._emit(
            context.workflow_id,
            stage,
            "stage_start",
            f"Running {agent.name} agent for {context.job_name}",
        )
        result = await agent.execute(context)
        if result.success:
            self._emit(
                context.workflow_id,
                stage,
                "stage_complete",
                f"{agent.name} completed for {context.job_name}",
                metadata={"tokens_used": result.tokens_used, "cost_usd": result.cost_usd},
            )
        elif emit_failure:
            error_msg = result.error or f"{agent.name} agent failed"
            self._emit(
                context.workflow_id,
                stage,
                "error",
                error_msg,
                metadata={"agent": agent.name, "job_name": context.job_name},
            )
        return result

    def _require_success(
        self,
        workflow_id: str,
        stage: str,
        result: AgentResult,
        job_name: str,
    ) -> None:
        """Raise and mark workflow failed if an agent did not succeed."""
        if result.success:
            return
        error_msg = result.error or f"{stage} failed for {job_name}"
        self._fail_workflow(workflow_id, error_msg)
        raise AgentExecutionError(error_msg)

    def _fail_partial_conversion(
        self,
        workflow_id: str,
        project_id: str,
        job_id: str,
        job_name: str,
        job_info: dict,
        wf: dict,
        failure_stage: str,
        error_msg: str,
        failed_sections: list | None,
        attempts_used: int,
        max_attempts: int,
        validation_score: float | None = None,
    ) -> None:
        """Mark workflow failed but emit a partial conversion report for the UI."""
        report = build_conversion_report(
            self.artifact_store,
            project_id,
            job_id,
            job_name,
            wf["repo_path"],
            job_info["source_file"],
            failure_stage=failure_stage,
            attempts_used=attempts_used,
            max_attempts=max_attempts,
            failed_sections=failed_sections,
            validation_score=validation_score,
        )
        wf["partial_conversion_report"] = report.model_dump()
        self._emit(
            workflow_id,
            failure_stage,
            "partial_conversion",
            report.message,
            metadata=report.model_dump(),
        )
        self._fail_workflow(workflow_id, error_msg)

    def _fail_workflow(self, workflow_id: str, error_msg: str) -> None:
        wf = self._workflows[workflow_id]
        sm = self._state_machines[workflow_id]
        wf["last_error"] = error_msg
        try:
            sm.transition(WorkflowStage.FAILED)
        except ValueError:
            sm._stage = WorkflowStage.FAILED  # noqa: SLF001
        self.metrics.update_workflow(
            workflow_id, stage="FAILED", status="failed", error=error_msg
        )
        self._emit(workflow_id, "FAILED", "error", error_msg)

    def _accumulate_cost(self, workflow_id: str, result) -> None:
        wf = self._workflows[workflow_id]
        wf["tokens_used"] += result.tokens_used
        wf["cost_usd"] += result.cost_usd

    async def approve_plan(
        self, workflow_id: str, approved: bool, comments: str = ""
    ) -> None:
        wf = self._workflows.get(workflow_id)
        if not wf:
            raise WorkflowError(f"Workflow not found: {workflow_id}")

        if not approved:
            wf["cancelled"] = True

        self.metrics.record_approval(
            workflow_id,
            wf.get("developer", ""),
            approved,
            comments,
        )

        if workflow_id in self._approval_events:
            self._approval_events[workflow_id].set()

    async def resume_workflow(self, workflow_id: str) -> WorkflowStatus:
        return self.get_status(workflow_id)

    async def abort_workflow(self, workflow_id: str) -> None:
        wf = self._workflows.get(workflow_id)
        if wf:
            wf["cancelled"] = True
        sm = self._state_machines.get(workflow_id)
        if sm:
            sm.transition(WorkflowStage.CANCELLED)
        self.metrics.update_workflow(workflow_id, status="cancelled")

    def get_status(self, workflow_id: str) -> WorkflowStatus:
        wf = self._workflows.get(workflow_id)
        sm = self._state_machines.get(workflow_id)
        if not wf or not sm:
            raise WorkflowError(f"Workflow not found: {workflow_id}")

        return WorkflowStatus(
            workflow_id=workflow_id,
            project_id=wf["project_id"],
            stage=sm.stage.value,
            progress_pct=sm.progress_pct,
            iteration=1,
            elapsed_seconds=int(time.time() - wf["started_at"]),
            tokens_used=wf["tokens_used"],
            cost_usd=wf["cost_usd"],
            error=wf.get("last_error"),
        )

    def estimate_cost(self, repo_path: str, job_names: list[str]) -> CostEstimate:
        scan = self.scanner.scan(repo_path, job_names)
        num_jobs = len(scan.glue_jobs)
        per_job_input = 35000
        per_job_output = 18000
        total_input = per_job_input * num_jobs
        total_output = per_job_output * num_jobs
        cost = (
            (total_input / 1_000_000) * self.config.cost_estimation.input_price_per_million
            + (total_output / 1_000_000) * self.config.cost_estimation.output_price_per_million
        )
        return CostEstimate(
            estimated_input_tokens=total_input,
            estimated_output_tokens=total_output,
            estimated_cost_usd=round(cost, 4),
            estimated_duration_seconds=num_jobs * 600,
            estimated_api_calls=num_jobs * 7,
        )

    def create_output_package(self, project_id: str, job_id: str) -> Path:
        """Create ZIP output package for a completed migration."""
        output_dir = Path(self.config.output_dir) / project_id / job_id
        zip_path = output_dir.parent / f"{job_id}_package.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if output_dir.exists():
                for file_path in output_dir.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, file_path.relative_to(output_dir))
        return zip_path

    def _emit(
        self,
        workflow_id: str,
        stage: str,
        event_type: str,
        message: str,
        metadata: dict | None = None,
    ) -> None:
        self.event_bus.emit(workflow_id, stage, event_type, message, metadata)
        try:
            progress = STAGE_PROGRESS.get(WorkflowStage(stage), 0.0)
        except ValueError:
            progress = 0.0
        self.metrics.update_workflow(workflow_id, stage=stage, progress_pct=progress)
