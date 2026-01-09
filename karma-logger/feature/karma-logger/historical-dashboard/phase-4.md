# Phase 4: Frontend — Agent Tree

**Scope**: Visualize agent hierarchy within sessions.

**Files**: `public/index.html`, `public/app.js`, `public/style.css`

---

## UI Components

### 1. Agent Tree Container

Displayed within session detail view.

```html
<div id="agent-tree-view" class="agent-tree-view">
  <div class="tree-header">
    <h3>Agent Hierarchy</h3>
    <button id="expand-all-btn">Expand All</button>
  </div>
  <div id="agent-tree" class="agent-tree">
    <!-- Tree nodes rendered here -->
  </div>
</div>
```

### 2. Tree Node Structure

```html
<div class="tree-node" data-agent-id="abc123">
  <div class="node-content">
    <button class="expand-btn">▶</button>
    <span class="agent-badge sonnet">sonnet</span>
    <span class="agent-type">Explore</span>
    <span class="agent-cost">$0.12</span>
    <span class="agent-tokens">1.2k tokens</span>
  </div>
  <div class="node-children collapsed">
    <!-- Child nodes -->
  </div>
</div>
```

---

## JavaScript (app.js)

### Tree Builder

```javascript
function buildAgentTree(agents) {
  // Create lookup map
  const map = new Map();
  agents.forEach(a => {
    map.set(a.id, { ...a, children: [] });
  });

  // Build hierarchy
  const roots = [];
  for (const agent of map.values()) {
    if (agent.parent_id && map.has(agent.parent_id)) {
      map.get(agent.parent_id).children.push(agent);
    } else {
      roots.push(agent);
    }
  }

  // Sort children by start time
  const sortChildren = (node) => {
    node.children.sort((a, b) =>
      new Date(a.started_at) - new Date(b.started_at)
    );
    node.children.forEach(sortChildren);
  };
  roots.forEach(sortChildren);

  return roots;
}
```

### Render Functions

```javascript
function renderAgentTree(agents) {
  const tree = buildAgentTree(agents);
  const container = document.getElementById('agent-tree');
  container.innerHTML = tree.map(node => renderTreeNode(node, 0)).join('');
}

function renderTreeNode(node, depth) {
  const hasChildren = node.children.length > 0;
  const modelClass = getModelClass(node.model);
  const agentType = node.agent_type || 'main';

  return `
    <div class="tree-node" data-agent-id="${node.id}" style="--depth: ${depth}">
      <div class="node-content">
        ${hasChildren
          ? `<button class="expand-btn" onclick="toggleNode('${node.id}')">▶</button>`
          : `<span class="expand-placeholder"></span>`
        }
        <span class="agent-badge ${modelClass}">${getModelShort(node.model)}</span>
        <span class="agent-type">${escapeHtml(agentType)}</span>
        <span class="agent-cost">${formatCost(node.cost_total)}</span>
        <span class="agent-tokens">${formatTokens(node.tokens_in + node.tokens_out)}</span>
      </div>
      ${hasChildren ? `
        <div class="node-children collapsed">
          ${node.children.map(c => renderTreeNode(c, depth + 1)).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

function getModelClass(model) {
  if (!model) return 'unknown';
  if (model.includes('opus')) return 'opus';
  if (model.includes('sonnet')) return 'sonnet';
  if (model.includes('haiku')) return 'haiku';
  return 'other';
}

function getModelShort(model) {
  if (!model) return '?';
  if (model.includes('opus')) return 'opus';
  if (model.includes('sonnet')) return 'sonnet';
  if (model.includes('haiku')) return 'haiku';
  return model.split('-')[0];
}
```

### Expand/Collapse Logic

```javascript
function toggleNode(agentId) {
  const node = document.querySelector(`[data-agent-id="${agentId}"]`);
  const children = node.querySelector('.node-children');
  const btn = node.querySelector('.expand-btn');

  if (children) {
    children.classList.toggle('collapsed');
    btn.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
  }
}

function expandAll() {
  document.querySelectorAll('.node-children').forEach(el => {
    el.classList.remove('collapsed');
  });
  document.querySelectorAll('.expand-btn').forEach(btn => {
    btn.textContent = '▼';
  });
}

function collapseAll() {
  document.querySelectorAll('.node-children').forEach(el => {
    el.classList.add('collapsed');
  });
  document.querySelectorAll('.expand-btn').forEach(btn => {
    btn.textContent = '▶';
  });
}
```

---

## CSS (style.css)

```css
/* Agent tree */
.agent-tree-view {
  margin-top: 1rem;
}

.tree-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.agent-tree {
  font-family: monospace;
  font-size: 0.875rem;
}

.tree-node {
  position: relative;
  padding-left: calc(var(--depth, 0) * 1.5rem);
}

/* Tree lines */
.tree-node::before {
  content: '';
  position: absolute;
  left: calc(var(--depth, 0) * 1.5rem - 1rem);
  top: 0;
  height: 100%;
  width: 1px;
  background: var(--border);
}

.tree-node:last-child::before {
  height: 1rem;
}

.tree-node::after {
  content: '';
  position: absolute;
  left: calc(var(--depth, 0) * 1.5rem - 1rem);
  top: 1rem;
  width: 0.75rem;
  height: 1px;
  background: var(--border);
}

.tree-node[style*="--depth: 0"]::before,
.tree-node[style*="--depth: 0"]::after {
  display: none;
}

.node-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}

.expand-btn {
  width: 1.25rem;
  height: 1.25rem;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 0.75rem;
  color: var(--muted);
}

.expand-btn:hover {
  color: var(--text);
}

.expand-placeholder {
  width: 1.25rem;
}

.node-children {
  transition: max-height 0.2s;
}

.node-children.collapsed {
  display: none;
}

/* Agent badges */
.agent-badge {
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.agent-badge.opus {
  background: #4a1d96;
  color: white;
}

.agent-badge.sonnet {
  background: #1d4ed8;
  color: white;
}

.agent-badge.haiku {
  background: #059669;
  color: white;
}

.agent-badge.unknown,
.agent-badge.other {
  background: var(--muted-bg);
  color: var(--muted);
}

.agent-type {
  color: var(--text);
  min-width: 80px;
}

.agent-cost {
  color: var(--cost-color);
  min-width: 50px;
  text-align: right;
}

.agent-tokens {
  color: var(--muted);
  font-size: 0.75rem;
}
```

---

## Data Flow

```
Session Selected
      │
      ▼
GET /api/session/:id (returns agents array)
      │
      ▼
buildAgentTree(agents)
      │
      ▼
renderAgentTree(tree)
      │
      ▼
User expands/collapses nodes
```

---

## Acceptance Criteria

- [ ] Tree displays correct parent-child relationships
- [ ] Nodes sorted by start time within each level
- [ ] Expand/collapse toggles work correctly
- [ ] "Expand All" expands entire tree
- [ ] Model badges color-coded (opus/sonnet/haiku)
- [ ] Cost and token counts display per agent
- [ ] Tree handles sessions with no agents gracefully
- [ ] Tree handles orphan agents (missing parent)

---

## Dependencies

- **Phase 2**: `/api/session/:id` must return `agents` array

## Estimated Complexity

Medium — recursive rendering, tree building, CSS for lines.
