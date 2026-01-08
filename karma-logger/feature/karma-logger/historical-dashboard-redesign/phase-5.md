# Phase 5: Agent Tree Redesign

**Scope**: ASCII tree connectors, model badges, expansion counter, running state animation.

**Files**: `public/app.js`, `public/style.css`

**Effort**: Medium | **Impact**: High

---

## Overview

Transform the agent hierarchy from a flat list to a terminal-inspired tree structure with visual connectors, colored model badges, and clear expansion state.

---

## 5.1 Target Appearance

### Current

```
Agent Hierarchy                          [Expand All]
└── agent-12345: opus ($26.10)
    agent-67890: opus ($11.62)
    agent-abcde: haiku ($0.71)
```

### Proposed

```
Agents                                     2/8 expanded
├── ◈ opus  main              $26.10  1.2M  
│   ├── ◇ opus  general-purpose   $11.62  450K
│   ├── ◇ opus  general-purpose   $5.18   200K
│   └── ◇ haiku Explore           $0.71   12K
└── ◇ sonnet unknown            $0.09   5K
```

---

## 5.2 HTML Structure

```html
<section class="agent-tree">
  <header class="agent-tree__header">
    <h3 class="title-section">Agents</h3>
    <span class="agent-tree__counter">2/8 expanded</span>
  </header>
  
  <div class="agent-tree__list" role="tree">
    <div class="agent-node agent-node--depth-0 is-expanded" 
         role="treeitem" 
         aria-expanded="true"
         tabindex="0">
      <span class="agent-node__connector">├──</span>
      <span class="agent-node__indicator">◈</span>
      <span class="agent-node__model agent-node__model--opus">opus</span>
      <span class="agent-node__type">main</span>
      <span class="agent-node__cost">$26.10</span>
      <span class="agent-node__tokens">1.2M</span>
    </div>
    
    <div class="agent-node agent-node--depth-1" 
         role="treeitem" 
         tabindex="-1">
      <span class="agent-node__connector">│   ├──</span>
      <span class="agent-node__indicator">◇</span>
      <span class="agent-node__model agent-node__model--opus">opus</span>
      <span class="agent-node__type">general-purpose</span>
      <span class="agent-node__cost">$11.62</span>
      <span class="agent-node__tokens">450K</span>
    </div>
    
    <!-- More nodes... -->
  </div>
</section>
```

---

## 5.3 CSS Styling

```css
.agent-tree {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  overflow: hidden;
}

.agent-tree__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color);
}

.agent-tree__counter {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.agent-tree__list {
  padding: 0.5rem 0;
  font-family: var(--font-mono);
  font-size: 0.8125rem;
}

/* Agent Node */
.agent-node {
  display: grid;
  grid-template-columns: auto auto auto 1fr auto auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 1rem;
  transition: background 100ms ease-out;
}

.agent-node:hover {
  background: var(--bg-hover);
}

.agent-node:focus-visible {
  outline: 1px solid var(--primary);
  outline-offset: -1px;
  background: var(--bg-hover);
}

/* Connector */
.agent-node__connector {
  color: var(--text-muted);
  white-space: pre;
  font-family: var(--font-mono);
}

/* Indicator */
.agent-node__indicator {
  width: 1rem;
  text-align: center;
}

.agent-node.is-expanded .agent-node__indicator {
  color: var(--primary);
}

.agent-node:not(.is-expanded) .agent-node__indicator {
  color: var(--text-muted);
}

/* Model Badge */
.agent-node__model {
  padding: 0.125rem 0.375rem;
  border-radius: 3px;
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: lowercase;
}

.agent-node__model--opus {
  color: var(--color-opus);
  background: rgba(124, 58, 237, 0.15);
}

.agent-node__model--sonnet {
  color: var(--color-sonnet);
  background: rgba(59, 130, 246, 0.15);
}

.agent-node__model--haiku {
  color: var(--color-haiku);
  background: rgba(16, 185, 129, 0.15);
}

/* Agent Type */
.agent-node__type {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Cost & Tokens */
.agent-node__cost,
.agent-node__tokens {
  text-align: right;
  color: var(--text-primary);
}

.agent-node__tokens {
  color: var(--text-muted);
  min-width: 4rem;
}
```

---

## 5.4 Running State Animation

```css
/* Running agent indicator */
.agent-node.is-running {
  position: relative;
}

.agent-node.is-running::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 100%;
  background: var(--primary);
  animation: running-pulse 1.5s ease-in-out infinite;
}

@keyframes running-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Running status dot */
.agent-node.is-running .agent-node__indicator::after {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 4px;
  background: var(--primary);
  border-radius: 50%;
  animation: status-pulse 2s infinite;
}
```

---

## 5.5 Tree Connector Logic

