# Claude Code Agent Telemetry & Tracking

## Summary

This document captures findings about tracking agent/subagent activity in Claude Code CLI.

---

## 1. OpenTelemetry Support

Claude Code has built-in OTEL export for metrics and events.

### Environment Variables

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp          # or console, prometheus
export OTEL_LOGS_EXPORTER=otlp             # or console
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### Metrics Exported

| Metric | Description |
|--------|-------------|
| `claude_code.token.usage` | Input/output tokens per request |
| `claude_code.cost.usage` | Cost in USD |
| `claude_code.session.count` | Session counter |
| `claude_code.tool_result` | Tool execution results |

### Events Exported

- `api_request` - Each Claude API call
- `tool_result` - Tool execution outcome
- `tool_decision` - Which tool was selected
- `user_prompt` - User message events

### Limitation

**OTEL telemetry does NOT include native `agent_id` or `subagent_id` attributes.** It tracks tool usage but lacks hierarchy granularity for agent→subagent relationships.

---

## 2. Internal JSONL Logs (Agent Hierarchy Tracking)

Claude Code writes detailed conversation logs that DO include agent hierarchy info.

### Log Location

```
~/.claude/projects/<project-hash>/<session-uuid>.jsonl     # Main session
~/.claude/projects/<project-hash>/agent-<agentId>.jsonl    # Per-agent logs
```

### Key Fields for Agent Tracking (VERIFIED 2026-01-07)

| Field | Description |
|-------|-------------|
| `agentId` | Unique 7-char hex ID assigned when Task tool spawns agent |
| `slug` | Session name (e.g., "reflective-orbiting-hanrahan") |
| `isSidechain` | `true` if this is a subagent, `false` for main session |
| `parentUuid` | Links subagent entry to parent message UUID |
| `sessionId` | Session UUID identifier |
| `uuid` | Unique ID for each log entry |
| `type` | Entry type: `user`, `assistant`, or tool results |
| `userType` | `"external"` for subagents |
| `version` | Claude Code CLI version (e.g., "2.1.1") |
| `cwd` | Working directory path |
| `gitBranch` | Current git branch |
| `timestamp` | ISO 8601 timestamp |
| `requestId` | Anthropic API request ID |

### Model & Token Fields

| Field | Description |
|-------|-------------|
| `message.model` | Model ID (e.g., `claude-haiku-4-5-20251001`, `claude-opus-4-5-20251101`) |
| `message.id` | API message ID |
| `message.usage.input_tokens` | Input tokens for this request |
| `message.usage.output_tokens` | Output tokens generated |
| `message.usage.cache_creation_input_tokens` | Tokens written to cache |
| `message.usage.cache_read_input_tokens` | Tokens read from cache |
| `message.usage.cache_creation.ephemeral_5m_input_tokens` | 5-minute ephemeral cache |
| `message.usage.cache_creation.ephemeral_1h_input_tokens` | 1-hour ephemeral cache |
| `message.usage.service_tier` | Service tier (e.g., "standard") |
| `message.stop_reason` | Why generation stopped |

### Tool Tracking Fields

| Field | Description |
|-------|-------------|
| `message.content[].type` | `text`, `tool_use`, or `tool_result` |
| `message.content[].name` | Tool name (for tool_use) |
| `message.content[].input` | Tool parameters (for tool_use) |
| `message.content[].id` | Tool use ID for linking |
| `tool_use_id` | Links tool_result to tool_use |

### Real-time Monitoring Commands

```bash
# Watch all agent activity
tail -f ~/.claude/projects/*/conversations/*.jsonl | \
  jq -c 'select(.agentId != null) | {agentId, slug, isSidechain, model: .message.model}'

# Dashboard view
tail -f ~/.claude/projects/*/conversations/*.jsonl 2>/dev/null | \
  jq -r 'select(.agentId) | "\(.timestamp | split("T")[1] | split(".")[0]) | \(.agentId) [\(.slug // "main")] | tokens: \(.message.usage.input_tokens // 0)+\(.message.usage.output_tokens // 0)"'

# Filter for subagents only
tail -f ~/.claude/projects/*/conversations/*.jsonl | \
  jq -c 'select(.isSidechain == true)'
```

---

## 3. Agent ID System (Verified)

When using the `Task` tool to spawn subagents, Claude Code automatically assigns unique agent IDs.

### Test Results (2026-01-07 - Re-verified)

**Test Run 1** (original):

| Agent | Task Description | Assigned ID |
|-------|------------------|-------------|
| A | File line count scan | `ac13ca4` |
| B | Schema class scan | `af8d8c3` |
| C | MCP tool count | `a07e8fb` |

**Test Run 2** (verification):

| Agent | Task Description | Assigned ID | Model |
|-------|------------------|-------------|-------|
| A | Python file count | `a9c71af` | claude-haiku-4-5-20251001 |
| B | Schema class scan | `aae6205` | claude-haiku-4-5-20251001 |
| C | MCP tool list | `ad54325` | claude-haiku-4-5-20251001 |

### Model Assignment Patterns

Claude Code assigns different models based on agent type and complexity:

| Context | Model | Notes |
|---------|-------|-------|
| Main session | `claude-opus-4-5-20251101` | Primary conversation |
| Explore agents | `claude-haiku-4-5-20251001` | Fast, efficient searches |
| Complex agents | `claude-opus-4-5-20251101` | Heavy analysis tasks |
| Bash agents | `claude-haiku-4-5-20251001` | Quick command execution |

### How It Works

1. **Spawning**: Call `Task` tool with `subagent_type` and `prompt`
2. **ID Assignment**: System returns `agentId` (7-char hex)
3. **Tracking**: Use `TaskOutput` tool with `task_id` to check status
4. **Resuming**: Pass `agentId` to `resume` parameter to continue agent

### Example Task Call

```json
{
  "subagent_type": "Explore",
  "prompt": "List Python files in coderoots/",
  "description": "Test agent A"
}
```

### Response Includes

```
agentId: ac13ca4 (for resuming to continue this agent's work if needed)
```

---

## 4. Practical Tracking Strategy

For tracking agent hierarchies in your workflows:

### Option A: JSONL Log Tailing (Real-time)

Best for live monitoring during development.

```bash
# Create alias
alias claude-agents='tail -f ~/.claude/projects/*/conversations/*.jsonl | jq -c "select(.agentId)"'
```

### Option B: Post-hoc Analysis

Parse completed session logs:

```bash
# Extract all agent IDs from a session
cat ~/.claude/projects/<hash>/conversations/<session>.jsonl | \
  jq -s '[.[] | select(.agentId)] | group_by(.agentId) | map({agentId: .[0].agentId, slug: .[0].slug, count: length})'
```

### Option C: Custom Wrapper Script

For production tracking, wrap Task calls and log to your own telemetry:

```python
# Pseudocode
def tracked_task(subagent_type, prompt, parent_id=None):
    result = call_task_tool(subagent_type, prompt)
    agent_id = extract_agent_id(result)
    emit_telemetry({
        "agent_id": agent_id,
        "parent_id": parent_id,
        "type": subagent_type,
        "timestamp": now()
    })
    return result
```

---

## 5. Token Usage Aggregation

Per-agent token tracking enables cost analysis and optimization.

### Aggregate Tokens Per Agent

```bash
# Calculate token usage for all agents in a project
for f in ~/.claude/projects/<project-hash>/agent-*.jsonl; do
  agent=$(basename $f .jsonl)
  totals=$(cat $f | jq -s '[.[] | select(.message.usage)] | {
    total_input: (map(.message.usage.input_tokens // 0) | add),
    total_output: (map(.message.usage.output_tokens // 0) | add),
    cache_created: (map(.message.usage.cache_creation_input_tokens // 0) | add),
    cache_read: (map(.message.usage.cache_read_input_tokens // 0) | add),
    model: .[0].message.model
  }')
  echo "$agent: $totals"
done
```

### Sample Output

```
agent-a9c71af: {"total_input":11,"total_output":3,"cache_created":187375,"cache_read":93422,"model":"claude-haiku-4-5-20251001"}
agent-aae6205: {"total_input":11,"total_output":3,"cache_created":193446,"cache_read":93423,"model":"claude-haiku-4-5-20251001"}
agent-ad54325: {"total_input":11,"total_output":95,"cache_created":202082,"cache_read":93424,"model":"claude-haiku-4-5-20251001"}
```

### Cost Estimation

```bash
# Estimate costs (rough, based on public pricing)
cat ~/.claude/projects/<hash>/agent-*.jsonl | jq -s '
  [.[] | select(.message.usage)] |
  reduce .[] as $item (
    {input: 0, output: 0, cache_write: 0, cache_read: 0};
    .input += ($item.message.usage.input_tokens // 0) |
    .output += ($item.message.usage.output_tokens // 0) |
    .cache_write += ($item.message.usage.cache_creation_input_tokens // 0) |
    .cache_read += ($item.message.usage.cache_read_input_tokens // 0)
  )'
```

---

## 6. Per-Agent Log Files

Each spawned agent gets its own JSONL log file for isolated tracking.

### File Naming Convention

```
agent-{7-char-hex-id}.jsonl
```

### Use Cases

1. **Debugging**: Inspect individual agent behavior
2. **Billing**: Track costs per task type
3. **Performance**: Measure agent efficiency
4. **Audit**: Full trace of agent actions

### List Active Agents

```bash
# List all agent log files with modification times
ls -la ~/.claude/projects/<project-hash>/agent-*.jsonl | awk '{print $6, $7, $8, $9}'

# Count entries per agent
for f in ~/.claude/projects/<project-hash>/agent-*.jsonl; do
  echo "$(basename $f): $(wc -l < $f) entries"
done
```

---

## 7. Feature Gap

**Native OTEL agent hierarchy tracking is not currently supported.**

Workarounds:
- Use internal JSONL logs for agent tracking
- Build custom instrumentation layer
- Request feature from Anthropic

---

## References

- Claude Code docs: https://docs.anthropic.com/en/docs/claude-code
- OTEL collector setup: https://opentelemetry.io/docs/collector/
- Session logs: `~/.claude/projects/`
