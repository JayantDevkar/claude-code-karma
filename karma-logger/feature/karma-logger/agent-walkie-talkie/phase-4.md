# Phase 4: Hook Templates

## Objective

Provide ready-to-use Claude Code hook definitions that automatically broadcast agent status via `karma radio`.

## Prerequisites (BLOCKING - DO NOT IMPLEMENT UNTIL VALIDATED)

**STATUS: UNVALIDATED** - Claude Code hook system has not been confirmed to work as specified.

Before implementing this phase, the following MUST be validated:

### Hook System Validation Checklist
- [ ] **BLOCKER**: Confirm Claude Code supports hook frontmatter in agent definitions
- [ ] **BLOCKER**: Verify environment variables are provided by Claude Code runtime:
  - `$TOOL_NAME`, `$TOOL_INPUT`, `$TOOL_OUTPUT`, `$TOOL_ERROR`
  - `$AGENT_ID`, `$SESSION_ID`, `$PARENT_SESSION_ID`
  - `$STOP_REASON`, `$AGENT_RESULT`
- [ ] Test minimal hook execution end-to-end
- [ ] Document hook execution model (sync/async, error handling)
- [ ] Validation completed by: __________ (date)
- [ ] Validated by: __________ (engineer name)

### Validation Steps
1. Create test agent with single PreToolUse hook
2. Run agent and verify hook command executes
3. Confirm environment variables are populated
4. Test hook failure behavior (does agent continue or abort?)
5. **Document actual available env vars** (may differ from spec above)

### If Validation Fails
**Fall back to Manual Mode:** Agents call `karma radio` directly in prompts.
- Skip hook templates entirely
- Document as "manual mode" in README
- Consider re-evaluating when Claude Code updates hook support

**If hooks are not supported:** Fall back to explicit instrumentation (agents call `karma radio` directly in prompts). Document as "manual mode" vs future "hook mode".

## Dependencies

- **Phase 3**: karma radio CLI must be complete

## Deliverables

```
templates/hooks/
├── walkie-talkie-hooks.yaml    # Copy-paste hook definitions
├── agent-explore.yaml          # Example: Explore agent with hooks
├── agent-plan.yaml             # Example: Plan agent with hooks
└── README.md                   # Setup instructions
```

## Tasks

### 4.1 Standard Hook Definitions

```yaml
# templates/hooks/walkie-talkie-hooks.yaml
# Add to your agent's frontmatter or .claude/settings.json

hooks:
  PreToolUse:
    - matcher: "*"
      command: |
        karma radio set-status active \
          --tool "$TOOL_NAME" \
          --metadata "{\"operation\":\"starting\"}"

  PostToolUse:
    - matcher: "*"
      command: |
        karma radio report-progress \
          --tool "$TOOL_NAME" \
          --message "completed"

  Stop:
    - command: |
        karma radio set-status completed \
          --metadata "{\"exitReason\":\"$STOP_REASON\"}"
```

### 4.2 Available Environment Variables

Document which vars Claude Code provides to hooks:

| Variable | Hook | Description |
|----------|------|-------------|
| `TOOL_NAME` | PreToolUse, PostToolUse | Name of tool being executed |
| `TOOL_INPUT` | PreToolUse | JSON string of tool input |
| `TOOL_OUTPUT` | PostToolUse | JSON string of tool result |
| `TOOL_ERROR` | PostToolUse | Error message if tool failed |
| `STOP_REASON` | Stop | Why agent stopped (completed, error, etc.) |
| `SESSION_ID` | All | Current session ID |
| `AGENT_ID` | All (if subagent) | Subagent's ID |
| `PARENT_SESSION_ID` | All (if subagent) | Parent's session ID |

### 4.3 Example: Explore Agent

```yaml
# templates/hooks/agent-explore.yaml
---
name: explore-agent
description: Explores codebase for patterns
model: haiku
context: fork

# Walkie-talkie status broadcasting
hooks:
  PreToolUse:
    - matcher: "Glob"
      command: |
        karma radio set-status active \
          --tool "Glob" \
          --metadata "{\"pattern\":\"$TOOL_INPUT\"}"

    - matcher: "Grep"
      command: |
        karma radio set-status active \
          --tool "Grep" \
          --metadata "{\"searching\":true}"

    - matcher: "Read"
      command: |
        karma radio report-progress \
          --tool "Read" \
          --message "Reading file"

  PostToolUse:
    - matcher: "*"
      command: |
        karma radio report-progress \
          --tool "$TOOL_NAME" \
          --message "done"

  Stop:
    - command: |
        # Write result to temp file for parent
        echo "$AGENT_RESULT" > /tmp/explore-result-$AGENT_ID.json
        karma radio publish-result /tmp/explore-result-$AGENT_ID.json
        rm /tmp/explore-result-$AGENT_ID.json
---

Explore the codebase for {{pattern}} and report findings.
```

### 4.4 Example: Plan Agent

