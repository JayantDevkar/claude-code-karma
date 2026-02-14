# Feature: Session Title Generation

## Problem

Claude Code stopped generating session titles (`"type": "summary"` in JSONL) and updating `sessions-index.json` around **Feb 3, 2026**. This was an upstream Anthropic change. All sessions after this date have no titles in the dashboard.

### Evidence

- Last `"type": "summary"` JSONL entry: Jan 31, 2026
- Last `sessions-index.json` update: Feb 3, 2026
- Both title sources (JSONL summary messages + sessions-index.json) stopped simultaneously

## Decision: Hybrid Title Generation (Option 5)

Generate our own titles using a `SessionEnd` hook + cheap LLM call, with git context enrichment and graceful fallback.

### How It Works

```
Session ends
  → SessionEnd hook fires (captain-hook)
  → Hook reads: initial_prompt + first assistant response from JSONL
  → Hook checks: git commits made during session timeframe
  → Hook sends context to Haiku: "Generate a 5-10 word title"
  → Hook writes title to sessions-index.json (or custom title cache)
  → Fallback: truncated initial_prompt if LLM call fails
```

### Why This Approach

| Alternative Considered | Why Not |
|------------------------|---------|
| Git commit hook only | Not every session produces commits; commit messages describe changes, not sessions |
| Thinking events summary | Requires LLM anyway; thinking blocks not always available |
| First prompt as title | Low quality; prompts can be long/messy; describes ask, not outcome |
| LLM only (no git) | Misses valuable commit context that describes what actually changed |

### Cost

~$0.001 per session using Claude Haiku. Negligible even at high usage.

## Changes Required

### 1. Captain-Hook: SessionEnd Title Generator

**Location:** `captain-hook/` (new hook script or module)

- New hook handler for `SessionEnd` event
- Reads the session JSONL file to extract:
  - `initial_prompt` (first human message)
  - First assistant response (truncated)
  - Session UUID and project path
- Queries git log for commits within session timeframe
- Calls Claude Haiku API with a prompt template:
  ```
  Generate a concise 5-10 word title for this coding session.

  User asked: {initial_prompt}
  Assistant did: {first_response_summary}
  Git commits: {commit_messages}

  Title:
  ```
- Writes result to title storage

### 2. Title Storage

**Option A: Patch `sessions-index.json`** (maintain compatibility)
- Append/update entry with `{ "sessionId": "...", "summary": "..." }`
- Pro: Existing API code (`SessionIndex.load()`) works unchanged
- Con: Claude Code may overwrite or conflict with this file

**Option B: Custom title cache** (recommended)
- Write to `~/.claude_karma/cache/titles/{encoded_name}.json`
- Pro: No conflict with Claude Code files; already used by `SessionTitleCache`
- Con: Need to update the cache format to support hook-written titles

**Decision: Option B** — Write to our own title cache at `~/.claude_karma/cache/titles/`. This avoids any conflict with Claude Code's own files and integrates directly with the existing `SessionTitleCache` system.

### 3. API Changes

**`services/session_title_cache.py`:**
- Update `_build_from_sessions()` to also check for hook-generated titles
- Add method `set_title(encoded_name, uuid, title)` for the hook to call directly (via API endpoint) or for the cache to pick up from disk

**`routers/` (new endpoint):**
- `POST /sessions/{uuid}/title` — Allow the hook to push a generated title
- Also useful for manual title override from the dashboard

**`db/indexer.py`:**
- Ensure hook-generated titles flow into `session_titles` column during indexing

### 4. Frontend Changes

**Fallback display logic:**
- If `session_titles` is empty, display truncated `initial_prompt` as a dimmed/italic title
- This covers the gap for sessions where the hook hasn't run yet (historical sessions)

### 5. Backfill Script

**One-time script** to generate titles for sessions between Feb 3 and now:
- Iterate sessions with no titles in the DB
- Extract initial_prompt + first response
- Batch call Haiku for title generation
- Update title cache

## Implementation Order

1. **Frontend fallback** — Show `initial_prompt` when no title exists (immediate improvement, no backend needed)
2. **API endpoint** — `POST /sessions/{uuid}/title` for setting titles
3. **SessionEnd hook** — Captain-hook handler that generates and pushes titles
4. **Backfill script** — Generate titles for the ~2 week gap
5. **Dashboard manual edit** — Optional: let users rename sessions from the UI

## Configuration

```json
// ~/.claude_karma/config.json
{
  "title_generation": {
    "enabled": true,
    "model": "claude-haiku-4-5-20251001",
    "include_git_context": true,
    "fallback_to_prompt": true,
    "max_prompt_length": 200
  }
}
```

## Open Questions

- [ ] Should we store the generated title in the JSONL itself (append a summary message) or keep it external?
- [ ] Rate limiting: If many sessions end at once (e.g., subagents), should we debounce/batch?
- [ ] Should the backfill script also cover other projects, or just claude-karma?
