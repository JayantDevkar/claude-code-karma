# Backend Data Fetching Observations

Date: 2026-01-11
Scope: FastAPI backend (`apps/api/`) and Python models (`models/`)

---

## Observation 1: Session Detail Endpoint Iteration Count

**Location**: `apps/api/routers/sessions.py:280-335`

The `get_session()` endpoint calls the following methods sequentially:

| Line | Method Called | Underlying Iterator |
|------|---------------|---------------------|
| 290 | `session.get_usage_summary()` | `iter_assistant_messages()` |
| 291 | `session.get_tools_used()` | `iter_assistant_messages()` |
| 295-297 | Loop for `initial_prompt` | `iter_user_messages()` |
| 322 | `session.get_models_used()` | `iter_assistant_messages()` |
| 323 | `session.list_subagents()` | Glob on `subagents_dir` |
| 328 | `session.get_git_branches()` | `iter_messages()` |
| 329 | `session.get_working_directories()` | `iter_messages()` |

Each `iter_*` method opens and reads the JSONL file from disk.

---

## Observation 2: Start/End Time Computation

**Location**: `models/session.py:280-301`

```python
@property
def start_time(self) -> Optional[datetime]:
    for msg in self.iter_messages():
        return msg.timestamp  # Returns on first message
    return None

@property
def end_time(self) -> Optional[datetime]:
    last_ts = None
    for msg in self.iter_messages():
        last_ts = msg.timestamp  # Must iterate all
    return last_ts
```

`start_time` exits early on first message. `end_time` iterates through all messages. Both are properties called independently.

---

## Observation 3: Subagent Endpoint Processing

**Location**: `apps/api/routers/sessions.py:408-491`

The `get_subagents()` endpoint performs:

1. **Lines 416-418**: Iterates `session.list_subagents()` to collect agent IDs
2. **Lines 428-444**: Iterates `session.iter_messages()` to find Task tool calls with `subagent_type`
3. **Lines 448-489**: For each subagent, calls `subagent.iter_messages()` to count tools

Each subagent is a separate JSONL file in `{uuid}/subagents/agent-*.jsonl`.

---

## Observation 4: Timeline Endpoint Structure

**Location**: `apps/api/routers/sessions.py:824-952`

The `get_timeline()` endpoint:

1. **Line 839-840**: Calls `_collect_tool_results(session, subagent_info)` which iterates all messages to build a `tool_results` dict
2. **Line 846**: Iterates `session.iter_messages()` again to build timeline events, looking up results from the dict

The `_collect_tool_results` function is defined at lines 754-783.

---

## Observation 5: Analytics Aggregation Pattern

**Location**: `apps/api/routers/analytics.py:155-225`

The `_calculate_analytics_from_sessions()` function:

```python
for session in sessions:
    usage = session.get_usage_summary()  # Calls iter_assistant_messages()
    # ... accumulate usage stats

    session_tools = session.get_tools_used()  # Calls iter_assistant_messages() again
    for tool, count in session_tools.items():
        tools_used[tool] += count

    for subagent in session.list_subagents():  # Glob + load per session
        for msg in subagent.iter_messages():   # Full iteration per subagent
            if isinstance(msg, AssistantMessage):
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        tools_used[block.name] += 1
```

---

## Observation 6: Date Filtering Placement

**Location**: `apps/api/routers/analytics.py:63-79`

```python
def _filter_sessions_by_date(sessions: list, start_date, end_date):
    filtered = []
    for session in sessions:
        if not session.start_time:
            continue
        if start_date and session.start_time < start_date:
            continue
        if end_date and session.start_time > end_date:
            continue
        filtered.append(session)
    return filtered
```

This function is called at lines 120 and 150, after sessions are loaded via `project.list_sessions()`.

---

## Observation 7: Project Listing Latest Session Detection

**Location**: `apps/api/routers/projects.py:77-98`

```python
def get_latest_session_time(project: Project):
    jsonl_files = list(project.project_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None
    latest_file = max(jsonl_files, key=lambda f: f.stat().st_mtime)
    try:
        session = Session.from_path(latest_file)
        return session.start_time
    except Exception:
        return None
```

Called at line 115 in `list_projects()` for each project in the listing.

---

## Observation 8: Slug Extraction

**Location**: `models/session.py:386-400`

```python
@property
def slug(self) -> Optional[str]:
    for msg in self.iter_messages():
        if hasattr(msg, "slug") and msg.slug:
            return msg.slug
    return None
```

The slug field exists on every message in the JSONL (consistent across all messages in a session).

---

