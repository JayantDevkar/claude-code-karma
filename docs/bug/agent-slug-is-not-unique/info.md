# Bug: Agent `slug` is Session-Based, Not Agent-Based

**Date Discovered:** 2026-01-10
**Status:** Confirmed
**Priority:** Medium
**Affected Components:** `models/agent.py`, `apps/api/routers/sessions.py`, `apps/api/schemas.py`

---

## Summary

The `slug` field (e.g., "eager-puzzling-fairy", "refactored-meandering-knuth") was incorrectly assumed to be a unique identifier for each agent/subagent. **In reality, `slug` is the session's human-readable name**, and all subagents spawned from a session inherit the same slug.

---

## Evidence

### Live Data Analysis

Session `b4985950-bbf2-4f1c-a38e-5216ba77d443` with slug `refactored-meandering-knuth`:

```
Session slug: refactored-meandering-knuth

Subagents (ALL share the SAME slug):
    a3c3f19: slug=refactored-meandering-knuth  ← SAME
    a549947: slug=refactored-meandering-knuth  ← SAME
    a768842: slug=refactored-meandering-knuth  ← SAME
    a7f1667: slug=refactored-meandering-knuth  ← SAME
    a81796a: slug=refactored-meandering-knuth  ← SAME
    a94d8e3: slug=refactored-meandering-knuth  ← SAME
    ad27626: slug=refactored-meandering-knuth  ← SAME
    adab47e: slug=refactored-meandering-knuth  ← SAME
```

Multiple agents with **different `agentId` values** share the **same `slug`**.

---

## Correct Understanding

| Field | Scope | Purpose | Example |
|-------|-------|---------|---------|
| `slug` | **Session** | Human-readable session name | `"refactored-meandering-knuth"` |
| `agentId` | **Agent** | Unique hex ID per subagent | `"a3c3f19"` |
| `subagent_type` | **Task invocation** | Type of agent spawned | `"Explore"`, `"Plan"`, custom agent name |

### Key Insight

- **`slug`** identifies the **session** (conversation), not the agent
- **`agentId`** is the **unique identifier** for each subagent within a session
- When displaying/identifying agents, use `agentId`, not `slug`

---

## Affected Code

### 1. `models/agent.py:48`

**Current (incorrect):**
```python
slug: Optional[str] = Field(default=None, description="Human-readable agent slug")
```

**Fix:**
```python
slug: Optional[str] = Field(
    default=None,
    description="Session slug (human-readable session name, inherited from parent session)"
)
```

### 2. `apps/api/routers/sessions.py:390`

**Current (problematic):**
```python
actor = subagent.slug or subagent.agent_id
```

This doesn't differentiate agents since they all share the same slug.

**Fix:**
```python
actor = subagent.agent_id  # Always use agent_id for unique identification
```

### 3. `apps/api/routers/sessions.py:374`

**Current:**
```python
actor = msg.slug or msg.agent_id or "unknown-subagent"
```

**Fix:**
```python
actor = msg.agent_id or "unknown-subagent"
```

### 4. `apps/api/schemas.py` - `FileActivity` and `SubagentSummary`

Update docstrings to clarify:
- `actor` should be `agentId`, not slug
- `slug` is optional session context, not agent identifier

---

## Implementation Plan

### Phase 1: Update Actor Identification (High Priority)

1. **`apps/api/routers/sessions.py`**
   - Change all `actor = subagent.slug or subagent.agent_id` to `actor = subagent.agent_id`
   - Update timeline event actors to use `agentId`

2. **Files to modify:**
   - `apps/api/routers/sessions.py:374` - `get_file_activity()`
   - `apps/api/routers/sessions.py:390` - `get_file_activity()` subagent loop
   - `apps/api/routers/sessions.py:446` - `get_subagents()`
   - `apps/api/routers/sessions.py:846-848` - `get_timeline()` actor determination

### Phase 2: Add Session Slug to Session Model (Medium Priority)

1. **`models/session.py`** - Add `slug` property:

```python
@property
def slug(self) -> Optional[str]:
    """
    Get the session's human-readable slug.

    The slug is stored in message entries and is consistent across
    all messages in a session.

    Returns:
        Session slug (e.g., "refactored-meandering-knuth") or None
    """
    for msg in self.iter_messages():
        if hasattr(msg, 'slug') and msg.slug:
            return msg.slug
    return None
```

2. **`apps/api/schemas.py`** - Add to `SessionSummary`:

```python
slug: Optional[str] = Field(
    None,
    description="Human-readable session name (e.g., 'eager-puzzling-fairy')"
)
```

### Phase 3: Update Documentation (Low Priority)

1. Update `models/agent.py` docstrings
2. Update `apps/api/schemas.py` docstrings
3. Update research documents (see below)

---

## API Response Changes

### Before (incorrect actor identification)

```json
{
  "agent_id": "a3c3f19",
  "slug": "refactored-meandering-knuth",
  "actor": "refactored-meandering-knuth"  // All agents show same actor!
}
```

### After (correct actor identification)

```json
{
  "agent_id": "a3c3f19",
  "slug": "refactored-meandering-knuth",
  "actor": "a3c3f19"  // Unique per agent
}
```

---

## Test Cases to Add

```python
class TestSlugIsSessionBased:
    """Verify slug is session-based, not agent-based."""

    def test_multiple_subagents_share_session_slug(self, session_with_subagents):
        """All subagents from same session should have same slug."""
        subagents = session_with_subagents.list_subagents()
        slugs = [sa.slug for sa in subagents if sa.slug]

        # All non-None slugs should be identical (session slug)
        if slugs:
            assert len(set(slugs)) == 1, "Subagents should share session slug"

    def test_agent_id_is_unique_per_subagent(self, session_with_subagents):
        """Each subagent should have unique agentId."""
        subagents = session_with_subagents.list_subagents()
        agent_ids = [sa.agent_id for sa in subagents]

        assert len(agent_ids) == len(set(agent_ids)), "agentIds must be unique"
```

---

## References

- Original research: `research/tracking_custom_agents_and_skills/research.md`
- Storage format: `docs/claude-code-local-storage-research.md`
- Live data location: `~/.claude/projects/{project}/{session-uuid}/subagents/`
