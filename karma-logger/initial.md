# Karma Logger - Initial Research

## Session & Subagent Tracking in Claude Code CLI

**Research Date:** 2026-01-08
**Verified by:** Spawning 3 test subagents and inspecting JSONL logs

---

## 1. Log File Locations

```
~/.claude/projects/{project-path-encoded}/
├── {session-uuid}.jsonl          # Main session logs
└── agent-{7-char-hex-id}.jsonl   # Per-subagent logs
```

**Project path encoding:** Forward slashes replaced with dashes
Example: `/Users/jayantdevkar/Documents/GitHub/claude-karma` → `-Users-jayantdevkar-Documents-GitHub-claude-karma`

---

## 2. Agent ID System (Verified)

When `Task` tool spawns a subagent, Claude Code assigns a **7-character hex ID**.

### Test Results (2026-01-08)

| Agent Type | Task | Agent ID | Model |
|------------|------|----------|-------|
| Explore | Python file count | `ad44c70` | claude-haiku-4-5-20251001 |
| Explore | TypeScript scan | `a987c02` | claude-haiku-4-5-20251001 |
| Bash | Echo command | `af9b2a3` | claude-haiku-4-5-20251001 |

### Key Observations
- All subagents use **Haiku** model by default (cost optimization)
- Main session uses **Opus** model
- Each agent gets its own dedicated JSONL file

---

## 3. JSONL Log Structure (Verified)

Each log entry contains these fields:

```json
{
  "agentId": "ad44c70",
  "isSidechain": true,
  "userType": "external",
  "parentUuid": "5ccdf184-a86c-4b8f-90b6-d6b5a0cf5c83",
  "sessionId": "...",
  "uuid": "...",
  "timestamp": "2026-01-08T...",
  "type": "assistant|user",
  "version": "2.1.1",
  "cwd": "/path/to/project",
  "gitBranch": "initial-commit",
  "requestId": "req_...",
  "message": {
    "model": "claude-haiku-4-5-20251001",
    "usage": {
      "input_tokens": 3,
      "output_tokens": 1,
      "cache_creation_input_tokens": 0,
      "cache_read_input_tokens": 0
    },
    "content": [...]
  }
}
```

### Key Fields for Tracking

| Field | Purpose |
|-------|---------|
| `agentId` | Unique 7-char hex identifier |
| `isSidechain` | `true` = subagent, `false` = main session |
| `userType` | `"external"` for subagents |
| `parentUuid` | Links entry to parent message |
| `message.model` | Model used (haiku/opus) |
| `message.usage.*` | Token consumption |

---

## 4. Token Usage Per Agent (Verified)

```bash
# Aggregate tokens for test agents
Agent ad44c70: {"entries":8, "input":20, "output":112, "model":"haiku"}
Agent a987c02: {"entries":10, "input":24, "output":37, "model":"haiku"}
Agent af9b2a3: {"entries":4, "input":7904, "output":90, "model":"haiku"}
```

**Note:** Bash agent (af9b2a3) has higher input tokens due to system context.

---

## 5. Monitoring Commands

### Real-time Agent Activity
```bash
tail -f ~/.claude/projects/*/*.jsonl 2>/dev/null | \
  jq -c 'select(.agentId) | {agentId, model: .message.model, tokens: (.message.usage.input_tokens + .message.usage.output_tokens)}'
```

### Aggregate Token Usage Per Agent
```bash
for f in ~/.claude/projects/<project>/agent-*.jsonl; do
  agent=$(basename $f .jsonl | sed 's/agent-//')
  cat "$f" | jq -s '{
    agent: "'$agent'",
    input: [.[] | .message.usage.input_tokens // 0] | add,
    output: [.[] | .message.usage.output_tokens // 0] | add,
    model: [.[] | select(.message.model) | .message.model][0]
  }'
done
```

### List Recent Subagents
```bash
find ~/.claude/projects -name "agent-*.jsonl" -mmin -60 | \
  xargs -I{} sh -c 'echo "$(basename {})": $(jq -s "length" {})" entries"'
```

---

## 6. Hierarchy Tracking

Subagent logs include `parentUuid` which links back to the parent session's message UUID.

```
Main Session (session-uuid.jsonl)
  └── Message UUID: 5ccdf184-...
        └── Spawns agent-ad44c70.jsonl
              └── parentUuid: 5ccdf184-...
```

This enables reconstruction of agent→subagent trees.

---

## 7. Limitations

1. **No native OTEL agent hierarchy** - Must use JSONL logs
2. **No cross-session agent linking** - Each session is isolated
3. **Slug field often null** - Subagents don't always get slugs
4. **No built-in cost tracking** - Must calculate from token counts

---

## 8. Karma Logger Implications

For building a karma scoring system:

### Data Available
- Token usage per agent
- Tool calls made
- Model selection
- Timestamps and durations (calculable)
- Parent-child relationships

### Recommended Approach
1. **Tail JSONL files** in real-time for live tracking
2. **Parse on session end** for aggregate metrics
3. **Store agent IDs** from Task tool responses
4. **Build hierarchy tree** using parentUuid links

### Sample Tracking Schema
```json
{
  "session_id": "uuid",
  "agents": [
    {
      "agent_id": "ad44c70",
      "type": "Explore",
      "model": "haiku",
      "tokens": {"input": 20, "output": 112},
      "parent_uuid": "5ccdf184-...",
      "tools_used": ["Glob", "Grep"],
      "duration_ms": 1234
    }
  ]
}
```

---

## References

- Log location: `~/.claude/projects/`
- Agent ID format: 7-character hex
- Models: `claude-haiku-4-5-20251001`, `claude-opus-4-5-20251101`