```javascript
function buildConnector(depth, isLast, parentConnectors) {
  if (depth === 0) {
    return isLast ? '└──' : '├──';
  }
  
  // Build prefix from parent state
  let prefix = '';
  for (let i = 0; i < depth; i++) {
    prefix += parentConnectors[i] ? '│   ' : '    ';
  }
  
  return prefix + (isLast ? '└──' : '├──');
}

function renderAgentTree(agents, parentId = null, depth = 0, parentConnectors = []) {
  const children = agents.filter(a => a.parentId === parentId);
  
  return children.map((agent, index) => {
    const isLast = index === children.length - 1;
    const connector = buildConnector(depth, isLast, parentConnectors);
    
    // Update connector state for children
    const childConnectors = [...parentConnectors];
    childConnectors[depth] = !isLast;
    
    const childrenHtml = renderAgentTree(
      agents, 
      agent.id, 
      depth + 1, 
      childConnectors
    );
    
    return `
      <div class="agent-node agent-node--depth-${depth} ${agent.isRunning ? 'is-running' : ''}"
           role="treeitem"
           tabindex="${depth === 0 ? '0' : '-1'}"
           data-agent-id="${agent.id}">
        <span class="agent-node__connector">${connector}</span>
        <span class="agent-node__indicator">${agent.children?.length ? '◈' : '◇'}</span>
        <span class="agent-node__model agent-node__model--${agent.model.toLowerCase()}">${agent.model}</span>
        <span class="agent-node__type">${agent.type || 'unknown'}</span>
        <span class="agent-node__cost">${formatCost(agent.cost)}</span>
        <span class="agent-node__tokens">${formatTokens(agent.tokens)}</span>
      </div>
      ${childrenHtml}
    `;
  }).join('');
}
```

---

## 5.6 Token Formatting

```javascript
function formatTokens(tokens) {
  if (tokens >= 1_000_000) {
    return (tokens / 1_000_000).toFixed(1) + 'M';
  }
  if (tokens >= 1_000) {
    return (tokens / 1_000).toFixed(0) + 'K';
  }
  return tokens.toString();
}

function formatCost(cost) {
  return '$' + cost.toFixed(2);
}
```

---

## 5.7 Keyboard Navigation

```javascript
function handleAgentTreeKeyboard(event) {
  const currentNode = event.target;
  const allNodes = [...document.querySelectorAll('.agent-node')];
  const currentIndex = allNodes.indexOf(currentNode);
  
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault();
      if (currentIndex < allNodes.length - 1) {
        allNodes[currentIndex + 1].focus();
      }
      break;
      
    case 'ArrowUp':
      event.preventDefault();
      if (currentIndex > 0) {
        allNodes[currentIndex - 1].focus();
      }
      break;
      
    case 'ArrowRight':
      event.preventDefault();
      if (currentNode.classList.contains('is-expanded')) {
        // Already expanded, move to first child
        const depth = parseInt(currentNode.dataset.depth);
        const next = allNodes[currentIndex + 1];
        if (next && parseInt(next.dataset.depth) > depth) {
          next.focus();
        }
      } else {
        // Expand node
        toggleAgentNode(currentNode);
      }
      break;
      
    case 'ArrowLeft':
      event.preventDefault();
      if (currentNode.classList.contains('is-expanded')) {
        // Collapse node
        toggleAgentNode(currentNode);
      } else {
        // Move to parent
        const depth = parseInt(currentNode.dataset.depth);
        for (let i = currentIndex - 1; i >= 0; i--) {
          if (parseInt(allNodes[i].dataset.depth) < depth) {
            allNodes[i].focus();
            break;
          }
        }
      }
      break;
      
    case 'Enter':
    case ' ':
      event.preventDefault();
      toggleAgentNode(currentNode);
      break;
  }
}

// Add event listener
document.querySelector('.agent-tree__list')?.addEventListener('keydown', handleAgentTreeKeyboard);
```

---

## 5.8 Expansion Counter

```javascript
function updateExpansionCounter() {
  const allExpandable = document.querySelectorAll('.agent-node:has(.agent-node)').length;
  const expanded = document.querySelectorAll('.agent-node.is-expanded').length;
  
  const counter = document.querySelector('.agent-tree__counter');
  if (counter) {
    counter.textContent = `${expanded}/${allExpandable} expanded`;
  }
}
```

---

## Acceptance Criteria

- [ ] ASCII connectors render correctly (├──, └──, │)
- [ ] Model badges have distinct colors (Opus purple, Sonnet blue, Haiku green)
- [ ] Running agents show pulse animation
- [ ] Expansion counter updates on toggle
- [ ] Keyboard navigation works (↑↓←→)
- [ ] Cost and tokens are right-aligned
- [ ] Deep nesting (4+ levels) renders correctly
- [ ] Focus state is visible for accessibility

---

## Dependencies

- Phase 1 (Layout Foundation)
- Phase 2 (Interaction States - hover/focus)

---

## Testing Checklist

- [ ] Tree renders with 1, 3, 5 levels of depth
- [ ] Last child uses └── connector
- [ ] Middle children use ├── connector
- [ ] Parent connector continues with │
- [ ] Click expands/collapses node
- [ ] Arrow keys navigate tree
- [ ] Running state animates
- [ ] Model badges have correct colors
