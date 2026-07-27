"""Configuration loader with YAML merge and environment overrides."""

import os
from pathlib import Path
from typing import Any

import yaml

from utils.env import get_api_key, load_env
from utils.config_models import (
    AgentConfig,
    AppConfig,
    CacheConfig,
    ClaudeConfig,
    CodingStandardsConfig,
    CostEstimationConfig,
    KnowledgeConfig,
    PromptConfig,
    DemoConfig,
    ScannerConfig,
)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_dir: str | Path | None = None) -> AppConfig:
    """Load configuration from YAML files with environment overrides."""
    load_env()

    if config_dir is None:
        config_dir = Path(os.getenv("AI_SDLC_CONFIG", "config"))
    else:
        config_dir = Path(config_dir)

    with open(config_dir / "default.yaml") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    user_config = config_dir / "user.yaml"
    if user_config.exists():
        with open(user_config) as f:
            user = yaml.safe_load(f)
            if user:
                config = deep_merge(config, user)

    claude_cfg = config.get("claude", {})
    api_key = get_api_key()
    if api_key:
        claude_cfg["api_key"] = api_key

    app_section = config.get("app", {})
    if os.getenv("AI_SDLC_LOG_LEVEL"):
        app_section["log_level"] = os.environ["AI_SDLC_LOG_LEVEL"]

    database_url = config.get("database", {}).get("url", "sqlite:///history/aisdlc.db")
    if os.getenv("AI_SDLC_DB_URL"):
        database_url = os.environ["AI_SDLC_DB_URL"]

    prompts_cfg = config.get("prompts", {})
    if os.getenv("AI_SDLC_PROMPT_MODE"):
        prompts_cfg["mode"] = os.environ["AI_SDLC_PROMPT_MODE"]

    if os.getenv("AI_SDLC_CLAUDE_MODEL"):
        claude_cfg["model"] = os.environ["AI_SDLC_CLAUDE_MODEL"]

    return AppConfig(
        name=app_section.get("name", "AI-SDLC Framework"),
        version=app_section.get("version", "1.0.0"),
        log_level=app_section.get("log_level", "INFO"),
        output_dir=app_section.get("output_dir", "outputs/"),
        artifacts_dir=app_section.get("artifacts_dir", "artifacts/"),
        claude=ClaudeConfig(**claude_cfg),
        cache=CacheConfig(**config.get("cache", {})),
        knowledge=KnowledgeConfig(**config.get("knowledge", {})),
        agents=AgentConfig(**config.get("agents", {})),
        scanner=ScannerConfig(**config.get("scanner", {})),
        cost_estimation=CostEstimationConfig(**config.get("cost_estimation", {})),
        coding_standards=CodingStandardsConfig(**config.get("coding_standards", {})),
        prompts=PromptConfig(**prompts_cfg),
        demo=DemoConfig(**config.get("demo", {})),
        database_url=database_url,
    )


def save_user_config(updates: dict[str, Any], config_dir: str | Path | None = None) -> Path:
    """Persist developer overrides to config/user.yaml."""
    if config_dir is None:
        config_dir = Path(os.getenv("AI_SDLC_CONFIG", "config"))
    else:
        config_dir = Path(config_dir)

    config_dir.mkdir(parents=True, exist_ok=True)
    user_path = config_dir / "user.yaml"

    existing: dict[str, Any] = {}
    if user_path.exists():
        with open(user_path) as f:
            loaded = yaml.safe_load(f)
            if loaded:
                existing = loaded

    merged = deep_merge(existing, updates)
    with open(user_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, sort_keys=False, default_flow_style=False)

    return user_path


def save_prompt_mode(mode: str, config_dir: str | Path | None = None) -> Path:
    """Save developer-selected prompt mode to user config."""
    return save_user_config({"prompts": {"mode": mode.lower()}}, config_dir=config_dir)


def save_claude_model(model: str, config_dir: str | Path | None = None) -> Path:
    """Save developer-selected Claude model to user config."""
    return save_user_config({"claude": {"model": model}}, config_dir=config_dir)
