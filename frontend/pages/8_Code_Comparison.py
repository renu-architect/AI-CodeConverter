"""Side-by-side comparison of original Glue code and converted Synapse Python."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from artifacts.conversion_report import build_conversion_report, format_code_with_line_numbers
from artifacts.store import FileArtifactStore
from theme import configure_page, page_header, section_title, workflow_steps
from utils.config_loader import load_config

configure_page("Code Comparison", icon="🔍")

page_header(
    "Code Comparison",
    "Side-by-side view of original Glue source and converted Synapse Python.",
)

workflow_steps(current=3)  # Code comparison

config = load_config()
ctx = st.session_state.get("comparison_context")

if not ctx:
    project_id = st.session_state.get("project_id", "")
    selected_jobs = st.session_state.get("selected_jobs", [])
    repo_path = st.session_state.get("repo_path", "")
    scan = st.session_state.get("project_scan", {})
    if project_id and selected_jobs and repo_path:
        job_name = selected_jobs[0]
        job_id = f"job_{job_name}"
        source_file = next(
            (j["file_path"] for j in scan.get("glue_jobs", []) if j["name"] == job_name),
            f"{job_name}.py",
        )
        store = FileArtifactStore(config.artifacts_dir)
        try:
            ctx = build_conversion_report(
                store,
                project_id,
                job_id,
                job_name,
                repo_path,
                source_file,
                failure_stage="REVIEWING",
                attempts_used=config.agents.max_implement_iterations,
                max_attempts=config.agents.max_implement_iterations,
            ).model_dump()
            st.session_state["comparison_context"] = ctx
        except Exception:
            ctx = None

if not ctx:
    st.warning(
        "No comparison context available. Run a migration on **Execution**, "
        "or open from the partial-conversion summary."
    )
    st.stop()

project_id = ctx.get("project_id", st.session_state.get("project_id", ""))
job_id = ctx.get("job_id", "")
job_name = ctx.get("job_name", "")
repo_path = ctx.get("repo_path", st.session_state.get("repo_path", ""))
source_file = ctx.get("source_file", "")

store = FileArtifactStore(config.artifacts_dir)

if not ctx.get("failed_sections"):
    try:
        ctx = build_conversion_report(
            store,
            project_id,
            job_id,
            job_name,
            repo_path,
            source_file,
            failure_stage=ctx.get("failure_stage", "REVIEWING"),
            attempts_used=ctx.get("attempts_used", 1),
            max_attempts=ctx.get("max_attempts", 3),
        ).model_dump()
        st.session_state["comparison_context"] = ctx
    except Exception:
        pass

st.info(ctx.get("message", "Review converted code against the original Glue job."))

section_title("Conversion Metrics")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Score", f"{ctx.get('success_pct', 0):.0f}%")
m2.metric("Stages", f"{ctx.get('stage_completion_pct', 0):.0f}%")
m3.metric("Original Lines", ctx.get("original_lines", 0))
m4.metric("Converted Lines", ctx.get("converted_lines", 0))
m5.metric("Attempts", f"{ctx.get('attempts_used', 0)}/{ctx.get('max_attempts', 0)}")

if ctx.get("checks_total", 0) > 0:
    st.caption(
        f"Checks passed: **{ctx.get('checks_passed', 0)}** / **{ctx.get('checks_total', 0)}**"
    )

failed_sections = ctx.get("failed_sections", [])
if failed_sections:
    section_title("Open Issues")
    st.dataframe(
        [
            {
                "Lines": (
                    f"{s.get('line_start', 0)}–{s.get('line_end', 0)}"
                    if s.get("line_start", 0) > 0
                    else "—"
                ),
                "Check": s.get("check", ""),
                "Severity": s.get("severity", ""),
                "Issue": s.get("issue", ""),
                "Suggestion": s.get("suggestion", ""),
            }
            for s in failed_sections
        ],
        width="stretch",
        hide_index=True,
    )

section_title("Side-by-Side Source")
st.caption(f"Job `{job_name}` · Project `{project_id}`")

source_path = Path(repo_path) / source_file if repo_path and source_file else None
original_code = ""
if source_path and source_path.exists():
    original_code = source_path.read_text(encoding="utf-8")
else:
    st.error(f"Original Glue file not found: {source_path}")

converted_code = ""
try:
    converted_code = store.read_latest(project_id, job_id, "converted_code")
except Exception as exc:
    st.error(f"Converted code not found: {exc}")

highlight_ranges = [
    (s.get("line_start", 0), s.get("line_end", 0))
    for s in failed_sections
    if s.get("line_start", 0) > 0
]

left, right = st.columns(2)
with left:
    st.markdown(f"##### Original Glue — `{source_file}`")
    st.code(
        format_code_with_line_numbers(original_code),
        language="python",
        line_numbers=False,
    )
with right:
    st.markdown("##### Converted Synapse — `>>>` marks issue lines")
    st.code(
        format_code_with_line_numbers(converted_code, highlight_ranges),
        language="python",
        line_numbers=False,
    )

c1, c2 = st.columns(2)
with c1:
    if st.button("← Back to Execution", width="stretch"):
        st.switch_page("pages/4_Execution.py")
with c2:
    if st.button("Output Comparison", width="stretch"):
        st.switch_page("pages/9_Output_Comparison.py")
