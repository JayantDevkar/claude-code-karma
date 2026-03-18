import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
	formatDuration,
	formatDurationCompact,
	formatTokens,
	formatTokensFull,
	formatCost,
	truncate,
	formatFileSize,
	formatCharCount,
	cn,
	getModelDisplayName,
	getModelDisplayNameCompact,
	getModelBadgeLabel,
	formatDisplayPath,
	decodeProjectPath,
	getProjectNameFromEncoded,
	getSessionDisplayName,
	sessionHasTitle,
	getModelColor,
	cleanSkillName,
	getSkillPluginNamespace,
	cleanAgentIdForDisplay,
	isSystemAgent,
	inferSubagentTypeFromId,
	getEffectiveSubagentType,
	findSessionByIdentifier,
	formatElapsedTime,
	getMondayOfWeek,
	isHourBasedFilter,
	isKnownSubagentType,
	calculateSubagentDuration
} from '$lib/utils';

// ============================================================
// formatDuration
// ============================================================
describe('formatDuration', () => {
	it('returns -- for null', () => {
		expect(formatDuration(null)).toBe('--');
	});

	it('returns -- for undefined', () => {
		expect(formatDuration(undefined)).toBe('--');
	});

	it('returns -- for 0', () => {
		expect(formatDuration(0)).toBe('--');
	});

	it('returns -- for negative', () => {
		expect(formatDuration(-1)).toBe('--');
	});

	it('formats 45 seconds', () => {
		expect(formatDuration(45)).toBe('45s');
	});

	it('formats 2m 10s for 130 seconds (minutes < 10)', () => {
		expect(formatDuration(130)).toBe('2m 10s');
	});

	it('formats 1h 1m for 3661 seconds', () => {
		expect(formatDuration(3661)).toBe('1h 1m');
	});

	it('formats 2h for 7200 seconds', () => {
		expect(formatDuration(7200)).toBe('2h');
	});

	it('formats whole minutes without seconds when minutes >= 10', () => {
		// 600 seconds = 10m exactly, no seconds
		expect(formatDuration(600)).toBe('10m');
	});

	it('formats minutes without seconds when seconds = 0', () => {
		expect(formatDuration(120)).toBe('2m');
	});
});

// ============================================================
// formatDurationCompact
// ============================================================
describe('formatDurationCompact', () => {
	it('returns -- for null', () => {
		expect(formatDurationCompact(null)).toBe('--');
	});

	it('returns -- for undefined', () => {
		expect(formatDurationCompact(undefined)).toBe('--');
	});

	it('returns -- for 0', () => {
		expect(formatDurationCompact(0)).toBe('--');
	});

	it('formats 45 seconds', () => {
		expect(formatDurationCompact(45)).toBe('45s');
	});

	it('formats 130 seconds as 2m (compact, no seconds)', () => {
		expect(formatDurationCompact(130)).toBe('2m');
	});

	it('formats 3661 seconds as 1h', () => {
		expect(formatDurationCompact(3661)).toBe('1h');
	});
});

// ============================================================
// formatTokens
// ============================================================
describe('formatTokens', () => {
	it('returns -- for null', () => {
		expect(formatTokens(null)).toBe('--');
	});

	it('returns -- for undefined', () => {
		expect(formatTokens(undefined)).toBe('--');
	});

	it('returns -- for 0', () => {
		expect(formatTokens(0)).toBe('--');
	});

	it('formats 500 as 500', () => {
		expect(formatTokens(500)).toBe('500');
	});

	it('formats 1500 as 1.5K', () => {
		expect(formatTokens(1500)).toBe('1.5K');
	});

	it('formats 1500000 as 1.5M', () => {
		expect(formatTokens(1_500_000)).toBe('1.5M');
	});

	it('formats 1000 as 1.0K', () => {
		expect(formatTokens(1000)).toBe('1.0K');
	});
});

// ============================================================
// formatTokensFull
// ============================================================
describe('formatTokensFull', () => {
	it('returns -- for null', () => {
		expect(formatTokensFull(null)).toBe('--');
	});

	it('returns -- for undefined', () => {
		expect(formatTokensFull(undefined)).toBe('--');
	});

	it('returns -- for 0', () => {
		expect(formatTokensFull(0)).toBe('--');
	});

	it('formats 1234 with locale formatting', () => {
		expect(formatTokensFull(1234)).toBe('1,234');
	});

	it('formats small numbers without comma', () => {
		expect(formatTokensFull(500)).toBe('500');
	});
});

