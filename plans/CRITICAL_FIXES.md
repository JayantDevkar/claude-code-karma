# Critical Architectural Fixes for Agent Designs

## Issues Identified and Solutions

---

## Issue 1: Incorrect Tool References ❌

### Problem
The designs reference tools incorrectly:
```yaml
tools:
  primary:
    - Glob   # ❌ How is this provided to agents?
    - Read   # ❌ How is this provided to agents?
    - Grep   # ❌ How is this provided to agents?
```

### Root Cause
Confusion between:
1. **Built-in Claude Code tools** (available to main session: Glob, Grep, Read, Bash, etc.)
2. **MCP server tools** (namespaced: `mcp__server-name__tool-name`)
3. **Tools available to agents** (unclear what subset agents can access)

### Solution

**For agents that need filesystem operations**, use **Bash tool** to run standard commands:

```yaml
# fetch-plane-tasks - CORRECTED
tools:
  primary:
    - mcp__plane-project-task-manager__list_projects
    - mcp__plane-project-task-manager__list_work_items
    - mcp__plane-project-task-manager__retrieve_work_item

# No Glob/Read needed - all data comes from MCP server
```

```yaml
# analyze-work-item - CORRECTED
tools:
  primary:
    - Bash  # For running grep/find if file validation needed

# Content parsing uses LLM built-in capabilities (no tool needed)
# Optional: Use Bash to run: grep -r "pattern" /path
```

```yaml
# select-agent - CORRECTED
tools:
  primary:
    - Bash  # For running: find agents/ -name "*.yaml"
           # And: grep -l "keyword" agents/**/agent.yaml

# Read agent.yaml files via Bash: cat agents/agent-name/agent.yaml
# Or use Read tool if available to agents (needs verification)
```

---

## Issue 2: Missing MCP Integration ❌

### Problem
fetch-plane-tasks design doesn't explicitly use the **actual MCP server name**.

### Solution

```yaml
# fetch-plane-tasks agent.yaml - CORRECTED
name: fetch-plane-tasks
description: "Fetches work items from Plane MCP server for current project"
model: sonnet

tools:
  primary:
    # Use FULL MCP tool names with namespace
    - mcp__plane-project-task-manager__list_projects
    - mcp__plane-project-task-manager__list_work_items
    - mcp__plane-project-task-manager__retrieve_work_item

  support:
    - Bash  # For git context detection: git remote get-url origin

# NO TodoWrite (not an MCP tool)
# NO AskUserQuestion (not an MCP tool)
```

**MCP Server Configuration** (must be in Claude Code settings):
```yaml
mcp:
  servers:
    plane-project-task-manager:
      command: uvx
      args:
        - plane-mcp-server
      env:
        PLANE_API_KEY: ${PLANE_API_KEY}
        PLANE_API_URL: https://api.plane.so
        WORKSPACE_SLUG: ${WORKSPACE_SLUG}
```

---

## Issue 3: Agent Communication Gap ❌

### Problem
Designs don't explain how agents pass data between each other.

### Solution: Use Structured JSON Contracts

#### Architecture Pattern: Orchestrator + Worker Agents

```
Main Claude Code Session (Orchestrator)
    │
    ├─> Task tool: Launch fetch-plane-tasks agent
    │       └─> Returns: JSON { work_items: [...] }
    │
    ├─> Task tool: Launch analyze-work-item agent
    │       └─> Input: { work_item_content: {...} }
    │       └─> Returns: JSON { task_type, complexity, steps: [...] }
    │
    ├─> Task tool: Launch select-agent agent
    │       └─> Input: { task_type, required_capabilities: [...] }
    │       └─> Returns: JSON { recommendations: [...] }
    │
    └─> Main session uses recommendations to execute work
```

#### Data Flow Contracts

**1. fetch-plane-tasks Output → Main Session**
```json
{
  "project_id": "uuid",
  "work_items": [
    {
      "id": "uuid",
      "name": "Task title",
      "description_html": "<p>HTML content</p>",
      "priority": "high",
      "state": "uuid"
    }
  ],
  "total_fetched": 5
}
```

**2. Main Session → analyze-work-item Input**
```json
{
  "work_item_content": {
    "name": "Task title",
    "description_html": "<p>HTML content</p>"
  }
}
```

**3. analyze-work-item Output → Main Session**
```json
{
  "task_type": "FEATURE",
  "complexity": "MEDIUM",
  "actionable_steps": ["Step 1", "Step 2"],
  "file_references": ["/path/to/file.ts"],
  "parsing_confidence": "HIGH"
}
```

**4. Main Session → select-agent Input**
```json
{
  "task_type": "FEATURE",
  "required_capabilities": ["typescript", "react"],
  "complexity": "MEDIUM"
}
```

**5. select-agent Output → Main Session**
```json
{
  "recommendations": [
    {
      "agent_name": "implement-react-feature",
      "score": 95,
      "rationale": "Exact match for React feature implementation"
    }
  ],
  "selection_confidence": "HIGH"
}
```

#### Communication Rules

1. **Orchestrator owns workflow**: Main Claude Code session coordinates all agents
2. **Agents don't call agents**: No agent-to-agent direct calls
3. **Strict JSON contracts**: All inputs/outputs are validated JSON schemas
4. **Stateless agents**: Each agent call is independent (no session state)
5. **Error propagation**: Agents return errors as JSON, orchestrator handles

