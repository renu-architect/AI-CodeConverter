"""Live workflow execution page."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from agents.analyzer.agent import AnalyzerAgent
from agents.documentation.agent import DocumentationAgent
from agents.implementer.agent import ImplementerAgent
from agents.planner.agent import PlannerAgent
from agents.reviewer.agent import ReviewerAgent
from agents.tester.agent import TesterAgent
from agents.validator.agent import ValidatorAgent
from demo.pipeline import run_demo_pipeline
from demo_helpers import ensure_demo_repo_defaults, scan_demo_repository
from artifacts.conversion_report import build_conversion_report
from artifacts.store import FileArtifactStore
from gateway.gateway import ClaudeGateway
from orchestrator.events import EventBus
from orchestrator.orchestrator import MigrationOrchestrator
from orchestrator.registry import AgentRegistry
from theme import configure_page, page_header, section_title, workflow_steps
from utils.config_loader import load_config
from utils.exceptions import ArtifactNotFoundError

configure_page("Execution", icon="▶️")

page_header(
    "Live Execution",
    "Run the multi-agent migration pipeline with artifact reuse and live progress.",
)

workflow_steps(current=2)

config = load_config()
ensure_demo_repo_defaults(config)

if config.demo.enabled and "project_scan" not in st.session_state:
    scan_demo_repository(config)

if "selected_jobs" not in st.session_state:
    st.warning("Please complete repository scan and plan approval first.")
    st.stop()

if not st.session_state.get("plan_approved"):
    st.error("Migration plan not approved. Go to **Migration Plan** and approve first.")
    st.stop()

repo_path = st.session_state.get("repo_path", "")
selected_jobs = st.session_state["selected_jobs"]
project_id = st.session_state.get("project_id", "proj_default")

if "workflow_events" not in st.session_state:
    st.session_state["workflow_events"] = []

section_title("Migration Context")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f"**Repository**  \n`{repo_path}`")
with c2:
    st.markdown(f"**Jobs**  \n{', '.join(selected_jobs)}")
with c3:
    st.markdown(f"**Project ID**  \n`{project_id}`")

progress_bar = st.progress(0)
status_text = st.empty()
metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
log_container = st.container()

if "workflow_running" not in st.session_state:
    st.session_state["workflow_running"] = False


def _format_event(event: dict) -> str:
    ts = event.get("timestamp", "")
    stage = event.get("stage", "")
    event_type = event.get("type", "")
    message = event.get("message", "")
    icon = {
        "stage_complete": "✓",
        "stage_start": "…",
        "error": "✗",
        "approval_needed": "⏳",
        "artifact_reused": "↺",
        "retry": "↻",
        "partial_conversion": "◐",
    }.get(event_type, "·")
    return f"{ts}  {icon}  [{stage}]  {message}"


def _find_partial_conversion(events: list[dict]) -> dict | None:
    for event in reversed(events):
        if event.get("type") == "partial_conversion":
            return event.get("metadata") or {}
    return None


def _workflow_reached_complete(events: list[dict]) -> bool:
    return any(
        e.get("stage") == "COMPLETE" and e.get("type") != "error"
        for e in events
    )


def _resolve_source_file(job_name: str) -> str:
    scan = st.session_state.get("project_scan", {})
    return next(
        (j["file_path"] for j in scan.get("glue_jobs", []) if j["name"] == job_name),
        f"{job_name}.py",
    )


def _build_comparison_context(job_name: str, failure_stage: str = "COMPLETE") -> dict | None:
    job_id = f"job_{job_name}"
    source_file = _resolve_source_file(job_name)
    store = FileArtifactStore(config.artifacts_dir)
    try:
        store.read_latest(project_id, job_id, "converted_code")
    except ArtifactNotFoundError:
        return None

    try:
        report = build_conversion_report(
            store,
            project_id,
            job_id,
            job_name,
            repo_path,
            source_file,
            failure_stage=failure_stage,
            attempts_used=config.agents.max_implement_iterations,
            max_attempts=config.agents.max_implement_iterations,
        )
        report_dict = report.model_dump()
        if failure_stage == "COMPLETE":
            report_dict["message"] = (
                f"Migration for '{job_name}' completed successfully. "
                f"{report.converted_lines} lines of Synapse Python generated "
                f"from {report.original_lines} lines of Glue source."
            )
        return report_dict
    except Exception:
        return None


def _render_view_conversion_button(
    report: dict,
    *,
    label: str = "View Conversion Output →",
    button_key: str = "view_conversion_output",
) -> None:
    st.session_state["comparison_context"] = report
    if st.button(label, type="primary", key=button_key):
        st.switch_page("pages/8_Code_Comparison.py")


def _render_partial_conversion_summary(report: dict) -> None:
    section_title("Partial Conversion Summary")
    st.warning(report.get("message", "Review exhausted all retry attempts."))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Conversion Score", f"{report.get('success_pct', 0):.0f}%")
    c2.metric("Stages Complete", f"{report.get('stage_completion_pct', 0):.0f}%")
    c3.metric("Converted Lines", report.get("converted_lines", 0))
    c4.metric("Open Issues", len(report.get("failed_sections", [])))

    failed = report.get("failed_sections", [])
    if failed:
        st.markdown("**Issue locations in converted file:**")
        for item in failed[:8]:
            lines = item.get("line_start", 0)
            line_label = (
                f"lines {item.get('line_start')}–{item.get('line_end')}"
                if lines > 0
                else "location n/a"
            )
            st.markdown(
                f"- **{item.get('severity', 'MEDIUM')}** `{item.get('check', 'check')}` "
                f"({line_label}): {item.get('issue', '')}"
            )
        if len(failed) > 8:
            st.caption(f"... and {len(failed) - 8} more in Code Comparison")

    _render_view_conversion_button(
        report,
        label="Open Code Comparison →",
        button_key="view_partial_conversion",
    )


def _render_conversion_complete_summary(report: dict) -> None:
    section_title("Conversion Output")
    st.success(report.get("message", "Migration completed successfully."))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Conversion Score", f"{report.get('success_pct', 0):.0f}%")
    c2.metric("Stages Complete", f"{report.get('stage_completion_pct', 0):.0f}%")
    c3.metric("Original Lines", report.get("original_lines", 0))
    c4.metric("Converted Lines", report.get("converted_lines", 0))

    if report.get("checks_total", 0) > 0:
        st.caption(
            f"Review checks passed: **{report.get('checks_passed', 0)}** / "
            f"**{report.get('checks_total', 0)}**"
        )

    _render_view_conversion_button(report)


def _find_output_comparison(events: list[dict]) -> dict | None:
    for event in reversed(events):
        if event.get("stage") == "TESTING" and event.get("metadata"):
            meta = event.get("metadata") or {}
            if "glue_output" in meta:
                return meta
    return st.session_state.get("output_comparison")


def _render_output_comparison_summary(report: dict) -> None:
    section_title("Output Validation (Sample Data)")
    if report.get("status") == "PASS":
        st.success(report.get("message", "Output parity confirmed"))
    else:
        st.warning(report.get("message", "Partial output match"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Input Rows", report.get("input_rows", 0))
    c2.metric("Glue Output", report.get("glue_output_rows", 0))
    c3.metric("Synapse Output", report.get("synapse_output_rows", 0))
    c4.metric("Match", f"{report.get('match_pct', 0):.0f}%")

    st.session_state["output_comparison"] = report
    if st.button("View Output Comparison →", type="primary", key="view_output_comparison"):
        st.switch_page("pages/9_Output_Comparison.py")


def _run_demo_pipeline_ui(status_widget) -> None:
    """Execute zero-token demo pipeline with staged UI updates."""
    st.session_state["workflow_running"] = True
    st.session_state["workflow_events"] = []
    st.session_state["workflow_complete"] = False

    job_name = selected_jobs[0] if selected_jobs else config.demo.default_job

    def on_event(entry: dict) -> None:
        st.session_state["workflow_events"].append(entry)
        status_widget.write(_format_event(entry))
        if entry.get("stage") == "TESTING" and entry.get("metadata"):
            st.session_state["output_comparison"] = entry["metadata"]
        if entry.get("stage") == "COMPLETE":
            status_widget.update(label="Demo pipeline complete", state="complete")

    try:
        status_widget.write(f"Repository: {repo_path}")
        status_widget.write(f"Job: {job_name}")
        status_widget.write("Using cached artifacts — 0 Claude API tokens")

        asyncio.run(
            run_demo_pipeline(
                job_name=job_name,
                on_event=on_event,
                stage_delay_seconds=config.demo.stage_delay_seconds,
            )
        )

        progress_bar.progress(100)
        status_text.success("Demo complete — 0 tokens · cached artifacts · output parity checked")
        st.session_state["workflow_complete"] = True
        st.session_state["workflow_id"] = "demo-local"

        with metrics_col1:
            st.metric("Tokens Used", "0")
        with metrics_col2:
            st.metric("Cost", "$0.00")
        with metrics_col3:
            st.metric("Stage", "COMPLETE")
    except Exception as e:
        status_widget.update(label="Demo pipeline failed", state="error")
        status_widget.write(f"Fatal error: {e}")
        status_text.error(f"Demo failed: {e}")
    finally:
        st.session_state["workflow_running"] = False


def _render_log(events: list[dict]) -> None:
    if not events:
        return
    with log_container:
        section_title("Execution Log")
        st.code("\n".join(_format_event(e) for e in events), language="text")


def _build_orchestrator(status_widget) -> MigrationOrchestrator:
    event_bus = EventBus()

    def on_event(event) -> None:
        entry = {
            "timestamp": event.timestamp.strftime("%H:%M:%S"),
            "stage": event.stage,
            "type": event.event_type,
            "message": event.message,
            "metadata": event.metadata,
        }
        st.session_state["workflow_events"].append(entry)
        line = _format_event(entry)
        status_widget.write(line)
        if event.event_type == "error":
            status_widget.update(label=f"Error at {event.stage}", state="error")
        elif event.stage == "COMPLETE":
            status_widget.update(label="Migration complete", state="complete")

    event_bus.subscribe(on_event)

    artifact_store = FileArtifactStore(config.artifacts_dir)
    gateway = ClaudeGateway(config)
    agent_config = config.agents

    registry = AgentRegistry()
    registry.register("ANALYZING", AnalyzerAgent(gateway, artifact_store, agent_config))
    registry.register("PLANNING", PlannerAgent(gateway, artifact_store, agent_config))
    registry.register("IMPLEMENTING", ImplementerAgent(gateway, artifact_store, agent_config))
    registry.register("REVIEWING", ReviewerAgent(gateway, artifact_store, agent_config))
    registry.register("VALIDATING", ValidatorAgent(gateway, artifact_store, agent_config))
    registry.register("TESTING", TesterAgent(gateway, artifact_store, agent_config))
    registry.register("DOCUMENTING", DocumentationAgent(gateway, artifact_store, agent_config))

    return MigrationOrchestrator(
        config=config,
        registry=registry,
        artifact_store=artifact_store,
        event_bus=event_bus,
    )


section_title("Run Pipeline")

if config.demo.enabled:
    st.caption(
        "Demo mode: **Run Demo Pipeline** replays all stages instantly using cached "
        "artifacts and runs sample-data output comparison — no Claude API calls."
    )

run_demo = False
run_api = False

if config.demo.enabled:
    c_demo, c_api = st.columns(2)
    with c_demo:
        run_demo = st.button(
            "Run Demo Pipeline (0 tokens)",
            type="primary",
            disabled=st.session_state["workflow_running"],
            width="stretch",
        )
    with c_api:
        run_api = st.button(
            "Start Migration (API)",
            disabled=st.session_state["workflow_running"],
            width="stretch",
        )
else:
    run_api = st.button(
        "Start Migration",
        type="primary",
        disabled=st.session_state["workflow_running"],
        width="stretch",
    )

if config.demo.enabled and not st.session_state.get("workflow_events"):
    if not st.session_state.get("demo_auto_started"):
        st.session_state["demo_auto_started"] = True
        run_demo = True

if run_demo:
    with st.status("Running demo pipeline...", expanded=True) as demo_status:
        _run_demo_pipeline_ui(demo_status)

elif run_api:
    st.session_state["workflow_running"] = True
    st.session_state["workflow_events"] = []
    st.session_state["workflow_complete"] = False

    with st.status("Running migration workflow...", expanded=True) as status:
        try:
            orchestrator = _build_orchestrator(status)
            status.write(f"Repository: {repo_path}")
            status.write(f"Jobs: {', '.join(selected_jobs)}")
            status.write("Plan pre-approved — starting pipeline")

            workflow_id = asyncio.run(
                orchestrator.start_workflow(
                    project_id=project_id,
                    repo_path=repo_path,
                    job_names=selected_jobs,
                    developer="developer",
                    pre_approved=True,
                )
            )
            st.session_state["workflow_id"] = workflow_id
            final_status = orchestrator.get_status(workflow_id)

            progress_bar.progress(int(final_status.progress_pct))

            if final_status.stage == "COMPLETE":
                status.update(label="Migration completed successfully", state="complete")
                status_text.success(
                    f"Complete — {final_status.progress_pct:.0f}% · "
                    f"{final_status.tokens_used:,} tokens · ${final_status.cost_usd:.4f}"
                )
                st.session_state["workflow_complete"] = True
            else:
                status.update(label="Migration failed", state="error")
                status_text.error(
                    final_status.error or f"Stopped at stage: {final_status.stage}"
                )

            with metrics_col1:
                st.metric("Tokens Used", f"{final_status.tokens_used:,}")
            with metrics_col2:
                st.metric("Cost", f"${final_status.cost_usd:.4f}")
            with metrics_col3:
                st.metric("Stage", final_status.stage)

        except Exception as e:
            status.update(label="Migration failed", state="error")
            status.write(f"Fatal error: {e}")
            status_text.error(f"Workflow failed: {e}")
            st.session_state["workflow_events"].append({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "stage": "FAILED",
                "type": "error",
                "message": str(e),
                "metadata": {},
            })
        finally:
            st.session_state["workflow_running"] = False

_render_log(st.session_state.get("workflow_events", []))

partial_report = _find_partial_conversion(st.session_state.get("workflow_events", []))
if partial_report and not st.session_state.get("workflow_running"):
    _render_partial_conversion_summary(partial_report)
elif not st.session_state.get("workflow_running") and selected_jobs:
    events = st.session_state.get("workflow_events", [])
    has_complete = st.session_state.get("workflow_complete") or _workflow_reached_complete(events)
    if has_complete:
        complete_report = _build_comparison_context(selected_jobs[0])
        if complete_report:
            _render_conversion_complete_summary(complete_report)

output_report = _find_output_comparison(st.session_state.get("workflow_events", []))
if output_report and not st.session_state.get("workflow_running"):
    _render_output_comparison_summary(output_report)

if st.session_state.get("workflow_events"):
    errors = [e for e in st.session_state["workflow_events"] if e["type"] == "error"]
    if errors:
        section_title("Errors")
        for err in errors:
            st.error(f"[{err['stage']}] {err['message']}")
