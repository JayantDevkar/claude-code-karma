# Phase 8: Keyboard Navigation

**Scope**: Global shortcuts, view-specific shortcuts, keyboard shortcuts help modal.

**Files**: `public/app.js`, `public/style.css`

**Effort**: Medium | **Impact**: High

---

## Overview

Add comprehensive keyboard navigation for power users. Keyboard-first interaction improves accessibility and productivity for developers who prefer staying on the keyboard.

---

## 8.1 Global Shortcuts

| Key | Action | Context |
|-----|--------|---------|
| `1` | Switch to Live view | Global |
| `2` | Switch to Projects view | Global |
| `3` | Switch to History view | Global |
| `r` | Refresh data | Global |
| `?` | Show keyboard shortcuts modal | Global |
| `/` | Focus search/filter | Global |
| `Esc` | Close modal / cancel | Global |

---

## 8.2 View-Specific Shortcuts

### Live View

| Key | Action |
|-----|--------|
| `e` | Expand all agents |
| `c` | Collapse all agents |
| `↑/↓` | Navigate agent tree |
| `←/→` | Collapse/expand node |

### Projects View

| Key | Action |
|-----|--------|
| `j/k` | Navigate project list |
| `Enter` | Open selected project |
| `s` | Toggle select mode |
| `a` | Select all |
| `g` | Toggle grid/list view |

### History View

| Key | Action |
|-----|--------|
| `[` | Previous time period |
| `]` | Next time period |
| `p` | Cycle project filter |
| `d` | Download current view |

---

## 8.3 Keyboard Manager Implementation

```javascript
class KeyboardManager {
  constructor() {
    this.shortcuts = new Map();
    this.enabled = true;
    this.currentView = 'live';
    this.setupListeners();
  }

  setupListeners() {
    document.addEventListener('keydown', (e) => {
      if (!this.enabled) return;
      if (this.isInputFocused()) return;
      
      this.handleKeydown(e);
    });
  }

  isInputFocused() {
    const active = document.activeElement;
    const tag = active?.tagName?.toLowerCase();
    return ['input', 'textarea', 'select'].includes(tag);
  }

  handleKeydown(e) {
    const key = this.normalizeKey(e);
    
    // Check view-specific shortcuts first
    const viewShortcut = this.shortcuts.get(`${this.currentView}:${key}`);
    if (viewShortcut) {
      e.preventDefault();
      viewShortcut.handler();
      return;
    }
    
    // Check global shortcuts
    const globalShortcut = this.shortcuts.get(`global:${key}`);
    if (globalShortcut) {
      e.preventDefault();
      globalShortcut.handler();
      return;
    }
  }

  normalizeKey(e) {
    const parts = [];
    if (e.metaKey || e.ctrlKey) parts.push('mod');
    if (e.shiftKey) parts.push('shift');
    if (e.altKey) parts.push('alt');
    parts.push(e.key.toLowerCase());
    return parts.join('+');
  }

  register(scope, key, description, handler) {
    this.shortcuts.set(`${scope}:${key}`, { description, handler });
  }

  setView(view) {
    this.currentView = view;
  }

  disable() {
    this.enabled = false;
  }

  enable() {
    this.enabled = true;
  }

  getShortcuts() {
    const result = { global: [], live: [], projects: [], history: [] };
    
    this.shortcuts.forEach((value, key) => {
      const [scope, shortcut] = key.split(':');
      if (result[scope]) {
        result[scope].push({ key: shortcut, description: value.description });
      }
    });
    
    return result;
  }
}

// Initialize and register shortcuts
const keyboard = new KeyboardManager();

// Global shortcuts
keyboard.register('global', '1', 'Switch to Live view', () => switchView('live'));
keyboard.register('global', '2', 'Switch to Projects view', () => switchView('projects'));
keyboard.register('global', '3', 'Switch to History view', () => switchView('history'));
keyboard.register('global', 'r', 'Refresh data', () => refreshData());
keyboard.register('global', '?', 'Show keyboard shortcuts', () => showShortcutsModal());
keyboard.register('global', '/', 'Focus search', () => focusSearch());
keyboard.register('global', 'escape', 'Close modal', () => closeModal());

// Live view shortcuts
keyboard.register('live', 'e', 'Expand all agents', () => expandAllAgents());
keyboard.register('live', 'c', 'Collapse all agents', () => collapseAllAgents());

// Projects view shortcuts
keyboard.register('projects', 'j', 'Next project', () => navigateProjects(1));
keyboard.register('projects', 'k', 'Previous project', () => navigateProjects(-1));
keyboard.register('projects', 'enter', 'Open project', () => openSelectedProject());
keyboard.register('projects', 'g', 'Toggle grid view', () => toggleProjectsView());

// History view shortcuts
keyboard.register('history', '[', 'Previous period', () => changePeriod(-1));
keyboard.register('history', ']', 'Next period', () => changePeriod(1));
keyboard.register('history', 'p', 'Cycle project filter', () => cycleProjectFilter());
keyboard.register('history', 'd', 'Download data', () => downloadData());
```