// ============================================================
// formatCost
// ============================================================
describe('formatCost', () => {
	it('returns -- for null', () => {
		expect(formatCost(null)).toBe('--');
	});

	it('returns -- for undefined', () => {
		expect(formatCost(undefined)).toBe('--');
	});

	it('returns -- for 0', () => {
		expect(formatCost(0)).toBe('--');
	});

	it('formats cost < 0.01 with 4 decimal places', () => {
		expect(formatCost(0.005)).toBe('$0.0050');
	});

	it('formats cost between 0.01 and 1 with 3 decimal places', () => {
		expect(formatCost(0.05)).toBe('$0.050');
	});

	it('formats cost >= 1 with 2 decimal places', () => {
		expect(formatCost(1.5)).toBe('$1.50');
	});

	it('formats cost exactly 0.01 with 3 decimal places', () => {
		expect(formatCost(0.01)).toBe('$0.010');
	});
});

// ============================================================
// truncate
// ============================================================
describe('truncate', () => {
	it('returns short text unchanged', () => {
		expect(truncate('hello', 10)).toBe('hello');
	});

	it('returns text exactly at max unchanged', () => {
		expect(truncate('hello', 5)).toBe('hello');
	});

	it('truncates long text with ellipsis', () => {
		expect(truncate('hello world', 8)).toBe('hello...');
	});

	it('truncates preserving maxLength including ellipsis', () => {
		const result = truncate('abcdefghij', 7);
		expect(result).toBe('abcd...');
		expect(result.length).toBe(7);
	});
});

// ============================================================
// formatFileSize
// ============================================================
describe('formatFileSize', () => {
	it('formats 0 bytes', () => {
		expect(formatFileSize(0)).toBe('0 B');
	});

	it('formats 1024 bytes as 1 KB', () => {
		expect(formatFileSize(1024)).toBe('1 KB');
	});

	it('formats 1048576 bytes as 1 MB', () => {
		expect(formatFileSize(1_048_576)).toBe('1 MB');
	});

	it('formats 512 bytes as B', () => {
		expect(formatFileSize(512)).toBe('512 B');
	});

	it('formats 1536 bytes as 1.5 KB', () => {
		expect(formatFileSize(1536)).toBe('1.5 KB');
	});
});

// ============================================================
// formatCharCount
// ============================================================
describe('formatCharCount', () => {
	it('formats 500 as 500', () => {
		expect(formatCharCount(500)).toBe('500');
	});

	it('formats 1500 as 1.5K', () => {
		expect(formatCharCount(1500)).toBe('1.5K');
	});

	it('formats 1500000 as 1.5M', () => {
		expect(formatCharCount(1_500_000)).toBe('1.5M');
	});

	it('formats 0 as 0', () => {
		expect(formatCharCount(0)).toBe('0');
	});
});

// ============================================================
// cn
// ============================================================
describe('cn', () => {
	it('combines multiple class names', () => {
		expect(cn('foo', 'bar')).toBe('foo bar');
	});

	it('filters out falsy values', () => {
		expect(cn('foo', false, null, undefined, 'bar')).toBe('foo bar');
	});

	it('returns empty string for all falsy', () => {
		expect(cn(false, null, undefined)).toBe('');
	});

	it('handles single class', () => {
		expect(cn('only')).toBe('only');
	});

	it('handles empty call', () => {
		expect(cn()).toBe('');
	});
});

// ============================================================
// getModelDisplayName
// ============================================================
describe('getModelDisplayName', () => {
	it('returns Sonnet for sonnet model', () => {
		expect(getModelDisplayName('claude-3-5-sonnet-20241022')).toBe('Sonnet');
	});

	it('returns Opus for opus model', () => {
		expect(getModelDisplayName('claude-3-opus')).toBe('Opus');
	});

	it('returns Sonnet 4.5 for sonnet-4-5 model', () => {
		expect(getModelDisplayName('claude-sonnet-4-5-xxx')).toBe('Sonnet 4.5');
	});

	it('returns Haiku for haiku model', () => {
		expect(getModelDisplayName('claude-3-haiku')).toBe('Haiku');
	});

	it('returns Opus 4.5 for opus-4-5 model', () => {
		expect(getModelDisplayName('claude-opus-4-5-20251101')).toBe('Opus 4.5');
	});

	it('strips claude- prefix and hyphens for unknown model', () => {
		expect(getModelDisplayName('claude-unknown-model')).toBe('unknown model');
	});
});

