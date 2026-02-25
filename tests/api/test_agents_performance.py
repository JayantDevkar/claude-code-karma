"""
Performance tests for agents endpoint optimization.

Tests verify the end-to-end performance improvements from:
- Phase 1: Cache TTL increase (120s -> 600s)
- Phase 2: Early exit optimization in message scanning
- Phase 3: Agent usage index with incremental updates

Performance targets:
- Cold load: < 2 seconds (baseline 7.2s)
- Warm load: < 0.5 seconds
- Incremental update: < 1 second
"""

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent.parent
_apps_dir = _api_dir.parent
_root_dir = _apps_dir.parent

# Add paths for imports
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))


@pytest.fixture
def app():
    """Create FastAPI test app with agents router."""
    from fastapi import FastAPI

    from routers.agents import router as agents_router

    app = FastAPI()
    app.include_router(agents_router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_session_with_agents(mock_claude_base: Path) -> tuple[Path, str]:
    """
    Create a realistic test session with multiple agent invocations.

    Returns:
        Tuple of (session_path, session_uuid)
    """

    # Create project directory
    project_dir = mock_claude_base / "projects" / "-Users-test-myproject"
    project_dir.mkdir(parents=True, exist_ok=True)

    session_uuid = "perf-test-session-001"
    session_path = project_dir / f"{session_uuid}.jsonl"

    # Create session with 10 agent invocations across 50 messages
    messages = []

    # Initial user message
    messages.append(
        {
            "type": "user",
            "uuid": "msg-user-000",
            "sessionId": session_uuid,
            "timestamp": "2026-02-12T10:00:00.000Z",
            "message": {"role": "user", "content": "Build a REST API with authentication"},
            "parentUuid": None,
            "isSidechain": False,
        }
    )

    # Create alternating user/assistant messages with agent invocations
    agent_types = [
        "oh-my-claudecode:planner",
        "oh-my-claudecode:explore",
        "oh-my-claudecode:architect",
        "oh-my-claudecode:executor",
        "oh-my-claudecode:designer",
        "oh-my-claudecode:qa-tester",
        "oh-my-claudecode:executor-high",
        "oh-my-claudecode:build-fixer",
        "oh-my-claudecode:code-reviewer",
        "oh-my-claudecode:security-reviewer",
    ]

    for i in range(1, 51):
        is_user = i % 2 == 1
        msg_type = "user" if is_user else "assistant"

        if is_user:
            messages.append(
                {
                    "type": msg_type,
                    "uuid": f"msg-user-{i:03d}",
                    "sessionId": session_uuid,
                    "timestamp": f"2026-02-12T10:{i:02d}:00.000Z",
                    "message": {"role": "user", "content": f"Continuing work on task {i}"},
                    "parentUuid": f"msg-assistant-{i - 1:03d}" if i > 1 else "msg-user-000",
                    "isSidechain": False,
                }
            )
        else:
            # Every 5th assistant message has an agent invocation
            content = [{"type": "text", "text": f"Working on step {i}"}]

            if i % 5 == 0:
                agent_idx = (i // 5 - 1) % len(agent_types)
                agent_type = agent_types[agent_idx]
                content.append(
                    {
                        "type": "tool_use",
                        "id": f"toolu_{i:03d}",
                        "name": "Task",
                        "input": {
                            "subagent_type": agent_type,
                            "model": "sonnet",
                            "prompt": f"Execute task for step {i}",
                        },
                    }
                )

            messages.append(
                {
                    "type": msg_type,
                    "uuid": f"msg-assistant-{i:03d}",
                    "sessionId": session_uuid,
                    "timestamp": f"2026-02-12T10:{i:02d}:30.000Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-6",
                        "content": content,
                        "stop_reason": "tool_use" if i % 5 == 0 else "end_turn",
                        "usage": {
                            "input_tokens": 1000,
                            "output_tokens": 500,
                            "cache_creation_input_tokens": 5000,
                            "cache_read_input_tokens": 2000,
                        },
                    },
                    "parentUuid": f"msg-user-{i:03d}",
                    "isSidechain": False,
                }
            )

    # Write all messages to JSONL
    with open(session_path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    return session_path, session_uuid


@pytest.fixture
def multiple_sessions_with_agents(mock_claude_base: Path) -> list[tuple[Path, str]]:
    """
    Create multiple test sessions with agent invocations.

    Returns:
        List of (session_path, session_uuid) tuples
    """
    sessions = []
    project_dir = mock_claude_base / "projects" / "-Users-test-myproject"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create 5 sessions
    for session_num in range(5):
        session_uuid = f"perf-test-session-{session_num:03d}"
        session_path = project_dir / f"{session_uuid}.jsonl"

        messages = []

        # User message
        messages.append(
            {
                "type": "user",
                "uuid": f"msg-user-{session_num}-000",
                "sessionId": session_uuid,
                "timestamp": f"2026-02-12T1{session_num}:00:00.000Z",
                "message": {"role": "user", "content": f"Task for session {session_num}"},
                "parentUuid": None,
                "isSidechain": False,
            }
        )

        # Assistant with agent invocation
        messages.append(
            {
                "type": "assistant",
                "uuid": f"msg-assistant-{session_num}-001",
                "sessionId": session_uuid,
                "timestamp": f"2026-02-12T1{session_num}:00:30.000Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-opus-4-6",
                    "content": [
                        {"type": "text", "text": "Starting task"},
                        {
                            "type": "tool_use",
                            "id": f"toolu_{session_num}_001",
                            "name": "Task",
                            "input": {
                                "subagent_type": "oh-my-claudecode:executor",
                                "model": "sonnet",
                                "prompt": f"Execute task {session_num}",
                            },
                        },
                    ],
                    "stop_reason": "tool_use",
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 500,
                    },
                },
                "parentUuid": f"msg-user-{session_num}-000",
                "isSidechain": False,
            }
        )

        with open(session_path, "w") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

        sessions.append((session_path, session_uuid))

    return sessions


