<script lang="ts">
	import { BookOpen, ChevronDown, ChevronRight, Code2, Settings as SettingsIcon } from 'lucide-svelte';
	import { SettingsSkeleton } from '$lib/components/skeleton';
	import { onMount } from 'svelte';
	import Switch from '$lib/components/ui/Switch.svelte';
	import SelectDropdown from '$lib/components/ui/SelectDropdown.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import CopyIconButton from '$lib/components/ui/CopyIconButton.svelte';
	import SettingsSection from '$lib/components/settings/SettingsSection.svelte';
	import SettingItem from '$lib/components/settings/SettingItem.svelte';
	import ManifestSettingItem from '$lib/components/settings/ManifestSettingItem.svelte';
	import PermissionsList from '$lib/components/settings/PermissionsList.svelte';
	import DesktopAppSetting from '$lib/components/settings/DesktopAppSetting.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import type { ClaudeSettings, PermissionMode, SettingsEnvironment } from '$lib/api-types';
	import { RETENTION_OPTIONS, PERMISSION_MODE_OPTIONS } from '$lib/api-types';
	import {
		SETTINGS_MANIFEST,
		getSettingValue,
		buildSettingPayload,
		type SettingManifestEntry
	} from '$lib/settings-manifest';
	import { API_BASE } from '$lib/config';

	// State
	let isLoading = $state(true);
	let settings = $state<ClaudeSettings>({});
	let environment = $state<SettingsEnvironment | null>(null);
	let savingField = $state<string | null>(null);
	let successField = $state<string | null>(null);
	let error = $state<string | null>(null);
	let showRawJson = $state(false);

	const manifestTimeouts: Record<string, ReturnType<typeof setTimeout>> = {};

	// Derived states
	let retentionValue = $derived(settings.cleanupPeriodDays ?? 30);
	let retentionIsDefault = $derived(
		settings.cleanupPeriodDays === undefined || settings.cleanupPeriodDays === 30
	);
	let permissionMode = $derived(settings.permissions?.defaultMode ?? 'default');
	let permissionModeIsDefault = $derived(
		settings.permissions?.defaultMode === undefined || settings.permissions?.defaultMode === 'default'
	);
	let permissions = $derived(settings.permissions?.allow ?? []);
	let plugins = $derived(Object.entries(settings.enabledPlugins ?? {}));
	let statusLineCommand = $derived(settings.statusLine?.command ?? '');
	let activePermissionDescription = $derived(
		PERMISSION_MODE_OPTIONS.find((o) => o.value === permissionMode)?.description ?? ''
	);
	let thinkingIsDefault = $derived(
		settings.alwaysThinkingEnabled === undefined || settings.alwaysThinkingEnabled === false
	);
	let spellcheckerMissing = $derived(environment !== null && environment.spellcheckers.length === 0);

	function settingsBySection(section: string): SettingManifestEntry[] {
		return SETTINGS_MANIFEST.filter((entry) => entry.section === section);
	}

	// Accordion: at most 2 sections open at once. Opening a 3rd closes
	// whichever of the current 2 was opened first (oldest-in, first-out).
	let openSections = $state<string[]>(['Desktop App']);

	function isSectionOpen(title: string): boolean {
		return openSections.includes(title);
	}

	function toggleSection(title: string) {
		if (openSections.includes(title)) {
			openSections = openSections.filter((t) => t !== title);
		} else if (openSections.length >= 2) {
			openSections = [...openSections.slice(1), title];
		} else {
			openSections = [...openSections, title];
		}
	}

	// Load settings + environment on mount
	onMount(async () => {
		try {
			const [settingsRes, envRes] = await Promise.all([
				fetch(`${API_BASE}/settings/`),
				fetch(`${API_BASE}/settings/environment`)
			]);
			if (settingsRes.ok) {
				settings = await settingsRes.json();
			}
			if (envRes.ok) {
				environment = await envRes.json();
			}
		} catch (e) {
			console.error('Error fetching settings:', e);
			error = 'Failed to load settings. Please ensure the backend is running.';
		} finally {
			isLoading = false;
		}
	});

	// Generic update function. The API always returns the full, freshly-merged
	// settings.json — replace local state wholesale (not a shallow spread) so a
	// server-side key deletion (reset-to-default) is reflected immediately.
	//
	// `trackingKey` (defaults to `field`) is what drives the saving/success UI
	// state, kept separate from `field` (the actual top-level API field sent)
	// so a dot-path manifest entry can track by its full key — e.g.
	// "spellcheck.enabled" — rather than by "spellcheck", the shared top-level
	// field a sibling entry (e.g. a future "spellcheck.language") would also
	// send, which would otherwise show a false "saving" spinner on it too.
	async function updateSetting(field: string, value: unknown, trackingKey: string = field) {
		savingField = trackingKey;
		successField = null;

		try {
			const res = await fetch(`${API_BASE}/settings/`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ [field]: value })
			});

			if (res.ok) {
				settings = await res.json();
				successField = trackingKey;
				setTimeout(() => {
					if (successField === trackingKey) successField = null;
				}, 2000);
			} else {
				const body = await res.json().catch(() => null);
				throw new Error(body?.detail ?? 'Failed to save');
			}
		} catch (e) {
			console.error(`Error saving ${field}:`, e);
			error = e instanceof Error ? e.message : `Failed to save ${field}`;
		} finally {
			savingField = null;
		}
	}

	// Update nested permission settings. `defaultMode: null` deletes the key
	// (reset to Claude Code's own default) rather than writing a literal null.
	type PermissionsPatch = {
		allow?: string[] | null;
		deny?: string[] | null;
		defaultMode?: PermissionMode | null;
	};

	async function updatePermissions(newPermissions: PermissionsPatch) {
		const currentPermissions = settings.permissions ?? {};
		const merged = { ...currentPermissions, ...newPermissions };
		await updateSetting('permissions', merged);
	}

	// Handlers
	function handleRetentionChange(value: string | number) {
		updateSetting('cleanupPeriodDays', Number(value));
	}

	function handleRetentionReset() {
		updateSetting('cleanupPeriodDays', null);
	}

	function handleThinkingToggle(checked: boolean) {
		updateSetting('alwaysThinkingEnabled', checked);
	}

	function handleThinkingReset() {
		updateSetting('alwaysThinkingEnabled', null);
	}

	function handlePermissionModeChange(value: string) {
		updatePermissions({ defaultMode: value as PermissionMode });
	}

	function handlePermissionModeReset() {
		updatePermissions({ defaultMode: null });
	}

	function handlePermissionAdd(perm: string) {
		const current = settings.permissions?.allow ?? [];
		if (!current.includes(perm)) {
			updatePermissions({ allow: [...current, perm] });
		}
	}

	function handlePermissionRemove(perm: string) {
		const current = settings.permissions?.allow ?? [];
		updatePermissions({ allow: current.filter((p) => p !== perm) });
	}

	function handlePluginToggle(pluginName: string, enabled: boolean) {
		const currentPlugins = settings.enabledPlugins ?? {};
		updateSetting('enabledPlugins', { ...currentPlugins, [pluginName]: enabled });
	}

	let statusLineTimeout: ReturnType<typeof setTimeout>;
	function handleStatusLineChange(e: Event) {
		const target = e.target as HTMLInputElement;
		const value = target.value;

		// Debounce status line updates
		clearTimeout(statusLineTimeout);
		statusLineTimeout = setTimeout(() => {
			updateSetting('statusLine', { type: 'command', command: value });
		}, 500);
	}

	// Manifest-driven settings — one generic path for all seven curated keys.
	function manifestValue(entry: SettingManifestEntry): unknown {
		return getSettingValue(settings as Record<string, unknown>, entry.key);
	}

	function handleManifestChange(entry: SettingManifestEntry, value: string | boolean) {
		const topKey = entry.key.split('.')[0];
		const payload = buildSettingPayload(entry.key, value)[topKey];

		if (entry.type === 'string') {
			clearTimeout(manifestTimeouts[entry.key]);
			manifestTimeouts[entry.key] = setTimeout(
				() => updateSetting(topKey, payload, entry.key),
				500
			);
		} else {
			updateSetting(topKey, payload, entry.key);
		}
	}

	function handleManifestReset(entry: SettingManifestEntry) {
		const topKey = entry.key.split('.')[0];
		const payload = buildSettingPayload(entry.key, null)[topKey];
		updateSetting(topKey, payload, entry.key);
	}
