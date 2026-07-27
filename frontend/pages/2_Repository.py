"""Repository selection and scanning page."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from demo_helpers import ensure_demo_repo_defaults, resolve_demo_repo_path, scan_demo_repository
from parser.scanner import GlueRepositoryScanner
from theme import configure_page, page_header, section_title, workflow_steps
from utils.config_loader import load_config

configure_page("Repository", icon="📁")

page_header(
    "Repository Selection",
    "Scan your AWS Glue repository and select jobs for Synapse migration.",
)

workflow_steps(current=0)

config = load_config()
ensure_demo_repo_defaults(config)

default_repo = resolve_demo_repo_path(config)

if config.demo.enabled:
    st.info(
        f"**Demo mode** — default repository: `{default_repo}` · "
        f"job: `{config.demo.default_job}` · no API tokens required for demo run."
    )

section_title("Source Repository")
repo_path = st.text_input(
    "Repository Path",
    value=st.session_state.get("repo_path", default_repo),
    help="Local folder containing Glue ETL Python scripts",
)
job_filter = st.text_input(
    "Job Filter (comma-separated, optional)",
    value=config.demo.default_job if config.demo.enabled else "",
    placeholder="data_cleaning_and_lambda",
)

col_scan, col_demo = st.columns(2)
with col_scan:
    scan_clicked = st.button("Scan Repository", type="primary", width="stretch")
with col_demo:
    demo_clicked = config.demo.enabled and st.button(
        "Quick Demo Setup (scan + select job)",
        width="stretch",
    )

if demo_clicked:
    st.session_state["repo_path"] = repo_path or default_repo
    with st.spinner("Setting up demo repository..."):
        if scan_demo_repository(config):
            st.success(
                f"Demo ready — `{config.demo.default_job}` selected · "
                f"project `{st.session_state.get('project_id', '')}`"
            )
        else:
            st.error(f"Demo repository not found at `{st.session_state['repo_path']}`")

if scan_clicked:
    if not repo_path:
        st.error("Please enter a repository path.")
    else:
        with st.spinner("Scanning repository..."):
            try:
                scanner = GlueRepositoryScanner(config.scanner)
                job_names = (
                    [j.strip() for j in job_filter.split(",") if j.strip()]
                    if job_filter
                    else None
                )
                result = scanner.scan(
                    repo_path,
                    job_names,
                    project_id=st.session_state.get("project_id"),
                    artifacts_dir=config.artifacts_dir,
                )

                st.session_state["project_scan"] = result.model_dump(mode="json")
                st.session_state["repo_path"] = repo_path
                st.session_state["project_id"] = result.project_id

                st.success(f"Found {len(result.glue_jobs)} Glue job(s)")

                for job in result.glue_jobs:
                    with st.expander(
                        f"{job.name}  ·  complexity {job.complexity_score}",
                        expanded=False,
                    ):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**File:** `{job.file_path}`")
                            st.markdown(f"**Entry Point:** `{job.entry_point}`")
                        with c2:
                            st.markdown(
                                f"**Dependencies:** {', '.join(job.dependencies) or 'None'}"
                            )
                            st.markdown(
                                f"**Glue API Calls:** {len(job.ast_summary.glue_api_calls)}"
                            )

                section_title("Dependency Graph")
                st.json(result.dependency_graph.model_dump())

                if config.demo.enabled and not job_names:
                    default = config.demo.default_job
                    names = [j.name for j in result.glue_jobs]
                    if default in names:
                        st.session_state["selected_jobs"] = [default]

            except Exception as e:
                st.error(f"Scan failed: {e}")

if "project_scan" in st.session_state:
    section_title("Select Jobs to Migrate")
    job_options = [j["name"] for j in st.session_state["project_scan"]["glue_jobs"]]
    default_selection = st.session_state.get(
        "selected_jobs",
        [config.demo.default_job] if config.demo.default_job in job_options else [],
    )
    selected_jobs = st.multiselect(
        "Glue jobs",
        job_options,
        default=[j for j in default_selection if j in job_options],
    )
    if selected_jobs:
        st.session_state["selected_jobs"] = selected_jobs
        if config.demo.auto_approve_plan:
            st.session_state["plan_approved"] = True
        if st.button("Proceed to Migration Plan →", type="primary"):
            st.switch_page("pages/3_Migration_Plan.py")
