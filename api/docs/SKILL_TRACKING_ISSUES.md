# Skill Invocation Tracking — Issues & Design

## Current State (branch: fix/command-skill-tracking)

### Three Invocation Categories

| Category | DB Value | Meaning | UI Label |
|----------|----------|---------|----------|
| Manual | `slash_command` | User explicitly typed `/command` or `/skill` | "Manual" |
| Auto | `skill_tool` | Claude auto-invoked via `Skill` tool without user typing `/command` | "Auto" |
| Mentioned | `text_detection` | User typed `/command` in text but Claude never invoked it | "Mentioned (Not invoked)" |

### Detection Sources

| Source | How Detected | Code Location |
|--------|-------------|---------------|
| `slash_command` | `<command-message>` XML tags in user prompt | `parse_command_from_content()` in `command_helpers.py` |
| `text_detection` | `/command` regex pattern in plain-text user prompt | `detect_slash_commands_in_text()` in `command_helpers.py` |
| `skill_tool` | `Skill` tool use block in assistant message content | `session.py` line ~393 (ToolUseBlock with name=="Skill") |

### Dedup Logic (`_dedup_invocation_sources`)

Combines signals from the same session into the correct category:

| User typed `/command`? | Claude called Skill tool? | Result |
|------------------------|--------------------------|--------|
| Yes (XML tags) | Yes | `slash_command` (Manual) |
| Yes (plain text) | Yes | `slash_command` (Manual) — **upgraded from text_detection+skill_tool** |
| Yes (plain text) | No | `text_detection` (Mentioned) |
| No | Yes | `skill_tool` (Auto) |
| Yes (XML tags) | No | `slash_command` (Manual) — command fired but skill not invoked |

---

## Bugs Fixed in This Branch

### Bug 1: `text_detection` + `skill_tool` → showed as "Auto" (should be "Manual")

**Scenario**: User types `/brainstorming` in plain text (no XML tags), Claude invokes `Skill` tool.

**Root cause**: Dedup treated `skill_tool` as higher priority than `text_detection`, absorbing it. Result was `skill_tool` (auto).

**Fix**: When both `text_detection` and `skill_tool` exist for the same skill (and no `slash_command`), upgrade to `slash_command` (manual). User typed it AND Claude ran it = manual.

### Bug 2: Short-form skill names not recognized by `classify_invocation()`