// ============================================================
// getModelDisplayNameCompact
// ============================================================
describe('getModelDisplayNameCompact', () => {
	it('returns S4.5 for sonnet-4-5 model', () => {
		expect(getModelDisplayNameCompact('claude-sonnet-4-5-xxx')).toBe('S4.5');
	});

	it('returns O4.5 for opus-4-5 model', () => {
		expect(getModelDisplayNameCompact('claude-opus-4-5-xxx')).toBe('O4.5');
	});

	it('returns Sonnet for generic sonnet', () => {
		expect(getModelDisplayNameCompact('claude-3-5-sonnet-20241022')).toBe('Sonnet');
	});

	it('returns Opus for generic opus', () => {
		expect(getModelDisplayNameCompact('claude-3-opus')).toBe('Opus');
	});

	it('returns Haiku for haiku model', () => {
		expect(getModelDisplayNameCompact('claude-3-haiku')).toBe('Haiku');
	});

	it('slices first 8 chars for unknown model', () => {
		expect(getModelDisplayNameCompact('abcdefghijklmnop')).toBe('abcdefgh');
	});
});

// ============================================================
// getModelBadgeLabel
// ============================================================
describe('getModelBadgeLabel', () => {
	it('returns O 4.6 for opus-4-6 model', () => {
		expect(getModelBadgeLabel('claude-opus-4-6-xxx')).toBe('O 4.6');
	});

	it('returns S 4.5 for sonnet-4-5 model', () => {
		expect(getModelBadgeLabel('claude-sonnet-4-5-xxx')).toBe('S 4.5');
	});

	it('returns Haiku for haiku model', () => {
		expect(getModelBadgeLabel('claude-3-haiku')).toBe('Haiku');
	});

	it('returns O for generic opus', () => {
		expect(getModelBadgeLabel('claude-3-opus')).toBe('O');
	});

	it('returns S for generic sonnet', () => {
		expect(getModelBadgeLabel('claude-3-5-sonnet-20241022')).toBe('S');
	});

	it('returns O 4.5 for opus-4-5 model', () => {
		expect(getModelBadgeLabel('claude-opus-4-5-xxx')).toBe('O 4.5');
	});

	it('returns S 4.6 for sonnet-4-6 model', () => {
		expect(getModelBadgeLabel('claude-sonnet-4-6-xxx')).toBe('S 4.6');
	});

	it('returns non-claude for unrecognized model', () => {
		expect(getModelBadgeLabel('gpt-4')).toBe('non-claude');
	});
});

// ============================================================
// formatDisplayPath
// ============================================================
describe('formatDisplayPath', () => {
	it('returns empty string for empty input', () => {
		expect(formatDisplayPath('')).toBe('');
	});

	it('returns project-relative path when inside project', () => {
		expect(
			formatDisplayPath('/Users/jay/project/src/file.ts', '/Users/jay/project')
		).toBe('src/file.ts');
	});

	it('returns . for exact project path match', () => {
		expect(formatDisplayPath('/Users/jay/project', '/Users/jay/project')).toBe('.');
	});

	it('shortens home dir with ~ when outside project', () => {
		expect(
			formatDisplayPath('/Users/jay/.config/settings.json', '/Users/jay/project')
		).toBe('~/.config/settings.json');
	});

	it('shortens home dir with ~ when no project path provided', () => {
		expect(formatDisplayPath('/Users/jay/file.txt')).toBe('~/file.txt');
	});

	it('returns absolute path when outside home dir', () => {
		expect(formatDisplayPath('/etc/hosts')).toBe('/etc/hosts');
	});

	it('handles Linux home paths', () => {
		expect(formatDisplayPath('/home/user/file.txt')).toBe('~/file.txt');
	});

	it('handles Windows paths with backslashes', () => {
		expect(
			formatDisplayPath('C:\\Users\\jay\\project\\src\\file.ts', 'C:/Users/jay/project')
		).toBe('src/file.ts');
	});

	it('handles Windows home dir with ~ shortening', () => {
		expect(
			formatDisplayPath('C:/Users/jay/.config/settings.json', 'C:/Users/jay/project')
		).toBe('~/.config/settings.json');
	});
});

