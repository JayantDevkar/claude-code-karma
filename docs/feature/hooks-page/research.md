# Hooks Page - Research & System Observations

> **Date:** 2026-02-16
> **System:** macOS (Darwin 24.5.0)
> **Claude Code Version:** Current (with hooks support)

## Complete Hook Inventory (This Machine)

### Source 1: claude-karma (Global/Manual)

**Config file:** `~/.claude/settings.json` → `hooks` object

**Hook scripts** (in `~/.claude/hooks/`, all symlinked):

| Script | Symlink Target | Language |
|--------|---------------|----------|
| `live_session_tracker.py` | `→ ~/Documents/GitHub/claude-karma/hooks/live_session_tracker.py` | Python 3 |
| `session_title_generator.py` | `→ ~/Documents/GitHub/claude-karma/hooks/session_title_generator.py` | Python 3 |
| `plan_approval.py` | `→ ~/Documents/GitHub/claude-karma/hooks/plan_approval.py` | Python 3 |

**Registrations (10):**

| # | Event Type | Matcher | Script | Timeout |
|---|-----------|---------|--------|---------|
| 1 | `SessionStart` | `*` | `live_session_tracker.py` | 5000ms |
| 2 | `PostToolUse` | `*` | `live_session_tracker.py` | 5000ms |
| 3 | `Notification` | `*` | `live_session_tracker.py` | 5000ms |
| 4 | `Stop` | `*` | `live_session_tracker.py` | 5000ms |
| 5 | `SessionEnd` | `*` | `live_session_tracker.py` | 5000ms |
| 6 | `SessionEnd` | `*` | `session_title_generator.py` | 15000ms |
| 7 | `UserPromptSubmit` | `*` | `live_session_tracker.py` | 5000ms |
| 8 | `SubagentStart` | `*` | `live_session_tracker.py` | 5000ms |
| 9 | `SubagentStop` | `*` | `live_session_tracker.py` | 5000ms |
| 10 | `PermissionRequest` | `ExitPlanMode` | `plan_approval.py` | 30000ms |

**What they do:**

1. **`live_session_tracker.py`** (7 events)
   - Tracks real-time session state for the Claude Code Karma dashboard
   - Writes to: `~/.claude_karma/live-sessions/{slug}.json`
   - State machine: STARTING → LIVE → WAITING/STOPPED/STALE → ENDED
   - Tracks subagent lifecycle (start/complete times, status)
   - Captures: session_id, cwd, transcript_path, permission_mode

2. **`session_title_generator.py`** (1 event: SessionEnd)
   - Generates human-readable session titles
   - Strategy: Uses recent git commits (free) or Claude Haiku API (fallback)
   - Posts result to: `POST http://localhost:8000/sessions/{uuid}/title`
   - Timeout: 15s (needs API call time)

3. **`plan_approval.py`** (1 event: PermissionRequest, matcher: ExitPlanMode)
   - Intercepts ExitPlanMode permission requests
   - Queries: `GET http://localhost:8000/plans/{slug}/status`
   - Allows if plan is approved, denies if not
   - Timeout: 30s (longest — waits for plan approval)

---

### Source 2: oh-my-claudecode (Plugin)

**Plugin location:** `~/.claude/plugins/cache/omc/oh-my-claudecode/3.9.9/`
**Hooks config:** `hooks/hooks.json`
**Scripts directory:** `scripts/`

**Registrations (13):**

