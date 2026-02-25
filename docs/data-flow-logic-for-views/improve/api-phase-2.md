# Phase 2: Single-Pass Iteration Patterns

**Priority**: High
**Complexity**: Medium
**Impact**: High
**Risk**: Medium

**Dependency**: Phase 1 (Model-Level Caching) should be completed first

---

## Problem Statement

API endpoints perform multiple sequential iterations over the same message stream. Each iteration reopens and reparses the JSONL file.

### Verified Issues

| Endpoint | Location | Iterations | Issue |
|----------|----------|------------|-------|
| `get_subagents()` | `sessions.py:408-491` | 4+ passes | Pre-collect, tool results, Task mapping, per-subagent x2 |
| `get_timeline()` | `sessions.py:824-952` | 2 passes | `_collect_tool_results()` + main timeline build |
| `get_file_activity()` | `sessions.py:365-405` | 2 passes | Main session + per-subagent |
| `get_tools()` | `sessions.py:494-540` | 2 passes | Main session + per-subagent |

---

## Solution Design

### Pattern 1: Unified Data Collector

Create a single-pass collector that extracts all needed data in one iteration.

#### Implementation: SessionDataCollector

```python
# apps/api/utils/collectors.py

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from models import Session, AssistantMessage, UserMessage, ToolUseBlock

@dataclass
class ToolCall:
    """Represents a single tool invocation."""
    tool_use_id: str
    name: str
    input: Dict[str, Any]
    timestamp: datetime
    actor: str  # "main" or agent_id
    result: Optional[str] = None

@dataclass
class SessionData:
    """All extractable data from a session's messages."""
    # Timestamps
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Identity
    slug: Optional[str] = None

    # Messages
    messages: List[Message] = field(default_factory=list)
    initial_prompt: Optional[str] = None

    # Tool usage
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_counts: Dict[str, int] = field(default_factory=dict)

    # File activity
    file_reads: List[Dict] = field(default_factory=list)
    file_writes: List[Dict] = field(default_factory=list)

    # Subagent spawning info
    task_to_subagent: Dict[str, str] = field(default_factory=dict)  # tool_use_id -> spawned_agent_id
    subagent_types: Dict[str, str] = field(default_factory=dict)    # agent_id -> subagent_type

    # Context
    git_branches: Set[str] = field(default_factory=set)
    working_directories: Set[str] = field(default_factory=set)

    # Usage
    usage: Optional[TokenUsage] = None


def collect_session_data(session: Session, include_subagents: bool = False) -> SessionData:
    """
    Single-pass extraction of all session data.

    Args:
        session: The session to collect data from
        include_subagents: Whether to also collect subagent data

    Returns:
        SessionData with all extracted information
    """
    data = SessionData()
    usage = TokenUsage()

    FILE_TOOLS = {"Read", "Write", "Edit", "Delete", "Glob", "Grep"}

    for msg in session.iter_messages():
        # Store message reference
        data.messages.append(msg)

        # Timestamps
        if data.start_time is None:
            data.start_time = msg.timestamp
        data.end_time = msg.timestamp

        # Slug
        if not data.slug and hasattr(msg, 'slug') and msg.slug:
            data.slug = msg.slug

        # Initial prompt (first user message)
        if data.initial_prompt is None and isinstance(msg, UserMessage):
            data.initial_prompt = msg.content[:500] if msg.content else None

        # Git branches and working directories
        if hasattr(msg, 'git_branch') and msg.git_branch:
            data.git_branches.add(msg.git_branch)
        if hasattr(msg, 'cwd') and msg.cwd:
            data.working_directories.add(msg.cwd)
        elif hasattr(msg, 'workingDirectory') and msg.workingDirectory:
            data.working_directories.add(msg.workingDirectory)

        # Assistant message processing
        if isinstance(msg, AssistantMessage):
            # Usage aggregation
            if msg.usage:
                usage = usage + msg.usage

            # Tool processing
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock):
                    tool_name = block.name

                    # Count tools
                    data.tool_counts[tool_name] = data.tool_counts.get(tool_name, 0) + 1

                    # Create tool call record
                    tool_call = ToolCall(
                        tool_use_id=block.id,
                        name=tool_name,
                        input=block.input or {},
                        timestamp=msg.timestamp,
                        actor="main"
                    )
                    data.tool_calls.append(tool_call)

                    # Extract file activity
                    if tool_name in FILE_TOOLS:
                        file_path = block.input.get("file_path") or block.input.get("path")
                        if file_path:
                            file_record = {
                                "path": file_path,
                                "tool": tool_name,
                                "timestamp": msg.timestamp,
                                "actor": "main"
                            }
                            if tool_name in {"Write", "Edit", "Delete"}:
                                data.file_writes.append(file_record)
                            else:
                                data.file_reads.append(file_record)

                    # Extract Task -> subagent mapping
                    if tool_name == "Task":
                        subagent_type = block.input.get("subagent_type")
                        if subagent_type:
                            data.task_to_subagent[block.id] = subagent_type

    data.usage = usage

    # Collect subagent data if requested
    if include_subagents:
        for subagent in session.list_subagents():
            _collect_subagent_data(subagent, data)

    return data


def _collect_subagent_data(subagent, data: SessionData) -> None:
    """Add subagent data to the session data collector."""
    agent_id = subagent.agent_id
    FILE_TOOLS = {"Read", "Write", "Edit", "Delete", "Glob", "Grep"}

    for msg in subagent.iter_messages():
        if isinstance(msg, AssistantMessage):
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock):
                    tool_name = block.name

                    # Count tools
                    data.tool_counts[tool_name] = data.tool_counts.get(tool_name, 0) + 1

                    # Create tool call record
                    tool_call = ToolCall(
                        tool_use_id=block.id,
                        name=tool_name,
                        input=block.input or {},
                        timestamp=msg.timestamp,
                        actor=agent_id
                    )
                    data.tool_calls.append(tool_call)

                    # Extract file activity
                    if tool_name in FILE_TOOLS:
                        file_path = block.input.get("file_path") or block.input.get("path")
                        if file_path:
                            file_record = {
                                "path": file_path,
                                "tool": tool_name,
                                "timestamp": msg.timestamp,
                                "actor": agent_id
                            }
                            if tool_name in {"Write", "Edit", "Delete"}:
                                data.file_writes.append(file_record)
                            else:
                                data.file_reads.append(file_record)
```

