"""
Token usage model for Claude Code API responses.

Tracks input/output tokens including cache statistics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import settings

logger = logging.getLogger(__name__)

PricingTable = dict[str, Any]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_model_entry(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and "input" in entry
        and "output" in entry
        and all(_is_number(v) for v in entry.values())
    )


def load_pricing(defaults_path: Path, override_path: Optional[Path]) -> PricingTable:
    """Shipped prices with the override applied per model (whole entry) and per multiplier; bad input is logged and skipped."""
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    pricing: PricingTable = {
        "default_model": defaults["default_model"],
        "multipliers": dict(defaults["multipliers"]),
        "models": dict(defaults["models"]),
    }
    if override_path is None or not override_path.is_file():
        return pricing
    try:
        override = json.loads(override_path.read_text(encoding="utf-8"))
        if not isinstance(override, dict):
            raise ValueError("top level must be a JSON object")
    except (OSError, ValueError) as e:
        logger.warning("Ignoring pricing override %s: %s", override_path, e)
        return pricing

    for model_id, entry in (override.get("models") or {}).items():
        if _valid_model_entry(entry):
            pricing["models"][model_id] = entry
        else:
            logger.warning("Ignoring pricing override for %s: needs numeric input/output", model_id)
    for key, value in (override.get("multipliers") or {}).items():
        if key in pricing["multipliers"] and _is_number(value):
            pricing["multipliers"][key] = value
        else:
            logger.warning("Ignoring pricing override multiplier %s=%r", key, value)
    default_model = override.get("default_model")
    if default_model is not None:
        if default_model in pricing["models"]:
            pricing["default_model"] = default_model
        else:
            logger.warning("Ignoring pricing override default_model %r: not priced", default_model)
    return pricing


# Prices load once at import; edits to the override file apply on API restart
_PRICING = load_pricing(
    Path(__file__).with_name("pricing.json"), settings.karma_base / "pricing.json"
)
MODEL_PRICING: dict[str, dict[str, float]] = _PRICING["models"]
DEFAULT_PRICING_MODEL: str = _PRICING["default_model"]

_FAMILIES = "fable|mythos|opus|sonnet|haiku"
# Modern IDs: claude-opus-4-8, claude-sonnet-4-5-20250929; legacy: claude-3-5-sonnet-20241022
_MODERN_ID = re.compile(rf"({_FAMILIES})(?:-(\d+))?(?:-(\d+))?")
_LEGACY_ID = re.compile(rf"claude-(\d+)(?:-(\d+))?-({_FAMILIES})")

ModelVersion = tuple[str, Optional[int], Optional[int]]


def _parse_model_id(model: str) -> Optional[ModelVersion]:
    """Extract (family, major, minor) from a model ID; date suffixes are not versions."""

    def version(part: Optional[str]) -> Optional[int]:
        return int(part) if part and len(part) < 8 else None

    model_lower = model.lower()
    legacy = _LEGACY_ID.search(model_lower)
    if legacy:
        return legacy.group(3), version(legacy.group(1)), version(legacy.group(2))
    modern = _MODERN_ID.search(model_lower)
    if modern:
        return modern.group(1), version(modern.group(2)), version(modern.group(3))
    return None


def _rank(major: Optional[int], minor: Optional[int]) -> tuple[int, int]:
    return (major or 0, minor or 0)


def _index_known_versions() -> tuple[
    dict[ModelVersion, str], dict[str, list[tuple[tuple[int, int], str]]]
]:
    """Map each priced (family, major, minor) to its ID, and each family to its versions, oldest first."""
    known: dict[ModelVersion, str] = {}
    by_family: dict[str, list[tuple[tuple[int, int], str]]] = {}
    for model_id in MODEL_PRICING:
        parsed = _parse_model_id(model_id)
        if parsed is None:
            continue
        family, major, minor = parsed
        if parsed in known:
            continue
        known[parsed] = model_id
        by_family.setdefault(family, []).append((_rank(major, minor), model_id))
    for versions in by_family.values():
        versions.sort()
    return known, by_family


_KNOWN_VERSIONS, _VERSIONS_BY_FAMILY = _index_known_versions()


@lru_cache(maxsize=None)
def _nearest_known(model: str, parsed: ModelVersion) -> str:
    """Closest priced version at or below the parsed one, preferring the same major version."""
    family, major, minor = parsed
    target = _rank(major, minor)
    versions = _VERSIONS_BY_FAMILY[family]
    pool = [v for v in versions if v[0][0] == target[0]] or versions
    at_or_below = [model_id for rank, model_id in pool if rank <= target]
    guess = at_or_below[-1] if at_or_below else pool[0][1]
    logger.warning("No pricing for %s; billing it as %s", model, guess)
    return guess


def _resolve_model(model: Optional[str]) -> dict[str, float]:
    """Resolve a model ID to its pricing; unknown versions bill like the nearest known one."""
    if not model:
        return MODEL_PRICING[DEFAULT_PRICING_MODEL]
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    parsed = _parse_model_id(model)
    if parsed is None:
        return MODEL_PRICING[DEFAULT_PRICING_MODEL]
    canonical = _KNOWN_VERSIONS.get(parsed) or _nearest_known(model, parsed)
    return MODEL_PRICING[canonical]


# Cache pricing multipliers of the base input price (cache reads can be overridden per model via "cache_read")
CACHE_WRITE_MULTIPLIER: float = _PRICING["multipliers"]["cache_write_5m"]
CACHE_WRITE_1H_MULTIPLIER: float = _PRICING["multipliers"]["cache_write_1h"]
CACHE_READ_MULTIPLIER: float = _PRICING["multipliers"]["cache_read"]


def pricing_fingerprint() -> str:
    """Hash of the effective prices; the indexer re-prices stored sessions when it changes."""
    effective = {
        "default_model": DEFAULT_PRICING_MODEL,
        "multipliers": [CACHE_WRITE_MULTIPLIER, CACHE_WRITE_1H_MULTIPLIER, CACHE_READ_MULTIPLIER],
        "models": MODEL_PRICING,
    }
    return hashlib.sha256(json.dumps(effective, sort_keys=True).encode()).hexdigest()


class TokenUsage(BaseModel):
    """
    Token usage statistics from an assistant message.

    Attributes:
        input_tokens: Direct input tokens consumed
        output_tokens: Output tokens generated
        cache_creation_input_tokens: Tokens used to create cache
        cache_read_input_tokens: Tokens read from cache (free/discounted)
        cache_creation_1h_input_tokens: Portion of cache_creation_input_tokens written with 1-hour TTL
        service_tier: API service tier (e.g., "standard")
    """

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)
    cache_creation_1h_input_tokens: int = Field(default=0, ge=0)
    service_tier: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _extract_cache_ttl_split(cls, data: Any) -> Any:
        """Lift the 1-hour cache-write count out of the API's nested cache_creation object."""
        if isinstance(data, dict) and "cache_creation_1h_input_tokens" not in data:
            cache_creation = data.get("cache_creation")
            if isinstance(cache_creation, dict):
                data = {
                    **data,
                    "cache_creation_1h_input_tokens": cache_creation.get(
                        "ephemeral_1h_input_tokens"
                    )
                    or 0,
                }
        return data

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
            cache_creation_1h_input_tokens=self.cache_creation_1h_input_tokens
            + other.cache_creation_1h_input_tokens,
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

        # Long-context threshold counts total context, including cache reads (matches billing)
        total_input = (
            self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens
        )
        threshold = pricing.get("long_context_threshold", 0)
        is_long = threshold > 0 and total_input > threshold

        input_price = pricing.get("input_long", pricing["input"]) if is_long else pricing["input"]
        output_price = (
            pricing.get("output_long", pricing["output"]) if is_long else pricing["output"]
        )

        cache_write_1h = min(self.cache_creation_1h_input_tokens, self.cache_creation_input_tokens)
        cache_write_5m = self.cache_creation_input_tokens - cache_write_1h

        uncached_input_cost = (self.input_tokens / 1_000_000) * input_price
        cache_write_5m_cost = (cache_write_5m / 1_000_000) * input_price * CACHE_WRITE_MULTIPLIER
        cache_write_1h_cost = (cache_write_1h / 1_000_000) * input_price * CACHE_WRITE_1H_MULTIPLIER
        cache_write_cost = cache_write_5m_cost + cache_write_1h_cost
        cache_read_cost = (
            (self.cache_read_input_tokens / 1_000_000)
            * input_price
            * pricing.get("cache_read", CACHE_READ_MULTIPLIER)
        )
        output_cost = (self.output_tokens / 1_000_000) * output_price

        return uncached_input_cost + cache_write_cost + cache_read_cost + output_cost


class UsageAccumulator:
    """
    Sums token usage and cost once per API response.

    Claude Code writes one JSONL line per content block and repeats the
    response's usage on each, so usage is keyed by message id. Later lines
    carry the final streamed counts, so the last line for an id wins.
    """

    def __init__(self) -> None:
        self._responses: dict[str, tuple[TokenUsage, Optional[str]]] = {}

    def add(self, msg: Any) -> None:
        """Record an AssistantMessage's usage under its response id."""
        if msg.usage is None:
            return
        key = msg.message_id or msg.request_id or msg.uuid
        self._responses[key] = (msg.usage, msg.model)

    @property
    def usage(self) -> TokenUsage:
        total = TokenUsage.zero()
        for usage, _ in self._responses.values():
            total = total + usage
        return total

    @property
    def cost(self) -> float:
        return sum(usage.calculate_cost(model) for usage, model in self._responses.values())
