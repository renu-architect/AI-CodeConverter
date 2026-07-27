"""Helpers for including source code in LLM prompts without silent truncation."""


def format_code_for_prompt(
    code: str,
    label: str = "Source",
    max_chars: int = 24_000,
) -> str:
    """Format code for prompts, with an explicit notice when excerpted."""
    if not code:
        return f"# {label}: (empty)"

    lines = code.count("\n") + 1
    header = f"# {label}: {lines} lines, {len(code)} characters"

    if len(code) <= max_chars:
        return f"{header}\n# (complete file shown below)\n\n{code}"

    head_budget = int(max_chars * 0.55)
    tail_budget = max_chars - head_budget
    head = code[:head_budget]
    tail = code[-tail_budget:]
    omitted_lines = lines - head.count("\n") - tail.count("\n")

    return (
        f"{header}\n"
        f"# (excerpt only — {omitted_lines} middle lines omitted for token limits)\n\n"
        f"{head}\n\n"
        f"# ... [{omitted_lines} lines omitted] ...\n\n"
        f"{tail}"
    )


def build_code_context(
    *,
    original_code: str = "",
    converted_code: str = "",
    max_chars_per_file: int = 20_000,
) -> str:
    """Build a combined context block for review/validation agents."""
    sections: list[str] = []
    if original_code:
        sections.append(
            format_code_for_prompt(
                original_code, label="Original Glue Code", max_chars=max_chars_per_file
            )
        )
    if converted_code:
        sections.append(
            format_code_for_prompt(
                converted_code,
                label="Converted Synapse Code",
                max_chars=max_chars_per_file,
            )
        )
    return "\n\n".join(sections)
