"""Settings page."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: F401

import streamlit as st

from gateway.prompt_modes import list_prompt_modes, normalize_prompt_mode
from theme import configure_page, page_header, section_title
from utils.claude_models import SUPPORTED_CLAUDE_MODELS, get_model_ids
from utils.config_loader import load_config, save_claude_model, save_prompt_mode

configure_page("Settings", icon="⚙️")

page_header(
    "Settings",
    "Configure Claude model, prompt mode, and framework defaults.",
)

config = load_config()

section_title("Claude Model")
model_ids = get_model_ids()
model_labels = {m.model_id: m.label for m in SUPPORTED_CLAUDE_MODELS}
current_model = config.claude.model
current_model_index = model_ids.index(current_model) if current_model in model_ids else 0

selected_model = st.selectbox(
    "Claude Model",
    options=model_ids,
    index=current_model_index,
    format_func=lambda value: model_labels.get(value, value),
    help="Model used for all agent LLM calls via the gateway.",
)

selected_model_profile = next(
    m for m in SUPPORTED_CLAUDE_MODELS if m.model_id == selected_model
)
st.info(f"**{selected_model_profile.label}** — {selected_model_profile.description}")

if st.button("Save Claude Model", type="primary"):
    save_claude_model(selected_model)
    st.success(f"Saved: **{selected_model_profile.label}**")

section_title("Prompt Mode")
st.caption(
    "The framework applies the selected mode to every agent prompt automatically."
)

mode_profiles = list_prompt_modes()
mode_values = [p.mode.value for p in mode_profiles]
mode_labels = {p.mode.value: p.label for p in mode_profiles}

current_mode = normalize_prompt_mode(config.prompts.mode).value
current_index = mode_values.index(current_mode) if current_mode in mode_values else 1

selected_mode = st.selectbox(
    "Prompt Mode",
    options=mode_values,
    index=current_index,
    format_func=lambda value: mode_labels.get(value, value.title()),
)

selected_profile = next(p for p in mode_profiles if p.mode.value == selected_mode)
st.info(f"**{selected_profile.label}** — {selected_profile.description}")
st.caption(f"Estimated token usage: {selected_profile.token_hint}")

if st.button("Save Prompt Mode", type="primary"):
    save_prompt_mode(selected_mode)
    st.success(f"Saved: **{selected_profile.label}**")

section_title("Framework Configuration")

tab1, tab2, tab3 = st.tabs(["Application", "Agents", "Infrastructure"])

with tab1:
    st.markdown(f"**Name:** {config.name}")
    st.markdown(f"**Version:** {config.version}")
    st.markdown(f"**Log Level:** {config.log_level}")
    st.markdown(f"**Active Prompt Mode:** {mode_labels.get(current_mode, current_mode)}")

with tab2:
    st.markdown(f"**Max Context Tokens:** {config.agents.max_context_tokens:,}")
    st.markdown(f"**Reuse Artifacts:** `{config.agents.reuse_artifacts}`")
    st.markdown(f"**Max Output Tokens:** {config.agents.max_output_tokens:,}")
    st.markdown(f"**Validation Threshold:** {config.agents.validation_threshold}")
    st.markdown(f"**POC Mode:** `{config.agents.poc_mode}`")
    st.caption(
        "POC mode relaxes reviewer/validator gates for demos. "
        "Set `agents.poc_mode: false` in config for production rigor."
    )
    st.markdown(f"**Max Implement Iterations:** {config.agents.max_implement_iterations}")

with tab3:
    api_key_set = "Yes" if config.claude.api_key else "No"
    st.markdown(f"**API Key Configured:** {api_key_set}")
    if not config.claude.api_key:
        st.warning("Set `ANTHROPIC_API_KEY` in the project root `.env` file.")
    st.markdown(f"**Cache Enabled:** {config.cache.enabled}")
    st.markdown(f"**Database:** `{config.database_url}`")
    st.markdown(f"**Embedding Model:** {config.knowledge.embedding_model}")

st.caption("UST AI-SDLC · Structured logging active · Observability deferred")