// ============================================================
// decodeProjectPath
// ============================================================
describe('decodeProjectPath', () => {
	it('decodes a standard Documents/GitHub path', () => {
		const result = decodeProjectPath('-Users-me-Documents-GitHub-my-project');
		expect(result).toContain('/Users/');
		expect(result).toContain('my-project');
	});

	it('decodes a Users path', () => {
		const result = decodeProjectPath('-Users-jayant-Projects-repo');
		expect(result).toContain('/Users/jayant/');
	});

	it('fallback decode replaces hyphens with slashes', () => {
		const result = decodeProjectPath('-etc-config-file');
		expect(result).toBe('/etc/config/file');
	});

	// Windows path tests
	it('decodes a Windows C: drive path', () => {
		const result = decodeProjectPath('C--Code-Tools');
		expect(result).toBe('C:/Code/Tools');
	});

	it('decodes a Windows user path', () => {
		const result = decodeProjectPath('C--Users-test-Documents-GitHub-my-project');
		expect(result).toContain('C:/Users/test/');
		expect(result).toContain('my-project');
	});

	it('decodes a Windows D: drive path', () => {
		const result = decodeProjectPath('D--Projects-myapp');
		expect(result).toBe('D:/Projects/myapp');
	});

	it('normalizes lowercase Windows drive letter to uppercase', () => {
		const result = decodeProjectPath('c--Code-Tools');
		expect(result).toBe('C:/Code/Tools');
	});
});

// ============================================================
// getProjectNameFromEncoded
// ============================================================
describe('getProjectNameFromEncoded', () => {
	it('extracts project name from Documents/GitHub path', () => {
		const result = getProjectNameFromEncoded('-Users-me-Documents-GitHub-my-project');
		expect(result).toBe('Documents-GitHub-my-project');
	});

	it('extracts project name preserving all content after user prefix', () => {
		const result = getProjectNameFromEncoded('-Users-me-Documents-GitHub-claude-karma');
		expect(result).toBe('Documents-GitHub-claude-karma');
	});

	it('extracts from Desktop path preserving intermediate dirs', () => {
		const result = getProjectNameFromEncoded('-Users-me-Desktop-cool-app');
		expect(result).toBe('Desktop-cool-app');
	});

	it('extracts from non-standard parent directory like My-Github', () => {
		const result = getProjectNameFromEncoded('-Users-me-My-Github-verticalSlice');
		expect(result).toBe('My-Github-verticalSlice');
	});

	it('extracts from Linux home path', () => {
		const result = getProjectNameFromEncoded('-home-user-projects-my-app');
		expect(result).toBe('projects-my-app');
	});

	it('returns stripped encoded name for unrecognized format', () => {
		const result = getProjectNameFromEncoded('weird-format');
		expect(result).toBe('weird-format');
	});

	it('handles single-component after user prefix', () => {
		const result = getProjectNameFromEncoded('-Users-me-myrepo');
		expect(result).toBe('myrepo');
	});

	// Windows path tests
	it('extracts from Windows Users path', () => {
		const result = getProjectNameFromEncoded('C--Users-test-Documents-GitHub-my-project');
		expect(result).toBe('Documents-GitHub-my-project');
	});

	it('extracts from Windows non-Users path', () => {
		const result = getProjectNameFromEncoded('C--Code-Tools');
		expect(result).toBe('Code-Tools');
	});

	it('extracts from Windows D: drive path', () => {
		const result = getProjectNameFromEncoded('D--Projects-myapp');
		expect(result).toBe('Projects-myapp');
	});
});

