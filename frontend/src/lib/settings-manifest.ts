// Manifest of curated, day-to-day Claude Code settings the settings page
// renders generically. Each entry drives one control end-to-end: no code
// change is needed elsewhere to relabel, redefault, or re-enum a setting —
// only this file. See docs/settings-page-v2-plan.md for the full rationale
// and .github/workflows/schema-drift.yml for how this list stays honest
// against upstream Claude Code releases.
//
// Bespoke settings (permissions, plugins, statusLine, retention) render from
// hand-written markup in +page.svelte and are intentionally not forced in here.

export type SettingValueType = 'boolean' | 'enum' | 'string';

export interface SettingSelectOption {
	value: string;
	label: string;
}

export interface SettingManifestEntry {
	/** Dot-path into settings.json, e.g. "spellcheck.enabled" */
	key: string;
	type: SettingValueType;
	/** Required when type === 'enum' */
	options?: SettingSelectOption[];
	default: string | boolean | null;
	title: string;
	/** One sentence — the "what". Deeper "why"/tradeoffs live in the Settings Guide doc, not here. */
	description: string;
	/** Optional short caveat worth surfacing inline even after the guide exists (e.g. a prerequisite gotcha). */
	hint?: string;
	/** Every setting on this page is read at session start, so this is always true today — kept as a field in case a live-reloadable setting is added later. */
	restartRequired: boolean;
	section: string;
	prerequisite?: 'spellchecker';
	docsUrl: string;
	placeholder?: string;
	/** Suggestions for type === 'string' */
	datalist?: string[];
}

export const SETTINGS_MANIFEST: SettingManifestEntry[] = [
	{
		key: 'spellcheck.enabled',
		type: 'boolean',
		default: false,
		title: 'Spell Check',
		description:
			'Underlines misspelled words as you type — purely visual, nothing gets auto-corrected.',
		restartRequired: true,
		section: 'Input',
		prerequisite: 'spellchecker',
		docsUrl: 'https://code.claude.com/docs/en/settings-reference#spellcheck'
	},
	{
		key: 'editorMode',
		type: 'enum',
		options: [
			{ value: 'normal', label: 'Normal' },
			{ value: 'vim', label: 'Vim' }
		],
		default: 'normal',
		title: 'Editor Mode',
		description: 'Vim keybindings in the prompt box — hjkl, text objects, the usual.',
		hint: 'Enter still submits, even in insert mode.',
		restartRequired: true,
		section: 'Input',
		docsUrl: 'https://code.claude.com/docs/en/settings-reference#editormode'
	},
	{
		key: 'preferredNotifChannel',
		type: 'enum',
		options: [
			{ value: 'auto', label: 'Auto' },
			{ value: 'iterm2', label: 'iTerm2' },
			{ value: 'terminal_bell', label: 'Terminal Bell' },
			{ value: 'iterm2_with_bell', label: 'iTerm2 w/ Bell' },
			{ value: 'kitty', label: 'Kitty' },
			{ value: 'ghostty', label: 'Ghostty' },
			{ value: 'notifications_disabled', label: 'Disabled' }
		],
		default: 'auto',
		title: 'Notifications',
		description: 'How Claude Code alerts you when it finishes or needs input.',
		hint: 'Desktop notifications only fire in iTerm2, Kitty, or Ghostty — pick Terminal Bell for a sound in any terminal.',
		restartRequired: true,
		section: 'Notifications',
		docsUrl: 'https://code.claude.com/docs/en/settings-reference#preferrednotifchannel'
	},
	{
		key: 'includeCoAuthoredBy',
		type: 'boolean',
		default: true,
		title: 'Commit Attribution',
		description: 'Removes the "Co-Authored-By: Claude" line from commits when turned off.',
		restartRequired: true,
		section: 'Git',
		docsUrl: 'https://code.claude.com/docs/en/settings-reference#includecoauthoredby'
	},
	{
		key: 'model',
		type: 'string',
		default: null,
		title: 'Default Model',
		description: 'Model used at session start — an alias like sonnet/opus, or a full model ID.',
		restartRequired: true,
		section: 'General',
		placeholder: 'e.g. sonnet, opus, claude-sonnet-5',
		datalist: [
			'sonnet',
			'opus',
			'haiku',
			'fable',
			'claude-sonnet-5',
			'claude-opus-5',
			'claude-haiku-4-5-20251001',
			'claude-fable-5'
		],
		docsUrl: 'https://code.claude.com/docs/en/settings-reference#model'
	},
	{
		key: 'autoUpdatesChannel',
		type: 'enum',
		options: [
			{ value: 'latest', label: 'Latest (default)' },
			{ value: 'stable', label: 'Stable' }
		],
		default: 'latest',
		title: 'Update Channel',
		description: 'Release channel Claude Code follows for updates.',
		hint: 'Stable trails Latest by about a week and skips versions with major regressions.',
		restartRequired: true,
		section: 'General',
		docsUrl: 'https://code.claude.com/docs/en/settings-reference#autoupdateschannel'
	},
	{
		key: 'verbose',
		type: 'boolean',
		default: false,
		title: 'Verbose Output',
		description: 'Shows full command output in the transcript instead of collapsed summaries.',
		restartRequired: true,
		section: 'General',
		docsUrl: 'https://code.claude.com/docs/en/settings-reference#verbose'
	}
];

/** Reads a dot-path (e.g. "spellcheck.enabled") out of a settings object. */
export function getSettingValue(settings: Record<string, unknown>, key: string): unknown {
	return key.split('.').reduce<unknown>((acc, part) => {
		if (acc == null || typeof acc !== 'object') return undefined;
		return (acc as Record<string, unknown>)[part];
	}, settings);
}

/**
 * Builds the nested PUT payload for a dot-path key, e.g.
 * buildSettingPayload("spellcheck.enabled", true) -> { spellcheck: { enabled: true } }
 * Passing `null` builds the same shape with a null leaf, which the API's
 * deep-merge treats as "delete this key" — this is how reset-to-default works.
 */
export function buildSettingPayload(key: string, value: unknown): Record<string, unknown> {
	const parts = key.split('.');
	const leafKey = parts.pop() as string;
	let payload: Record<string, unknown> = { [leafKey]: value };
	for (let i = parts.length - 1; i >= 0; i--) {
		payload = { [parts[i]]: payload };
	}
	return payload;
}
