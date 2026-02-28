# Hooks Page - Feature Plan

> **Status:** Planning
> **Created:** 2026-02-16
> **Last Updated:** 2026-02-16

## Executive Summary

Build a Hooks registry and awareness page in Claude Code Karma that shows users exactly what hooks are intercepting their Claude Code sessions — where they come from (manual, plugin, project), what events they fire on, which can block execution, and how they're configured. Unlike agents and skills (which have usage analytics from JSONL data), hooks are a **configuration-level feature** — the value is awareness and control, not analytics.

---

## Problem Statement

### Current Gaps

1. **Zero visibility into hooks** - Users have no way to see what hooks are active, which plugins registered them, or what they do
2. **No understanding of hook layering** - Global, project, and plugin hooks are merged silently — users don't know the execution order
3. **Mystery system-reminders** - Users see `<system-reminder>` tags injected by hooks but can't trace which hook produced them
4. **Plugin hook opacity** - Plugins register hooks silently on install — users don't know what a plugin is intercepting
5. **No hook management** - No centralized view to understand the hook landscape across all sources

### User Stories

**As a Claude Code user, I want to:**
- See all hooks that are active in my environment
- Understand which hooks fire during each phase of a session lifecycle
- Know which hooks can block my actions (PreToolUse, PermissionRequest, etc.)
- Trace a `<system-reminder>` back to the hook and plugin that produced it
- See hooks grouped by source (my hooks vs plugin hooks)

**As a plugin developer, I want to:**
- See how my plugin's hooks fit into the broader hook ecosystem
- Verify my hooks are registered correctly
- Understand potential conflicts with other plugins' hooks on the same events

---

## Research Findings

### How Claude Code Discovers Hooks

Hooks are defined in JSON settings files and merged from multiple sources:

1. **Global**: `~/.claude/settings.json` → `hooks` object
2. **Global local**: `~/.claude/settings.local.json` → `hooks` object
3. **Project**: `{project}/.claude/settings.json` → `hooks` object
4. **Project local**: `{project}/.claude/settings.local.json` → `hooks` object
5. **Plugins**: For each enabled plugin, `{installPath}/hooks/hooks.json`

**Merge behavior**: Hooks are **additive** — all matching hooks from all sources fire in order. No deduplication or conflict resolution.

**Activation**: A hook is active if it's present in the merged config. There are no enable/disable toggles — presence = active. Plugin hooks are active when their plugin is in `enabledPlugins`.

### Hook Configuration Schema

```json
{
  "hooks": {
    "HookEventName": [
      {
        "matcher": "pattern or *",
        "hooks": [
          {
            "type": "command",
            "command": "node script.js",
            "timeout": 5000
          }
        ],
        "description": "Optional description"
      }
    ]
  }
}
```

**Fields:**
- `HookEventName`: One of 11 Claude Code hook events
- `matcher`: Filter pattern — `*` for all, tool name, or regex on tool input
- `type`: Always `"command"` for executable hooks
- `command`: Shell command to execute (plugins use `${CLAUDE_PLUGIN_ROOT}` variable)
- `timeout`: Max execution time in milliseconds
- `description`: Optional human-readable description

### Hook Event Types (11 total)

| Event | Phase | Can Block? | Fires When |
|-------|-------|------------|------------|
| `SessionStart` | Session Lifecycle | No | Session begins |
| `SessionEnd` | Session Lifecycle | No | Session ends |
| `UserPromptSubmit` | User Input | Yes | User submits a message |
| `PreToolUse` | Tool Lifecycle | Yes | Before tool execution |
| `PostToolUse` | Tool Lifecycle | No | After tool success |
| `SubagentStart` | Agent Lifecycle | No | Subagent spawned |
| `SubagentStop` | Agent Lifecycle | No | Subagent completes |
| `Stop` | Agent Lifecycle | Yes (can continue) | Claude finishes response |
| `PreCompact` | Context | No | Before context compaction |
| `PermissionRequest` | Permissions | Yes | Permission dialog shown |
| `Notification` | System | No | System notification |

