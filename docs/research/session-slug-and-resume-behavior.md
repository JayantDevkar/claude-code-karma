# Session Slug and Resume Behavior - Research Observations

**Date:** 2026-01-22
**Status:** Research / Observations Only

---

## Observed Session Files

Project: `claude-karma` (`-Users-jayantdevkar-Documents-GitHub-claude-karma`)

Four JSONL files share the slug `serene-meandering-scott`:

| UUID (short) | Full UUID | Line Count | Messages | Start Time | End Time |
|--------------|-----------|------------|----------|------------|----------|
| `1e64e33f` | `1e64e33f-92cf-4fe3-8ed5-93fc2968c85b` | 393 | 265 | 07:54:43 | 08:05:55 |
| `40a8348f` | `40a8348f-bd41-4471-99cd-b792721e8ba4` | 649 | 388 | 06:15:54 | 08:14:30 |
| `6ffdfd95` | `6ffdfd95-50a0-4828-834e-1d1f6af62ddb` | 1 | - | 06:15:54 | - |
| `b4b05d78` | `b4b05d78-bb18-43bb-8552-61b31213c16d` | 376 | - | 08:21:32 | 17:56:29 |

---

## Observation 1: Each Session File Has Its Own UUID

Each JSONL file contains messages with a consistent `sessionId` field matching the filename:

```
File: 1e64e33f-92cf-4fe3-8ed5-93fc2968c85b.jsonl
  → All 380 entries have sessionId: "1e64e33f-92cf-4fe3-8ed5-93fc2968c85b"

File: 40a8348f-bd41-4471-99cd-b792721e8ba4.jsonl
  → All 637 entries have sessionId: "40a8348f-bd41-4471-99cd-b792721e8ba4"

File: b4b05d78-bb18-43bb-8552-61b31213c16d.jsonl
  → All 368 entries have sessionId: "b4b05d78-bb18-43bb-8552-61b31213c16d"
```

---

## Observation 2: Slug Is Stored Per-Message

The `slug` field appears on individual message entries, not as file-level metadata:

```json
{
  "type": "user",
  "sessionId": "1e64e33f-92cf-4fe3-8ed5-93fc2968c85b",
  "slug": "serene-meandering-scott",
  ...
}
```

---

## Observation 3: File Structure Starts with file-history-snapshot

All session files begin with `file-history-snapshot` entries that do NOT contain slug:

```json
{
  "type": "file-history-snapshot",
  "messageId": "a189bd5f-1034-42a3-943c-0f73a84d0940",
  "snapshot": {
    "messageId": "a189bd5f-1034-42a3-943c-0f73a84d0940",
    "trackedFileBackups": {},
    "timestamp": "2026-01-22T06:15:54.685Z"
  },
  "isSnapshotUpdate": false
}
```

The slug only appears in subsequent `user`, `assistant`, and `progress` type messages.

---

## Observation 4: Message Type Distribution

```
Session 1e64e33f (393 lines):
  173 assistant
  110 progress
   79 user
   12 file-history-snapshot
   10 system
    8 queue-operation
    1 summary

Session 40a8348f (649 lines):
  249 assistant
  238 progress
  127 user
   18 queue-operation
   10 file-history-snapshot
    5 system
    2 summary

Session b4b05d78 (376 lines):
  157 assistant
  114 progress
   78 user
   10 file-history-snapshot
    8 system
    7 queue-operation
    2 summary
```

---

## Observation 5: Continuation Marker Files

Session `6ffdfd95-50a0-4828-834e-1d1f6af62ddb` has only 1 line:
- Contains only a `file-history-snapshot` entry
- Same timestamp as `40a8348f` first entry (06:15:54.685Z)
- This appears to be a "continuation marker" - a minimal file created when a session is continued elsewhere

---

## Observation 6: Summary Messages and leafUuid

**UPDATE (2026-01-23): Initial observation was incorrect.**

Summary messages in JSONL files DO contain valid `leafUuid` values that reference messages in previous sessions:

```json
{
  "type": "summary",
  "summary": "Implement Agent Usage Analytics & Agents Page V1",
  "leafUuid": "e040067f-88af-4f1e-8455-7a5c1c405473"
}
```

Verified examples from sessions with slug `serene-meandering-scott`:
- `1e64e33f.jsonl`: leafUuid: `e040067f-88af-4f1e-8455-7a5c1c405473`
- `40a8348f.jsonl`: leafUuid: `4dd557a5-84d2-401b-bf0c-bde2d842d0ff`

The `leafUuid` field references a message UUID from a PREVIOUS session that provided context. This is the **primary linking mechanism** for session chains.

**Edge cases where leafUuid may be null:**
- Interrupted sessions
- Sessions started fresh without resume
- Older Claude Code versions

---

## Observation 7: Timeline Overlap

Sessions with same slug have overlapping timestamps:

```
40a8348f: 06:15:54 ────────────────────────────────── 08:14:30
1e64e33f:          07:54:43 ──────── 08:05:55
b4b05d78:                              08:21:32 ──────────────── 17:56:29
```

Session `1e64e33f` started while `40a8348f` was still active (based on timestamps).

---

## Observation 8: API Returns Separate Entries

The `/projects/{name}` API endpoint returns these as separate sessions:

```json
{
  "uuid": "1e64e33f-92cf-4fe3-8ed5-93fc2968c85b",
  "slug": "serene-meandering-scott",
  "short_id": "1e64e33f",
  "message_count": 265
}
{
  "uuid": "40a8348f-bd41-4471-99cd-b792721e8ba4",
  "slug": "serene-meandering-scott",
  "short_id": "40a8348f",
  "message_count": 388
}
```

Each has a different `short_id` (first 8 chars of UUID).

---

## Observation 9: Fields Available in JSONL Entries

Common fields observed in message entries:

| Field | Description | Present In |
|-------|-------------|------------|
| `type` | Message type (user, assistant, progress, etc.) | All entries |
| `sessionId` | Session UUID | Most entries |
| `slug` | Human-readable session name | user, assistant, progress |
| `uuid` | Individual message UUID | Some entries |
| `parentUuid` | Parent message UUID (for threading) | Some entries |
| `timestamp` | ISO timestamp | Most entries |
| `cwd` | Current working directory | Some entries |
| `gitBranch` | Git branch name | Some entries |
| `version` | Claude Code version | Some entries |
| `isSidechain` | Whether message is from subagent | Some entries |
| `agentId` | Subagent ID if applicable | Subagent entries |

---

## Observation 10: Session Linking via leafUuid

**UPDATE (2026-01-23): leafUuid IS the linking mechanism.**

While there is no explicit `resumedFrom` or `previousSessionId` field, Claude Code uses `leafUuid` in summary messages to link sessions:

- `leafUuid` references a message UUID from the PREVIOUS session
- This appears in `SummaryMessage` entries BEFORE the first user/assistant message
- The `CompactionDetector` extracts these into `project_context_leaf_uuids`
- `SessionRelationshipResolver` uses this to build session chains

**Detection hierarchy:**
1. `leaf_uuid` (95% confidence): Direct reference in summary messages
2. `slug_match` (85% confidence): Same slug with time ordering (fallback)

---

## Raw Data Locations

- Session JSONL files: `~/.claude/projects/-Users-jayantdevkar-Documents-GitHub-claude-karma/*.jsonl`
- Live session tracking: `~/.claude_karma/live-sessions/*.json`
- Subagent files: `~/.claude/projects/{project}/{session-uuid}/subagents/agent-*.jsonl`

---

---

## Observation 11: Existing Chain Detection Mechanism

The codebase **already has** session chain detection via `SessionRelationshipResolver`:

**Detection Method:** `leaf_uuid` matching (95% confidence)

When Claude Code resumes a session, it injects `SummaryMessage` objects containing:
```json
{
  "type": "summary",
  "summary": "Previous session context...",
  "leafUuid": "abc-def-123-456"  // References last message UUID of previous session
}
```

**Key properties in Session model:**
```python
project_context_summaries: Optional[List[str]]     # Summaries from previous sessions
project_context_leaf_uuids: Optional[List[str]]    # Message UUIDs from previous sessions
```

---

## Observation 12: Chain API Endpoints Exist

| Endpoint | Description |
|----------|-------------|
| `GET /sessions/{uuid}/chain` | Full session chain (ancestors + descendants) |
| `GET /sessions/{uuid}/relationships` | Direct relationships for a session |

**Chain response structure:**
```python
SessionChain(
    current_session_uuid: str
    nodes: List[SessionChainNode]  # Tree of all related sessions
    root_uuid: str                 # Oldest ancestor
    total_sessions: int
    max_depth: int                 # Depth of inheritance tree
)
```

---

## Observation 13: Project View Does NOT Include Chain Data

The `/projects/{name}` endpoint returns sessions **without** relationship data:

```python
# routers/projects.py
def get_project(encoded_name: str) -> ProjectDetail:
    return ProjectDetail(
        sessions=[session_to_summary(s) for s in sessions]  # No chain info
    )
```

**Reason:** Chain resolution is expensive (requires scanning all sessions for UUID matching).

---

## Observation 14: Frontend Has Chain Visualization

Component `SessionChainView.svelte` exists and:
- Shows horizontal timeline with connector lines
- Displays chain depth badges
- Links nodes to session detail pages
- Only renders when `total_sessions > 1`

**Integration point:** `ConversationOverview.svelte` fetches chain on session detail mount.

---

## Observation 15: Continuation Marker Detection

Sessions are marked as "continuation markers" when:
```python
is_continuation_marker = (
    file_snapshot_count > 0 and
    user_message_count == 0 and
    assistant_message_count == 0
)
```

This matches `6ffdfd95` which has only 1 line (file-history-snapshot).

---

## Key Finding: Why Two Sessions Show Separately

**Root cause:** `/projects/{name}` doesn't fetch chain relationships for performance reasons.

**Existing solution:** Chain data is available via `/sessions/{uuid}/chain` but only fetched per-session, not in list view.

---

## Questions for Further Investigation

1. Should the project view group sessions by slug or chain?
2. Should chain relationships be precomputed/cached at project level?
3. How to handle sessions where `leafUuid` is null (no explicit linking)?
4. Performance implications of fetching chains for all sessions in project view?
5. Does the `/clear` command or context compaction affect session UUID assignment?