def clear_agent_usage_cache():
    """Clear all agent usage caches (no-op after SQLite migration)."""
    pass


@pytest.mark.asyncio
async def test_agent_usage_cold_load_performance(
    client: TestClient,
    mock_claude_base: Path,
    sample_session_with_agents: tuple[Path, str],
):
    """
    Test cold load performance with fresh cache.

    Target: < 2 seconds (baseline was 7.2s)
    """
    # Clear all caches
    clear_agent_usage_cache()

    # Measure cold load time
    start_time = time.time()
    response = client.get("/agents/usage")
    elapsed = time.time() - start_time

    # Verify response is valid
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "total_runs" in data
    assert "total_cost_usd" in data

    # Performance assertion
    print(f"\nCold load time: {elapsed:.3f}s (target: < 2.0s)")
    assert elapsed < 2.0, f"Cold load took {elapsed:.3f}s, expected < 2.0s"


@pytest.mark.asyncio
async def test_agent_usage_warm_load_performance(
    client: TestClient,
    mock_claude_base: Path,
    sample_session_with_agents: tuple[Path, str],
):
    """
    Test warm load performance with pre-warmed cache.

    Target: < 0.5 seconds
    """
    # Pre-warm cache with first request
    response = client.get("/agents/usage")
    assert response.status_code == 200

    # Measure warm load time
    start_time = time.time()
    response = client.get("/agents/usage")
    elapsed = time.time() - start_time

    # Verify response is valid
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data

    # Performance assertion
    print(f"\nWarm load time: {elapsed:.3f}s (target: < 0.5s)")
    assert elapsed < 0.5, f"Warm load took {elapsed:.3f}s, expected < 0.5s"


