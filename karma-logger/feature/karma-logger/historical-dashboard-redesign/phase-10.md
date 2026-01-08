# Phase 10: Power Features

**Scope**: Command palette, bulk operations, export modal, URL state persistence.

**Files**: `public/app.js`, `public/style.css`

**Effort**: High | **Impact**: Medium

---

## Overview

Advanced features for power users: command palette for quick actions, bulk selection and operations, data export, and URL-based state for shareability.

---

## 10.1 Command Palette

### Invoke with `⌘+K` (Mac) or `Ctrl+K` (Windows/Linux)

### HTML

```html
<dialog class="command-palette" id="command-palette">
  <div class="command-palette__search">
    <span class="command-palette__icon">></span>
    <input 
      type="text" 
      class="command-palette__input" 
      placeholder="Type a command..." 
      autocomplete="off"
    >
  </div>
  
  <div class="command-palette__results">
    <section class="command-section">
      <h4 class="command-section__title">Recent</h4>
      <ul class="command-list" id="recent-commands"></ul>
    </section>
    
    <section class="command-section">
      <h4 class="command-section__title">Commands</h4>
      <ul class="command-list" id="all-commands"></ul>
    </section>
  </div>
</dialog>
```

### CSS

```css
.command-palette {
  position: fixed;
  top: 20%;
  left: 50%;
  transform: translateX(-50%);
  width: 90%;
  max-width: 600px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 0;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.command-palette::backdrop {
  background: rgba(0, 0, 0, 0.6);
}

.command-palette__search {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.command-palette__icon {
  color: var(--primary);
  font-family: var(--font-mono);
}

.command-palette__input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 1rem;
  outline: none;
}

.command-palette__input::placeholder {
  color: var(--text-muted);
}

.command-palette__results {
  max-height: 400px;
  overflow-y: auto;
}

.command-section {
  padding: 0.5rem 0;
}

.command-section__title {
  padding: 0.5rem 1rem;
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.command-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.command-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  cursor: pointer;
  transition: background 100ms ease-out;
}

.command-item:hover,
.command-item.is-selected {
  background: var(--bg-hover);
}

.command-item__icon {
  width: 1.5rem;
  text-align: center;
  color: var(--text-muted);
}

.command-item__text {
  flex: 1;
  color: var(--text-primary);
}

.command-item__shortcut {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-muted);
}
```

### JavaScript

