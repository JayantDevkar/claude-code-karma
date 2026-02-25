# Backend: Expose `subagent_type` from Task Tool

> **Status: IMPLEMENTED** (2026-01-10)

## Goal
Extract and expose `subagent_type` from Task tool invocations so consumers can identify what kind of subagent was spawned (e.g., `Explore`, `Plan`, `Bash`).

---

## Phase 1: Update Schema

**File:** `apps/api/schemas.py`

Add `subagent_type` to `SubagentSummary`:

```python
class SubagentSummary(BaseModel):
    agent_id: str
    slug: Optional[str] = None
    subagent_type: Optional[str] = None  # NEW: e.g., "Explore", "Plan", "Bash"
    tools_used: dict[str, int] = Field(default_factory=dict)
    message_count: int = 0
    initial_prompt: Optional[str] = None
```

**Why optional:** Not all Task invocations have `subagent_type` (older data, custom prompts).

---

## Phase 2: Extract `subagent_type` in Timeline Processing

**File:** `apps/api/routers/sessions.py`

### 2a. Update `get_tool_summary()` (~line 503-505)

Current:
```python
elif tool_name == "Task":
    description = tool_input.get("description", "")
    return "Spawn subagent", description[:100] if description else None, {"description": description}
```

Change to:
```python
elif tool_name == "Task":
    description = tool_input.get("description", "")
    subagent_type = tool_input.get("subagent_type", "")
    return "Spawn subagent", description[:100] if description else None, {
        "description": description,
        "subagent_type": subagent_type,
    }
```

### 2b. Propagate to TimelineEvent metadata

The `subagent_type` is now in `metadata["subagent_type"]` for all `subagent_spawn` events.

---

## Phase 3: Link Subagents to Their Task Invocation

**File:** `apps/api/routers/sessions.py`

### Correlation Strategy