// ============================================================
// getSessionDisplayName
// ============================================================
describe('getSessionDisplayName', () => {
	it('returns first title when titles array has items', () => {
		expect(getSessionDisplayName(['My Title', 'Other'], 'my-slug', 'uuid-123')).toBe('My Title');
	});

	it('falls back to chainTitle when no session titles', () => {
		expect(getSessionDisplayName([], undefined, 'uuid-123', 'Chain Title')).toBe('Chain Title');
	});

	it('falls back to slug when no title or chainTitle', () => {
		expect(getSessionDisplayName([], 'my-slug', 'uuid-12345678')).toBe('my-slug');
	});

	it('falls back to uuid prefix (8 chars) when no slug', () => {
		expect(getSessionDisplayName([], undefined, 'uuid-12345678abc')).toBe('uuid-123');
	});

	it('returns Session when everything is undefined', () => {
		expect(getSessionDisplayName()).toBe('Session');
	});

	it('prefers titles over chainTitle', () => {
		expect(getSessionDisplayName(['Real Title'], 'slug', 'uuid', 'Chain')).toBe('Real Title');
	});
});

// ============================================================
// sessionHasTitle
// ============================================================
describe('sessionHasTitle', () => {
	it('returns true when titles array has items', () => {
		expect(sessionHasTitle(['My Title'])).toBe(true);
	});

	it('returns false for empty titles array', () => {
		expect(sessionHasTitle([])).toBe(false);
	});

	it('returns false for undefined titles', () => {
		expect(sessionHasTitle(undefined)).toBe(false);
	});

	it('returns true when chainTitle provided and no session titles', () => {
		expect(sessionHasTitle([], 'Chain Title')).toBe(true);
	});

	it('returns false when both are empty/undefined', () => {
		expect(sessionHasTitle(undefined, undefined)).toBe(false);
	});
});

// ============================================================
// getModelColor
// ============================================================
describe('getModelColor', () => {
	it('returns default for empty array', () => {
		expect(getModelColor([])).toBe('default');
	});

	it('returns opus for opus model', () => {
		expect(getModelColor(['claude-3-opus'])).toBe('opus');
	});

	it('returns sonnet for sonnet model', () => {
		expect(getModelColor(['claude-3-5-sonnet-20241022'])).toBe('sonnet');
	});

	it('returns haiku for haiku model', () => {
		expect(getModelColor(['claude-3-haiku'])).toBe('haiku');
	});

	it('returns default for unrecognized model', () => {
		expect(getModelColor(['gpt-4'])).toBe('default');
	});

	it('uses first model in array', () => {
		expect(getModelColor(['claude-3-opus', 'claude-3-haiku'])).toBe('opus');
	});
});

// ============================================================
// cleanSkillName
// ============================================================
describe('cleanSkillName', () => {
	it('returns name unchanged for non-plugin skill', () => {
		expect(cleanSkillName('my-custom-skill', false)).toBe('my-custom-skill');
	});

	it('extracts final segment for plugin skill with one colon', () => {
		expect(cleanSkillName('oh-my-claudecode:autopilot', true)).toBe('autopilot');
	});

	it('extracts final segment for nested plugin skill', () => {
		expect(cleanSkillName('plugin:feature-dev:code-explorer', true)).toBe('code-explorer');
	});

	it('returns name unchanged for plugin without colon', () => {
		expect(cleanSkillName('no-colon', true)).toBe('no-colon');
	});

	it('defaults isPlugin to false', () => {
		expect(cleanSkillName('oh-my-claudecode:test')).toBe('oh-my-claudecode:test');
	});
});

// ============================================================
// getSkillPluginNamespace
// ============================================================
describe('getSkillPluginNamespace', () => {
	it('returns namespace before last colon', () => {
		expect(getSkillPluginNamespace('oh-my-claudecode:autopilot')).toBe('oh-my-claudecode');
	});

	it('returns full prefix for nested namespaces', () => {
		expect(getSkillPluginNamespace('plugin:feature-dev:code-explorer')).toBe('plugin:feature-dev');
	});

	it('returns null when no colon present', () => {
		expect(getSkillPluginNamespace('no-namespace')).toBeNull();
	});
});

// ============================================================
// cleanAgentIdForDisplay
// ============================================================
describe('cleanAgentIdForDisplay', () => {
	it('strips aprompt_suggestion- prefix', () => {
		expect(cleanAgentIdForDisplay('aprompt_suggestion-7796cd')).toBe('7796cd');
	});

	it('strips acompact- prefix', () => {
		expect(cleanAgentIdForDisplay('acompact-abc123')).toBe('abc123');
	});

	it('returns id unchanged for non-system agent', () => {
		expect(cleanAgentIdForDisplay('regular-agent-id')).toBe('regular-agent-id');
	});
});

