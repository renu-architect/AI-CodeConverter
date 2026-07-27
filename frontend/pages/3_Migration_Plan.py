"""Migration plan review and approval page."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from orchestrator.orchestrator import MigrationOrchestrator
from orchestrator.registry import AgentRegistry
from theme import configure_page, info_card, page_header, section_title, workflow_steps
from utils.config_loader import load_config

configure_page("Migration Plan", icon="📋")

page_header(
    "Migration Plan",
    "Review cost estimates and approve before agents begin the migration pipeline.",
)

workflow_steps(current=1)

config = load_config()

if "selected_jobs" not in st.session_state:
    st.warning("Please scan a repository and select jobs first.")
    st.stop()

selected_jobs = st.session_state["selected_jobs"]
repo_path = st.session_state.get("repo_path", "")

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Repository:** `{repo_path}`")
with c2:
    st.markdown(f"**Selected Jobs:** {', '.join(selected_jobs)}")

section_title("Cost Estimation")
if st.button("Estimate Migration Cost", type="primary"):
    try:
        registry = AgentRegistry()
        orchestrator = MigrationOrchestrator(config=config, registry=registry)
        estimate = orchestrator.estimate_cost(repo_path, selected_jobs)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Est. Input Tokens", f"{estimate.estimated_input_tokens:,}")
        with col2:
            st.metric("Est. Output Tokens", f"{estimate.estimated_output_tokens:,}")
        with col3:
            st.metric("Est. Cost", f"${estimate.estimated_cost_usd:.4f}")
        with col4:
            st.metric("Est. Duration", f"{estimate.estimated_duration_seconds // 60} min")

        st.caption(f"Estimated API calls: {estimate.estimated_api_calls}")
        st.session_state["cost_estimate"] = estimate.model_dump()
    except Exception as e:
        st.error(f"Cost estimation failed: {e}")

section_title("Developer Approval")
info_card(
    "Approval authorizes execution",
    "The migration plan is generated during execution by the Analyzer and Planner agents. "
    "Approving here allows the framework to proceed past the plan stage without waiting.",
)

comments = st.text_area("Comments (optional)", height=80)
col1, col2 = st.columns(2)
with col1:
    if st.button("Approve Plan", type="primary", width="stretch"):
        st.session_state["plan_approved"] = True
        st.session_state["approval_comments"] = comments
        st.success("Plan approved — proceed to Execution.")
with col2:
    if st.button("Reject Plan", width="stretch"):
        st.session_state["plan_approved"] = False
        st.warning("Plan rejected. Return to Repository to make changes.")

if st.session_state.get("plan_approved"):
    st.success("Plan approved — proceed to Execution.")
    if config.demo.enabled:
        st.caption("Demo mode: plan auto-approved; use **Run Demo Pipeline** on Execution (0 tokens).")
    if st.button("Go to Execution →", type="primary"):
        st.switch_page("pages/4_Execution.py")
