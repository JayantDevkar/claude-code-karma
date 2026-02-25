"""
Unit tests for TokenUsage model.

Tests cover instantiation, computed properties, aggregation,
immutability, validation, and edge cases.
"""

import pytest
from pydantic import ValidationError

from models import TokenUsage

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def zero_usage() -> TokenUsage:
    """TokenUsage with all zero values."""
    return TokenUsage.zero()


@pytest.fixture
def typical_usage() -> TokenUsage:
    """TokenUsage with typical values from a conversation."""
    return TokenUsage(
        input_tokens=100,
        output_tokens=500,
        cache_creation_input_tokens=50000,
        cache_read_input_tokens=10000,
        service_tier="standard",
    )


@pytest.fixture
def no_cache_usage() -> TokenUsage:
    """TokenUsage with no cache activity."""
    return TokenUsage(
        input_tokens=1000,
        output_tokens=2000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        service_tier="standard",
    )


@pytest.fixture
def all_cache_hits_usage() -> TokenUsage:
    """TokenUsage with all input from cache hits."""
    return TokenUsage(
        input_tokens=0,
        output_tokens=100,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=5000,
        service_tier="standard",
    )


# =============================================================================
# Basic Instantiation Tests
# =============================================================================


class TestTokenUsageInstantiation:
    """Tests for basic TokenUsage instantiation."""

    def test_default_values(self):
        """TokenUsage should have sensible defaults for all fields."""
        usage = TokenUsage()

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 0
        assert usage.service_tier is None

    def test_all_fields_populated(self, sample_usage_data):
        """TokenUsage should accept all fields from sample data."""
        usage = TokenUsage(**sample_usage_data)

        assert usage.input_tokens == 100
        assert usage.output_tokens == 500
        assert usage.cache_creation_input_tokens == 50000
        assert usage.cache_read_input_tokens == 10000
        assert usage.service_tier == "standard"

    def test_partial_fields(self):
        """TokenUsage should accept partial field specification."""
        usage = TokenUsage(input_tokens=50, output_tokens=100)

        assert usage.input_tokens == 50
        assert usage.output_tokens == 100
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 0
        assert usage.service_tier is None

    def test_service_tier_optional(self):
        """service_tier should be optional and accept any string."""
        usage_none = TokenUsage(input_tokens=100)
        assert usage_none.service_tier is None

        usage_standard = TokenUsage(input_tokens=100, service_tier="standard")
        assert usage_standard.service_tier == "standard"

        usage_premium = TokenUsage(input_tokens=100, service_tier="premium")
        assert usage_premium.service_tier == "premium"


# =============================================================================
# Computed Properties Tests
# =============================================================================


class TestTokenUsageComputedProperties:
    """Tests for computed properties: total_input, total_tokens, cache_hit_rate."""

    def test_total_input_calculation(self, typical_usage):
        """total_input should sum input_tokens and cache_creation_input_tokens."""
        # input_tokens(100) + cache_creation_input_tokens(50000)
        assert typical_usage.total_input == 50100

    def test_total_input_zero_when_empty(self, zero_usage):
        """total_input should be 0 when no input tokens."""
        assert zero_usage.total_input == 0

    def test_total_input_no_cache_creation(self, no_cache_usage):
        """total_input should equal input_tokens when no cache creation."""
        assert no_cache_usage.total_input == 1000

    def test_total_tokens_calculation(self, typical_usage):
        """total_tokens should sum all token types."""
        # input(100) + cache_creation(50000) + cache_read(10000) + output(500)
        expected = 100 + 50000 + 10000 + 500
        assert typical_usage.total_tokens == expected

    def test_total_tokens_zero_when_empty(self, zero_usage):
        """total_tokens should be 0 when all fields are zero."""
        assert zero_usage.total_tokens == 0

    def test_total_tokens_no_cache(self, no_cache_usage):
        """total_tokens should sum input and output when no cache."""
        # input(1000) + output(2000)
        assert no_cache_usage.total_tokens == 3000

    def test_cache_hit_rate_typical(self, typical_usage):
        """cache_hit_rate should calculate proportion of cache reads."""
        # cache_read(10000) / (input(100) + cache_creation(50000) + cache_read(10000))
        expected = 10000 / (100 + 50000 + 10000)
        assert typical_usage.cache_hit_rate == pytest.approx(expected)

    def test_cache_hit_rate_zero_when_no_cacheable(self, zero_usage):
        """cache_hit_rate should be 0.0 when no cacheable tokens."""
        assert zero_usage.cache_hit_rate == 0.0

    def test_cache_hit_rate_no_cache_usage(self, no_cache_usage):
        """cache_hit_rate should be 0.0 when no cache reads."""
        assert no_cache_usage.cache_hit_rate == 0.0

    def test_cache_hit_rate_all_from_cache(self, all_cache_hits_usage):
        """cache_hit_rate should be 1.0 when all input from cache."""
        # cache_read(5000) / (input(0) + cache_creation(0) + cache_read(5000))
        assert all_cache_hits_usage.cache_hit_rate == 1.0

    def test_cache_hit_rate_output_only(self):
        """cache_hit_rate should be 0.0 when only output tokens exist."""
        usage = TokenUsage(output_tokens=1000)
        assert usage.cache_hit_rate == 0.0