| # | Event Type | Matcher | Script | Timeout | Purpose |
|---|-----------|---------|--------|---------|---------|
| 1 | `UserPromptSubmit` | `*` | `keyword-detector.mjs` | 5ms | Detect magic keywords (autopilot, ralph, ulw, eco) |
| 2 | `UserPromptSubmit` | `*` | `skill-injector.mjs` | 3ms | Auto-inject learned skills matching prompt |
| 3 | `SessionStart` | `*` | `session-start.mjs` | 5ms | Restore persistent mode states |
| 4 | `SessionStart` | `init` | `setup-init.mjs` | 30ms | First-time setup wizard |
| 5 | `SessionStart` | `maintenance` | `setup-maintenance.mjs` | 60ms | Maintenance tasks |
| 6 | `PreToolUse` | `*` | `pre-tool-enforcer.mjs` | 3ms | Inject Sisyphus task reminders, enforce delegation |
| 7 | `PermissionRequest` | `Bash` | `permission-handler.mjs` | 5ms | Handle Bash permission dialogs |
| 8 | `PostToolUse` | `*` | `post-tool-verifier.mjs` | 3ms | Verification reminders, `<remember>` tag processing |
| 9 | `SubagentStart` | `*` | `subagent-tracker.mjs start` | 3ms | Track agent spawning |
| 10 | `SubagentStop` | `*` | `subagent-tracker.mjs stop` | 5ms | Track agent completion |
| 11 | `PreCompact` | `*` | `pre-compact.mjs` | 10ms | Save state before context compaction |
| 12 | `Stop` | `*` | `persistent-mode.cjs` | 5ms | Ralph-loop persistence (block stop if active) |
| 13 | `SessionEnd` | `*` | `session-end.mjs` | 10ms | Clean up session state |

**Notable behaviors:**
- `keyword-detector.mjs` creates state files at `.omc/state/{mode}-state.json`
- `skill-injector.mjs` searches `.omc/skills/` and `~/.claude/skills/omc-learned/`, injects up to 5 per session
- `pre-tool-enforcer.mjs` reads todo state from `.omc/todos.json` and `~/.claude/todos/*.json`
- `post-tool-verifier.mjs` processes `<remember>` tags, writes to `.omc/notepad.md`
- `persistent-mode.cjs` uses CommonJS (not ESM) — handles ralph-loop stop blocking

---

### Source 3: everything-claude-code (Plugin)

**Plugin location:** `~/.claude/plugins/cache/everything-claude-code/everything-claude-code/660e0d3badd3/`
**Hooks config:** `hooks/hooks.json`

**Registrations (14):**

| # | Event Type | Matcher | Purpose |
|---|-----------|---------|---------|
| 1 | `PreToolUse` | `Bash` + npm/yarn/pnpm dev | Block dev servers outside tmux |
| 2 | `PreToolUse` | `Bash` + npm install/cargo build | Remind to use tmux for long builds |
| 3 | `PreToolUse` | `Bash` + git push | Warning reminder before push |
| 4 | `PreToolUse` | `Write` + `\.(md\|txt)$` (excl. README/CLAUDE) | Block random .md file creation |
| 5 | `PreCompact` | `*` | Save state via `pre-compact.js` |
| 6 | `SessionStart` | `*` | Load context via `session-start.js` |
| 7 | `PostToolUse` | `Bash` + `gh pr create` | Log PR URL, provide review command |
| 8 | `PostToolUse` | `Edit` + `\.(ts\|tsx\|js\|jsx)$` | Auto-format with Prettier |
| 9 | `PostToolUse` | `Edit` + `\.(ts\|tsx)$` | TypeScript check after edits |
| 10 | `PostToolUse` | `Edit` + `\.(ts\|tsx\|js\|jsx)$` | Warn about console.log |
| 11 | `Stop` | `*` | Check for console.log in modified files |
| 12 | `SessionEnd` | `*` | Persist session state |
| 13 | `SessionEnd` | `*` | Evaluate session performance |
| 14 | `PostToolUse` | `Bash` + test commands | Track test results |

**Notable behaviors:**
- Complex matcher patterns using tool name + regex on tool input
- Multiple PostToolUse hooks with different matchers (selective firing)
- Automated code quality enforcement (prettier, tsc, console.log warnings)

---

### Source 4: ralph-wiggum (Plugin)

**Plugin location:** `~/.claude/plugins/cache/claude-plugins-official/ralph-wiggum/bf48ae6c75e7/`
**Hooks config:** `hooks/hooks.json`

**Registrations (1):**

| # | Event Type | Matcher | Script | Timeout | Purpose |
|---|-----------|---------|--------|---------|---------|
| 1 | `Stop` | `*` | `stop-hook.sh` | 5ms | Prevent exit when ralph-loop active |

