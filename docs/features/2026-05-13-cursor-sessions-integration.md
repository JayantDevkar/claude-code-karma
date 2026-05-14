# Cursor Sessions Integration — Backend Feasibility Research

**Issue:** [#71](https://github.com/JayantDevkar/claude-code-karma/issues/71)
**Status:** Research only (Phase 1). No implementation.
**Branch:** `worktree-71-cursor-sessions-research`
**Date:** 2026-05-13
**Cursor version inspected:** 2.5.26 (macOS, local install)

> **⚠️ This document was superseded by a POC validation pass on 2026-05-13.**
> Some facts in §4 (parser sketches) were corrected after running the parser on real data.
> **For the validated, build-ready spec, see** [`2026-05-13-cursor-sessions-implementation-plan.md`](./2026-05-13-cursor-sessions-implementation-plan.md).
>
> Key corrections (full list in implementation plan):
> - Tool calls live at `bubble.toolFormerData` (top-level), **not** `bubble.capabilities[].data.toolFormerData`.
> - `tool` field is an integer; use sibling `name` field. Registry: see implementation plan Appendix B.
> - Per-bubble tokens are always `{inputTokens:0, outputTokens:0}` on 2.5.26 — only session-level `contextTokensUsed` is real.
> - Subagents verdict: ❌ → ⚠️ (sub-composers are full first-class entries; code path works, just no Cursor 2.4+ data yet).
> - Skills verdict: ❌ → ⚠️ Partial (listing yes, usage tracking no).
> - The `session_source` column already exists at schema v10 (PR #37). No new column needed for source discrimination.

---

## 1. TL;DR — Viability Verdict

**Verdict: PARTIAL parity is achievable. Full parity is not.**

| Category | Verdict | Notes |
|---|---|---|
| Projects + sessions list/detail | ✅ Yes | Different path encoding, different store, but parseable. |
| Conversation timeline (user/assistant/tool calls) | ✅ Yes | Richer raw data than Claude Code (thinking, token counts per bubble, dedup blobs). |
| File activity | ✅ Yes | Tool call args/results are in `bubbleId` records as plain JSON. |
| Analytics (tokens, models, modes, branches) | ✅ Yes | All fields present in `composerData`. |
| Live sessions / real-time state | ❌ No | Cursor has no hook substrate equivalent to claude-karma's. |
| Subagents | ❌ No (today) | Cursor 2.4 added Subagents but storage layout is undocumented and not surfaced on disk yet on 2.5.26. |
| Skills | ⚠️ Maybe | `~/.cursor/skills-cursor/` exists but was not inspected; needs Phase 2. |
| Plans | ✅ Yes | `~/.cursor/plans/*.plan.md` with YAML front-matter, already structured. |
| Hooks | ❌ No | Cursor has no public hook API. |
| Skills + commands usage analytics | ❌ No | No skill/command invocation surface in storage. |

**Effort estimate:** 2–3 weeks for the 5 fully-feasible endpoint families; +4–6 weeks if we want to add a Cursor-side live-state shim. Total realistic: **6–9 weeks for "Cursor support roughly equivalent to claude-karma's Claude-Code mode."**

---

## 2. Where Cursor Actually Stores Sessions (2.5.26)

Cursor inherits VS Code's storage skeleton and adds a Cursor-specific table.

### 2.1 The master chat store

**`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`** — a **2.4 GB SQLite database** on the inspected machine.

Two tables (both `key TEXT UNIQUE, value BLOB`):

| Table | Rows | Purpose |
|---|---:|---|
| `ItemTable` | 856 | App settings, registry keys, per-day stats. |
| `cursorDiskKV` | 186,318 | **All chat content** — keyed by structured prefixes. |

`cursorDiskKV` key prefixes (top 8 on this machine):

| Prefix | Rows | What it stores |
|---|---:|---|
| `agentKv:blob:<sha256>` | 85,071 | Hex-encoded JSON of raw LLM messages. Content-addressed → dedup across composers. |
| `bubbleId:<composerId>:<bubbleId>` | 70,682 | One per chat message ("bubble"). The primary parse target. |
| `checkpointId:<composerId>:<bubbleId>` | 15,780 | Workspace file checkpoint at that bubble (rewind state). |
| `codeBlockDiff:<id>` | 7,229 | Code-edit diffs. |
| `messageRequestContext:<composerId>:<requestId>` | 3,876 | Per-request context bundle. |
| `composerData:<composerId>` | **1,334** | One per conversation — **the session header**. |
| `codeBlockPartialInlineDiffFates:...` | 942 | Inline-diff acceptance state. |
| misc (`inlineDiff:*`, `patch-graph`, ...) | small | UI/edit infra. |

**Concurrency:** Cursor writes WAL (`state.vscdb-wal`, ~4.4 MB and active). A parser must open read-only with WAL-aware mode (`?mode=ro&immutable=1`) or copy the file first to avoid lock contention with the live app.

### 2.2 Workspace → conversation index

**`~/Library/Application Support/Cursor/User/workspaceStorage/<16-hex-hash>/`** — 76 dirs on this machine. Each contains:

- `workspace.json` — one line: `{"folder": "file:///Users/.../GitHub/<repo>"}`. **This is the only reliable workspace-hash → real-path lookup.**
- `state.vscdb` — per-workspace SQLite (~200 KB).
- `ItemTable['composer.composerData']` value contains `{"allComposers": [{"composerId": "...", ...}, ...]}` — **the per-project composer list.**

The 16-hex hash is VS Code's MD5-of-workspace-URI scheme (same as upstream).

### 2.3 `~/.cursor/projects/<encoded-path>/` — per-project artifacts

38 directories on this machine. Layout per project:

```
~/.cursor/projects/<encoded>/
├── agent-transcripts/<composerId>/<composerId>.jsonl   # rare — see §2.4
├── agent-tools/                                        # always empty in samples
├── terminals/                                          # always empty in samples
└── mcps/<server>/
    ├── SERVER_METADATA.json
    ├── tools/<tool_name>.json
    ├── INSTRUCTIONS.md   (optional)
    └── STATUS.md         (optional)
```

### 2.4 JSONL transcripts are a debug feature, not the primary store

Across 38 projects on this machine, **only 3 sessions out of 1,334 (0.2%)** have a JSONL transcript on disk. The official changelog markets JSONL transcripts (especially for headless mode) but the on-disk reality is that `cursorDiskKV` is the source of truth.

JSONL shape when present (community-inferred — not officially specified):
```jsonl
{"role": "user", "message": {"content": [{"type": "text", "text": "<user_query>...</user_query>"}]}}
{"role": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
```
Cursor staff confirm tool-call **outputs are deliberately excluded** from JSONL (too large) — they live in `bubbleId` records.

### 2.5 Plans

**`~/.cursor/plans/<slug>_<8-hex-id>.plan.md`** — 124 files. YAML front-matter + Markdown body:

```yaml
---
name: <title>
overview: <one-line>
todos:
  - id: create-models-dir
    content: ...
    status: completed | in_progress | pending
    dependencies: [<other-id>, ...]
---

# Title
... markdown body ...
```

Tie-back: composers reference plan IDs via `composerData.referencedPlans[]` (matches the 8-hex suffix in the filename).

### 2.6 AI-vs-human line attribution

**`~/.cursor/ai-tracking/ai-code-tracking.db`** (16 MB SQLite). Useful side-data:

- `scored_commits` (1,458 rows) — per-commit `tabLinesAdded`, `composerLinesAdded`, `humanLinesAdded`, `v1AiPercentage`, `v2AiPercentage`, `commitMessage`, `commitDate`.
- `conversation_summaries` — schema present but empty on this machine. Don't rely on it.

### 2.7 Misc small files

- `~/.cursor/ide_state.json` — current `recentlyViewedFiles[]` only.
- `~/.cursor/mcp.json` — user-level MCP server config (`chmod 600`, likely holds env-var secrets).
- `~/.cursor/skills-cursor/` — Cursor's analog to Claude skills. **Not inspected. Phase 2.**

---

## 3. Path Encoding — DIFFERENT from Claude Code

This is the #1 footgun for a port. The two products use **incompatible** encodings.

| | Claude Code | Cursor |
|---|---|---|
| Real path | `/Users/me/repo` | `/Users/me/repo` |
| Encoded form | `-Users-me-repo` | `Users-me-repo` |
| Rule | Replace every `/` with `-` (preserves leading `-`) | Drop leading `/`, then replace `/` with `-` |
| Source of truth | `cwd` field on each JSONL line | `workspace.json.folder` URI per workspace-hash dir |

**Implication:** `api/models/project.py:108-163`'s `encode_path`/`decode_path` is **not directly reusable** for Cursor. We need either:

1. A second encoder (`cursor_encode_path` / `cursor_decode_path`), OR
2. Treat the encoded dir name as an opaque display key and use `workspace.json.folder` as the canonical real-path lookup.

**Recommendation:** Option 2. Cursor's own `~/.cursor/projects/<encoded>/` is lossy (paths containing real `-` chars collide), so the workspaceStorage `folder` URI must be the source of truth anyway.

---

## 4. Data Model Mapping (Cursor → claude-karma Pydantic)

```
                    claude-karma                              Cursor
                    -----------                               ------
Project             ~/.claude/projects/<encoded>/             workspaceStorage/<hash>/workspace.json["folder"]
Session             {uuid}.jsonl                              composerData:<composerId>  (in cursorDiskKV)
Message             1 line of JSONL                           bubbleId:<composerId>:<bubbleId>
  UserMessage         type=user                                 type=1
  AssistantMessage    type=assistant                            type=2
  ToolUseBlock        in content[].type=tool_use                bubble.capabilities[].data.toolFormerData
  ToolResult          tool-results/toolu_*.txt                  bubble.capabilities[].data.toolFormerData.result (inline)
  FileHistory         type=file_history_snapshot                bubble.checkpointId → checkpointId:<...>
  CompactBoundary     type=compact                              (no equivalent — Cursor doesn't compact the same way)
  SessionTitle        type=title                                composerData.name + composerData.subtitle
Agent (subagent)    subagents/agent-*.jsonl                   composerData.subagentComposerIds[] (sub-composers in cursorDiskKV)
Todo                ~/.claude/todos/{uuid}-*.json             composerData.todos[]
Plan                (loose — /sessions/{uuid}/plan)           ~/.cursor/plans/<slug>_<8hex>.plan.md  +  composerData.referencedPlans
LiveSession        ~/.claude_karma/live-sessions/{slug}.json (NO EQUIVALENT — hook substrate absent)
ToolUsage          parsed from JSONL                         bubble.capabilities[].data.toolFormerData (richer)
ProjectAnalytics   computed from JSONLs                       composerData.{contextTokensUsed, totalLinesAdded, modelConfig.modelName, ...}
```

### 4.1 `composerData` — the session header (key fields)

```json
{
  "composerId": "e9947a5e-...",
  "createdAt": 1778607901598,        // unix ms
  "lastUpdatedAt": 1778607950369,
  "name": "Project memory for repository",
  "subtitle": "Read 2026-03-03-mcp-plan.md, plan.md, README.md",
  "unifiedMode": "agent" | "chat" | "plan" | "debug" | "edit",
  "modelConfig": {"modelName": "claude-opus-4-7-thinking-xhigh", "maxMode": false},
  "contextUsagePercent": 19.128,
  "contextTokensUsed": 57387,
  "contextTokenLimit": 300000,
  "createdOnBranch": "main",
  "isAgentic": true,
  "agentBackend": "cursor-agent",
  "fullConversationHeadersOnly": [
    {"bubbleId": "17a90108-...", "type": 1},   // 1=user
    {"bubbleId": "cec7291d-...", "type": 2}    // 2=assistant
  ],
  "subagentComposerIds": [],
  "referencedPlans": [],
  "todos": [],
  "totalLinesAdded": 0,
  "totalLinesRemoved": 0,
  "status": "completed" | "aborted" | "none",
  "blobEncryptionKey": "9vTLmmpGjX2..."         // exists but blobs are NOT encrypted on inspected machine
}
```

### 4.2 `bubbleId` — the message (key fields)

User bubbles (`type=1`): `text`, `richText`, `context`, `requestId`, `tokenCount`, `modelInfo`, `checkpointId`.

Assistant bubbles (`type=2`): `text`, `thinking.{text,type}`, `thinkingDurationMs`, `capabilityType`, `capabilities[]`.

**Tool calls** live in `bubble.capabilities[].data.toolFormerData`:
```json
{
  "toolCallId": "toolu_0166vUa8jRXvjL46Tp7h59va",
  "name": "read_file_v2",
  "status": "completed",
  "rawArgs": "{\"path\":\"/Users/.../README.md\"}",
  "params": "{\"targetFile\":\"...\",\"charsLimit\":1000000}",
  "result": "{\"contents\":\"# dev-tools\\n\\na source code repository...\"}"
}
```

Cursor stores the **full tool result inline** in `bubbleId` — richer than Claude Code's tool-results/*.txt sidecars, which require a second read. Good news for analytics.

### 4.3 `agentKv:blob:<sha256>` — raw LLM messages

Hex-encoded JSON of `{"role": "user"|"system"|"assistant", "content": "..."}`. Content-addressed for dedup (85k blobs ~890 MB on this machine). **Not strictly needed** for our parser — `bubbleId` records already carry `text`/`thinking`/`toolResults` in plain JSON.

---

## 5. Parity Matrix — Claude-Karma's 96 Endpoints

(Full enumeration; the 15 listed in `CLAUDE.md` are starred ⭐.)

### 5.1 Fully feasible ✅

| Endpoint family | Cursor source |
|---|---|
| ⭐ `GET /projects` | Union of `~/.cursor/projects/` dirs + `workspaceStorage/<hash>/workspace.json` URIs |
| ⭐ `GET /projects/{encoded_name}` | Same + `composerData[]` for session list |
| ⭐ `GET /sessions/{uuid}` (`uuid` = composerId) | `composerData:<uuid>` + `bubbleId:<uuid>:*` |
| ⭐ `GET /sessions/{uuid}/timeline` | Iterate `fullConversationHeadersOnly` |
| ⭐ `GET /sessions/{uuid}/tools` | Aggregate `bubble.capabilities[].data.toolFormerData` |
| ⭐ `GET /sessions/{uuid}/file-activity` | Filter tools to {`read_file_v2`, `edit_file`, `write_file`, ...} |
| `GET /sessions/{uuid}/initial-prompt` | First bubble with `type=1` |
| `GET /sessions/{uuid}/todos` | `composerData.todos[]` |
| `GET /sessions/all` | Union of all `composerData:*` keys |
| ⭐ `GET /analytics/projects/{encoded_name}` | Sum `contextTokensUsed`, group by `modelConfig.modelName`, `unifiedMode`, `createdOnBranch` |
| `GET /analytics/dashboard` | Aggregate across composers |
| ⭐ `GET /history` | `~/Library/Application Support/Cursor/User/History/` (VS Code's local-file-history) |
| ⭐ `GET /settings` | `~/Library/Application Support/Cursor/User/settings.json` + `keybindings.json` |
| `GET /plans/*` | Parse YAML front-matter from `~/.cursor/plans/*.plan.md` |
| `GET /tools` (MCP overview) | Walk `~/.cursor/projects/*/mcps/*` |

### 5.2 Partially feasible ⚠️

| Endpoint family | Why partial |
|---|---|
| `GET /sessions/{uuid}/tasks` | Cursor has no public task substrate — `composerData.todos[]` is shallower than claude-karma's `TaskCreate` tool history. |
| ⭐ `GET /agents` | Cursor has built-in agents (Composer, Explore, Plan, Bash) but no custom-agent system. Inventory is hard-coded, not on-disk. |
| `GET /sessions/{uuid}/relationships` + `/chain` | Cursor's `subComposerIds` / `subagentComposerIds` provide some chaining, but there's no `leaf_uuid` / slug-match concept. Mapping is lossy. |
| ⭐ `GET /plugins` | Cursor's plugin model differs from Claude Code's plugin system; partial overlap via MCP. |

### 5.3 Not feasible ❌

| Endpoint family | Why not |
|---|---|
| ⭐ `GET /live-sessions` (and all 7 live-sessions routes) | No Cursor hook substrate. State only changes when Cursor flushes `state.vscdb`. Filesystem polling would be best-effort and laggy. |
| ⭐ `GET /hooks` (and all routes) | No public hook API in Cursor. |
| ⭐ `GET /sessions/{uuid}/subagents` (and `/agents/{encoded}/{uuid}/agents/{id}/*`) | Cursor 2.4 added Subagents but storage layout is undocumented; no subagent transcripts found on disk on 2.5.26. |
| ⭐ `GET /skills` + `/commands` (and all usage routes) | Cursor doesn't expose a skills-invocation log. `~/.cursor/skills-cursor/` exists but is unparseable surface today (Phase 2 to investigate). |
| `POST /sessions/{uuid}/title` | We don't own Cursor's title field — it's auto-set by Cursor itself in `composerData.name`. |
| `POST /reindex`, `/rebuild-fts`, `/vacuum` | Admin endpoints would still apply to our own SQLite cache, just over Cursor-sourced data — feasible but not Cursor-specific. |

### 5.4 The 15 endpoints from `CLAUDE.md`

| # | Endpoint | Verdict | One-line plan |
|---|---|---|---|
| 1 | `GET /projects` | ✅ | List `workspaceStorage/*/workspace.json` folder URIs, union with `~/.cursor/projects/`. |
| 2 | `GET /projects/{encoded_name}` | ✅ | Decode via workspaceStorage lookup; list composers. |
| 3 | `GET /sessions/{uuid}` | ✅ | Read `composerData:<uuid>` + walk `fullConversationHeadersOnly`. |
| 4 | `GET /sessions/{uuid}/timeline` | ✅ | Sort bubbles by `createdAt`, emit `TimelineEvent`s. |
| 5 | `GET /sessions/{uuid}/tools` | ✅ | Aggregate `toolFormerData.name` counts per session. |
| 6 | `GET /sessions/{uuid}/file-activity` | ✅ | Filter tools to file ops + capture `path`/`result` deltas. |
| 7 | `GET /sessions/{uuid}/subagents` | ❌ | No on-disk subagent data on 2.5.26. |
| 8 | `GET /analytics/projects/{encoded_name}` | ✅ | All needed fields present in `composerData`. |
| 9 | `GET /live-sessions` | ❌ | No hook substrate. |
| 10 | `GET /agents` | ⚠️ | Show built-in Cursor agents only; no custom-agent introspection. |
| 11 | `GET /skills` | ❌ | Phase 2 — inspect `~/.cursor/skills-cursor/` before final no. |
| 12 | `GET /history` | ✅ | Read VS Code's `User/History/` entries.json + snapshots. |
| 13 | `GET /settings` | ✅ | Stream `User/settings.json` + `keybindings.json`. |
| 14 | `GET /hooks` | ❌ | Cursor has no hook API. |
| 15 | `GET /plugins` | ⚠️ | Map Cursor extensions + MCP servers; coverage incomplete. |

**Score: 8 ✅ / 2 ⚠️ / 5 ❌ on the headline 15.**

---

## 6. Architectural Recommendations

### 6.1 Add a `source` discriminator, don't fork the codebase

Introduce a `SessionSource` enum (`claude_code` | `cursor`) on the `Session` / `Project` models, and route parsing via a strategy pattern:

```python
class SessionSource(StrEnum):
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"

class SessionParser(Protocol):
    def list_projects(self) -> Iterable[Project]: ...
    def iter_messages(self, project: Project, session_id: str) -> Iterator[Message]: ...

PARSERS: dict[SessionSource, SessionParser] = {
    SessionSource.CLAUDE_CODE: ClaudeCodeParser(),
    SessionSource.CURSOR: CursorParser(),
}
```

Reuse the entire `models/`, `schemas.py`, FastAPI router layer, SQLite FTS index. Only the **filesystem-touching layer** (`models/project.py`, `models/session.py:iter_messages`, etc.) gets a Cursor-shaped sibling.

### 6.2 Two new modules under `api/`

```
api/
├── cursor/                                  # NEW
│   ├── __init__.py
│   ├── paths.py                # ~/.cursor + Application Support detection, WAL-safe sqlite open
│   ├── state_db.py             # cursorDiskKV / ItemTable readers (read-only, immutable=1)
│   ├── parser.py               # composerData / bubbleId / agentKv decoders → Message union
│   ├── plans.py                # .plan.md YAML front-matter parser
│   └── tracking.py             # ai-code-tracking.db scored_commits reader (optional analytics)
└── models/
    └── session.py              # add source: SessionSource discriminator; dispatch on it
```

### 6.3 SQLite read safety (critical)

The 2.4 GB `state.vscdb` is **actively written** by Cursor. Use:

```python
con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
```

`immutable=1` tells SQLite to **ignore the WAL**, giving us a consistent snapshot of pre-WAL state — at the cost of missing the most recent ~30s of writes. Trade-off: stale-but-stable vs. fresh-but-locked. Pick stable; we already have a 5s TTL cache pattern (`models/project.py:19-53`) for similar concerns.

### 6.4 Lazy loading still applies

The existing `Iterator[Message]` pattern (`models/jsonl_utils.py:82`, `models/session.py:677`) ports directly. Cursor's per-bubble SQLite reads are point lookups (`SELECT value FROM cursorDiskKV WHERE key=?`) — even cheaper than line-by-line JSONL.

### 6.5 Indexing

Add Cursor-source columns to `metadata.db` (currently schema v10). Suggested schema v11 (or coordinate with the existing v11 from #65 — name them v12+):

```sql
ALTER TABLE sessions ADD COLUMN source TEXT NOT NULL DEFAULT 'claude_code';
-- Composite key: (source, uuid) becomes the new identity.
CREATE INDEX idx_sessions_source_project ON sessions(source, project);
```

---

## 7. Open Questions for Phase 2

1. **`~/.cursor/skills-cursor/`** — does Cursor 2.4's Skills feature surface invocation history anywhere parseable? Worth a focused inspection.
2. **Cursor 2.4 Subagents storage** — `composerData.subagentComposerIds` is populated for some sessions; do sub-composers exist as full `composerData` entries themselves? (Likely yes, would unlock subagent parity.)
3. **`blobEncryptionKey` mystery** — field exists on every `composerData`, but `agentKv:blob:*` values are plaintext hex JSON on the inspected machine. Likely future-proofing; needs cross-machine verification before any user-facing encryption claim.
4. **Ghost Mode behavior** — Cursor's "Local / Ghost Mode" claims to disable "chat storage." Unclear whether `cursorDiskKV` writes are skipped entirely. Toggle + verify locally.
5. **Cursor 3.x compatibility** — referenced in [anthropics/claude-code#53516](https://github.com/anthropics/claude-code/issues/53516) as a supported platform. Design the parser so a `cursorDiskKV` schema bump in 3.x doesn't break us — use lenient parsing + version detection.
6. **`workspace.json` collision** — multiple workspaces can have empty `{}` (unsaved). Need a fallback: probably the workspace-hash itself as the canonical project ID, with the folder URI as a label.

---

## 8. Recommended Next Steps

If we want to ship Cursor parity:

1. **Phase 2a (1 week):** Build `api/cursor/state_db.py` + `parser.py`. Confirm we can list projects, list sessions per project, and reconstruct one full conversation timeline end-to-end from `cursorDiskKV`. **No router changes yet.**
2. **Phase 2b (1 week):** Wire a `source=cursor` branch into `models/session.py` and `routers/projects.py`. Behind a feature flag.
3. **Phase 2c (1 week):** Backfill `metadata.db` with Cursor session metadata; reuse FTS.
4. **Phase 3 (optional, 1-2 weeks):** Frontend toggle to switch source (or merged "all sources" view).
5. **Phase 4 (deferred):** Tackle subagents, skills, live-sessions only if Phase 2 shows real user demand.

If we don't ship Cursor parity but want value from this research: the **`scored_commits` table** (AI-vs-human attribution per commit) is the highest-leverage standalone surface — it gives us project-level "what % of this branch was AI-written" without needing any of the session-parsing infrastructure.

---

## Appendix A — Sample parser sketch (Python)

```python
import sqlite3, json
from pathlib import Path

HOME = Path.home()
GLOBAL_DB = HOME / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
WORKSPACE_STORAGE = HOME / "Library/Application Support/Cursor/User/workspaceStorage"

def open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)

def list_projects() -> list[dict]:
    """Each workspace-hash dir → one project entry."""
    out = []
    for ws_dir in WORKSPACE_STORAGE.iterdir():
        wj = ws_dir / "workspace.json"
        if not wj.exists():
            continue
        try:
            data = json.loads(wj.read_text())
            folder_uri = data.get("folder")
            if folder_uri:
                out.append({
                    "workspace_hash": ws_dir.name,
                    "folder_uri": folder_uri,
                    "real_path": folder_uri.removeprefix("file://"),
                })
        except json.JSONDecodeError:
            continue
    return out

def list_composers_for_workspace(workspace_hash: str) -> list[str]:
    db = WORKSPACE_STORAGE / workspace_hash / "state.vscdb"
    if not db.exists():
        return []
    with open_ro(db) as con:
        row = con.execute(
            "SELECT value FROM ItemTable WHERE key='composer.composerData'"
        ).fetchone()
        if not row:
            return []
        return [c["composerId"] for c in json.loads(row[0])["allComposers"]]

def read_composer(composer_id: str) -> dict:
    with open_ro(GLOBAL_DB) as con:
        row = con.execute(
            "SELECT value FROM cursorDiskKV WHERE key=?",
            (f"composerData:{composer_id}",),
        ).fetchone()
        return json.loads(row[0]) if row else {}

def iter_bubbles(composer_id: str):
    composer = read_composer(composer_id)
    headers = composer.get("fullConversationHeadersOnly", [])
    with open_ro(GLOBAL_DB) as con:
        for entry in headers:
            bid = entry["bubbleId"]
            row = con.execute(
                "SELECT value FROM cursorDiskKV WHERE key=?",
                (f"bubbleId:{composer_id}:{bid}",),
            ).fetchone()
            if row:
                yield {
                    "bubble_id": bid,
                    "type": entry["type"],   # 1=user, 2=assistant
                    "data": json.loads(row[0]),
                }
```

---

## Appendix B — Sources

**Local ground truth (Cursor 2.5.26, this machine):** Direct filesystem + SQLite inspection. 1,334 composers, 70,682 bubbles, 85,071 agent blobs surveyed.

**Web research:** Cursor docs ([2.0 changelog](https://cursor.com/changelog/2-0), [2.4 changelog](https://cursor.com/changelog/2-4), [data use](https://cursor.com/data-use)), forum staff replies on storage + recovery, and community parsers — most useful: [0xSero/ai-data-extraction](https://github.com/0xSero/ai-data-extraction) (explicit v2 schema), [S2thend/cursor-history](https://github.com/S2thend/cursor-history) ([CLAUDE.md schema notes](https://github.com/S2thend/cursor-history/blob/main/CLAUDE.md)), [ThreePalmTrees/Contrails](https://github.com/ThreePalmTrees/Contrails) (capabilityType codes), [vibe-replay deep dive](https://vibe-replay.com/blog/cursor-local-storage/).

**Codebase ground truth:** `api/routers/`, `api/models/`, `api/schemas.py`, `api/db/schema.py`, `captain-hook/models.py` in this worktree.
