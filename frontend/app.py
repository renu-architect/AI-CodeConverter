"""AI-SDLC Streamlit Application — UST branded home."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: F401

from utils.env import load_env

load_env()

import streamlit as st

from theme import configure_page, info_card, page_header, section_title

configure_page("Home", icon="🏠")

page_header(
    "AI-SDLC Migration Platform",
    "Enterprise multi-agent framework for migrating AWS Glue ETL jobs to Azure Synapse Spark Python.",
    badge="UST",
)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Status", "Ready")
with col2:
    st.metric("Version", "1.0.0")
with col3:
    st.metric("Agents", "7")
with col4:
    st.metric("Target", "Synapse")

section_title("Migration Workflow")
info_card(
    "1. Repository Scan",
    "Point to your Glue repository, detect jobs, and select which ETL pipelines to migrate.",
)
info_card(
    "2. Plan & Approve",
    "Review cost estimates and approve the migration plan before agents begin execution.",
)
info_card(
    "3. Live Execution",
    "Watch analyzer, planner, implementer, reviewer, and validator agents run with artifact reuse.",
)
info_card(
    "4. Output Comparison",
    "Run sample Medicare data through Glue and Synapse transforms and compare row-level results.",
)
info_card(
    "5. Code Comparison",
    "Compare original Glue source with converted Synapse Python side-by-side.",
)

st.divider()
c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Start — Scan Repository", type="primary", width="stretch"):
        st.switch_page("pages/2_Repository.py")
with c2:
    if st.button("View History", width="stretch"):
        st.switch_page("pages/5_History.py")
with c3:
    if st.button("Settings", width="stretch"):
        st.switch_page("pages/7_Settings.py")

st.caption("Powered by UST · Boundless Impact")
