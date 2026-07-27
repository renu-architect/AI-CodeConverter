"""Output comparison — sample data through Glue vs Synapse transforms."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import pandas as pd
import streamlit as st

from demo.output_runner import build_output_comparison
from theme import configure_page, page_header, section_title, workflow_steps
from utils.config_loader import load_config

configure_page("Output Comparison", icon="📊")

page_header(
    "Output Comparison",
    "Run sample Medicare data through Glue and Synapse logic and compare results.",
)

workflow_steps(current=4)  # Output comparison step

config = load_config()
report_dict = st.session_state.get("output_comparison")

if not report_dict:
    job_name = config.demo.default_job
    if st.session_state.get("selected_jobs"):
        job_name = st.session_state["selected_jobs"][0]
    try:
        report_dict = build_output_comparison(job_name=job_name).model_dump()
        st.session_state["output_comparison"] = report_dict
    except Exception as exc:
        st.error(f"Could not build output comparison: {exc}")
        st.stop()

status = report_dict.get("status", "UNKNOWN")
if status == "PASS":
    st.success(report_dict.get("message", "Outputs match"))
else:
    st.warning(report_dict.get("message", "Partial match"))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Input Rows", report_dict.get("input_rows", 0))
c2.metric("Glue Output", report_dict.get("glue_output_rows", 0))
c3.metric("Synapse Output", report_dict.get("synapse_output_rows", 0))
c4.metric("Match", f"{report_dict.get('match_pct', 0):.0f}%")

for note in report_dict.get("diff_summary", []):
    st.caption(f"• {note}")

section_title("Sample Input Data")
input_df = pd.DataFrame(report_dict.get("input_preview", []))
if input_df.empty:
    st.info("No input preview available.")
else:
    st.dataframe(input_df, width="stretch", hide_index=True)

section_title("Transform Output Comparison")
left, right = st.columns(2)
glue_df = pd.DataFrame(report_dict.get("glue_output", []))
synapse_df = pd.DataFrame(report_dict.get("synapse_output", []))

with left:
    st.markdown("##### Glue-equivalent output")
    st.dataframe(glue_df, width="stretch", hide_index=True)
with right:
    st.markdown("##### Synapse-converted output")
    st.dataframe(synapse_df, width="stretch", hide_index=True)

if not glue_df.empty and not synapse_df.empty:
    section_title("Row-Level Parity")
    merged = glue_df.merge(
        synapse_df,
        on=list(glue_df.columns),
        how="outer",
        indicator=True,
    )
    parity = merged["_merge"].value_counts().rename(
        {"both": "Matching rows", "left_only": "Glue only", "right_only": "Synapse only"}
    )
    st.bar_chart(parity)

nav1, nav2, nav3 = st.columns(3)
with nav1:
    if st.button("← Execution", width="stretch"):
        st.switch_page("pages/4_Execution.py")
with nav2:
    if st.button("Code Comparison", width="stretch"):
        st.switch_page("pages/8_Code_Comparison.py")
with nav3:
    if st.button("Re-run Parity Check", width="stretch"):
        job_name = config.demo.default_job
        if st.session_state.get("selected_jobs"):
            job_name = st.session_state["selected_jobs"][0]
        st.session_state["output_comparison"] = build_output_comparison(
            job_name=job_name
        ).model_dump()
        st.rerun()