**How it works:**
- Checks for `.claude/ralph-loop.local.md` state file
- If active: blocks stop, feeds continuation prompt back to Claude
- Tracks iteration count vs max_iterations
- Supports `<promise>` tags for completion detection

---

### Plugins with NO Hooks (9 enabled)

| Plugin | Type | Why No Hooks |
|--------|------|-------------|
| pyright-lsp | LSP | Provides language server, no interception needed |
| gopls-lsp | LSP | Provides language server, no interception needed |
| github | MCP | Provides tools via MCP protocol |
| code-review | Skills | Provides skills/agents only |
| commit-commands | Skills | Provides skills/agents only |
| linear | MCP | Provides tools via MCP protocol |
| playwright | MCP | Provides browser automation tools |
| feature-dev | Skills | Provides skills/agents only |
| frontend-design | Skills | Provides skills/agents only |

---

## Event-Level Summary

Merged view of all hooks by event type (execution order within each event):

### SessionStart (4 registrations)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |
| 2 | oh-my-claudecode | `session-start.mjs` | 5ms | `*` |
| 3 | oh-my-claudecode | `setup-init.mjs` | 30ms | `init` |
| 4 | everything-cc | `session-start.js` | -- | `*` |

### UserPromptSubmit (3 registrations) — CAN BLOCK

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |
| 2 | oh-my-claudecode | `keyword-detector.mjs` | 5ms | `*` |
| 3 | oh-my-claudecode | `skill-injector.mjs` | 3ms | `*` |

### PreToolUse (5 registrations) — CAN BLOCK

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | oh-my-claudecode | `pre-tool-enforcer.mjs` | 3ms | `*` |
| 2 | everything-cc | (inline) | -- | `Bash` + dev server pattern |
| 3 | everything-cc | (inline) | -- | `Bash` + install/build pattern |
| 4 | everything-cc | (inline) | -- | `Bash` + git push |
| 5 | everything-cc | (inline) | -- | `Write` + `.md/.txt` files |

### PostToolUse (6 registrations)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |
| 2 | oh-my-claudecode | `post-tool-verifier.mjs` | 3ms | `*` |
| 3 | everything-cc | (inline) | -- | `Bash` + `gh pr create` |
| 4 | everything-cc | (inline) | -- | `Edit` + `.ts/.tsx/.js/.jsx` (prettier) |
| 5 | everything-cc | (inline) | -- | `Edit` + `.ts/.tsx` (tsc) |
| 6 | everything-cc | (inline) | -- | `Edit` + `.ts/.tsx/.js/.jsx` (console.log) |

### SubagentStart (2 registrations)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |
| 2 | oh-my-claudecode | `subagent-tracker.mjs start` | 3ms | `*` |

### SubagentStop (2 registrations)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |
| 2 | oh-my-claudecode | `subagent-tracker.mjs stop` | 5ms | `*` |

### Stop (4 registrations) — CAN BLOCK (to continue)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |
| 2 | oh-my-claudecode | `persistent-mode.cjs` | 5ms | `*` |
| 3 | everything-cc | (inline) | -- | `*` (console.log check) |
| 4 | ralph-wiggum | `stop-hook.sh` | 5ms | `*` |

### PreCompact (2 registrations)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | oh-my-claudecode | `pre-compact.mjs` | 10ms | `*` |
| 2 | everything-cc | `pre-compact.js` | -- | `*` |

### PermissionRequest (2 registrations) — CAN BLOCK

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `plan_approval.py` | 30000ms | `ExitPlanMode` |
| 2 | oh-my-claudecode | `permission-handler.mjs` | 5ms | `Bash` |

### Notification (1 registration)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |

### SessionEnd (4 registrations)

| Order | Source | Script | Timeout | Matcher |
|-------|--------|--------|---------|---------|
| 1 | claude-karma | `live_session_tracker.py` | 5000ms | `*` |
| 2 | claude-karma | `session_title_generator.py` | 15000ms | `*` |
| 3 | oh-my-claudecode | `session-end.mjs` | 10ms | `*` |
| 4 | everything-cc | session-end.js + evaluate-session.js | -- | `*` |

