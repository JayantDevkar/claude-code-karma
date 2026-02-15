# Timeline Event Category Mapping Analysis

## Research Goal
Understand ALL message types in Claude Code JSONL sessions and how they map to timeline event categories, identifying which message types are incorrectly mapped to "user_prompt".

## Complete Message Type Inventory

### Message Types from `api/models/message.py`

| Message Type | Python Class | Type Field | Subtype Field |
|--------------|--------------|------------|---------------|
| User messages | `UserMessage` | `"user"` | - |
| Assistant responses | `AssistantMessage` | `"assistant"` | - |
| File snapshots | `FileHistorySnapshot` | `"file-history-snapshot"` | - |
| Session titles | `SessionTitleMessage` | `"summary"` | - |
| Compaction markers | `CompactBoundaryMessage` | `"system"` | `"compact_boundary"` |
| Queue operations | `QueueOperationMessage` | `"queue-operation"` | - |
| Progress updates | `ProgressMessage` | `"progress"` | - |

**Total: 7 distinct message types**

## Timeline Event Generation Logic

### Source: `api/services/conversation_endpoints.py::build_conversation_timeline()`

The timeline builder processes messages in a single pass:

```python
for msg in conversation.iter_messages():
    if isinstance(msg, UserMessage):
        # Process user messages
    elif isinstance(msg, AssistantMessage):
        # Process assistant messages
    # NO OTHER CASES - other message types are silently skipped
```

### Message Types Processed

#### 1. UserMessage (type: "user")

**Processing logic (lines 67-103):**
- **Tool result messages**: SKIPPED (lines 69-71)
  - Detected via `parse_tool_result_content(msg.content)`
  - These are merged into tool call events instead
- **Actual user prompts**: Create timeline event (lines 74-103)
  - Detect command from `<command-message>` tags
  - Event type determined by `_detect_command_from_content()`:
    - No command → `event_type="prompt"`
    - Builtin command → `event_type="prompt"`
    - Plugin skill → `event_type="skill_invocation"`
    - User command → `event_type="command_invocation"`
  - **Actor**: `"user"`
  - **Actor type**: `"user"`

#### 2. AssistantMessage (type: "assistant")

**Processing logic (lines 105-200):**
Iterates over `content_blocks`, creating events for each:

##### ToolUseBlock (lines 118-168)
- **TodoWrite** → `event_type="todo_update"` (line 137)
- **Task** → `event_type="subagent_spawn"` (line 139)
- **Skill** → `event_type="skill_invocation"` or `"command_invocation"` (lines 141-146)
  - Extracts skill name from `block.input.get("skill")`
  - Plugin skills (contain `:`) → `"skill_invocation"`
  - User commands (no `:`) → `"command_invocation"`
- **Other tools** → `event_type="tool_call"` (default, line 155)
- **Actor**: Session or subagent ID (lines 107-112)
- **Actor type**: `"session"` or `"subagent"`

##### ThinkingBlock (lines 170-183)
- `event_type="thinking"` (line 175)

##### TextBlock (lines 185-200)
- `event_type="response"` (line 192)
- Only if text length > 50 characters

### Message Types NOT Processed (Silently Skipped)

The following message types are **NEVER** converted to timeline events:

| Message Type | Why Skipped |
|--------------|-------------|
| FileHistorySnapshot | No handler in if/elif chain |
| SessionTitleMessage | No handler in if/elif chain |
| CompactBoundaryMessage | No handler in if/elif chain |
| QueueOperationMessage | No handler in if/elif chain |
| ProgressMessage | No handler in if/elif chain |

**These message types CANNOT be the source of the "user_prompt" miscategorization issue.**

## Timeline Event Types → Frontend Categories

### Source: `frontend/.../TimelineEventCard.svelte::getCategoryFromEvent()`

```typescript
function getCategoryFromEvent(event: TimelineEvent): EventCategory {
  const type = event.event_type;
  
  // User prompts and commands
  if (type === 'prompt' || type === 'skill_invocation' || type === 'command_invocation') {
    return 'user_prompt';
  }
  
  // Tool usage
  if (type === 'tool_call' || type === 'subagent_spawn' || type === 'todo_update') {
    return 'tool_usage';
  }
  
  // Assistant responses
  if (type === 'thinking' || type === 'response') {
    return 'assistant_response';
  }
  
  return 'user_prompt'; // Fallback
}
```

### Category Mapping Table

