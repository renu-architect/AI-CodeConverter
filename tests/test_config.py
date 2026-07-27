"""Tests for configuration loader."""

import os

from utils.config_loader import load_config
from utils.env import get_api_key, load_env


def test_load_config_returns_valid_config():
    config = load_config()
    assert config.name == "AI-SDLC Framework"
    assert config.claude.model == "claude-sonnet-4-6"
    assert config.claude.temperature == 0.0
    assert config.agents.max_context_tokens == 24000


def test_load_config_has_required_sections():
    config = load_config()
    assert config.cache.enabled is True
    assert config.knowledge.top_k == 5
    assert config.scanner.max_file_size_mb == 10


def test_load_env_from_dotenv():
    env_path = load_env()
    assert env_path is not None
    assert env_path.name == ".env"


def test_api_key_loaded_into_config(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    config = load_config()
    assert config.claude.api_key == "sk-ant-test-key"


def test_get_api_key_reads_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    assert get_api_key() == "sk-ant-from-env"


def test_prompt_mode_from_user_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        "app:\n  name: Test\nprompts:\n  mode: on\nagents: {}\nclaude: {}\ncache: {}\n"
        "knowledge: {}\nscanner: {}\ncost_estimation: {}\ncoding_standards: {}\n"
        "database:\n  url: sqlite:///test.db\n",
        encoding="utf-8",
    )
    from utils.config_loader import save_prompt_mode, load_config

    save_prompt_mode("ultra", config_dir=config_dir)
    config = load_config(config_dir=config_dir)
    assert config.prompts.mode == "ultra"
