# Feature Definition: Claude Code Audit — Remediation Action Items (v2.1.81 → v2.1.92)

**Status**: Planning
**Date**: 2026-04-06
**Audit Window**: 2026-03-20 → 2026-04-06
**Last Tracked Release**: v2.1.92 (2026-04-04)

---

## Section 1: Scope & Remediation Goals

### Purpose

Claude Code shipped 9 releases between 2026-03-20 and 2026-04-06 (v2.1.81 through v2.1.92). The dashboard's main branch remained at the 2026-03-20 baseline, creating a 17-day drift. An audit via `claude-code-guide` identified 14 action items across storage discovery, hook expansion, tool recognition, settings parsing, and edge case handling. Zero JSONL schema breaking changes occurred, but multiple additive features and one regression in already-shipped code require remediation. This document tracks the sprint across three priority tiers.

### Goals

- Add 11 new captain-hook event types to the Pydantic models and hook parser
- Discover and display Agent Teams storage (`~/.claude/teams/`) and task context
- Detect and badge scripted `--bare` mode sessions to eliminate "empty session" false positives
- Extend tool recognition to PowerShell and Agent Teams tools (SendMessage, TaskCreate, etc.)
- Parse frontmatter additions: subagent `initialPrompt`, skill `shell: powershell`, skill `paths: [list]`
- Merge and display `~/.claude/managed-settings.d/` fragments with per-fragment source attribution
- Preserve and render MCP tool result size metadata (`_meta["anthropic/maxResultSizeChars"]`)
- Expand settings.json parser to handle 14 new fields introduced in the audit window
- Ensure session resumption handles tool_result blocks from the v2.1.85–v2.1.91 regression window
- Deliver complete test coverage for all new code paths with passing CI

### Not In Scope

- Rewriting any existing parser from scratch
- Backporting fixes to older Claude Code versions (< v2.1.81)
- Implementing the `if` field on hook matchers in captain-hook (belongs in settings parser, not hook models)
- Dashboard UI redesign or breaking UI changes
- Syncthing sync architecture overhaul (separate workstream)
- Audio recording, webcam, or camera tool support
- Streaming response ingestion or incremental JSONL appending

---

## Section 2: Findings Summary

| Tier | Count | Affected Subsystems | Representative Finding |
|------|-------|---------------------|--------------------------|
| **Tier 1 (Blockers)** | 4 | captain-hook, JSONL merge, Teams discovery, session detection | `[Image #N]` regression blocks timeline rendering; 11 new hook types unrecognized; Teams storage discovery absent |
| **Tier 2 (High Priority)** | 7 | Tool recognition, frontmatter parsing, settings expansion, MCP metadata | PowerShell tool unsupported; 14 new settings fields unparsed; managed-settings.d fragments not merged |
| **Tier 3 (Experimental/Polish)** | 3 | Extended thinking, hook settings, session resumption hardening | Thinking summary visibility requires settings flag; resumption edge cases across version boundary |

---

## Section 3: Vocabulary

| Term | Definition | NOT the Same As |
|------|-----------|-----------------|
| **Hook event** | A discrete action fired by Claude Code (SessionStart, PreToolUse, SessionEnd, etc.). Modeled in captain-hook. | **Hook matcher** — a conditional rule in settings.json that filters when hooks run. Different layer. |
| **`[Image #N]` marker** | Integer suffix on MessageAttachment for images, e.g., `[Image 1]`. Appears in merged messages. | **ImageAttachment** — the Pydantic model representing an image object with mime_type and data. |
| **Agent Team** | A multi-user collaboration workspace. Storage: `~/.claude/teams/{team-name}/config.json` and `~/.claude/tasks/{team-name}/`. | **Subagent** — a single-user task agent spawned within a session. Storage: `~/.claude/projects/.../subagents/`. |
| **Tool name** | Recognized tool from Bash, Read, Write, SearchCode (API layer). E.g., "PowerShell" or "TaskCreate". | **Plugin-namespaced tool** — @plugin/toolname notation for plugin tools. Different discovery and execution model. |
| **managed-settings.d** | Directory fragment pattern: `~/.claude/managed-settings.d/*.json`. Last-write-wins merge semantics. | **settings.json** — monolithic user settings at `~/.claude/settings.json`. No fragment support. |
| **Bare mode session** | Scripted invocation with `--bare` flag. No hook events, no skill invocations. Appears "empty" to dashboard. | **Minimal session** — a session with few events but normal initialization/termination. Has hook events. |

---

## Section 4: Tier 1 — Blockers (Sprint 1)

### 4.1 `[Image #N]` JSONL Merge Regression

**Problem**: Commit `272f506` on branch `enhance/timeline-updates` fixed the `[Image #N]` marker regression where image references were incorrectly merged. This fix must be listed as shipped so readers understand the timeline.