| event_type | Frontend Category | Source Message | Actor |
|------------|-------------------|----------------|-------|
| `prompt` | `user_prompt` ✓ | UserMessage | `user` |
| `skill_invocation` | `user_prompt` ⚠️ | **UserMessage OR AssistantMessage** | **`user` OR `session`** |
| `command_invocation` | `user_prompt` ⚠️ | **UserMessage OR AssistantMessage** | **`user` OR `session`** |
| `tool_call` | `tool_usage` ✓ | AssistantMessage | `session` |
| `subagent_spawn` | `tool_usage` ✓ | AssistantMessage | `session` |
| `todo_update` | `tool_usage` ✓ | AssistantMessage | `session` |
| `thinking` | `assistant_response` ✓ | AssistantMessage | `session` |
| `response` | `assistant_response` ✓ | AssistantMessage | `session` |

## ROOT CAUSE IDENTIFIED

### The Problem

**`skill_invocation` and `command_invocation` events are categorized as `user_prompt` regardless of their `actor` field.**

This is INCORRECT because:

1. **User prompts** with `/skill` or `/command` create:
   - UserMessage with `<command-message>` tags
   - `event_type="skill_invocation"` or `"command_invocation"`
   - `actor="user"`, `actor_type="user"`
   - **Should be** `user_prompt` ✓

2. **Assistant invocations** of the Skill tool create:
   - AssistantMessage with ToolUseBlock(name="Skill")
   - `event_type="skill_invocation"` or `"command_invocation"`
   - `actor="session"` or subagent ID, `actor_type="session"` or `"subagent"`
   - **Currently categorized as** `user_prompt` ❌
   - **Should be** `tool_usage` ✓

### Evidence from Code

**Backend (conversation_endpoints.py, lines 141-153):**
```python
elif block.name == "Skill":
    # Extract skill details from tool input
    skill_name = block.input.get("skill", "Unknown")
    is_plugin = ":" in skill_name
    is_builtin = skill_name in BUILTIN_CLI_COMMANDS
    event_type = "skill_invocation" if is_plugin else "command_invocation"
    # ...
    # This is an AssistantMessage, but event_type is skill_invocation/command_invocation
```

**Frontend (getCategoryFromEvent):**
```typescript
if (type === 'prompt' || type === 'skill_invocation' || type === 'command_invocation') {
  return 'user_prompt';  // ❌ Doesn't check actor field!
}
```

## Impact

### Sessions Affected
Any session where Claude:
1. Spawns a subagent via Task tool with `subagent_type` parameter
2. Invokes a skill/command via Skill tool
3. Uses OMC skills (e.g., `/oh-my-claudecode:autopilot`)

### User Experience Impact
- Timeline shows assistant tool invocations as "User Prompts"
- Filter by category shows incorrect events
- Event counts by category are wrong
- Visual confusion about what the user vs assistant did

## Solution

### Option 1: Fix Frontend (Recommended)
Update `getCategoryFromEvent()` to check the `actor` field:

```typescript
function getCategoryFromEvent(event: TimelineEvent): EventCategory {
  const type = event.event_type;
  const actor = event.actor;
  
  // User prompts (only if actor is 'user')
  if (actor === 'user' && 
      (type === 'prompt' || type === 'skill_invocation' || type === 'command_invocation')) {
    return 'user_prompt';
  }
  
  // Tool usage (including assistant skill/command invocations)
  if (type === 'tool_call' || type === 'subagent_spawn' || type === 'todo_update' ||
      type === 'skill_invocation' || type === 'command_invocation') {
    return 'tool_usage';
  }
  
  // Assistant responses
  if (type === 'thinking' || type === 'response') {
    return 'assistant_response';
  }
  
  return 'tool_usage'; // Fallback (changed from user_prompt)
}
```

### Option 2: Fix Backend Event Types
Create distinct event types for user vs assistant skill invocations:
- `user_skill_invocation` / `user_command_invocation` (UserMessage)
- `assistant_skill_invocation` / `assistant_command_invocation` (AssistantMessage)

**Drawback**: More complex, requires schema changes

### Option 3: Add Category Field to API
Have the backend compute the category and include it in the TimelineEvent schema.

**Drawback**: Frontend loses flexibility

## Recommended Fix

**Option 1** is the best solution:
- Minimal code change
- Preserves existing event_type semantics
- Frontend uses already-available `actor` field
- No breaking changes to API

## Testing Strategy

1. Create a test session with:
   - User prompt: "Hello"
   - User command: "/help"
   - User skill: "/oh-my-claudecode:plan"
   - Assistant skill invocation (Task tool spawn)
   - Assistant command invocation (Skill tool with user command)

2. Verify timeline categories:
   - User events → `user_prompt`
   - Assistant skill/command invocations → `tool_usage`
   - Other assistant actions → `tool_usage` or `assistant_response`

3. Check filter behavior:
   - Filter by "User Prompts" shows only user actions
   - Filter by "Tool Usage" shows assistant skill/command invocations
