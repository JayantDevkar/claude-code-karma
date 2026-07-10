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
Share sessions with teammates and freelancers using peer-to-peer sync. Everyone sees relevant sessions in a unified dashboard — no manual copying, no central server.

### How it Works
1. You create a team from the `/team` page
2. Your teammate generates a **join code** from their `/sync` page
3. You paste the code to add them — devices pair automatically via Syncthing
4. You share projects with the team — each member gets a **subscription**
5. Members accept subscriptions and choose their sync direction (send, receive, or both)
6. Sessions flow automatically — new sessions appear within seconds on LAN

### Subscription Control
Every member controls what they receive. When a project is shared with a team, each member gets an **offered** subscription. They can:
- **Accept** it (and choose send-only, receive-only, or both)
- **Pause** it temporarily
- **Decline** it entirely

This means a team of 5 people sharing 10 projects can each have different preferences — no one-size-fits-all.

### Read-Only Remote Sessions
Sessions from teammates show up in your dashboard as read-only. You can browse their conversations, see tool usage, and learn from their approach — but you can't modify their data.

## Syncthing Backend

Uses Syncthing for automatic, encrypted, peer-to-peer file sync. Sessions are packaged locally and synced directly between machines.

**Why Syncthing?**
- No servers to manage — your data never touches a third party
- Real-time sync — sessions appear within seconds on the same network
- Works anywhere — LAN, VPN, or across the internet via encrypted relays
- End-to-end encrypted — even relay servers can't read your data
- Simple setup — the `/sync` page walks you through everything
