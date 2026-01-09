# Phase 9: Celebrations & Alerts

**Scope**: Toast notifications, cost efficiency celebrations, cost alerts and budget warnings.

**Files**: `public/app.js`, `public/style.css`

**Effort**: Medium | **Impact**: Medium

---

## Overview

Add positive reinforcement for cost efficiency achievements and configurable cost alerts to help users stay within budgets. Celebrations should be subtle and non-intrusive.

---

## 9.1 Toast Notification System

### HTML Structure

```html
<div class="toast-container" aria-live="polite">
  <!-- Toasts are dynamically inserted here -->
</div>
```

### Toast Component

```html
<div class="toast toast--success" role="alert">
  <span class="toast__icon">✓</span>
  <span class="toast__message">Session complete · $0.42 (record!)</span>
  <button class="toast__close" aria-label="Dismiss">✕</button>
</div>
```

### CSS

```css
.toast-container {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  display: flex;
  flex-direction: column-reverse;
  gap: 0.5rem;
  z-index: 1000;
  max-width: 400px;
}

.toast {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  animation: toast-slide-in 200ms ease-out;
}

.toast.is-exiting {
  animation: toast-slide-out 200ms ease-in forwards;
}

@keyframes toast-slide-in {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes toast-slide-out {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}

.toast--success {
  border-left: 3px solid var(--primary);
}

.toast--success .toast__icon {
  color: var(--primary);
}

.toast--warning {
  border-left: 3px solid var(--color-warning);
}

.toast--warning .toast__icon {
  color: var(--color-warning);
}

.toast--celebration {
  border-left: 3px solid var(--color-trend-up);
  background: linear-gradient(
    135deg,
    rgba(34, 197, 94, 0.1) 0%,
    var(--bg-card) 50%
  );
}

.toast__icon {
  font-size: 1rem;
}

.toast__message {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.toast__close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.25rem;
}

.toast__close:hover {
  color: var(--text-primary);
}
```

### JavaScript

```javascript
class ToastManager {
  constructor() {
    this.container = document.querySelector('.toast-container');
    this.maxVisible = 3;
    this.defaultDuration = 4000;
  }

  show(message, options = {}) {
    const {
      type = 'info',
      duration = this.defaultDuration,
      icon = this.getDefaultIcon(type)
    } = options;

    const toast = this.createToast(message, type, icon);
    this.container.appendChild(toast);

    // Limit visible toasts
    const toasts = this.container.querySelectorAll('.toast');
    if (toasts.length > this.maxVisible) {
      this.dismiss(toasts[0]);
    }

    // Auto-dismiss
    if (duration > 0) {
      setTimeout(() => this.dismiss(toast), duration);
    }

    return toast;
  }

  createToast(message, type, icon) {
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
      <span class="toast__icon">${icon}</span>
      <span class="toast__message">${message}</span>
      <button class="toast__close" aria-label="Dismiss">✕</button>
    `;

    toast.querySelector('.toast__close').addEventListener('click', () => {
      this.dismiss(toast);
    });

    return toast;
  }

  dismiss(toast) {
    toast.classList.add('is-exiting');
    setTimeout(() => toast.remove(), 200);
  }

  getDefaultIcon(type) {
    const icons = {
      success: '✓',
      warning: '⚠',
      error: '✕',
      celebration: '★',
      info: 'ℹ'
    };
    return icons[type] || icons.info;
  }
}

const toast = new ToastManager();
```

---

## 9.2 Celebration Triggers

```javascript
class CelebrationManager {
  constructor(toastManager) {
    this.toast = toastManager;
    this.settings = this.loadSettings();
    this.history = [];
  }

  loadSettings() {
    const stored = localStorage.getItem('karma-celebration-settings');
    return stored ? JSON.parse(stored) : {
      showEfficiency: true,
      showMilestones: true,
      showStreaks: false,
      dailyCostTarget: null
    };
  }

  saveSettings(settings) {
    this.settings = { ...this.settings, ...settings };
    localStorage.setItem('karma-celebration-settings', JSON.stringify(this.settings));
  }

  checkSessionComplete(session) {
    if (!this.settings.showMilestones) return;

    const avgCost = this.getAverageCost();
    if (avgCost && session.cost < avgCost * 0.5) {
      this.toast.show(
        `Session complete · $${session.cost.toFixed(2)} (56% below avg!)`,
        { type: 'celebration', icon: '★' }
      );
    }
  }