// ============================================================
// isSystemAgent
// ============================================================
describe('isSystemAgent', () => {
	it('returns true for aprompt_suggestion- prefix', () => {
		expect(isSystemAgent('aprompt_suggestion-7796cd')).toBe(true);
	});

	it('returns true for acompact- prefix', () => {
		expect(isSystemAgent('acompact-abc123')).toBe(true);
	});

	it('returns false for regular agent', () => {
		expect(isSystemAgent('regular-agent')).toBe(false);
	});
});

// ============================================================
// inferSubagentTypeFromId
// ============================================================
describe('inferSubagentTypeFromId', () => {
	it('infers acompact from acompact- prefix', () => {
		expect(inferSubagentTypeFromId('acompact-abc')).toBe('acompact');
	});

	it('infers aprompt_suggestion from aprompt_suggestion- prefix', () => {
		expect(inferSubagentTypeFromId('aprompt_suggestion-xyz')).toBe('aprompt_suggestion');
	});

	it('returns null for unknown prefix', () => {
		expect(inferSubagentTypeFromId('unknown-agent')).toBeNull();
	});
});

// ============================================================
// getEffectiveSubagentType
// ============================================================
describe('getEffectiveSubagentType', () => {
	it('returns subagentType when provided', () => {
		expect(getEffectiveSubagentType('Explore', 'some-id')).toBe('Explore');
	});

	it('falls back to inferring from agentId when type is null', () => {
		expect(getEffectiveSubagentType(null, 'acompact-abc')).toBe('acompact');
	});

	it('falls back to inferring from agentId when type is undefined', () => {
		expect(getEffectiveSubagentType(undefined, 'aprompt_suggestion-xyz')).toBe('aprompt_suggestion');
	});

	it('returns null when no type and unknown id', () => {
		expect(getEffectiveSubagentType(null, 'unknown-agent')).toBeNull();
	});
});

// ============================================================
// findSessionByIdentifier
// ============================================================
describe('findSessionByIdentifier', () => {
	const sessions = [
		{ uuid: 'abc123def456', slug: 'my-session' },
		{ uuid: 'xyz789uvw012', slug: null },
		{ uuid: 'fff000111222', slug: 'another-session' }
	];

	it('matches by exact slug', () => {
		const result = findSessionByIdentifier(sessions, 'my-session');
		expect(result?.uuid).toBe('abc123def456');
	});

	it('matches by UUID prefix', () => {
		const result = findSessionByIdentifier(sessions, 'xyz789');
		expect(result?.uuid).toBe('xyz789uvw012');
	});

	it('matches by full UUID', () => {
		const result = findSessionByIdentifier(sessions, 'fff000111222');
		expect(result?.uuid).toBe('fff000111222');
	});

	it('returns undefined when no match', () => {
		const result = findSessionByIdentifier(sessions, 'nonexistent');
		expect(result).toBeUndefined();
	});

	it('returns undefined for empty sessions array', () => {
		const result = findSessionByIdentifier([], 'anything');
		expect(result).toBeUndefined();
	});
});

// ============================================================
// formatElapsedTime
// ============================================================
describe('formatElapsedTime', () => {
	it('formats elapsed time in minutes and seconds', () => {
		const start = '2024-01-01T10:00:00.000Z';
		const event = '2024-01-01T10:02:30.000Z'; // 2m 30s later
		expect(formatElapsedTime(event, start)).toBe('+2:30');
	});

	it('formats elapsed time with hours', () => {
		const start = '2024-01-01T10:00:00.000Z';
		const event = '2024-01-01T11:05:10.000Z'; // 1h 5m 10s later
		expect(formatElapsedTime(event, start)).toBe('+1:05:10');
	});

	it('returns +0:00 for event before start', () => {
		const start = '2024-01-01T10:00:00.000Z';
		const event = '2024-01-01T09:59:00.000Z';
		expect(formatElapsedTime(event, start)).toBe('+0:00');
	});

	it('formats exactly 0 elapsed as +0:00', () => {
		const time = '2024-01-01T10:00:00.000Z';
		expect(formatElapsedTime(time, time)).toBe('+0:00');
	});
});

