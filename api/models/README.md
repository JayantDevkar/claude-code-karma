# Claude Code Session Models

Pydantic models for parsing and querying Claude Code's local storage (`~/.claude/`).

> 📖 For installation instructions, quick start, and the example script, see the [main README](../README.md).

## Installation

Requires Python 3.9+ and Pydantic v2:

```bash
pip install pydantic>=2.0
```

## Quick Start

```python
from models import Project, Session

# Load a project by its original path
project = Project.from_path("/Users/me/my-project")

# List all sessions
for session in project.list_sessions():
    print(f"Session: {session.uuid}")
    print(f"  Messages: {session.message_count}")
    print(f"  Duration: {session.duration_seconds}s")
    
    # Token usage
    usage = session.get_usage_summary()
    print(f"  Tokens: {usage.total_tokens:,}")
    
    # Tool usage
    for tool, count in session.get_tools_used().most_common(5):
        print(f"    {tool}: {count}")
```

## Model Hierarchy

```
Project
├── Session (UUID.jsonl)
│   ├── Message
│   │   ├── UserMessage
│   │   ├── AssistantMessage
│   │   │   └── ContentBlock (TextBlock, ThinkingBlock, ToolUseBlock)
│   │   └── FileHistorySnapshot
│   ├── Agent (subagents/)
│   ├── ToolResult (tool-results/)
│   └── TodoItem
└── Agent (standalone agents)
```

## Models Reference

### Project

Represents a Claude Code project directory.

```python
from models import Project

# From original path
project = Project.from_path("/Users/me/my-project")

# From encoded directory name
project = Project.from_encoded_name("-Users-me-my-project")

# Properties
project.path              # "/Users/me/my-project"
project.encoded_name      # "-Users-me-my-project"
project.project_dir       # Path to ~/.claude/projects/-Users-me-my-project
project.exists            # bool
project.session_count     # int
project.agent_count       # int

# Methods
project.list_sessions()   # List[Session]
project.list_agents()     # List[Agent] (standalone)
project.get_session(uuid) # Optional[Session]
project.get_agent(id)     # Optional[Agent]
project.get_all_subagents() # List[Agent] (across all sessions)
```

### Session

Represents a main conversation session.

```python
from models import Session

session = project.list_sessions()[0]

# Properties
session.uuid              # Session UUID
session.jsonl_path        # Path to JSONL file
session.exists            # bool
session.message_count     # int
session.start_time        # Optional[datetime]
session.end_time          # Optional[datetime]
session.duration_seconds  # Optional[float]

# Resource checks
session.has_debug_log     # bool
session.has_file_history  # bool
session.has_subagents     # bool
session.has_tool_results  # bool

# Message access (lazy-loaded)
session.iter_messages()          # Iterator[Message]
session.list_messages()          # List[Message]
session.iter_user_messages()     # Iterator[UserMessage]
session.iter_assistant_messages() # Iterator[AssistantMessage]

# Related resources
session.list_subagents()    # List[Agent]
session.list_tool_results() # List[ToolResult]
session.list_todos()        # List[TodoItem]
session.read_debug_log()    # Optional[str]

# Analytics
session.get_usage_summary() # TokenUsage (aggregated)
session.get_models_used()   # Set[str]
session.get_tools_used()    # Counter[str]
session.get_git_branches()  # Set[str]
session.get_working_directories() # Set[str]
```

### Agent

Represents both standalone agents and subagents.

```python
from models import Agent

# Standalone agents
agents = project.list_agents()

# Subagents
subagents = session.list_subagents()

# Properties
agent.agent_id            # Short hex ID (e.g., "a5793c3")
agent.jsonl_path          # Path to JSONL file
agent.is_subagent         # bool
agent.parent_session_uuid # Optional[str]
agent.slug                # Optional[str] (e.g., "eager-puzzling-fairy")
agent.exists              # bool
agent.message_count       # int
agent.start_time          # Optional[datetime]
agent.end_time            # Optional[datetime]

# Methods
agent.iter_messages()     # Iterator[Message]
agent.list_messages()     # List[Message]
agent.get_usage_summary() # TokenUsage
```

### Messages

Three message types parsed from JSONL:

```python
from models import UserMessage, AssistantMessage, FileHistorySnapshot

for msg in session.iter_messages():
    # Common fields
    msg.uuid           # str
    msg.timestamp      # datetime
    msg.parent_uuid    # Optional[str] (for threading)
    msg.session_id     # Optional[str]
    msg.is_sidechain   # bool
    msg.cwd            # Optional[str]
    msg.git_branch     # Optional[str]
    msg.version        # Optional[str]
    
    if isinstance(msg, UserMessage):
        msg.content    # str
        msg.user_type  # Optional[str]
        
    elif isinstance(msg, AssistantMessage):
        msg.model          # Optional[str] (e.g., "claude-opus-4-5-20251101")
        msg.content_blocks # List[ContentBlock]
        msg.usage          # Optional[TokenUsage]
        msg.stop_reason    # Optional[str]
        msg.text_content   # str (concatenated text blocks)
        msg.tool_calls     # List[ToolUseBlock]
        msg.tool_names     # List[str]
```

