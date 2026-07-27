"""AI Gateway implementation — sole Claude API entry point."""

import asyncio
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import anthropic
import yaml
from jinja2 import Template

from artifacts.models import GatewayRequest, GatewayResponse
from gateway.cache import GatewayCache
from gateway.cost_estimator import estimate_cost
from gateway.prompt_modes import apply_prompt_mode, scaled_max_output_tokens
from gateway.response_parser import parse_response
from gateway.token_counter import count_messages_tokens, count_tokens
from utils.config_models import AppConfig
from utils.exceptions import ContextTooLargeError, GatewayError
from utils.logging import get_logger, log_with_context

logger = get_logger("gateway")


class AIGateway(ABC):
    """Abstract base class for AI Gateway."""

    @abstractmethod
    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Send prompt to Claude and return parsed response."""

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD for token counts."""


class ClaudeGateway(AIGateway):
    """Claude API gateway with caching, retries, and structured logging."""

    def __init__(self, config: AppConfig, prompts_dir: str = "prompts") -> None:
        self.config = config
        self.prompts_dir = Path(prompts_dir)
        self.cache = GatewayCache(
            directory=config.cache.directory,
            ttl_seconds=config.cache.ttl_seconds,
            enabled=config.cache.enabled,
        )
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            api_key = self.config.claude.api_key
            if not api_key:
                raise GatewayError(
                    "ANTHROPIC_API_KEY not configured. "
                    "Set it in the project root .env file: ANTHROPIC_API_KEY=sk-ant-..."
                )
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        return self._client

    def load_prompt_template(self, template_name: str) -> dict:
        """Load prompt template from YAML file."""
        path = self.prompts_dir / f"{template_name}.yaml"
        if not path.exists():
            raise GatewayError(f"Prompt template not found: {path}")
        with open(path) as f:
            return yaml.safe_load(f)

    def build_prompt(self, template_name: str, variables: dict[str, str]) -> str:
        """Build prompt from template and variables (caveman base)."""
        template_data = self.load_prompt_template(template_name)
        template_str = template_data.get("template", "")
        return Template(template_str).render(**variables)

    def build_prompt_messages(
        self, template_name: str, variables: dict[str, str]
    ) -> tuple[str, str]:
        """Build system + user prompts with the configured prompt mode applied."""
        base_prompt = self.build_prompt(template_name, variables)
        return apply_prompt_mode(base_prompt, template_name, self.config.prompts.mode)

    def compress_context(self, context: str, max_tokens: int) -> str:
        """Truncate context to fit within token budget."""
        tokens = count_tokens(context)
        if tokens <= max_tokens:
            return context
        # Truncate by character ratio (approximate)
        ratio = max_tokens / tokens
        truncated_len = int(len(context) * ratio * 0.95)
        truncated = context[:truncated_len]
        truncated += "\n\n[... context truncated due to token limit ...]"
        logger.warning(
            "Context compressed",
            extra={"original_tokens": tokens, "max_tokens": max_tokens},
        )
        return truncated

    def estimate_tokens(self, text: str) -> int:
        return count_tokens(text)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return estimate_cost(input_tokens, output_tokens, self.config.cost_estimation)

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Execute Claude API call with caching and retries."""
        start_time = time.time()

        system_prompt, prompt = self.build_prompt_messages(
            request.template_name, request.variables
        )
        context = self.compress_context(
            request.context, self.config.agents.max_context_tokens
        )

        mode_tag = self.config.prompts.mode.lower()
        cache_key = GatewayCache.compute_key(f"{mode_tag}||{prompt}", context)
        cached = self.cache.get(cache_key)
        if cached:
            return GatewayResponse(
                content=cached["content"],
                parsed=cached["parsed"],
                tokens_input=cached["tokens_input"],
                tokens_output=cached["tokens_output"],
                cost_usd=0.0,
                latency_ms=0,
                cached=True,
                model=self.config.claude.model,
            )

        tokens_in = count_messages_tokens(prompt, context)
        if tokens_in > self.config.agents.max_context_tokens:
            raise ContextTooLargeError(
                f"Input tokens ({tokens_in}) exceed limit "
                f"({self.config.agents.max_context_tokens})"
            )

        max_output = request.max_output_tokens
        if max_output is None:
            template_data = self.load_prompt_template(request.template_name)
            max_output = template_data.get("max_output_tokens")
        max_output = max_output or self.config.agents.max_output_tokens
        max_output = scaled_max_output_tokens(max_output, self.config.prompts.mode)
        full_content = f"{prompt}\n\n{context}" if context else prompt

        response = await self._call_with_retry(full_content, max_output, system_prompt)

        content = response.content[0].text
        parsed = parse_response(content, request.expected_format)
        tokens_out = response.usage.output_tokens
        cost = self.estimate_cost(tokens_in, tokens_out)
        latency_ms = int((time.time() - start_time) * 1000)

        log_with_context(
            logger,
            20,
            "Gateway call completed",
            model=self.config.claude.model,
            template=request.template_name,
            prompt_mode=self.config.prompts.mode,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
            latency_ms=latency_ms,
            cached=False,
        )

        result = GatewayResponse(
            content=content,
            parsed=parsed,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
            latency_ms=latency_ms,
            cached=False,
            model=self.config.claude.model,
        )

        self.cache.set(
            cache_key,
            {
                "content": content,
                "parsed": parsed,
                "tokens_input": tokens_in,
                "tokens_output": tokens_out,
            },
        )

        return result

    async def _call_with_retry(
        self, content: str, max_tokens: int, system: str = ""
    ) -> anthropic.types.Message:
        """Call Claude API with exponential backoff retry."""
        client = self._get_client()
        max_retries = self.config.claude.max_retries
        retryable_statuses = {429, 500, 502, 503}

        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                kwargs: dict = {
                    "model": self.config.claude.model,
                    "max_tokens": max_tokens,
                    "temperature": self.config.claude.temperature,
                    "messages": [{"role": "user", "content": content}],
                    "timeout": self.config.claude.timeout_seconds,
                }
                # Newer Claude models reject requests with both temperature and top_p.
                # Use temperature only (deterministic output at 0.0).
                if system:
                    kwargs["system"] = system
                return await client.messages.create(**kwargs)
            except anthropic.APIStatusError as e:
                last_error = e
                if e.status_code not in retryable_statuses or attempt == max_retries:
                    raise GatewayError(f"Claude API error: {e.message}") from e
                wait = 2**attempt
                logger.warning(
                    f"Retrying after {wait}s",
                    extra={"attempt": attempt + 1, "status": e.status_code},
                )
                await asyncio.sleep(wait)
            except anthropic.APITimeoutError as e:
                last_error = e
                if attempt == max_retries:
                    raise GatewayError("Claude API timeout") from e
                wait = 2**attempt
                await asyncio.sleep(wait)

        raise GatewayError(f"Max retries exceeded: {last_error}")