```javascript
class CommandPalette {
  constructor() {
    this.dialog = document.getElementById('command-palette');
    this.input = this.dialog.querySelector('.command-palette__input');
    this.resultsContainer = this.dialog.querySelector('.command-palette__results');
    this.selectedIndex = 0;
    this.filteredCommands = [];
    this.recentCommands = this.loadRecent();
    
    this.commands = [
      { id: 'export', icon: '↓', text: 'Export data...', action: () => this.showExportModal() },
      { id: 'cost-alert', icon: '⚠', text: 'Set cost alert...', action: () => this.showAlertSettings() },
      { id: 'compare', icon: '⇄', text: 'Compare projects...', action: () => this.showCompare() },
      { id: 'filter-model', icon: '◇', text: 'Filter by model...', action: () => this.filterByModel() },
      { id: 'jump-date', icon: '📅', text: 'Jump to date...', action: () => this.jumpToDate() },
      { id: 'view-live', icon: '●', text: 'Go to Live view', shortcut: '1', action: () => switchView('live') },
      { id: 'view-projects', icon: '📁', text: 'Go to Projects view', shortcut: '2', action: () => switchView('projects') },
      { id: 'view-history', icon: '📈', text: 'Go to History view', shortcut: '3', action: () => switchView('history') },
      { id: 'refresh', icon: '↻', text: 'Refresh data', shortcut: 'R', action: () => refreshData() },
      { id: 'shortcuts', icon: '⌨', text: 'Keyboard shortcuts', shortcut: '?', action: () => showShortcutsModal() },
    ];
    
    this.setupListeners();
  }

  setupListeners() {
    // Open with Cmd+K / Ctrl+K
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        this.open();
      }
    });
    
    // Input handling
    this.input.addEventListener('input', () => this.filter());
    
    // Keyboard navigation
    this.input.addEventListener('keydown', (e) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          this.selectNext();
          break;
        case 'ArrowUp':
          e.preventDefault();
          this.selectPrev();
          break;
        case 'Enter':
          e.preventDefault();
          this.executeSelected();
          break;
        case 'Escape':
          e.preventDefault();
          this.close();
          break;
      }
    });
    
    // Close on backdrop click
    this.dialog.addEventListener('click', (e) => {
      if (e.target === this.dialog) {
        this.close();
      }
    });
  }

  open() {
    this.input.value = '';
    this.filter();
    this.dialog.showModal();
    this.input.focus();
  }

  close() {
    this.dialog.close();
  }

  filter() {
    const query = this.input.value.toLowerCase();
    
    if (!query) {
      this.filteredCommands = this.commands;
    } else {
      this.filteredCommands = this.commands.filter(cmd => 
        cmd.text.toLowerCase().includes(query)
      );
    }
    
    this.selectedIndex = 0;
    this.render();
  }

  render() {
    const recentHtml = this.recentCommands.length > 0 ? `
      <section class="command-section">
        <h4 class="command-section__title">Recent</h4>
        <ul class="command-list">
          ${this.recentCommands.map((cmd, i) => this.renderItem(cmd, i)).join('')}
        </ul>
      </section>
    ` : '';
    
    const commandsHtml = `
      <section class="command-section">
        <h4 class="command-section__title">Commands</h4>
        <ul class="command-list">
          ${this.filteredCommands.map((cmd, i) => 
            this.renderItem(cmd, i + this.recentCommands.length)
          ).join('')}
        </ul>
      </section>
    `;
    
    this.resultsContainer.innerHTML = recentHtml + commandsHtml;
    
    // Add click handlers
    this.resultsContainer.querySelectorAll('.command-item').forEach((el, i) => {
      el.addEventListener('click', () => {
        this.selectedIndex = i;
        this.executeSelected();
      });
    });
  }

  renderItem(cmd, index) {
    const isSelected = index === this.selectedIndex;
    return `
      <li class="command-item ${isSelected ? 'is-selected' : ''}" data-index="${index}">
        <span class="command-item__icon">${cmd.icon}</span>
        <span class="command-item__text">${cmd.text}</span>
        ${cmd.shortcut ? `<span class="command-item__shortcut">${cmd.shortcut}</span>` : ''}
      </li>
    `;
  }

  selectNext() {
    const total = this.recentCommands.length + this.filteredCommands.length;
    this.selectedIndex = (this.selectedIndex + 1) % total;
    this.render();
  }

  selectPrev() {
    const total = this.recentCommands.length + this.filteredCommands.length;
    this.selectedIndex = (this.selectedIndex - 1 + total) % total;
    this.render();
  }

  executeSelected() {
    const allCommands = [...this.recentCommands, ...this.filteredCommands];
    const cmd = allCommands[this.selectedIndex];
    
    if (cmd) {
      this.addToRecent(cmd);
      this.close();
      cmd.action();
    }
  }

  addToRecent(cmd) {
    this.recentCommands = [
      cmd,
      ...this.recentCommands.filter(c => c.id !== cmd.id)
    ].slice(0, 3);
    
    localStorage.setItem('karma-recent-commands', JSON.stringify(
      this.recentCommands.map(c => c.id)
    ));
  }

  loadRecent() {
    const stored = localStorage.getItem('karma-recent-commands');
    if (!stored) return [];
    
    const ids = JSON.parse(stored);
    return ids.map(id => this.commands.find(c => c.id === id)).filter(Boolean);
  }
}

// Initialize
const commandPalette = new CommandPalette();
```

---

## 10.2 Bulk Operations

### Multi-Select Mode

```html
<div class="bulk-controls" id="bulk-controls">
  <span class="bulk-controls__count">2 projects selected</span>
  <span class="bulk-controls__total">· $24.75 total</span>
  <div class="bulk-controls__actions">
    <button class="btn btn--small" onclick="bulkExport()">Export CSV</button>
    <button class="btn btn--small" onclick="bulkCompare()">Compare</button>
    <button class="btn btn--small" onclick="bulkSetBudget()">Set Budget</button>
    <button class="btn btn--small btn--ghost" onclick="cancelBulk()">Cancel</button>
  </div>
</div>
```

