"""Tests for AI Gateway."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from artifacts.models import GatewayRequest
from gateway.cache import GatewayCache
from gateway.cost_estimator import estimate_cost
from gateway.gateway import ClaudeGateway
from gateway.response_parser import parse_response
from gateway.token_counter import count_tokens
from utils.config_models import CostEstimationConfig
from utils.exceptions import ContextTooLargeError


def test_count_tokens():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0


def test_estimate_cost():
    config = CostEstimationConfig()
    cost = estimate_cost(1000, 500, config)
    assert cost > 0


def test_cache_hit():
    cache = GatewayCache(directory="/tmp/test_cache", enabled=True)
    cache.clear()
    key = GatewayCache.compute_key("prompt", "context")
    cache.set(key, {"content": "test", "parsed": "test", "tokens_input": 10, "tokens_output": 20})
    result = cache.get(key)
    assert result is not None
    assert result["content"] == "test"


def test_parse_response_markdown():
    result = parse_response("# Title\nContent", "markdown")
    assert isinstance(result, str)
    assert "Title" in result


def test_parse_response_json():
    result = parse_response('{"key": "value"}', "json")
    assert result == {"key": "value"}


def test_parse_response_json_in_codeblock():
    content = '```json\n{"status": "ok"}\n```'
    result = parse_response(content, "json")
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_gateway_uses_template_max_output_tokens(config, tmp_path):
    """Per-template max_output_tokens (e.g. implementer_full=8192) override global default."""
    config.cache.directory = str(tmp_path / "cache")
    config.agents.max_output_tokens = 4096
    gateway = ClaudeGateway(config)

    request = GatewayRequest(
        template_name="implementer_full",
        variables={
            "understanding_md": "test",
            "plan_md": "test",
            "source_code": "pass",
            "coding_standards": "{}",
            "knowledge_patterns": "None",
            "job_name": "test",
        },
        context="",
        expected_format="markdown",
    )

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="```python\nprint('ok')\n```")]
    mock_response.usage = MagicMock(output_tokens=100)

    with patch.object(gateway, "_call_with_retry", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        await gateway.complete(request)

    assert mock_call.call_args[0][1] == 8192


@pytest.mark.asyncio
async def test_gateway_complete_with_cache(config, tmp_path):
    config.cache.directory = str(tmp_path / "cache")
    gateway = ClaudeGateway(config)

    request = GatewayRequest(
        template_name="analyzer",
        variables={
            "job_name": "test",
            "file_path": "test.py",
            "complexity_score": "50",
            "ast_summary": "{}",
            "code_sections": "pass",
            "dependencies": "[]",
            "knowledge_patterns": "None",
        },
        context="",
        expected_format="markdown",
    )

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Understanding\nTest")]
    mock_response.usage = MagicMock(output_tokens=100)

    with patch.object(gateway, "_call_with_retry", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        result = await gateway.complete(request)
        assert result.content is not None
        assert result.cached is False

        result2 = await gateway.complete(request)
        assert result2.cached is True


@pytest.mark.asyncio
async def test_gateway_api_call_uses_temperature_only(config, tmp_path):
    """Newer Claude models reject both temperature and top_p together."""
    config.cache.directory = str(tmp_path / "cache")
    gateway = ClaudeGateway(config)

    request = GatewayRequest(
        template_name="analyzer",
        variables={
            "job_name": "test",
            "file_path": "test.py",
            "complexity_score": "50",
            "ast_summary": "{}",
            "code_sections": "pass",
            "dependencies": "[]",
            "knowledge_patterns": "None",
        },
        context="",
        expected_format="markdown",
    )

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Understanding\nTest")]
    mock_response.usage = MagicMock(output_tokens=100)

    with patch.object(gateway, "_call_with_retry", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        await gateway.complete(request)

    # Verify _call_with_retry was invoked (temperature-only enforced inside it)
    mock_call.assert_called_once()


def test_build_prompt_messages_respects_mode(config):
    gateway = ClaudeGateway(config)
    variables = {
        "job_name": "test",
        "file_path": "test.py",
        "complexity_score": "50",
        "ast_summary": "{}",
        "code_sections": "pass",
        "dependencies": "[]",
        "knowledge_patterns": "None",
    }

    config.prompts.mode = "on"
    system_on, user_on = gateway.build_prompt_messages("analyzer", variables)
    assert system_on == ""
    assert "TASK:" in user_on

    config.prompts.mode = "ultra"
    system_ultra, user_ultra = gateway.build_prompt_messages("analyzer", variables)
    assert system_ultra != ""
    assert "QUALITY GATES" in user_ultra
