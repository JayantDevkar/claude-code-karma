# PR Review: hook-update-jan-2026

Branch: `hook-update-jan-2026`
Files Changed: 2 (298 additions, 25 deletions)

## Commits

| SHA | Type | Description |
|-----|------|-------------|
| `ebbc14a` | feat | Add subagent tracking to live sessions |
| `51f23d1` | style | Apply ruff formatting to live_session.py |
| `1cc694c` | docs | Add comprehensive hook configuration for subagent tracking |

## Files Modified

- `models/live_session.py` (+57 lines)
- `SETUP.md` (+242 lines)

---

## Issue Summary

| Severity | Count | Category |
|----------|-------|----------|
| HIGH | 4 | API integration gaps, race condition, missing code |
| MEDIUM | 4 | Redundancy, documentation accuracy, efficiency |

---

## HIGH Severity Issues

### 1. Schema Not Updated - API Won't Expose Subagent Data

**Location:** `schemas.py:581-616`

`LiveSessionSummary` only includes `subagent_count: Optional[int]` but NOT the rich subagent tracking data from `LiveSessionState.subagents`.

**Missing fields:**
```python
subagents: Dict[str, SubagentState]  # Full subagent details
active_subagent_count: int            # Running subagents (from hooks)
total_subagent_count: int             # Total tracked
```

**Impact:** Frontend cannot display real-time subagent details (type, status, timestamps).

---

### 2. hooks.yaml Missing SubagentStart/SubagentStop

**Location:** `scripts/hooks.yaml`

Project-level hooks config is missing `SubagentStart` and `SubagentStop` entries.

**Current:** 6 hooks (SessionStart, UserPromptSubmit, PostToolUse, Notification, Stop, SessionEnd)
**Missing:** SubagentStart, SubagentStop

**Impact:** Users following project-level hook setup will have subagent tracking silently fail.

---

### 3. Router Ignores Hook-Tracked Subagent Data

**Location:** `routers/live_sessions.py:156-158`

`state_to_summary()` takes `subagent_count` from JSONL files but ignores `state.subagents`, `state.active_subagent_count`, and `state.total_subagent_count`.

**Impact:** Subagent count is slow/delayed (JSONL parsing) instead of real-time (hooks).

---

## MEDIUM Severity Issues

### 4. Redundant Datetime Parsing (DRY Violation)

**Location:** `models/live_session.py:133, 135, 143, 147`

Pattern `datetime.fromisoformat(ts.replace("Z", "+00:00"))` repeated 4 times.

**Fix:** Extract helper function:
```python
@staticmethod
def _parse_iso_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
```

Existing examples: `batch_loader.py:160-192`, `async_session.py:139-155`

---

### 5. Documentation Claims Non-Existent API Integration

**Location:** `SETUP.md:195-220`

SETUP.md shows example JSON with full subagent details in API response, but actual `LiveSessionSummary` schema doesn't include this data.

**Fix:** Either update schema to match docs, or update docs to match reality.

---

### 6. Verbose Type Checking in Subagent Parsing

**Location:** `models/live_session.py:141-148`

Triple-nested isinstance checks:
```python
if isinstance(subagent_data, dict):
    if isinstance(subagent_data.get("started_at"), str):
        ...
```

**Fix:** Combine checks or use helper handling None/string.

---

### 7. Property Computations on Every Access

**Location:** `models/live_session.py:183, 188`

`active_subagent_count` and `total_subagent_count` iterate on every access.

**Fix:** Consider `@cached_property` since models are frozen.

---

## HIGH Severity Issues (Continued)

### 4. Race Condition in Parallel Subagent Tracking

**Location:** `scripts/live_session_tracker.py:162, 196, 253`

**Root Cause:** File writes have no locking mechanism. When parallel subagents start:

```python
# No file locking - concurrent writes overwrite each other
target_path.write_text(json.dumps(existing, indent=2))
```

**Timeline of failure (meta-test with 2 parallel review agents):**

| Time | Agent a940ee7 | Agent ac61775 | File State |
|------|---------------|---------------|------------|
| T1 | SubagentStart fires | SubagentStart fires | `{}` |
| T2 | read_existing_state() | read_existing_state() | `{}` |
| T3 | add_subagent(a940ee7) | add_subagent(ac61775) | `{}` |
| T4 | write_text() | | `{a940ee7}` |
| T5 | | write_text() | `{ac61775}` **OVERWRITES!** |

**Evidence:**
- Both agents have JSONL files (42 and 44 entries)
- Both agents have `SubagentStop` hook events
- Only `ac61775` exists in final `subagents` dict
- `a940ee7` SubagentStop at 12:51:09, `ac61775` at 12:52:49

**Fix:** Add file locking:
```python
import fcntl

def write_state_atomic(path, data):
    with open(path, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock
        # Re-read after acquiring lock (another process may have updated)
        existing = json.load(f)
        # Merge changes...
        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()
        fcntl.flock(f, fcntl.LOCK_UN)
```

---

## Verification: Subagent Tracking Works (Single Agent)

**Live test during review:** Tracked subagent showed proper state transitions:

```json
{
  "agent_id": "ac61775",
  "agent_type": "feature-dev:code-reviewer",
  "status": "completed",
  "transcript_path": "~/.claude/.../subagents/agent-ac61775.jsonl",
  "started_at": "2026-01-28T12:51:12Z",
  "completed_at": "2026-01-28T12:52:49Z"
}
```

---

## Recommended Actions

1. **Add file locking** to `live_session_tracker.py` for concurrent hook handling
2. **Add subagent fields to `LiveSessionSummary`** in `schemas.py`
3. **Add SubagentStart/SubagentStop to `hooks.yaml`**
4. **Update `state_to_summary()`** to use hook-tracked data
5. **Extract datetime parsing** to helper function
6. **Update SETUP.md** to match actual API schema
