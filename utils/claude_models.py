"""Supported Claude API model IDs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaudeModelOption:
    model_id: str
    label: str
    description: str


SUPPORTED_CLAUDE_MODELS: list[ClaudeModelOption] = [
    ClaudeModelOption(
        model_id="claude-sonnet-4-6",
        label="Claude Sonnet 4.6 (Recommended)",
        description="Best balance of speed, cost, and quality for migrations.",
    ),
    ClaudeModelOption(
        model_id="claude-sonnet-4-5-20250929",
        label="Claude Sonnet 4.5",
        description="Previous generation Sonnet — stable dated snapshot.",
    ),
    ClaudeModelOption(
        model_id="claude-opus-4-6",
        label="Claude Opus 4.6",
        description="Highest quality for complex migrations. Higher cost.",
    ),
    ClaudeModelOption(
        model_id="claude-haiku-4-5-20251001",
        label="Claude Haiku 4.5",
        description="Fastest and cheapest. Good for simple jobs.",
    ),
]

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def get_model_ids() -> list[str]:
    return [m.model_id for m in SUPPORTED_CLAUDE_MODELS]


def get_model_option(model_id: str) -> ClaudeModelOption | None:
    for option in SUPPORTED_CLAUDE_MODELS:
        if option.model_id == model_id:
            return option
    return None


def normalize_model_id(model_id: str) -> str:
    """Return model_id if supported, otherwise default."""
    if model_id in get_model_ids():
        return model_id
    return DEFAULT_CLAUDE_MODEL
