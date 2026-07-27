"""Prompt mode definitions and transformations for the AI Gateway."""

from dataclasses import dataclass

from utils.enums import PromptMode

PROMPT_MODE_ORDER: list[PromptMode] = [
    PromptMode.OFF,
    PromptMode.ON,
    PromptMode.MEDIUM,
    PromptMode.PRO,
    PromptMode.ULTRA,
]


@dataclass(frozen=True)
class PromptModeProfile:
    mode: PromptMode
    label: str
    description: str
    token_hint: str
    output_multiplier: float


PROMPT_MODE_PROFILES: dict[PromptMode, PromptModeProfile] = {
    PromptMode.OFF: PromptModeProfile(
        mode=PromptMode.OFF,
        label="Off",
        description=(
            "Verbose expert-style prompts with full context and explanations. "
            "Best for learning or when maximum narrative detail is needed. "
            "Highest token usage."
        ),
        token_hint="~150% tokens",
        output_multiplier=1.5,
    ),
    PromptMode.ON: PromptModeProfile(
        mode=PromptMode.ON,
        label="On (Caveman)",
        description=(
            "Default framework mode. Minimal TASK / INPUT / RULES / OUTPUT prompts. "
            "No fluff, deterministic output. Recommended for production migrations."
        ),
        token_hint="~100% tokens (baseline)",
        output_multiplier=1.0,
    ),
    PromptMode.MEDIUM: PromptModeProfile(
        mode=PromptMode.MEDIUM,
        label="Medium",
        description=(
            "Caveman structure plus concise quality checks. "
            "Balanced between token efficiency and output thoroughness."
        ),
        token_hint="~110% tokens",
        output_multiplier=1.1,
    ),
    PromptMode.PRO: PromptModeProfile(
        mode=PromptMode.PRO,
        label="Pro",
        description=(
            "Caveman structure with senior-engineer constraints, "
            "explicit verification steps, and assumption tracking."
        ),
        token_hint="~130% tokens",
        output_multiplier=1.3,
    ),
    PromptMode.ULTRA: PromptModeProfile(
        mode=PromptMode.ULTRA,
        label="Ultra",
        description=(
            "Maximum rigor: audit-grade instructions, quality gates, "
            "and self-review checklist. Best for critical/complex jobs. "
            "Highest quality, highest token cost."
        ),
        token_hint="~160% tokens",
        output_multiplier=1.6,
    ),
}


def normalize_prompt_mode(mode: str | PromptMode) -> PromptMode:
    """Normalize mode string to PromptMode enum."""
    if isinstance(mode, PromptMode):
        return mode
    normalized = str(mode).strip().lower()
    aliases = {
        "caveman": PromptMode.ON,
        "default": PromptMode.ON,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return PromptMode(normalized)
    except ValueError:
        return PromptMode.ON


def get_mode_profile(mode: str | PromptMode) -> PromptModeProfile:
    return PROMPT_MODE_PROFILES[normalize_prompt_mode(mode)]


def list_prompt_modes() -> list[PromptModeProfile]:
    return [PROMPT_MODE_PROFILES[m] for m in PROMPT_MODE_ORDER]


def apply_prompt_mode(
    base_prompt: str,
    template_name: str,
    mode: str | PromptMode,
) -> tuple[str, str]:
    """Transform base caveman prompt for the selected mode.

    Returns:
        (system_prompt, user_prompt) tuple for the Claude API.
    """
    profile = get_mode_profile(mode)
    mode_enum = profile.mode

    if mode_enum == PromptMode.ON:
        return "", base_prompt

    if mode_enum == PromptMode.OFF:
        system = (
            "You are an expert AWS Glue and Azure Synapse migration specialist. "
            "Provide comprehensive, well-explained technical analysis."
        )
        user = f"""Please complete the following migration task with thorough detail.

Agent template: {template_name}

{base_prompt}

Additional instructions:
- Explain reasoning clearly where helpful
- Be comprehensive and professional
- Follow the required output schema exactly
"""
        return system, user

    if mode_enum == PromptMode.MEDIUM:
        user = f"""{base_prompt}

QUALITY CHECKS:
- Be precise and complete
- Follow the output schema exactly
- No conversational filler in the response
"""
        return "", user

    if mode_enum == PromptMode.PRO:
        system = (
            "You are a senior data engineer specializing in AWS Glue to Azure Synapse migrations."
        )
        user = f"""{base_prompt}

PRO REQUIREMENTS:
- Verify every Glue API and transformation is addressed
- Document assumptions explicitly
- Cross-check output against the required schema
- Flag ambiguity or risk as structured findings
"""
        return system, user

    # ULTRA
    system = (
        "You are an elite enterprise migration architect with deep expertise in "
        "AWS Glue ETL and Azure Synapse Spark. Produce audit-grade migration artifacts."
    )
    user = f"""{base_prompt}

ULTRA EXECUTION:
1. Parse all input completely before responding
2. Validate each rule against the output schema
3. Cross-reference Glue APIs with Synapse equivalents
4. Document every assumption and risk
5. Self-review output before finalizing

QUALITY GATES:
- Zero missing sections in the output schema
- All transformations explicitly mapped
- Business logic preservation verified
- Performance and security considerations included
"""
    return system, user


def scaled_max_output_tokens(base_max_tokens: int, mode: str | PromptMode) -> int:
    """Scale max output tokens based on prompt mode."""
    profile = get_mode_profile(mode)
    return max(256, int(base_max_tokens * profile.output_multiplier))
