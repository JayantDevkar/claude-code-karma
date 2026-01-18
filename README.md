# claude-karma

Agents, skills, and tools for enhanced Claude Code development workflows.

## Project Structure

```
claude-karma/
├── agents/                  # Task orchestration agents
│   ├── fetch-plane-tasks/   # Plane MCP work item fetcher
│   ├── analyze-work-item/   # Work item content parser
│   └── plane-task-orchestrator/ # Sequential task delegation
│
├── karma-logger/            # Session metrics and agent coordination
│   ├── CLI commands         # status, watch, report, dashboard
│   ├── Web dashboard        # Real-time metrics visualization
│   └── Live sessions        # Hook-based session state tracking
│
├── captain-hooks/           # Claude Code hooks reference
│   ├── Hook documentation   # All 10 hook types documented
│   └── Pydantic models      # Type-safe Python models
│
├── philosophy/              # Agent development guidelines
│   ├── Core principles      # Single responsibility, tool minimalism
│   └── Best practices       # Naming, architecture, context engineering
│
└── skills/                  # Reusable skill definitions
```

## Subprojects

### [karma-logger](./karma-logger/)

Local metrics and cost tracking for Claude Code sessions. Features:
- Real-time token usage and cost monitoring
- Session history with SQLite persistence
- Interactive TUI and web dashboard
- Live session state tracking via Claude Code hooks
- Subagent tracking via JSONL inference

```bash
cd karma-logger && npm install && npm link
karma status    # Current session metrics
karma dashboard # Web-based dashboard
```

### [captain-hooks](./captain-hooks/)

Claude Code hooks reference and utilities:
- Documentation for all 10 hook types
- Pydantic models for type-safe hook handling
- Example configurations (YAML and JSON)

### Agent Philosophy

See [philosophy/](./philosophy/) for agent development guidelines:
- Single responsibility principle
- Tool minimalism (max 3 primary tools)
- Prompt brevity (<500 tokens)
- Test-Driven Agent Development (TDAD)

## Quick Start

1. **Install karma-logger:**
   ```bash
   cd karma-logger && npm install && npm link
   ```

2. **Enable live session tracking (optional):**
   ```bash
   # Install the session tracker script
   cp api/scripts/live_session_tracker.py ~/.local/bin/claude-karma-tracker
   chmod +x ~/.local/bin/claude-karma-tracker

   # Copy hooks configuration to your project
   cp api/scripts/hooks.yaml .claude/hooks.yaml
   ```

3. **Start monitoring:**
   ```bash
   karma dashboard
   ```

## Integration with Plane

This repository includes agents for Plane project management integration:
- Fetch work items from Plane API
- Parse and analyze task descriptions
- Orchestrate task delegation to specialized agents

Requires Plane MCP server configuration in Claude Code settings.

## License

MIT