### Hook Input/Output Protocol

**Input**: JSON on stdin with hook event data (session_id, tool_name, tool_input, etc.)

**Output options**:
- Continue: `{"continue": true}`
- Inject context: `{"continue": true, "hookSpecificOutput": {"additionalContext": "text"}}`
- Allow (PermissionRequest): `{"hookSpecificOutput": {"decision": {"behavior": "allow"}}}`
- Deny (blocking hooks): `{"hookSpecificOutput": {"decision": {"behavior": "deny", "message": "..."}}}`
- Block stop: `{"decision": "block", "reason": "prompt text"}`

### Matcher Patterns

| Pattern | Meaning | Example |
|---------|---------|---------|
| `*` | All events of this type | Most common |
| `"Bash"` | Tool name match (PreToolUse/PostToolUse) | `"matcher": "Bash"` |
| `"ExitPlanMode"` | Specific tool (PermissionRequest) | Plan approval hook |
| Regex on input | Match tool input content | `"tool_input.command matches \"npm run dev\""` |
| `"init"` / `"maintenance"` | Special SessionStart modes | OMC setup hooks |
| *(omitted)* | Same as `*` | Fires for all |

### Active Hooks on This System (Observed 2026-02-16)

**38 total hook registrations** across 4 sources. See `research.md` for complete inventory.

### Key Difference from Agents/Skills

| Dimension | Agents | Skills | Hooks |
|-----------|--------|--------|-------|
| Data source | JSONL (tool calls) | JSONL (tool calls) | Config files (settings.json, hooks.json) |
| Has usage history | Yes (runs, tokens, cost) | Yes (invocation counts) | **No** (not logged anywhere) |
| Categorization | builtin/plugin/custom/project | plugin/custom | global/project/plugin |
| Detail page shows | Stats, charts, sessions | Stats, definition, sessions | Schema, scripts, matchers |
| Primary value | Analytics | Analytics | **Awareness & control** |

---

## Data Model

### HookRegistration

Core data structure for a single hook binding:

```
HookRegistration
├── Identity
│   ├── event_type: str              # "PreToolUse", "SessionEnd", etc.
│   ├── source_type: enum            # "global" | "project" | "plugin"
│   ├── source_name: str             # "claude-karma" | "oh-my-claudecode" | etc.
│   ├── plugin_id: str | None        # Plugin identifier if source_type == "plugin"
│   └── description: str | None      # From hooks.json description field
│
├── Configuration
│   ├── matcher: str                 # "*", "Bash", "ExitPlanMode", etc.
│   ├── command: str                 # Full command string
│   ├── script_path: str             # Resolved path to script file
│   ├── script_language: enum        # "python" | "node" | "shell" | "unknown"
│   ├── timeout_ms: int              # Timeout in milliseconds
│   └── can_block: bool              # Derived from event_type
│
└── Metadata
    ├── settings_file: str           # Which file defined this hook
    └── plugin_version: str | None   # Plugin version if applicable
```

### HookSource

Aggregated view of all hooks from one source:

```python
class HookSource:
    source_type: str          # "global" | "project" | "plugin"
    source_name: str          # Display name
    plugin_id: str | None     # If plugin
    plugin_version: str | None

    # Scripts
    scripts: list[HookScript]

    # Aggregates
    total_registrations: int
    event_types_covered: list[str]
    blocking_hooks_count: int
```

### HookScript

Individual script file:

```python
class HookScript:
    filename: str             # "live_session_tracker.py"
    full_path: str            # Resolved absolute path
    language: str             # "python" | "node" | "shell"
    source_name: str          # Which source owns it
    event_types: list[str]    # Which events it handles
    registrations: int        # How many hook bindings use it
    is_symlink: bool          # True if symlinked (global hooks often are)
    symlink_target: str | None
```

