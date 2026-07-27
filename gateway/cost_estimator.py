"""Cost estimation for Claude API calls."""

from utils.config_models import CostEstimationConfig


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    config: CostEstimationConfig,
) -> float:
    """Estimate cost in USD based on token counts."""
    input_cost = (input_tokens / 1_000_000) * config.input_price_per_million
    output_cost = (output_tokens / 1_000_000) * config.output_price_per_million
    return round(input_cost + output_cost, 6)