# =============================================================================
# Addition Operator Tests
# =============================================================================


class TestTokenUsageAddition:
    """Tests for __add__ operator for aggregating usage."""

    def test_add_two_usages(self, typical_usage):
        """Adding two usages should sum all token fields."""
        other = TokenUsage(
            input_tokens=200,
            output_tokens=300,
            cache_creation_input_tokens=1000,
            cache_read_input_tokens=500,
            service_tier="standard",
        )
        result = typical_usage + other

        assert result.input_tokens == 100 + 200
        assert result.output_tokens == 500 + 300
        assert result.cache_creation_input_tokens == 50000 + 1000
        assert result.cache_read_input_tokens == 10000 + 500

    def test_add_preserves_service_tier_from_first(self, typical_usage):
        """Addition should preserve service_tier from first operand if set."""
        other = TokenUsage(input_tokens=100, service_tier="premium")
        result = typical_usage + other

        assert result.service_tier == "standard"

    def test_add_uses_other_service_tier_when_first_none(self):
        """Addition should use other's service_tier when first is None."""
        first = TokenUsage(input_tokens=100, service_tier=None)
        other = TokenUsage(input_tokens=100, service_tier="premium")
        result = first + other

        assert result.service_tier == "premium"

    def test_add_with_zero(self, typical_usage, zero_usage):
        """Adding zero usage should return equivalent values."""
        result = typical_usage + zero_usage

        assert result.input_tokens == typical_usage.input_tokens
        assert result.output_tokens == typical_usage.output_tokens
        assert result.cache_creation_input_tokens == typical_usage.cache_creation_input_tokens
        assert result.cache_read_input_tokens == typical_usage.cache_read_input_tokens

    def test_add_zero_to_zero(self, zero_usage):
        """Adding zero to zero should return zero usage."""
        result = zero_usage + zero_usage

        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.cache_creation_input_tokens == 0
        assert result.cache_read_input_tokens == 0

    def test_add_returns_new_instance(self, typical_usage):
        """Addition should return a new TokenUsage instance."""
        other = TokenUsage(input_tokens=100)
        result = typical_usage + other

        assert result is not typical_usage
        assert result is not other

    def test_add_non_tokenusage_returns_not_implemented(self, typical_usage):
        """Adding non-TokenUsage should return NotImplemented."""
        result = typical_usage.__add__(42)
        assert result is NotImplemented

        result = typical_usage.__add__("not a usage")
        assert result is NotImplemented

        result = typical_usage.__add__(None)
        assert result is NotImplemented

    def test_add_chain(self, typical_usage):
        """Chaining additions should work correctly."""
        usage1 = TokenUsage(input_tokens=100, output_tokens=50)
        usage2 = TokenUsage(input_tokens=200, output_tokens=100)
        usage3 = TokenUsage(input_tokens=300, output_tokens=150)

        result = usage1 + usage2 + usage3

        assert result.input_tokens == 600
        assert result.output_tokens == 300


# =============================================================================
# zero() Class Method Tests
# =============================================================================


class TestTokenUsageZeroMethod:
    """Tests for zero() class method."""

    def test_zero_returns_zero_values(self):
        """zero() should return TokenUsage with all zeros."""
        usage = TokenUsage.zero()

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 0
        assert usage.service_tier is None

    def test_zero_returns_new_instance_each_call(self):
        """zero() should return a new instance each call."""
        usage1 = TokenUsage.zero()
        usage2 = TokenUsage.zero()

        # Note: With frozen=True, instances with same values might be considered equal
        # but they should still be separate objects
        assert usage1 == usage2  # Equal by value
        assert usage1 is not usage2  # Different objects

    def test_zero_useful_for_aggregation(self):
        """zero() should work as starting point for aggregation."""
        usages = [
            TokenUsage(input_tokens=100, output_tokens=50),
            TokenUsage(input_tokens=200, output_tokens=100),
            TokenUsage(input_tokens=300, output_tokens=150),
        ]

        total = TokenUsage.zero()
        for usage in usages:
            total = total + usage

        assert total.input_tokens == 600
        assert total.output_tokens == 300


