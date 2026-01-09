# Phase 4: Sparklines & Trends

**Scope**: Canvas-based sparkline component, trend indicators, metric card integration.

**Files**: `public/charts.js`, `public/app.js`, `public/style.css`

**Effort**: Medium | **Impact**: High

---

## Overview

Add mini sparkline visualizations to metric cards showing the last 10 data points, plus trend indicators comparing current values to recent averages.

---

## 4.1 Sparkline Component

### Target Appearance

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ ▲ 21.2K     │ ▼ 1.8K      │ $ 0.2009    │ ⚡ 45        │
│ tokens in   │ tokens out  │ session     │ agents      │
│ ▁▂▃▄▅▆▇ +8% │ ▁▁▂▂▃▄▅ +2% │ ▂▃▄▅▆▇▇ 12% │ ▄▄▃▃▂▁▁ -4% │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

### HTML Structure

```html
<article class="metric-card metric-card--compact">
  <div class="metric-card__header">
    <span class="metric-card__icon">▲</span>
    <span class="metric-card__value">21.2K</span>
  </div>
  <div class="metric-card__label">tokens in</div>
  <div class="metric-card__footer">
    <canvas class="sparkline" width="60" height="20" data-values="[...]"></canvas>
    <span class="trend trend--up">+8%</span>
  </div>
</article>
```

---

## 4.2 Sparkline Class (JavaScript)

```javascript
// Add to charts.js

class Sparkline {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.options = {
      lineColor: '#10b981',
      fillColor: 'rgba(16, 185, 129, 0.2)',
      lineWidth: 1.5,
      padding: 2,
      ...options
    };
    this.data = [];
  }

  setData(values) {
    this.data = values;
    this.render();
  }

  render() {
    const { ctx, canvas, data, options } = this;
    const { lineColor, fillColor, lineWidth, padding } = options;
    
    if (!data || data.length < 2) {
      this.renderEmpty();
      return;
    }

    const width = canvas.width;
    const height = canvas.height;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Calculate bounds
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    
    // Calculate points
    const stepX = (width - padding * 2) / (data.length - 1);
    const points = data.map((val, i) => ({
      x: padding + i * stepX,
      y: height - padding - ((val - min) / range) * (height - padding * 2)
    }));
    
    // Draw fill
    ctx.beginPath();
    ctx.moveTo(points[0].x, height);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, height);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();
    
    // Draw line
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    points.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
    
    // Draw end point
    const lastPoint = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(lastPoint.x, lastPoint.y, 2, 0, Math.PI * 2);
    ctx.fillStyle = lineColor;
    ctx.fill();
  }

  renderEmpty() {
    const { ctx, canvas } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw dashed baseline
    ctx.beginPath();
    ctx.setLineDash([2, 2]);
    ctx.moveTo(2, canvas.height / 2);
    ctx.lineTo(canvas.width - 2, canvas.height / 2);
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

// Initialize sparklines
function initSparklines() {
  document.querySelectorAll('.sparkline').forEach(canvas => {
    const values = JSON.parse(canvas.dataset.values || '[]');
    const sparkline = new Sparkline(canvas);
    sparkline.setData(values);
    canvas._sparkline = sparkline; // Store reference for updates
  });
}
```

---

## 4.3 Trend Indicator

### Calculation

```javascript
function calculateTrend(current, history) {
  if (!history || history.length === 0) return null;
  
  const avg = history.reduce((a, b) => a + b, 0) / history.length;
  if (avg === 0) return null;
  
  const percentChange = ((current - avg) / avg) * 100;
  
  return {
    value: percentChange,
    direction: percentChange >= 0 ? 'up' : 'down',
    formatted: `${percentChange >= 0 ? '+' : ''}${percentChange.toFixed(0)}%`
  };
}
```

### CSS

```css
.metric-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.5rem;
  gap: 0.5rem;
}

.sparkline {
  flex: 1;
  height: 20px;
  max-width: 60px;
}

.trend {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: 500;
  padding: 0.125rem 0.25rem;
  border-radius: 2px;
}

.trend--up {
  color: var(--color-trend-up);
  background: rgba(34, 197, 94, 0.15);
}

.trend--down {
  color: var(--color-trend-down);
  background: rgba(239, 68, 68, 0.15);
}

.trend--neutral {
  color: var(--text-muted);
  background: rgba(100, 116, 139, 0.15);
}
```

