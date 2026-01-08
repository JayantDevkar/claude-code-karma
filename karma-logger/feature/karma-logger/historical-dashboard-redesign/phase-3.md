# Phase 3: Error & Connection States

**Scope**: Connection error banner, error cards, SSE reconnection flow, partial data handling.

**Files**: `public/app.js`, `public/style.css`, `public/index.html`

**Effort**: Low | **Impact**: High

---

## Overview

Errors should be **informative, actionable, and non-blocking** where possible. The dashboard should degrade gracefully while providing clear recovery paths.

---

## 3.1 Connection States

### SSE Connection Indicator

```
Connected:    ● (filled, green, pulsing)
Reconnecting: ◐ (half-filled, yellow, spinning)
Disconnected: ○ (hollow, gray)
Error:        ✕ (red)
```

### HTML Structure

```html
<span class="connection-status" data-state="connected" title="Connected">
  <span class="connection-status__dot"></span>
</span>
```

### CSS

```css
.connection-status {
  display: inline-flex;
  align-items: center;
  cursor: help;
}

.connection-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  transition: all 150ms ease-out;
}

/* Connected */
.connection-status[data-state="connected"] .connection-status__dot {
  background: var(--primary);
  animation: status-pulse 2s infinite;
}

/* Reconnecting */
.connection-status[data-state="reconnecting"] .connection-status__dot {
  background: var(--color-warning);
  animation: spin 1s linear infinite;
}

/* Disconnected */
.connection-status[data-state="disconnected"] .connection-status__dot {
  background: transparent;
  border: 2px solid var(--text-muted);
}

/* Error */
.connection-status[data-state="error"] .connection-status__dot {
  background: var(--color-error);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

---

## 3.2 Connection Error Banner

### States

1. **Reconnecting** (auto): Yellow banner, spinner, "Reconnecting..."
2. **Retry Available**: Yellow banner, button, "Connection lost · Last data: 2m ago"
3. **Offline Mode**: Gray banner, "Offline · Showing cached data"

### HTML

```html
<div class="error-banner error-banner--warning" role="alert">
  <span class="error-banner__icon">⚠</span>
  <span class="error-banner__message">
    Connection lost · Reconnecting...
  </span>
  <button class="error-banner__action btn btn--small">Retry</button>
  <button class="error-banner__dismiss" aria-label="Dismiss">✕</button>
</div>
```

### CSS

```css
.error-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  background: rgba(245, 158, 11, 0.15);
  border-bottom: 1px solid rgba(245, 158, 11, 0.3);
}

.error-banner--warning {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.3);
}

.error-banner--error {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.3);
}

.error-banner--info {
  background: rgba(59, 130, 246, 0.15);
  border-color: rgba(59, 130, 246, 0.3);
}

.error-banner__icon {
  font-size: 1rem;
}

.error-banner--warning .error-banner__icon {
  color: var(--color-warning);
}

.error-banner--error .error-banner__icon {
  color: var(--color-error);
}

