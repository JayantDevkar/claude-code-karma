# Agents Page - Feature Plan

> **Status:** Planning
> **Created:** 2026-01-21
> **Last Updated:** 2026-01-21

## Executive Summary

Build a comprehensive Agents analytics page in Claude Code Karma that tracks all agent usage across projects and sessions. This feature enables plugin developers to test and optimize their plugins, and helps users understand their agent usage patterns and costs.

---

## Problem Statement

### Current Gaps

1. **No visibility into agent usage** - Users cannot see which agents they use most, their costs, or performance characteristics
2. **Plugin developers lack analytics** - No way to understand how plugins are being used, which agents are popular, or identify optimization opportunities
3. **No agent-level cost tracking** - Costs are only visible at session level, not broken down by agent
4. **No prompt analysis** - Cannot see how agent prompts vary or correlate with performance

### User Stories

**As a Claude Code user, I want to:**
- See which agents I use most frequently
- Understand the cost breakdown by agent
- Compare efficiency between different agents
- Track agent usage trends over time

**As a plugin developer, I want to:**
- See adoption metrics for my plugin's agents
- Analyze prompt variants and their performance
- Identify optimization opportunities (token usage, cache efficiency)
- Debug failed agent invocations
- Compare my agents against built-in alternatives

---

## Research Findings

### Agent Data Available in JSONL

When an agent is spawned via the `Task` tool, the following data is captured:

```json
{
  "name": "Task",
  "input": {
    "subagent_type": "feature-dev:code-reviewer",
    "description": "Reviews code for bugs...",
    "prompt": "You are an expert code reviewer specializing in..."
  }
}
```

### Agent Identification

| Agent Type | `subagent_type` Format | Example |
|------------|------------------------|---------|
| Built-in | `{name}` | `Explore`, `Plan`, `Bash` |
| Plugin | `{plugin}:{agent}` | `feature-dev:code-reviewer` |
| Custom (user) | `{name}` | `fetch-plane-tasks` |
| Project | `{name}` | `my-project-agent` |

**Key insight:** Plugin agents use a namespaced format (`plugin:agent`) that allows us to identify the source plugin.

### Data Sources

| Data | Location | Content |
|------|----------|---------|
| Agent invocations | Session JSONL | Task tool calls with subagent_type, prompt |
| Agent execution | `{session}/subagents/agent-{id}.jsonl` | Full conversation, tool usage, tokens |
| Installed plugins | `~/.claude/plugins/installed_plugins.json` | Plugin versions, install dates |
| Plugin agents | `~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/agents/*.md` | Agent definitions with frontmatter |
| Custom agents | `~/.claude/agents/*.md` | User-defined agent definitions |

### Agent Definition Structure

Agents are defined as Markdown files with YAML frontmatter:

```yaml
---
name: code-reviewer
description: Reviews code for bugs and security issues
tools: Read, Grep, Glob, WebFetch
model: sonnet
---

You are an expert code reviewer...
```

**Available frontmatter fields:**
- `name` - Unique identifier
- `description` - When to use this agent
- `tools` - Allowed tools (allowlist)
- `disallowedTools` - Forbidden tools (denylist)
- `model` - `sonnet`, `opus`, `haiku`, or `inherit`
- `permissionMode` - Permission handling behavior
- `skills` - Skills to preload
- `hooks` - Lifecycle hooks

---

## Data Model

### AgentUsageRecord

Core data structure for tracking agent invocations:

```
AgentUsageRecord
├── Identity
│   ├── subagent_type: str          # Raw value: "feature-dev:code-reviewer"
│   ├── plugin_source: str | None   # Extracted: "feature-dev"
│   ├── agent_name: str             # Extracted: "code-reviewer"
│   ├── agent_category: enum        # "plugin" | "builtin" | "custom" | "project"
│   └── agent_id: str               # Execution instance: "a5793c3"
│
├── Context
│   ├── project_path: str
│   ├── session_uuid: str
│   ├── parent_agent_id: str | None # If nested agent
│   ├── invoked_at: datetime
│   └── git_branch: str | None
│
├── Execution
│   ├── description: str            # From Task tool input
│   ├── prompt: str                 # Full prompt text
│   ├── prompt_hash: str            # For grouping similar prompts
│   ├── duration_seconds: float
│   ├── message_count: int
│   └── status: enum                # "completed" | "error" | "cancelled"
│
├── Costs
│   ├── input_tokens: int
│   ├── output_tokens: int
│   ├── cache_hit_tokens: int
│   ├── cache_hit_rate: float
│   ├── model: str
│   └── estimated_cost_usd: float
│
└── Activity
    ├── tools_used: dict[str, int]
    ├── files_touched: list[str]
    ├── files_created: int
    ├── files_modified: int
    └── errors_encountered: int
```

### AgentSummary

Aggregated statistics for an agent across all invocations:

```python
class AgentSummary:
    subagent_type: str
    plugin_source: Optional[str]
    agent_name: str
    agent_category: str  # "plugin" | "builtin" | "custom" | "project"

    # Aggregates
    total_runs: int
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    avg_duration_seconds: float
    avg_cost_per_run: float
    success_rate: float

    # Usage
    projects_used_in: list[str]
    top_tools: dict[str, int]
    first_used: datetime
    last_used: datetime
```

### PluginSummary

Plugin-level aggregation:

```python
class PluginSummary:
    plugin_name: str
    marketplace: str  # e.g., "claude-plugins-official"
    version: str
    installed_at: datetime

    # Agents in this plugin
    agents: list[AgentSummary]

    # Aggregates across all agents
    total_runs: int
    total_cost_usd: float
    projects_used_in: list[str]
```

---

## Page Structure

### 1. Global Agents Overview (`/agents`)

**Purpose:** High-level view of all agent usage across the system.

**Components:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ Hero Stats Row                                                       │
│ ┌───────────┬───────────┬───────────┬───────────┐                   │
│ │ 47 Agents │ 1,234 Runs│ $45.67    │ 32s Avg   │                   │
│ └───────────┴───────────┴───────────┴───────────┘                   │
├─────────────────────────────────────────────────────────────────────┤
│ Category Filter Tabs                                                 │
│ [All] [Built-in (5)] [Plugins (23)] [Custom (12)] [Project (7)]     │
├─────────────────────────────────────────────────────────────────────┤
│ Agent Cards Grid                                                     │
│ ┌─────────────────────┐ ┌─────────────────────┐                     │
│ │ feature-dev:        │ │ Explore             │                     │
│ │ code-reviewer       │ │ (built-in)          │                     │
│ │ 156 runs | $8.45    │ │ 892 runs | $7.14    │                     │
│ └─────────────────────┘ └─────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Filter by category (plugin, builtin, custom, project)
- Filter by plugin source
- Sort by runs, cost, recency
- Search by agent name

### 2. Agent Detail Page (`/agents/{subagent_type}`)

**Purpose:** Deep dive into a single agent's usage and performance.

**Tabs:**

| Tab | Content |
|-----|---------|
| Overview | Stats, charts, projects using agent |
| History | Paginated list of all invocations |
| Prompts | Prompt variants analysis |
| Performance | Duration distribution, cache efficiency |
| Compare | Side-by-side with other agents |

**Overview Tab:**
- Usage over time (line chart)
- Cost breakdown (donut chart + table)
- Tool usage distribution (horizontal bars)
- Projects using this agent (table with drill-down)

**History Tab:**
- Filterable table of invocations
- Columns: Time, Project, Duration, Tokens, Cost, Status
- Click row → Jump to session timeline

**Prompts Tab (for plugin developers):**
- Group invocations by prompt similarity (hash)
- Show prompt variants with stats
- Identify customized vs default prompts

**Performance Tab:**
- Duration distribution histogram
- Token efficiency (output/input ratio)
- Cache hit rate over time
- p50/p90/p99 latency metrics

**Compare Tab:**
- Select another agent for comparison
- Side-by-side metrics table
- Overlay charts

### 3. Plugins Page (`/plugins`)

**Purpose:** View analytics at the plugin level.

**Components:**
- List of installed plugins with aggregate stats
- Click plugin → Expand to show its agents
- Total runs, cost, projects for each plugin

### 4. Plugin Detail Page (`/plugins/{plugin_name}`)

**Purpose:** Deep dive into a specific plugin.

**Content:**
- Plugin metadata (version, marketplace, install date)
- List of agents with individual stats
- Combined usage charts
- Skills and MCP tools in the plugin

---

## URL Structure

```
/agents                                    # All agents list
/agents?category=plugin                    # Filter by category
/agents?plugin=feature-dev                 # Filter by plugin
/agents/{subagent_type}                    # Agent detail (URL-encoded)
/agents/{subagent_type}/history            # Usage history
/agents/{subagent_type}/compare            # Comparison view

/plugins                                   # All plugins
/plugins/{plugin_name}                     # Plugin detail

/projects/{name}/agents                    # Agents in project
/sessions/{uuid}/agents/{agent_id}         # Specific execution
```

---

## API Endpoints

### New Endpoints

```python
# Agent endpoints
GET /agents
    Query params:
    - category: "plugin" | "builtin" | "custom" | "project"
    - plugin: str (filter by plugin name)
    - project: str (filter by project)
    - sort: "runs" | "cost" | "last_used" | "name"
    - order: "asc" | "desc"
    Response: list[AgentSummary]

GET /agents/{subagent_type}
    Response: AgentDetail (extended AgentSummary with charts data)

GET /agents/{subagent_type}/history
    Query params:
    - page: int
    - per_page: int
    - project: str
    - status: "completed" | "error" | "cancelled"
    - date_from: datetime
    - date_to: datetime
    Response: PaginatedList[AgentInvocation]

GET /agents/{subagent_type}/prompts
    Response: list[PromptVariant]

GET /agents/compare
    Query params:
    - agents: list[str] (subagent_types to compare)
    Response: ComparisonResult

# Plugin endpoints
GET /plugins
    Response: list[PluginSummary]

GET /plugins/{plugin_name}
    Response: PluginDetail

# Analytics endpoints
GET /analytics/agents
    Response: GlobalAgentAnalytics (trends, top agents, etc.)

GET /analytics/agents/trends
    Query params:
    - period: "day" | "week" | "month"
    - metric: "runs" | "cost" | "tokens"
    Response: TimeSeriesData
```

