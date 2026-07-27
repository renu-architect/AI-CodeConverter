"""Tests for code context formatting."""

from utils.code_context import build_code_context, format_code_for_prompt


def test_format_code_for_prompt_shows_complete_file_for_small_code():
    code = "line1\nline2\nline3"
    result = format_code_for_prompt(code, label="Test")
    assert "complete file shown" in result
    assert "line3" in result


def test_format_code_for_prompt_marks_excerpt_for_large_code():
    code = "x" * 30_000
    result = format_code_for_prompt(code, label="Test", max_chars=1000)
    assert "excerpt only" in result
    assert "lines omitted" in result


def test_build_code_context_includes_both_files():
    result = build_code_context(
        original_code="glue code",
        converted_code="synapse code",
    )
    assert "Original Glue Code" in result
    assert "Converted Synapse Code" in result