---

## 8.4 Navigation Helpers

```javascript
// Project list navigation
let selectedProjectIndex = -1;

function navigateProjects(direction) {
  const projects = document.querySelectorAll('.project-card');
  if (projects.length === 0) return;
  
  // Remove current selection
  if (selectedProjectIndex >= 0) {
    projects[selectedProjectIndex]?.classList.remove('is-keyboard-selected');
  }
  
  // Calculate new index
  selectedProjectIndex += direction;
  if (selectedProjectIndex < 0) selectedProjectIndex = projects.length - 1;
  if (selectedProjectIndex >= projects.length) selectedProjectIndex = 0;
  
  // Apply selection
  const selected = projects[selectedProjectIndex];
  selected.classList.add('is-keyboard-selected');
  selected.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  selected.focus();
}

function openSelectedProject() {
  const selected = document.querySelector('.project-card.is-keyboard-selected');
  if (selected) {
    selected.click();
  }
}

// Date range navigation
const DATE_RANGES = [7, 30, 90];
let currentRangeIndex = 1; // Default to 30d

function changePeriod(direction) {
  currentRangeIndex += direction;
  if (currentRangeIndex < 0) currentRangeIndex = DATE_RANGES.length - 1;
  if (currentRangeIndex >= DATE_RANGES.length) currentRangeIndex = 0;
  
  const days = DATE_RANGES[currentRangeIndex];
  updateDateRange(days);
  
  // Update button states
  document.querySelectorAll('.range-btn').forEach((btn, i) => {
    btn.classList.toggle('is-active', i === currentRangeIndex);
  });
}
```

---

## 8.5 Keyboard Selection Styling

```css
/* Keyboard navigation selection */
.project-card.is-keyboard-selected {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
  background: var(--bg-hover);
}

/* Focus visible for keyboard users only */
.project-card:focus:not(:focus-visible) {
  outline: none;
}

.project-card:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* Agent tree keyboard focus */
.agent-node.is-keyboard-focused {
  background: var(--bg-hover);
  outline: 1px solid var(--primary);
  outline-offset: -1px;
}
```

---

## 8.6 Keyboard Shortcuts Modal

### HTML

```html
<dialog class="modal modal--shortcuts" id="shortcuts-modal">
  <header class="modal__header">
    <h2 class="modal__title">Keyboard Shortcuts</h2>
    <button class="modal__close" onclick="closeShortcutsModal()">✕</button>
  </header>
  
  <div class="modal__body">
    <section class="shortcuts-section">
      <h3 class="shortcuts-section__title">Global</h3>
      <dl class="shortcuts-list" id="shortcuts-global"></dl>
    </section>
    
    <section class="shortcuts-section">
      <h3 class="shortcuts-section__title">Live View</h3>
      <dl class="shortcuts-list" id="shortcuts-live"></dl>
    </section>
    
    <section class="shortcuts-section">
      <h3 class="shortcuts-section__title">Projects</h3>
      <dl class="shortcuts-list" id="shortcuts-projects"></dl>
    </section>
    
    <section class="shortcuts-section">
      <h3 class="shortcuts-section__title">History</h3>
      <dl class="shortcuts-list" id="shortcuts-history"></dl>
    </section>
  </div>
</dialog>
```