**Scenario**: User types `/brainstorming` in text. `detect_slash_commands_in_text()` finds `brainstorming`. But `classify_invocation("brainstorming")` returns `"command"` (not `"skill"`) because:
- No `:` in name
- Not a custom skill file (`~/.claude/skills/brainstorming/` doesn't exist)
- Not a plugin directory (`brainstorming` is an entry inside `superpowers`, not a plugin itself)

**Root cause**: Code classified BEFORE expanding the name. `expand_plugin_short_name("brainstorming")` → `"superpowers:brainstorming"` (which classifies as skill), but expansion happened after classification.

**Fix**: Expand short names first, then classify. `brainstorming` → `superpowers:brainstorming` → classified as `"skill"`.

---

## Open Issue: Command vs Skill Distinction

### Plugin Architecture

Plugins can define three types of invocables:

```
plugin-name/
├── commands/        # Thin wrappers — user types /command-name
│   └── brainstorm.md
├── skills/          # Rich skills — invoked via Skill tool
│   └── brainstorming/
│       └── SKILL.md
└── agents/          # Agent definitions
    └── code-reviewer.md
```

**Commands** are short `.md` files that typically instruct Claude to invoke a skill:
```markdown
# commands/brainstorm.md
Invoke the superpowers:brainstorming skill and follow it exactly
```

**Skills** are full skill definitions with prompts, workflows, etc.

### The Command→Skill Chain

When a user types `/brainstorm`:

```
User types /brainstorm
    ↓
Claude Code wraps in XML: <command-message>superpowers:brainstorm</command-message>
    ↓
Command content loaded: "Invoke the superpowers:brainstorming skill"
    ↓
Claude calls Skill tool: Skill(skill: "brainstorming")
    ↓
"Launching Skill: brainstorming" message
    ↓
Skill content (SKILL.md) loaded and executed
```

### Current Tracking Problem

| What happens | What we detect | DB entry |
|---|---|---|
| User types `/brainstorm` | `parse_command_from_content()` → `superpowers:brainstorm` | `session_skills` as `slash_command` (**wrong table** — this is a command) |
| Claude calls `Skill(brainstorming)` | Skill tool block → `superpowers:brainstorming` | `session_skills` as `skill_tool` |

**Problems:**
1. `superpowers:brainstorm` (a command) is classified as `"skill"` because it contains `:`. Goes to `session_skills` instead of `session_commands`.
2. `superpowers:brainstorm` ≠ `superpowers:brainstorming` — dedup can't link the command to the skill it triggers.
3. The skill (`brainstorming`) shows as "Auto" even though user explicitly typed `/brainstorm`.

### Why `classify_invocation()` Gets It Wrong

```python
def classify_invocation(name):
    if name in BUILTIN_CLI_COMMANDS:  # /exit, /model, etc.
        return "builtin"
    if ":" in name:                    # <-- superpowers:brainstorm hits this
        return "skill"                 #     but it's actually a COMMAND
    if _is_custom_skill(name):
        return "skill"
    if _is_plugin_skill(name):
        return "skill"
    return "command"
```

The `":"` check assumes all `plugin:entry` names are skills, but they can also be commands or agents.

### Known Command→Skill Mappings (This Machine)

| Plugin | Command | Triggers Skill |
|--------|---------|---------------|
| superpowers | `brainstorm` | `brainstorming` |
| superpowers | `write-plan` | `writing-plans` |
| superpowers | `execute-plan` | `executing-plans` |
| oh-my-claudecode | `omc-setup` | (setup flow) |
| oh-my-claudecode | `ralplan` | (planning flow) |

### Fixes Applied

**Step 1: Entry type awareness** (`command_helpers.py`)

Added `_build_entry_type_map()` which scans plugin directories to map `plugin:entry` → `"command"|"skill"|"agent"` based on which subdirectory (`commands/`, `skills/`, `agents/`) the entry lives in. Uses `TTLCache(maxsize=1, ttl=60)` for caching.

Refactored `_collect_plugin_entries()` to return `dict[str, str]` (entry_name → kind) instead of `list[str]`.

**Step 2: Fixed `classify_invocation()`** (`command_helpers.py`)

The `":" in name` branch now consults `_build_entry_type_map()`:
- `superpowers:brainstorm` → `"command"` (it's in `commands/`)
- `superpowers:brainstorming` → `"skill"` (it's in `skills/`)
- Unknown `plugin:entry` → `"skill"` (backward compat)

**Step 3: Command→Skill linkage** (`session.py`)

Added `_link_command_to_skill()` which upgrades `skill_tool` entries to `slash_command` when a same-plugin command exists in `user_prompt_commands`. Called before `_dedup_invocation_sources()`.

Heuristic: same plugin prefix = linked. This covers the common pattern where commands exist specifically to trigger skills.

---

## DB Schema Reference

```sql
-- Skills tracking
CREATE TABLE session_skills (
    session_uuid TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invocation_source TEXT NOT NULL DEFAULT 'skill_tool',  -- slash_command | skill_tool | text_detection
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, skill_name)
);

-- Commands tracking (separate table)
CREATE TABLE session_commands (
    session_uuid TEXT NOT NULL,
    command_name TEXT NOT NULL,
    invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, command_name)
);
```

## Files Involved

| File | Role |
|------|------|
| `api/models/session.py` | Main detection loop (`_compute_and_cache`), dedup logic |
| `api/command_helpers.py` | `classify_invocation()`, `parse_command_from_content()`, `detect_slash_commands_in_text()`, `expand_plugin_short_name()` |
| `api/db/indexer.py` | Writes `session_skills` and `session_commands` to SQLite |
| `api/db/queries.py` | Reads skills data for API endpoints |
| `api/routers/skills.py` | Skills API endpoints |
| `frontend/src/routes/skills/[skill_name]/+page.svelte` | Skills detail page UI |