```css
.bulk-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: var(--bg-hover);
  border-radius: 6px;
  margin-bottom: 1rem;
}

.bulk-controls.hidden {
  display: none;
}

.bulk-controls__count {
  font-weight: 500;
  color: var(--text-primary);
}

.bulk-controls__total {
  color: var(--text-muted);
}

.bulk-controls__actions {
  margin-left: auto;
  display: flex;
  gap: 0.5rem;
}

/* Project card checkbox */
.project-card__checkbox {
  position: absolute;
  top: 0.75rem;
  left: 0.75rem;
  width: 18px;
  height: 18px;
  appearance: none;
  background: var(--bg-dark);
  border: 2px solid var(--border-color);
  border-radius: 3px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 150ms ease-out;
}

.projects-list.is-select-mode .project-card__checkbox,
.project-card:hover .project-card__checkbox {
  opacity: 1;
}

.project-card__checkbox:checked {
  background: var(--primary);
  border-color: var(--primary);
}

.project-card__checkbox:checked::after {
  content: '✓';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--bg-dark);
  font-size: 0.75rem;
}
```

### JavaScript

```javascript
class BulkSelector {
  constructor() {
    this.selected = new Set();
    this.isActive = false;
    this.controls = document.getElementById('bulk-controls');
  }

  toggle(projectId) {
    if (this.selected.has(projectId)) {
      this.selected.delete(projectId);
    } else {
      this.selected.add(projectId);
    }
    this.updateUI();
  }

  selectAll() {
    document.querySelectorAll('.project-card').forEach(card => {
      this.selected.add(card.dataset.project);
    });
    this.updateUI();
  }

  deselectAll() {
    this.selected.clear();
    this.updateUI();
  }

  updateUI() {
    const count = this.selected.size;
    
    // Update checkboxes
    document.querySelectorAll('.project-card__checkbox').forEach(cb => {
      cb.checked = this.selected.has(cb.dataset.project);
    });
    
    // Update controls
    if (count > 0) {
      this.controls.classList.remove('hidden');
      this.controls.querySelector('.bulk-controls__count').textContent = 
        `${count} project${count > 1 ? 's' : ''} selected`;
      
      // Calculate total cost
      const total = this.getSelectedTotal();
      this.controls.querySelector('.bulk-controls__total').textContent = 
        `· $${total.toFixed(2)} total`;
    } else {
      this.controls.classList.add('hidden');
    }
  }

  getSelectedTotal() {
    let total = 0;
    this.selected.forEach(projectId => {
      const card = document.querySelector(`[data-project="${projectId}"]`);
      const cost = parseFloat(card?.dataset.cost || 0);
      total += cost;
    });
    return total;
  }

  getSelectedProjects() {
    return Array.from(this.selected);
  }
}

const bulkSelector = new BulkSelector();
```

---

## 10.3 Export Modal

```html
<dialog class="modal modal--export" id="export-modal">
  <header class="modal__header">
    <h2 class="modal__title">Export Data</h2>
    <button class="modal__close" onclick="closeExportModal()">✕</button>
  </header>
  
  <form class="modal__body" id="export-form">
    <fieldset class="form-group">
      <legend class="form-group__title">Format</legend>
      <label class="radio-label">
        <input type="radio" name="format" value="csv" checked> CSV
      </label>
      <label class="radio-label">
        <input type="radio" name="format" value="json"> JSON
      </label>
      <label class="radio-label">
        <input type="radio" name="format" value="markdown"> Markdown
      </label>
    </fieldset>
    
    <fieldset class="form-group">
      <legend class="form-group__title">Scope</legend>
      <label class="radio-label">
        <input type="radio" name="scope" value="current" checked> 
        Current view (<span id="export-scope-label">karma, 7d</span>)
      </label>
      <label class="radio-label">
        <input type="radio" name="scope" value="all"> All projects
      </label>
      <label class="radio-label" id="export-selected-option" style="display: none;">
        <input type="radio" name="scope" value="selected"> 
        Selected only (<span id="export-selected-count">0</span> projects)
      </label>
    </fieldset>
    
    <fieldset class="form-group">
      <legend class="form-group__title">Include</legend>
      <label class="checkbox-label">
        <input type="checkbox" name="include" value="daily" checked> Daily summaries
      </label>
      <label class="checkbox-label">
        <input type="checkbox" name="include" value="sessions" checked> Session details
      </label>
      <label class="checkbox-label">
        <input type="checkbox" name="include" value="agents"> Agent-level data
      </label>
      <label class="checkbox-label">
        <input type="checkbox" name="include" value="raw"> Raw JSONL events
      </label>
    </fieldset>
  </form>
  
  <footer class="modal__footer">
    <button class="btn btn--ghost" onclick="closeExportModal()">Cancel</button>
    <button class="btn btn--primary" onclick="executeExport()">Export</button>
  </footer>
</dialog>
```

