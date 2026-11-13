/**
 * Shared configuration for live session status display
 * Used by LiveSessionsTerminal and SessionCard components
 */

import type { LiveSessionStatus, LiveSessionSummary, StopError } from './api-types';

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
		pulse: false,
		bgTint: 'var(--status-starting-bg)'
	},
	active: {
		color: 'var(--success)',
		label: 'active',
		pulse: false,
		bgTint: 'var(--status-active-bg)'
	},
	idle: {
		color: 'var(--warning)',
		label: 'idle',
		pulse: false,
		bgTint: 'var(--status-idle-bg)'
	},
	// Pulse means "blocked on you" everywhere — a dot blinking for merely-busy trains you to ignore it.
	waiting: {
		color: 'var(--info)',
		label: 'waiting',
		pulse: true,
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
	},
	// No pulse: a usage limit usually can't be acted on until it resets.
	interrupted: {
		color: 'var(--nav-orange)',
		label: 'interrupted',
		pulse: false,
		bgTint: 'var(--status-interrupted-bg)'
	}
};

/** One-line reason a live session or subagent stopped on an API error or limit. */
export function stopErrorReason(err: StopError | null | undefined): string | null {
	if (!err) return null;
	if (err.message) return err.message;
	return err.kind === 'limit' ? 'Stopped by usage limit' : 'Stopped by API error';
}

/** Status dot tooltip: the reason when interrupted, else the status label. */
export function liveStatusTitle(session: LiveSessionSummary): string {
	if (session.status === 'interrupted') {
		return stopErrorReason(session.stop_error) ?? statusConfig.interrupted.label;
	}
	return statusConfig[session.status].label;
}

/** Tooltip text: error code plus details. */
export function stopErrorTooltip(err: StopError | null | undefined): string | undefined {
	if (!err) return undefined;
	return err.details ? `${err.code}: ${err.details}` : err.code;
}

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