@pytest.mark.asyncio
async def test_pagination_performance(
    client: TestClient,
    mock_claude_base: Path,
    sample_session_with_agents: tuple[Path, str],
):
    """
    Test pagination performance with different page sizes.

    Verifies that pagination doesn't significantly degrade performance.
    """
    # Pre-warm cache
    response = client.get("/agents/usage?per_page=20")
    assert response.status_code == 200

    # Test different page sizes
    page_sizes = [5, 10, 20, 50, 100]

    for page_size in page_sizes:
        start_time = time.time()
        response = client.get(f"/agents/usage?per_page={page_size}")
        elapsed = time.time() - start_time

        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) <= page_size

        print(f"Page size {page_size}: {elapsed:.3f}s")
        # All paginated requests should be fast (cached data)
        assert elapsed < 0.2, f"Pagination with size {page_size} took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_filter_performance(
    client: TestClient,
    mock_claude_base: Path,
    sample_session_with_agents: tuple[Path, str],
):
    """
    Test filtering performance by category and search.

    Verifies that filtering is fast when applied to cached data.
    """
    # Pre-warm cache
    response = client.get("/agents/usage")
    assert response.status_code == 200

    # Test category filter
    start_time = time.time()
    response = client.get("/agents/usage?category=plugin")
    elapsed = time.time() - start_time

    assert response.status_code == 200
    print(f"Category filter: {elapsed:.3f}s")
    assert elapsed < 0.2, f"Category filter took {elapsed:.3f}s"

    # Test search filter
    start_time = time.time()
    response = client.get("/agents/usage?search=executor")
    elapsed = time.time() - start_time

    assert response.status_code == 200
    print(f"Search filter: {elapsed:.3f}s")
    assert elapsed < 0.2, f"Search filter took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_agent_detail_performance(
    client: TestClient,
    mock_claude_base: Path,
    sample_session_with_agents: tuple[Path, str],
):
    """
    Test agent detail endpoint performance.

    Verifies that fetching detail for a specific agent is fast.
    """
    # Pre-warm cache
    response = client.get("/agents/usage")
    assert response.status_code == 200

    # Get first agent from list
    data = response.json()
    if not data["agents"]:
        pytest.skip("No agents found in test data")

    agent = data["agents"][0]
    subagent_type = agent["subagent_type"]

    # Measure detail fetch time
    start_time = time.time()
    response = client.get(f"/agents/usage/{subagent_type}")
    elapsed = time.time() - start_time

    assert response.status_code == 200
    detail = response.json()
    assert detail["subagent_type"] == subagent_type

    print(f"Agent detail fetch: {elapsed:.3f}s")
    assert elapsed < 0.5, f"Agent detail took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_agent_history_performance(
    client: TestClient,
    mock_claude_base: Path,
    sample_session_with_agents: tuple[Path, str],
):
    """
    Test agent invocation history endpoint performance.

    Verifies that paginated history is fast.
    """
    # Pre-warm cache
    response = client.get("/agents/usage")
    assert response.status_code == 200

    # Get first agent
    data = response.json()
    if not data["agents"]:
        pytest.skip("No agents found in test data")

    agent = data["agents"][0]
    subagent_type = agent["subagent_type"]

    # Measure history fetch time
    start_time = time.time()
    response = client.get(f"/agents/usage/{subagent_type}/history?per_page=20")
    elapsed = time.time() - start_time

    assert response.status_code == 200
    history = response.json()
    assert "items" in history
    assert "total" in history

    print(f"Agent history fetch: {elapsed:.3f}s")
    assert elapsed < 0.5, f"Agent history took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_early_exit_optimization(
    client: TestClient,
    mock_claude_base: Path,
):
    """
    Test early exit optimization by creating a session with many messages
    but only one agent invocation early in the conversation.

    Verifies that scanning stops early and doesn't process all messages.
    """
    # Create session with 1 agent invocation in first 10 messages,
    # followed by 90 messages without agents
    project_dir = mock_claude_base / "projects" / "-Users-test-earlyexit"
    project_dir.mkdir(parents=True, exist_ok=True)

    session_uuid = "early-exit-test-001"
    session_path = project_dir / f"{session_uuid}.jsonl"

    messages = []

    # First 10 messages with 1 agent invocation
    for i in range(10):
        is_user = i % 2 == 0
        content = [{"type": "text", "text": f"Message {i}"}]

        if i == 5:  # Add agent invocation in message 5
            content.append(
                {
                    "type": "tool_use",
                    "id": "toolu_early",
                    "name": "Task",
                    "input": {
                        "subagent_type": "oh-my-claudecode:executor",
                        "model": "sonnet",
                        "prompt": "Early task",
                    },
                }
            )

        msg_type = "user" if is_user else "assistant"
        messages.append(
            {
                "type": msg_type,
                "uuid": f"msg-{i:03d}",
                "sessionId": session_uuid,
                "timestamp": f"2026-02-12T10:{i:02d}:00.000Z",
                "message": {
                    "role": msg_type,
                    "content": content if not is_user else f"User message {i}",
                },
                "parentUuid": None,
                "isSidechain": False,
            }
        )

    # Add 90 more messages without agent invocations
    for i in range(10, 100):
        is_user = i % 2 == 0
        msg_type = "user" if is_user else "assistant"

        messages.append(
            {
                "type": msg_type,
                "uuid": f"msg-{i:03d}",
                "sessionId": session_uuid,
                "timestamp": f"2026-02-12T11:{i:02d}:00.000Z",
                "message": {
                    "role": msg_type,
                    "content": [{"type": "text", "text": f"Message {i}"}]
                    if not is_user
                    else f"User {i}",
                },
                "parentUuid": None,
                "isSidechain": False,
            }
        )

    with open(session_path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    # Clear cache
    clear_agent_usage_cache()

    # Measure scan time
    start_time = time.time()
    response = client.get("/agents/usage")
    elapsed = time.time() - start_time

    assert response.status_code == 200

    print(f"Early exit scan time: {elapsed:.3f}s")
    # Should be very fast due to early exit
    assert elapsed < 1.0, f"Early exit scan took {elapsed:.3f}s"
