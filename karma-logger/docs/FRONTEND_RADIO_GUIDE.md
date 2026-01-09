# Frontend Radio UI Guide

This guide documents the frontend components for visualizing agent status from the karma radio system in the dashboard.

## Overview

The karma dashboard integrates with the walkie-talkie radio system to provide real-time visualization of agent status, progress, and hierarchies. When the dashboard is started with `--radio` flag, it:

1. Connects to the radio socket server
2. Auto-starts the **subagent watcher** to bridge JSONL files from Claude Code → Radio (solves missing KARMA_* env vars for Task-spawned subagents)
3. Displays agent status in the Agent Status Panel

This enables real-time tracking of all agents, including those spawned by Claude Code's Task tool without environment variable configuration.

## Agent Status Panel

The Agent Status Panel displays real-time status cards for all agents registered with the radio system.

### Features

- **Real-time status updates via SSE** - Status changes are pushed to the browser instantly
- **Progress bar visualization** - Shows completion percentage for ongoing tasks
- **State-based color coding** - Visual differentiation of agent states
- **Agent hierarchy tree view** - Parent-child relationships displayed in tree structure
- **Responsive layout** - Grid adapts to screen size

### HTML Structure

The Agent Status Panel is rendered in `index.html` with the following structure:

```html
<!-- Agent Status Panel (Radio) -->
<section id="agent-panel" class="agent-panel hidden">
  <h2>Agent Status</h2>
  <div id="agent-cards" class="agent-cards">
    <!-- Agent cards are rendered dynamically -->
  </div>
</section>
```

### JavaScript Integration

The panel is controlled by methods in `app.js`:

```javascript
// Handle agent status updates from walkie-talkie
handleAgentStatus(agentId, status) {
  this.agentStatuses[agentId] = status;
  this.renderAgentPanel();
}

// Handle agent progress updates from walkie-talkie
handleAgentProgress(agentId, progress) {
  this.agentProgress[agentId] = progress;
  this.renderAgentPanel();
}

// Render agent cards
renderAgentPanel() {
  // Shows/hides panel based on registered agents
  // Generates HTML for each agent card
}
```

## SSE Events

The dashboard subscribes to Server-Sent Events (SSE) for real-time updates.

### agent:status

Fired when an agent's status changes.

**Event Data:**
```json
{
  "agentId": "test-agent-001",
  "status": {
    "agentId": "test-agent-001",
    "sessionId": "session-e2e",
    "state": "active",
    "agentType": "task",
    "model": "sonnet",
    "message": "Processing file analysis"
  }
}
```

**Handler:**
```javascript
es.addEventListener('agent:status', (event) => {
  const data = JSON.parse(event.data);
  this.handleAgentStatus(data.agentId, data.status);
});
```

### agent:progress

Fired when an agent reports progress.

**Event Data:**
```json
{
  "agentId": "test-agent-001",
  "progress": {
    "percent": 75,
    "message": "Step 3 of 4 complete"
  }
}
```

**Handler:**
```javascript
es.addEventListener('agent:progress', (event) => {
  const data = JSON.parse(event.data);
  this.handleAgentProgress(data.agentId, data.progress);
});
```

## State Colors

Agent states are visually differentiated using CSS custom properties and state-specific classes.

| State | Color | CSS Class | Hex | Meaning |
|-------|-------|-----------|-----|---------|
| idle | Gray | `.agent-state-idle` | `#6b7280` | Waiting for work |
| pending | Gray | `.agent-state-pending` | `#6b7280` | Registered but not active |
| active | Blue | `.agent-state-active` | `#3b82f6` | Actively processing |
| working | Blue | `.agent-state-working` | `#3b82f6` | Actively processing |
| waiting | Amber | `.agent-state-waiting` | `#f59e0b` | Blocked on dependency |
| done | Green | `.agent-state-done` | `#10b981` | Completed successfully |
| completed | Green | `.agent-state-completed` | `#10b981` | Completed successfully |
| error | Red | `.agent-state-error` | `#ef4444` | Failed with error |
| failed | Red | `.agent-state-failed` | `#ef4444` | Failed with error |
| thinking | Purple | `.agent-state-thinking` | `#8b5cf6` | Processing/reasoning |
| tool_use | Cyan | `.agent-state-tool_use` | `#06b6d4` | Using a tool |

### CSS Implementation

```css
/* State Colors */
.agent-state-idle,
.agent-state-pending {
  --state-color: #6b7280;
}

.agent-state-working,
.agent-state-active {
  --state-color: #3b82f6;
}

.agent-state-waiting {
  --state-color: #f59e0b;
}

.agent-state-done,
.agent-state-completed {
  --state-color: #10b981;
}

.agent-state-error,
.agent-state-failed {
  --state-color: #ef4444;
}
```

## Agent Card Structure

Each agent is displayed as a card with the following structure:

```html
<div class="agent-card agent-state-active">
  <div class="agent-header">
    <span class="agent-id">test-agent-001</span>
    <span class="agent-state">active</span>
  </div>
  <div class="agent-message">Processing file analysis</div>
  <div class="progress-bar">
    <div class="progress-fill" style="width: 75%"></div>
  </div>
  <div class="agent-meta">
    <span>sonnet</span>
    <span>task</span>
  </div>
</div>
```