### CSS

```css
.modal--shortcuts {
  max-width: 600px;
  width: 90%;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 0;
  color: var(--text-primary);
}

.modal--shortcuts::backdrop {
  background: rgba(0, 0, 0, 0.7);
}

.modal__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
}

.modal__title {
  font-size: 1.125rem;
  font-weight: 600;
}

.modal__close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.25rem;
  font-size: 1.25rem;
}

.modal__close:hover {
  color: var(--text-primary);
}

.modal__body {
  padding: 1.5rem;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
}

.shortcuts-section__title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
}

.shortcuts-list {
  display: grid;
  gap: 0.5rem;
}

.shortcuts-list dt {
  display: inline-block;
  background: var(--bg-dark);
  padding: 0.125rem 0.5rem;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.shortcuts-list dd {
  display: inline;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  margin-left: 0.75rem;
}
```

### JavaScript

```javascript
function showShortcutsModal() {
  const modal = document.getElementById('shortcuts-modal');
  const shortcuts = keyboard.getShortcuts();
  
  // Populate each section
  Object.entries(shortcuts).forEach(([scope, items]) => {
    const container = document.getElementById(`shortcuts-${scope}`);
    if (!container) return;
    
    container.innerHTML = items.map(({ key, description }) => `
      <div class="shortcut-item">
        <dt>${formatKey(key)}</dt>
        <dd>${description}</dd>
      </div>
    `).join('');
  });
  
  modal.showModal();
  keyboard.disable(); // Disable shortcuts while modal is open
}

function closeShortcutsModal() {
  const modal = document.getElementById('shortcuts-modal');
  modal.close();
  keyboard.enable();
}

function formatKey(key) {
  const formatted = key
    .replace('mod+', '⌘')
    .replace('shift+', '⇧')
    .replace('alt+', '⌥')
    .replace('escape', 'Esc')
    .replace('enter', '↵')
    .replace('arrowup', '↑')
    .replace('arrowdown', '↓')
    .replace('arrowleft', '←')
    .replace('arrowright', '→');
  
  return formatted.toUpperCase();
}
```

---

## 8.7 Keyboard Hint in UI

Show subtle hint for new users:

```html
<footer class="keyboard-hint">
  Press <kbd>?</kbd> for keyboard shortcuts
</footer>
```

```css
.keyboard-hint {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  opacity: 0.6;
}

.keyboard-hint kbd {
  background: var(--bg-dark);
  padding: 0.125rem 0.375rem;
  border-radius: 3px;
  border: 1px solid var(--border-color);
  font-family: var(--font-mono);
}

/* Hide after user has seen it */
.keyboard-hint.is-dismissed {
  display: none;
}
```

---

## Acceptance Criteria

- [ ] Number keys (1, 2, 3) switch between views
- [ ] `r` refreshes current view data
- [ ] `?` opens keyboard shortcuts modal
- [ ] `/` focuses search input (if present)
- [ ] `Esc` closes any open modal
- [ ] Arrow keys navigate agent tree
- [ ] `j/k` navigate project list
- [ ] `[/]` change date range in history
- [ ] Shortcuts are disabled when typing in input fields
- [ ] Modal shows all available shortcuts

---

## Dependencies

- Phase 1 (Layout Foundation)
- Phase 2 (Interaction States - focus styles)

---

## Testing Checklist

- [ ] All global shortcuts work from any view
- [ ] View-specific shortcuts only work in correct view
- [ ] Shortcuts don't fire when typing in inputs
- [ ] Modal opens and closes correctly
- [ ] Focus is trapped in modal while open
- [ ] Navigation maintains scroll position
- [ ] Screen reader announces shortcut actions
