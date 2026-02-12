# Plugins Page - Feature Plan

> **Status:** Planning
> **Created:** 2026-01-31
> **Replaces:** Hooks tab in navigation

## Executive Summary

Replace the current "Hooks" navigation tab with a comprehensive **Plugins** page that provides users visibility into their installed Claude Code plugins, what each plugin provides, and usage analytics. This shift reflects that hooks are just one component of the broader plugin system.

---

## Problem Statement

### Current State

The dashboard has a "Hooks" tab that doesn't exist as a page. This is confusing because:
1. **Hooks are a subset of plugins** - Hooks are just one of four extension types plugins can provide
2. **No plugin visibility** - Users can't see what plugins they have installed or what they provide
3. **Fragmented analytics** - Agent and skill usage is tracked but not attributed to plugins at the dashboard level
4. **API exists but no UI** - `/plugins` endpoints are already implemented but no frontend route uses them

### Two Different "Plugin" Concepts in the Codebase

| Concept | Source | Current UI |
|---------|--------|------------|
| **Plugin Installations** | `~/.claude/plugins/installed_plugins.json` | None (API exists, no UI) |
| **Plugin Skills/Agents** | Session messages with `plugin:skill` format | Skills page (grouped by plugin) |
| **Plugin Toggles** | `enabledPlugins` in `~/.claude/settings.json` | Settings page |

The plan is to unify these into a single Plugins page.

### Why "Plugins" Instead of "Hooks"

Claude Code plugins are packaging units that bundle:

| Component | Description |
|-----------|-------------|
| **Slash Commands** | Custom `/` commands for specialized workflows |
| **Subagents** | Specialized AI agents with tailored instructions |
| **MCP Servers** | External tool integrations via Model Context Protocol |
| **Hooks** | Event-driven automation (PreToolUse, SessionStart, etc.) |

A "Plugins" page encompasses all of these, while a "Hooks" page would only show one piece.

---

## User Value Proposition

### Primary Value: "What extensions do I have and how are they performing?"

Users should be able to answer:
1. **What plugins do I have installed?** - Inventory view
2. **What does each plugin provide?** - Capabilities breakdown
3. **How much am I using each plugin?** - Usage analytics
4. **Are my plugins up-to-date?** - Health/currency status

---

## Data Available

### From `~/.claude/plugins/installed_plugins.json`

```json
{
  "version": 2,
  "plugins": {
    "github@claude-plugins-official": [{
      "scope": "user",
      "installPath": "/path/to/plugin",
      "version": "e30768372b41",
      "installedAt": "2026-01-03T01:14:29.419Z",
      "lastUpdated": "2026-01-21T09:41:35.704Z"
    }]
  }
}
```

**Available fields per plugin:**
- `name` - Plugin identifier (e.g., "github@claude-plugins-official")
- `scope` - Installation scope ("user" or "project")
- `installPath` - Filesystem path to installation
- `version` - Version hash or semver
- `installedAt` - Initial installation timestamp
- `lastUpdated` - Last update timestamp

### From Plugin Cache (`~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/`)

Each plugin directory contains:

```
{plugin}/
├── plugin.json          # Plugin metadata (name, description)
├── commands/            # Slash commands (*.md files)
├── agents/              # Agent definitions (*.md files)
├── skills/              # Agent skills
├── hooks/               # Hook handlers
└── .mcp.json           # MCP server configuration
```

### From Session Data (Already Tracked)

- **Agent usage by subagent_type** - Format: `{plugin}:{agent}` (e.g., "oh-my-claudecode:executor")
- **Skill usage by skill name** - Format: `{plugin}:{skill}` (e.g., "oh-my-claudecode:autopilot")
- **Token costs** per agent invocation
- **Tool usage** breakdown

---

## Information Themes for the Page

### Theme 1: Plugin Inventory

**What the user sees:**
- List of all installed plugins
- For each: name, version, scope, install date, last update
- Marketplace source (official vs community)
- Installation count (if installed at multiple scopes)

**User value:** "I know exactly what plugins I have"

### Theme 2: Plugin Capabilities

**What the user sees per plugin:**
- Commands it provides (count + list)
- Agents it provides (count + list)
- MCP tools it provides
- Hooks it registers

**User value:** "I understand what each plugin does"

### Theme 3: Plugin Usage Analytics

**What the user sees:**
- Total agent runs from this plugin
- Total skill invocations from this plugin
- Estimated token cost attributed to plugin
- Usage trend over time
- Top agents/skills within the plugin

**User value:** "I see how much value I'm getting from each plugin"

### Theme 4: Plugin Health

**What the user sees:**
- Days since last update
- Update availability indicator (future: check marketplace)
- Agent success/error rates

**User value:** "I know if my plugins are current and healthy"

---

## Page Structure