## Observation 9: Path Validation During Project Loading

**Location**: `models/project.py:82-126`

The `_extract_real_path_from_sessions()` method:

- Reads up to 5 session files (line 96: `[:5]`)
- Reads up to 50 lines per file (line 113: `[:50]`)
- Parses JSON to extract `cwd` or `workingDirectory` fields

Called during `Project.from_encoded_name()` at line 192.

---

## Observation 10: Model Layer Iterator Pattern

**Location**: `models/session.py:150-170`

```python
def iter_messages(self) -> Iterator[Message]:
    if not self.jsonl_path.exists():
        return
    with open(self.jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                yield parse_message(data)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
```

Returns a generator. File is opened and read each time the method is called. Same pattern exists in `models/agent.py:112-132`.

---

## Observation 11: Caching in Models

**Location**: `models/project.py:231-262`

Only one `@cached_property` decorator found in models:

```python
@cached_property
def git_root_path(self) -> Optional[str]:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=self.path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None
```

No `@cached_property` or `@lru_cache` decorators found on:
- `iter_messages()`
- `get_usage_summary()`
- `get_tools_used()`
- `start_time`
- `end_time`
- `slug`

---

## Observation 12: HTTP Response Headers

**Location**: All files in `apps/api/routers/`

Grep results for caching headers:

```
$ grep -r "Cache-Control\|ETag\|Last-Modified" apps/api/
(no results)
```

No HTTP caching headers are set on any endpoint responses.

---

## Observation 13: File Activity Endpoint

**Location**: `apps/api/routers/sessions.py:530-600`

The `get_file_activity()` endpoint:

1. Iterates `session.iter_messages()` to find tool calls
2. For each `ToolUseBlock`, checks if tool name is in `["Read", "Write", "Edit", "Delete", "Glob", "Grep"]`
3. Extracts file paths from tool input parameters

Subagent file activity is collected by iterating each subagent's messages separately.

---

## Observation 14: Tool Usage Endpoint

**Location**: `apps/api/routers/sessions.py:680-750`

The `get_tools()` endpoint:

1. Calls `session.get_tools_used()` for main session tools
2. Iterates each subagent via `session.list_subagents()`
3. For each subagent, iterates `subagent.iter_messages()` to count tools

Returns aggregated counts split by `by_session` and `by_subagents`.

---

## Observation 15: Frontend Caching Configuration

**Location**: `apps/web/hooks/use-session.ts`, `apps/web/hooks/use-project.ts`

TanStack Query stale times observed:

| Query | Stale Time |
|-------|------------|
| `["projects"]` | 5 minutes |
| `["project", id]` | 2 minutes |
| `["session", uuid]` | 1 minute |
| `["session-timeline", uuid]` | 1 minute |
| `["session-file-activity", uuid]` | 1 minute |

---

## Observation 16: Frozen Model Configuration

**Location**: All Pydantic models

```python
model_config = ConfigDict(frozen=True)
```

Found in:
- `models/session.py:49`
- `models/agent.py:35`
- `models/message.py:45, 78, 125`
- `models/content.py:23, 35, 47`
- `models/usage.py:31`

Frozen models cannot be mutated after creation.

---

## Observation 17: Content Block Filtering

**Location**: `models/message.py:99-120`

```python
@property
def text_content(self) -> str:
    from .content import TextBlock
    return "\n".join(
        block.text for block in self.content_blocks
        if isinstance(block, TextBlock)
    )
```

This property filters and joins content blocks on each access. No memoization.

---

## Observation 18: Tool Result Loading

**Location**: `models/tool_result.py:76-86`

```python
def read_content(self) -> Optional[str]:
    if not self.result_path.exists():
        return None
    return self.result_path.read_text(encoding="utf-8")
```

Tool result files are read fully into memory. Located at `{uuid}/tool-results/toolu_*.txt`.

---

## Observation 19: Dataset Size (Runtime)

From browser inspection of live data at localhost:3000:

| Metric | Count |
|--------|-------|
| Git Repositories | 11 |
| Non-Git Projects | 6 |
| Total Sessions | 450 |
| Total Agents | 1326 |

Largest project observed: `claude-root` with 101 sessions and 465 agents.

---

## Observation 20: API Response Sizes

Sample curl responses:

```
GET /projects                          → ~15KB (23 projects)
GET /projects/{encoded_name}           → ~8KB (includes sessions array)
GET /sessions/{uuid}                   → ~2KB (single session)
GET /sessions/{uuid}/timeline          → Variable (3 events = ~1KB, large sessions = 50KB+)
```