### Enhanced Existing Endpoints

```python
GET /projects/{encoded_name}
    Add: agent_usage summary

GET /sessions/{uuid}
    Add: agents_spawned list with basic stats
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (MVP)

**Backend:**
1. Add `parse_agent_source()` utility to extract plugin/agent from subagent_type
2. Create `AgentSummary` and `AgentInvocation` schemas
3. Implement `/agents` list endpoint with basic stats
4. Implement `/agents/{subagent_type}` detail endpoint

**Frontend:**
1. Create `/agents` route with agent cards grid
2. Create `/agents/[subagent_type]` detail page
3. Add category filter pills
4. Basic stats display

**Estimated complexity:** Medium

### Phase 2: Usage History & Drill-down

**Backend:**
1. Implement `/agents/{subagent_type}/history` with pagination
2. Add filtering by project, date range, status
3. Link invocations to session timeline

**Frontend:**
1. Add History tab with filterable table
2. Click-to-navigate to session timeline
3. Add date range picker

**Estimated complexity:** Medium

### Phase 3: Plugin Grouping

**Backend:**
1. Parse `~/.claude/plugins/installed_plugins.json`
2. Create `PluginSummary` schema
3. Implement `/plugins` and `/plugins/{name}` endpoints
4. Cross-reference plugin agents with usage data

**Frontend:**
1. Create `/plugins` route
2. Create `/plugins/[name]` detail page
3. Add plugin filter to agents page

**Estimated complexity:** Medium

### Phase 4: Prompt Analysis

**Backend:**
1. Extract prompts from Task tool inputs
2. Implement prompt hashing for grouping
3. Create `/agents/{subagent_type}/prompts` endpoint
4. Calculate per-prompt-variant statistics

**Frontend:**
1. Add Prompts tab to agent detail
2. Prompt variant cards with expandable content
3. Stats comparison between variants

**Estimated complexity:** High

### Phase 5: Performance & Comparison

**Backend:**
1. Calculate percentile metrics (p50, p90, p99)
2. Implement `/agents/compare` endpoint
3. Add cache efficiency tracking over time

**Frontend:**
1. Add Performance tab with charts
2. Add Compare tab with agent selector
3. Duration histogram, cache efficiency charts

**Estimated complexity:** High

### Phase 6: Advanced Features

- Export to CSV/JSON
- Webhook integration for real-time analytics
- Plugin marketplace integration (future)
- Custom dashboards

**Estimated complexity:** High

---

## Technical Considerations

### Performance

1. **Aggregation caching** - Pre-compute agent stats periodically, cache in memory
2. **Lazy loading** - Don't scan all sessions on page load; use incremental aggregation
3. **Pagination** - All list endpoints must support pagination
4. **Indexed lookups** - Consider SQLite for agent stats if JSONL scanning becomes slow

### Data Extraction

```python
def parse_agent_source(subagent_type: str) -> tuple[str | None, str]:
    """Extract plugin source and agent name from subagent_type."""
    if ":" in subagent_type:
        plugin, agent = subagent_type.split(":", 1)
        return plugin, agent
    return None, subagent_type

def determine_agent_category(
    subagent_type: str,
    builtin_agents: set[str],
    plugin_agents: set[str],
    custom_agents: set[str]
) -> str:
    """Determine agent category based on known agent sets."""
    if ":" in subagent_type:
        return "plugin"
    if subagent_type in builtin_agents:
        return "builtin"
    if subagent_type in custom_agents:
        return "custom"
    return "project"  # Default: project-level agent
```

### Built-in Agents Reference

```python
BUILTIN_AGENTS = {
    "Explore",
    "Plan",
    "Bash",
    "general-purpose",
    "statusline-setup",
    "claude-code-guide",
}
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Page load time | < 2s for agents list |
| Data freshness | Stats updated within 1 session |
| Coverage | Track 100% of agent invocations |
| Adoption | Users view agents page weekly |

---

## Open Questions

1. **Historical data** - Should we backfill stats from existing sessions?
2. **Real-time updates** - WebSocket for live agent tracking during sessions?
3. **Privacy** - Should prompt text be stored/displayed? (may contain sensitive info)
4. **Retention** - How long to keep detailed invocation history?

---

## References

- [Claude Code Custom Subagents Docs](https://code.claude.com/docs/en/sub-agents)
- [ClaudeLog Task/Agent Tools](https://claudelog.com/mechanics/task-agent-tools/)
- Internal: `api/models/agent.py`, `api/routers/subagent_sessions.py`