### `/plugins` - Plugins Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│ Hero Stats Row                                                       │
│ ┌───────────┬───────────┬───────────┬───────────┐                   │
│ │ 5 Plugins │ 23 Agents │ 47 Skills │ $127.45   │                   │
│ │ Installed │ Available │ Available │ Total Cost│                   │
│ └───────────┴───────────┴───────────┴───────────┘                   │
├─────────────────────────────────────────────────────────────────────┤
│ Filter/Sort Controls                                                 │
│ [All] [Official] [Community]    Sort: [Most Used ▼]  [Search...]    │
├─────────────────────────────────────────────────────────────────────┤
│ Plugin Cards                                                         │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ oh-my-claudecode                                    [Official]  │ │
│ │ Multi-agent orchestration and productivity tools                │ │
│ │                                                                 │ │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │ │
│ │ │ 32 Agents│ │ 25 Skills│ │ 1,234    │ │ $45.67   │            │ │
│ │ │          │ │          │ │ Runs     │ │ Cost     │            │ │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘            │ │
│ │                                                                 │ │
│ │ Installed: Jan 3, 2026  •  Updated: Jan 21, 2026  •  v3.4.0    │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ github                                              [Official]  │ │
│ │ GitHub integration with PR, issue, and repo tools               │ │
│ │ ...                                                             │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### `/plugins/[plugin_name]` - Plugin Detail

```
┌─────────────────────────────────────────────────────────────────────┐
│ Breadcrumb: Plugins > oh-my-claudecode                              │
├─────────────────────────────────────────────────────────────────────┤
│ Plugin Header                                                        │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ oh-my-claudecode                                                │ │
│ │ Multi-agent orchestration and productivity tools                │ │
│ │                                                                 │ │
│ │ Version: 3.4.0  •  Scope: user  •  Updated: 3 days ago         │ │
│ └─────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│ Tabs: [Overview] [Agents] [Skills] [Usage History]                  │
├─────────────────────────────────────────────────────────────────────┤
│ Overview Tab Content                                                 │
│                                                                       │
│ ┌─── What This Plugin Provides ───────────────────────────────────┐ │
│ │                                                                 │ │
│ │  Agents (32)        Skills (25)       MCP Tools (3)             │ │
│ │  ├─ executor        ├─ autopilot      ├─ lsp_hover              │ │
│ │  ├─ architect       ├─ ultrawork      ├─ ast_grep_search        │ │
│ │  ├─ explorer        ├─ ralph          ├─ python_repl            │ │
│ │  └─ +29 more        └─ +22 more                                 │ │
│ │                                                                 │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│ ┌─── Usage Analytics ─────────────────────────────────────────────┐ │
│ │                                                                 │ │
│ │  Total Runs: 1,234    │  Est. Cost: $45.67  │  Avg/Day: 12     │ │
│ │                                                                 │ │
│ │  [Usage Chart - Last 30 Days]                                   │ │
│ │                                                                 │ │
│ │  Top Agents              Top Skills                             │ │
│ │  1. executor (456)       1. autopilot (234)                     │ │
│ │  2. architect (321)      2. ultrawork (189)                     │ │
│ │  3. explorer (198)       3. plan (145)                          │ │
│ │                                                                 │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### New Endpoints Needed

```python
# Enhanced plugin endpoints (extend existing /plugins router)

GET /plugins
    # Already exists - returns PluginsOverview
    # ENHANCE: Add usage stats aggregation

GET /plugins/{plugin_name}
    # Already exists - returns PluginDetail
    # ENHANCE: Add capabilities and usage stats

GET /plugins/{plugin_name}/capabilities
    # NEW: List agents, skills, commands, hooks in plugin
    Response: {
        "agents": ["executor", "architect", ...],
        "skills": ["autopilot", "ultrawork", ...],
        "commands": ["commit", "review", ...],
        "mcp_tools": ["lsp_hover", ...],
        "hooks": ["PreToolUse", ...]
    }

GET /plugins/{plugin_name}/usage
    # NEW: Usage analytics for this plugin
    Query params:
        - period: "day" | "week" | "month" | "all"
    Response: {
        "total_agent_runs": 1234,
        "total_skill_invocations": 567,
        "estimated_cost_usd": 45.67,
        "by_agent": {"executor": 456, "architect": 321, ...},
        "by_skill": {"autopilot": 234, ...},
        "trend": [{"date": "2026-01-30", "runs": 45}, ...]
    }

GET /plugins/stats
    # Already exists - aggregate stats
    # ENHANCE: Include usage totals
