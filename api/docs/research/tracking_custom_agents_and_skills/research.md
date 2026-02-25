# Research: Tracking Custom Agents and Skills in Claude Karma

**Date:** 2026-01-10
**Requested by:** UI/UX Team
**Author:** Data Engineering

---

## Executive Summary

**YES, tracking custom agent and skill invocations is POSSIBLE**, but requires additional parsing infrastructure. The key finding is that `subagent_type` is captured in Task tool invocations within parent session JSONL files, enabling correlation to custom agent definitions.

| Capability | Status | Implementation Effort |
|------------|--------|----------------------|
| Detect subagent invocations | **Already exists** | None |
| Link subagent to `subagent_type` | **Possible** | Medium - parse Task tool inputs |
| Link to custom agent definitions | **Possible** | Medium - build agent registry |
| Track skill invocations | **Possible** | Medium - parse Skill tool usage |
| Show custom agent metadata | **Possible** | Low - parse agent.md frontmatter |

---

## 1. Custom Agent Definitions (`~/.claude/agents/`)

### 1.1 Directory Structure

```
~/.claude/agents/
├── analyze-work-item/
│   └── agent.md
├── fetch-plane-tasks/
│   └── agent.md
├── plane-task-grabber/        (empty)
└── plane-task-orchestrator/
    └── agent.md
```

### 1.2 Agent Definition Schema (agent.md)

Custom agents use **Markdown with YAML frontmatter**:

```yaml
---
name: analyze-work-item                    # Unique kebab-case identifier
description: "Description of when to use"  # Used for auto-invocation matching
model: sonnet                              # sonnet | opus | haiku
tools: Bash                                # Comma-separated or YAML list
---

## Role
[Agent role description]

## Objective
[What the agent accomplishes]

## Process
[Steps the agent performs]

## Output Format
[Expected output structure]
```

### 1.3 Key Fields for Linking

| Field | Type | Purpose |
|-------|------|---------|
| `name` | string | **Primary identifier** - matches `subagent_type` in Task tool |
| `description` | string | Auto-invocation matching criteria |
| `model` | string | Claude model used |
| `tools` | string/array | Available tools for this agent |

---

## 2. Custom Skills (`~/.claude/skills/`)

### 2.1 Directory Structure

```
~/.claude/skills/
├── agent-discovery/
│   └── skill.md
├── agent-selection/
│   └── skill.md
├── capability-matching/
│   └── skill.md
├── knowledge-addition -> /external/path
├── knowledge-query -> /external/path
└── knowledge-specifications -> /external/path
```

Skills can be symlinked from external repositories.

### 2.2 Skill Definition Schema (skill.md)

```yaml
---
name: agent-discovery
description: "Discovers available agents by scanning the agents/ directory"
model: haiku
tools:
  - Glob
  - Read
---

## Role
[Skill role description]

## Process
[Steps the skill performs]

## Output Format
[Expected JSON output structure]
```

### 2.3 Skill Invocation Tracking

Skills are invoked via the **Skill tool** in session JSONL:

```json
{
  "type": "tool_use",
  "name": "Skill",
  "input": {
    "skill": "agent-discovery",
    "args": {}
  }
}
```

---

## 3. The Key Discovery: Task Tool Captures `subagent_type`

### 3.1 Evidence from Session JSONL

Found in actual session data at `~/.claude/projects/`:

```json
{
  "type": "tool_use",
  "id": "toolu_01M1xtXQTmKVfWKMtvn5f1qK",
  "name": "Task",
  "input": {
    "description": "Explore ~/.claude/projects structure",
    "prompt": "Explore the directory structure...",
    "subagent_type": "Explore",       // <-- KEY FIELD
    "run_in_background": true
  }
}
```

> **CORRECTION (2026-01-10):** The `slug` field (e.g., "eager-puzzling-fairy") is **SESSION-BASED**, not agent-based. All subagents spawned from a session inherit the same slug. Use `agentId` for unique agent identification. See `docs/bug/agent-slug-is-not-unique/info.md` for details.

### 3.2 Available `subagent_type` Values

| Type | Source | Description |
|------|--------|-------------|
| `Explore` | Built-in | Read-only codebase exploration |
| `Plan` | Built-in | Plan mode research |
| `general-purpose` | Built-in | Complex multi-step tasks |
| `claude-code-guide` | Built-in | Claude Code documentation |
| `haiku` | Built-in | Fast, lightweight tasks |
| `{custom-agent-name}` | User-defined | Custom agents from `~/.claude/agents/` |