# =============================================================================
# Immutability Tests
# =============================================================================


class TestTokenUsageImmutability:
    """Tests for frozen=True immutability."""

    def test_cannot_modify_input_tokens(self, typical_usage):
        """Should not be able to modify input_tokens after creation."""
        with pytest.raises(ValidationError):
            typical_usage.input_tokens = 999

    def test_cannot_modify_output_tokens(self, typical_usage):
        """Should not be able to modify output_tokens after creation."""
        with pytest.raises(ValidationError):
            typical_usage.output_tokens = 999

    def test_cannot_modify_cache_creation_input_tokens(self, typical_usage):
        """Should not be able to modify cache_creation_input_tokens after creation."""
        with pytest.raises(ValidationError):
            typical_usage.cache_creation_input_tokens = 999

    def test_cannot_modify_cache_read_input_tokens(self, typical_usage):
        """Should not be able to modify cache_read_input_tokens after creation."""
        with pytest.raises(ValidationError):
            typical_usage.cache_read_input_tokens = 999

    def test_cannot_modify_service_tier(self, typical_usage):
        """Should not be able to modify service_tier after creation."""
        with pytest.raises(ValidationError):
            typical_usage.service_tier = "premium"

    def test_hashable_due_to_frozen(self, typical_usage):
        """Frozen model should be hashable."""
        # Should not raise an error
        hash_value = hash(typical_usage)
        assert isinstance(hash_value, int)

    def test_can_use_in_set(self, typical_usage, zero_usage):
        """Frozen models should be usable in sets."""
        usage_set = {typical_usage, zero_usage, typical_usage}
        assert len(usage_set) == 2  # typical_usage appears twice


# =============================================================================
# Field Validation Tests
# =============================================================================