```

### Leverage Existing Data

The API already tracks:
- **Agent usage** via session parsing → attribute to plugin via `plugin:agent` format
- **Skill usage** via `GET /skills/usage` → already has `is_plugin` and `plugin` fields
- **Plugin installations** via `GET /plugins` → has install/update timestamps

---

## Implementation Phases

### Phase 1: Plugin Inventory (MVP)

**Backend:**
1. Enhance `GET /plugins` to include basic usage counts
2. Add capability scanning (list agents/skills in plugin cache)

**Frontend:**
1. Create `/plugins` route replacing hooks tab
2. Plugin cards with name, version, scope, dates
3. Basic stats (agent count, skill count)

**Effort:** Medium

### Phase 2: Plugin Capabilities

**Backend:**
1. Implement `GET /plugins/{name}/capabilities`
2. Parse plugin cache directory for agents/skills/commands

**Frontend:**
1. Create `/plugins/[name]` detail page
2. Capabilities section with expandable lists
3. Link to agent/skill detail pages

**Effort:** Medium

### Phase 3: Usage Analytics

**Backend:**
1. Implement `GET /plugins/{name}/usage`
2. Aggregate from existing session/agent/skill tracking
3. Add time-series data for trends

**Frontend:**
1. Usage stats in plugin cards
2. Usage charts on detail page
3. Top agents/skills lists

**Effort:** Medium-High

### Phase 4: Polish

- Usage trend sparklines in cards
- Cost attribution
- Days since update indicator
- Empty states for unused plugins

**Effort:** Low

---

## Navigation Changes

### Before
```
Dashboard | Projects | Agents | Skills | Analytics | History | [Hooks] | Settings
```

### After
```
Dashboard | Projects | Agents | Skills | Plugins | Analytics | History | Settings
```

The "Plugins" page becomes the natural home for:
- Plugin inventory (what's installed)
- Plugin-level analytics (roll-up of agent/skill usage)
- Eventually: plugin management (update, disable)

---

## Data Model

### PluginCapabilities (new schema)

```python
class PluginCapabilities(BaseModel):
    """What a plugin provides."""

    plugin_name: str
    agents: list[str]           # Agent names in this plugin
    skills: list[str]           # Skill names in this plugin
    commands: list[str]         # Slash commands
    mcp_tools: list[str]        # MCP tool names
    hooks: list[str]            # Hook types (PreToolUse, etc.)
```

### PluginUsageStats (new schema)

```python
class PluginUsageStats(BaseModel):
    """Usage analytics for a plugin."""

    plugin_name: str
    total_agent_runs: int
    total_skill_invocations: int
    estimated_cost_usd: float
    by_agent: dict[str, int]    # agent_name -> run count
    by_skill: dict[str, int]    # skill_name -> invocation count
    trend: list[DailyUsage]     # Time series
```

### Enhanced PluginSummary

```python
class PluginSummary(BaseModel):
    """Summary with usage stats."""

    # Existing fields
    name: str
    installation_count: int
    scopes: list[str]
    latest_version: str
    latest_update: datetime

    # New fields
    agent_count: int
    skill_count: int
    total_runs: int             # Combined agent + skill usage
    days_since_update: int
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Page load time | < 2s |
| Plugin inventory accuracy | 100% of installed plugins shown |
| Usage attribution | 95%+ agent/skill runs attributed to plugins |
| User engagement | Users visit plugins page at least weekly |

---

## Hook System Details

The captain-hook library documents **13 hook types** that plugins can register:

| Hook Type | When It Fires | Can Block? |
|-----------|---------------|------------|
| `PreToolUse` | Before a tool executes | Yes |
| `PostToolUse` | After a tool executes | No |
| `PostToolUseFailure` | When a tool fails | No |
| `UserPromptSubmit` | When user submits message | Yes |
| `SessionStart` | Session begins | No |
| `SessionEnd` | Session ends | No |
| `Stop` | Agent stops | No |
| `SubagentStart` | Subagent spawned | No |
| `SubagentStop` | Subagent completes | No |
| `PreCompact` | Before context compaction | No |
| `PermissionRequest` | Permission dialog shown | Yes |
| `Notification` | System notification | No |
| `Setup` | Initial setup | No |

**Future consideration**: Show which hooks a plugin registers and track hook event counts.

---

## Open Questions

1. **Plugin descriptions** - Can we get descriptions from marketplace or must we parse local files?
2. **Update checking** - Should we check marketplace for newer versions? (requires network)
3. **Hook visibility** - Should we show active hooks and their trigger counts?
4. **Project-scoped plugins** - How to differentiate user vs project plugins in the UI?
5. **Settings integration** - Should plugin enable/disable toggles move from Settings to Plugins page?

---

## References

- [Claude Code Plugins Documentation](https://code.claude.com/docs/en/plugins)
- [Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Agents Page Plan](../agents-page/plan.md) - Similar pattern for agent analytics
- Internal: `api/models/plugin.py`, `api/routers/plugins.py`, `api/routers/skills.py`