### 3.3 How Linking Works

```
Parent Session JSONL
    └── AssistantMessage
        └── ToolUseBlock (name="Task")
            └── input.subagent_type = "analyze-work-item"  ← CAPTURED HERE
                    ↓
                    ↓  LINK VIA NAME MATCH
                    ↓
~/.claude/agents/analyze-work-item/agent.md
    └── name: "analyze-work-item"
    └── description: "..."
    └── model: "sonnet"
    └── tools: ["Bash"]
```

---

## 4. Current Parsing Gap in Claude Karma

### 4.1 What Already Exists

| Component | Location | Status |
|-----------|----------|--------|
| Subagent detection | `models/agent.py` | Works |
| `agentId` extraction | `models/agent.py:50-107` | Works |
| `slug` extraction | `models/agent.py` | Works |
| `isSidechain` tracking | `models/message.py:36` | Works |
| Subagent list per session | `models/session.py:197-210` | Works |

### 4.2 What's Missing

| Component | Required For | Priority |
|-----------|--------------|----------|
| **Parse Task tool `subagent_type`** | Link subagent to type | **High** |
| **Agent definition parser** | Show custom agent metadata | **High** |
| **Agent registry model** | List available agents | Medium |
| **Skill definition parser** | Track skill usage | Medium |
| **Skill tool invocation parser** | Detect skill calls | Medium |

---

## 5. Proposed Implementation

### 5.1 New Models Required

#### `AgentDefinition` (new file: `models/agent_definition.py`)

```python
from pydantic import BaseModel, ConfigDict
from pathlib import Path
from typing import List, Optional
import yaml
import re

class AgentDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str                           # From YAML frontmatter
    description: str                    # From YAML frontmatter
    model: str                          # sonnet | opus | haiku
    tools: List[str]                    # Available tools
    definition_path: Path               # Path to agent.md
    is_user_level: bool                 # True if in ~/.claude/agents/

    @classmethod
    def from_path(cls, path: Path) -> "AgentDefinition":
        content = path.read_text()
        frontmatter = cls._parse_frontmatter(content)
        return cls(
            name=frontmatter["name"],
            description=frontmatter.get("description", ""),
            model=frontmatter.get("model", "sonnet"),
            tools=cls._normalize_tools(frontmatter.get("tools", [])),
            definition_path=path,
            is_user_level=".claude/agents" in str(path)
        )

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if match:
            return yaml.safe_load(match.group(1))
        return {}
```

#### `SkillDefinition` (new file: `models/skill_definition.py`)

```python
class SkillDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    model: str
    tools: List[str]
    definition_path: Path
```

#### `AgentRegistry` (new file: `models/agent_registry.py`)

```python
class AgentRegistry(BaseModel):
    """Index of all available agents and skills"""

    user_agents: List[AgentDefinition]      # ~/.claude/agents/
    project_agents: List[AgentDefinition]   # .claude/agents/
    user_skills: List[SkillDefinition]      # ~/.claude/skills/
    project_skills: List[SkillDefinition]   # .claude/skills/

    @classmethod
    def build(cls, project_path: Optional[Path] = None) -> "AgentRegistry":
        # Scan and build registry
        ...

    def get_agent_by_name(self, name: str) -> Optional[AgentDefinition]:
        # Project agents take priority
        ...
```

### 5.2 Enhanced Session Parsing

Add to `Session` class:

```python
def get_subagent_invocations(self) -> List[dict]:
    """Extract Task tool invocations with subagent_type"""
    invocations = []
    for msg in self.iter_assistant_messages():
        for block in msg.content:
            if isinstance(block, ToolUseBlock) and block.name == "Task":
                invocations.append({
                    "tool_use_id": block.id,
                    "subagent_type": block.input.get("subagent_type"),
                    "description": block.input.get("description"),
                    "prompt": block.input.get("prompt"),
                    "timestamp": msg.timestamp
                })
    return invocations
```

### 5.3 API Schema Updates

```python
class SubagentInvocation(BaseModel):
    tool_use_id: str
    subagent_type: str
    description: Optional[str]
    prompt_preview: Optional[str]       # First 200 chars
    timestamp: datetime
    agent_definition: Optional[AgentDefinitionSummary]  # Linked metadata

class AgentDefinitionSummary(BaseModel):
    name: str
    description: str
    model: str
    tools: List[str]
    is_custom: bool
    definition_path: Optional[str]
```

---

## 6. Known Limitations

### 6.1 No Direct Link in Subagent JSONL

