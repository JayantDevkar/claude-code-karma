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

// Export for use in app.js
window.ChartManager = ChartManager;
window.CHART_DATA_RETENTION_POINTS = CHART_DATA_RETENTION_POINTS;
