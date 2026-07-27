"""Dashboard page — overview metrics and recent activity."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from theme import configure_page, page_header, section_title
from utils.config_loader import load_config

configure_page("Dashboard", icon="📊")

page_header(
    "Dashboard",
    "Migration metrics, token usage, and quality scores across all workflows.",
)

config = load_config()

try:
    from history.db import init_db
    from history.metrics import MetricsService

    session_factory = init_db(config.database_url)
    metrics = MetricsService(session_factory)
    dashboard = metrics.get_dashboard_metrics()
except Exception:
    dashboard = {
        "total_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "avg_review_score": 0.0,
        "avg_validation_score": 0.0,
    }

section_title("Overview")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Jobs", dashboard["total_jobs"])
with col2:
    st.metric("Completed", dashboard["completed_jobs"])
with col3:
    st.metric("Failed", dashboard["failed_jobs"])
with col4:
    st.metric("Total Cost", f"${dashboard['total_cost_usd']:.4f}")

col5, col6, col7 = st.columns(3)
with col5:
    st.metric("Total Tokens", f"{dashboard['total_tokens']:,}")
with col6:
    st.metric("Avg Review Score", f"{dashboard['avg_review_score']:.1f}")
with col7:
    st.metric("Avg Validation Score", f"{dashboard['avg_validation_score']:.1f}")

section_title("Quick Actions")
col_a, col_b, col_c = st.columns(3)
with col_a:
    if st.button("Scan Repository", type="primary", width="stretch"):
        st.switch_page("pages/2_Repository.py")
with col_b:
    if st.button("View History", width="stretch"):
        st.switch_page("pages/5_History.py")
with col_c:
    if st.button("Search Knowledge", width="stretch"):
        st.switch_page("pages/6_Knowledge.py")