// ============================================================
// getMondayOfWeek
// ============================================================
describe('getMondayOfWeek', () => {
	it('returns Monday for a Wednesday input', () => {
		const wednesday = new Date(2024, 0, 10); // Wednesday Jan 10 2024 (local)
		const monday = getMondayOfWeek(wednesday);
		expect(monday.getDay()).toBe(1); // 1 = Monday
	});

	it('returns the same day for Monday input', () => {
		const monday = new Date(2024, 0, 8); // Monday Jan 8 2024 (local)
		const result = getMondayOfWeek(monday);
		expect(result.getDay()).toBe(1);
		expect(result.getDate()).toBe(8);
	});

	it('returns previous Monday for Sunday input', () => {
		const sunday = new Date(2024, 0, 14); // Sunday Jan 14 2024 (local)
		const result = getMondayOfWeek(sunday);
		expect(result.getDay()).toBe(1);
		expect(result.getDate()).toBe(8); // Should be Jan 8
	});

	it('sets time to midnight', () => {
		const date = new Date('2024-01-10T15:30:00');
		const monday = getMondayOfWeek(date);
		expect(monday.getHours()).toBe(0);
		expect(monday.getMinutes()).toBe(0);
		expect(monday.getSeconds()).toBe(0);
		expect(monday.getMilliseconds()).toBe(0);
	});
});

// ============================================================
// isHourBasedFilter
// ============================================================
describe('isHourBasedFilter', () => {
	it('returns true for 6h', () => {
		expect(isHourBasedFilter('6h')).toBe(true);
	});

	it('returns true for 12h', () => {
		expect(isHourBasedFilter('12h')).toBe(true);
	});

	it('returns true for 24h', () => {
		expect(isHourBasedFilter('24h')).toBe(true);
	});

	it('returns true for 48h', () => {
		expect(isHourBasedFilter('48h')).toBe(true);
	});

	it('returns false for all', () => {
		expect(isHourBasedFilter('all')).toBe(false);
	});

	it('returns false for this_week', () => {
		expect(isHourBasedFilter('this_week')).toBe(false);
	});

	it('returns false for this_month', () => {
		expect(isHourBasedFilter('this_month')).toBe(false);
	});
});

// ============================================================
// isKnownSubagentType
// ============================================================
describe('isKnownSubagentType', () => {
	it('returns true for Explore', () => {
		expect(isKnownSubagentType('Explore')).toBe(true);
	});

	it('returns true for Plan', () => {
		expect(isKnownSubagentType('Plan')).toBe(true);
	});

	it('returns true for Bash', () => {
		expect(isKnownSubagentType('Bash')).toBe(true);
	});

	it('returns true for acompact', () => {
		expect(isKnownSubagentType('acompact')).toBe(true);
	});

	it('returns true for aprompt_suggestion', () => {
		expect(isKnownSubagentType('aprompt_suggestion')).toBe(true);
	});

	it('returns false for unknown type', () => {
		expect(isKnownSubagentType('CustomType')).toBe(false);
	});

	it('returns false for null', () => {
		expect(isKnownSubagentType(null)).toBe(false);
	});

	it('returns false for undefined', () => {
		expect(isKnownSubagentType(undefined)).toBe(false);
	});
});

// ============================================================
// calculateSubagentDuration
// ============================================================
describe('calculateSubagentDuration', () => {
	it('returns null when started_at is undefined', () => {
		expect(calculateSubagentDuration(undefined)).toBeNull();
	});

	it('calculates duration from start to completed_at', () => {
		const start = '2024-01-01T10:00:00.000Z';
		const end = '2024-01-01T10:01:30.000Z'; // 90 seconds later
		expect(calculateSubagentDuration(start, end)).toBe(90);
	});

	it('calculates duration from start to now when completed_at is null', () => {
		const start = new Date(Date.now() - 5000).toISOString(); // 5 seconds ago
		const result = calculateSubagentDuration(start, null);
		// Should be approximately 5 seconds, allow for small timing variance
		expect(result).toBeGreaterThanOrEqual(4);
		expect(result).toBeLessThan(10);
	});

	it('returns 0 for zero duration', () => {
		const time = '2024-01-01T10:00:00.000Z';
		expect(calculateSubagentDuration(time, time)).toBe(0);
	});
});