**Cite**: Claude Code v2.1.85–v2.1.86 regression window. Fix landed before audit.

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/jsonl_utils.py` | Modify | Parser/Merge | Drop `[Image #N]` markers during JSONL merge (already fixed, commit 272f506) |
| `api/tests/test_jsonl_utils.py` | Modify | Test | Add test_merge_drops_image_hash_number_marker (already present) |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Confirm commit 272f506 is on main | `git log --oneline \| grep "272f506"` should show commit |
| 2 | Verify test exists and passes | `pytest tests/test_jsonl_utils.py::TestMessageMerging -v` should PASS |
| 3 | Spot-check JSONL merge in sample | Read a merged message, confirm `[Image #N]` absent from final output |

**Postconditions**

- [ ] Commit 272f506 verified on branch
- [ ] All merge regression tests passing
- [ ] No `[Image #N]` artifacts in merged JSONL

---

### 4.2 Captain-Hook Library Expansion

**Problem**: Claude Code v2.1.82–v2.1.92 introduced 11 new hook event types. captain-hook models only 10 hook types (PreToolUse, PostToolUse, etc.). Parser fails silently or raises on unrecognized events.

**Cite**: Claude Code v2.1.82 (InstructionsLoaded), v2.1.84 (CwdChanged, FileChanged), v2.1.86 (PermissionDenied, TaskCreated), v2.1.87 (TaskCompleted, TeammateIdle), v2.1.88 (WorktreeCreate, WorktreeRemove), v2.1.90 (Elicitation, ElicitationResult).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `captain-hook/models/hooks.py` | Modify | Expansion | Add 11 new Pydantic event models |
| `captain-hook/models/__init__.py` | Modify | Expansion | Export new event types |
| `captain-hook/parser.py` | Modify | Expansion | Update parse_hook_event() to dispatch to new types |
| `captain-hook/tests/test_models.py` | Modify | Test | Add round-trip tests for all 21 event types |

**New Hook Event Types** (detailed specs {needs clarification — awaiting official hook schema docs})

| Hook Type | Fires | Input Schema | Output Schema | Can Block? |
|-----------|-------|-------------|---------------|-----------|
| InstructionsLoaded | System instructions loaded into context | `{ "instructions": [...] }` | N/A | No |
| CwdChanged | Working directory changed | `{ "old_cwd": str, "new_cwd": str }` | N/A | No |
| FileChanged | File created/modified outside session | `{ "path": str, "action": "create"\|"modify" }` | N/A | No |
| PermissionDenied | Tool execution blocked by policy | `{ "tool_name": str, "reason": str }` | N/A | No |
| TaskCreated | New task spawned in Agent Teams | `{ "task_id": str, "title": str }` | N/A | No |
| TaskCompleted | Task marked complete | `{ "task_id": str, "status": str }` | N/A | No |
| TeammateIdle | Teammate inactive for threshold | `{ "member_id": str, "duration_seconds": int }` | N/A | No |
| WorktreeCreate | Git worktree created for session | `{ "worktree_path": str, "branch": str }` | N/A | No |
| WorktreeRemove | Git worktree cleaned up | `{ "worktree_path": str }` | N/A | No |
| Elicitation | LLM requesting user info | `{ "prompt": str, "field_name": str }` | `{ "response": str }` | Yes |
| ElicitationResult | User provided elicitation response | `{ "field_name": str, "response": str }` | N/A | No |

**Additional Changes**

- Modify `PreToolUseOutput.permissionDecision` Literal to include `"defer"` value
- Add `PermissionDeniedOutput` class (output schema for PermissionDenied hook when it can block)

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Create new Pydantic models for each hook | Each model has BaseModel + ConfigDict(frozen=True) |
| 2 | Update parser dispatch logic | parse_hook_event() routes each event_type string to correct class |
| 3 | Add round-trip tests | For each new hook: parse JSON → model → json, compare |
| 4 | Test existing hooks still parse | Regression: all 10 original hook types work unchanged |
| 5 | Run full test suite | `pytest captain-hook/tests/ -v` all green |

**Postconditions**

- [ ] All 21 hook types (10 original + 11 new) parse correctly
- [ ] Round-trip JSON serialization works for all types
- [ ] Zero regressions on existing 10 hook types
- [ ] Full test coverage for new types

---

### 4.3 Agent Teams Storage Discovery

**Problem**: Claude Code v2.1.85+ stores multi-user team context in `~/.claude/teams/`. Dashboard has zero awareness of teams. Sessions spawned within teams show no team affiliation or task context in UI.

**Cite**: Claude Code v2.1.85 (Agent Teams feature launch).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/team.py` | Create | Models | Team, Task, TeamMember Pydantic models |
| `api/routers/teams.py` | Create | Routers | Endpoints for team discovery and context |
| `api/utils.py` | Modify | Utils | Add team discovery and validation logic |
| `frontend/src/routes/teams/+page.svelte` | Create | Frontend | Team listing and browser view |
| `frontend/src/routes/teams/[team_name]/+page.svelte` | Create | Frontend | Team detail with tasks |
| `frontend/src/lib/components/TeamCard.svelte` | Create | Components | Reusable team summary card |

**Storage Locations to Discover**

```
~/.claude/teams/{team-name}/
  config.json              # Team metadata, members, permissions
  settings.json            # Team-specific settings (optional)
  
~/.claude/tasks/{team-name}/
  {task-id}.json           # Individual task definition + status
```

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Scan `~/.claude/teams/` for team directories | If absent, teams UI hidden; if present, list teams |
| 2 | Parse team config.json and task definitions | Load into Pydantic models |
| 3 | Link sessions to teams via metadata correlation | Check JSONL session metadata for team_id field |
| 4 | Create API endpoints for team listing and detail | /teams, /teams/{name}, /teams/{name}/tasks |
| 5 | Build frontend team browser | Replicate project/session browser UX for teams |
| 6 | Add team context to session card (optional) | Show team affiliation badge if applicable |

**Postconditions**

- [ ] Teams directory discovery works when present, degrades gracefully when absent
- [ ] All team metadata parsed into models without errors
- [ ] API endpoints return 200 for valid teams, 404 for missing teams
- [ ] Frontend team browser renders correctly with team cards
- [ ] Sessions show team affiliation when applicable

---

### 4.4 `--bare` Mode Session Detection

**Problem**: Claude Code supports `--bare` flag for scripted sessions (no GUI, no interactive hooks). These sessions produce zero hook events and zero skill invocations. Dashboard classifies them as "empty" or "corrupt" instead of "bare mode". Users see warnings/errors instead of understanding the mode.

**Cite**: Claude Code v2.1.80+ (bare mode flag support, no specific hook added for it).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/session.py` | Modify | Models | Add `is_bare_mode: bool` property |
| `api/utils.py` | Modify | Utils | Detect bare mode by absence of hook events + skill invocations |
| `frontend/src/lib/components/SessionCard.svelte` | Modify | Components | Render "Bare mode" badge instead of "Empty" warning |
| `frontend/src/lib/utils/session.ts` | Modify | Utils | Add is_bare_mode() helper for frontend logic |

**Detection Logic**

A session is bare mode if ALL of:
- Session has > 0 messages (not completely empty)
- Zero PostToolUse hook events (no tool invocations tracked)
- Zero skill invocation references in JSONL
- Session has normal start/end markers (not corrupted)

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Implement is_bare_mode() detection in Session model | Read first 10 messages, check for hook absence |
| 2 | Add is_bare_mode property to session metadata | Expose in API responses |
| 3 | Update session card to check is_bare_mode | If true, show "Bare mode" badge; if false, proceed normally |
| 4 | Test with sample bare-mode JSONL file | Verify detection triggers correctly |
| 5 | Run regression on normal sessions | Ensure no false positives |

**Postconditions**

- [ ] Bare mode sessions detected and badged correctly
- [ ] No false positives on normal sessions with few events
- [ ] Session card displays "Bare mode" instead of warnings
- [ ] API includes is_bare_mode in session detail response

---

## Section 5: Tier 2 — High Priority (Sprint 2)

### 5.1 PowerShell Tool Support

**Problem**: Claude Code v2.1.88+ supports PowerShell as a first-class tool (alongside Bash). Dashboard's `get_tool_summary()` in `api/utils.py` only recognizes Bash, classifying PowerShell invocations as unknown.

**Cite**: Claude Code v2.1.88 (PowerShell tool launch).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/utils.py` | Modify | Utils | Add PowerShell to recognized tools in get_tool_summary() |
| `api/models/tool_result.py` | Modify | Models | Ensure tool_result.tool_name handles "PowerShell" string |
| `frontend/src/lib/components/timeline/TimelineEventCard.svelte` | Modify | Components | Add PowerShell icon/badge distinct from Bash |
| `frontend/src/routes/tools/+page.svelte` | Modify | Routes | Split tool stats: Bash vs PowerShell columns |
| `api/tests/test_utils.py` | Modify | Test | Add test_powershell_tool_recognized |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Update tool_name recognition to accept "PowerShell" | get_tool_summary() includes PowerShell in known_tools |
| 2 | Add PowerShell icon to timeline (lucide-svelte: Terminal, Shield, or custom) | Visual distinction from Bash icon |
| 3 | Update /tools route analytics to split Bash and PowerShell | Two separate rows in tool breakdown table |
| 4 | Test with sample session containing PowerShell invocations | Verify correct categorization |
| 5 | Check backward compat (sessions with only Bash) | No regressions |

**Postconditions**

- [ ] PowerShell invocations recognized and categorized
- [ ] Timeline shows PowerShell tool calls with correct icon
- [ ] /tools route splits Bash and PowerShell statistics
- [ ] No regressions on existing Bash handling

---

### 5.2 Agent Teams Tools Recognition

**Problem**: Claude Code v2.1.86+ treats Agent Teams operations (SendMessage, TeamCreate, TaskCreate, TaskUpdate, etc.) as first-class "tools" in the timeline. Dashboard's tool parser sees them as unknown or ignores them.

**Cite**: Claude Code v2.1.86 (TaskCreate mapping via PR #55). v2.1.87+ (SendMessage, TeamCreate, TaskDelete, TaskUpdate, TaskRead).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/utils.py` | Modify | Utils | Extend get_tool_summary() to recognize Teams tools |
| `api/models/tool_result.py` | Modify | Models | Add tool_result variants for Teams operations |
| `frontend/src/lib/components/timeline/TimelineEventCard.svelte` | Modify | Components | Render Teams tool cards (SendMessage shows message preview, etc.) |

**Recognized Teams Tools**

| Tool | Semantic | Appears As | Input Schema | Notes |
|------|----------|-----------|--------------|-------|
| SendMessage | Async communication | "→ {recipient}" | `{ "member_id": str, "message": str }` | Teammate messaging |
| TeamCreate | Collaboration setup | "👥 Create team" | `{ "team_name": str, "members": [...] }` | New team formation |
| TeamDelete | Team removal | "👥 Delete team" | `{ "team_id": str }` | Decommission team |
| TaskCreate | Work unit creation | "✓ Create task" | `{ "title": str, "assignee": str, "description": str }` | New task (already mapped in PR #55) |
| TaskUpdate | Task mutation | "✓ Update task" | `{ "task_id": str, "status": str }` | Status/assignment changes |
| TaskRead | Task query | "✓ Read task" | `{ "task_id": str }` | Metadata fetch |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Update tool_name recognition to include all Teams tools | get_tool_summary() covers all 6 tools |
| 2 | Extend timeline event rendering to handle Teams operations | Different card template per Teams tool |
| 3 | Add Teams tool icons (bits-ui icons or custom SVG) | Visual distinction for each operation |
| 4 | Test with sample session containing Teams tool calls | Verify correct parsing and rendering |
| 5 | Verify TaskCreate mapping from PR #55 still works | No regression on already-shipped feature |

**Postconditions**

- [ ] All 6 Teams tools recognized in timeline
- [ ] Timeline cards render Teams operations with semantic clarity
- [ ] No regressions on TaskCreate mapping from PR #55
- [ ] /tools route includes Teams operations in tool breakdown

---

### 5.3 Subagent `initialPrompt` Frontmatter Field

**Problem**: Claude Code v2.1.87+ includes `initialPrompt` in subagent frontmatter (the first user message to the agent). Dashboard's subagent parser does not extract or display this field.

**Cite**: Claude Code v2.1.87 (subagent frontmatter expansion).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/agent.py` | Modify | Models | Add initial_prompt property |
| `api/parsers/subagent_frontmatter.py` | Modify or Create | Parser | Extract initialPrompt from frontmatter YAML |
| `frontend/src/lib/components/subagents/SubagentCard.svelte` | Modify | Components | Display initial_prompt in tooltip or expanded view |
| `api/tests/test_agent.py` | Modify | Test | Test frontmatter parsing includes initialPrompt |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Parse initialPrompt from subagent JSONL frontmatter | Frontmatter parser yields initial_prompt field |
| 2 | Add initial_prompt property to Agent model | Cached or computed from JSONL header |
| 3 | Display in SubagentCard (tooltip on hover, or detail panel) | User can see what task was given to agent |
| 4 | Handle missing initialPrompt gracefully (older agents) | No errors if field absent |
| 5 | Test with sample subagent JSONL | Verify parsing works |

**Postconditions**

- [ ] initial_prompt extracted and available in API
- [ ] SubagentCard displays initial_prompt in UI
- [ ] Graceful handling of missing field (no errors)
- [ ] Zero regressions on existing subagent display

---

### 5.4 Skill Frontmatter Additions

**Problem**: Claude Code v2.1.87+ extends skill frontmatter with new fields: `shell: powershell`, `paths: [list]`, and `${CLAUDE_SKILL_DIR}` variable support. Dashboard's skill parser is outdated.

**Cite**: Claude Code v2.1.87 (skill frontmatter expansion) and v2.1.88 (PowerShell support).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/skill.py` | Modify | Models | Add shell, paths, and expand_variables support |
| `api/parsers/skill_frontmatter.py` | Modify or Create | Parser | Extract shell, parse paths (list or string), handle ${CLAUDE_SKILL_DIR} |
| `frontend/src/lib/components/skills/SkillCard.svelte` | Modify | Components | Display shell type (bash/powershell) and path info |
| `api/tests/test_skill.py` | Modify | Test | Test parsing of new frontmatter fields |

**New Fields**

| Field | Type | Examples | Notes |
|-------|------|----------|-------|
| `shell` | string | "bash", "powershell" | Default "bash" if omitted |
| `paths` | list OR string | `["path/a", "path/b"]` or `"path/a, path/b"` | Both YAML list and comma-separated string supported |
| `${CLAUDE_SKILL_DIR}` | variable | Used in paths: `"${CLAUDE_SKILL_DIR}/lib"` | Expands to skill directory at runtime |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Update skill frontmatter parser to extract shell, paths | Parse both list and string formats for paths |
| 2 | Implement variable expansion for ${CLAUDE_SKILL_DIR} | Replace token with actual skill directory path |
| 3 | Add shell and paths properties to Skill model | Expose in API responses |
| 4 | Update SkillCard to display shell type and paths | Show visual indicators (shell icon, path list) |
| 5 | Test with sample skills featuring new fields | Verify parsing and rendering work |
| 6 | Backward compat: skills without new fields | No errors, graceful defaults |

**Postconditions**

- [ ] Skill shell type (bash/powershell) extracted and displayed
- [ ] Paths field parsed (both list and string formats)
- [ ] ${CLAUDE_SKILL_DIR} variable expanded correctly
- [ ] SkillCard displays new info in UI
- [ ] Backward compatible with older skills

---

### 5.5 Managed-Settings Fragments Merging

**Problem**: Claude Code v2.1.89+ supports modular settings via `~/.claude/managed-settings.d/*.json` (e.g., `override.json`, `team-defaults.json`). These fragments use last-write-wins merging. Dashboard only reads monolithic `settings.json` and ignores fragments.

**Cite**: Claude Code v2.1.89 (managed-settings.d directory support).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/settings.py` | Modify | Models | Add merged_settings field tracking per-fragment source |
| `api/services/settings_loader.py` | Modify or Create | Services | Implement fragment discovery, merging (last-write-wins), and source attribution |
| `frontend/src/lib/components/settings/SettingsPanel.svelte` | Modify | Components | Show merged settings with per-value source attribution |
| `api/tests/test_settings.py` | Modify | Test | Test fragment merging with multiple fragments |

**Merging Rules**

1. Read `~/.claude/settings.json` (base)
2. Scan `~/.claude/managed-settings.d/` for all `*.json` files
3. Sort fragments by modification time (last-write-wins)
4. Merge each fragment into base using deep-merge (nested objects combined, arrays replaced)
5. Track source file for each value

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Implement fragment discovery in settings loader | Scan managed-settings.d, find all *.json |
| 2 | Implement merge logic (last-write-wins for each key) | Deep merge with array replacement strategy |
| 3 | Track source attribution for each merged value | Store {key: {value, source_file}} |
| 4 | Update SettingsPanel to display source annotations | e.g., "defaultShell: bash (from team-defaults.json)" |
| 5 | Test with 3+ fragment files and conflicts | Verify correct merge order and attribution |

**Postconditions**

- [ ] All managed-settings.d fragments discovered and loaded
- [ ] Merging follows last-write-wins semantics
- [ ] Source file tracked for each setting value
- [ ] SettingsPanel displays source attribution
- [ ] Graceful handling if managed-settings.d absent

---

### 5.6 MCP Tool Result Size Annotation Preservation

**Problem**: Claude Code v2.1.90+ annotates large tool results with `_meta["anthropic/maxResultSizeChars"]` metadata. Dashboard's ToolResult model discards this metadata, losing visibility into truncation.

**Cite**: Claude Code v2.1.90 (MCP metadata standardization).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/tool_result.py` | Modify | Models | Add meta field with Optional[Dict] for metadata |
| `api/routers/sessions.py` | Modify | Routers | Include meta in tool_result response |
| `frontend/src/lib/components/timeline/TimelineToolCall.svelte` | Modify | Components | Render "(large output)" badge if maxResultSizeChars present |
| `api/tests/test_tool_result.py` | Modify | Test | Test parsing and preserving metadata |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Add Optional[Dict[str, Any]] meta field to ToolResult model | Pydantic field with default None |
| 2 | Update JSONL parser to preserve _meta block | Extract from tool_result structure |
| 3 | Expose meta in API responses | Include in /sessions/{uuid}/tools endpoint |
| 4 | Render "(large output)" badge in timeline | Check if meta["anthropic/maxResultSizeChars"] present |
| 5 | Test with sample tool_result containing metadata | Verify preservation and rendering |

**Postconditions**

- [ ] MCP metadata preserved in ToolResult model
- [ ] Metadata exposed in API responses
- [ ] Timeline shows "(large output)" annotation for truncated results
- [ ] Zero regressions on tool results without metadata

---

### 5.7 Fourteen New Settings Fields

**Problem**: Claude Code v2.1.81–v2.1.92 introduced 14 new settings.json fields. Dashboard's settings parser model omits them, causing validation errors or silent omissions.

**Cite**: Multiple versions across the audit window.

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/settings.py` | Modify | Models | Add 14 new fields to Settings Pydantic model |
| `frontend/src/lib/components/settings/SettingsPanel.svelte` | Modify | Components | Render new fields with appropriate UI controls |
| `api/tests/test_settings.py` | Modify | Test | Test each new field parsing and display |

**New Settings Fields** (specifications {needs clarification — awaiting official settings schema docs})

| Field | Type | Purpose | Default | Notes |
|-------|------|---------|---------|-------|
| `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | bool | Enable Agent Teams feature | false | Feature flag for Teams |
| `forceRemoteSettingsRefresh` | bool | Refresh settings from server on startup | false | Multi-device sync aid |
| `disableSkillShellExecution` | bool | Prevent skill shell commands | false | Security policy |
| `sandbox.failIfUnavailable` | bool | Error if sandbox unavailable | false | Sandbox policy |
| `env.CLAUDE_CODE_NO_FLICKER` | bool | Disable UI flicker during updates | false | Performance/aesthetics |
| `env.CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` | bool | Strip environment vars in subprocesses | false | Security hardening |
| `env.CLAUDE_CODE_USE_POWERSHELL_TOOL` | bool | Prefer PowerShell over Bash | false | Shell preference |
| `env.CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE` | bool | Keep marketplace UI on plugin load fail | false | UX continuity |
| `env.CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING` | bool | Disable extended thinking in Claude Code | false | Performance tuning |
| `showThinkingSummaries` | bool | Display extended thinking summaries in UI | false | UX feature |
| `defaultShell` | string | Default shell: "bash", "zsh", "powershell" | "bash" | Shell choice |
| `agent` (plugin-specific) | object | Plugin-defined agent settings | {} | Per-plugin config |
| `allowedChannelPlugins` | array[string] | Whitelist of allowed channel plugins | [] | Plugin security |
| `includeGitInstructions` | bool | Prepend git best practices to prompts | false | Git guidance |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Add all 14 fields to Settings Pydantic model | Each field with correct type and Optional handling |
| 2 | Set sensible defaults for each field | Match Claude Code defaults or safe fallbacks |
| 3 | Update SettingsPanel to render new fields | Appropriate controls (toggle, text input, dropdown) per type |
| 4 | Test each field parsing from settings.json | pytest validates all 14 fields |
| 5 | Backward compat: settings without new fields | No errors if fields omitted |

**Postconditions**

- [ ] All 14 new fields recognized and parsed
- [ ] SettingsPanel renders all fields with appropriate UI
- [ ] Backward compatible (no errors for old settings.json)
- [ ] API includes all fields in /settings endpoint

---

## Section 6: Tier 3 — Experimental & Polish (Sprint 3)

### 6.1 Extended Thinking Visibility

**Problem**: Claude Code v2.1.90+ can display extended thinking summaries when `showThinkingSummaries: true` in settings. Dashboard has zero awareness of thinking blocks and does not render them.

**Cite**: Claude Code v2.1.90 (extended thinking UI support).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/message.py` | Modify | Models | Ensure thinking block content preserved in AssistantMessage |
| `api/routers/sessions.py` | Modify | Routers | Include thinking content in timeline responses when showThinkingSummaries=true |
| `frontend/src/lib/components/timeline/TimelineEventCard.svelte` | Modify | Components | Render thinking summary (collapsed by default, expandable) |
| `frontend/src/lib/utils/settings.ts` | Modify or Create | Utils | Read showThinkingSummaries from settings, pass to components |
| `api/tests/test_message.py` | Modify | Test | Test thinking block preservation in AssistantMessage |

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Verify AssistantMessage preserves thinking block content | Check JSONL parsing includes thinking in content array |
| 2 | Check settings loader reads showThinkingSummaries | Frontend utils can access flag |
| 3 | Update timeline to conditionally render thinking | If showThinkingSummaries=true, render in collapsed detail |
| 4 | Style thinking summary (monospace, dimmed, expandable) | Match Claude Code's display aesthetic |
| 5 | Test with sample session containing thinking blocks | Verify rendering works when flag enabled |

**Postconditions**

- [ ] Thinking blocks preserved in models and API
- [ ] Timeline respects showThinkingSummaries setting
- [ ] Thinking summary renders with expand/collapse
- [ ] No regression when flag disabled

---

### 6.2 Hook Conditional `if` Field Support

**Problem**: Claude Code v2.1.91+ supports conditional `if` field on hook matchers in settings.json. These are NOT hook event types (captain-hook concern) but rather matcher conditions (settings parser concern). Dashboard must display the `if` condition for each hook matcher.

**Cite**: Claude Code v2.1.91 (hook matcher conditionals).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/settings.py` | Modify | Models | Add conditional_if field to HookMatcher model |
| `api/parsers/hook_matcher.py` | Modify or Create | Parser | Extract and parse if field from settings hook array |
| `frontend/src/lib/components/settings/HookMatcherRow.svelte` | Modify or Create | Components | Display if condition in settings hook table |
| `api/tests/test_settings.py` | Modify | Test | Test parsing hook matcher conditionals |

**Hook Matcher Conditional Example**

```json
{
  "hook": "PreToolUse",
  "if": "tool_name == 'Read' && context.file_size > 1000000",
  "command": "/path/to/script.py"
}
```

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Add conditional_if: Optional[str] to HookMatcher model | Optional field, default None |
| 2 | Parse if field from hook matcher in settings | Extract condition string as-is |
| 3 | Display if condition in settings UI (HookMatcherRow) | Show condition in table, truncate if long |
| 4 | Test with sample hook matchers with if conditions | Verify parsing and display |

**Postconditions**

- [ ] Hook matcher if conditions parsed
- [ ] Settings UI displays hook conditions
- [ ] Graceful handling if if field absent
- [ ] No regressions on existing hook matchers

---

### 6.3 Session Resumption Hardening

**Problem**: Claude Code v2.1.85–v2.1.91 experienced a regression where session resumption across versions could produce tool_result blocks with mismatched IDs. Dashboard must validate tool_use ID ↔ tool_result ID pairing during resumption parsing.

**Cite**: Claude Code v2.1.85–v2.1.91 regression window (fixed in v2.1.92).

**Affected Files**

| File | Change Type | Workstream | Notes |
|------|-------------|-----------|-------|
| `api/models/message.py` | Modify | Models | Add validation for tool_use/tool_result ID pairing |
| `api/parsers/jsonl_parser.py` | Modify | Parser | Add resumption-edge-case detection and warnings |
| `api/routers/sessions.py` | Modify | Routers | Include resumption warnings in session metadata if detected |
| `api/tests/test_session_resumption.py` | Modify or Create | Test | Test resumption across regression boundary versions |

**Validation Logic**

When parsing a session that shows resumption (detected by session_uuid changing mid-JSONL or by explicit resume marker):

1. Collect all tool_use IDs from AssistantMessage content blocks
2. Collect all tool_result IDs from UserMessage content blocks
3. For each tool_result, verify corresponding tool_use exists by ID
4. Flag any orphaned tool_results (no matching tool_use)
5. Log warnings but do not fail parse

**Steps**

| # | Action | Verification |
|---|--------|--------------|
| 1 | Implement tool_use/result ID pairing validation | Check all IDs match during resumption |
| 2 | Detect sessions with resumption (markers or UUID change) | Identify resumption boundary |
| 3 | Add warnings to session metadata if ID mismatches found | Report as "resumption_warnings" array |
| 4 | Test with sample session from regression window | Verify validation catches ID mismatches |
| 5 | Test with normal sessions (no resumption) | Zero false positives |

**Postconditions**

- [ ] Tool_use/result ID pairing validated
- [ ] Resumption edge cases detected and warned
- [ ] Session parse does not fail on ID mismatches
- [ ] Zero regressions on normal sessions

---

## Section 7: File Change Index

| File | Change Type | Sprint | Workstream | Notes |
|------|-------------|--------|-----------|-------|
| `api/models/agent.py` | Modify | S1 | Expansion | Add initial_prompt property |
| `api/models/hooks.py` (captain-hook) | Modify | S1 | Expansion | Add 11 new hook event types |
| `api/models/message.py` | Modify | S3 | Validation | Add tool_use/result ID validation |
| `api/models/settings.py` | Modify | S2 | Expansion | Add 14 new settings fields + conditional_if for hooks |
| `api/models/session.py` | Modify | S1 | Detection | Add is_bare_mode property |
| `api/models/skill.py` | Modify | S2 | Expansion | Add shell, paths, variable expansion |
| `api/models/team.py` | Create | S1 | Discovery | Team, Task, TeamMember Pydantic models |
| `api/models/tool_result.py` | Modify | S2 | Preservation | Add meta field for MCP metadata |
| `api/parsers/hook_matcher.py` | Create or Modify | S3 | Settings | Parse hook conditional if field |
| `api/parsers/jsonl_parser.py` | Modify | S3 | Validation | Add resumption validation |
| `api/parsers/skill_frontmatter.py` | Create or Modify | S2 | Expansion | Parse shell, paths, variables |
| `api/parsers/subagent_frontmatter.py` | Create or Modify | S2 | Expansion | Extract initialPrompt |
| `api/routers/sessions.py` | Modify | S2, S3 | Routers | Include tool meta, resumption warnings, thinking content |
| `api/routers/teams.py` | Create | S1 | Discovery | Team listing and detail endpoints |
| `api/services/settings_loader.py` | Create or Modify | S2 | Merging | Implement fragment discovery and merging |
| `api/tests/test_agent.py` | Modify | S2 | Test | Test initialPrompt extraction |
| `api/tests/test_hook_matcher.py` | Modify | S3 | Test | Test conditional if parsing |
| `api/tests/test_jsonl_utils.py` | Modify | S1 | Test | Confirm merge regression test (already shipped) |
| `api/tests/test_message.py` | Modify | S3 | Test | Test tool_use/result ID validation |
| `api/tests/test_session_resumption.py` | Create or Modify | S3 | Test | Test resumption edge cases |
| `api/tests/test_settings.py` | Modify | S2, S3 | Test | Test new fields and fragment merging |
| `api/tests/test_skill.py` | Modify | S2 | Test | Test shell, paths parsing |
| `api/tests/test_tool_result.py` | Modify | S2 | Test | Test metadata preservation |
| `api/tests/test_utils.py` | Modify | S2 | Test | Test PowerShell and Teams tool recognition |
| `api/utils.py` | Modify | S1, S2 | Utils | Bare mode detection, Teams tool discovery, PowerShell support |
| `captain-hook/models/__init__.py` | Modify | S1 | Expansion | Export new hook event types |
| `captain-hook/parser.py` | Modify | S1 | Expansion | Update parse_hook_event dispatch |
| `captain-hook/tests/test_models.py` | Modify | S1 | Test | Add tests for 11 new hook types |
| `frontend/src/lib/api-types.ts` | Modify | S1, S2 | Types | Add Team types, extend tool and settings types |
| `frontend/src/lib/components/settings/HookMatcherRow.svelte` | Create or Modify | S3 | Components | Display if conditions |
| `frontend/src/lib/components/settings/SettingsPanel.svelte` | Modify | S2, S3 | Components | Render new settings, fragment sources, thinking |
| `frontend/src/lib/components/skills/SkillCard.svelte` | Modify | S2 | Components | Display shell, paths info |
| `frontend/src/lib/components/subagents/SubagentCard.svelte` | Modify | S2 | Components | Display initialPrompt |
| `frontend/src/lib/components/TeamCard.svelte` | Create | S1 | Components | Team summary card |
| `frontend/src/lib/components/timeline/TimelineEventCard.svelte` | Modify | S2, S3 | Components | Add PowerShell icon, Teams tool cards, thinking render |
| `frontend/src/lib/components/timeline/TimelineToolCall.svelte` | Modify | S2 | Components | Render "(large output)" badge |
| `frontend/src/lib/utils/session.ts` | Modify | S1 | Utils | Add is_bare_mode() helper |
| `frontend/src/lib/utils/settings.ts` | Modify or Create | S3 | Utils | Read showThinkingSummaries setting |
| `frontend/src/routes/settings/+page.svelte` | Modify | S2, S3 | Routes | Display new settings, conditionals |
| `frontend/src/routes/teams/+page.svelte` | Create | S1 | Routes | Team listing view |
| `frontend/src/routes/teams/[team_name]/+page.svelte` | Create | S1 | Routes | Team detail view |
| `frontend/src/routes/tools/+page.svelte` | Modify | S2 | Routes | Split Bash/PowerShell stats, include Teams tools |

---

## Section 8: Cross-Cutting Concerns

### 8.1 Sequencing & Dependencies

**Sequential (must complete in order)**

1. **S1 captain-hook expansion** — must complete before any S2 code references new hook types
2. **S1 bare mode detection** — quick, unblocks session card updates
3. **S1 Teams discovery** — foundational, other code may reference teams
4. **S2 tool recognition expansion** — depends on S1 captain-hook; can run in parallel with settings/metadata work

**Parallel (can run together)**

- S2 settings parsing (14 fields + fragments) — independent
- S2 skill/subagent frontmatter parsing — independent
- S2 MCP metadata preservation — independent

**Late-stage (S3, after core work stable)**

- S3 thinking visibility — depends on S2 settings being solid
- S3 hook conditional if — depends on S2 settings parser refactored
- S3 resumption hardening — can start in parallel but test last

### 8.2 Test Strategy

**Test Scope per Sprint**

| Sprint | Test Execution | Coverage Target |
|--------|---|---|
| S1 | `pytest api/tests/ captain-hook/tests/ -v` | ~85% (captain-hook 100%, models/utils 70%+) |
| S2 | `pytest api/tests/test_settings.py api/tests/test_utils.py api/tests/test_*.py -v` | ~80% (new parsers, model serialization) |
| S3 | `pytest api/tests/test_session_resumption.py api/tests/test_message.py -v` | ~75% (edge cases, validation) |

**Integration Tests**

- End-to-end timeline rendering with all new tools (PowerShell, Teams, thinking)
- Settings merge with 3+ fragments + source attribution
- Bare mode detection on sample JSONL (zero hook events)
- Session resumption across version boundary with ID mismatch detection

**Test File Locations**

```
api/tests/
  test_utils.py           # Tool recognition, bare mode
  test_settings.py        # Settings parsing, fragment merging
  test_agent.py           # Subagent initialPrompt
  test_message.py         # Thinking blocks, tool_use/result validation
  test_session_resumption.py  # Edge cases, ID validation
  
captain-hook/tests/
  test_models.py          # All 21 hook types round-trip
```

### 8.3 Rollout

**Backward Compatibility**

- No breaking JSONL schema changes (all new features are additive)
- Settings with missing new fields: use defaults, no errors
- Sessions without new metadata: degrade gracefully (no badges, no warnings)
- Fragments missing: use base settings.json only (no errors)

**Zero-Downtime Deploy**

1. Deploy backend (api) with new models and endpoints
2. Deploy frontend (SvelteKit) with new components
3. No data migration needed (all new fields optional)

**Visibility Flags**

- Teams tab: hidden if `~/.claude/teams/` absent
- Thinking summary: controlled by showThinkingSummaries setting
- Bare mode badge: always visible (detection automatic)
- PowerShell stats: visible if any PowerShell invocations found

---

## Section 9: Verification Matrix

### 9.1 Sprint 1 Verification

| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1.1 | `[Image #N]` marker dropped during merge | `pytest tests/test_jsonl_utils.py::TestMessageMerging::test_merge_drops_image_hash_number_marker -v` | [ ] |
| 1.2 | All 21 captain-hook types parse without error | `pytest captain-hook/tests/test_models.py::TestParseHookEvent -v` | [ ] |
| 1.3 | New 11 hook types round-trip JSON serialization | `pytest captain-hook/tests/test_models.py::TestRoundTrip -v` | [ ] |
| 1.4 | Bare mode detection triggers on zero-hook JSONL | Sample: read bare-mode-sample.jsonl, confirm is_bare_mode=true | [ ] |
| 1.5 | Normal sessions do NOT trigger bare mode | Sample: read normal-session.jsonl, confirm is_bare_mode=false | [ ] |
| 1.6 | Teams discovery returns empty when ~./claude/teams/ absent | Manual: rm -rf ~/.claude/teams; curl http://localhost:8000/teams; expect 200 with empty list | [ ] |
| 1.7 | Teams API returns team metadata when directory present | Manual: create test team dir; curl /teams/{name}; expect team object | [ ] |
| 1.8 | Frontend teams route renders correctly | Manual: navigate to /teams in browser; expect team cards | [ ] |

### 9.2 Sprint 2 Verification

| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 2.1 | PowerShell tool recognized in get_tool_summary | `pytest tests/test_utils.py::TestToolSummary::test_powershell_recognized -v` | [ ] |
| 2.2 | PowerShell timeline card renders with correct icon | Manual: view session with PowerShell invocation; icon visible | [ ] |
| 2.3 | /tools route splits Bash and PowerShell stats | Manual: navigate to /tools; expect two rows (Bash, PowerShell) | [ ] |
| 2.4 | Teams tools (SendMessage, TaskCreate, etc.) recognized | `pytest tests/test_utils.py::TestTeamsTools -v` | [ ] |
| 2.5 | Teams tool timeline cards render semantically | Manual: view session with Teams operations; cards show operation type | [ ] |
| 2.6 | Subagent initialPrompt extracted and stored | `pytest tests/test_agent.py::TestSubagentFrontmatter::test_initial_prompt -v` | [ ] |
| 2.7 | Subagent initialPrompt displayed in card tooltip | Manual: hover subagent card; tooltip shows initial prompt | [ ] |
| 2.8 | Skill shell field parsed (bash/powershell) | `pytest tests/test_skill.py::TestFrontmatter::test_shell_field -v` | [ ] |
| 2.9 | Skill paths field parsed (list and string format) | `pytest tests/test_skill.py::TestFrontmatter::test_paths_list` and `test_paths_string -v` | [ ] |
| 2.10 | ${CLAUDE_SKILL_DIR} variable expanded in paths | `pytest tests/test_skill.py::TestFrontmatter::test_variable_expansion -v` | [ ] |
| 2.11 | Managed-settings.d fragments discovered | Manual: create 2+ fragments in managed-settings.d; curl /settings; expect merged result | [ ] |
| 2.12 | Fragment merging follows last-write-wins | Manual: modify fragment timestamps; verify merge order | [ ] |
| 2.13 | Settings UI shows fragment source attribution | Manual: navigate to settings; hover/expand field; see "(from team-defaults.json)" | [ ] |
| 2.14 | MCP metadata preserved in ToolResult model | `pytest tests/test_tool_result.py::TestMeta -v` | [ ] |
| 2.15 | "(large output)" badge renders when meta present | Manual: view tool result with maxResultSizeChars; badge visible | [ ] |
| 2.16 | All 14 new settings fields parse without error | `pytest tests/test_settings.py::TestNewFields -v` | [ ] |
| 2.17 | New settings fields render in SettingsPanel | Manual: navigate to settings; verify all 14 fields visible | [ ] |

### 9.3 Sprint 3 Verification

| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 3.1 | Thinking blocks preserved in AssistantMessage | `pytest tests/test_message.py::TestThinkingBlocks -v` | [ ] |
| 3.2 | Thinking block rendered in timeline when showThinkingSummaries=true | Manual: set showThinkingSummaries=true; view session; thinking visible | [ ] |
| 3.3 | Thinking block hidden when showThinkingSummaries=false | Manual: set showThinkingSummaries=false; view session; no thinking | [ ] |
| 3.4 | Hook conditional if field parsed from settings | `pytest tests/test_settings.py::TestHookConditional -v` | [ ] |
| 3.5 | Hook conditional if displayed in settings UI | Manual: navigate to settings hooks; see if conditions in hook rows | [ ] |
| 3.6 | Tool_use/result ID pairing validated on parse | `pytest tests/test_message.py::TestIdValidation -v` | [ ] |
| 3.7 | Resumption edge case detected (ID mismatch) | `pytest tests/test_session_resumption.py::TestIdMismatch -v` | [ ] |
| 3.8 | Orphaned tool_result warnings logged (not fatal) | Manual: parse sample with ID mismatch; check session metadata warnings | [ ] |
| 3.9 | Normal sessions with valid IDs show zero warnings | `pytest tests/test_session_resumption.py::TestNormalSessions -v` | [ ] |

---

## Section 10: Release Reference

| CC Version | Date | Headline Change | Impact | In Audit Window? |
|-----------|------|-----------------|--------|---|
| v2.1.81 | 2026-03-20 | Baseline | Audit window start | No (baseline) |
| v2.1.82 | 2026-03-21 | InstructionsLoaded hook | captain-hook expansion | Yes |
| v2.1.83 | 2026-03-23 | Bug fixes | Minor | No |
| v2.1.84 | 2026-03-24 | CwdChanged, FileChanged hooks | captain-hook expansion | Yes |
| v2.1.85 | 2026-03-25 | Agent Teams launch, session resumption regression | Teams discovery, resumption hardening | Yes |
| v2.1.86 | 2026-03-26 | PermissionDenied, TaskCreated hooks; TaskCreate tool | captain-hook expansion, tool recognition | Yes |
| v2.1.87 | 2026-03-27 | TaskCompleted, TeammateIdle hooks; subagent initialPrompt; skill shell field | captain-hook expansion, frontmatter parsing | Yes |
| v2.1.88 | 2026-03-28 | PowerShell tool; WorktreeCreate, WorktreeRemove hooks; skill paths field | Tool recognition, captain-hook expansion, frontmatter | Yes |
| v2.1.89 | 2026-03-30 | managed-settings.d fragment support | Settings merging | Yes |
| v2.1.90 | 2026-04-01 | Extended thinking, Elicitation hooks; MCP metadata; showThinkingSummaries setting; 14 new settings fields | Thinking visibility, hook expansion, metadata preservation, settings expansion | Yes |
| v2.1.91 | 2026-04-03 | Hook conditional if field; ElicitationResult hook | Hook settings, captain-hook expansion | Yes |
| v2.1.92 | 2026-04-04 | Resumption regression fix | Closes v2.1.85 regression | Yes |

---

## Appendix: Glossary of Claude Code Concepts

**Agent Teams**: Multi-user collaboration feature (v2.1.85+) for coordinated work on projects. Not the same as subagents (single-user task agents).

**Bare Mode**: Scripted session invocation with `--bare` flag. No GUI, no hooks, no interactive features. Appears empty to dashboard without proper detection.

**Extended Thinking**: Claude's reasoning process (formerly "thinking"). Displayed in UI when `showThinkingSummaries: true`.

**Hook Events**: Discrete actions fired by Claude Code (SessionStart, PreToolUse, etc.). Defined in captain-hook. 21 types total (10 original + 11 new).

**Hook Matchers**: Conditional rules in settings.json that filter when hooks run (e.g., `if: tool_name == 'Read'`). Different from hook events.

**Managed Settings**: Fragment-based settings system (`~/.claude/managed-settings.d/`) for modular config. Merges with base settings.json via last-write-wins.

**MCP Tools**: Tools from Model Context Protocol (Search, Read, Write, custom tools). Metadata (`_meta["anthropic/maxResultSizeChars"]`) annotates truncation.

**Session Resumption**: Continuing a session across version boundaries or after interruption. Regression v2.1.85–v2.1.91 caused tool_use/result ID mismatches; fixed in v2.1.92.

**Skill**: Reusable command prompt with frontmatter metadata (shell, paths, description). Invocable from prompt context.

---

**Document Status**: Ready for planning interview and Sprint 1 execution.
