# Agent Work Summary - Backend Implementation Guide

## Overview

This document provides implementation details for extending the `/sessions/{uuid}/subagents` API endpoint to include task summary data for each subagent.

**Goal**: Expose duration, token usage, completion status, and file operations for each subagent spawned during a session.

---

## Current State

**Endpoint**: `GET /sessions/{uuid}/subagents`
**Location**: `apps/api/routers/sessions.py` (lines 361-444)

**Current Response**:
```python
class SubagentSummary(BaseModel):
    agent_id: str
    slug: str | None
    subagent_type: str | None
    tools_used: dict[str, int]
    message_count: int
    initial_prompt: str | None
```

---

## Phase 1: Extend Schema

**File**: `apps/api/schemas.py`

### 1.1 Update SubagentSummary Model

Add the following fields to the existing `SubagentSummary` class:

```python
class SubagentSummary(BaseModel):
    """Summary of a subagent spawned during a session."""

    # Existing fields
    agent_id: str = Field(..., description="Unique agent identifier")
    slug: str | None = Field(None, description="Human-readable agent slug")
    subagent_type: str | None = Field(None, description="Type from Task invocation")
    tools_used: dict[str, int] = Field(default_factory=dict, description="Tool usage counts")
    message_count: int = Field(..., description="Total messages in conversation")
    initial_prompt: str | None = Field(None, description="First user message (max 500 chars)")

    # NEW: Timing fields
    start_time: datetime | None = Field(None, description="First message timestamp")
    end_time: datetime | None = Field(None, description="Last message timestamp")
    duration_seconds: float | None = Field(None, description="Total duration in seconds")

    # NEW: Token usage fields
    total_input_tokens: int = Field(0, description="Total input tokens consumed")
    total_output_tokens: int = Field(0, description="Total output tokens generated")
    cache_read_tokens: int = Field(0, description="Tokens read from cache")
    cache_creation_tokens: int = Field(0, description="Tokens used for cache creation")
    cache_hit_rate: float = Field(0.0, description="Cache hit rate (0.0-1.0)")

    # NEW: Task completion fields
    completion_status: str | None = Field(
        None,
        description="Inferred status: 'completed', 'error', or None if unknown"
    )
    final_output: str | None = Field(
        None,
        description="Last text response from agent (max 500 chars)"
    )

    # NEW: File operations
    file_read_count: int = Field(0, description="Number of file read operations")
    file_write_count: int = Field(0, description="Number of file write/edit operations")

    # NEW: Model info
    models_used: list[str] = Field(default_factory=list, description="Models used by this agent")
```

### 1.2 Add Required Import

```python
from datetime import datetime
```

---

## Phase 2: Add Timing Data

**File**: `apps/api/routers/sessions.py`

### 2.1 Extract Timing from Agent

The `Agent` model already has `start_time` and `end_time` properties. Use them in the subagents endpoint.

**Location**: Inside the `get_session_subagents()` function (around line 400)

```python
@router.get("/sessions/{uuid}/subagents", response_model=list[SubagentSummary])
async def get_session_subagents(uuid: str) -> list[SubagentSummary]:
    session = _get_session(uuid)

    # ... existing type matching logic (lines 368-397) ...

    summaries = []
    for subagent in session.list_subagents():
        # Existing: tool counting
        tool_counts: dict[str, int] = {}
        for msg in subagent.iter_messages():
            if isinstance(msg, AssistantMessage):
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        tool_counts[block.name] = tool_counts.get(block.name, 0) + 1

        # Existing: initial prompt
        initial_prompt = None
        for msg in subagent.iter_messages():
            if isinstance(msg, UserMessage):
                initial_prompt = msg.content[:500] if msg.content else None
                break

        # NEW: Timing data
        start_time = subagent.start_time
        end_time = subagent.end_time
        duration_seconds = None
        if start_time and end_time:
            duration_seconds = (end_time - start_time).total_seconds()

        # ... rest of function ...
```

### 2.2 Update Summary Construction

```python
        summaries.append(SubagentSummary(
            agent_id=subagent.agent_id,
            slug=subagent.slug,
            subagent_type=matched_type,
            tools_used=tool_counts,
            message_count=subagent.message_count,
            initial_prompt=initial_prompt,
            # NEW
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_seconds,
        ))
```

---

## Phase 3: Add Token Usage Data

**File**: `apps/api/routers/sessions.py`

### 3.1 Get Usage Summary

The `Agent` model has a `get_usage_summary()` method that aggregates token usage.

```python
        # NEW: Token usage
        usage = subagent.get_usage_summary()

        cache_hit_rate = 0.0
        if usage:
            total_cacheable = usage.cache_creation_input_tokens + usage.cache_read_input_tokens
            if total_cacheable > 0:
                cache_hit_rate = usage.cache_read_input_tokens / total_cacheable
```

### 3.2 Update Summary Construction

