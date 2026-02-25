# Claude Code Local Storage Research

## Executive Summary

This document details the complete local storage structure of Claude Code CLI, focusing on per-project session information stored in `~/.claude/projects/`. The research combines direct filesystem exploration with official documentation analysis.

---

## Table of Contents

1. [Global Directory Structure](#1-global-directory-structure)
2. [Projects Directory (Per-Project Sessions)](#2-projects-directory-per-project-sessions)
3. [Session JSONL Format](#3-session-jsonl-format)
4. [Supporting Directories](#4-supporting-directories)
5. [Global Files](#5-global-files)
6. [Data Extraction Possibilities](#6-data-extraction-possibilities)
7. [Useful Commands](#7-useful-commands)

---

## 1. Global Directory Structure

The `~/.claude/` directory contains all Claude Code local data:

```
~/.claude/
├── agents/                    # Custom agent definitions
├── cache/                     # Cached data (changelog, etc.)
├── debug/                     # Debug logs per session
├── decisions/                 # Project decisions storage
├── file-history/              # File backup history per session
├── history.jsonl              # Global command history
├── ide/                       # IDE integration data
├── paste-cache/               # Pasted content cache
├── plans/                     # Plan mode markdown files
├── plugins/                   # Installed plugins
├── projects/                  # **PRIMARY: Per-project session data**
├── session-env/               # Session environment data
├── settings.json              # Global user settings
├── settings.local.json        # Local permission overrides
├── shell-snapshots/           # Shell environment snapshots
├── skills/                    # Custom skills
├── stats-cache.json           # Usage statistics
├── statsig/                   # Analytics/feature flags
├── statusline-command.sh      # Custom statusline script
├── telemetry/                 # Telemetry data
└── todos/                     # Todo list persistence per session
```

---

## 2. Projects Directory (Per-Project Sessions)

### 2.1 Path Encoding

Claude Code encodes project paths by replacing `/` with `-`:

| Original Path | Encoded Directory Name |
|---------------|----------------------|
| `/Users/jayantdevkar/Documents/GitHub/claude-karma` | `-Users-jayantdevkar-Documents-GitHub-claude-karma` |
| `/home/user/projects/myapp` | `-home-user-projects-myapp` |

### 2.2 Directory Contents

Each project directory contains:

```
~/.claude/projects/-Users-jayantdevkar-Documents-GitHub-claude-karma/
├── {session-uuid}.jsonl           # Main session transcript
├── {session-uuid}/                # Session-specific folder
│   ├── tool-results/              # Large tool outputs
│   │   └── toolu_xxxxx.txt        # Individual tool result
│   └── subagents/                 # Subagent transcripts
│       └── agent-{id}.jsonl       # Subagent session
├── agent-{short-id}.jsonl         # Standalone agent sessions
└── ...
```

### 2.3 Session File Naming

- **Main sessions**: UUID format (e.g., `0074cde8-b763-45ee-be32-cfc80f965b4d.jsonl`)
- **Subagent sessions**: `agent-{7-char-hex}.jsonl` (e.g., `agent-a5793c3.jsonl`)
- **Tool results**: `toolu_{id}.txt` stored in `{session-uuid}/tool-results/`

---

## 3. Session JSONL Format

### 3.1 Entry Types

Each line in a `.jsonl` file is a JSON object with a `type` field:

| Type | Description |
|------|-------------|
| `user` | User message/input |
| `assistant` | Claude's response |
| `file-history-snapshot` | File backup checkpoint |

### 3.2 Common Fields

```json
{
  "parentUuid": "uuid-of-parent-message",
  "isSidechain": false,
  "userType": "external",
  "cwd": "/Users/.../project",
  "sessionId": "uuid",
  "version": "2.1.2",
  "gitBranch": "feature/branch-name",
  "type": "user|assistant",
  "uuid": "message-uuid",
  "timestamp": "2026-01-09T07:12:34.567Z",
  "slug": "eager-puzzling-fairy"
}
```

**Note:** The `slug` field (when present) is a human-readable **session** identifier, not message-specific. All messages in a session share the same slug.

### 3.3 User Message Structure

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": "User's prompt text or tool results"
  },
  "thinkingMetadata": {
    "level": "high",
    "disabled": false,
    "triggers": []
  },
  "todos": []
}
```

### 3.4 Assistant Message Structure

```json
{
  "type": "assistant",
  "message": {
    "model": "claude-opus-4-5-20251101",
    "id": "msg_xxxxx",
    "type": "message",
    "role": "assistant",
    "content": [
      {"type": "thinking", "thinking": "...", "signature": "..."},
      {"type": "text", "text": "..."},
      {"type": "tool_use", "id": "toolu_xxx", "name": "Read", "input": {...}}
    ],
    "stop_reason": "end_turn|tool_use",
    "usage": {
      "input_tokens": 100,
      "cache_creation_input_tokens": 50000,
      "cache_read_input_tokens": 10000,
      "output_tokens": 500,
      "service_tier": "standard"
    }
  },
  "requestId": "req_xxxxx"
}
```

### 3.5 Subagent-Specific Fields

```json
{
  "isSidechain": true,
  "agentId": "a5793c3",
  "slug": "eager-puzzling-fairy"
}
```

> **IMPORTANT (2026-01-10):** The `slug` field is the **SESSION slug** (human-readable session name), NOT unique to each agent. All messages and subagents within a session share the same slug. Use `agentId` for unique subagent identification.
>
> | Field | Scope | Purpose |
> |-------|-------|---------|
> | `slug` | Session | Human-readable session name |
> | `agentId` | Agent | Unique identifier per subagent |

### 3.6 File History Snapshot

```json
{
  "type": "file-history-snapshot",
  "messageId": "uuid",
  "snapshot": {
    "messageId": "uuid",
    "trackedFileBackups": {},
    "timestamp": "2026-01-08T13:03:26.669Z"
  },
  "isSnapshotUpdate": false
}
```

---

## 4. Supporting Directories

### 4.1 Debug Logs (`~/.claude/debug/`)

Plain text debug logs per session:
- Filename: `{session-uuid}.txt`
- Contains: Initialization logs, MCP configs, plugin loading, LSP events, permission updates

**Sample content:**
```
2026-01-08T13:02:04.118Z [DEBUG] Watching for changes in setting files...
2026-01-08T13:02:04.125Z [DEBUG] [init] configureGlobalMTLS starting
2026-01-08T13:02:04.136Z [DEBUG] Applying permission update: Adding 3 allow rule(s)...
2026-01-08T13:02:04.169Z [DEBUG] Parsed repository: JayantDevkar/claude-karma
```

### 4.2 File History (`~/.claude/file-history/`)

Per-session file backups before edits:
- Directory: `{session-uuid}/`
- Files: `{content-hash}@v{version}` (e.g., `11d6d2afde29309c@v1`)
- Contains: Full file content at time of backup

### 4.3 Todos (`~/.claude/todos/`)

Todo list state per session:
- Filename: `{session-uuid}-agent-{session-uuid}.json`
- Contains: Array of todo objects with `content`, `status`, `activeForm`

**Sample:**
```json
[
  {
    "content": "Explore codebase structure",
    "status": "completed",
    "activeForm": "Exploring codebase"
  },
  {
    "content": "Initialize feature",
    "status": "in_progress",
    "activeForm": "Initializing feature"
  }
]
```

### 4.4 Session Environment (`~/.claude/session-env/`)

Empty directories per session, used for environment isolation.

### 4.5 Shell Snapshots (`~/.claude/shell-snapshots/`)

Shell state snapshots for session restoration:
- Filename: `snapshot-{shell}-{timestamp}-{random}.sh`
- Contains: Aliases, functions, PATH, shell options

### 4.6 Plans (`~/.claude/plans/`)

Plan mode markdown files:
- Random memorable names (e.g., `agile-mixing-lightning.md`)
- Contains: Structured plans with steps, code blocks, etc.

### 4.7 Paste Cache (`~/.claude/paste-cache/`)

Cached pasted content:
- Filename: `{content-hash}.txt`
- Contains: Large pasted content for reference

---

## 5. Global Files

### 5.1 `history.jsonl`

Global command/prompt history across all projects:

```json
{
  "display": "User's prompt text",
  "pastedContents": {},
  "timestamp": 1761059868967,
  "project": "/Users/.../project-path"
}
```

### 5.2 `stats-cache.json`

Usage statistics cache:

```json
{
  "version": 1,
  "lastComputedDate": "2026-01-08",
  "dailyActivity": [
    {
      "date": "2026-01-08",
      "messageCount": 10571,
      "sessionCount": 126,
      "toolCallCount": 2929
    }
  ],
  "dailyModelTokens": [
    {
      "date": "2026-01-08",
      "tokensByModel": {
        "claude-opus-4-5-20251101": 500000,
        "claude-haiku-4-5-20251001": 100000
      }
    }
  ]
}
```

### 5.3 `settings.json`

Global user settings:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline-command.sh"
  },
  "enabledPlugins": {
    "github@claude-plugins-official": true,
    "code-review@claude-plugins-official": true
  },
  "alwaysThinkingEnabled": true
}
```

### 5.4 `settings.local.json`

Local permission overrides:

```json
{
  "permissions": {
    "allow": [
      "mcp__analyzer__analyzer_query",
      "mcp__analyzer__coderoots_query"
    ]
  }
}
```

---

## 6. Data Extraction Possibilities

### 6.1 What Can Be Extracted

| Data Type | Location | Format |
|-----------|----------|--------|
| Full conversation history | `projects/{project}/*.jsonl` | JSONL |
| Tool usage patterns | `projects/{project}/*.jsonl` | JSONL (tool_use entries) |
| Token usage per session | `projects/{project}/*.jsonl` | usage field in assistant messages |
| Model switches | `projects/{project}/*.jsonl` | model field changes |
| File edits timeline | `file-history/{session}/` | File content + timestamps |
| Debug/error logs | `debug/{session}.txt` | Plain text |
| Todo progress | `todos/{session}.json` | JSON array |
| Daily usage stats | `stats-cache.json` | JSON |
| Command history | `history.jsonl` | JSONL |
| Git branch context | Session JSONL | gitBranch field |
| Working directory | Session JSONL | cwd field |
| Subagent spawning | Session subagents folder | JSONL |
| Plan documents | `plans/*.md` | Markdown |

### 6.2 Key Metrics Derivable

1. **Session Analytics**
   - Duration (first to last timestamp)
   - Message count (user vs assistant)
   - Tool call frequency and types
   - Token consumption breakdown

2. **Code Activity**
   - Files read/edited per session
   - Edit success/failure rates
   - File backup points

3. **Model Usage**
   - Model distribution (opus/sonnet/haiku)
   - Cache hit rates
   - Token efficiency

4. **Workflow Patterns**
   - Subagent usage frequency
   - Plan mode engagement
   - Todo completion rates

---

## 7. Useful Commands

### List all sessions for a project
```bash
ls -la ~/.claude/projects/-Users-jayantdevkar-Documents-GitHub-claude-karma/*.jsonl
```

### Count messages in a session
```bash
wc -l ~/.claude/projects/{project}/{session}.jsonl
```

### Extract user messages
```bash
grep '"type":"user"' {session}.jsonl | jq -r '.message.content'
```

### Find sessions by date
```bash
find ~/.claude/projects/ -name "*.jsonl" -newermt "2026-01-01" -ls
```

### Get token usage from a session
```bash
grep '"usage"' {session}.jsonl | jq '.message.usage'
```

### Clean old sessions (>30 days)
```bash
find ~/.claude/projects/ -type f -name "*.jsonl" -mtime +30 -delete
```

### Extract tool calls
```bash
grep '"type":"tool_use"' {session}.jsonl | jq '{tool: .name, input: .input}'
```

---

## Sources

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference)
- [Claude Code Best Practices - Anthropic](https://www.anthropic.com/engineering/claude-code-best-practices)
- [claude-JSONL-browser - GitHub](https://github.com/withLinda/claude-JSONL-browser)
- [claude-code-log - GitHub](https://github.com/daaain/claude-code-log)
- [Claude Code Continue Migration Guide](https://gist.github.com/gwpl/e0b78a711b4a6b2fc4b594c9b9fa2c4c)
- [Claude Code Cheat Sheet - Shipyard](https://shipyard.build/blog/claude-code-cheat-sheet/)
- [Claude Code Complete Guide - Sid Bharath](https://www.siddharthbharath.com/claude-code-the-complete-guide/)

---

## Research Conducted

**Date:** 2026-01-09
**Method:** Direct filesystem exploration + web documentation analysis
**System:** macOS Darwin 24.5.0
**Claude Code Version:** 2.1.x
