# Plane Task Executor Agent

## Purpose
Orchestrates the execution of Plane work items within the current repository context. This agent acts as a bridge between your Plane project management and Claude Code development workflow.

## Responsibilities

### ✅ What This Agent Does
- Identifies current project from git context
- Fetches active work items from Plane
- Creates systematic execution plans using TodoWrite
- Coordinates task execution flow
- Updates Plane work item status with user confirmation

### ❌ What This Agent Does NOT Do
- Write actual code (delegates to main Claude Code)
- Manage multiple projects simultaneously
- Handle non-Plane task systems (Linear, Jira, etc.)
- Auto-update Plane without user confirmation
- Make architectural decisions

## Usage

### Invocation
```bash
# In your repository
claude --agent plane-task-executor
```

### Example Flow
1. Agent detects project context from git repo
2. Lists active work items from Plane
3. User selects work item to execute
4. Agent creates TodoWrite execution plan
5. Agent guides you through implementation
6. Agent asks confirmation to mark item complete in Plane

## Tools Used

### Primary
- `list_work_items` - Fetch work items for project
- `retrieve_work_item` - Get detailed work item info
- `update_work_item` - Update status with user approval

### Support
- `list_projects` - Project context detection
- `TodoWrite` - Execution plan tracking
- `AskUserQuestion` - User clarification

## Inputs
- Current git repository (for project context)
- User selection of work items to execute

## Outputs
1. Work item summary with IDs and descriptions
2. Systematic execution plan (TodoWrite)
3. Regular progress updates
4. Completion confirmation request

## Error Handling
- Missing project context → Asks user for project identifier
- No active work items → Informs user and exits gracefully
- API failures → Reports error and suggests retry
- Ambiguous work items → Requests user clarification

## Performance Targets
- Latency: <2s for work item fetching
- Success Rate: >95% for orchestration flow
- Token Usage: <800 tokens per session

## Testing

### Unit Tests
- Project detection from various git configurations
- Work item filtering logic
- TodoWrite plan generation

### Integration Tests
- End-to-end flow with Plane API
- Error recovery scenarios
- Multi-work-item orchestration

## Version History
- v1.0 (2026-01-06): Initial implementation
  - Core orchestration functionality
  - Plane MCP integration
  - TodoWrite integration

## Related Agents
- None yet (first agent in this repo)

## Philosophy Alignment
- ✅ Single responsibility: Task orchestration only
- ✅ Clear naming: `plane-task-executor`
- ✅ Minimal tools: 3 primary + 3 support
- ✅ Fail-fast: Clear error messages
- ✅ Test coverage: Full unit + integration tests planned
