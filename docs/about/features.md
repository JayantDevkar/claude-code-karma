# Features

## Core Features

### Session Browsing
Browse all your Claude Code sessions across all projects. See which sessions ran, how long they took, how many tokens they used, and which model ran them. Search, filter by date or project, and sort by any column.

### Conversation Playback
Read the full conversation from any session exactly as it happened. See user messages, Claude's responses, tool calls with inputs and outputs, and file modifications in chronological order.

### Timeline View
Chronological event log showing everything that happened in a session. See messages, tool calls (with success/failure status), subagent activity, and file operations step-by-step.

### Token and Cost Tracking
Every session shows token counts: input tokens, output tokens, cache reads, and cache writes. Costs are calculated based on the model. Track per-session costs and see trends across all sessions.

### File Activity
See every file that was touched during a session. Know which files were read, written, created, or modified. Useful for understanding what changed and where.

### Real-Time Session Monitoring
With hooks installed, watch active sessions as they happen. See current state (STARTING, LIVE, WAITING, STOPPED, ENDED). Know when Claude is actively processing versus waiting for your input. Sessions with no activity for 30 minutes are marked stale.

### Automatic Session Titles
Sessions get descriptive titles when they end. Titles come from git commits made during the session, or Claude Haiku generates them if no commits were made. Makes sessions easy to find in the browser.

### Subagent Tracking
See subagents (Task agents) spawned during sessions. Track which agents were created, their status, what tools they used, how long they ran, and their outcomes. Browse individual agent conversations.

## Analytics

### Project Analytics
Per-project dashboards showing charts of:
- Session count and duration over time
- Token usage trends
- Tool usage breakdown
- Cost estimates
- Most active files

### Global Analytics
Cross-project analytics comparing all projects by activity, cost, tool usage, and other metrics.

### Agent and Skill Analytics
See which subagents are spawned most often and how frequently Claude Code skills are invoked.

### MCP Tool Tracking
Discover which MCP (Model Context Protocol) tools are configured and actually used, with usage patterns across sessions.

## Dashboard Pages

| Page | What you see |
|------|---|
| **Home** | Overview of recent activity and quick stats |
| **Projects** | All your projects with session counts and recent activity |
| **Sessions** | Global session browser with search and filters |
| **Analytics** | Cross-project charts and trends |
| **Agents** | Subagent statistics and details |
| **Skills** | Skill invocation data |
| **Tools** | MCP tool discovery and usage |
| **Plans** | Plan-mode sessions (read-only browsing) |
| **Team** | Remote sessions synced from team members |
| **Members** | Team members and their sync status |
| **Hooks** | Hook status and event log |
| **History** | All file changes across all sessions |
| **Settings** | Preferences and dashboard configuration |

## Session Features

### Session Chaining
Claude Code Karma detects when a session is resumed or related to another. These sessions are linked together so you can follow a task across multiple sessions and see the full chain.

### Compaction Detection
When Claude Code runs out of context, it compacts the session by summarizing old messages. Sessions with compaction are flagged so you know the older part of the conversation has been summarized.

### Command Palette
Press Ctrl+K (Cmd+K on Mac) to open the command palette. Quickly jump to any project or session by name.

### URL State
All filters and view settings are saved in the URL. Share a link to give someone the exact view you're looking at with all filters applied.

## Cross-Team Session Sharing

### Overview
Freelancers register their projects with your team and use the CLI to auto-sync sessions. You see everything in a unified dashboard without manual commands.

### How it Works
1. You create a team
2. Freelancer joins the team by device ID
3. Freelancer registers their projects with `karma project add`
4. Freelancer runs `karma watch` to auto-sync
5. New sessions appear in your dashboard on the Teams page

### Real-Time Syncing
Sessions are synced automatically via Syncthing as they're created. No manual commands needed — just keep the watcher running.

### Read-Only Remote Sessions
View sessions synced from team members. Remote sessions are read-only in the dashboard — you can't modify them, but you can leave feedback.

### Feedback and Annotations
Leave feedback on individual sessions. Feedback syncs back to freelancers so they know what you thought of their work.

## Command-Line Tool (Karma CLI)

Manage session sync from the terminal:

```bash
karma init                           # Initialize on this machine
karma team create alpha              # Create a team
karma team add alice <device-id>     # Add a team member
karma project add app --path /work/app --team alpha
karma watch --team alpha             # Auto-sync as you work
karma status                         # Check sync status
```

See [Syncing Sessions](syncing-sessions.md) for full details.

## Syncthing Backend

Uses Syncthing for automatic, encrypted, peer-to-peer file sync. Sessions are packaged locally and synced without any extra daemon.

**Why Syncthing?**
- No extra infrastructure to manage (just start Syncthing once)
- Real-time sync (no manual pull commands)
- Works over LAN, VPN, or the internet
- Encrypted end-to-end (relays can't read data)
- Simple setup (exchange device IDs, create team, start watching)
