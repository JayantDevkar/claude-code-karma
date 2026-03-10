/**
 * Shared utility functions for Claude Code Karma
 */

import type {
	AnalyticsFilterPeriod,
	AnalyticsFilterOption,
	SubagentState,
	SubagentSummary,
	McpSessionSummary,
	SessionSummary,
	SessionWithContext
} from './api-types';
import { marked } from 'marked';
import DOMPurify from 'isomorphic-dompurify';

// ============================================
// Duration Formatting
// ============================================

/**
 * Format seconds into human-readable duration (e.g., "2h 15m", "45m 30s")
 */
export function formatDuration(seconds?: number | null): string {
	if (seconds == null || seconds <= 0) return '--';

	const hours = Math.floor(seconds / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);
	const secs = Math.floor(seconds % 60);

	if (hours > 0) {
		return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
	}
	if (minutes > 0) {
		return secs > 0 && minutes < 10 ? `${minutes}m ${secs}s` : `${minutes}m`;
	}
	return `${secs}s`;
}

/**
 * Format seconds into compact duration (e.g., "2h", "45m", "30s")
 */
export function formatDurationCompact(seconds?: number | null): string {
	if (seconds == null || seconds <= 0) return '--';

	const hours = Math.floor(seconds / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);
	const secs = Math.floor(seconds % 60);

	if (hours > 0) return `${hours}h`;
	if (minutes > 0) return `${minutes}m`;
	return `${secs}s`;
}

// ============================================
// Token Formatting
// ============================================

/**
 * Format token count with appropriate suffix (K, M)
 */
export function formatTokens(tokens?: number | null): string {
	if (tokens == null || tokens <= 0) return '--';

	if (tokens >= 1_000_000) {
		return `${(tokens / 1_000_000).toFixed(1)}M`;
	}
	if (tokens >= 1_000) {
		return `${(tokens / 1_000).toFixed(1)}K`;
	}
	return tokens.toLocaleString();
}

/**
 * Format token count with full number
 */
export function formatTokensFull(tokens?: number | null): string {
	if (tokens == null || tokens <= 0) return '--';
	return tokens.toLocaleString();
}

// ============================================
// Cost Formatting
// ============================================

/**
 * Format cost in USD
 */
export function formatCost(cost?: number | null): string {
	if (cost == null || cost <= 0) return '--';

	if (cost < 0.01) {
		return `$${cost.toFixed(4)}`;
	}
	if (cost < 1) {
		return `$${cost.toFixed(3)}`;
	}
	return `$${cost.toFixed(2)}`;
}

// ============================================
// Date/Time Formatting
// ============================================

/**
 * Format ISO timestamp to human-readable date
 */
export function formatDate(timestamp: string): string {
	const date = new Date(timestamp);
	return date.toLocaleString('en-US', {
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit',
		hour12: true
	});
}

/**
 * Format ISO timestamp to full date with year
 */
export function formatDateFull(timestamp: string): string {
	const date = new Date(timestamp);
	return date.toLocaleString('en-US', {
		month: 'short',
		day: 'numeric',
		year: 'numeric',
		hour: 'numeric',
		minute: '2-digit',
		second: '2-digit',
		hour12: true
	});
}

/**
 * Format ISO timestamp to date with timezone
 */
export function formatDateWithTimezone(timestamp: string): string {
	const date = new Date(timestamp);
	return date.toLocaleString('en-US', {
		month: 'short',
		day: 'numeric',
		year: 'numeric',
		hour: 'numeric',
		minute: '2-digit',
		hour12: true,
		timeZoneName: 'short'
	});
}

/**
 * Format relative time (e.g., "2 hours ago", "5 minutes ago")
 */
export function formatRelativeTime(timestamp: string): string {
	const date = new Date(timestamp);
	const now = new Date();
	const diffMs = now.getTime() - date.getTime();
	const diffMins = Math.floor(diffMs / 60000);
	const diffHours = Math.floor(diffMins / 60);
	const diffDays = Math.floor(diffHours / 24);

	if (diffMins < 1) return 'just now';
	if (diffMins < 60) return `${diffMins}m ago`;
	if (diffHours < 24) return `${diffHours}h ago`;
	if (diffDays < 7) return `${diffDays}d ago`;

	return formatDate(timestamp);
}

/**
 * Format elapsed time from session start (e.g., "+0:15", "+2:30:45")
 */