---

## File Locations Reference

### Configuration Files

| File | Contains |
|------|----------|
| `~/.claude/settings.json` | Global hooks, enabledPlugins, permissions |
| `~/.claude/settings.local.json` | Global local overrides |
| `{project}/.claude/settings.json` | Project hooks (none on this project) |
| `{project}/.claude/settings.local.json` | Project local (permissions only here) |
| `~/.claude/plugins/installed_plugins.json` | Plugin install metadata |

### Plugin Hook Files

| Plugin | Hooks File |
|--------|-----------|
| oh-my-claudecode | `~/.claude/plugins/cache/omc/oh-my-claudecode/3.9.9/hooks/hooks.json` |
| everything-claude-code | `~/.claude/plugins/cache/everything-claude-code/everything-claude-code/660e0d3badd3/hooks/hooks.json` |
| ralph-wiggum | `~/.claude/plugins/cache/claude-plugins-official/ralph-wiggum/bf48ae6c75e7/hooks/hooks.json` |

### Hook Script Files

| Script | Actual Location |
|--------|----------------|
| `live_session_tracker.py` | `~/Documents/GitHub/claude-karma/hooks/live_session_tracker.py` |
| `session_title_generator.py` | `~/Documents/GitHub/claude-karma/hooks/session_title_generator.py` |
| `plan_approval.py` | `~/Documents/GitHub/claude-karma/hooks/plan_approval.py` |
| OMC scripts | `~/.claude/plugins/cache/omc/oh-my-claudecode/3.9.9/scripts/*.mjs` |
| everything-cc scripts | `~/.claude/plugins/cache/everything-claude-code/everything-claude-code/660e0d3badd3/hooks/*.js` |
| ralph-wiggum scripts | `~/.claude/plugins/cache/claude-plugins-official/ralph-wiggum/bf48ae6c75e7/hooks/stop-hook.sh` |

### Data Written by Hooks

| Hook Script | Output Location | Format |
|-------------|----------------|--------|
| `live_session_tracker.py` | `~/.claude_karma/live-sessions/{slug}.json` | JSON state file |
| `session_title_generator.py` | `POST /sessions/{uuid}/title` | API call |
| `plan_approval.py` | `GET /plans/{slug}/status` | API call |
| OMC keyword-detector | `.omc/state/{mode}-state.json` | JSON state |
| OMC skill-injector | Session context injection | `additionalContext` |
| OMC post-tool-verifier | `.omc/notepad.md` | Markdown |

---

## Observations & Insights

### 1. Timeout Disparity

Plugin hooks use very low timeouts (3-60ms) while manual hooks use 5000-30000ms. This suggests plugins are optimized for speed while manual hooks prioritize reliability.

### 2. The "Stop" Event is Contested

3 different sources try to intercept Stop: OMC (persistent-mode), everything-cc (console.log check), and ralph-wiggum (loop continuation). All fire on every stop — potential for conflicting behavior.

### 3. No Project-Level Hooks on This Project

Despite being the project that builds the hooks infrastructure, claude-karma has no project-level hooks in `.claude/settings.local.json` — all hooks are global.

### 4. Matcher Complexity Varies by Source

- claude-karma: All `*` matchers (fire on everything)
- OMC: Mix of `*` and specific matchers (`init`, `Bash`)
- everything-cc: Complex regex matchers on tool input (most selective)
- ralph-wiggum: Simple `*` matcher

### 5. Duplicate Functionality

Both OMC and ralph-wiggum handle Stop event for ralph-loop persistence. Both OMC and everything-cc handle PreCompact and SessionStart/End. These aren't conflicts (both fire), but represent redundancy.

### 6. No Hook Execution Logging

None of the hook sources log their own executions. There's no way to know:
- How often each hook fires
- How long each hook takes
- Whether hooks succeed or fail
- What context they inject

This is the biggest gap for a future analytics feature.
