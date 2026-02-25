"""
API integration tests for the plans router.

Tests plan listing, detail, and stats endpoints.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent.parent

# Add paths for imports
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from main import app

client = TestClient(app)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_plans_dir(tmp_path: Path):
    """Create a mock plans directory with test plans and patch get_plans_dir."""
    plans_dir = tmp_path / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    # Patch in models.plan where load_all_plans calls it, AND in routers.plans
    with (
        patch("models.plan.get_plans_dir", return_value=plans_dir),
        patch("routers.plans.get_plans_dir", return_value=plans_dir),
    ):
        yield plans_dir


@pytest.fixture
def sample_plan(mock_plans_dir: Path) -> Path:
    """Create a sample plan file."""
    plan_content = """# Test Feature Implementation

## Overview

Implement the test feature with full coverage.

## Steps

1. Create models
2. Add API endpoints
3. Write tests
4. Update documentation

## Technical Details

- Use FastAPI for endpoints
- Pydantic for validation
"""
    plan_path = mock_plans_dir / "test-feature-plan.md"
    plan_path.write_text(plan_content)
    return plan_path


@pytest.fixture
def multiple_plans(mock_plans_dir: Path) -> list[Path]:
    """Create multiple plan files for testing list endpoint."""
    plans = []
    for i in range(3):
        plan_path = mock_plans_dir / f"plan-{i}.md"
        plan_path.write_text(f"# Plan {i}\n\nContent for plan {i}")
        plans.append(plan_path)
    return plans


# =============================================================================
# List Plans Tests
# =============================================================================


class TestListPlans:
    """Tests for GET /plans endpoint."""

    def test_list_plans_empty(self, mock_plans_dir: Path):
        """Test listing plans when none exist."""
        response = client.get("/plans")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_plans_with_plans(self, sample_plan: Path, mock_plans_dir: Path):
        """Test listing plans returns plan summaries."""
        response = client.get("/plans")
        assert response.status_code == 200

        plans = response.json()
        assert len(plans) == 1
        assert plans[0]["slug"] == "test-feature-plan"
        assert plans[0]["title"] == "Test Feature Implementation"
        assert "preview" in plans[0]
        assert "word_count" in plans[0]

    def test_list_plans_multiple(self, multiple_plans: list[Path], mock_plans_dir: Path):
        """Test listing multiple plans."""
        response = client.get("/plans")
        assert response.status_code == 200

        plans = response.json()
        assert len(plans) == 3


# =============================================================================
# Get Plan Tests
# =============================================================================


class TestGetPlan:
    """Tests for GET /plans/{slug} endpoint."""

    def test_get_plan_success(self, sample_plan: Path, mock_plans_dir: Path):
        """Test getting a specific plan by slug."""
        response = client.get("/plans/test-feature-plan")
        assert response.status_code == 200

        plan = response.json()
        assert plan["slug"] == "test-feature-plan"
        assert plan["title"] == "Test Feature Implementation"
        assert "content" in plan
        assert "## Steps" in plan["content"]

    def test_get_plan_not_found(self, mock_plans_dir: Path):
        """Test 404 when plan doesn't exist."""
        response = client.get("/plans/nonexistent-plan")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# =============================================================================
# Plan Stats Tests
# =============================================================================


class TestPlanStats:
    """Tests for GET /plans/stats endpoint."""

    def test_stats_empty(self, mock_plans_dir: Path):
        """Test stats when no plans exist."""
        response = client.get("/plans/stats")
        assert response.status_code == 200

        stats = response.json()
        assert stats["total_plans"] == 0
        assert stats["total_words"] == 0
        assert stats["oldest_plan"] is None
        assert stats["newest_plan"] is None

    def test_stats_with_plans(self, multiple_plans: list[Path], mock_plans_dir: Path):
        """Test stats with multiple plans."""
        response = client.get("/plans/stats")
        assert response.status_code == 200

        stats = response.json()
        assert stats["total_plans"] == 3
        assert stats["total_words"] > 0
        assert stats["newest_plan"] is not None
        assert stats["oldest_plan"] is not None


# =============================================================================
# Plan Context Tests
# =============================================================================


class TestPlanContext:
    """Tests for GET /plans/{slug}/context endpoint."""

    def test_context_no_matching_session(self, sample_plan: Path, mock_plans_dir: Path):
        """Test context returns null when no session matches the plan slug."""
        with patch("routers.plans.find_session_context_for_slug", return_value=None):
            response = client.get("/plans/test-feature-plan/context")
            assert response.status_code == 200
            assert response.json() is None

    def test_context_endpoint_exists(self, mock_plans_dir: Path):
        """Test context endpoint returns 200 even for unknown slugs (returns null)."""
        with patch("routers.plans.find_session_context_for_slug", return_value=None):
            response = client.get("/plans/any-slug-here/context")
            assert response.status_code == 200
            assert response.json() is None
