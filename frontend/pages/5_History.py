"""Migration history page."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from history.db import init_db
from history.metrics import MetricsService
from theme import configure_page, page_header, section_title, workflow_steps
from utils.config_loader import load_config

configure_page("History", icon="📜")

page_header(
    "Migration History",
    "Past workflows, token usage, and output package locations.",
)

workflow_steps(current=4)

config = load_config()

try:
    session_factory = init_db(config.database_url)
    metrics = MetricsService(session_factory)
    history = metrics.get_migration_history()
except Exception:
    history = []

section_title("Past Migrations")
if not history:
    st.info("No migration history yet. Run a migration to see results here.")
else:
    st.dataframe(history, width="stretch", hide_index=True)

section_title("Download Output Package")
c1, c2 = st.columns(2)
with c1:
    project_id = st.text_input("Project ID")
with c2:
    job_id = st.text_input("Job ID")

if st.button("Locate Output Package", type="primary"):
    if project_id and job_id:
        output_dir = Path(config.output_dir) / project_id / job_id
        if output_dir.exists():
            files = list(output_dir.rglob("*"))
            st.success(f"Found {len(files)} files in output package")
            for f in files:
                st.text(f"  {f.relative_to(output_dir)}")
        else:
            st.warning(f"Output directory not found: {output_dir}")
    else:
        st.warning("Enter both Project ID and Job ID.")
