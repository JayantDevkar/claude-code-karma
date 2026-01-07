# Claude Code Tools Reference Guide

**Project**: claude-karma
**Purpose**: Comprehensive reference for all tools available to Claude Code agents
**Last Updated**: 2026-01-06
**Work Item**: CLAUDEKARM-2

---

## Table of Contents

1. [Complete List of Available Tools](#1-complete-list-of-available-tools)
2. [Tool Categories & Groupings](#2-tool-categories--groupings)
3. [How to Configure Tools for Agents](#3-how-to-configure-tools-for-agents)
4. [Tool Specifications & Parameters](#4-tool-specifications--parameters)
5. [Tool Access Restrictions & Best Practices](#5-tool-access-restrictions--best-practices)
6. [Common Tool Usage Patterns](#6-common-tool-usage-patterns)
7. [Token Costs for Tools](#7-token-costs-for-tools)
8. [Advanced Tool Use Patterns](#8-advanced-tool-use-patterns)
9. [Troubleshooting & Common Issues](#9-troubleshooting--common-issues)
10. [Claude-Karma Project Configuration](#10-claude-karma-project-configuration)

---

## 1. Complete List of Available Tools

### Anthropic-Defined Server Tools (Managed by Anthropic)

#### Web Search Tool
- **Type**: `web_search_20250305`
- **Description**: Real-time internet search with automatic citations
- **Key Features**:
  - Up to 1,000 searches per request (configurable via `max_uses`)
  - Domain filtering (allowed_domains/blocked_domains)
  - User location localization
  - Automatic source citations
  - Works with prompt caching
- **Pricing**: $10 per 1,000 searches + standard token costs
- **Usage Context**: Finding current information beyond knowledge cutoff, research tasks

#### Web Fetch Tool (Beta)
- **Type**: `web_fetch_20250910`
- **Description**: Retrieve full text content from web pages and PDFs
- **Key Features**:
  - Fetch full webpage content and PDFs
  - Extract text from PDFs automatically
  - Optional citations for fetched content
  - Content length limits via `max_content_tokens`
  - Domain filtering support
  - URL validation (only user-provided or search result URLs)
- **Pricing**: No additional charges, only standard token costs
- **Usage Context**: Detailed document analysis, multi-turn web research

---

### Anthropic-Defined Client Tools (Require implementation on your system)

#### Computer Use Tool
- **Type**: `computer_20251124` (Opus 4.5) or `computer_20250124` (other models)
- **Beta Header Required**: `computer-use-2025-11-24` (Opus 4.5) or `computer-use-2025-01-24` (others)
- **Capabilities**:
  - **Visual**: Screenshot capture (see desktop)
  - **Input**: Mouse clicks, keyboard input, mouse drag
  - **Enhanced Actions** (v20250124):
    - Scroll, left_click_drag, right_click, middle_click
    - Double_click, triple_click, mouse position control
    - Key hold, wait actions
  - **Advanced** (v20251124 Opus 4.5 only):
    - Zoom action for detailed region inspection
- **Parameters**:
  - `display_width_px`, `display_height_px`: Display dimensions
  - `enable_zoom`: Enable zoom action (Opus 4.5 only)
- **Security**: Requires sandboxed environment; prompt injection protections included
- **Cost**: 466-499 system prompt tokens + 735 input tokens per tool definition
- **Use Cases**: Desktop automation, GUI interaction, cross-application workflows

#### Text Editor Tool
- **Type**: `text_editor_20250728` (Claude 4) or `text_editor_20250124` (Sonnet 3.7)
- **Commands**:
  - `view`: Read files/directories with optional line range
  - `str_replace`: Replace exact text matches
  - `create`: Create new files
  - `insert`: Insert text at specific line
  - `undo_edit`: Revert last edit (Sonnet 3.7 only)
- **Parameters**:
  - `max_characters`: Limit file viewing size (Claude 4 only)
- **Cost**: 700 additional input tokens
- **Use Cases**: Code debugging, file editing, documentation generation, test creation

#### Bash Tool
- **Type**: `bash_20250124`
- **Capabilities**:
  - Execute shell commands in persistent session
  - Command chaining and scripting
  - Environment variable persistence
  - Working directory persistence
- **Parameters**:
  - `command`: The bash command to execute
  - `restart`: Reset the session
- **Cost**: 245 additional input tokens
- **Use Cases**: Build processes, test execution, system administration, file operations

---

### Custom User-Defined Tools

You can define custom tools with:
- **name**: Identifier matching regex `^[a-zA-Z0-9_-]{1,64}$`
- **description**: Detailed plaintext explaining purpose, when to use, behavior
- **input_schema**: JSON Schema object defining parameters
- **input_examples** (beta, optional): Example input objects for complex tools
- **strict** (optional): Set to `true` for guaranteed schema validation

**Example Custom Tool**:
```json
{
  "name": "get_weather",
  "description": "Get current weather in a location. Returns temperature, conditions, and precipitation chance. Should be used when user asks about current weather or conditions. Will not provide historical data or forecasts beyond today.",
  "input_schema": {
    "type": "object",
    "properties": {
      "location": {"type": "string", "description": "City and state, e.g., San Francisco, CA"},
      "unit": {"enum": ["celsius", "fahrenheit"], "description": "Temperature unit"}
    },
    "required": ["location"]
  }
}
```

---

## 2. Tool Categories & Groupings

### By Execution Model

**Server Tools** (Anthropic handles execution):
- Web Search
- Web Fetch

**Client Tools** (Your system executes):
- Computer Use
- Text Editor
- Bash
- Custom Tools

### By Function

**Information Gathering**:
- Web Search (real-time data)
- Web Fetch (full document retrieval)

**System/Code Execution**:
- Bash (shell commands)
- Computer Use (desktop interaction)

**File & Code Manipulation**:
- Text Editor (view/edit files)
- Computer Use (visual file interaction)

**Domain-Specific**:
- Custom tools you define

### By Risk Profile

**Low Risk** (read-only):
- Web Search
- Web Fetch
- Text Editor (view command)

**Medium Risk** (file operations):
- Text Editor (str_replace, create, insert)
- Bash (non-destructive operations)

**High Risk** (requires isolation):
- Computer Use
- Bash (destructive operations)

---

## 3. How to Configure Tools for Agents

### Agent SDK Configuration

In your agent configuration (Python):
```python
from anthropic import Anthropic

client = Anthropic()

# Define tools
tools = [
    {
        "name": "get_weather",
        "description": "Get current weather in a given location. Returns temperature, conditions, and precipitation chance. Should be used when user asks about current weather or conditions. Will not provide historical data or forecasts beyond today.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City and state"}
            },
            "required": ["location"]
        }
    }
]

# Create message with tools
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "What's the weather in Paris?"}]
)
```

### In Claude Code (Skills with Tool Restrictions)

Restrict tool access in a SKILL.md file:
```markdown
---
allowed-tools: [bash, text_editor]
---

Tool: bash
Command to run bash commands
```

### In Claude Code Agents (YAML Configuration)

For claude-karma agents, specify tools in agent.yaml:
```yaml
tools:
  - name: "bash"
    description: "Execute shell commands"
  - name: "text_editor"
    description: "Edit files"
```

### Tool Choice Control

```python
# Allow Claude to decide (default)
tool_choice = "auto"

# Force Claude to use a specific tool
tool_choice = {"type": "tool", "name": "specific_tool"}

# Force any tool to be used
tool_choice = {"type": "any"}

# Prevent tool use
tool_choice = "none"
```

---

## 4. Tool Specifications & Parameters

### General Tool Definition Format

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `name` | Yes | string | Tool identifier, pattern: `^[a-zA-Z0-9_-]{1,64}$` |
| `description` | Yes | string | Detailed plaintext description (3-4+ sentences recommended) |
| `input_schema` | Yes | object | JSON Schema defining tool parameters |
| `input_examples` | No | array | Example valid inputs (beta feature) |
| `strict` | No | boolean | Enable strict schema validation (default: false) |
| `type` | Yes (server tools) | string | Tool type version (e.g., `web_search_20250305`) |
| `max_uses` | No (server tools) | number | Limit tool invocations per request |

### Best Practices for Tool Descriptions

**Good Description** (what Claude needs):
```
"Get the current weather in a given location. Returns temperature, conditions,
and precipitation chance. Should be used when user asks about current weather
or conditions. Will not provide historical data or forecasts beyond today."
```

**Poor Description** (too vague):
```
"Gets the weather"
```

**Key Elements**:
1. What the tool does (1-2 sentences)
2. What data it returns
3. When to use it
4. What it doesn't do (limitations)

---

## 5. Tool Access Restrictions & Best Practices

### Restricting Tools in Agents

**Method 1: Skills with allowed-tools**
```yaml
# In SKILL.md
---
allowed-tools: [bash, text_editor]
---
```

**Method 2: Permissions Configuration**
Configure in `settings.json`:
```json
{
  "permissions": {
    "allow": [
      "mcp__plane-project-task-manager__list_projects",
      "mcp__tool_bash",
      "mcp__tool_text_editor"
    ]
  }
}
```

### Security Best Practices

#### For Computer Use:
1. Use dedicated virtual machines/containers
2. Limit system privileges
3. Avoid sensitive credentials in prompts
4. Enable prompt injection detection (automatic)
5. Verify all actions before execution

#### For Bash:
1. Implement command filtering (block: `rm -rf /`, `sudo`, etc.)
2. Set resource limits (CPU, memory, disk)
3. Run with minimal permissions
4. Log all command execution
5. Use timeouts (recommended 30 seconds)

#### For Text Editor:
1. Implement file path validation
2. Create backups before editing
3. Verify file changes match schema
4. Restrict to allowed directories
5. Log all file modifications

#### For Web Tools:
1. Use domain filtering (`allowed_domains`, `blocked_domains`)
2. Set `max_uses` limits
3. Enable content truncation (`max_content_tokens`)
4. Watch for prompt injection in web content
5. Verify URLs before fetching (web fetch only)

#### General:
1. Implement comprehensive error handling
2. Return detailed error messages to Claude
3. Handle partial failures gracefully
4. Monitor token usage
5. Log all tool invocations with context

---

## 6. Common Tool Usage Patterns

### Pattern 1: Sequential Information Gathering
```python
# Agent uses web_search → web_fetch → analysis
tools = [
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
    {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 5}
]
# Claude searches for relevant articles, then fetches full content
```

### Pattern 2: Code Development Workflow
```python
tools = [
    {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
    {"type": "bash_20250124", "name": "bash"},
]
# Claude views file → makes edits → runs tests → verifies output
```

### Pattern 3: Desktop Automation
```python
tools = [
    {"type": "computer_20250124", "name": "computer", "display_width_px": 1024, "display_height_px": 768},
    {"type": "bash_20250124", "name": "bash"},
    {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}
]
# Claude takes screenshots → clicks UI → runs commands → edits files
```

### Pattern 4: Parallel Tool Execution
When Claude has independent operations (best with Claude 4 models):
```python
# Claude can execute multiple tool calls in single response:
# - get_weather(location1)
# - get_weather(location2)
# - get_time(timezone1)
# - get_time(timezone2)

# ALL tool results must be returned in SINGLE user message:
{
    "role": "user",
    "content": [
        {"type": "tool_result", "tool_use_id": "id1", "content": "..."},
        {"type": "tool_result", "tool_use_id": "id2", "content": "..."},
        {"type": "tool_result", "tool_use_id": "id3", "content": "..."},
        {"type": "tool_result", "tool_use_id": "id4", "content": "..."}
    ]
}
```

### Pattern 5: Error Handling & Retry
```python
# Return error with is_error flag
{
    "type": "tool_result",
    "tool_use_id": "toolu_01A09q90qw90lq917835lq9",
    "content": "Error: File not found at /path/to/file",
    "is_error": true
}
# Claude will retry with different approach or ask for clarification
```

---

## 7. Token Costs for Tools

| Tool | System Prompt Overhead | Input Tokens |
|------|------------------------|----|
| Computer Use (general) | 466-499 tokens | 735 |
| Text Editor | N/A | 700 |
| Bash | N/A | 245 |
| Web Search | Included in tool use | Varies by results |
| Web Fetch | Included in tool use | Varies by content |

**Additional costs**:
- Tool definitions in `tools` parameter: ~20-50 tokens per tool
- Tool use request blocks: Varies by complexity
- Tool result blocks: Size of returned content
- Web Search: $10 per 1,000 searches
- Web Fetch: No additional charge

---

## 8. Advanced Tool Use Patterns

### Tool Runner (Beta - Recommended)

The SDK provides automatic tool execution in Python/TypeScript:

```python
from anthropic import beta_tool

@beta_tool
def get_weather(location: str, unit: str = "fahrenheit") -> str:
    """Get current weather"""
    return json.dumps({"temperature": "20°C"})

runner = client.beta.messages.tool_runner(
    model="claude-opus-4-5",
    max_tokens=1024,
    tools=[get_weather],
    messages=[{"role": "user", "content": "What's the weather in Paris?"}]
)

final_message = runner.until_done()
print(final_message.content[0].text)
```

### Strict Tool Use (Guaranteed Schema Conformance)

```python
tools = [
    {
        "name": "process_order",
        "description": "Process a customer order with order ID and amount. Returns confirmation number when successful. Use when user wants to place or complete an order.",
        "strict": True,  # Enable strict validation
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount": {"type": "number"}
            },
            "required": ["order_id", "amount"]
        }
    }
]
```

### MCP Tool Integration

Convert MCP tools to Claude format:

```python
async def get_claude_tools(mcp_session):
    mcp_tools = await mcp_session.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema  # Rename inputSchema to input_schema
        }
        for tool in mcp_tools.tools
    ]
```

---

## 9. Troubleshooting & Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Claude not using tool | Vague description | Provide 3-4 detailed sentences explaining when/why to use |
| Invalid tool parameters | Schema mismatch | Use `strict: true` for guaranteed validation |
| Parallel tools not working | Wrong message format | Return ALL tool results in single user message |
| Tool timeouts | Long-running commands | Set timeouts (30 seconds recommended), use restart parameter |
| File editing failing | Multiple text matches | Provide exact context to make str_replace unique |
| Web fetch not authorized | URL not in context | Only user-provided or search result URLs allowed |
| Computer use coordinate errors | Resolution mismatch | Scale coordinates based on actual display resolution |

---

## 10. Claude-Karma Project Configuration

### Current MCP Servers

- **plugin:github** - GitHub operations
- **plugin:linear** - Linear issue tracking
- **coderoots** - Code analysis and knowledge graph
- **plane-project-task-manager** - Plane integration

### Custom Agents Available

1. **plane-task-orchestrator** - Coordinates sequential work item execution
2. **select-agent** - Discovers and recommends best-fit agents
3. **analyze-work-item** - Parses HTML/markdown work item descriptions
4. **fetch-plane-tasks** - Fetches work items from Plane MCP server

### Enabled Plugins

- pyright-lsp (Python)
- gopls-lsp (Go)
- ralph-wiggum (technique)
- code-review
- commit-commands
- linear

### Custom Skills

- /ralph-wiggum:* (3 commands)
- /code-review:code-review
- /commit-commands:* (3 commands)
- /init, /pr-comments, /statusline, /review, /security-review

### Tool Access for Claude-Karma Agents

**plane-task-orchestrator**:
- Task (delegation to subagents)
- AskUserQuestion (user interaction)
- TodoWrite (planning)
- update_work_item (Plane status updates)
- add_comment (Plane comments)

**fetch-plane-tasks**:
- mcp__plane-project-task-manager__list_projects
- mcp__plane-project-task-manager__list_work_items
- mcp__plane-project-task-manager__retrieve_work_item
- Bash (git context detection)

**analyze-work-item**:
- Bash (~30% usage for file validation)

**select-agent**:
- Glob (discover agent.yaml files)
- Read (parse agent configurations)
- Grep (keyword searches)

---

## Quick Reference Links

- **Tool Use Documentation**: https://platform.claude.com/docs/en/build-with-claude/tool-use.md
- **Implement Tool Use**: https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use.md
- **Claude Agent SDK**: https://platform.claude.com/docs/en/agents-and-tools/agent-sdk-overview.md
- **Claude Code Skills**: https://code.claude.com/docs/en/skills.md
- **MCP Documentation**: https://modelcontextprotocol.io/

---

## Appendix: Tool Mapping for Common Agent Tasks

| Agent Task | Recommended Tools | Pattern |
|------------|------------------|---------|
| Research & Documentation | Web Search, Web Fetch, Text Editor | Sequential gathering |
| Code Development | Text Editor, Bash | Edit → Test → Verify |
| File Organization | Text Editor, Bash | View → Move → Verify |
| Data Analysis | Bash, Text Editor | Extract → Process → Report |
| Testing & QA | Bash, Text Editor | Run → Analyze → Fix |
| Project Management Integration | MCP Tools (Plane, Linear) | Fetch → Update → Comment |
| Agent Discovery | Glob, Read, Grep | Scan → Parse → Score |
| Desktop Automation | Computer Use, Bash, Text Editor | Screenshot → Interact → Verify |

---

**End of Reference Guide**