```yaml
# templates/hooks/agent-plan.yaml
---
name: plan-agent
description: Creates implementation plans
model: sonnet
context: fork

hooks:
  PreToolUse:
    - matcher: "Read"
      command: |
        karma radio report-progress \
          --step "research" \
          --message "Reading reference files"

    - matcher: "Write"
      command: |
        karma radio set-status active \
          --metadata "{\"phase\":\"writing_plan\"}"

  PostToolUse:
    - matcher: "Write"
      command: |
        karma radio report-progress \
          --step "writing" \
          --percent 80 \
          --message "Plan written"

  Stop:
    - command: |
        karma radio set-status completed \
          --metadata "{\"planReady\":true}"
---

Create an implementation plan for: {{task}}
```

### 4.5 Conditional Hooks

```yaml
hooks:
  PreToolUse:
    # Only broadcast for long-running tools
    - matcher: "Bash"
      command: |
        karma radio set-status active --tool "Bash"

    # Skip quick lookups
    - matcher: "Glob"
      # No command = no broadcast
```

### 4.6 Error Handling in Hooks

```yaml
hooks:
  PostToolUse:
    - matcher: "*"
      command: |
        if [ -n "$TOOL_ERROR" ]; then
          karma radio set-status failed \
            --metadata "{\"error\":\"$TOOL_ERROR\",\"tool\":\"$TOOL_NAME\"}"
        else
          karma radio report-progress --tool "$TOOL_NAME" --message "success"
        fi

  Stop:
    - command: |
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
          karma radio set-status failed \
            --metadata "{\"exitCode\":$EXIT_CODE}"
        else
          karma radio set-status completed
        fi
```

### 4.7 Parent-Child Coordination

```yaml
# Parent agent: waits for child before proceeding
hooks:
  PostToolUse:
    - matcher: "Task"  # After spawning subagent
      command: |
        # Extract child agent ID from tool output
        CHILD_ID=$(echo "$TOOL_OUTPUT" | jq -r '.agentId')

        # Wait for child to complete (blocks until done or timeout)
        karma radio wait-for "$CHILD_ID" completed --timeout 60000

        # Get child's result
        karma radio get-status --agent "$CHILD_ID"
```

### 4.8 Setup Instructions README

```markdown
# Walkie-Talkie Hook Setup

## Prerequisites

1. karma-logger installed: `npm install -g karma-logger`
2. `karma watch` running (starts the radio server)

## Quick Setup

### Option A: Per-Agent Hooks

Add to your agent's YAML frontmatter:

\`\`\`yaml
---
name: my-agent
hooks:
  PreToolUse:
    - matcher: "*"
      command: karma radio set-status active --tool "$TOOL_NAME"
  Stop:
    - command: karma radio set-status completed
---
\`\`\`

### Option B: Global Hooks

Add to `~/.claude/settings.json`:

\`\`\`json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "*", "command": "karma radio set-status active --tool \"$TOOL_NAME\"" }
    ]
  }
}
\`\`\`

## Verify It Works

1. Run `karma watch --ui` in one terminal
2. Start a Claude Code session
3. Watch agent status updates appear in real-time
```

## Tests

```typescript
describe('Hook templates', () => {
  test('walkie-talkie-hooks.yaml is valid YAML');
  test('all example agents have valid frontmatter');
  test('hook commands use correct karma radio syntax');
});
```

## Acceptance Criteria

- [ ] Standard hooks template works copy-paste
- [ ] Example agents demonstrate common patterns
- [ ] Error handling documented
- [ ] Parent-child coordination example works
- [ ] README has clear setup steps

## Estimated Complexity

- Lines of code: ~50 (YAML templates)
- Documentation: ~200 lines
- Risk: **HIGH** (depends on unvalidated Claude Code hook system)

## Implementation Priority

**DEFER this phase** until hook system is validated. Implement Phases 1, 2, 3, 5 first.
Manual mode (agents calling `karma radio` in prompts) provides equivalent functionality without hook dependency.

## Troubleshooting

**Hooks not executing:**
- Check `karma watch` is running: `ps aux | grep karma`
- Verify socket exists: `ls -la /tmp/karma-radio.sock`
- Enable hook debugging: `export KARMA_DEBUG_HOOKS=1`

**Environment variables missing:**
- Hooks receive env vars from Claude Code runtime
- Test manually: `echo $TOOL_NAME` in hook command
- Fallback: Parse from context if vars unavailable

**Shell escaping issues:**
- Use environment variable expansion instead of inline JSON
- Test hooks manually before adding to agent definition

## Alternative: Manual Instrumentation

If hook system is not available, agents can call radio directly:

```yaml
prompt: |
  Before each tool use, broadcast status:
  Run: karma radio set-status active --tool "$CURRENT_TOOL"

  After task completion:
  Run: karma radio set-status completed
```

This is more verbose but doesn't depend on hook infrastructure.