```python
        summaries.append(SubagentSummary(
            # ... existing fields ...

            # Token usage
            total_input_tokens=usage.input_tokens if usage else 0,
            total_output_tokens=usage.output_tokens if usage else 0,
            cache_read_tokens=usage.cache_read_input_tokens if usage else 0,
            cache_creation_tokens=usage.cache_creation_input_tokens if usage else 0,
            cache_hit_rate=cache_hit_rate,
        ))
```

---

## Phase 4: Add Completion Status and Final Output

**File**: `apps/api/routers/sessions.py`

### 4.1 Infer Completion Status

Analyze the last assistant message to determine completion status.

```python
def _infer_completion_status(subagent: Agent) -> tuple[str | None, str | None]:
    """
    Infer completion status and extract final output from last assistant message.

    Returns:
        tuple: (completion_status, final_output)
        - completion_status: 'completed', 'error', or None
        - final_output: Last text content (max 500 chars)
    """
    last_assistant_msg = None

    # Get last assistant message
    for msg in subagent.iter_messages():
        if isinstance(msg, AssistantMessage):
            last_assistant_msg = msg

    if not last_assistant_msg:
        return None, None

    # Extract final text output
    final_output = None
    text_blocks = [
        block.text for block in last_assistant_msg.content_blocks
        if isinstance(block, TextBlock)
    ]
    if text_blocks:
        final_output = text_blocks[-1][:500]

    # Infer status from stop_reason and content
    completion_status = None

    if last_assistant_msg.stop_reason == "end_turn":
        completion_status = "completed"
    elif last_assistant_msg.stop_reason == "tool_use":
        # Agent was interrupted mid-tool-use - might be incomplete
        completion_status = None

    # Check for error indicators in final output
    if final_output:
        error_indicators = ["error:", "failed:", "exception:", "traceback"]
        if any(indicator in final_output.lower() for indicator in error_indicators):
            completion_status = "error"

    return completion_status, final_output
```

### 4.2 Use in Endpoint

```python
        # NEW: Completion status
        completion_status, final_output = _infer_completion_status(subagent)
```

### 4.3 Update Summary Construction

```python
        summaries.append(SubagentSummary(
            # ... existing fields ...

            # Completion
            completion_status=completion_status,
            final_output=final_output,
        ))
```

---

## Phase 5: Add File Operations Count

**File**: `apps/api/routers/sessions.py`

### 5.1 Count File Operations

Extract file operation counts from tool usage.

```python
def _count_file_operations(tool_counts: dict[str, int]) -> tuple[int, int]:
    """
    Count file read and write operations from tool usage.

    Returns:
        tuple: (read_count, write_count)
    """
    read_tools = {"Read", "Glob", "Grep", "LS", "SemanticSearch"}
    write_tools = {"Write", "Edit", "StrReplace", "Delete", "MultiEdit"}

    read_count = sum(tool_counts.get(tool, 0) for tool in read_tools)
    write_count = sum(tool_counts.get(tool, 0) for tool in write_tools)

    return read_count, write_count
```

### 5.2 Use in Endpoint

```python
        # NEW: File operations
        file_read_count, file_write_count = _count_file_operations(tool_counts)
```

### 5.3 Update Summary Construction

```python
        summaries.append(SubagentSummary(
            # ... existing fields ...

            # File operations
            file_read_count=file_read_count,
            file_write_count=file_write_count,
        ))
```

---

## Phase 6: Add Models Used

**File**: `apps/api/routers/sessions.py`

### 6.1 Extract Models

```python
        # NEW: Models used
        models_used = list(subagent.get_models_used())
```

### 6.2 Update Summary Construction

```python
        summaries.append(SubagentSummary(
            # ... existing fields ...

            # Models
            models_used=models_used,
        ))
```

---

## Complete Updated Function

Here's the complete updated `get_session_subagents` function:

