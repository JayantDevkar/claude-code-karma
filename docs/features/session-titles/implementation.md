# POST /sessions/{uuid}/title Implementation

## Overview

Added a POST endpoint to set or update session titles. This endpoint is used by the SessionEnd hook and supports manual title override from the UI.

## Files Modified

### 1. `api/services/session_title_cache.py`

Added `set_title()` method to SessionTitleCache:

```python
def set_title(self, encoded_name: str, uuid: str, title: str) -> None:
    """
    Set or update a session title in the cache.

    If the session already has titles, the new title is prepended to the list.
    If the session doesn't exist in the cache, creates a new entry.
    """
```

**Behavior:**
- Prepends new title to existing titles list (most recent first)
- Skips duplicate titles (doesn't add if already present)
- Creates new cache entry if session doesn't exist
- Persists to disk at `~/.claude_karma/cache/titles/{encoded_name}.json`
- Thread-safe with per-project locking

### 2. `api/routers/sessions.py`

Added POST endpoint and request model:

```python
class SetTitleRequest(BaseModel):
    title: str

@router.post("/{uuid}/title")
def set_session_title(uuid: str, request: SetTitleRequest):
    """Set or update a session title."""
```

**Endpoint behavior:**
1. Validates session exists (404 if not found)
2. Updates SessionTitleCache
3. Updates SQLite database (if available)
4. Returns JSON: `{"status": "ok", "uuid": "...", "title": "..."}`

**Error handling:**
- 404 if session not found
- SQLite update failure is logged but doesn't fail the request (graceful degradation)

## API Usage

### Request

```bash
POST /sessions/{uuid}/title
Content-Type: application/json

{
  "title": "My Session Title"
}
```

### Response

```json
{
  "status": "ok",
  "uuid": "abc-123-def",
  "title": "My Session Title"
}
```

### Error Response

```json
{
  "detail": "Session not found"
}
```

## Testing

Created comprehensive test suite in `tests/api/test_set_session_title.py`:

- ✅ `test_set_title_success` - Basic title setting
- ✅ `test_set_title_prepends_to_existing` - Multiple titles handling
- ✅ `test_set_title_session_not_found` - 404 error handling
- ✅ `test_set_title_duplicate_not_added` - Duplicate detection
- ✅ `test_set_title_empty_string` - Edge case: empty title
- ✅ `test_set_title_special_characters` - Unicode and special chars
- ✅ `test_set_title_long_title` - Long title handling (1000 chars)

All tests passing ✅

## Integration Points

### SessionEnd Hook (captain-hook)

The hook can now call this endpoint to persist session titles:

```python
import requests

response = requests.post(
    f"http://localhost:8000/sessions/{session_uuid}/title",
    json={"title": generated_title}
)
```

### Frontend UI

The UI can use this endpoint for manual title override:

```typescript
async function setSessionTitle(uuid: string, title: string) {
  const response = await fetch(`/sessions/${uuid}/title`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  });
  return response.json();
}
```

## Cache Structure

### In-Memory (SessionTitleCache)

```python
{
  "abc-123": TitleEntry(
    titles=["New Title", "Old Title"],
    slug="feature-implementation",
    mtime=1707888000000
  )
}
```

### On-Disk (~/.claude_karma/cache/titles/{encoded_name}.json)

```json
{
  "version": 1,
  "built_at": "2024-02-14T08:00:00Z",
  "session_count": 42,
  "entries": {
    "abc-123": {
      "titles": ["New Title", "Old Title"],
      "slug": "feature-implementation",
      "mtime": 1707888000000
    }
  }
}
```

### SQLite (sessions table)

```sql
UPDATE sessions
SET session_titles = '["New Title", "Old Title"]'
WHERE uuid = 'abc-123';
```

## Performance Characteristics

- **Cache writes**: O(1) with file I/O (~10ms)
- **SQLite writes**: O(1) with index lookup (~5ms)
- **Thread-safe**: Per-project locking prevents race conditions
- **Atomic disk writes**: Temp file + rename for crash safety

## Design Decisions

### 1. Prepend vs Append
Titles are prepended (newest first) to match chronological ordering.

### 2. Duplicate Handling
Duplicates are silently skipped to avoid clutter in the titles list.

### 3. SQLite Graceful Degradation
If SQLite update fails, the request still succeeds (cache is source of truth).

### 4. No Title Validation
Accepts any string (including empty) to support edge cases and future use.

### 5. No Authentication
Local-only tool, no auth needed (same pattern as other endpoints).

## Future Enhancements

- [ ] GET /sessions/{uuid}/titles - Return all titles for a session
- [ ] DELETE /sessions/{uuid}/title - Remove a specific title
- [ ] POST /sessions/{uuid}/title/primary - Set primary display title
- [ ] Bulk title setting for multiple sessions
- [ ] Title history tracking with timestamps
