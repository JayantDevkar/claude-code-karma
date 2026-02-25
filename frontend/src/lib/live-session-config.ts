/**
 * Shared configuration for live session status display
 * Used by LiveSessionsTerminal and SessionCard components
 */

import type { LiveSessionStatus } from './api-types';

export interface StatusConfig {
	/** Primary color for status indicator and text */
	color: string;
	/** Display label for the status */
	label: string;
	/** Whether the status indicator should pulse/animate */
	pulse: boolean;
	/** Subtle background tint for card (uses CSS variable) */
	bgTint: string;
}

/**
 * Status configuration for all live session states
 */
export const statusConfig: Record<LiveSessionStatus, StatusConfig> = {
	starting: {
		color: 'var(--nav-purple)',
		label: 'starting',
		pulse: true,
		bgTint: 'var(--status-starting-bg)'
	},
	active: {
		color: 'var(--success)',
		label: 'active',
		pulse: true,
		bgTint: 'var(--status-active-bg)'
	},
	idle: {
		color: 'var(--warning)',
		label: 'idle',
		pulse: false,
		bgTint: 'var(--status-idle-bg)'
	},
	waiting: {
		color: 'var(--info)',
		label: 'waiting',
		pulse: false,
		bgTint: 'var(--status-waiting-bg)'
	},
	stopped: {
		color: 'var(--text-muted)',
		label: 'stopped',
		pulse: false,
		bgTint: 'var(--status-stopped-bg)'
	},
	ended: {
		color: 'var(--text-faint)',
		label: 'ended',
		pulse: false,
		bgTint: 'var(--status-ended-bg)'
	},
	stale: {
		color: 'var(--error)',
		label: 'stale',
		pulse: false,
		bgTint: 'var(--status-stale-bg)'
	}
};

/** 45 minutes in milliseconds - stop showing ended status after this */
export const ENDED_STATUS_TIMEOUT_MS = 45 * 60 * 1000;

/**
 * Check if ended status should still be displayed
 * Returns false if session ended more than 45 minutes ago
 */
export function shouldShowEndedStatus(updatedAt: string): boolean {
	const endedTime = new Date(updatedAt).getTime();
	const now = Date.now();
	return now - endedTime < ENDED_STATUS_TIMEOUT_MS;
}