### Card Elements

| Element | Class | Description |
|---------|-------|-------------|
| Container | `.agent-card` | Card wrapper with state color border |
| Header | `.agent-header` | Contains ID and state badge |
| ID | `.agent-id` | Agent identifier (monospace font) |
| State | `.agent-state` | State badge with background color |
| Message | `.agent-message` | Current activity message |
| Progress | `.progress-bar` | Progress bar container |
| Fill | `.progress-fill` | Progress fill element |
| Meta | `.agent-meta` | Model and type information |

## Progress Bar

The progress bar shows task completion percentage:

```css
.agent-card .progress-bar {
  height: 4px;
  background: var(--border-color);
  border-radius: 2px;
  margin: 0.75rem 0;
  overflow: hidden;
}

.agent-card .progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}
```

The width is set dynamically based on the progress percentage:

```javascript
const progressBar = progress
  ? `<div class="progress-bar">
       <div class="progress-fill" style="width:${progress.percent}%"></div>
     </div>`
  : '';
```

## Responsive Layout

The agent cards grid adapts to different screen sizes:

```css
.agent-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

@media (max-width: 768px) {
  .agent-cards {
    grid-template-columns: 1fr;
  }
}
```

## API Endpoints

The dashboard uses these REST API endpoints for radio data:

### GET /api/radio/agents

Returns all registered agents with their current status.

**Response:**
```json
{
  "test-agent-001": {
    "agentId": "test-agent-001",
    "sessionId": "session-e2e",
    "rootSessionId": "session-e2e",
    "state": "completed",
    "startedAt": "2026-01-09T01:26:35.540Z",
    "updatedAt": "2026-01-09T01:26:55.442Z",
    "parentId": null,
    "parentType": "session",
    "agentType": "unknown",
    "model": "unknown",
    "metadata": {}
  }
}
```

### GET /api/radio/session/:sessionId/tree

Returns the agent hierarchy tree for a session.

**Response:**
```json
[
  {
    "agentId": "parent-001",
    "sessionId": "session-test",
    "state": "active",
    "agentType": "task",
    "model": "sonnet",
    "parentId": null,
    "children": [
      {
        "agentId": "child-001",
        "sessionId": "session-test",
        "state": "active",
        "agentType": "explore",
        "model": "sonnet",
        "parentId": "parent-001",
        "children": []
      }
    ]
  }
]
```

## Subagent Watcher Bridge

The dashboard automatically starts a subagent watcher when `--radio` is enabled. This bridges Claude Code's subagent JSONL files to the radio system.

### How It Works

When Claude Code's Task tool spawns subagents, they typically don't have `KARMA_*` environment variables set. The subagent watcher:

1. Monitors subagent JSONL files in `~/.claude/` (every 2 seconds)
2. Infers agent status from file timestamps and content
3. Registers agents with the radio system automatically
4. Sends `agent:status` and `agent:progress` SSE events

### Configuration

The subagent watcher is enabled automatically when you use:

```bash
karma dashboard --radio
# or
karma dashboard --persist-radio
```

No additional configuration needed. All subagents will be tracked without requiring hooks or env vars.

### Debug Mode

To see subagent watcher logs:

```bash
DEBUG=subagent-watcher karma dashboard --radio
```

Output includes:
- File discovery and monitoring
- Status inference from JSONL content
- Radio registration events

---

## Integration with Hooks (Optional)

To enable agent status reporting from Claude Code sessions via hooks (complementary to subagent watcher), configure hooks in `.claude/hooks.yaml`:

```yaml
hooks:
  PreToolUse:
    - command: |
        karma radio set-status active --message "Using $TOOL_NAME"
      env:
        KARMA_AGENT_ID: "{{agentId}}"
        KARMA_SESSION_ID: "{{sessionId}}"
      timeout: 5000
      on_error: ignore

  Stop:
    - command: |
        karma radio set-status completed
      env:
        KARMA_AGENT_ID: "{{agentId}}"
        KARMA_SESSION_ID: "{{sessionId}}"
      timeout: 5000
      on_error: ignore
```

See `karma-logger/examples/.claude/hooks.yaml` for a complete example configuration.

## Accessibility

The Agent Status Panel follows accessibility best practices:

- **Color + text**: State is indicated by both color and text label
- **Reduced motion**: Animations respect `prefers-reduced-motion` setting
- **Focus indicators**: Interactive elements have visible focus states
- **Semantic HTML**: Uses appropriate heading hierarchy

```css
@media (prefers-reduced-motion: reduce) {
  .agent-card,
  .progress-fill {
    transition: none;
  }
}
```

## Troubleshooting

### Panel not appearing

1. Verify dashboard started with `--radio` flag:
   ```bash
   karma dashboard --radio
   ```

2. Check if radio socket is running:
   ```bash
   ls -la /tmp/karma-radio.sock
   ```

3. Verify agents are registered:
   ```bash
   curl http://localhost:3333/api/radio/agents
   ```

### No real-time updates

1. Check SSE connection status in browser DevTools Network tab
2. Verify the dashboard console for SSE errors
3. Ensure `agent:status` events are being emitted

### Incorrect state colors

1. Verify the state value is one of the expected states
2. Check that the CSS class is correctly applied to the card
3. Inspect the `--state-color` CSS variable in DevTools
