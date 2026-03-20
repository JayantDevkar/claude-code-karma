---
name: karma-search
description: Search and retrieve context from past Claude Code sessions using the karma CLI. Use this skill WHENEVER the user asks about previous work, what was done on a branch, past sessions, previous conversations, session history, or wants to recall what happened in a specific timeframe, project, or feature. Also trigger when the user references a branch name, date, or keyword in the context of past work (e.g., "what did we do on branch X", "yesterday's session", "when did we use ralph-loop"). This skill is the bridge between past session data and current context — if the user's question requires knowledge from a previous session, use this skill.
---

# Karma Search — Session Context Retrieval

Retrieve context from past Claude Code sessions using the `karma` CLI, which reads directly from the SQLite index at `~/.claude_karma/metadata.db`. No server needed.

## When to Use

- User asks about past work: "what did we do on branch X?", "what happened yesterday?"
- User references a branch, date, or feature from a previous session
- User wants to recall decisions, plans, or code changes from earlier sessions
- User asks to compare work across sessions or branches
- You need context from a previous session to inform current work

## Workflow

### Step 1: Search for relevant sessions

Extract search criteria from the user's message and run the appropriate search. Always use `--for-claude` for structured output you can analyze.

```bash
# By branch (most common — partial match works)
karma search --branch 1610 --for-claude

# By date
karma search --date 2026-03-15 --for-claude

# By keyword (full-text search in prompts and titles)
karma search --keyword "refactor auth" --for-claude

# By skill used
karma search --skill ralph-loop --for-claude

# Combine filters
karma search --branch 1610 --date 2026-03-12 --for-claude
```

**Choosing filters:** Start broad — prefer `--branch` alone over combining multiple filters. You can narrow down after seeing results. The goal is to give yourself enough context to answer the user's question, not to find one exact session.

### Step 2: Analyze the search results

Read the output and identify which sessions are relevant to the user's question. The `--for-claude` output includes:
- Session title and initial prompt
- Branch name and date
- Duration, message count, and cost
- Skills and tools used
- Full UUID (for drilling into specific sessions)

Often this metadata alone is enough to answer the user's question. If not, proceed to Step 3.

### Step 3: Get full session content (only if needed)

If the metadata doesn't provide enough detail, retrieve the cleaned conversation content for specific sessions:

```bash
karma sessions get <uuid> --content --for-claude
```

This calls `clean-session.py` internally, which strips noise (tool_use, tool_result, thinking blocks, progress records) and returns only the actual conversation text — keeping token usage efficient.

**Use partial UUIDs** — the first 8 characters are usually enough:

```bash
karma sessions get 180c170c --content --for-claude
```

### Step 4: Synthesize and respond

Combine the session context with your understanding of the user's question. Present findings in a clear, structured way. Reference specific sessions when relevant.

## Command Reference

| Command | Purpose |
|---------|---------|
| `karma search --branch <name>` | Find sessions by branch (partial match) |
| `karma search --date <YYYY-MM-DD>` | Find sessions by date |
| `karma search --keyword <text>` | Full-text search in prompts/titles |
| `karma search --skill <name>` | Find sessions that used a specific skill |
| `karma search --limit <N>` | Limit results (default: 50) |
| `karma sessions get <uuid>` | Get session metadata |
| `karma sessions get <uuid> --content` | Get metadata + cleaned conversation |
| `--for-claude` | Add to any command for structured markdown output |

## Tips

- **Start broad, narrow later.** `--branch 1610` is better than `--branch 1610 --skill X --date Y` as a first query — you might miss relevant context with overly specific filters.
- **Use `--content` sparingly.** Full conversation content can be large. Only fetch it for sessions you've identified as relevant from the search results.
- **Multiple sessions are normal.** A single feature often spans many sessions. Scan all of them for a complete picture before synthesizing.
- **Branch names are partial matches.** `--branch 1610` matches `APR-1610-feature-name`, `fix/1610-bug`, etc.