---

## 4.4 Metrics Data Buffer

Store last N data points for sparklines:

```javascript
class MetricsBuffer {
  constructor(maxSize = 10) {
    this.maxSize = maxSize;
    this.buffers = {
      tokensIn: [],
      tokensOut: [],
      cost: [],
      agentCount: []
    };
  }

  push(metric, value) {
    if (!this.buffers[metric]) return;
    
    this.buffers[metric].push(value);
    
    if (this.buffers[metric].length > this.maxSize) {
      this.buffers[metric].shift();
    }
  }

  get(metric) {
    return this.buffers[metric] || [];
  }

  getAll() {
    return { ...this.buffers };
  }
}

// Usage
const metricsBuffer = new MetricsBuffer(10);

// On each metrics update
function updateMetrics(data) {
  metricsBuffer.push('tokensIn', data.tokensIn);
  metricsBuffer.push('tokensOut', data.tokensOut);
  metricsBuffer.push('cost', data.cost);
  metricsBuffer.push('agentCount', data.agentCount);
  
  // Update sparklines
  updateSparkline('tokens-in-sparkline', metricsBuffer.get('tokensIn'));
  updateSparkline('cost-sparkline', metricsBuffer.get('cost'));
}

function updateSparkline(id, values) {
  const canvas = document.getElementById(id);
  if (canvas && canvas._sparkline) {
    canvas._sparkline.setData(values);
  }
}
```

---

## 4.5 Color Variants

Different sparkline colors for different metrics:

```javascript
const SPARKLINE_COLORS = {
  tokensIn: {
    lineColor: '#22c55e',
    fillColor: 'rgba(34, 197, 94, 0.2)'
  },
  tokensOut: {
    lineColor: '#3b82f6',
    fillColor: 'rgba(59, 130, 246, 0.2)'
  },
  cost: {
    lineColor: '#10b981',
    fillColor: 'rgba(16, 185, 129, 0.2)'
  },
  agentCount: {
    lineColor: '#f59e0b',
    fillColor: 'rgba(245, 158, 11, 0.2)'
  }
};
```

---

## 4.6 Celebration State

When session cost is below average:

```html
<article class="metric-card metric-card--compact metric-card--celebrating">
  <div class="metric-card__header">
    <span class="metric-card__icon">★</span>
    <span class="metric-card__value">$0.0892</span>
  </div>
  <div class="metric-card__label">session cost</div>
  <div class="metric-card__footer">
    <canvas class="sparkline"></canvas>
    <span class="trend trend--down">56% below avg ↓</span>
  </div>
</article>
```

```css
.metric-card--celebrating {
  background: linear-gradient(
    135deg,
    rgba(16, 185, 129, 0.15) 0%,
    var(--bg-card) 50%
  );
  border-color: var(--primary);
  animation: celebrate-pulse 2s ease-out;
}

@keyframes celebrate-pulse {
  0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}
```

---

## 4.7 HiDPI Canvas Support

```javascript
function createHiDPICanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  
  return ctx;
}
```

---

## Acceptance Criteria

- [ ] Sparkline renders last 10 data points
- [ ] Sparkline updates on each metrics event
- [ ] Empty sparkline shows dashed baseline
- [ ] Trend indicator shows +/- percentage
- [ ] Trend colors: green for up, red for down
- [ ] Celebration state triggers when below average
- [ ] HiDPI displays render crisp sparklines
- [ ] Performance: <1ms per sparkline render

---

## Dependencies

- Phase 1 (Layout Foundation - metric card structure)

---

## Testing Checklist

- [ ] Sparklines render with varying data
- [ ] Single data point shows no line
- [ ] Empty data shows dashed line
- [ ] Trend calculation is correct
- [ ] Celebration animation plays once
- [ ] Canvas renders correctly on Retina displays
- [ ] No memory leaks on continuous updates