.error-banner__message {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.error-banner__action {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}

.error-banner__dismiss {
  padding: 0.25rem;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
}

.error-banner__dismiss:hover {
  color: var(--text-primary);
}
```

---

## 3.3 JavaScript: SSE Reconnection Logic

```javascript
// Add to app.js

class SSEConnection {
  constructor(url) {
    this.url = url;
    this.eventSource = null;
    this.retryCount = 0;
    this.maxRetries = 5;
    this.retryDelay = 1000; // Start with 1s, exponential backoff
    this.lastDataTime = null;
    this.state = 'disconnected'; // connected, reconnecting, disconnected, error
  }

  connect() {
    this.updateState('reconnecting');
    
    this.eventSource = new EventSource(this.url);
    
    this.eventSource.onopen = () => {
      this.retryCount = 0;
      this.retryDelay = 1000;
      this.updateState('connected');
      this.hideBanner();
    };
    
    this.eventSource.onerror = () => {
      this.eventSource.close();
      this.handleDisconnect();
    };
    
    this.eventSource.onmessage = (event) => {
      this.lastDataTime = new Date();
      // ... handle message
    };
  }

  handleDisconnect() {
    if (this.retryCount < this.maxRetries) {
      this.updateState('reconnecting');
      this.showBanner('reconnecting');
      
      setTimeout(() => {
        this.retryCount++;
        this.retryDelay = Math.min(this.retryDelay * 2, 30000); // Max 30s
        this.connect();
      }, this.retryDelay);
    } else {
      this.updateState('error');
      this.showBanner('retry');
    }
  }

  updateState(state) {
    this.state = state;
    const indicator = document.querySelector('.connection-status');
    if (indicator) {
      indicator.dataset.state = state;
      indicator.title = this.getStateLabel(state);
    }
  }

  getStateLabel(state) {
    const labels = {
      connected: 'Connected',
      reconnecting: 'Reconnecting...',
      disconnected: 'Disconnected',
      error: 'Connection failed'
    };
    return labels[state] || state;
  }

  showBanner(type) {
    const banner = document.querySelector('.error-banner');
    if (!banner) return;
    
    banner.classList.remove('hidden');
    
    if (type === 'reconnecting') {
      banner.querySelector('.error-banner__message').textContent = 
        'Connection lost · Reconnecting...';
      banner.querySelector('.error-banner__action').classList.add('hidden');
    } else if (type === 'retry') {
      const ago = this.lastDataTime 
        ? this.formatTimeAgo(this.lastDataTime) 
        : 'unknown';
      banner.querySelector('.error-banner__message').textContent = 
        `Connection lost · Last data: ${ago}`;
      banner.querySelector('.error-banner__action').classList.remove('hidden');
    }
  }

  hideBanner() {
    const banner = document.querySelector('.error-banner');
    if (banner) {
      banner.classList.add('hidden');
    }
  }

  formatTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    return `${Math.floor(seconds / 3600)}h ago`;
  }

  retry() {
    this.retryCount = 0;
    this.connect();
  }
}
```

---

## 3.4 Error Cards

### Full-Screen Error

```html
<div class="error-card error-card--full">
  <span class="error-card__icon">✕</span>
  <h3 class="error-card__title">Failed to load projects</h3>
  <p class="error-card__message">
    Could not connect to the Karma API.
  </p>
  <pre class="error-card__details">
    Error: ECONNREFUSED 127.0.0.1:3737
  </pre>
  <div class="error-card__actions">
    <button class="btn" onclick="location.reload()">Retry</button>
    <button class="btn btn--secondary">View Logs</button>
  </div>
</div>
```

### CSS

```css
.error-card {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-left: 3px solid var(--color-error);
  border-radius: 6px;
  padding: 1.5rem;
  text-align: center;
}

.error-card--full {
  max-width: 400px;
  margin: 3rem auto;
}

.error-card__icon {
  display: block;
  font-size: 2rem;
  color: var(--color-error);
  margin-bottom: 0.75rem;
}

.error-card__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.error-card__message {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.error-card__details {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-dark);
  padding: 0.75rem;
  border-radius: 4px;
  text-align: left;
  margin-bottom: 1rem;
  overflow-x: auto;
}

.error-card__actions {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}
```

---

## 3.5 Partial Data Errors

### Inline Warning

```html
<div class="inline-warning">
  <span class="inline-warning__icon">⚠</span>
  <span class="inline-warning__message">2 projects failed to load</span>
  <button class="btn btn--small">Retry</button>
</div>
```

### CSS

```css
.inline-warning {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: rgba(245, 158, 11, 0.1);
  border-radius: 4px;
  font-size: 0.875rem;
}

.inline-warning__icon {
  color: var(--color-warning);
}

.inline-warning__message {
  color: var(--text-secondary);
}
```

---

## 3.6 SSE Error Codes Mapping

```javascript
const SSE_ERROR_MESSAGES = {
  ECONNREFUSED: {
    title: 'Dashboard server not running',
    message: 'Run `karma dashboard` to start the server.',
    recoverable: false
  },
  TIMEOUT: {
    title: 'Server not responding',
    message: 'Will retry automatically...',
    recoverable: true
  },
  PARSE_ERROR: {
    title: 'Invalid server response',
    message: 'Logged to console. Continuing with partial data.',
    recoverable: true
  }
};

function handleSSEError(error) {
  const config = SSE_ERROR_MESSAGES[error.code] || {
    title: 'Connection error',
    message: error.message,
    recoverable: true
  };
  
  if (config.recoverable) {
    showBanner('warning', config.title);
  } else {
    showErrorCard(config.title, config.message);
  }
}
```

---

## Acceptance Criteria

- [ ] Connection indicator shows 4 states (connected/reconnecting/disconnected/error)
- [ ] Error banner appears on SSE disconnect
- [ ] Auto-reconnect with exponential backoff (1s → 2s → 4s → 8s → 16s → 30s max)
- [ ] Manual retry button after max retries
- [ ] Error cards display actionable messages
- [ ] Partial data errors show inline warnings
- [ ] All errors are dismissible

---

## Dependencies

- Phase 1 (Layout Foundation)
- Phase 2 (Interaction States - for button styles)

---

## Testing Checklist

- [ ] Kill server, verify reconnection flow
- [ ] Test max retry count (5 attempts)
- [ ] Verify "Last data: Xm ago" updates
- [ ] Test Retry button functionality
- [ ] Verify banner dismissal
- [ ] Test partial load scenario
- [ ] Verify error card displays correctly
