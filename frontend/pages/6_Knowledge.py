"""Knowledge base search page."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from knowledge.engine import ChromaKnowledgeEngine
from theme import configure_page, page_header, section_title
from utils.config_loader import load_config

configure_page("Knowledge", icon="🧠")

page_header(
    "Knowledge Base",
    "Search migration patterns, corrections, and Synapse best practices.",
)

config = load_config()
engine = ChromaKnowledgeEngine(config.knowledge)

section_title("Pattern Search")
c1, c2 = st.columns([3, 1])
with c1:
    query = st.text_input(
        "Search",
        placeholder="Glue DynamicFrame to DataFrame conversion",
    )
with c2:
    collection = st.selectbox("Collection", config.knowledge.collections, index=0)

top_k = st.slider("Max results", min_value=1, max_value=20, value=5)

if st.button("Search", type="primary"):
    if query:
        with st.spinner("Searching knowledge base..."):
            results = engine.retrieve(query, collection, top_k)
            if results:
                for i, match in enumerate(results):
                    with st.expander(
                        f"Result {i + 1}  ·  distance {match.get('distance', 0):.4f}"
                    ):
                        st.write(match.get("content", "")[:2000])
                        if match.get("metadata"):
                            st.json(match["metadata"])
            else:
                st.info("No matching patterns found. Knowledge grows with each migration.")
    else:
        st.warning("Enter a search query.")

section_title("Store Correction")
with st.form("correction_form"):
    pattern = st.text_input("Pattern")
    correction = st.text_input("Correction")
    context_text = st.text_area("Context", height=100)
    if st.form_submit_button("Store Correction", type="primary"):
        if pattern and correction:
            engine.store_correction(pattern, correction, context_text)
            st.success("Correction stored in knowledge base.")
        else:
            st.error("Pattern and correction are required.")
