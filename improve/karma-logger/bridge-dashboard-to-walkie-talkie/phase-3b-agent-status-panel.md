# Phase 3b: Agent Status Panel HTML Structure

> **Priority:** Medium | **Complexity:** Medium | **Type:** Code Implementation

## Objective

Add HTML structure for displaying agent status cards in the dashboard.

## Prerequisites

- Phase 3a complete (SSE handlers storing data)

## Files to Modify

| File | Action |
|------|--------|
| `src/dashboard/public/index.html` | Add agent panel section |
| `src/dashboard/public/app.js` | Implement `renderAgentPanel()` |

## Implementation (HTML)

```html
<!-- Add after existing metrics cards -->
<section id="agent-panel" class="agent-panel hidden">
  <h2>Active Agents</h2>
  <div id="agent-cards" class="agent-cards">
    <!-- Populated by JS -->
  </div>
</section>
```

## Implementation (JS)

```javascript
renderAgentPanel() {
  const panel = document.getElementById('agent-panel');
  const container = document.getElementById('agent-cards');

  const statuses = this.agentStatuses || {};
  const progress = this.agentProgress || {};

  if (Object.keys(statuses).length === 0) {
    panel.classList.add('hidden');
    return;
  }

  panel.classList.remove('hidden');
  container.innerHTML = Object.entries(statuses)
    .map(([id, status]) => this.renderAgentCard(id, status, progress[id]))
    .join('');
},

renderAgentCard(agentId, status, progress) {
  const stateClass = `agent-state-${status.state}`;
  const progressBar = progress
    ? `<div class="progress-bar"><div class="progress-fill" style="width:${progress.percent}%"></div></div>`
    : '';

  return `
    <div class="agent-card ${stateClass}">
      <div class="agent-header">
        <span class="agent-id">${agentId}</span>
        <span class="agent-state">${status.state}</span>
      </div>
      ${status.message ? `<div class="agent-message">${status.message}</div>` : ''}
      ${progressBar}
      <div class="agent-meta">
        <span>${status.model || 'unknown'}</span>
        <span>${status.agentType || 'agent'}</span>
      </div>
    </div>
  `;
}
```

## Acceptance Criteria

- [x] Panel hidden when no agents
- [x] Cards render for each agent
- [x] State displayed with visual indicator
- [x] Progress bar shows percentage
- [x] Panel updates in real-time

## Testing

Open dashboard, register multiple agents, verify cards appear.

## Next Phase

→ Phase 3c: Agent status CSS styles
