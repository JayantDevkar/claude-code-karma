/**
 * Dashboard Configuration
 * Shared constants and configurable values for the dashboard
 */

/**
 * Default threshold in milliseconds for considering a session as "running"
 * Sessions with no activity within this threshold are marked as completed
 *
 * Can be overridden via KARMA_RUNNING_THRESHOLD_MS environment variable
 */
export const RUNNING_THRESHOLD_MS = parseInt(
  process.env.KARMA_RUNNING_THRESHOLD_MS || '30000',
  10
);

/**
 * Dashboard configuration interface
 */
export interface DashboardConfig {
  /** Port to run the dashboard server on */
  port: number;
  /** Whether to open browser on startup */
  openBrowser: boolean;
  /** Session running threshold in ms */
  runningThresholdMs: number;
}

/**
 * Get dashboard configuration with defaults
 */
export function getDashboardConfig(overrides?: Partial<DashboardConfig>): DashboardConfig {
  return {
    port: 3333,
    openBrowser: true,
    runningThresholdMs: RUNNING_THRESHOLD_MS,
    ...overrides,
  };
}