---

## Issue 4: No Agent Execution Mechanism ❌

### Problem
select-agent recommends an agent but has no way to invoke it.

### Solution: Orchestrator Pattern (Main Session Executes)

**INCORRECT Approach** (Agent trying to execute another agent):
```yaml
# ❌ BAD - select-agent trying to invoke another agent
- Task tool: invoke recommended agent  # Doesn't work!
```

**CORRECT Approach** (Return recommendation, let orchestrator invoke):
```yaml
# ✅ GOOD - select-agent returns recommendation
Output:
  {
    "recommendations": [
      {
        "agent_name": "implement-feature",
        "config_path": "agents/implement-feature/agent.yaml",
        "invocation_hint": "Use Task tool with this agent name"
      }
    ]
  }
```

#### Orchestrator Workflow (Main Session)

```python
# Pseudo-code for main Claude Code session workflow

# Step 1: Fetch work items
result = Task(
    subagent_type="fetch-plane-tasks",
    prompt="Fetch work items for project claude-karma"
)
work_items = result["work_items"]

# Step 2: User selects work item
selected_item = work_items[0]  # User choice

# Step 3: Analyze work item
analysis = Task(
    subagent_type="analyze-work-item",
    prompt=f"Parse work item: {json.dumps(selected_item)}"
)

# Step 4: Select execution agent
recommendation = Task(
    subagent_type="select-agent",
    prompt=f"Find agent for: {json.dumps(analysis)}"
)

# Step 5: Execute recommended agent (orchestrator's job)
execution_agent = recommendation["recommendations"][0]["agent_name"]

# Main session invokes the recommended agent
Task(
    subagent_type=execution_agent,
    prompt=f"Implement: {selected_item['name']}"
)
```

---

## Corrected Three-Agent Architecture

### Agent 1: fetch-plane-tasks
**Responsibility**: Query Plane MCP server ONLY
**Tools**:
```yaml
primary:
  - mcp__plane-project-task-manager__list_projects
  - mcp__plane-project-task-manager__list_work_items
  - mcp__plane-project-task-manager__retrieve_work_item
support:
  - Bash  # For git context: git config --get remote.origin.url
```

**Does NOT**:
- ❌ Parse HTML content (analyze-work-item's job)
- ❌ Select agents (select-agent's job)
- ❌ Execute tasks (orchestrator's job)
- ❌ Use TodoWrite (not available to agents)

---

### Agent 2: analyze-work-item
**Responsibility**: Parse HTML/markdown content ONLY
**Tools**:
```yaml
primary:
  # Uses LLM built-in parsing (no tool needed for HTML→text)
  - Bash  # OPTIONAL: For file validation via grep/find
```

**Does NOT**:
- ❌ Fetch from Plane (fetch-plane-tasks's job)
- ❌ Select agents (select-agent's job)
- ❌ Execute tasks (orchestrator's job)

---

### Agent 3: select-agent
**Responsibility**: Scan agents/ and match to requirements ONLY
**Tools**:
```yaml
primary:
  - Bash  # For: find agents/ -name "agent.yaml"
         #     cat agents/*/agent.yaml
         #     grep -l "capability" agents/**/agent.yaml
```

**Does NOT**:
- ❌ Invoke selected agent (orchestrator's job via Task tool)
- ❌ Fetch from Plane (fetch-plane-tasks's job)
- ❌ Parse work items (analyze-work-item's job)

---

## Verification Checklist

Before implementing agents, verify:

- [ ] **Tool availability**: Confirm Bash is available to agents
- [ ] **MCP server configured**: plane-project-task-manager in Claude Code settings
- [ ] **No TodoWrite/AskUserQuestion**: Only in orchestrator, not agents
- [ ] **JSON schemas defined**: All input/output contracts documented
- [ ] **Orchestrator pattern**: Main session coordinates workflow
- [ ] **Agent boundaries respected**: Each agent has single responsibility
- [ ] **Error handling**: Agents return structured errors, don't crash
- [ ] **Stateless design**: No session state in agents

---

## Implementation Priority

1. **FIRST**: Fix tool references in all 3 agent designs
2. **SECOND**: Document JSON contracts for data passing
3. **THIRD**: Create orchestrator skill/agent that uses Task tool
4. **FOURTH**: Test each agent independently with mock inputs
5. **FIFTH**: Test full pipeline with orchestrator

---

## Open Questions Requiring Clarification

1. **Tool availability to agents**: Which built-in tools (Glob, Read, Grep) are actually available to agents launched via Task tool?
2. **Filesystem MCP server**: Should we create a filesystem MCP server, or is Bash sufficient?
3. **Agent invocation**: Should select-agent return agent names, or full Task tool invocation commands?
4. **Error handling**: Should agents use structured error codes, or plain text messages?
5. **Performance**: What's the latency overhead of launching 3 sequential agents vs. 1 monolithic agent?

---

## Next Steps

1. Read Claude Code agent documentation to confirm tool availability
2. Update all 3 agent designs with corrected tool references
3. Create orchestrator agent/skill that coordinates the 3-agent pipeline
4. Define strict JSON schemas for all data contracts
5. Implement and test incrementally (one agent at a time)