### HookEventSummary

Per-event-type aggregation:

```python
class HookEventSummary:
    event_type: str           # "PreToolUse"
    phase: str                # "Tool Lifecycle"
    can_block: bool
    description: str          # What this event does
    total_registrations: int
    sources: list[str]        # Which sources have hooks here
    registrations: list[HookRegistration]
```

---

## Page Structure

### 1. Global Hooks Overview (`/hooks`)

**Purpose:** Central hook registry showing all active hooks, their sources, and the session lifecycle.

**Components:**

```
+------------------------------------------------------------------+
| Hero Stats Row (amber gradient)                                    |
| +------------+-----------------+----------------+                  |
| | 4 Sources  | 38 Registrations| 8 Can Block   |                  |
| +------------+-----------------+----------------+                  |
+------------------------------------------------------------------+
| View Toggle                                                        |
| [Event Timeline]  [By Source]                                      |
+------------------------------------------------------------------+
| Content area (switches based on view)                              |
+------------------------------------------------------------------+
```

#### View 1: Event Timeline (default)

Vertical timeline showing the 11 hook event types in lifecycle order. Each event node expands to show all registrations that fire for it.

```
  SESSION LIFECYCLE

  o SessionStart -------------------------------- 4 hooks
  |  [claude-karma] live_session_tracker.py       5000ms
  |  [oh-my-claudecode] session-start.mjs         5ms
  |  [oh-my-claudecode] setup-init.mjs            30ms   matcher: init
  |  [everything-cc] session-start.js              --
  |
  o UserPromptSubmit  [CAN BLOCK] -------------- 3 hooks
  |  [claude-karma] live_session_tracker.py       5000ms
  |  [oh-my-claudecode] keyword-detector.mjs      5ms
  |  [oh-my-claudecode] skill-injector.mjs         3ms
  |
  TOOL LIFECYCLE

  o PreToolUse  [CAN BLOCK] -------------------- 5 hooks
  |  ...
  o PostToolUse --------------------------------- 6 hooks
  |  ...

  AGENT LIFECYCLE

  o SubagentStart ------------------------------- 2 hooks
  |  ...
  o SubagentStop -------------------------------- 2 hooks
  |  ...
  o Stop  [CAN BLOCK] -------------------------- 4 hooks
  |  ...

  CONTEXT & PERMISSIONS

  o PreCompact ---------------------------------- 2 hooks
  |  ...
  o PermissionRequest  [CAN BLOCK] ------------- 2 hooks
  |  ...
  o Notification -------------------------------- 1 hook
  |  ...

  SESSION END

  o SessionEnd ---------------------------------- 4 hooks
     ...
```

**Each hook entry shows:**
- Source color dot + source name
- Script filename (clickable)
- Timeout (as badge)
- Matcher (if not `*`)
- Language icon (Python/Node/Shell)

**Interactions:**
- Click event type name → `/hooks/[event_type]`
- Click source name → `/hooks/sources/[source_id]` or `/plugins/[name]`
- Collapse/expand event groups

#### View 2: By Source

Uses `CollapsibleGroup` pattern (matches agents/skills):

```
[Your Hooks (Global)]                    10 registrations
  live_session_tracker.py    7 events   Python   5000ms
  session_title_generator.py 1 event    Python   15000ms
  plan_approval.py           1 event    Python   30000ms

[oh-my-claudecode (Plugin)]              13 registrations
  keyword-detector.mjs       1 event    Node.js  5ms
  skill-injector.mjs         1 event    Node.js  3ms
  ...

[everything-claude-code (Plugin)]        14 registrations
  ...

[ralph-wiggum (Plugin)]                  1 registration
  stop-hook.sh               1 event    Shell    5ms
```

**Each script card** (`HookScriptCard`):
- Script filename + language icon
- Event type pills (colored badges showing which events)
- Timeout
- Source badge linking to plugin page

### 2. Hook Event Detail (`/hooks/[event_type]`)