---

### Pattern 2: Refactored Endpoints

#### Refactored `get_subagents()` Endpoint

```python
# apps/api/routers/sessions.py

@router.get("/{session_uuid}/subagents")
async def get_subagents(session_uuid: str) -> SubagentResponse:
    """Get subagent activity with single-pass data collection."""
    session = _get_session(session_uuid)

    # Single pass through main session + subagents
    data = collect_session_data(session, include_subagents=True)

    # Build response from collected data
    subagents = []
    subagent_map = {sa.agent_id: sa for sa in session.list_subagents()}

    for agent_id, subagent in subagent_map.items():
        # Filter tool calls for this subagent
        agent_tools = [tc for tc in data.tool_calls if tc.actor == agent_id]
        tool_counts = {}
        for tc in agent_tools:
            tool_counts[tc.name] = tool_counts.get(tc.name, 0) + 1

        # Get subagent type from Task tool mapping
        subagent_type = None
        for tool_use_id, stype in data.task_to_subagent.items():
            # Match by checking if this subagent was spawned by this Task
            if _matches_subagent(tool_use_id, agent_id, data.tool_calls):
                subagent_type = stype
                break

        # Find initial prompt for this subagent
        initial_prompt = None
        for msg in subagent.iter_messages():
            if isinstance(msg, UserMessage):
                initial_prompt = msg.content[:500] if msg.content else None
                break

        subagents.append({
            "agent_id": agent_id,
            "slug": subagent.slug,
            "subagent_type": subagent_type,
            "tool_counts": tool_counts,
            "initial_prompt": initial_prompt
        })

    return SubagentResponse(subagents=subagents)
```

#### Refactored `get_timeline()` Endpoint