Match subagent to Task invocation by comparing:
- `Task.input.description` ↔ `Agent.initial_prompt` (first 100 chars)
- Fallback: sequence order (Task #1 → Subagent #1)

### 3a. Build Task-to-Type Map

In `get_session_subagents()` endpoint, before building `SubagentSummary` list:

```python
# Build map: description_prefix -> subagent_type from Task tool calls
task_type_map: dict[str, str] = {}
for msg in session.iter_messages():
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, ToolUseBlock) and block.name == "Task":
                desc = block.input.get("description", "")[:100]
                stype = block.input.get("subagent_type", "")
                if desc and stype:
                    task_type_map[desc] = stype
```

### 3b. Match When Building SubagentSummary

```python
# In subagent iteration
initial_prompt = get_initial_prompt(agent)
prompt_prefix = (initial_prompt or "")[:100]
subagent_type = task_type_map.get(prompt_prefix, None)

subagents.append(SubagentSummary(
    agent_id=agent.agent_id,
    slug=agent.slug,
    subagent_type=subagent_type,  # NEW
    tools_used=tools_used,
    message_count=msg_count,
    initial_prompt=initial_prompt,
))
```

### Performance Note

This adds one iteration over messages. For future agent view:
- Consider caching Task invocations during session load
- Or create a dedicated `TaskInvocation` model for reuse

---

## Phase 4: Update Existing Endpoints

### 4a. `/sessions/{uuid}/subagents`
Already covered by Phase 3.

### 4b. `/sessions/{uuid}/timeline`
Already covered by Phase 2b - `subagent_type` in metadata.

### 4c. `/sessions/{uuid}` (SessionDetail)
No change needed - subagent count is sufficient here.

---

## Testing

**File:** `apps/api/tests/test_sessions.py`

Three test cases were added to `TestGetSubagentsEndpoint`:

```python
def test_subagent_type_extracted():
    """Verify subagent_type is extracted from Task tool and linked to SubagentSummary."""
    # Creates Task tool call with subagent_type="Explore"
    # Creates subagent with matching initial_prompt
    # Asserts subagent_type="Explore" in response

def test_subagent_type_optional():
    """Verify missing subagent_type doesn't break parsing and returns None."""
    # Creates Task tool call WITHOUT subagent_type field
    # Asserts subagent_type=None (not error)

def test_subagent_type_no_match():
    """Verify subagent_type is None when subagent prompt doesn't match any Task."""
    # Creates Task with description "Task A"
    # Creates subagent with different initial_prompt
    # Asserts subagent_type=None (no correlation found)
```

**Run tests:**
```bash
python3 -m pytest apps/api/tests/test_sessions.py -v -k "subagent_type"
```

---

## Files Changed

| File | Change |
|------|--------|
| `apps/api/schemas.py` | Added `subagent_type: Optional[str]` to `SubagentSummary` |
| `apps/api/routers/sessions.py` | Extract `subagent_type` in `get_tool_summary()`, build `task_type_map` and link in `get_subagents()` |
| `apps/api/tests/test_sessions.py` | Updated test router, added 3 tests for `subagent_type` |
| `packages/types/src/index.ts` | Added `subagent_type` to `SubagentSummary` and `ToolCallMetadata` interfaces |
| `apps/web/hooks/__tests__/use-session.test.ts` | Updated mock data with `subagent_type` field |

---

## Implementation Notes

### Correlation Strategy

The `subagent_type` is linked to subagents by matching:
- **Task tool's `description`** (first 100 chars) ↔ **Subagent's `initial_prompt`** (first 100 chars)

This works because Claude Code passes the Task description as the first user message to the spawned subagent.

### Refinements Applied (2026-01-10)

1. **Whitespace Normalization** - Added `normalize_key()` helper that:
   - Converts to lowercase
   - Strips leading/trailing whitespace
   - Collapses multiple spaces to single space
   - Applied to both Task description and subagent prompt for matching

2. **None Instead of Empty String** - Changed `block.input.get("subagent_type", "")` to `block.input.get("subagent_type")` for clearer semantics

3. **Debug Logging** - Added logging for unmatched subagents:
   ```python
   logger.debug(f"Subagent {subagent.agent_id} unmatched. Prompt: '{prompt_prefix[:50]}...'")
   ```

### Known `subagent_type` Values

| Type | Source | Description |
|------|--------|-------------|
| `Explore` | Built-in | Read-only codebase exploration |
| `Plan` | Built-in | Plan mode research |
| `general-purpose` | Built-in | Complex multi-step tasks |
| `claude-code-guide` | Built-in | Claude Code documentation |
| `haiku` | Built-in | Fast, lightweight tasks |
| `Bash` | Built-in | Shell command execution |
| `acompact` | System | Auto-compaction agent for context management (added v2.1.21+) |
| `aprompt_suggestion` | System | Prompt suggestion/autocomplete agent (added v2.1.21+) |
| `{custom-name}` | User-defined | Custom agents from `~/.claude/agents/` |

### System Agents (v2.1.19+)

System agents are automatically spawned by Claude Code for internal operations. They differ from user-initiated subagents:

| Type | Purpose | User Visible? |
|------|---------|---------------|
| `acompact` | Runs auto-compaction when context limit is reached | Partially (runs in background) |
| `aprompt_suggestion` | Generates prompt suggestions/autocomplete | No (UI integration) |

These agents use the `a` prefix pattern (likely "auto" or "async") and are tracked in JSONL but not explicitly triggered by user Task tool calls.

### Test Results

All 195 API tests pass, including:
- `test_subagent_type_extracted` - Verifies linking works
- `test_subagent_type_optional` - Verifies None handling
- `test_subagent_type_no_match` - Verifies unmatched subagents get None
- `test_subagent_type_whitespace_normalization` - Verifies whitespace/case differences don't break matching

---

## Future Considerations

1. **Agent View**: When building dedicated agent analytics, extract Task invocations into reusable data structure
2. **Filtering**: Add `?subagent_type=Explore` query param to `/sessions/{uuid}/subagents`
3. **Aggregation**: Add `subagent_types_used: dict[str, int]` to `SessionDetail` for summary stats

---

## Code Review (2026-01-10)

**Reviewer:** Senior System Architect

### Verdict: ✅ APPROVED - All concerns addressed

| Criteria | Status | Notes |
|----------|--------|-------|
| Schema Design | ✅ PASS | `Optional[str]` correct, clear docs |
| Data Extraction | ✅ PASS | Safe `.get()` with defaults |
| Correlation Logic | ✅ FIXED | Now uses `normalize_key()` for robust matching |
| Performance | ⚠️ ACCEPTABLE | O(n×m) acceptable for typical sessions |
| Test Coverage | ✅ PASS | All critical paths tested + whitespace test |
| Error Handling | ✅ PASS | Graceful with missing fields |

### ❌ Blockers
None

### ⚠️ Concerns - RESOLVED

1. **Correlation Matching** - ✅ FIXED
   - Added `normalize_key()` helper: lowercase, strip, collapse whitespace
   - Applied to both Task description and subagent prompt
   - New test `test_subagent_type_whitespace_normalization` verifies fix

2. **Empty String vs None** - ✅ FIXED
   - Changed to `block.input.get("subagent_type")` (returns `None` if missing)
   - Applied in both `get_subagents()` and `get_tool_summary()`

3. **No Debug Logging** - ✅ FIXED
   - Added `logger.debug()` for unmatched subagents
   - Shows agent_id and first 50 chars of prompt

### 💡 Priority Follow-ups

| Priority | Action | Effort | Status |
|----------|--------|--------|--------|
| High | Normalize whitespace in correlation matching | 30min | ✅ Done |
| Medium | Add debug logging for unmatched subagents | 15min | ✅ Done |
| Medium | Use None instead of empty string | 10min | ✅ Done |
| Low | Cache `task_invocations` at Session level | 1h | ⏳ Future |

### Whitespace Normalization Implementation

```python
def normalize_key(text: str) -> str:
    """Normalize text for matching: lowercase, strip, collapse whitespace."""
    return " ".join(text.lower().strip().split())

# Applied to both sides of matching
task_type_map[normalize_key(desc)] = stype
subagent_type = task_type_map.get(normalize_key(prompt_prefix), None)

# Debug logging for unmatched
if subagent_type is None and prompt_prefix:
    logger.debug(f"Subagent {subagent.agent_id} unmatched. Prompt: '{prompt_prefix[:50]}...'")
```
