# Documentation Verification Report

**Verification Date**: January 2025
**Verified Against**: Official Claude Code Documentation (code.claude.com/docs/en/hooks)
**Overall Accuracy**: 9/10

## Verification Summary

### VERIFIED CORRECT

| Item | Status |
|------|--------|
| **10 Hook Types** | All exist and correctly documented |
| PreToolUse, PostToolUse, UserPromptSubmit | Correct |
| SessionStart, SessionEnd | Correct |
| Stop, SubagentStop | Correct |
| PreCompact, PermissionRequest, Notification | Correct |
| **5 Common Fields** | All verified |
| session_id | Correct |
| transcript_path | Correct |
| cwd | Correct |
| permission_mode | Correct |
| hook_event_name | Correct |
| **Hook-Specific Fields** | Almost all correct |
| PreToolUse: tool_name, tool_input, tool_use_id | Correct |
| PostToolUse: +tool_response | Correct |
| UserPromptSubmit: prompt | Correct |
| SessionStart: source | Correct |
| SessionEnd: reason | Correct |
| Stop/SubagentStop: stop_hook_active | Correct |
| PreCompact: trigger, custom_instructions | Correct |
| **Environment Variables** | Correct |
| CLAUDE_PROJECT_DIR | Correct |
| CLAUDE_CODE_REMOTE | Correct |
| CLAUDE_ENV_FILE (SessionStart only) | Correct |
| **Exit Codes** | Correct |
| Exit 0 = success | Correct |
| Exit 2 = block | Correct |
| **Recent Features** | Mostly correct |
| Prompt-based hooks (type: "prompt") | Correct |
| Component-scoped hooks | Correct |
| once: true flag | Correct |

### CORRECTIONS MADE

1. **`match_tools` → `matcher`**
   - Original: Used `match_tools` parameter
   - Corrected: Uses `matcher` with regex patterns
   - Config structure is `matcher: "pattern"` at the hook group level

2. **Hook Configuration Structure**
   - Clarified the nested structure: `matcher` → `hooks` → `command/prompt`

3. **Execution Behavior**
   - Added: Hooks run in **parallel** (not sequential)
   - Added: Identical commands are **deduplicated**

4. **Timeout Defaults**
   - Commands: 60 seconds
   - Prompt-based: 30 seconds

### ADDITIONAL FIELDS DISCOVERED

These advanced output fields exist but were not in original documentation:

| Field | Purpose | Hook Types |
|-------|---------|------------|
| `suppressOutput` | Hide stdout from transcript | All |
| `systemMessage` | Warning shown to user | All |
| `permissionDecisionReason` | Explanation for permission decision | PreToolUse |
| `behavior` | For PermissionRequest (allow/deny) | PermissionRequest |
| `interrupt` | For deny decisions | PermissionRequest |

### SOURCE REFERENCES

- [Hooks Reference](https://code.claude.com/docs/en/hooks) - Complete specification
- [Hooks Guide](https://code.claude.com/docs/en/hooks-guide) - Quick start
- [GitHub CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) - Version history

### VERSION NOTES

Features confirmed from CHANGELOG:
- v1.0.18: SessionStart hook added
- v1.0.41: hook_event_name field, timeout configuration
- v1.0.48: PreCompact hook added
- v1.0.85: SessionEnd hook introduced
- v1.0.112: systemMessage support for SessionEnd
- v2.0.41: model parameter for prompt-based Stop hooks
- v2.0.54: PermissionRequest hook for 'always allow' suggestions
- v2.0.68: disableAllHooks setting
- v2.1.0: Agent-scoped hooks, once: true flag, prompt/agent hook types from plugins
- v2.1.0: Fixed PreToolUse updatedInput with 'ask' permission decision

---

*This verification was performed by an independent research agent cross-referencing official documentation.*