export function formatElapsedTime(timestamp: string, sessionStartTime: string): string {
	const eventTime = new Date(timestamp).getTime();
	const startTime = new Date(sessionStartTime).getTime();
	const elapsedMs = eventTime - startTime;

	if (elapsedMs < 0) return '+0:00';

	const totalSeconds = Math.floor(elapsedMs / 1000);
	const hours = Math.floor(totalSeconds / 3600);
	const minutes = Math.floor((totalSeconds % 3600) / 60);
	const seconds = totalSeconds % 60;

	if (hours > 0) {
		return `+${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
	}
	return `+${minutes}:${seconds.toString().padStart(2, '0')}`;
}

/**
 * Format time only (e.g., "10:30 AM")
 */
export function formatTime(timestamp: string): string {
	const date = new Date(timestamp);
	return date.toLocaleTimeString('en-US', {
		hour: 'numeric',
		minute: '2-digit',
		second: '2-digit',
		hour12: true
	});
}

// ============================================
// String Utilities
// ============================================

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, maxLength: number): string {
	if (text.length <= maxLength) return text;
	return text.slice(0, maxLength - 3) + '...';
}

/**
 * Format file size in human-readable format (e.g., "1.2 KB", "3.4 MB")
 */
export function formatFileSize(bytes: number): string {
	if (bytes === 0) return '0 B';
	const k = 1024;
	const sizes = ['B', 'KB', 'MB', 'GB'];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/**
 * Format character count with appropriate suffix (K, M)
 */
export function formatCharCount(count: number): string {
	if (count >= 1_000_000) {
		return `${(count / 1_000_000).toFixed(1)}M`;
	}
	if (count >= 1_000) {
		return `${(count / 1_000).toFixed(1)}K`;
	}
	return count.toLocaleString();
}

/**
 * Trim project path prefix for cleaner display
 * @deprecated Use formatDisplayPath instead for better UX with home directory shortening
 */
export function trimProjectPath(filePath: string, projectPath?: string | null): string {
	if (!projectPath) return filePath;

	// Normalize paths
	const normalizedFile = filePath.replace(/\\/g, '/');
	const normalizedProject = projectPath.replace(/\\/g, '/').replace(/\/$/, '');

	if (normalizedFile.startsWith(normalizedProject)) {
		const relativePath = normalizedFile.slice(normalizedProject.length);
		return relativePath.startsWith('/') ? relativePath.slice(1) : relativePath;
	}

	return filePath;
}

/**
 * Extract home directory path from a file path.
 * Handles: /Users/username/..., /home/username/..., C:\Users\username\...
 */
function inferHomePath(path: string): string | null {
	const normalized = path.replace(/\\/g, '/');

	// macOS: /Users/username
	const macMatch = normalized.match(/^(\/Users\/[^/]+)/);
	if (macMatch) return macMatch[1];

	// Linux: /home/username
	const linuxMatch = normalized.match(/^(\/home\/[^/]+)/);
	if (linuxMatch) return linuxMatch[1];

	// Windows: C:/Users/username
	const winMatch = normalized.match(/^([A-Za-z]:\/Users\/[^/]+)/i);
	if (winMatch) return winMatch[1];

	return null;
}

/**
 * Format file path for display with smart trimming.
 * Priority: project-relative > home-relative (~) > absolute
 *
 * Examples:
 * - /Users/jay/project/src/file.ts with projectPath=/Users/jay/project → src/file.ts
 * - /Users/jay/.config/settings.json with projectPath=/Users/jay/project → ~/.config/settings.json
 * - /etc/hosts → /etc/hosts (unchanged)
 */
export function formatDisplayPath(filePath: string, projectPath?: string | null): string {
	if (!filePath) return '';

	const normalizedFile = filePath.replace(/\\/g, '/');

	// 1. Try project-relative first (most specific)
	if (projectPath) {
		const normalizedProject = projectPath.replace(/\\/g, '/').replace(/\/$/, '');
		if (normalizedFile.startsWith(normalizedProject + '/')) {
			return normalizedFile.slice(normalizedProject.length + 1);
		}
		// Handle exact match (path IS the project path)
		if (normalizedFile === normalizedProject) {
			return '.';
		}
	}

	// 2. Infer home directory and replace with ~
	const homePath = inferHomePath(filePath);
	if (homePath && normalizedFile.startsWith(homePath + '/')) {
		return '~' + normalizedFile.slice(homePath.length);
	}
	// Handle exact match (path IS the home directory)
	if (homePath && normalizedFile === homePath) {
		return '~';
	}

	return filePath;
}

/**
 * Get project name from path
 */
export function getProjectName(path: string): string {
	return path.split('/').pop() || path;
}

/**
 * Decode an encoded project path back to a readable path.
 * Note: The encoding is lossy (can't distinguish path separators from literal hyphens),
 * so this is a best-effort decode using common path patterns.
 */
export function decodeProjectPath(encodedName: string): string {
	// Common path prefixes to match (order matters - more specific first)
	const patterns = [
		/^-Users-[^-]+-Documents-GitHub-/,
		/^-Users-[^-]+-Documents-/,
		/^-Users-[^-]+-Desktop-/,
		/^-Users-[^-]+-Projects-/,
		/^-Users-[^-]+-Code-/,
		/^-Users-[^-]+-/,
		/^-home-[^-]+-Documents-/,
		/^-home-[^-]+-Projects-/,
		/^-home-[^-]+-/
	];

	for (const pattern of patterns) {
		const match = encodedName.match(pattern);
		if (match) {
			// Return the remainder after the prefix (this is the project path with hyphens preserved)
			const projectPart = encodedName.slice(match[0].length);
			// Decode the prefix normally for the full path
			const prefixPath = match[0].replace(/^-/, '/').replace(/-/g, '/');
			return prefixPath + projectPart;
		}
	}

	// Fallback: simple decode (replace - with /)
	return encodedName.replace(/^-/, '/').replace(/-/g, '/');
}

// ============================================================================
// Session Display Helpers (shared across all session card components)
// ============================================================================

/**
 * Get session display name with consistent hierarchy: title → slug → uuid prefix.
 */
export function getSessionDisplayName(
	sessionTitles?: string[],
	slug?: string,
	uuid?: string,
	chainTitle?: string
): string {
	return sessionTitles?.[0] || chainTitle || slug || uuid?.slice(0, 8) || 'Session';
}

/**
 * Check if a session has a real title (not slug/uuid fallback).
 */
export function sessionHasTitle(sessionTitles?: string[], chainTitle?: string): boolean {
	return !!sessionTitles?.[0] || !!chainTitle;
}

/**
 * Get display prompt with consistent fallback logic.
 * Hierarchy: initial_prompt (if not "No prompt") → session title → null.
 */
export function getSessionDisplayPrompt(
	initialPrompt?: string,
	sessionTitles?: string[]
): string | null {
	if (initialPrompt && initialPrompt !== 'No prompt') return initialPrompt;
	return sessionTitles?.[0] || null;
}

/**
 * Get project name from an encoded project name.
 * Uses pattern matching to preserve hyphens in the actual project folder name.
 */
export function getProjectNameFromEncoded(encodedName: string): string {
	// Strip the platform prefix: -Users-{username}- or -home-{username}-
	// Returns everything after the user's home directory
	// This is a last-resort fallback — prefer API-provided display_name
	const macosMatch = encodedName.match(/^-Users-[^-]+-(.+)$/);
	if (macosMatch) return macosMatch[1];

	const linuxMatch = encodedName.match(/^-home-[^-]+-(.+)$/);
	if (linuxMatch) return linuxMatch[1];

	// Fallback: return as-is (strip leading dash if present)
	return encodedName.replace(/^-/, '') || encodedName;
}

/**
 * Get short model display name
 */
export function getModelDisplayName(modelName: string): string {
	if (modelName.includes('sonnet-4-5') || modelName.includes('sonnet-4.5')) return 'Sonnet 4.5';
	if (modelName.includes('opus-4-5') || modelName.includes('opus-4.5')) return 'Opus 4.5';
	if (modelName.includes('sonnet')) return 'Sonnet';
	if (modelName.includes('opus')) return 'Opus';
	if (modelName.includes('haiku')) return 'Haiku';
	return modelName.replace('claude-', '').replace(/-/g, ' ');
}

/**
 * Get compact model display name
 */
export function getModelDisplayNameCompact(modelName: string): string {
	if (modelName.includes('sonnet-4-5') || modelName.includes('sonnet-4.5')) return 'S4.5';
	if (modelName.includes('opus-4-5') || modelName.includes('opus-4.5')) return 'O4.5';
	if (modelName.includes('sonnet')) return 'Sonnet';
	if (modelName.includes('opus')) return 'Opus';
	if (modelName.includes('haiku')) return 'Haiku';
	return modelName.slice(0, 8);
}

/**
 * Get single-letter model badge label for compact card badges
 */
export function getModelBadgeLabel(modelName: string): string {
	if (modelName.includes('opus-4-6') || modelName.includes('opus-4.6')) return 'O 4.6';
	if (modelName.includes('opus-4-5') || modelName.includes('opus-4.5')) return 'O 4.5';
	if (modelName.includes('opus')) return 'O';
	if (modelName.includes('sonnet-4-6') || modelName.includes('sonnet-4.6')) return 'S 4.6';
	if (modelName.includes('sonnet-4-5') || modelName.includes('sonnet-4.5')) return 'S 4.5';
	if (modelName.includes('sonnet')) return 'S';
	if (modelName.includes('haiku')) return 'Haiku';
	return 'non-claude';
}

// ============================================
// Utility Helpers
// ============================================

/**
 * Combine class names conditionally
 */
export function cn(...classes: (string | undefined | null | false)[]): string {
	return classes.filter(Boolean).join(' ');
}

/**
 * Debounce function
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
	fn: T,
	delay: number
): (...args: Parameters<T>) => void {
	let timeoutId: ReturnType<typeof setTimeout>;
	return (...args: Parameters<T>) => {
		clearTimeout(timeoutId);
		timeoutId = setTimeout(() => fn(...args), delay);
	};
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
	try {
		await navigator.clipboard.writeText(text);
		return true;
	} catch {
		return false;
	}
}

/**
 * Generate a random ID
 */
export function generateId(): string {
	return Math.random().toString(36).substring(2, 11);
}

// ============================================
// Analytics Filter Utilities
// ============================================

// Time constants
export const HOUR_MS = 60 * 60 * 1000;
export const DAY_MS = 24 * HOUR_MS;

// Filter options array
export const analyticsFilterOptions: AnalyticsFilterOption[] = [
	{ id: 'all', label: 'All Time', group: null },
	{ id: '6h', label: 'Last 6 hours', group: 'Hours' },
	{ id: '12h', label: 'Last 12 hours', group: 'Hours' },
	{ id: '24h', label: 'Last 24 hours', group: 'Hours' },
	{ id: '48h', label: 'Last 48 hours', group: 'Hours' },
	{ id: 'this_week', label: 'This week', group: 'Weeks' },
	{ id: 'last_week', label: 'Last week', group: 'Weeks' },
	{ id: '2_weeks_ago', label: '2 weeks ago', group: 'Weeks' },
	{ id: 'this_month', label: 'This month', group: 'Months' },
	{ id: 'last_month', label: 'Last month', group: 'Months' }
];

/**
 * Get label from filter id
 */
export function getAnalyticsFilterLabel(id: AnalyticsFilterPeriod): string {
	return analyticsFilterOptions.find((opt) => opt.id === id)?.label ?? 'All Time';
}

/**
 * Check if filter is hour-based (short period)
 */
export function isHourBasedFilter(id: AnalyticsFilterPeriod): boolean {
	return ['6h', '12h', '24h', '48h'].includes(id);
}

/**
 * Get Monday 00:00:00 of the week containing the given date
 */
export function getMondayOfWeek(date: Date): Date {
	const d = new Date(date);
	const dayOfWeek = d.getDay(); // 0 = Sunday, 1 = Monday, ...
	const daysFromMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
	d.setDate(d.getDate() - daysFromMonday);
	d.setHours(0, 0, 0, 0);
	return d;
}

/**
 * Get Sunday 23:59:59.999 of the week containing the given date
 */
export function getSundayOfWeek(date: Date): Date {
	const monday = getMondayOfWeek(date);
	const sunday = new Date(monday.getTime() + 7 * DAY_MS - 1);
	return sunday;
}

/**
 * Calculate timestamp range for a given filter.
 * Returns Unix milliseconds for start and end, or null for "all time".
 */
export function getTimestampRangeForFilter(
	filter: AnalyticsFilterPeriod
): { start: number; end: number } | null {
	const now = Date.now();

	if (filter === 'all') {
		return null;
	}

	// Hour-based filters - simple arithmetic
	if (filter === '6h' || filter === '12h' || filter === '24h' || filter === '48h') {
		const hours = parseInt(filter);
		return {
			start: now - hours * HOUR_MS,
			end: now
		};
	}

	// Week-based filters
	const today = new Date();
	const thisMonday = getMondayOfWeek(today);

	if (filter === 'this_week') {
		return {
			start: thisMonday.getTime(),
			end: now
		};
	}

	if (filter === 'last_week') {
		const lastSunday = new Date(thisMonday.getTime() - 1); // 23:59:59.999 of prev Sunday
		const lastMonday = getMondayOfWeek(lastSunday);
		return {
			start: lastMonday.getTime(),
			end: lastSunday.getTime()
		};
	}

	if (filter === '2_weeks_ago') {
		const lastMonday = new Date(thisMonday.getTime() - 7 * DAY_MS);
		const twoWeeksAgoSunday = new Date(lastMonday.getTime() - 1);
		const twoWeeksAgoMonday = getMondayOfWeek(twoWeeksAgoSunday);
		return {
			start: twoWeeksAgoMonday.getTime(),
			end: twoWeeksAgoSunday.getTime()
		};
	}

	// Month-based filters
	if (filter === 'this_month') {
		const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1, 0, 0, 0, 0);
		return {
			start: firstOfMonth.getTime(),
			end: now
		};
	}

	if (filter === 'last_month') {
		const firstOfLastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1, 0, 0, 0, 0);
		const lastMsOfLastMonth =
			new Date(today.getFullYear(), today.getMonth(), 1, 0, 0, 0, 0).getTime() - 1;
		return {
			start: firstOfLastMonth.getTime(),
			end: lastMsOfLastMonth
		};
	}

	return null;
}

// ============================================
// Model Color Utilities
// ============================================

export type ModelColor = 'opus' | 'sonnet' | 'haiku' | 'default';

/**
 * Detect model color from model names array
 */
export function getModelColor(models: string[]): ModelColor {
	if (models.length === 0) return 'default';
	const primary = models[0];
	if (primary.includes('opus')) return 'opus';
	if (primary.includes('sonnet')) return 'sonnet';
	if (primary.includes('haiku')) return 'haiku';
	return 'default';
}

/**
 * Model color configuration for styling
 */
export const modelColorConfig: Record<
	ModelColor,
	{ border: string; badge: string; sparkle: string; iconBg: string }
> = {
	opus: {
		border: 'var(--model-opus)',
		badge: 'bg-[var(--model-opus-subtle)] border-[var(--model-opus)]/20',
		sparkle: 'text-[var(--model-opus)]',
		iconBg: 'var(--model-opus-subtle)'
	},
	sonnet: {
		border: 'var(--model-sonnet)',
		badge: 'bg-[var(--model-sonnet-subtle)] border-[var(--model-sonnet)]/20',
		sparkle: 'text-[var(--model-sonnet)]',
		iconBg: 'var(--model-sonnet-subtle)'
	},
	haiku: {
		border: 'var(--model-haiku)',
		badge: 'bg-[var(--model-haiku-subtle)] border-[var(--model-haiku)]/20',
		sparkle: 'text-[var(--model-haiku)]',
		iconBg: 'var(--model-haiku-subtle)'
	},
	default: {
		border: 'var(--accent)',
		badge: 'bg-[var(--bg-muted)] border-[var(--border)]',
		sparkle: 'text-[var(--accent)]',
		iconBg: 'var(--accent-subtle)'
	}
};

// ============================================
// Team Member Color Utilities (Remote Sessions)
// ============================================

/** Color palette for team members, avoiding model colors (purple/blue/green) */
const TEAM_MEMBER_PALETTE = [
	'coral',
	'rose',
	'amber',
	'cyan',
	'pink',
	'lime',
	'indigo',
	'teal',
	'sky',
	'violet',
	'emerald',
	'orange',
	'fuchsia',
	'slate',
	'gold',
	'ruby'
] as const;

type TeamColor = (typeof TEAM_MEMBER_PALETTE)[number];

export interface TeamMemberColorConfig {
	border: string;
	badge: string;
	text: string;
	bg: string;
}

/** Deterministic hash to palette index for a userId */
function teamMemberPaletteIndex(userId: string): number {
	let hash = 0;
	for (let i = 0; i < userId.length; i++) {
		hash = (hash << 5) - hash + userId.charCodeAt(i);
		hash |= 0;
	}
	return Math.abs(hash) % TEAM_MEMBER_PALETTE.length;
}

/**
 * Deterministic hash-based color assignment for team members.
 * Same userId always gets the same color.
 */
export function getTeamMemberColor(userId: string): TeamMemberColorConfig {
	const color: TeamColor = TEAM_MEMBER_PALETTE[teamMemberPaletteIndex(userId)];
	return {
		border: `var(--team-${color})`,
		badge: `bg-[var(--team-${color}-subtle)] border-[var(--team-${color})]/20`,
		text: `text-[var(--team-${color})]`,
		bg: `var(--team-${color}-subtle)`
	};
}

// ============================================
// Chart Hex Color Utilities (for Chart.js canvas)
// ============================================

/** Hex colors matching TEAM_MEMBER_PALETTE CSS var names — for Chart.js canvas rendering */
const TEAM_HEX_COLORS: Record<string, string> = {
	coral: '#f97066',
	rose: '#f43f5e',
	amber: '#f59e0b',
	cyan: '#06b6d4',
	pink: '#ec4899',
	lime: '#84cc16',
	indigo: '#6366f1',
	teal: '#14b8a6',
	sky: '#0ea5e9',
	violet: '#7c3aed',
	emerald: '#10b981',
	orange: '#f97316',
	fuchsia: '#c026d3',
	slate: '#64748b',
	gold: '#eab308',
	ruby: '#be123c'
};

/** Accent purple used for local user in charts */
export const LOCAL_USER_HEX = '#7c3aed';

/**
 * Get hex color for a team member (for Chart.js).
 * Uses same hash as getTeamMemberColor() for consistency.
 */
export function getTeamMemberHexColor(userId: string): string {
	return TEAM_HEX_COLORS[TEAM_MEMBER_PALETTE[teamMemberPaletteIndex(userId)]];
}

/** Get hex color for a user_id. '_local' → accent purple, others → team color */
export function getUserChartColor(userId: string): string {
	return userId === '_local' ? LOCAL_USER_HEX : getTeamMemberHexColor(userId);
}

/** Get display label for a user in charts */
export function getUserChartLabel(
	userId: string,
	userNames?: Record<string, string>
): string {
	if (userId === '_local') return 'You';
	const name = userNames?.[userId];
	if (name) return name;
	return userId.length > 16 ? userId.slice(0, 14) + '\u2026' : userId;
}

/**
 * Check if a session is from a remote machine
 */
export function isRemoteSession(session: { remote_user_id?: string }): boolean {
	return !!session.remote_user_id;
}

// ============================================
// Subagent Color Utilities
// ============================================

/** Known subagent types with dedicated colors */
const KNOWN_SUBAGENT_TYPES = [
	'Explore',
	'Plan',
	'Bash',
	'Claude Tax',
	// System agents (auto-spawned by Claude Code)
	'acompact',
	'aprompt_suggestion'
];

/** Display names for subagent types (maps raw API values to user-friendly names) */
const SUBAGENT_TYPE_DISPLAY_NAMES: Record<string, string> = {
	acompact: 'Compaction Agent',
	aprompt_suggestion: 'Prompt Suggestion'
};

/** System agent prefixes that should be stripped from agent IDs for display */
const SYSTEM_AGENT_PREFIXES = ['aprompt_suggestion-', 'acompact-'];

/**
 * Get user-friendly display name for a subagent type.
 * Returns the original type if no display name mapping exists.
 */
export function getSubagentTypeDisplayName(type: string | null | undefined): string {
	if (!type) return 'Other';
	return SUBAGENT_TYPE_DISPLAY_NAMES[type] ?? type;
}

/**
 * Clean an agent ID for display by removing system agent prefixes.
 * E.g., "aprompt_suggestion-7796cd" → "7796cd"
 */
export function cleanAgentIdForDisplay(agentId: string): string {
	for (const prefix of SYSTEM_AGENT_PREFIXES) {
		if (agentId.startsWith(prefix)) {
			return agentId.slice(prefix.length);
		}
	}
	return agentId;
}

/**
 * Check if an agent ID belongs to a system agent (has known system prefix).
 */
export function isSystemAgent(agentId: string): boolean {
	return SYSTEM_AGENT_PREFIXES.some((prefix) => agentId.startsWith(prefix));
}

/**
 * Infer the subagent type from an agent ID by checking known prefixes.
 * Returns the inferred type or null if no pattern matches.
 * This is useful when the API doesn't return subagent_type for system agents.
 */
export function inferSubagentTypeFromId(agentId: string): string | null {
	if (agentId.startsWith('acompact-')) return 'acompact';
	if (agentId.startsWith('aprompt_suggestion-')) return 'aprompt_suggestion';
	return null;
}

/**
 * Get the effective subagent type, falling back to inferring from agent ID.
 * Use this when you have both subagent_type and agent_id available.
 */
export function getEffectiveSubagentType(
	subagentType: string | null | undefined,
	agentId: string
): string | null {
	if (subagentType) return subagentType;
	return inferSubagentTypeFromId(agentId);
}

/**
 * Simple string hash function for deterministic color assignment.
 * Uses djb2 algorithm - fast and provides good distribution.
 */
function hashString(str: string): number {
	let hash = 5381;
	for (let i = 0; i < str.length; i++) {
		hash = (hash * 33) ^ str.charCodeAt(i);
	}
	return Math.abs(hash);
}

/**
 * Check if a subagent type has a dedicated color.
 */
export function isKnownSubagentType(type: string | null | undefined): boolean {
	return type != null && KNOWN_SUBAGENT_TYPES.includes(type);
}

/**
 * Compute an OKLCH hue for a plugin name.
 * Uses golden angle distribution for maximum visual separation between plugins.
 */
function pluginHue(name: string): number {
	// Strip @registry suffix so "playwright" and "playwright@claude-plugins-official"
	// produce the same hue, ensuring color consistency across pages
	const baseName = name.includes('@') ? name.split('@')[0] : name;
	return (hashString(baseName) * 137.508) % 360;
}

/**
 * Get consistent color vars for a plugin by name.
 * Uses OKLCH color space — JS computes only the hue (per-plugin),
 * CSS variables control lightness/chroma (theme-aware).
 *
 * @param pluginName - The plugin name (e.g., "oh-my-claudecode", "feature-dev")
 * @returns Color CSS value strings (oklch with theme-aware L/C from CSS vars)
 */
export function getPluginColorVars(pluginName: string): {
	color: string;
	subtle: string;
} {
	const hue = pluginHue(pluginName);
	return {
		color: `oklch(var(--plugin-l) var(--plugin-c) ${hue.toFixed(1)})`,
		subtle: `oklch(var(--plugin-l-subtle) var(--plugin-c-subtle) ${hue.toFixed(1)})`
	};
}

/**
 * Convert OKLCH to sRGB hex.
 * Uses the standard OKLCH → OKLab → LMS → linear sRGB → sRGB pipeline.
 */
function oklchToHex(L: number, C: number, H: number): string {
	const hRad = (H * Math.PI) / 180;
	const a = C * Math.cos(hRad);
	const b = C * Math.sin(hRad);

	// OKLab → LMS (cube root domain)
	const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
	const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
	const s_ = L - 0.0894841775 * a - 1.291485548 * b;

	const l = l_ * l_ * l_;
	const m = m_ * m_ * m_;
	const s = s_ * s_ * s_;

	// LMS → linear sRGB
	const rl = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
	const gl = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
	const bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;

	// Linear sRGB → sRGB gamma
	const gamma = (x: number) =>
		x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055;

	const toHex = (x: number) =>
		Math.round(Math.min(1, Math.max(0, gamma(x))) * 255)
			.toString(16)
			.padStart(2, '0');

	return `#${toHex(rl)}${toHex(gl)}${toHex(bl)}`;
}

/**
 * Get a hex color for a plugin, suitable for canvas/Chart.js rendering.
 * Uses the same OKLCH color space as getPluginColorVars so chart colors
 * visually match the page accent. Uses L=0.65, C=0.14 as a middle ground
 * that works well in both light and dark themes.
 */
export function getPluginChartHex(pluginName: string): string {
	const hue = pluginHue(pluginName);
	return oklchToHex(0.65, 0.14, hue);
}

/**
 * Get a hex color for a subagent type, suitable for Chart.js canvas rendering.
 * Uses middle-ground hex values that work in both light and dark themes.
 */
const SUBAGENT_CHART_HEX: Record<string, string> = {
	Explore: '#0ea5e9',
	Plan: '#eab308',
	Bash: '#22c55e',
	'Claude Tax': '#ea580c',
	acompact: '#64748b',
	aprompt_suggestion: '#818cf8'
};

export function getSubagentChartHex(type: string): string {
	if (!type) return '#a78bfa'; // default violet
	if (SUBAGENT_CHART_HEX[type]) return SUBAGENT_CHART_HEX[type];
	// Plugin types (contains ':') — use plugin OKLCH hashing
	const colonIndex = type.indexOf(':');
	if (colonIndex !== -1) return getPluginChartHex(type.slice(0, colonIndex));
	return '#a78bfa'; // fallback default
}

/**
 * Get a hex color for a skill name, suitable for Chart.js canvas rendering.
 * Plugin skills get OKLCH-hashed colors; file-based skills get accent.
 */
export function getSkillChartHex(skillName: string): string {
	if (!skillName) return '#7c3aed'; // accent
	const colonIndex = skillName.indexOf(':');
	if (colonIndex !== -1) return getPluginChartHex(skillName.slice(0, colonIndex));
	return '#7c3aed'; // accent for file-based skills
}

/**
 * Scope-aware color for entity categories.
 */
export type EntityScope = 'builtin' | 'system' | 'plugin' | 'project' | 'user';

export function getScopeColorVars(scope: EntityScope): {
	color: string;
	subtle: string;
} {
	switch (scope) {
		case 'project':
			return { color: 'var(--scope-project)', subtle: 'var(--scope-project-subtle)' };
		case 'user':
			return { color: 'var(--scope-user)', subtle: 'var(--scope-user-subtle)' };
		default:
			return { color: 'var(--subagent-default)', subtle: 'var(--subagent-default-subtle)' };
	}
}

/**
 * Get color vars for a command based on its source and optional plugin.
 */
export function getCommandColorVars(
	source: string,
	plugin?: string | null
): { color: string; subtle: string } {
	if (source === 'plugin' && plugin) {
		return getPluginColorVars(plugin);
	}
	if (source === 'project') {
		return getScopeColorVars('project');
	}
	if (source === 'user') {
		return getScopeColorVars('user');
	}
	if (source === 'builtin') {
		return { color: 'var(--text-muted)', subtle: 'var(--bg-muted)' };
	}
	return { color: 'var(--accent)', subtle: 'var(--accent-subtle)' };
}

/**
 * Shared color vars for categories common to both commands and skills.
 * Ensures `bundled_skill`, `plugin_skill`, and `custom_skill` render
 * identically regardless of which page they appear on.
 */
function _getSharedCategoryColorVars(
	category: 'bundled_skill' | 'plugin_skill' | 'custom_skill'
): { color: string; subtle: string } {
	switch (category) {
		case 'bundled_skill':
			return { color: 'var(--nav-purple)', subtle: 'oklch(0.75 0.1 300 / 0.1)' };
		case 'plugin_skill':
			return { color: 'var(--nav-blue)', subtle: 'oklch(0.7 0.12 250 / 0.1)' };
		case 'custom_skill':
			return { color: 'var(--nav-teal)', subtle: 'oklch(0.75 0.1 180 / 0.1)' };
	}
}

/**
 * Get color vars for a command category (5-category classification).
 */
export function getCommandCategoryColorVars(category: string): { color: string; subtle: string } {
	switch (category) {
		case 'builtin_command':
			return { color: 'var(--text-muted)', subtle: 'var(--bg-muted)' };
		case 'bundled_skill':
		case 'plugin_skill':
		case 'custom_skill':
			return _getSharedCategoryColorVars(category);
		case 'plugin_command':
			return { color: 'var(--nav-blue)', subtle: 'oklch(0.7 0.12 250 / 0.1)' };
		case 'user_command':
			return { color: 'var(--accent)', subtle: 'var(--accent-subtle)' };
		default:
			return { color: 'var(--accent)', subtle: 'var(--accent-subtle)' };
	}
}

/**
 * Get a human-readable label for a command category.
 */
export function getCommandCategoryLabel(category: string): string {
	switch (category) {
		case 'builtin_command':
			return 'Built-in';
		case 'bundled_skill':
			return 'Bundled';
		case 'plugin_skill':
			return 'Plugin';
		case 'plugin_command':
			return 'Plugin Command';
		case 'custom_skill':
			return 'Custom';
		case 'user_command':
			return 'User';
		default:
			return category;
	}
}

/**
 * Get human-readable label for a skill category.
 */
export function getSkillCategoryLabel(category: string): string {
	switch (category) {
		case 'bundled_skill':
			return 'Bundled';
		case 'plugin_skill':
			return 'Plugin';
		case 'custom_skill':
			return 'Custom';
		case 'inherited_skill':
			return 'Inherited';
		default:
			return category;
	}
}

/**
 * Get color vars for a skill category (3-category classification).
 * Uses the shared helper for the 3 categories common with commands.
 */
export function getSkillCategoryColorVars(category: string): { color: string; subtle: string } {
	switch (category) {
		case 'bundled_skill':
		case 'plugin_skill':
		case 'custom_skill':
			return _getSharedCategoryColorVars(category);
		case 'inherited_skill':
			return { color: 'var(--nav-amber)', subtle: 'oklch(0.75 0.1 80 / 0.1)' };
		default:
			return { color: 'var(--text-muted)', subtle: 'var(--bg-muted)' };
	}
}

/**
 * Get a hex color for a command name (for Chart.js which can't use CSS vars).
 */
export function getCommandChartHex(name: string): string {
	let hash = 0;
	for (let i = 0; i < name.length; i++) {
		hash = name.charCodeAt(i) + ((hash << 5) - hash);
	}
	const h = ((hash % 360) + 360) % 360;
	return oklchToHex(0.7, 0.12, h);
}

/**
 * Get color vars for a hook source based on its type and name.
 * Global hooks get warm amber, plugin hooks use plugin colors, project hooks use scope colors.
 */
export function getHookSourceColorVars(
	sourceType: string,
	sourceName: string
): { color: string; subtle: string } {
	if (sourceType === 'plugin') return getPluginColorVars(sourceName);
	if (sourceType === 'project') return getScopeColorVars('project');
	return { color: 'var(--nav-amber)', subtle: 'var(--nav-amber-subtle)' };
}

/**
 * Get CSS variable names for a subagent type's colors.
 * For known types, returns their dedicated color vars.
 * For custom plugin types (with ":"), extracts plugin name for consistent coloring.
 */
export function getSubagentColorVars(type: string | null | undefined): {
	color: string;
	subtle: string;
} {
	if (!type) {
		return {
			color: 'var(--subagent-default)',
			subtle: 'var(--subagent-default-subtle)'
		};
	}

	// Known types get their dedicated colors
	switch (type) {
		case 'Explore':
			return { color: 'var(--subagent-explore)', subtle: 'var(--subagent-explore-subtle)' };
		case 'Plan':
			return { color: 'var(--subagent-plan)', subtle: 'var(--subagent-plan-subtle)' };
		case 'Bash':
			return { color: 'var(--subagent-bash)', subtle: 'var(--subagent-bash-subtle)' };
		case 'Claude Tax':
			return {
				color: 'var(--subagent-claude-tax)',
				subtle: 'var(--subagent-claude-tax-subtle)'
			};
		// System agents (auto-spawned by Claude Code for internal operations)
		case 'acompact':
			return { color: 'var(--subagent-acompact)', subtle: 'var(--subagent-acompact-subtle)' };
		case 'aprompt_suggestion':
			return {
				color: 'var(--subagent-prompt-suggestion)',
				subtle: 'var(--subagent-prompt-suggestion-subtle)'
			};
	}

	// For plugin types (e.g., "oh-my-claudecode:executor"), extract plugin prefix
	const colonIndex = type.indexOf(':');
	if (colonIndex !== -1) {
		const pluginName = type.slice(0, colonIndex);
		return getPluginColorVars(pluginName);
	}

	// Non-plugin custom types fall back to default
	return {
		color: 'var(--subagent-default)',
		subtle: 'var(--subagent-default-subtle)'
	};
}

/**
 * Get Tailwind-style class strings for a subagent type.
 * Uses CSS variable references for light/dark mode support.
 */
export function getSubagentColorClasses(type: string | null | undefined): {
	text: string;
	bg: string;
	border: string;
} {
	const vars = getSubagentColorVars(type);
	return {
		text: `text-[${vars.color}]`,
		bg: `bg-[${vars.subtle}]`,
		border: `border-l-[${vars.color}]`
	};
}

// ============================================
// Skill Color Utilities
// ============================================

/**
 * Get CSS variable names for a skill's colors.
 * Plugin skills get hash-based colors from the subagent palette (consistent with agents).
 * File-based skills get a dedicated accent color.
 */
export function getSkillColorVars(
	skillName: string | null | undefined,
	isPlugin: boolean,
	plugin?: string | null
): {
	color: string;
	subtle: string;
} {
	if (!skillName) {
		return {
			color: 'var(--accent)',
			subtle: 'var(--accent-subtle)'
		};
	}

	if (isPlugin && plugin) {
		// Plugin skills use unified plugin color system for consistency with agents
		return getPluginColorVars(plugin);
	}

	// File-based skills use the accent color
	return {
		color: 'var(--accent)',
		subtle: 'var(--accent-subtle)'
	};
}

// ============================================
// Usage Tier Utilities (shared by Skills, Agents, Tools)
// ============================================

export type UsageTier = 'low' | 'medium' | 'high' | 'very-high';

export interface TierConfig {
	bg: string;
	darkBg: string;
	iconColor: string;
	label: string;
}

/**
 * Determine usage tier based on count relative to max.
 */
export function getUsageTier(count: number, maxCount: number): UsageTier {
	const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
	if (pct >= 75) return 'very-high';
	if (pct >= 50) return 'high';
	if (pct >= 25) return 'medium';
	return 'low';
}

export const tierConfigs: Record<UsageTier, TierConfig> = {
	'very-high': {
		bg: 'rgba(251, 191, 36, 0.08)',
		darkBg: 'rgba(251, 191, 36, 0.12)',
		iconColor: '#f59e0b',
		label: 'Hot'
	},
	high: {
		bg: 'rgba(34, 197, 94, 0.08)',
		darkBg: 'rgba(34, 197, 94, 0.12)',
		iconColor: '#22c55e',
		label: 'Trending'
	},
	medium: {
		bg: 'rgba(59, 130, 246, 0.08)',
		darkBg: 'rgba(59, 130, 246, 0.12)',
		iconColor: '#3b82f6',
		label: 'Active'
	},
	low: {
		bg: 'rgba(156, 163, 175, 0.05)',
		darkBg: 'rgba(156, 163, 175, 0.08)',
		iconColor: '#9ca3af',
		label: 'Low'
	}
};

// ============================================
// Skill Name Utilities
// ============================================

/**
 * Clean skill name for display by removing plugin namespace prefixes.
 * Extracts the final segment after the last colon for namespaced skills.
 *
 * @param skillName - Full skill name (e.g., "oh-my-claudecode:autopilot")
 * @param isPlugin - Whether this is a plugin skill
 * @returns Cleaned name for display (e.g., "autopilot")
 *
 * @example
 * ```ts
 * cleanSkillName('oh-my-claudecode:autopilot', true) // 'autopilot'
 * cleanSkillName('plugin:feature-dev:code-explorer', true) // 'code-explorer'
 * cleanSkillName('everything-claude-code:tdd', true) // 'tdd'
 * cleanSkillName('my-custom-skill', false) // 'my-custom-skill'
 * ```
 */
export function cleanSkillName(skillName: string, isPlugin: boolean = false): string {
	if (!isPlugin) {
		return skillName;
	}

	// For plugin skills, extract the final segment after the last colon
	const colonIndex = skillName.lastIndexOf(':');
	if (colonIndex === -1) {
		return skillName;
	}

	return skillName.slice(colonIndex + 1);
}

/**
 * Extract plugin namespace from a skill name.
 *
 * @param skillName - Full skill name
 * @returns Plugin namespace or null
 *
 * @example
 * ```ts
 * getSkillPluginNamespace('oh-my-claudecode:autopilot') // 'oh-my-claudecode'
 * getSkillPluginNamespace('plugin:feature-dev:code-explorer') // 'plugin:feature-dev'
 * getSkillPluginNamespace('my-custom-skill') // null
 * ```
 */
export function getSkillPluginNamespace(skillName: string): string | null {
	const colonIndex = skillName.lastIndexOf(':');
	if (colonIndex === -1) {
		return null;
	}

	return skillName.slice(0, colonIndex);
}

/**
 * Get CSS variable names for a skill group header.
 * Uses plugin name for consistent hashing.
 */
export function getSkillGroupColorVars(groupKey: string): {
	color: string;
	subtle: string;
} {
	if (groupKey === 'file' || groupKey === 'other') {
		return {
			color: 'var(--accent)',
			subtle: 'var(--accent-subtle)'
		};
	}

	// Plugin groups: extract plugin name from "plugin:{name}" key and use unified color system
	const pluginName = groupKey.startsWith('plugin:') ? groupKey.slice(7) : groupKey;
	return getPluginColorVars(pluginName);
}

// ============================================
// Subagent Data Utilities
// ============================================

/**
 * Merge SubagentState (live hooks) with SubagentSummary (JSONL) data.
 * Returns enriched object with both real-time status and historical details.
 */
export function mergeSubagentData(
	summary: SubagentSummary,
	liveState?: SubagentState | null
): SubagentSummary & {
	status?: SubagentState['status'];
	started_at?: string;
	completed_at?: string | null;
	transcript_path?: string | null;
} {
	return {
		...summary,
		status: liveState?.status,
		started_at: liveState?.started_at,
		completed_at: liveState?.completed_at,
		transcript_path: liveState?.transcript_path
	};
}

/**
 * Calculate running duration in seconds from a start timestamp.
 * Returns duration from start to now (if running) or to completed_at.
 */
export function calculateSubagentDuration(
	started_at: string | undefined,
	completed_at?: string | null
): number | null {
	if (!started_at) return null;
	const start = new Date(started_at).getTime();
	const end = completed_at ? new Date(completed_at).getTime() : Date.now();
	return Math.floor((end - start) / 1000);
}

// ============================================
// Session Utilities
// ============================================

/**
 * Session identifier for matching (minimal interface)
 */
interface SessionIdentifier {
	uuid: string;
	slug?: string | null;
}

/**
 * Find a session by slug or UUID prefix.
 *
 * Matches in order of priority:
 * 1. Exact slug match (if session has a slug)
 * 2. UUID prefix match (first N characters)
 * 3. Exact UUID match
 *
 * @param sessions - Array of sessions to search
 * @param identifier - Slug or UUID prefix to match
 * @returns The matched session or undefined
 *
 * @example
 * ```ts
 * const session = findSessionByIdentifier(sessions, 'abc123');
 * if (session) {
 *   console.log(`Found session: ${session.uuid}`);
 * }
 * ```
 */
export function findSessionByIdentifier<T extends SessionIdentifier>(
	sessions: T[],
	identifier: string
): T | undefined {
	return sessions.find((s) => {
		// Match by slug (if available)
		if (s.slug && s.slug === identifier) return true;
		// Match by UUID prefix (first N chars)
		if (s.uuid.startsWith(identifier)) return true;
		// Match by full UUID
		if (s.uuid === identifier) return true;
		return false;
	});
}

// ============================================
// Markdown Utilities
// ============================================

/**
 * Options for rendering markdown content.
 */
export interface RenderMarkdownOptions {
	/** Strip H1 headings from the output (useful for content that already has a title) */
	stripH1?: boolean;
}

/**
 * Render markdown content to sanitized HTML.
 *
 * Uses marked for parsing and DOMPurify for sanitization.
 * Handles both sync and async parsing from marked.
 *
 * @param content - Markdown content to render
 * @param options - Rendering options
 * @returns Promise resolving to sanitized HTML string
 *
 * @example
 * ```ts
 * const html = await renderMarkdown('# Hello\n\nWorld');
 * // Returns: '<h1>Hello</h1>\n<p>World</p>'
 * ```
 */
export async function renderMarkdown(
	content: string,
	options: RenderMarkdownOptions = {}
): Promise<string> {
	const parsed = marked.parse(content || '');
	let html: string;

	if (parsed instanceof Promise) {
		html = await parsed;
	} else {
		html = parsed;
	}

	// Sanitize HTML
	html = DOMPurify.sanitize(html);

	// Optionally strip H1 headings
	if (options.stripH1) {
		html = html.replace(/<h1[^>]*>.*?<\/h1>/gi, '');
	}

	return html;
}

/**
 * Synchronous markdown rendering helper for reactive contexts.
 *
 * Returns an object with a `then` method for use in Svelte $effect blocks.
 * This handles the sync/async nature of marked.parse() gracefully.
 *
 * @param content - Markdown content to render
 * @param options - Rendering options
 * @param callback - Function to call with the rendered HTML
 *
 * @example
 * ```svelte
 * let renderedHtml = $state('');
 * $effect(() => {
 *   renderMarkdownEffect(content, {}, (html) => { renderedHtml = html; });
 * });
 * ```
 */
export function renderMarkdownEffect(
	content: string,
	options: RenderMarkdownOptions = {},
	callback: (html: string) => void
): void {
	const parsed = marked.parse(content || '');

	const processHtml = (html: string) => {
		html = DOMPurify.sanitize(html);
		if (options.stripH1) {
			html = html.replace(/<h1[^>]*>.*?<\/h1>/gi, '');
		}
		callback(html);
	};

	if (parsed instanceof Promise) {
		parsed.then(processHtml);
	} else {
		processHtml(parsed);
	}
}

// ============================================
// Table Sort Utilities
// ============================================

/**
 * Returns the sort indicator string for a column header.
 * Returns ' ↓' for descending, ' ↑' for ascending, '' if not the active column.
 */
export function sortIndicator(activeKey: string, columnKey: string, sortDir: 'asc' | 'desc'): string {
	if (activeKey !== columnKey) return '';
	return sortDir === 'desc' ? ' ↓' : ' ↑';
}

// ============================================
// Session Mapping
// ============================================

/**
 * Convert an McpSessionSummary (returned by skills/commands/tools endpoints)
 * into the SessionWithContext shape expected by GlobalSessionCard and session
 * filter components.
 */
export function toSessionWithContext(s: McpSessionSummary | SessionSummary): SessionWithContext {
	const encoded = ('project_encoded_name' in s ? s.project_encoded_name : undefined) ?? undefined;
	const displayName = ('project_display_name' in s ? s.project_display_name : undefined) ?? undefined;
	return {
		uuid: s.uuid,
		slug: s.slug ?? '',
		message_count: s.message_count,
		start_time: s.start_time ?? '',
		end_time: s.end_time ?? undefined,
		duration_seconds: s.duration_seconds ?? undefined,
		models_used: s.models_used,
		subagent_count: s.subagent_count,
		has_todos: false,
		initial_prompt: s.initial_prompt ?? undefined,
		git_branches: s.git_branches,
		session_titles: s.session_titles,
		project_encoded_name: encoded,
		project_path: encoded ?? '',
		project_name: displayName || getProjectNameFromEncoded(encoded ?? ''),
		session_source: ('session_source' in s ? s.session_source : undefined) ?? undefined,
		source: ('source' in s ? s.source : undefined) ?? undefined,
		remote_user_id: ('remote_user_id' in s ? s.remote_user_id : undefined) ?? undefined,
		remote_machine_id: ('remote_machine_id' in s ? s.remote_machine_id : undefined) ?? undefined
	};
}

// ============================================
// Byte Formatting
// ============================================

/**
 * Format bytes into human-readable size (e.g., "1.2 MB", "3.5 GB")
 * Uses binary units (1024-based).
 */
export function formatBytes(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/**
 * Format bytes per second into human-readable rate (e.g., "1.2 KB/s")
 * Uses binary units (1024-based).
 */
export function formatBytesRate(bytesPerSec: number): string {
	if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`;
	if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
	if (bytesPerSec < 1024 * 1024 * 1024)
		return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`;
	return `${(bytesPerSec / (1024 * 1024 * 1024)).toFixed(1)} GB/s`;
}
