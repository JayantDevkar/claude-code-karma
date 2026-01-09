# Phase 3a: Add Frontend SSE Handlers for Agent Events

> **Priority:** Medium | **Complexity:** Medium | **Type:** Code Implementation

## Objective

Add handlers in `app.js` for `agent:status` and `agent:progress` SSE events.

## Prerequisites

- Phase 2 complete (backend emitting events)

## Files to Modify

| File | Action |
|------|--------|
| `src/dashboard/public/app.js` | Add SSE event listeners |

## Implementation

```javascript
// In attachSSEHandlers() function, add:

es.addEventListener('agent:status', (event) => {
  markData();
  try {
    const data = JSON.parse(event.data);
    this.handleAgentStatus(data.agentId, data.status);
  } catch (err) {
    console.error('Failed to parse agent:status:', err);
  }
});

es.addEventListener('agent:progress', (event) => {
  markData();
  try {
    const data = JSON.parse(event.data);
    this.handleAgentProgress(data.agentId, data.progress);
  } catch (err) {
    console.error('Failed to parse agent:progress:', err);
  }
});

// Add handler methods to app object
handleAgentStatus(agentId, status) {
  console.log(`Agent ${agentId} status: ${status.state}`);
  // Will render in Phase 3b
  this.agentStatuses = this.agentStatuses || {};
  this.agentStatuses[agentId] = status;
  this.renderAgentPanel();
},

handleAgentProgress(agentId, progress) {
  console.log(`Agent ${agentId} progress: ${progress.percent}%`);
  // Will render in Phase 3c
  this.agentProgress = this.agentProgress || {};
  this.agentProgress[agentId] = progress;
  this.renderAgentPanel();
},

renderAgentPanel() {
  // Placeholder - implemented in Phase 3b
}
```

## Acceptance Criteria

- [x] SSE events logged to console
- [x] Agent state stored in app object
- [x] No JS errors on event receive
- [x] Events parsed correctly

## Testing

```bash
# Start dashboard
karma dashboard --radio

# Open browser console at localhost:3333

# Trigger status change
KARMA_AGENT_ID=test-1 KARMA_SESSION_ID=sess-1 karma radio set-status active

# Check browser console for log output
```

## Next Phase

→ Phase 3b: Agent status panel HTML