  checkWeeklyImprovement() {
    if (!this.settings.showMilestones) return;

    const thisWeek = this.getWeekCost(0);
    const lastWeek = this.getWeekCost(1);
    
    if (lastWeek && thisWeek < lastWeek * 0.9) {
      const pct = Math.round((1 - thisWeek / lastWeek) * 100);
      this.toast.show(
        `Weekly win! ${pct}% less than last week`,
        { type: 'celebration', icon: '✓', duration: 6000 }
      );
    }
  }

  checkCacheEfficiency(session) {
    if (!this.settings.showEfficiency) return;

    const cacheHitRate = session.cacheReadTokens / 
      (session.tokensIn + session.cacheReadTokens);
    
    if (cacheHitRate > 0.7) {
      const savings = this.estimateCacheSavings(session);
      this.toast.show(
        `Great cache usage! ${Math.round(cacheHitRate * 100)}% hit rate, ~$${savings.toFixed(2)} saved`,
        { type: 'celebration', icon: '✦' }
      );
    }
  }

  checkStreak() {
    if (!this.settings.showStreaks) return;
    if (!this.settings.dailyCostTarget) return;

    const streak = this.calculateStreak();
    if (streak >= 5) {
      this.toast.show(
        `🔥 ${streak}-day streak under $${this.settings.dailyCostTarget}/day`,
        { type: 'celebration' }
      );
    }
  }

  getAverageCost() {
    // Calculate 7-day average from history
    const recent = this.history.slice(-7);
    if (recent.length === 0) return null;
    return recent.reduce((a, b) => a + b.cost, 0) / recent.length;
  }

  getWeekCost(weeksAgo) {
    // Get total cost for a given week
    // Implementation depends on data structure
    return null;
  }

  calculateStreak() {
    // Count consecutive days under target
    return 0;
  }

  estimateCacheSavings(session) {
    // Rough estimate: cache read is 10% of input cost
    const inputCostPer1k = 0.003;
    const cacheReadCostPer1k = 0.0003;
    const savedTokens = session.cacheReadTokens;
    return (savedTokens / 1000) * (inputCostPer1k - cacheReadCostPer1k);
  }
}
```

---

## 9.3 Cost Alerts

### Configuration UI

```html
<section class="settings-section">
  <h3 class="settings-section__title">Cost Alerts</h3>
  
  <div class="setting-row">
    <label class="setting-label">Daily Budget</label>
    <div class="setting-input">
      <span class="input-prefix">$</span>
      <input type="number" id="daily-budget" step="0.01" min="0" value="10.00">
    </div>
  </div>
  
  <div class="setting-row">
    <label class="checkbox-label">
      <input type="checkbox" id="warn-at-80" checked>
      Show warning at 80%
    </label>
  </div>
  
  <div class="setting-row">
    <label class="checkbox-label">
      <input type="checkbox" id="alert-at-100" checked>
      Show alert at 100%
    </label>
  </div>
</section>
```

### Alert Manager

```javascript
class CostAlertManager {
  constructor(toastManager) {
    this.toast = toastManager;
    this.settings = this.loadSettings();
    this.alertedToday = new Set();
  }

  loadSettings() {
    const stored = localStorage.getItem('karma-alert-settings');
    return stored ? JSON.parse(stored) : {
      dailyBudget: null,
      sessionBudget: null,
      warnAt80: true,
      alertAt100: true
    };
  }

  checkDailyBudget(todayTotal) {
    if (!this.settings.dailyBudget) return;

    const pct = (todayTotal / this.settings.dailyBudget) * 100;
    const today = new Date().toDateString();

    if (pct >= 100 && !this.alertedToday.has(`100-${today}`)) {
      this.alertedToday.add(`100-${today}`);
      this.showBudgetAlert(todayTotal, 100);
    } else if (pct >= 80 && pct < 100 && !this.alertedToday.has(`80-${today}`)) {
      this.alertedToday.add(`80-${today}`);
      if (this.settings.warnAt80) {
        this.showBudgetWarning(todayTotal, pct);
      }
    }
  }

  showBudgetWarning(current, pct) {
    this.toast.show(
      `Daily budget: $${current.toFixed(2)} / $${this.settings.dailyBudget.toFixed(2)} (${Math.round(pct)}%)`,
      { type: 'warning', icon: '⚠' }
    );
    this.updateHeaderWarning(current, pct);
  }