class TestTokenUsageFieldValidation:
    """Tests for field validation (non-negative values)."""

    def test_negative_input_tokens_rejected(self):
        """Negative input_tokens should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TokenUsage(input_tokens=-1)

        assert "input_tokens" in str(exc_info.value)

    def test_negative_output_tokens_rejected(self):
        """Negative output_tokens should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TokenUsage(output_tokens=-1)

        assert "output_tokens" in str(exc_info.value)

    def test_negative_cache_creation_tokens_rejected(self):
        """Negative cache_creation_input_tokens should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TokenUsage(cache_creation_input_tokens=-1)

        assert "cache_creation_input_tokens" in str(exc_info.value)

    def test_negative_cache_read_tokens_rejected(self):
        """Negative cache_read_input_tokens should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TokenUsage(cache_read_input_tokens=-1)

        assert "cache_read_input_tokens" in str(exc_info.value)

    def test_zero_values_accepted(self):
        """Zero values should be accepted for all token fields."""
        usage = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_large_values_accepted(self):
        """Large token values should be accepted."""
        large_value = 10_000_000  # 10 million tokens
        usage = TokenUsage(
            input_tokens=large_value,
            output_tokens=large_value,
            cache_creation_input_tokens=large_value,
            cache_read_input_tokens=large_value,
        )
        assert usage.input_tokens == large_value
        assert usage.total_tokens == large_value * 4

    def test_invalid_type_rejected(self):
        """Non-integer values for token fields should raise ValidationError."""
        with pytest.raises(ValidationError):
            TokenUsage(input_tokens="not an int")

        with pytest.raises(ValidationError):
            TokenUsage(output_tokens=[100])

    def test_float_with_fractional_part_rejected(self):
        """Float values with fractional parts should raise ValidationError."""
        # Pydantic v2 is strict: floats with fractional parts are rejected
        with pytest.raises(ValidationError):
            TokenUsage(input_tokens=100.7)

    def test_float_without_fractional_part_accepted(self):
        """Float values without fractional parts should be coerced to int."""
        # Pydantic v2 accepts floats that are whole numbers (e.g., 100.0)
        usage = TokenUsage(input_tokens=100.0)
        assert usage.input_tokens == 100
        assert isinstance(usage.input_tokens, int)


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestTokenUsageEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_tokens_all_fields(self, zero_usage):
        """Zero tokens should result in zero for all computed properties."""
        assert zero_usage.total_input == 0
        assert zero_usage.total_tokens == 0
        assert zero_usage.cache_hit_rate == 0.0

    def test_all_cache_hits_no_direct_input(self, all_cache_hits_usage):
        """When all input is from cache, cache_hit_rate should be 1.0."""
        assert all_cache_hits_usage.cache_hit_rate == 1.0
        assert all_cache_hits_usage.total_input == 0
        assert all_cache_hits_usage.total_tokens == 5100  # 5000 cache_read + 100 output

    def test_no_cache_usage(self, no_cache_usage):
        """When no cache is used, cache_hit_rate should be 0.0."""
        assert no_cache_usage.cache_hit_rate == 0.0
        assert no_cache_usage.total_input == 1000
        assert no_cache_usage.total_tokens == 3000

    def test_only_output_tokens(self):
        """Usage with only output tokens should work correctly."""
        usage = TokenUsage(output_tokens=1000)

        assert usage.total_input == 0
        assert usage.total_tokens == 1000
        assert usage.cache_hit_rate == 0.0

    def test_only_cache_creation(self):
        """Usage with only cache creation should work correctly."""
        usage = TokenUsage(cache_creation_input_tokens=50000)

        assert usage.total_input == 50000
        assert usage.total_tokens == 50000
        assert usage.cache_hit_rate == 0.0

    def test_only_cache_read(self):
        """Usage with only cache read should work correctly."""
        usage = TokenUsage(cache_read_input_tokens=10000)

        assert usage.total_input == 0
        assert usage.total_tokens == 10000
        assert usage.cache_hit_rate == 1.0

    def test_very_small_cache_hit_rate(self):
        """Very small cache hit rates should be calculated accurately."""
        usage = TokenUsage(
            input_tokens=1_000_000,
            cache_read_input_tokens=1,
        )
        expected = 1 / (1_000_000 + 1)
        assert usage.cache_hit_rate == pytest.approx(expected)

    def test_equality_comparison(self, typical_usage):
        """Two TokenUsage instances with same values should be equal."""
        other = TokenUsage(
            input_tokens=100,
            output_tokens=500,
            cache_creation_input_tokens=50000,
            cache_read_input_tokens=10000,
            service_tier="standard",
        )
        assert typical_usage == other

    def test_inequality_on_different_values(self, typical_usage, zero_usage):
        """TokenUsage instances with different values should not be equal."""
        assert typical_usage != zero_usage

    def test_model_dump(self, typical_usage):
        """model_dump should return dictionary representation."""
        data = typical_usage.model_dump()

        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 500
        assert data["cache_creation_input_tokens"] == 50000
        assert data["cache_read_input_tokens"] == 10000
        assert data["service_tier"] == "standard"

    def test_model_dump_excludes_none_service_tier(self, zero_usage):
        """model_dump with exclude_none should omit None service_tier."""
        data = zero_usage.model_dump(exclude_none=True)
        assert "service_tier" not in data

    def test_repr_string(self, typical_usage):
        """TokenUsage should have a readable repr."""
        repr_str = repr(typical_usage)

        assert "TokenUsage" in repr_str
        assert "input_tokens=100" in repr_str
        assert "output_tokens=500" in repr_str


# =============================================================================
# Cost Calculation Tests
# =============================================================================


