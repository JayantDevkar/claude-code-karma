/**
 * Karma Dashboard - Chart Manager
 * uPlot-based time-series visualization
 */

/**
 * Chart data retention configuration
 * 3600 points = 1 hour of data at 1Hz refresh rate
 * Adjust this value based on memory constraints and desired history
 */
const CHART_DATA_RETENTION_POINTS = 3600;

/**
 * ChartManager handles uPlot chart lifecycle and data management
 */
class ChartManager {
  constructor(containerId, options = {}) {
    this.containerId = containerId;
    this.chart = null;
    this.chartData = [];
    this.chartTimestamps = [];
    this.maxDataPoints = options.maxDataPoints || CHART_DATA_RETENTION_POINTS;
  }

  /**
   * Get the chart container element
   */
  getContainer() {
    return document.getElementById(this.containerId);
  }

  /**
   * Add a data point to the chart
   * @param {Object} data - { timestamp, tokensIn, tokensOut }
   */
  addDataPoint(data) {
    const timestamp = data.timestamp || Date.now();
    const tokensIn = data.tokensIn || 0;
    const tokensOut = data.tokensOut || 0;

    this.chartTimestamps.push(timestamp / 1000); // uPlot uses seconds
    this.chartData.push([tokensIn, tokensOut]);

    // Keep only last N data points (configurable retention)
    if (this.chartTimestamps.length > this.maxDataPoints) {
      this.chartTimestamps.shift();
      this.chartData.shift();
    }

    this.update();
  }

  /**
   * Format number for axis display
   */
  formatNumber(num) {
    if (num == null) return '0';
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toLocaleString();
  }

  /**
   * Build uPlot options
   */
  buildOptions(width) {
    const self = this;
    return {
      width: width || 800,
      height: 200,
      series: [
        {},
        {
          label: 'Tokens In',
          stroke: '#10b981',
          width: 2,
          fill: 'rgba(16, 185, 129, 0.1)'
        },
        {
          label: 'Tokens Out',
          stroke: '#6366f1',
          width: 2,
          fill: 'rgba(99, 102, 241, 0.1)'
        }
      ],
      axes: [
        {
          stroke: '#64748b',
          grid: { stroke: '#334155', width: 1 }
        },
        {
          stroke: '#64748b',
          grid: { stroke: '#334155', width: 1 },
          values: (u, ticks) => ticks.map(v => self.formatNumber(v))
        }
      ],
      scales: {
        x: { time: true },
        y: { auto: true }
      },
      legend: {
        show: true
      }
    };
  }

  /**
   * Prepare data for uPlot format [timestamps, series1, series2, ...]
   */
  prepareData() {
    return [
      this.chartTimestamps,
      this.chartData.map(d => d[0]), // tokensIn
      this.chartData.map(d => d[1])  // tokensOut
    ];
  }

  /**
   * Initialize or update the chart
   */
  update() {
    if (this.chartData.length < 2) return;

    const container = this.getContainer();
    if (!container) return;

    // Clear empty state placeholder
    const emptyState = container.querySelector('.empty-state');
    if (emptyState) {
      emptyState.remove();
    }

    const data = this.prepareData();

    if (this.chart) {
      // Update existing chart
      this.chart.setData(data);
    } else {
      // Create new chart
      const opts = this.buildOptions(container.clientWidth);
      this.chart = new uPlot(opts, data, container);
    }
  }

  /**
   * Resize chart to fit container
   */
  resize() {
    if (!this.chart) return;

    const container = this.getContainer();
    if (container) {
      this.chart.setSize({ width: container.clientWidth, height: 200 });
    }
  }

  /**
   * Destroy chart and clean up
   */
  destroy() {
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    this.chartData = [];
    this.chartTimestamps = [];
  }

  /**
   * Get current data point count
   */
  getDataPointCount() {
    return this.chartData.length;
  }

  /**
   * Get max data points configuration
   */
  getMaxDataPoints() {
    return this.maxDataPoints;
  }
}

/**
 * HistoryChart - Canvas-based bar chart with cumulative line
 * For displaying daily cost metrics
 */
class HistoryChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
    this.data = [];
    this.padding = { top: 30, right: 60, bottom: 50, left: 60 };
    this.colors = {
      bar: '#3b82f6',
      barHover: '#60a5fa',
      line: '#f59e0b',
      grid: '#334155',
      text: '#94a3b8',
      axis: '#64748b'
    };

    // Bind resize handler
    this._resizeHandler = this.handleResize.bind(this);
    window.addEventListener('resize', this._resizeHandler);
  }

  setData(dailyMetrics) {
    // Convert costs from cents to dollars for display
    this.data = (dailyMetrics || []).map(d => ({
      ...d,
      cost: (d.cost || 0) / 100
    }));
    this.render();
  }

  handleResize() {
    if (this._resizeTimeout) clearTimeout(this._resizeTimeout);
    this._resizeTimeout = setTimeout(() => this.render(), 100);
  }

  render() {
    if (!this.canvas || !this.ctx) return;

    const container = this.canvas.parentElement;
    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.canvas.style.width = rect.width + 'px';
    this.canvas.style.height = rect.height + 'px';
    this.ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;

    this.ctx.clearRect(0, 0, width, height);

    if (this.data.length === 0) {
      this.renderEmpty(width, height);
      return;
    }

    this.renderAxes(width, height);
    this.renderBars(width, height);
    this.renderLine(width, height);
    this.renderLegend(width, height);
  }

  renderEmpty(width, height) {
    this.ctx.fillStyle = this.colors.text;
    this.ctx.font = '14px -apple-system, BlinkMacSystemFont, sans-serif';
    this.ctx.textAlign = 'center';
    this.ctx.fillText('No data for selected period', width / 2, height / 2);
  }

  renderAxes(width, height) {
    const { padding, data, ctx, colors } = this;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Calculate max cost
    const maxCost = Math.max(...data.map(d => d.cost || 0), 0.01);
    const yTicks = this.getNiceScale(0, maxCost, 5);

    ctx.strokeStyle = colors.axis;
    ctx.fillStyle = colors.text;
    ctx.font = '11px Monaco, Menlo, monospace';
    ctx.textAlign = 'right';

    // Y-axis ticks and grid lines
    yTicks.forEach(tick => {
      const y = padding.top + chartHeight * (1 - tick / yTicks[yTicks.length - 1]);

      // Grid line
      ctx.beginPath();
      ctx.strokeStyle = colors.grid;
      ctx.setLineDash([2, 2]);
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label
      ctx.fillText('$' + tick.toFixed(2), padding.left - 8, y + 4);
    });

    // X-axis labels
    ctx.textAlign = 'center';
    const barWidth = chartWidth / data.length;
    const labelInterval = Math.max(1, Math.ceil(data.length / 7));

    data.forEach((d, i) => {
      if (i % labelInterval === 0 || i === data.length - 1) {
        const x = padding.left + barWidth * (i + 0.5);
        const date = new Date(d.day);
        const label = (date.getMonth() + 1) + '/' + date.getDate();
        ctx.fillText(label, x, height - padding.bottom + 20);
      }
    });
  }

  renderBars(width, height) {
    const { padding, data, ctx, colors } = this;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const maxCost = Math.max(...data.map(d => d.cost || 0), 0.01);
    const yTicks = this.getNiceScale(0, maxCost, 5);
    const yMax = yTicks[yTicks.length - 1];

    const barWidth = chartWidth / data.length;
    const barPadding = Math.max(1, barWidth * 0.15);

    data.forEach((d, i) => {
      const barHeight = ((d.cost || 0) / yMax) * chartHeight;
      const x = padding.left + barWidth * i + barPadding;
      const y = padding.top + chartHeight - barHeight;

      // Bar gradient
      const gradient = ctx.createLinearGradient(x, y, x, y + barHeight);
      gradient.addColorStop(0, colors.bar);
      gradient.addColorStop(1, '#1e40af');

      ctx.fillStyle = d.cost > 0 ? gradient : colors.grid;
      ctx.fillRect(x, y, barWidth - barPadding * 2, barHeight);
    });
  }

  renderLine(width, height) {
    const { padding, data, ctx, colors } = this;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const barWidth = chartWidth / data.length;

    // Calculate cumulative costs
    let cumulative = 0;
    const cumData = data.map(d => {
      cumulative += (d.cost || 0);
      return cumulative;
    });
    const maxCum = Math.max(...cumData, 0.01);

    // Draw line
    ctx.beginPath();
    ctx.strokeStyle = colors.line;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';

    cumData.forEach((cum, i) => {
      const x = padding.left + barWidth * (i + 0.5);
      const y = padding.top + chartHeight * (1 - cum / maxCum);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.stroke();

    // Draw points
    ctx.fillStyle = colors.line;
    cumData.forEach((cum, i) => {
      const x = padding.left + barWidth * (i + 0.5);
      const y = padding.top + chartHeight * (1 - cum / maxCum);
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  renderLegend(width, height) {
    const { ctx, colors, padding } = this;
    const legendY = padding.top - 15;

    ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'left';

    // Daily cost legend
    ctx.fillStyle = colors.bar;
    ctx.fillRect(padding.left, legendY - 8, 12, 12);
    ctx.fillStyle = colors.text;
    ctx.fillText('Daily Cost', padding.left + 18, legendY);

    // Cumulative legend
    ctx.strokeStyle = colors.line;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding.left + 100, legendY - 2);
    ctx.lineTo(padding.left + 115, legendY - 2);
    ctx.stroke();
    ctx.fillStyle = colors.text;
    ctx.fillText('Cumulative', padding.left + 120, legendY);
  }

  getNiceScale(min, max, ticks) {
    const range = max - min || 1;
    const step = range / ticks;
    const magnitude = Math.pow(10, Math.floor(Math.log10(step)));
    const residual = step / magnitude;

    let niceStep;
    if (residual <= 1.5) niceStep = magnitude;
    else if (residual <= 3) niceStep = 2 * magnitude;
    else if (residual <= 7) niceStep = 5 * magnitude;
    else niceStep = 10 * magnitude;

    const result = [];
    for (let v = 0; v <= max + niceStep; v += niceStep) {
      result.push(Math.round(v * 100) / 100);
      if (result.length >= ticks + 1) break;
    }
    return result;
  }

  destroy() {
    window.removeEventListener('resize', this._resizeHandler);
    if (this._resizeTimeout) clearTimeout(this._resizeTimeout);
  }
}

// Export for use in app.js
window.ChartManager = ChartManager;
window.HistoryChart = HistoryChart;
window.CHART_DATA_RETENTION_POINTS = CHART_DATA_RETENTION_POINTS;
