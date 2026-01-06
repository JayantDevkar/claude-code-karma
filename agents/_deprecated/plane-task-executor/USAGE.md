# Plane Task Executor - Usage Guide

## Quick Start

### 1. Prerequisites
- Claude Code installed
- Plane MCP server configured in `.claude/config.yaml`
- Active Plane workspace with projects

### 2. Configuration

Verify Plane MCP server is configured:
```bash
cat ~/.config/claude-code/config.yaml
```

Should include:
```yaml
mcp:
  servers:
    plane-project-task-manager:
      command: uvx
      args:
        - plane-mcp-server
      env:
        PLANE_API_KEY: your-api-key
        PLANE_API_URL: https://api.plane.so
        WORKSPACE_SLUG: your-workspace
```

### 3. Basic Usage

Navigate to your project repository:
```bash
cd ~/projects/claude-karma
claude --agent plane-task-executor
```

## Usage Examples

### Example 1: Execute Current Work Item

```bash
$ cd ~/projects/claude-karma
$ claude --agent plane-task-executor
```

**Agent Output**:
```
Detecting project from repository...
✓ Found: Claude Karma (CLAUDEKARM)

Fetching active work items...

Active Work Items:
1. CLAUDEKARM-4: Create an agent to execute todo work item tickets in plane
   Status: Todo
   Priority: None

2. CLAUDEKARM-2: Understand the Available Tools for the Agents
   Status: In Progress
   Assigned: jayantdevkar

Which work item would you like to work on? (1-2, or 'all')
```

**User Input**: `1`

**Agent Output**:
```
Selected: CLAUDEKARM-4

Creating execution plan...

Tasks:
□ Review Plane MCP server integration
□ Examine philosophy docs for agent patterns
□ Design plane-task-executor agent
□ Create agent.yaml configuration
□ Write README.md documentation
□ Create test scenarios
□ Validate agent functionality

Ready to proceed? (yes/no)
```

### Example 2: Handle Completed Tasks

```bash
$ claude --agent plane-task-executor
```

**Agent Output**:
```
Detecting project from repository...
✓ Found: Claude Karma (CLAUDEKARM)

Fetching active work items...

Active Work Items:
1. CLAUDEKARM-2: Understand the Available Tools for the Agents
   Status: In Progress

All other items are completed! 🎉

Would you like to work on CLAUDEKARM-2? (yes/no)
```

### Example 3: Update Status After Completion

**Scenario**: All TodoWrite items marked complete

**Agent Output**:
```
✓ All tasks completed!

Summary:
- Reviewed Plane MCP integration ✓
- Examined philosophy docs ✓
- Designed agent architecture ✓
- Created agent.yaml ✓
- Wrote documentation ✓
- Created tests ✓
- Validated functionality ✓

Would you like to mark CLAUDEKARM-4 as 'Done' in Plane? (yes/no)
```

**User Input**: `yes`

**Agent Output**:
```
Updating Plane...
✓ CLAUDEKARM-4 marked as Done

Great work! The task is now complete in Plane.
```

### Example 4: Manual Project Specification

**Scenario**: Working in a directory without git context

```bash
$ claude --agent plane-task-executor
```

**Agent Output**:
```
Unable to detect project automatically.

Available projects:
1. Claude Karma (CLAUDEKARM)
2. Claude Root (CLAUDEROOT)
3. Claude Code Tools (CLAUD)

Select project: (1-3)
```

## Advanced Usage

### Filter by Status

The agent automatically filters work items by status:
- Shows: `Todo`, `In Progress`
- Hides: `Done`, `Cancelled`

To see all items, you can modify the agent prompt or use Plane UI directly.

### Working with Modules/Cycles

If your work item is part of a module or cycle, the agent will display this context:

```
CLAUDEKARM-4: Create an agent...
Status: In Progress
Module: Core Functionality
Cycle: Sprint 1 (Jan 6 - Jan 13)
```

### Handling Subtasks

If a work item has sub-items in Plane, the agent will:
1. Show parent-child relationships
2. Suggest completing children first
3. Track parent completion based on children

```
CLAUDEKARM-4: Create an agent...
  ├─ CLAUDEKARM-4.1: Design architecture ✓
  ├─ CLAUDEKARM-4.2: Implement core logic (in progress)
  └─ CLAUDEKARM-4.3: Write tests (todo)

Should we focus on CLAUDEKARM-4.2? (yes/no)
```

## Troubleshooting

### Issue: "Unable to connect to Plane"

**Solution**:
1. Check MCP server configuration
2. Verify API key is valid
3. Test connection: `uvx plane-mcp-server --test`

### Issue: "No active work items found"

**Solution**:
- Check Plane UI to confirm work items exist
- Verify workspace and project settings
- Ensure work items are not all in "Done" status

### Issue: "Project not found"

**Solution**:
1. Check repository name matches Plane project
2. Specify project manually when prompted
3. Verify project identifier in Plane settings

### Issue: Agent doesn't create TodoWrite plan

**Solution**:
- Work item description may be too vague
- Agent will ask for clarification
- Provide more specific requirements

## Tips & Best Practices

### 1. Write Clear Work Item Descriptions
```markdown
✓ Good:
- Implement user authentication using JWT
- Write unit tests for auth module
- Update API documentation

✗ Bad:
- Fix the thing
- Make it better
- Do stuff
```

### 2. Use Plane's Description Format
The agent parses HTML/markdown from Plane. Use bullet points for sub-tasks:
```html
<ul>
  <li>First task</li>
  <li>Second task</li>
  <li>Third task</li>
</ul>
```

### 3. One Work Item at a Time
Focus on completing one item fully before moving to the next. The agent is optimized for serial execution.

### 4. Regular Status Updates
Let the agent update Plane status as you complete tasks. This keeps your team informed.

### 5. Use Plan Mode for Complex Items
For work items requiring architectural decisions:
```bash
$ claude --agent plane-task-executor --plan-mode
```

## Integration with Other Tools

### Git Integration
The agent respects git context:
- Detects branch names
- Suggests branch creation for work items
- Can link commits to work items (future feature)

### Skills Integration
Combine with other Claude Code skills:
```bash
# Execute work item and create commit
$ claude --agent plane-task-executor
# After completion
$ /commit
```

## Workflow Recommendations

### Daily Workflow
1. **Morning**: Start agent to see day's tasks
2. **Working**: Agent guides through execution
3. **Completion**: Agent updates Plane status
4. **Review**: Check Plane for team updates

### Sprint Workflow
1. Sprint start: Review all work items in cycle
2. Mid-sprint: Focus on in-progress items
3. Sprint end: Ensure all items marked complete

## Configuration Options

### Custom Filters (Future Feature)
```yaml
# agents/plane-task-executor/config.yaml
filters:
  priority: high,medium
  assignee: me
  labels: backend
```

### Notification Settings (Future Feature)
```yaml
notifications:
  on_completion: slack
  on_error: email
  daily_summary: true
```

## See Also
- [Agent README](./README.md)
- [Test Scenarios](./tests.md)
- [Philosophy Docs](../../philosophy/)
- [Plane MCP Server](../../integrations/plane-mcp-server/)