</script>

<div class="max-w-2xl mx-auto px-6 pb-12">
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title="Settings"
		icon={SettingsIcon}
		iconColor="--nav-indigo"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Settings' }]}
		subtitle="Manage your Claude Code configuration"
	/>

	<a
		href="/about?doc=settings-guide.md"
		class="flex items-center justify-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors -mt-3 mb-6"
	>
		<BookOpen size={12} />
		Settings Guide — what these settings do and why they matter
	</a>

	{#if error}
		<div
			class="mb-6 p-4 bg-[var(--error-subtle)] border border-[var(--error)] rounded-lg text-sm text-[var(--error)]"
		>
			{error}
			<button
				class="ml-2 underline hover:no-underline"
				onclick={() => window.location.reload()}
			>
				Retry
			</button>
		</div>
	{/if}

	{#if isLoading}
		<SettingsSkeleton />
	{:else}
		<div class="space-y-6">
			<!-- DESKTOP APP Section -->
			<SettingsSection
				title="Desktop App"
				open={isSectionOpen('Desktop App')}
				onToggle={() => toggleSection('Desktop App')}
			>
				<DesktopAppSetting />
			</SettingsSection>

			<!-- GENERAL Section -->
			<SettingsSection
				title="General"
				open={isSectionOpen('General')}
				onToggle={() => toggleSection('General')}
			>
				<SettingItem
					title="Session Retention"
					description="How long inactive sessions stick around before their transcripts are deleted."
					saving={savingField === 'cleanupPeriodDays'}
					success={successField === 'cleanupPeriodDays' ? 'Saved' : null}
					restartRequired
					defaultLabel="Default: 30 days"
					showReset={!retentionIsDefault}
					onReset={handleRetentionReset}
				>
					{#snippet control()}
						<SelectDropdown
							options={RETENTION_OPTIONS.map((o) => ({
								label: o.label,
								value: o.value
							}))}
							value={retentionValue}
							onchange={handleRetentionChange}
							disabled={savingField === 'cleanupPeriodDays'}
						/>
					{/snippet}
				</SettingItem>

				<SettingItem
					title="Extended Thinking"
					description="Turns on deeper reasoning by default, for every session."
					hint="Slower and pricier per response — toggle per-session with Option+T instead if you only need it sometimes."
					saving={savingField === 'alwaysThinkingEnabled'}
					success={successField === 'alwaysThinkingEnabled' ? 'Saved' : null}
					restartRequired
					defaultLabel="Default: Off"
					showReset={!thinkingIsDefault}
					onReset={handleThinkingReset}
				>
					{#snippet control()}
						<Switch
							checked={settings.alwaysThinkingEnabled ?? false}
							onCheckedChange={handleThinkingToggle}
							disabled={savingField === 'alwaysThinkingEnabled'}
						/>
					{/snippet}
				</SettingItem>

				{#each settingsBySection('General') as entry (entry.key)}
					<ManifestSettingItem
						{entry}
						value={manifestValue(entry)}
						saving={savingField === entry.key}
						success={successField === entry.key}
						onchange={(value) => handleManifestChange(entry, value)}
						onreset={() => handleManifestReset(entry)}
					/>
				{/each}
			</SettingsSection>

			<!-- INPUT Section -->
			<SettingsSection
				title="Input"
				open={isSectionOpen('Input')}
				onToggle={() => toggleSection('Input')}
			>
				{#each settingsBySection('Input') as entry (entry.key)}
					<ManifestSettingItem
						{entry}
						value={manifestValue(entry)}
						saving={savingField === entry.key}
						success={successField === entry.key}
						blocked={entry.prerequisite === 'spellchecker' && spellcheckerMissing}
						blockedHint={entry.prerequisite === 'spellchecker' && spellcheckerMissing
							? 'No spell checker found — install one with `brew install aspell` (macOS) or `apt install aspell` (Linux).'
							: undefined}
						onchange={(value) => handleManifestChange(entry, value)}
						onreset={() => handleManifestReset(entry)}
					/>
				{/each}
			</SettingsSection>

			<!-- NOTIFICATIONS Section -->
			<SettingsSection
				title="Notifications"
				open={isSectionOpen('Notifications')}
				onToggle={() => toggleSection('Notifications')}
			>
				{#each settingsBySection('Notifications') as entry (entry.key)}
					<ManifestSettingItem
						{entry}
						value={manifestValue(entry)}
						saving={savingField === entry.key}
						success={successField === entry.key}
						onchange={(value) => handleManifestChange(entry, value)}
						onreset={() => handleManifestReset(entry)}
					/>
				{/each}
			</SettingsSection>

			<!-- GIT Section -->
			<SettingsSection
				title="Git"
				open={isSectionOpen('Git')}
				onToggle={() => toggleSection('Git')}
			>
				{#each settingsBySection('Git') as entry (entry.key)}
					<ManifestSettingItem
						{entry}
						value={manifestValue(entry)}
						saving={savingField === entry.key}
						success={successField === entry.key}
						onchange={(value) => handleManifestChange(entry, value)}
						onreset={() => handleManifestReset(entry)}
					/>
				{/each}
			</SettingsSection>

			<!-- PERMISSIONS Section -->
			<SettingsSection
				title="Permissions"
				open={isSectionOpen('Permissions')}
				onToggle={() => toggleSection('Permissions')}
			>
				<SettingItem
					title="Default Permission Mode"
					description="Controls how Claude handles tool permission requests at the start of each session."
					hint={activePermissionDescription || undefined}
					saving={savingField === 'permissions'}
					success={successField === 'permissions' ? 'Saved' : null}
					restartRequired
					defaultLabel="Default: Default"
					showReset={!permissionModeIsDefault}
					onReset={handlePermissionModeReset}
				>
					{#snippet control()}
						<SelectDropdown
							options={PERMISSION_MODE_OPTIONS.map((o) => ({
								label: o.label,
								value: o.value
							}))}
							value={permissionMode}
							onchange={(v) => handlePermissionModeChange(String(v))}
							disabled={savingField === 'permissions'}
						/>
					{/snippet}
				</SettingItem>

				<div class="p-5">
					<div class="space-y-1.5 mb-4">
						<h3 class="text-sm font-medium text-[var(--text-primary)]">
							Allowed Tools
						</h3>
						<p class="text-[13px] text-[var(--text-secondary)]">
							Tools and commands that are granted permission automatically, without prompting.
						</p>
					</div>
					<PermissionsList
						{permissions}
						onAdd={handlePermissionAdd}
						onRemove={handlePermissionRemove}
						disabled={savingField === 'permissions'}
					/>
				</div>
			</SettingsSection>

			<!-- PLUGINS Section -->
			<SettingsSection
				title="Plugins"
				open={isSectionOpen('Plugins')}
				onToggle={() => toggleSection('Plugins')}
			>
				{#if plugins.length > 0}
					{#each plugins as [pluginName, enabled]}
						<SettingItem
							title={pluginName}
							saving={savingField === 'enabledPlugins'}
							success={successField === 'enabledPlugins' ? 'Saved' : null}
							restartRequired
						>
							{#snippet control()}
								<Switch
									checked={enabled}
									onCheckedChange={(checked) =>
										handlePluginToggle(pluginName, checked)}
									disabled={savingField === 'enabledPlugins'}
								/>
							{/snippet}
						</SettingItem>
					{/each}
				{:else}
					<div class="p-5">
						<p class="text-sm text-[var(--text-muted)]">
							No plugins installed. Install plugins with <code class="text-xs font-mono bg-[var(--bg-muted)] px-1.5 py-0.5 rounded">/install-plugin</code> in Claude Code.
						</p>
					</div>
				{/if}
			</SettingsSection>

			<!-- ADVANCED Section -->
			<SettingsSection
				title="Advanced"
				open={isSectionOpen('Advanced')}
				onToggle={() => toggleSection('Advanced')}
			>
				<SettingItem
					title="Status Line Command"
					description="Shell command that prints a custom status line at the bottom of Claude Code's terminal."
					hint="Run /statusline in Claude Code to generate one, or try: jq -r '.model.display_name'"
					saving={savingField === 'statusLine'}
					success={successField === 'statusLine' ? 'Saved' : null}
					restartRequired
				>
					{#snippet control()}
						<div class="flex items-center gap-1.5">
							<TextInput
								value={statusLineCommand}
								placeholder="~/.claude/statusline-command.sh"
								oninput={handleStatusLineChange}
								disabled={savingField === 'statusLine'}
								class="w-64 font-mono text-xs"
							/>
							{#if statusLineCommand}
								<CopyIconButton text={statusLineCommand} title="Copy command" />
							{/if}
						</div>
					{/snippet}
				</SettingItem>

				<!-- Raw JSON Viewer -->
				<div class="p-5">
					<div class="flex items-center justify-between">
						<button
							onclick={() => (showRawJson = !showRawJson)}
							class="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
						>
							{#if showRawJson}
								<ChevronDown size={16} />
							{:else}
								<ChevronRight size={16} />
							{/if}
							<Code2 size={14} />
							View Raw JSON
						</button>
						{#if showRawJson}
							<CopyIconButton text={JSON.stringify(settings, null, 2)} title="Copy JSON" />
						{/if}
					</div>

					{#if showRawJson}
						<div class="mt-4">
							<pre
								class="p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg text-xs font-mono text-[var(--text-secondary)] overflow-x-auto">{JSON.stringify(
									settings,
									null,
									2
								)}</pre>
						</div>
					{/if}
				</div>
			</SettingsSection>
		</div>
	{/if}
</div>