```python
# apps/api/routers/sessions.py

@router.get("/{session_uuid}/timeline")
async def get_timeline(session_uuid: str) -> TimelineResponse:
    """Get chronological event timeline with single-pass collection."""
    session = _get_session(session_uuid)

    # Collect data including subagents
    data = collect_session_data(session, include_subagents=True)

    # Load tool results in batch
    tool_results = _load_tool_results_batch(session, [tc.tool_use_id for tc in data.tool_calls])

    # Build timeline events from collected data
    events = []
    for msg in data.messages:
        if isinstance(msg, UserMessage):
            events.append(TimelineEvent(
                type="user_message",
                timestamp=msg.timestamp,
                content=msg.content[:200] if msg.content else None
            ))
        elif isinstance(msg, AssistantMessage):
            # Add thinking event if present
            for block in msg.content_blocks:
                if isinstance(block, ThinkingBlock):
                    events.append(TimelineEvent(
                        type="thinking",
                        timestamp=msg.timestamp,
                        content=block.thinking[:200] if block.thinking else None
                    ))

            # Add tool events
            for tc in data.tool_calls:
                if tc.timestamp == msg.timestamp and tc.actor == "main":
                    events.append(TimelineEvent(
                        type="tool_use",
                        timestamp=tc.timestamp,
                        tool_name=tc.name,
                        tool_input=tc.input,
                        tool_result=tool_results.get(tc.tool_use_id)
                    ))

    return TimelineResponse(events=sorted(events, key=lambda e: e.timestamp))


def _load_tool_results_batch(session: Session, tool_use_ids: List[str]) -> Dict[str, str]:
    """Load multiple tool results efficiently."""
    results = {}
    tool_results_dir = session.tool_results_dir

    if not tool_results_dir or not tool_results_dir.exists():
        return results

    # Pre-list directory contents once
    available_files = {f.stem: f for f in tool_results_dir.glob("toolu_*.txt")}

    for tool_use_id in tool_use_ids:
        if tool_use_id in available_files:
            try:
                results[tool_use_id] = available_files[tool_use_id].read_text(encoding="utf-8")
            except Exception:
                pass

    return results
```

#### Refactored `get_file_activity()` Endpoint

```python
@router.get("/{session_uuid}/file-activity")
async def get_file_activity(session_uuid: str) -> FileActivityResponse:
    """Get file read/write operations with single-pass collection."""
    session = _get_session(session_uuid)

    # Single pass extraction
    data = collect_session_data(session, include_subagents=True)

    return FileActivityResponse(
        reads=data.file_reads,
        writes=data.file_writes
    )
```

#### Refactored `get_tools()` Endpoint

```python
@router.get("/{session_uuid}/tools")
async def get_tools(session_uuid: str) -> ToolsResponse:
    """Get tool usage breakdown with single-pass collection."""
    session = _get_session(session_uuid)

    # Single pass extraction
    data = collect_session_data(session, include_subagents=True)

    # Split by actor
    main_tools = {}
    subagent_tools = {}

    for tc in data.tool_calls:
        if tc.actor == "main":
            main_tools[tc.name] = main_tools.get(tc.name, 0) + 1
        else:
            subagent_tools[tc.name] = subagent_tools.get(tc.name, 0) + 1

    return ToolsResponse(
        by_session=main_tools,
        by_subagents=subagent_tools,
        total=data.tool_counts
    )
```

---

## Pattern 3: Request-Scoped Caching

For requests that hit multiple endpoints, cache collected data at request scope.

