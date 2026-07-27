"""Streamlit helpers for zero-token demo mode."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import bootstrap  # noqa: F401 — adds project root to sys.path

from demo.constants import DEFAULT_JOB_NAME, get_default_glue_repo
from parser.scanner import GlueRepositoryScanner
from utils.config_models import AppConfig


def resolve_demo_repo_path(config: AppConfig) -> str:
    """Resolve configured default repo to an absolute path."""
    configured = Path(config.demo.default_repo)
    if configured.is_absolute():
        return str(configured)
    return str(get_default_glue_repo().parent / configured.name)


def ensure_demo_repo_defaults(config: AppConfig) -> None:
    """Pre-fill session state for demo repository and job selection."""
    if "repo_path" not in st.session_state:
        st.session_state["repo_path"] = resolve_demo_repo_path(config)
    if config.demo.auto_approve_plan:
        st.session_state["plan_approved"] = True


def scan_demo_repository(config: AppConfig) -> bool:
    """Scan default Glue repo and select the demo job. Returns True on success."""
    repo_path = st.session_state.get("repo_path") or resolve_demo_repo_path(config)
    if not Path(repo_path).exists():
        return False

    scanner = GlueRepositoryScanner(config.scanner)
    job_name = config.demo.default_job or DEFAULT_JOB_NAME
    result = scanner.scan(
        repo_path,
        [job_name],
        project_id=st.session_state.get("project_id"),
        artifacts_dir=config.artifacts_dir,
    )
    st.session_state["project_scan"] = result.model_dump(mode="json")
    st.session_state["repo_path"] = repo_path
    st.session_state["project_id"] = result.project_id
    st.session_state["selected_jobs"] = [job_name]
    if config.demo.auto_approve_plan:
        st.session_state["plan_approved"] = True
    return True
