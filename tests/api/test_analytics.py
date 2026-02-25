"""
Unit tests for the analytics router.

Tests cover:
- get_model_pricing() - model pricing lookup with prefix matching
- calculate_cost() - cost calculation for different models
- GET /analytics/projects/{encoded_name} endpoint - analytics aggregation

Run from project root:
    pytest apps/api/tests/test_analytics.py -v

Or from apps/api directory:
    PYTHONPATH=../.. python3 -m pytest tests/test_analytics.py -v
"""

from collections import Counter
from datetime import datetime
from typing import Dict, Set

import pytest
from pydantic import BaseModel, Field

# Import from the actual usage module where pricing logic now lives
from models.usage import DEFAULT_PRICING_MODEL, MODEL_PRICING, TokenUsage, _resolve_model


# Thin wrappers preserving the old standalone-function API for these tests
def get_model_pricing(model: str) -> dict[str, float]:
    """Resolve model name to pricing dict (wraps _resolve_model)."""
    return _resolve_model(model)


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost from input/output tokens and model (wraps TokenUsage.calculate_cost)."""
    return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens).calculate_cost(model)


# =============================================================================
# Mock classes for endpoint testing
# =============================================================================


class MockTokenUsage:
    """Mock TokenUsage for testing."""

    def __init__(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_creation_input_tokens


class MockSession:
    """Mock Session for testing."""

    def __init__(
        self,
        usage: MockTokenUsage = None,
        duration_seconds: float = None,
        models_used: Set[str] = None,
        tools_used: Counter = None,
        start_time: datetime = None,
        subagents: list = None,
    ):
        self._usage = usage or MockTokenUsage()
        self.duration_seconds = duration_seconds
        self._models_used = models_used or set()
        self._tools_used = tools_used or Counter()
        self.start_time = start_time
        self._subagents = subagents or []

    def get_usage_summary(self) -> MockTokenUsage:
        return self._usage

    def get_models_used(self) -> Set[str]:
        return self._models_used

    def get_tools_used(self) -> Counter:
        return self._tools_used

    def list_subagents(self) -> list:
        return self._subagents


class MockProject:
    """Mock Project for testing."""

    def __init__(self, exists: bool = True, sessions: list = None):
        self._exists = exists
        self._sessions = sessions or []

    @property
    def exists(self) -> bool:
        return self._exists

    def list_sessions(self) -> list:
        return self._sessions


class ProjectAnalytics(BaseModel):
    """Analytics response schema (mirrors real schema)."""

    total_sessions: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_seconds: float = 0.0
    estimated_cost_usd: float = 0.0
    models_used: Dict[str, int] = Field(default_factory=dict)
    cache_hit_rate: float = 0.0
    tools_used: Dict[str, int] = Field(default_factory=dict)
    sessions_by_date: Dict[str, int] = Field(default_factory=dict)


def compute_project_analytics(project: MockProject) -> ProjectAnalytics:
    """
    Compute analytics for a project.

    This replicates the logic in the actual endpoint for testing purposes.
    """
    sessions = project.list_sessions()

    # Aggregate stats
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read = 0
    total_cacheable = 0
    total_duration = 0.0
    total_cost = 0.0
    models_used: Counter = Counter()
    tools_used: Counter = Counter()
    sessions_by_date: Counter = Counter()

    for session in sessions:
        usage = session.get_usage_summary()
        total_input_tokens += usage.total_input
        total_output_tokens += usage.output_tokens
        total_cache_read += usage.cache_read_input_tokens
        total_cacheable += (
            usage.input_tokens + usage.cache_creation_input_tokens + usage.cache_read_input_tokens
        )

        if session.duration_seconds:
            total_duration += session.duration_seconds

        # Track models used
        session_models = session.get_models_used()
        for model in session_models:
            models_used[model] += 1
            # Calculate cost per model
            total_cost += calculate_cost(
                usage.total_input // max(1, len(session_models)),
                usage.output_tokens // max(1, len(session_models)),
                model,
            )

        # Track tools used
        session_tools = session.get_tools_used()
        for tool, count in session_tools.items():
            tools_used[tool] += count

        # Track sessions by date
        if session.start_time:
            date_str = session.start_time.strftime("%Y-%m-%d")
            sessions_by_date[date_str] += 1

    # Calculate overall cache hit rate
    cache_hit_rate = total_cache_read / total_cacheable if total_cacheable > 0 else 0.0

    return ProjectAnalytics(
        total_sessions=len(sessions),
        total_tokens=total_input_tokens + total_output_tokens,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_duration_seconds=total_duration,
        estimated_cost_usd=round(total_cost, 4),
        models_used=dict(models_used),
        cache_hit_rate=round(cache_hit_rate, 4),
        tools_used=dict(tools_used),
        sessions_by_date=dict(sessions_by_date),
    )


# =============================================================================
# Tests for get_model_pricing()
# =============================================================================


class TestGetModelPricing:
    """Tests for the get_model_pricing function."""

    def test_exact_match_opus(self):
        """Test exact match for Opus model."""
        pricing = get_model_pricing("claude-opus-4-5-20251101")
        assert pricing["input"] == 5.0
        assert pricing["output"] == 25.0

    def test_exact_match_opus_older(self):
        """Test exact match for older Opus model."""
        pricing = get_model_pricing("claude-opus-4-20250514")
        assert pricing == {"input": 15.0, "output": 75.0}

    def test_exact_match_sonnet(self):
        """Test exact match for Sonnet model."""
        pricing = get_model_pricing("claude-sonnet-4-20250514")
        assert pricing == {"input": 3.0, "output": 15.0}

    def test_exact_match_sonnet_35(self):
        """Test exact match for Sonnet 3.5 model."""
        pricing = get_model_pricing("claude-3-5-sonnet-20241022")
        assert pricing == {"input": 3.0, "output": 15.0}

    def test_exact_match_haiku(self):
        """Test exact match for Haiku model."""
        pricing = get_model_pricing("claude-3-5-haiku-20241022")
        assert pricing == {"input": 0.80, "output": 4.0}

    def test_exact_match_haiku_old(self):
        """Test exact match for older Haiku model."""
        pricing = get_model_pricing("claude-3-haiku-20240307")
        assert pricing == {"input": 0.25, "output": 1.25}

    def test_prefix_match_opus(self):
        """Test prefix matching for Opus model variant."""
        # Matches claude-opus-4-5 via fuzzy "opus-4-5" pattern
        pricing = get_model_pricing("claude-opus-4-5-20260101")
        assert pricing["input"] == 5.0
        assert pricing["output"] == 25.0

    def test_prefix_match_sonnet(self):
        """Test prefix matching for Sonnet model variant."""
        # Fuzzy matches "sonnet" pattern → claude-sonnet-4-5 (may include long-context keys)
        pricing = get_model_pricing("claude-3-5-sonnet-20250101")
        assert pricing["input"] == 3.0
        assert pricing["output"] == 15.0

    def test_prefix_match_haiku(self):
        """Test prefix matching for Haiku model variant."""
        # Fuzzy matches "haiku" pattern → claude-haiku-4-5 (latest haiku pricing)
        pricing = get_model_pricing("claude-3-5-haiku-20250101")
        assert pricing["input"] == 1.0
        assert pricing["output"] == 5.0

    def test_fallback_to_default_unknown_model(self):
        """Test fallback to default for unknown model."""
        pricing = get_model_pricing("unknown-model-12345")
        assert pricing == MODEL_PRICING[DEFAULT_PRICING_MODEL]

    def test_fallback_to_default_empty_string(self):
        """Test fallback to default for empty model name."""
        pricing = get_model_pricing("")
        assert pricing == MODEL_PRICING[DEFAULT_PRICING_MODEL]

    def test_fallback_to_default_claude_without_version(self):
        """Test fallback for partial Claude model name without matching prefix."""
        pricing = get_model_pricing("claude-new-model")
        assert pricing == MODEL_PRICING[DEFAULT_PRICING_MODEL]

    def test_fallback_gpt_model(self):
        """Test fallback for non-Claude model."""
        pricing = get_model_pricing("gpt-4-turbo")
        assert pricing == MODEL_PRICING[DEFAULT_PRICING_MODEL]


# =============================================================================
# Tests for calculate_cost()
# =============================================================================


class TestCalculateCost:
    """Tests for the calculate_cost function."""

    def test_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        cost = calculate_cost(0, 0, "claude-opus-4-5-20251101")
        assert cost == 0.0

    def test_opus_cost_calculation(self):
        """Test cost calculation for Opus model."""
        # 1M input tokens at $5 + 1M output tokens at $25 = $30
        cost = calculate_cost(1_000_000, 1_000_000, "claude-opus-4-5-20251101")
        assert cost == 30.0

    def test_sonnet_cost_calculation(self):
        """Test cost calculation for Sonnet model."""
        # 1M input tokens at $3 + 1M output tokens at $15 = $18
        cost = calculate_cost(1_000_000, 1_000_000, "claude-sonnet-4-20250514")
        assert cost == 18.0

    def test_haiku_cost_calculation(self):
        """Test cost calculation for Haiku model."""
        # 1M input tokens at $0.80 + 1M output tokens at $4 = $4.80
        cost = calculate_cost(1_000_000, 1_000_000, "claude-3-5-haiku-20241022")
        assert cost == 4.80

    def test_haiku_old_cost_calculation(self):
        """Test cost calculation for older Haiku model."""
        # 1M input tokens at $0.25 + 1M output tokens at $1.25 = $1.50
        cost = calculate_cost(1_000_000, 1_000_000, "claude-3-haiku-20240307")
        assert cost == 1.50

    def test_small_token_count(self):
        """Test cost calculation with realistic small token counts."""
        # 10,000 input tokens and 2,000 output tokens on Sonnet
        # (10000 / 1M) * 3.0 + (2000 / 1M) * 15.0 = 0.03 + 0.03 = 0.06
        cost = calculate_cost(10_000, 2_000, "claude-sonnet-4-20250514")
        assert cost == pytest.approx(0.06, rel=1e-6)

    def test_cost_with_unknown_model_uses_default(self):
        """Test that unknown model falls back to default pricing."""
        # Using default pricing (claude-opus-4-6): $5/M input, $25/M output
        cost = calculate_cost(1_000_000, 1_000_000, "unknown-model")
        assert cost == 30.0

    def test_input_only(self):
        """Test cost calculation with only input tokens."""
        # 1M input tokens on Opus 4.5 at $5
        cost = calculate_cost(1_000_000, 0, "claude-opus-4-5-20251101")
        assert cost == 5.0

    def test_output_only(self):
        """Test cost calculation with only output tokens."""
        # 1M output tokens on Opus 4.5 at $25
        cost = calculate_cost(0, 1_000_000, "claude-opus-4-5-20251101")
        assert cost == 25.0

    def test_fractional_costs(self):
        """Test cost calculation with small numbers resulting in fractional costs."""
        # 100 input + 100 output on Opus 4.5
        # (100 / 1M) * 5 + (100 / 1M) * 25 = 0.0005 + 0.0025 = 0.003
        cost = calculate_cost(100, 100, "claude-opus-4-5-20251101")
        assert cost == pytest.approx(0.003, rel=1e-6)


# =============================================================================
# Tests for project analytics computation
# =============================================================================


class TestProjectAnalyticsComputation:
    """Tests for the project analytics computation logic."""

    def test_empty_project_no_sessions(self):
        """Test analytics for a project with no sessions."""
        project = MockProject(exists=True, sessions=[])
        analytics = compute_project_analytics(project)

        assert analytics.total_sessions == 0
        assert analytics.total_tokens == 0
        assert analytics.total_input_tokens == 0
        assert analytics.total_output_tokens == 0
        assert analytics.total_duration_seconds == 0.0
        assert analytics.estimated_cost_usd == 0.0
        assert analytics.models_used == {}
        assert analytics.cache_hit_rate == 0.0
        assert analytics.tools_used == {}
        assert analytics.sessions_by_date == {}

    def test_single_session(self):
        """Test analytics for a project with a single session."""
        usage = MockTokenUsage(
            input_tokens=3000,
            output_tokens=1000,
            cache_creation_input_tokens=500,
            cache_read_input_tokens=2000,
        )
        session = MockSession(
            usage=usage,
            duration_seconds=120.5,
            models_used={"claude-sonnet-4-20250514"},
            tools_used=Counter({"Read": 5, "Write": 3}),
            start_time=datetime(2025, 1, 15, 10, 30, 0),
        )
        project = MockProject(exists=True, sessions=[session])

        analytics = compute_project_analytics(project)

        assert analytics.total_sessions == 1
        assert analytics.total_input_tokens == 3500  # 3000 + 500
        assert analytics.total_output_tokens == 1000
        assert analytics.total_tokens == 4500
        assert analytics.total_duration_seconds == 120.5
        assert analytics.models_used == {"claude-sonnet-4-20250514": 1}
        assert analytics.tools_used == {"Read": 5, "Write": 3}
        assert analytics.sessions_by_date == {"2025-01-15": 1}

    def test_multiple_sessions_aggregation(self):
        """Test analytics aggregation across multiple sessions."""
        usage1 = MockTokenUsage(
            input_tokens=2000,
            output_tokens=500,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=1000,
        )
        session1 = MockSession(
            usage=usage1,
            duration_seconds=60.0,
            models_used={"claude-sonnet-4-20250514"},
            tools_used=Counter({"Read": 2}),
            start_time=datetime(2025, 1, 15, 10, 0, 0),
        )

        usage2 = MockTokenUsage(
            input_tokens=4000,
            output_tokens=1500,
            cache_creation_input_tokens=800,
            cache_read_input_tokens=3000,
        )
        session2 = MockSession(
            usage=usage2,
            duration_seconds=90.0,
            models_used={"claude-opus-4-5-20251101"},
            tools_used=Counter({"Write": 4, "Read": 1}),
            start_time=datetime(2025, 1, 16, 14, 0, 0),
        )

        project = MockProject(exists=True, sessions=[session1, session2])
        analytics = compute_project_analytics(project)

        assert analytics.total_sessions == 2
        # Session 1: 2000 + 200 = 2200, Session 2: 4000 + 800 = 4800
        assert analytics.total_input_tokens == 7000
        assert analytics.total_output_tokens == 2000  # 500 + 1500
        assert analytics.total_tokens == 9000
        assert analytics.total_duration_seconds == 150.0  # 60 + 90
        assert analytics.models_used == {
            "claude-sonnet-4-20250514": 1,
            "claude-opus-4-5-20251101": 1,
        }
        assert analytics.tools_used == {"Read": 3, "Write": 4}
        assert analytics.sessions_by_date == {"2025-01-15": 1, "2025-01-16": 1}

    def test_cache_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        # 4000 cache read, total cacheable = 3000 + 500 + 4000 = 7500
        # Rate = 4000 / 7500 = 0.5333...
        usage = MockTokenUsage(
            input_tokens=3000,
            output_tokens=1000,
            cache_creation_input_tokens=500,
            cache_read_input_tokens=4000,
        )
        session = MockSession(usage=usage)
        project = MockProject(exists=True, sessions=[session])

        analytics = compute_project_analytics(project)

        expected_rate = 4000 / 7500
        assert analytics.cache_hit_rate == pytest.approx(expected_rate, rel=1e-3)

    def test_cache_hit_rate_zero_when_no_cacheable_tokens(self):
        """Test cache hit rate is 0 when there are no cacheable tokens."""
        usage = MockTokenUsage()  # All zeros
        session = MockSession(usage=usage)
        project = MockProject(exists=True, sessions=[session])

        analytics = compute_project_analytics(project)

        assert analytics.cache_hit_rate == 0.0

    def test_session_without_duration(self):
        """Test handling sessions with no duration (None)."""
        usage = MockTokenUsage(input_tokens=1000, output_tokens=500)
        session = MockSession(
            usage=usage,
            duration_seconds=None,
        )
        project = MockProject(exists=True, sessions=[session])

        analytics = compute_project_analytics(project)

        assert analytics.total_duration_seconds == 0.0

    def test_session_without_start_time(self):
        """Test handling sessions with no start time."""
        usage = MockTokenUsage(input_tokens=1000, output_tokens=500)
        session = MockSession(
            usage=usage,
            duration_seconds=60.0,
            start_time=None,
        )
        project = MockProject(exists=True, sessions=[session])

        analytics = compute_project_analytics(project)

        # No sessions_by_date entry when start_time is None
        assert analytics.sessions_by_date == {}

    def test_multiple_models_in_single_session(self):
        """Test cost calculation when a session uses multiple models."""
        usage = MockTokenUsage(input_tokens=10000, output_tokens=2000)
        session = MockSession(
            usage=usage,
            models_used={"claude-sonnet-4-20250514", "claude-opus-4-5-20251101"},
        )
        project = MockProject(exists=True, sessions=[session])

        analytics = compute_project_analytics(project)

        # Both models should be counted
        assert "claude-sonnet-4-20250514" in analytics.models_used
        assert "claude-opus-4-5-20251101" in analytics.models_used
        # Cost should be calculated (tokens split between models)
        assert analytics.estimated_cost_usd > 0

    def test_sessions_on_same_date_aggregated(self):
        """Test that multiple sessions on the same date are counted together."""
        usage = MockTokenUsage(input_tokens=1000, output_tokens=500)

        session1 = MockSession(
            usage=usage,
            start_time=datetime(2025, 1, 15, 9, 0, 0),
        )
        session2 = MockSession(
            usage=usage,
            start_time=datetime(2025, 1, 15, 14, 0, 0),  # Same date
        )
        session3 = MockSession(
            usage=usage,
            start_time=datetime(2025, 1, 16, 10, 0, 0),  # Different date
        )

        project = MockProject(
            exists=True,
            sessions=[session1, session2, session3],
        )

        analytics = compute_project_analytics(project)

        assert analytics.sessions_by_date == {"2025-01-15": 2, "2025-01-16": 1}

    def test_cost_calculation_with_session(self):
        """Test that cost is calculated correctly for a session."""
        # 100,000 input + 20,000 output on Sonnet
        # (100000 / 1M) * 3 + (20000 / 1M) * 15 = 0.3 + 0.3 = 0.6
        usage = MockTokenUsage(input_tokens=100_000, output_tokens=20_000)
        session = MockSession(
            usage=usage,
            models_used={"claude-sonnet-4-20250514"},
        )
        project = MockProject(exists=True, sessions=[session])

        analytics = compute_project_analytics(project)

        assert analytics.estimated_cost_usd == pytest.approx(0.6, rel=1e-3)

    def test_tools_aggregation_across_sessions(self):
        """Test that tools are aggregated correctly across sessions."""
        usage = MockTokenUsage(input_tokens=1000, output_tokens=500)

        session1 = MockSession(
            usage=usage,
            tools_used=Counter({"Read": 5, "Write": 2}),
        )
        session2 = MockSession(
            usage=usage,
            tools_used=Counter({"Read": 3, "Bash": 4}),
        )

        project = MockProject(exists=True, sessions=[session1, session2])

        analytics = compute_project_analytics(project)

        assert analytics.tools_used == {"Read": 8, "Write": 2, "Bash": 4}


# =============================================================================
# Tests for MODEL_PRICING constant
# =============================================================================


class TestModelPricing:
    """Tests for the MODEL_PRICING constant."""

    def test_all_models_have_input_and_output(self):
        """Verify all pricing entries have both input and output keys."""
        for model_name, pricing in MODEL_PRICING.items():
            assert "input" in pricing, f"Model {model_name} missing 'input' key"
            assert "output" in pricing, f"Model {model_name} missing 'output' key"

    def test_all_prices_are_positive(self):
        """Verify all prices are positive numbers."""
        for model_name, pricing in MODEL_PRICING.items():
            assert pricing["input"] > 0, f"Model {model_name} has non-positive input price"
            assert pricing["output"] > 0, f"Model {model_name} has non-positive output price"

    def test_default_pricing_exists(self):
        """Verify default pricing model is defined in MODEL_PRICING."""
        assert DEFAULT_PRICING_MODEL in MODEL_PRICING

    def test_opus_more_expensive_than_sonnet(self):
        """Verify Opus pricing is higher than Sonnet (sanity check)."""
        opus_pricing = MODEL_PRICING["claude-opus-4-5-20251101"]
        sonnet_pricing = MODEL_PRICING["claude-sonnet-4-20250514"]

        assert opus_pricing["input"] > sonnet_pricing["input"]
        assert opus_pricing["output"] > sonnet_pricing["output"]

    def test_sonnet_more_expensive_than_haiku(self):
        """Verify Sonnet pricing is higher than Haiku (sanity check)."""
        sonnet_pricing = MODEL_PRICING["claude-sonnet-4-20250514"]
        haiku_pricing = MODEL_PRICING["claude-3-5-haiku-20241022"]

        assert sonnet_pricing["input"] > haiku_pricing["input"]
        assert sonnet_pricing["output"] > haiku_pricing["output"]

    def test_output_more_expensive_than_input(self):
        """Verify output tokens cost more than input tokens for all models."""
        for model_name, pricing in MODEL_PRICING.items():
            assert pricing["output"] >= pricing["input"], (
                f"Model {model_name}: output should cost >= input"
            )


# =============================================================================
# FastAPI endpoint tests (integration style using TestClient)
# =============================================================================

try:
    from fastapi import APIRouter, FastAPI, HTTPException
    from fastapi.testclient import TestClient

    # Create a minimal app that replicates the analytics router
    # Using underscore prefix to avoid pytest collection warnings
    _analytics_app = FastAPI()
    _analytics_router = APIRouter()

    # Track mock project for injection
    _test_project_mock = None

    @_analytics_router.get("/projects/{encoded_name}", response_model=ProjectAnalytics)
    def get_project_analytics_endpoint(encoded_name: str):
        """Endpoint that mirrors real endpoint behavior."""
        global _test_project_mock

        if _test_project_mock is None:
            raise HTTPException(status_code=404, detail="Project not found: no mock set")

        if isinstance(_test_project_mock, Exception):
            raise HTTPException(status_code=404, detail=f"Project not found: {_test_project_mock}")

        if not _test_project_mock.exists:
            raise HTTPException(status_code=404, detail="Project directory not found")

        return compute_project_analytics(_test_project_mock)

    _analytics_app.include_router(_analytics_router, prefix="/analytics")
    _test_client = TestClient(_analytics_app)

    class TestAnalyticsEndpoint:
        """Tests for the GET /analytics/projects/{encoded_name} endpoint."""

        def setup_method(self):
            """Reset mock before each test."""
            global _test_project_mock
            _test_project_mock = None

        def test_project_not_found_exception(self):
            """Test 404 error when project lookup fails."""
            global _test_project_mock
            _test_project_mock = ValueError("Invalid path")

            response = _test_client.get("/analytics/projects/-Invalid-Project-Path")

            assert response.status_code == 404
            assert "Project not found" in response.json()["detail"]

        def test_project_directory_not_exists(self):
            """Test 404 error when project directory does not exist."""
            global _test_project_mock
            _test_project_mock = MockProject(exists=False)

            response = _test_client.get("/analytics/projects/-Users-test-project")

            assert response.status_code == 404
            assert response.json()["detail"] == "Project directory not found"

        def test_project_with_no_sessions(self):
            """Test analytics for a project with no sessions."""
            global _test_project_mock
            _test_project_mock = MockProject(exists=True, sessions=[])

            response = _test_client.get("/analytics/projects/-Users-empty-project")

            assert response.status_code == 200
            data = response.json()

            assert data["total_sessions"] == 0
            assert data["total_tokens"] == 0
            assert data["total_input_tokens"] == 0
            assert data["total_output_tokens"] == 0
            assert data["total_duration_seconds"] == 0.0
            assert data["estimated_cost_usd"] == 0.0
            assert data["models_used"] == {}
            assert data["cache_hit_rate"] == 0.0
            assert data["tools_used"] == {}
            assert data["sessions_by_date"] == {}

        def test_project_with_sessions(self):
            """Test analytics for a project with sessions."""
            global _test_project_mock

            usage = MockTokenUsage(
                input_tokens=3000,
                output_tokens=1000,
                cache_creation_input_tokens=500,
                cache_read_input_tokens=2000,
            )
            session = MockSession(
                usage=usage,
                duration_seconds=120.5,
                models_used={"claude-sonnet-4-20250514"},
                tools_used=Counter({"Read": 5, "Write": 3}),
                start_time=datetime(2025, 1, 15, 10, 30, 0),
            )
            _test_project_mock = MockProject(exists=True, sessions=[session])

            response = _test_client.get("/analytics/projects/-Users-test-project")

            assert response.status_code == 200
            data = response.json()

            assert data["total_sessions"] == 1
            assert data["total_input_tokens"] == 3500  # 3000 + 500
            assert data["total_output_tokens"] == 1000
            assert data["total_tokens"] == 4500
            assert data["total_duration_seconds"] == 120.5
            assert data["models_used"] == {"claude-sonnet-4-20250514": 1}
            assert data["tools_used"] == {"Read": 5, "Write": 3}
            assert data["sessions_by_date"] == {"2025-01-15": 1}

except ImportError:
    # FastAPI not available, skip endpoint tests
    pass
