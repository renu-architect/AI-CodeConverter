"""Token counting for Claude API requests."""

import tiktoken

from utils.logging import get_logger

logger = get_logger("gateway.token_counter")

# Claude uses cl100k_base encoding (same as GPT-4)
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in text using cl100k_base encoding."""
    return len(_ENCODING.encode(text))


def count_messages_tokens(prompt: str, context: str) -> int:
    """Count total tokens for prompt + context."""
    return count_tokens(prompt + context)
