# Features

A comprehensive overview of everything Claude Code Karma provides.

---

## Core Monitoring

### Session Browser

Browse all Claude Code sessions across every project. Filter by project, date range, session status, and more. Sessions display key metadata: duration, token count, message count, model used, and cost estimate.

### Timeline View

Chronological event stream for any session. Events include user messages, assistant responses, tool calls (with inputs and outputs), subagent spawns, file operations, and system events. Each event is timestamped and categorized.

### Conversation Viewer

Full conversation playback showing user and assistant messages in sequence. Supports markdown rendering, code blocks, and tool call visualization inline with the conversation flow.

### Token Usage and Cost Tracking

Per-session and per-project token breakdowns: input tokens, output tokens, and cache reads/writes. Cost estimates based on model pricing. Aggregate views across all sessions for trend analysis.

### File Activity Tracking

See every file that was read, written, created, or modified during a session. Includes operation type, file path, and timestamp. Useful for understanding the scope of changes made by Claude Code.

---

## Real-Time Monitoring

### Live Session Tracking

Real-time session state powered by Claude Code hooks. Sessions transition through a state machine:

```
STARTING --> LIVE --> WAITING --> STOPPED --> ENDED
                \--> STALE (no heartbeat)
```

The live sessions view shows all active sessions with their current state, project, duration, and latest activity.

### Subagent Monitoring

Track subagent (Task agent) spawning within sessions. See which agents were created, their prompts, duration, tool usage, and outcomes. Subagent conversations are individually browsable.

### Session Title Auto-Generation

Automatic title generation when sessions end. Titles are derived from git commits made during the session, or generated via Claude Haiku when no commits are available. Titles appear in the session browser for quick identification.

---

## Analytics and Insights

### Project Analytics

Per-project dashboards with charts covering:
- Session count and duration over time
- Token usage trends
- Tool usage distribution
- Most active files
- Cost breakdown by model

### Global Analytics

Cross-project analytics aggregating data across all projects. Compare projects by activity, cost, and usage patterns.

### Agent Analytics

Track subagent usage patterns: which agent types are spawned most frequently, their success rates, average duration, and token consumption.

### Skill Analytics

Monitor Claude Code skill invocations across sessions. See which skills are used, how often, and in which projects.

### Tool Usage Analytics

Detailed breakdown of tool calls: Read, Write, Edit, Bash, Glob, Grep, and all MCP tools. Per-tool metrics include call count, success rate, and average execution time.

### MCP Tools Tracking

Discover and track MCP (Model Context Protocol) tool usage. See which MCP servers are configured, which tools are invoked, and their usage patterns across sessions.

---

## Dashboard Pages

Claude Code Karma provides 12 dashboard pages:

| Page | Description |
|------|-------------|
| **Projects** | All Claude Code projects with session counts and recent activity |
| **Sessions** | Session browser with filtering, sorting, and search |
| **Analytics** | Global analytics with charts and trends |
| **Plans** | Browse plan-mode sessions and approval workflows |
| **Skills** | Skill usage tracking across sessions |
| **Agents** | Subagent analytics and browsing |
| **Tools** | MCP tool discovery and usage tracking |
| **Hooks** | Hook configuration and event monitoring |
| **Plugins** | Plugin management and MCP tool details |
| **Settings** | User preferences and configuration |
| **Archived** | Archived and completed sessions |
| **About** | Documentation and guides (this section) |

---

## Advanced Features

### Session Chains

Claude Code Karma detects and links related sessions. When a session is resumed or continued, the chain is preserved so you can follow the full history of a task across multiple sessions. Detection uses `leaf_uuid` references and project slug matching.

### Compaction Detection

Sessions that undergo context compaction (when conversation history is summarized to free up context window) are detected via the presence of `SummaryMessage` entries. Compacted sessions are flagged in the UI.

### Plan Approval Workflow

Integration with Claude Code's plan mode. When Claude Code enters plan mode and requests approval, the `plan_approval.py` hook gates execution. Plans can be reviewed and approved through the dashboard.

### Command Palette

Press `Ctrl+K` (or `Cmd+K` on macOS) to open the command palette. Quickly navigate to any project, session, or page. Supports fuzzy search.

### Keyboard Shortcuts

Navigate the dashboard efficiently with keyboard shortcuts. Available shortcuts are displayed in the command palette.

### URL State

All filters, sort orders, and view states are persisted in the URL query parameters. Copy and share a URL to give someone the exact same view — including active filters, selected project, and page state.

### SQLite Metadata Index

An optional SQLite index caches session metadata for fast queries. Instead of re-parsing JSONL files on every request, the index provides instant lookups for session lists, project summaries, and analytics aggregations.