  showBudgetAlert(current, pct) {
    this.toast.show(
      `Daily budget exceeded: $${current.toFixed(2)} / $${this.settings.dailyBudget.toFixed(2)}`,
      { type: 'warning', icon: '⚠', duration: 0 } // Don't auto-dismiss
    );
    this.updateHeaderWarning(current, pct);
  }

  updateHeaderWarning(current, pct) {
    const banner = document.querySelector('.budget-banner');
    if (!banner) return;

    banner.classList.remove('hidden');
    banner.innerHTML = `
      <span class="budget-banner__icon">⚠</span>
      <span class="budget-banner__message">
        Daily: $${current.toFixed(2)} / $${this.settings.dailyBudget.toFixed(2)} (${Math.round(pct)}%)
      </span>
      <button class="budget-banner__dismiss">Dismiss</button>
    `;
  }
}
```

---

## 9.4 Budget Progress Indicator

```html
<article class="metric-card metric-card--compact metric-card--budget-warning">
  <div class="metric-card__header">
    <span class="metric-card__icon">⚠</span>
    <span class="metric-card__value">$8.42</span>
  </div>
  <div class="metric-card__label">84% of $10</div>
  <div class="metric-card__progress">
    <div class="progress-ring" data-progress="84"></div>
  </div>
</article>
```

```css
.metric-card--budget-warning {
  background: rgba(245, 158, 11, 0.1);
  border-color: var(--color-warning);
}

.metric-card__progress {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
}

.progress-ring {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: conic-gradient(
    var(--color-warning) calc(var(--progress) * 3.6deg),
    var(--bg-dark) 0deg
  );
}

.progress-ring::after {
  content: '';
  position: absolute;
  inset: 3px;
  background: var(--bg-card);
  border-radius: 50%;
}
```

---

## 9.5 Settings Panel

```javascript
function initSettingsPanel() {
  const celebrationSettings = new CelebrationManager(toast);
  const alertSettings = new CostAlertManager(toast);

  // Efficiency achievements toggle
  document.getElementById('show-efficiency')?.addEventListener('change', (e) => {
    celebrationSettings.saveSettings({ showEfficiency: e.target.checked });
  });

  // Cost milestones toggle
  document.getElementById('show-milestones')?.addEventListener('change', (e) => {
    celebrationSettings.saveSettings({ showMilestones: e.target.checked });
  });

  // Streak celebrations toggle
  document.getElementById('show-streaks')?.addEventListener('change', (e) => {
    celebrationSettings.saveSettings({ showStreaks: e.target.checked });
  });

  // Daily budget input
  document.getElementById('daily-budget')?.addEventListener('change', (e) => {
    const value = parseFloat(e.target.value);
    alertSettings.saveSettings({ 
      dailyBudget: value > 0 ? value : null 
    });
  });
}
```

---

## 9.6 Celebration Thresholds

| Achievement | Threshold | Frequency |
|-------------|-----------|-----------|
| Record low session | < 50% of 7-day avg | Per session |
| Weekly improvement | < 10% vs prev week | Weekly |
| Cache efficiency | > 70% cache hit | Per session |
| Agent efficiency | < 50% typical agents | Per task type |
| Cost streak | 5+ days under target | Daily |

---

## Acceptance Criteria

- [ ] Toast notifications appear at bottom-right
- [ ] Toasts auto-dismiss after 4 seconds
- [ ] Max 3 toasts visible at once
- [ ] Celebration triggers on record low cost
- [ ] Budget warning shows at 80%
- [ ] Budget alert shows at 100%
- [ ] Header warning bar appears when over budget
- [ ] All celebrations can be disabled in settings
- [ ] Settings persist in localStorage

---

## Dependencies

- Phase 4 (Sparklines - for metric card trend context)
- Phase 6 (Empty & Loading States - toast container positioning)

---

## Testing Checklist

- [ ] Toasts appear and animate correctly
- [ ] Click dismiss removes toast immediately
- [ ] Celebration triggers at correct thresholds
- [ ] Budget warnings show at 80%
- [ ] Budget alerts show at 100%
- [ ] Settings toggle celebrations on/off
- [ ] Settings persist after page reload
- [ ] Reduced motion respects preference