**Purpose:** Everything about one hook event type.

**Header:**
- Event name + lifecycle phase badge
- "Can Block" badge (if applicable)
- Plain-text description of when this event fires

**Sections:**

**All Registrations** (ordered by execution):
Cards for each registration, showing source, script, matcher, timeout, command.

**Event Schema** (collapsible):
- Input fields (from captain-hook Pydantic models)
- Output format (what the hook can return)
- Example JSON payload

**Related Events:**
- Links to adjacent events in the lifecycle (e.g., PreToolUse → PostToolUse)

### 3. Hook Source Detail (`/hooks/sources/[source_id]`)

For plugins → redirect to `/plugins/[name]` with hooks focus
For global/project → dedicated page:

**Header:** Source name, type badge, registration count

**Scripts Grid:**
Cards for each script file

**Event Coverage Matrix:**
Visual grid showing which of the 11 events this source covers (filled/empty dots)

---

## URL Structure

```
/hooks                                  # Hook overview (timeline view)
/hooks?view=sources                     # Hook overview (by source)
/hooks/[event_type]                     # Event type detail
/hooks/sources/[source_id]             # Source detail (global hooks)
/plugins/[name]                        # Plugin detail (for plugin hooks)
```

---

## API Endpoints

### New Endpoints

```python
GET /hooks
    Query params:
    - project: str (optional, to include project-level hooks)
    - source: str (filter by source name)
    - event_type: str (filter by event type)
    Response: {
        sources: list[HookSource],
        event_summaries: list[HookEventSummary],
        registrations: list[HookRegistration],
        stats: {
            total_sources: int,
            total_registrations: int,
            blocking_hooks: int
        }
    }

GET /hooks/{event_type}
    Response: {
        event: HookEventSummary,
        registrations: list[HookRegistration],
        schema: {
            input_fields: list[FieldInfo],
            output_format: dict,
            example: dict
        }
    }

GET /hooks/sources/{source_id}
    Response: {
        source: HookSource,
        scripts: list[HookScript],
        coverage_matrix: dict[str, bool]  # event_type → covered
    }
```

### Data Parsing Logic

```python
def discover_hooks(project_path: str | None = None) -> list[HookRegistration]:
    """
    Parse and merge hooks from all sources.

    1. Read ~/.claude/settings.json → extract hooks + enabledPlugins
    2. Read ~/.claude/settings.local.json → merge hooks
    3. For each enabled plugin:
       a. Find {installPath}/hooks/hooks.json
       b. Parse and attribute to plugin
    4. If project_path:
       a. Read {project}/.claude/settings.json
       b. Read {project}/.claude/settings.local.json
    5. Return unified list with source attribution
    """
```

---

## Implementation Plan

### Phase 1: API - Hook Discovery (MVP)

**Backend:**
1. Create `api/models/hook.py` with Pydantic models (HookRegistration, HookSource, etc.)
2. Create `api/utils/hook_discovery.py` with settings file parsing logic
3. Create `api/routers/hooks.py` with `/hooks` and `/hooks/{event_type}` endpoints
4. Parse `~/.claude/settings.json` for global hooks and `enabledPlugins`
5. Parse plugin `hooks.json` files for each enabled plugin
6. Merge and return with source attribution
7. Add response caching (60s TTL — config files rarely change)

### Phase 2: Frontend - Hooks Page

**Frontend:**
1. Create `/hooks` route with `+page.svelte` and `+page.ts` loader
2. Build `HookTimeline` component (vertical lifecycle timeline)
3. Build `HookRegistrationCard` component (individual hook entry)
4. Build `HookScriptCard` component (for by-source view)
5. Add hero stats section (amber gradient)
6. Add `SegmentedControl` for timeline/source view toggle
7. Skeleton loader

### Phase 3: Detail Pages