```python
# apps/api/middleware/request_cache.py

from contextvars import ContextVar
from typing import Dict, Any

_request_cache: ContextVar[Dict[str, Any]] = ContextVar('request_cache', default={})

def get_request_cache() -> Dict[str, Any]:
    return _request_cache.get()

def set_session_data(session_uuid: str, data: SessionData) -> None:
    cache = get_request_cache()
    cache[f"session:{session_uuid}"] = data

def get_session_data(session_uuid: str) -> Optional[SessionData]:
    cache = get_request_cache()
    return cache.get(f"session:{session_uuid}")


# Middleware to reset cache per request
@app.middleware("http")
async def request_cache_middleware(request: Request, call_next):
    _request_cache.set({})
    response = await call_next(request)
    return response
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `apps/api/utils/collectors.py` | NEW - Create `SessionData`, `ToolCall`, `collect_session_data()` |
| `apps/api/routers/sessions.py` | Refactor `get_subagents()`, `get_timeline()`, `get_file_activity()`, `get_tools()` |
| `apps/api/middleware/request_cache.py` | NEW - Optional request-scoped caching |

---

## Implementation Steps

### Step 1: Create Collector Module
1. Define `SessionData` dataclass with all fields
2. Implement `collect_session_data()` single-pass function
3. Add helper for subagent data collection

### Step 2: Refactor get_timeline()
1. Replace `_collect_tool_results()` + main iteration with single collector call
2. Add batch tool result loading
3. Verify response format unchanged

### Step 3: Refactor get_subagents()
1. Replace 4-pass logic with collector
2. Map Task tool_use_id to spawned agents
3. Verify response format unchanged

### Step 4: Refactor get_file_activity()
1. Replace dual iteration with collector
2. Verify response format unchanged

### Step 5: Refactor get_tools()
1. Replace dual iteration with collector
2. Verify response format unchanged

### Step 6: Add Request-Scoped Cache (Optional)
1. Implement middleware for cache lifecycle
2. Cache session data on first access
3. Reuse for subsequent endpoint calls in same request

---

## Testing Requirements

### Unit Tests

```python
# tests/test_collectors.py

def test_collect_session_data_single_pass(session_with_tools):
    """Verify all data extracted in one pass."""
    with patch.object(session_with_tools, 'iter_messages', wraps=session_with_tools.iter_messages) as mock:
        data = collect_session_data(session_with_tools)
        assert mock.call_count == 1

    assert data.start_time is not None
    assert data.end_time is not None
    assert len(data.tool_calls) > 0
    assert len(data.tool_counts) > 0

def test_collect_with_subagents(session_with_subagents):
    """Verify subagent data included correctly."""
    data = collect_session_data(session_with_subagents, include_subagents=True)

    # Should have tool calls from both main and subagents
    actors = {tc.actor for tc in data.tool_calls}
    assert "main" in actors
    assert len(actors) > 1  # Has subagent actors

def test_file_activity_extraction(session_with_file_ops):
    """Verify file reads/writes extracted correctly."""
    data = collect_session_data(session_with_file_ops)

    assert len(data.file_reads) > 0
    assert len(data.file_writes) > 0
    assert all("path" in f for f in data.file_reads)
```

### Integration Tests

```python
# tests/test_sessions_api.py

def test_get_timeline_single_iteration(client, session_uuid):
    """Verify timeline endpoint uses single pass."""
    with patch('apps.api.utils.collectors.collect_session_data') as mock:
        mock.return_value = create_mock_session_data()
        response = client.get(f"/sessions/{session_uuid}/timeline")
        assert response.status_code == 200
        mock.assert_called_once()

def test_get_subagents_single_iteration(client, session_uuid):
    """Verify subagents endpoint uses single pass."""
    # Similar pattern
```

---

## Expected Impact

| Endpoint | Before | After | Improvement |
|----------|--------|-------|-------------|
| `get_subagents()` | 4+ iterations | 1 iteration | 4x fewer file reads |
| `get_timeline()` | 2 iterations | 1 iteration | 2x fewer file reads |
| `get_file_activity()` | N+1 iterations | 1 iteration | N+1x fewer file reads |
| `get_tools()` | N+1 iterations | 1 iteration | N+1x fewer file reads |

Where N = number of subagents.

---

## Rollback Plan

1. Revert endpoint implementations to original multi-pass logic
2. Remove `collectors.py` module
3. Remove request cache middleware (if added)
4. No database changes required
5. No API contract changes

---

## Success Criteria

- [ ] All existing API tests pass
- [ ] New collector tests pass
- [ ] Response format unchanged (verified by snapshot tests)
- [ ] File I/O reduced by >50% for affected endpoints
- [ ] Latency reduced by >30% for sessions with 5+ subagents