```python
@router.get("/sessions/{uuid}/subagents", response_model=list[SubagentSummary])
async def get_session_subagents(uuid: str) -> list[SubagentSummary]:
    """Get all subagents spawned during a session with task summaries."""
    session = _get_session(uuid)

    # Build type mapping (existing logic - lines 368-397)
    agent_id_to_type: dict[str, str] = {}
    desc_to_type: dict[str, str] = {}

    for msg in session.iter_messages():
        if isinstance(msg, UserMessage) and msg.tool_use_id:
            # ... existing type extraction logic ...
            pass

    summaries = []
    for subagent in session.list_subagents():
        # Tool counting
        tool_counts: dict[str, int] = {}
        for msg in subagent.iter_messages():
            if isinstance(msg, AssistantMessage):
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        tool_counts[block.name] = tool_counts.get(block.name, 0) + 1

        # Initial prompt
        initial_prompt = None
        for msg in subagent.iter_messages():
            if isinstance(msg, UserMessage):
                initial_prompt = msg.content[:500] if msg.content else None
                break

        # Type matching (existing logic)
        matched_type = agent_id_to_type.get(subagent.agent_id)
        if not matched_type and initial_prompt:
            key = normalize_key(initial_prompt[:100])
            matched_type = desc_to_type.get(key)

        # NEW: Timing
        start_time = subagent.start_time
        end_time = subagent.end_time
        duration_seconds = None
        if start_time and end_time:
            duration_seconds = (end_time - start_time).total_seconds()

        # NEW: Token usage
        usage = subagent.get_usage_summary()
        cache_hit_rate = 0.0
        if usage:
            total_cacheable = usage.cache_creation_input_tokens + usage.cache_read_input_tokens
            if total_cacheable > 0:
                cache_hit_rate = usage.cache_read_input_tokens / total_cacheable

        # NEW: Completion status
        completion_status, final_output = _infer_completion_status(subagent)

        # NEW: File operations
        file_read_count, file_write_count = _count_file_operations(tool_counts)

        # NEW: Models
        models_used = list(subagent.get_models_used())

        summaries.append(SubagentSummary(
            agent_id=subagent.agent_id,
            slug=subagent.slug,
            subagent_type=matched_type,
            tools_used=tool_counts,
            message_count=subagent.message_count,
            initial_prompt=initial_prompt,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_seconds,
            total_input_tokens=usage.input_tokens if usage else 0,
            total_output_tokens=usage.output_tokens if usage else 0,
            cache_read_tokens=usage.cache_read_input_tokens if usage else 0,
            cache_creation_tokens=usage.cache_creation_input_tokens if usage else 0,
            cache_hit_rate=cache_hit_rate,
            completion_status=completion_status,
            final_output=final_output,
            file_read_count=file_read_count,
            file_write_count=file_write_count,
            models_used=models_used,
        ))

    return summaries
```

---

## Testing

**File**: `apps/api/tests/test_sessions.py`

### Add Tests for New Fields

```python
def test_subagent_summary_includes_timing(tmp_path, monkeypatch):
    """Test that subagent summary includes timing data."""
    # Setup session with subagent...

    response = client.get(f"/sessions/{uuid}/subagents")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1

    subagent = data[0]
    assert "start_time" in subagent
    assert "end_time" in subagent
    assert "duration_seconds" in subagent
    assert subagent["duration_seconds"] >= 0


def test_subagent_summary_includes_token_usage(tmp_path, monkeypatch):
    """Test that subagent summary includes token usage."""
    # Setup session with subagent that has usage data...

    response = client.get(f"/sessions/{uuid}/subagents")
    data = response.json()[0]

    assert "total_input_tokens" in data
    assert "total_output_tokens" in data
    assert "cache_hit_rate" in data
    assert 0 <= data["cache_hit_rate"] <= 1


def test_subagent_completion_status_completed(tmp_path, monkeypatch):
    """Test completion status is 'completed' for normal end_turn."""
    # Setup subagent with stop_reason="end_turn"...

    response = client.get(f"/sessions/{uuid}/subagents")
    data = response.json()[0]

    assert data["completion_status"] == "completed"


def test_subagent_completion_status_error(tmp_path, monkeypatch):
    """Test completion status is 'error' when error detected."""
    # Setup subagent with error in final output...

    response = client.get(f"/sessions/{uuid}/subagents")
    data = response.json()[0]

    assert data["completion_status"] == "error"


def test_subagent_file_operations_count(tmp_path, monkeypatch):
    """Test file operations are counted correctly."""
    # Setup subagent with Read, Write, Edit tools...

    response = client.get(f"/sessions/{uuid}/subagents")
    data = response.json()[0]

    assert data["file_read_count"] == 3  # Based on test data
    assert data["file_write_count"] == 2
```

---

## Validation Checklist

- [ ] Schema updated in `apps/api/schemas.py`
- [ ] Timing extraction implemented
- [ ] Token usage aggregation implemented
- [ ] Completion status inference implemented
- [ ] File operations counting implemented
- [ ] Models used extraction implemented
- [ ] All tests passing: `pytest apps/api/tests/test_sessions.py -v`
- [ ] Linting passes: `ruff check apps/api/`
- [ ] API docs updated (auto-generated from schema)

---

## API Response Example

After implementation, the endpoint will return:

```json
[
  {
    "agent_id": "a5793c3",
    "slug": "eager-puzzling-fairy",
    "subagent_type": "Explore",
    "tools_used": {
      "Read": 5,
      "Grep": 3,
      "Glob": 2
    },
    "message_count": 12,
    "initial_prompt": "Explore the codebase to find...",
    "start_time": "2024-01-15T10:30:00Z",
    "end_time": "2024-01-15T10:32:45Z",
    "duration_seconds": 165.0,
    "total_input_tokens": 15420,
    "total_output_tokens": 3250,
    "cache_read_tokens": 12000,
    "cache_creation_tokens": 3420,
    "cache_hit_rate": 0.778,
    "completion_status": "completed",
    "final_output": "I've completed the exploration. Here's what I found...",
    "file_read_count": 10,
    "file_write_count": 0,
    "models_used": ["claude-sonnet-4-20250514"]
  }
]
```