1. Create `/hooks/[event_type]` route with registrations list + schema view
2. Create `/hooks/sources/[source_id]` route with scripts + coverage matrix
3. Add event schema rendering (captain-hook field definitions)
4. Cross-link to `/plugins/[name]` for plugin sources

### Phase 4: Navigation Integration

1. Add "Hooks" card to home grid
2. Add "Hooks" to persistent nav bar (between Skills and Plugins)
3. Update breadcrumb patterns
4. Add hooks to command palette search

---

## Technical Considerations

### Performance

- **Config file parsing**: Fast — small JSON files, cached aggressively
- **Plugin discovery**: Iterate `enabledPlugins` list, read each `hooks.json` — O(n) where n = plugins
- **No JSONL scanning**: Unlike agents/skills, hooks page reads config files only — instant response

### Symlink Resolution

Global hook scripts (`~/.claude/hooks/*.py`) are often symlinks. The API should:
- Detect symlinks with `os.path.islink()`
- Resolve with `os.path.realpath()`
- Report both the symlink path and target path

### Plugin Path Resolution

Plugin hooks use `${CLAUDE_PLUGIN_ROOT}` in commands. The API must:
- Read plugin install path from `installed_plugins.json`
- Expand `${CLAUDE_PLUGIN_ROOT}` to the actual cache path
- Handle version changes (cache path includes version/hash)

### Project Context

The `/hooks` endpoint optionally accepts a `project` param. When provided:
- Also reads project-level `.claude/settings.json` and `.claude/settings.local.json`
- Marks registrations as `source_type: "project"`
- Enables project-scoped hook views in the project detail page

---

## Component Reuse Map

| New Component | Based On | Key Differences |
|---|---|---|
| `HookTimeline` | New (no equivalent) | Vertical timeline with event nodes |
| `HookRegistrationCard` | `AgentUsageCard` | No stats/progress bar — shows matcher, timeout, command |
| `HookScriptCard` | `SkillUsageCard` | Language icon, event pills, timeout badge |
| `HooksPageSkeleton` | `AgentsPageSkeleton` | Same structure |
| `HookEventBadge` | `Badge` | Lifecycle phase coloring |
| `HookSchemaDocs` | Skill definition collapsible | Field table + example JSON |

### Color System

```css
/* Hook-specific colors */
--hook-amber: oklch(0.75 0.15 75);
--hook-amber-subtle: oklch(0.75 0.15 75 / 0.1);
--hook-blocking: oklch(0.7 0.2 30);
--hook-blocking-subtle: oklch(0.7 0.2 30 / 0.1);
--hook-readonly: var(--text-muted);

/* Source colors: use existing getPluginColorVars() for plugins */
/* "Your Hooks" gets a dedicated warm yellow */
```

---

## What We're NOT Building (And Why)

| Feature | Why Not |
|---------|---------|
| Hook execution analytics | No data — hooks don't log executions anywhere |
| Enable/disable toggles | Would require writing to settings files — risky, better handled by editing config |
| Hook creation UI | Complex — users should edit `.claude/settings.json` directly or use plugins |
| Real-time hook firing indicators | Would require hook-level logging infrastructure |
| Hook performance monitoring | No timing data captured |

**Future (if hook logging is added):** Activity tab with execution counts, success/failure rates, timing distributions, and per-session hook traces.

---

## Open Questions

1. **Project-scoped view** - Should project detail pages (`/projects/[slug]?tab=hooks`) show project-specific hooks?
2. **Hook source code** - Should we display the actual script source code? (read-only viewer)
3. **Conflict detection** - Should we warn when multiple hooks with different matchers fire on the same event?
4. **Hook health** - Can we detect broken hooks (missing script files, syntax errors)?

---

## References

- See `research.md` for complete system hook inventory
- See `ui-design.md` for detailed UI specifications
- Captain Hook library: `captain-hook/src/captain_hook/`
- Claude Code hook docs: Settings files define hook configuration
- Internal: `api/routers/agents.py` (pattern reference), `api/routers/skills.py` (pattern reference)