class TestTokenUsageCalculateCost:
    """Tests for calculate_cost() method."""

    def test_default_model_all_components(self, typical_usage):
        """Cost should include uncached input, cache write, cache read, and output."""
        # Default model: claude-opus-4-6 ($5/$25)
        # uncached: 100/1M * $5 = $0.0005
        # cache_write: 50000/1M * $5 * 1.25 = $0.3125
        # cache_read: 10000/1M * $5 * 0.10 = $0.005
        # output: 500/1M * $25 = $0.0125
        expected = 0.0005 + 0.3125 + 0.005 + 0.0125
        assert typical_usage.calculate_cost() == pytest.approx(expected)

    def test_specific_model_haiku(self):
        """Haiku pricing should use its own rates."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        # Haiku 4.5: $1/$5
        cost = usage.calculate_cost("claude-haiku-4-5-20251001")
        assert cost == pytest.approx(1.0 + 5.0)

    def test_specific_model_opus_4_6(self):
        """Opus 4.6 pricing should use $5/$25."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("claude-opus-4-6")
        assert cost == pytest.approx(5.0 + 25.0)

    def test_no_cache_usage(self, no_cache_usage):
        """Cost with no cache should only have uncached input + output."""
        # Default model ($5/$25): input=1000, output=2000
        expected = (1000 / 1_000_000) * 5.0 + (2000 / 1_000_000) * 25.0
        assert no_cache_usage.calculate_cost() == pytest.approx(expected)

    def test_all_cache_hits(self, all_cache_hits_usage):
        """Cost with only cache reads should charge at 10% rate."""
        # input=0, output=100, cache_read=5000
        cache_read_cost = (5000 / 1_000_000) * 5.0 * 0.10
        output_cost = (100 / 1_000_000) * 25.0
        assert all_cache_hits_usage.calculate_cost() == pytest.approx(cache_read_cost + output_cost)

    def test_unknown_model_falls_back_to_default(self):
        """Completely unknown model should fall back to default pricing."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("unknown-model-xyz")
        # Falls back to claude-opus-4-6: $5/$25
        assert cost == pytest.approx(5.0 + 25.0)

    def test_zero_usage_returns_zero(self, zero_usage):
        """Zero token usage should return $0.00."""
        assert zero_usage.calculate_cost() == 0.0

    # --- Fuzzy model matching ---

    def test_fuzzy_match_haiku_alias(self):
        """Model alias containing 'haiku' should resolve to Haiku pricing."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("claude-haiku-4-5-latest")
        # Haiku 4.5: $1/$5
        assert cost == pytest.approx(1.0 + 5.0)

    def test_fuzzy_match_sonnet_alias(self):
        """Model alias containing 'sonnet-4-5' should resolve to Sonnet 4.5 pricing."""
        usage = TokenUsage(input_tokens=100_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("claude-sonnet-4-5-latest")
        # Sonnet 4.5 standard (under 200K threshold): $3/$15
        expected = (100_000 / 1_000_000) * 3.0 + (1_000_000 / 1_000_000) * 15.0
        assert cost == pytest.approx(expected)

    def test_fuzzy_match_opus_alias(self):
        """Model alias containing 'opus-4-6' should resolve to Opus 4.6 pricing."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("claude-opus-4-6-20260205")
        assert cost == pytest.approx(5.0 + 25.0)

    # --- Long-context pricing ---

    def test_long_context_sonnet_above_threshold(self):
        """Sonnet 4.5 with >200K input tokens should use long-context rates."""
        usage = TokenUsage(input_tokens=250_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("claude-sonnet-4-5-20250929")
        # Long-context: $6/$22.5
        expected = (250_000 / 1_000_000) * 6.0 + (1_000_000 / 1_000_000) * 22.5
        assert cost == pytest.approx(expected)

    def test_long_context_sonnet_below_threshold(self):
        """Sonnet 4.5 with <200K input tokens should use standard rates."""
        usage = TokenUsage(input_tokens=100_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("claude-sonnet-4-5-20250929")
        # Standard: $3/$15
        expected = (100_000 / 1_000_000) * 3.0 + (1_000_000 / 1_000_000) * 15.0
        assert cost == pytest.approx(expected)

    def test_long_context_includes_cache_in_threshold(self):
        """Long-context threshold should count all input types (uncached + cache write + cache read)."""
        # 50K uncached + 100K cache write + 60K cache read = 210K > 200K threshold
        usage = TokenUsage(
            input_tokens=50_000,
            output_tokens=100_000,
            cache_creation_input_tokens=100_000,
            cache_read_input_tokens=60_000,
        )
        cost = usage.calculate_cost("claude-sonnet-4-5-20250929")
        # Should use long-context rates ($6/$22.5)
        input_price = 6.0
        uncached = (50_000 / 1_000_000) * input_price
        cache_write = (100_000 / 1_000_000) * input_price * 1.25
        cache_read = (60_000 / 1_000_000) * input_price * 0.10
        output = (100_000 / 1_000_000) * 22.5
        assert cost == pytest.approx(uncached + cache_write + cache_read + output)

    def test_long_context_not_applied_to_opus(self):
        """Opus models should not have long-context pricing."""
        usage = TokenUsage(input_tokens=500_000, output_tokens=1_000_000)
        cost = usage.calculate_cost("claude-opus-4-6")
        # Standard: $5/$25 regardless of input size
        expected = (500_000 / 1_000_000) * 5.0 + (1_000_000 / 1_000_000) * 25.0
        assert cost == pytest.approx(expected)
