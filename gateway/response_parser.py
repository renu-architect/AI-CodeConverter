"""Response parsing for Claude API outputs."""

import json
import re

from utils.logging import get_logger

logger = get_logger("gateway.response_parser")


def parse_response(content: str, expected_format: str) -> dict | str:
    """Parse Claude response into structured format."""
    content = content.strip()

    if expected_format == "json":
        return _parse_json(content)
    return content


def _parse_json(content: str) -> dict:
    """Extract and parse JSON from response content."""
    # Try direct parse first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in content
    brace_match = re.search(r"\{.*\}", content, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse JSON response, returning raw content")
    return {"raw": content}
