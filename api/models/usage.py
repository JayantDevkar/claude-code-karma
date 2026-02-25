"""
Token usage model for Claude Code API responses.

Tracks input/output tokens including cache statistics.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Pricing per 1M tokens (USD) - https://www.anthropic.com/pricing
# Long-context pricing applies when input exceeds the threshold (e.g., 200K for Sonnet 4.5)
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Claude 4.6
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
    # Claude 4.5
    "claude-opus-4-5-20251101": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "input_long": 6.0,
        "output_long": 22.5,
        "long_context_threshold": 200_000,
    },
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    # Claude 4.1
    "claude-opus-4-1-20250805": {"input": 15.0, "output": 75.0},
    # Claude 4
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    # Claude 3.5
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.0},
    # Claude 3 (legacy)
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}
DEFAULT_PRICING_MODEL = "claude-opus-4-6"

# Model alias → canonical model ID for fuzzy matching unknown model strings
_MODEL_FAMILY_PATTERNS: list[tuple[str, str]] = [
    ("haiku-4-5", "claude-haiku-4-5-20251001"),
    ("haiku-4", "claude-haiku-4-5-20251001"),
    ("haiku-3-5", "claude-3-5-haiku-20241022"),
    ("haiku", "claude-haiku-4-5-20251001"),
    ("sonnet-4-5", "claude-sonnet-4-5-20250929"),
    ("sonnet-4", "claude-sonnet-4-20250514"),
    ("sonnet-3-5", "claude-3-5-sonnet-20241022"),
    ("sonnet", "claude-sonnet-4-5-20250929"),
    ("opus-4-6", "claude-opus-4-6"),
    ("opus-4-5", "claude-opus-4-5-20251101"),
    ("opus-4-1", "claude-opus-4-1-20250805"),
    ("opus-4", "claude-opus-4-20250514"),
    ("opus-3", "claude-3-opus-20240229"),
    ("opus", "claude-opus-4-6"),
]


def _resolve_model(model: Optional[str]) -> dict[str, float]:
    """Resolve a model name to its pricing dict, with fuzzy fallback for unknown IDs."""
    if model is None:
        return MODEL_PRICING[DEFAULT_PRICING_MODEL]
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Fuzzy match: check if the model string contains a known family pattern
    model_lower = model.lower()
    for pattern, canonical in _MODEL_FAMILY_PATTERNS:
        if pattern in model_lower:
            return MODEL_PRICING[canonical]
    return MODEL_PRICING[DEFAULT_PRICING_MODEL]


# Cache pricing multipliers (same across all models)
CACHE_WRITE_MULTIPLIER = 1.25  # Cache writes cost 125% of base input price (5-min TTL)
CACHE_READ_MULTIPLIER = 0.10  # Cache reads cost 10% of base input price


class TokenUsage(BaseModel):
    """
    Token usage statistics from an assistant message.

    Attributes:
        input_tokens: Direct input tokens consumed
        output_tokens: Output tokens generated
        cache_creation_input_tokens: Tokens used to create cache
        cache_read_input_tokens: Tokens read from cache (free/discounted)
        service_tier: API service tier (e.g., "standard")
    """

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)
    service_tier: Optional[str] = None

    @property
    def total_input(self) -> int:
        """Total input tokens including cache creation (actual tokens processed)."""
        return self.input_tokens + self.cache_creation_input_tokens

    @property
    def total_tokens(self) -> int:
        """Total tokens (all input types + output)."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
            + self.output_tokens
        )

    @property
    def cache_hit_rate(self) -> float:
        """
        Proportion of cacheable input tokens served from cache.

        Returns 0.0 if no cacheable tokens.
        """
        total_cacheable = (
            self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens
        )
        if total_cacheable == 0:
            return 0.0
        return self.cache_read_input_tokens / total_cacheable

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Aggregate token usage from multiple messages."""
        if not isinstance(other, TokenUsage):
            return NotImplemented
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens
            + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
            service_tier=self.service_tier or other.service_tier,
        )

    @classmethod
    def zero(cls) -> "TokenUsage":
        """Create a zero-valued usage instance for aggregation."""
        return cls()

    def calculate_cost(self, model: Optional[str] = None) -> float:
        """
        Calculate cost based on token usage and model pricing.

        Handles long-context pricing for models that charge more when total
        input tokens exceed a threshold (e.g., Sonnet 4.5 >200K tokens).

        Args:
            model: Model name (e.g., "claude-sonnet-4-20250514").
                   Uses fuzzy matching for unknown model IDs to pick the
                   closest family pricing instead of defaulting to Opus.

        Returns:
            Estimated cost in USD.
        """
        pricing = _resolve_model(model)

        total_input = (
            self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens
        )
        threshold = pricing.get("long_context_threshold", 0)
        is_long = threshold > 0 and total_input > threshold

        input_price = pricing.get("input_long", pricing["input"]) if is_long else pricing["input"]
        output_price = (
            pricing.get("output_long", pricing["output"]) if is_long else pricing["output"]
        )

        uncached_input_cost = (self.input_tokens / 1_000_000) * input_price
        cache_write_cost = (
            (self.cache_creation_input_tokens / 1_000_000) * input_price * CACHE_WRITE_MULTIPLIER
        )
        cache_read_cost = (
            (self.cache_read_input_tokens / 1_000_000) * input_price * CACHE_READ_MULTIPLIER
        )
        output_cost = (self.output_tokens / 1_000_000) * output_price

        return uncached_input_cost + cache_write_cost + cache_read_cost + output_cost