```javascript
async function executeExport() {
  const form = document.getElementById('export-form');
  const formData = new FormData(form);
  
  const options = {
    format: formData.get('format'),
    scope: formData.get('scope'),
    include: formData.getAll('include')
  };
  
  // Build export data
  const data = await buildExportData(options);
  
  // Generate file content
  let content, filename, mimeType;
  
  switch (options.format) {
    case 'csv':
      content = toCSV(data);
      filename = `karma-export-${Date.now()}.csv`;
      mimeType = 'text/csv';
      break;
    case 'json':
      content = JSON.stringify(data, null, 2);
      filename = `karma-export-${Date.now()}.json`;
      mimeType = 'application/json';
      break;
    case 'markdown':
      content = toMarkdown(data);
      filename = `karma-export-${Date.now()}.md`;
      mimeType = 'text/markdown';
      break;
  }
  
  // Trigger download
  downloadFile(content, filename, mimeType);
  closeExportModal();
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
```

---

## 10.4 URL State Persistence

```javascript
class URLState {
  constructor() {
    this.params = new URLSearchParams(window.location.search);
    this.setupPopState();
  }

  setupPopState() {
    window.addEventListener('popstate', () => {
      this.params = new URLSearchParams(window.location.search);
      this.apply();
    });
  }

  get(key) {
    return this.params.get(key);
  }

  set(key, value) {
    if (value === null || value === undefined || value === '') {
      this.params.delete(key);
    } else {
      this.params.set(key, value);
    }
    this.pushState();
  }

  setMultiple(updates) {
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') {
        this.params.delete(key);
      } else {
        this.params.set(key, value);
      }
    });
    this.pushState();
  }

  pushState() {
    const newUrl = this.params.toString() 
      ? `${window.location.pathname}?${this.params.toString()}`
      : window.location.pathname;
    
    window.history.pushState({}, '', newUrl);
  }

  apply() {
    const view = this.get('view');
    const project = this.get('project');
    const days = this.get('days');
    const session = this.get('session');
    
    if (view) switchView(view);
    if (project) setProjectFilter(project);
    if (days) setDateRange(parseInt(days));
    if (session) loadSession(session);
  }

  getShareableURL() {
    return window.location.href;
  }
}

const urlState = new URLState();

// Apply initial state on load
document.addEventListener('DOMContentLoaded', () => {
  urlState.apply();
});

// Update URL on view changes
function switchView(view) {
  urlState.set('view', view);
  // ... existing view switch logic
}

function setProjectFilter(project) {
  urlState.set('project', project);
  // ... existing filter logic
}

function setDateRange(days) {
  urlState.set('days', days);
  // ... existing date range logic
}
```

### Example URLs

```
/dashboard?view=history&project=karma&days=7
/dashboard?view=live&session=4d4c8731&expand=all
/dashboard?view=projects&sort=cost&order=desc&range=30
```

---

## Acceptance Criteria

- [ ] `⌘+K` / `Ctrl+K` opens command palette
- [ ] Command search filters results in real-time
- [ ] Arrow keys navigate command list
- [ ] Enter executes selected command
- [ ] Recent commands appear at top
- [ ] Multi-select mode enables checkboxes
- [ ] Bulk controls show count and total cost
- [ ] Export modal offers format/scope options
- [ ] Export generates downloadable file
- [ ] URL updates on view/filter changes
- [ ] URL state is restored on page load
- [ ] Share button copies URL to clipboard

---

## Dependencies

- Phase 8 (Keyboard Navigation - keyboard manager)

---

## Testing Checklist

- [ ] Command palette opens and closes correctly
- [ ] Search filters commands correctly
- [ ] Recent commands persist across sessions
- [ ] Bulk select works with shift+click
- [ ] Export generates valid CSV/JSON/Markdown
- [ ] URL updates on all state changes
- [ ] Browser back/forward restores state
- [ ] Shared URLs load correct view/filters