### Content Blocks

Assistant message content is a list of typed blocks:

```python
from models import TextBlock, ThinkingBlock, ToolUseBlock

for msg in session.iter_assistant_messages():
    for block in msg.content_blocks:
        if isinstance(block, TextBlock):
            print(block.text)
            
        elif isinstance(block, ThinkingBlock):
            print(block.thinking)
            print(block.signature)
            
        elif isinstance(block, ToolUseBlock):
            print(f"{block.name}({block.input})")
            print(block.id)  # toolu_xxx
```

### TokenUsage

Token statistics with aggregation support:

```python
from models import TokenUsage

usage = session.get_usage_summary()

usage.input_tokens                # int
usage.output_tokens               # int
usage.cache_creation_input_tokens # int
usage.cache_read_input_tokens     # int
usage.service_tier                # Optional[str]

# Computed properties
usage.total_input    # input_tokens + cache_read_input_tokens
usage.total_tokens   # total_input + output_tokens
usage.cache_hit_rate # float (0.0 - 1.0)

# Aggregation
total = TokenUsage.zero()
for msg in session.iter_assistant_messages():
    if msg.usage:
        total = total + msg.usage
```

### ToolResult

Large tool outputs stored on disk:

```python
from models import ToolResult

for result in session.list_tool_results():
    result.tool_use_id  # str (toolu_xxx)
    result.path         # Path
    result.exists       # bool
    result.size_bytes   # int
    
    content = result.read_content()      # str (raises if missing)
    content = result.read_content_safe() # Optional[str]
```

### TodoItem

Session todo list items:

```python
from models import TodoItem

for todo in session.list_todos():
    todo.content      # str
    todo.status       # "pending" | "in_progress" | "completed"
    todo.active_form  # Optional[str]
```

## Common Patterns

### Aggregate Usage Across Project

```python
from models import Project, TokenUsage

project = Project.from_path("/Users/me/my-project")
total = TokenUsage.zero()

for session in project.list_sessions():
    total = total + session.get_usage_summary()

print(f"Total tokens: {total.total_tokens:,}")
print(f"Cache hit rate: {total.cache_hit_rate:.1%}")
```

### Find Sessions by Model

```python
opus_sessions = [
    s for s in project.list_sessions()
    if "opus" in str(s.get_models_used())
]
```

### Extract All Tool Calls

```python
from models import ToolUseBlock

for session in project.list_sessions():
    for msg in session.iter_assistant_messages():
        for block in msg.content_blocks:
            if isinstance(block, ToolUseBlock):
                print(f"{block.name}: {block.input}")
```

### Session Timeline

```python
from datetime import datetime

sessions = sorted(
    project.list_sessions(),
    key=lambda s: s.start_time or datetime.min
)

for s in sessions:
    start = s.start_time.strftime("%Y-%m-%d %H:%M") if s.start_time else "?"
    print(f"{start}: {s.uuid[:8]}... ({s.message_count} msgs)")
```

## Error Handling

All models are designed to be resilient to missing or malformed data:

```python
from models import Project, Session

# Safe project loading
project = Project.from_path("/path/to/project")
if not project.exists:
    print("No Claude data found for this project")

# Safe session access
session = project.get_session("nonexistent-uuid")  # Returns None

# Safe tool result reading
for result in session.list_tool_results():
    content = result.read_content_safe()  # Returns None if missing
    if content:
        print(content)

# Iterate safely (empty iterators for missing data)
for msg in session.iter_messages():  # Won't raise if file missing
    pass
```

## Performance Notes

- **Lazy Loading**: Messages are loaded on-demand via `iter_messages()`. Use iterators for large sessions to avoid loading everything into memory.
- **Caching**: Session metadata (message count, start/end times) is cached after first access.
- **Batch Processing**: For project-wide analytics, iterate over sessions one at a time rather than loading all at once.

```python
# Memory-efficient pattern for large projects
from models import Project, TokenUsage

project = Project.from_path("/path/to/project")
total = TokenUsage.zero()

for session in project.list_sessions():
    # Messages are loaded lazily, then released
    total = total + session.get_usage_summary()
    
print(f"Total tokens across all sessions: {total.total_tokens:,}")
```

## File Structure Reference

```
~/.claude/
├── projects/{encoded-path}/
│   ├── {session-uuid}.jsonl          # Main session
│   ├── {session-uuid}/
│   │   ├── tool-results/toolu_*.txt  # Large tool outputs
│   │   └── subagents/agent-*.jsonl   # Subagent sessions
│   └── agent-{id}.jsonl              # Standalone agents
├── debug/{session-uuid}.txt          # Debug logs
├── file-history/{session-uuid}/      # File backups
└── todos/{session-uuid}-*.json       # Todo lists
```

## See Also

- [Main README](../README.md) — Installation, quick start, and example script
- [session_story.py](../session_story.py) — Example script for generating session activity reports
