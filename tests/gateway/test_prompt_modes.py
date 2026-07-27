"""Tests for prompt mode transformations."""

from gateway.prompt_modes import (
    apply_prompt_mode,
    list_prompt_modes,
    normalize_prompt_mode,
    scaled_max_output_tokens,
)
from utils.enums import PromptMode


BASE_PROMPT = """TASK: Analyze AWS Glue ETL job.
INPUT: Job: test_job
RULES: Document APIs.
OUTPUT: Understanding.md schema."""


def test_normalize_prompt_mode_aliases():
    assert normalize_prompt_mode("on") == PromptMode.ON
    assert normalize_prompt_mode("Caveman") == PromptMode.ON
    assert normalize_prompt_mode("ULTRA") == PromptMode.ULTRA
    assert normalize_prompt_mode("unknown") == PromptMode.ON


def test_on_mode_unchanged():
    system, user = apply_prompt_mode(BASE_PROMPT, "analyzer", PromptMode.ON)
    assert system == ""
    assert user == BASE_PROMPT


def test_off_mode_adds_verbose_wrapper():
    system, user = apply_prompt_mode(BASE_PROMPT, "analyzer", PromptMode.OFF)
    assert "expert" in system.lower()
    assert "thorough detail" in user.lower()
    assert BASE_PROMPT in user


def test_medium_mode_adds_quality_checks():
    system, user = apply_prompt_mode(BASE_PROMPT, "analyzer", PromptMode.MEDIUM)
    assert system == ""
    assert "QUALITY CHECKS" in user


def test_pro_mode_adds_requirements():
    system, user = apply_prompt_mode(BASE_PROMPT, "analyzer", PromptMode.PRO)
    assert "senior data engineer" in system.lower()
    assert "PRO REQUIREMENTS" in user


def test_ultra_mode_adds_quality_gates():
    system, user = apply_prompt_mode(BASE_PROMPT, "analyzer", PromptMode.ULTRA)
    assert "architect" in system.lower()
    assert "QUALITY GATES" in user


def test_scaled_max_output_tokens_increases_with_mode():
    base = 1000
    assert scaled_max_output_tokens(base, PromptMode.ON) == 1000
    assert scaled_max_output_tokens(base, PromptMode.ULTRA) > base


def test_list_prompt_modes_has_all_levels():
    modes = list_prompt_modes()
    assert len(modes) == 5
    assert [m.mode for m in modes] == list(PromptMode)