The subagent's own JSONL file (`agent-{agentId}.jsonl`) does **NOT** contain the `subagent_type`. It only has:

```json
{
  "isSidechain": true,
  "agentId": "a74f3744",
  "slug": "eager-puzzling-fairy"
}
```

The `subagent_type` is **only in the parent session's Task tool invocation**.

> **IMPORTANT:** The `slug` field here is the **SESSION slug**, not unique to this agent. All subagents spawned from the same session will have the same slug value. The `agentId` is the unique identifier for each subagent.

### 6.2 Community Feature Requests

Active GitHub issues requesting better tracking:

| Issue | Request |
|-------|---------|
| [#14784](https://github.com/anthropics/claude-code/issues/14784) | Add `subagent_type` to OTEL telemetry |
| [#10052](https://github.com/anthropics/claude-code/issues/10052) | Expose current agent info in statusline |
| [#7881](https://github.com/anthropics/claude-code/issues/7881) | SubagentStop hook can't identify which subagent |

### 6.3 Matching Challenges

- Runtime `agentId` (e.g., `a74f3744`) is **NOT** the same as agent name
- Must correlate via: Task tool invocation → spawned subagent timing/order
- Multiple subagents of same type may run concurrently

### 6.4 Slug Field Semantics (Corrected 2026-01-10)

| Field | Scope | Uniqueness | Example |
|-------|-------|------------|---------|
| `slug` | **Session** | Same for all messages/agents in session | `"refactored-meandering-knuth"` |
| `agentId` | **Agent** | Unique per subagent | `"a74f3744"` |
| `subagent_type` | **Task invocation** | Describes agent type | `"Explore"`, `"Plan"` |

**Live data proof:** Session `b4985950-bbf2-4f1c-a38e-5216ba77d443` has 8 subagents all with slug `refactored-meandering-knuth` but unique `agentId` values (`a3c3f19`, `a549947`, `a768842`, etc.).

---

## 7. Recommended Approach for UI/UX

### 7.1 Phase 1: Show Custom Agent Registry

Display available custom agents/skills:

```
Custom Agents
├── analyze-work-item (sonnet) - Parses work item content
├── fetch-plane-tasks (sonnet) - Fetches from Plane MCP
└── plane-task-orchestrator (sonnet) - Coordinates work items

Custom Skills
├── agent-discovery (haiku) - Discovers available agents
├── agent-selection (haiku) - Matches tasks to agents
└── capability-matching (haiku) - Scores capabilities
```

### 7.2 Phase 2: Track Invocations in Sessions

Show Task tool invocations with `subagent_type`:

```
Session Timeline
├── 10:15:32 - Task: "Explore codebase" (subagent_type: Explore)
├── 10:16:45 - Task: "Analyze work item" (subagent_type: analyze-work-item) ← CUSTOM
└── 10:18:20 - Skill: "agent-discovery" ← SKILL INVOCATION
```

### 7.3 Phase 3: Link to Definitions

Enrich with custom agent metadata:

```
Subagent: analyze-work-item
├── Type: Custom Agent
├── Model: sonnet
├── Tools: Bash
├── Description: Parses work item HTML/markdown content
├── Invocations this session: 3
└── Definition: ~/.claude/agents/analyze-work-item/agent.md
```

---

## 8. Files to Implement

| File | Type | Purpose |
|------|------|---------|
| `models/agent_definition.py` | New | Parse agent.md files |
| `models/skill_definition.py` | New | Parse skill.md files |
| `models/agent_registry.py` | New | Index all agents/skills |
| `models/session.py` | Modify | Add `get_subagent_invocations()` |
| `apps/api/schemas.py` | Modify | Add new response schemas |
| `apps/api/routes/agents.py` | New | Endpoints for agent registry |
| `tests/test_agent_definition.py` | New | Unit tests |

---

## 9. Conclusion

**For the UI/UX team:**

1. **YES** - We can track custom agent and skill invocations
2. The `subagent_type` is captured in the parent session's Task tool input
3. We need to build:
   - Agent/skill definition parser (YAML frontmatter)
   - Agent registry to index available agents
   - Enhanced session parsing to extract Task tool invocations
4. Estimated effort: **~2-3 days** for full implementation

**Key insight:** The linkage point is the `Task` tool's `input.subagent_type` field, which directly matches the `name` field in custom agent definitions.

---

## References

- [Claude Code Docs - Custom Subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code Docs - Agent Skills](https://code.claude.com/docs/en/skills)
- [Local storage research](../docs/claude-code-local-storage-research.md)
- GitHub Issues: #14784, #10052, #7881
