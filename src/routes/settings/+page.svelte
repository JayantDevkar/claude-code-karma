<script lang="ts">
	import { ChevronDown, ChevronRight, Code2, Settings as SettingsIcon } from 'lucide-svelte';
	import { SettingsSkeleton } from '$lib/components/skeleton';
	import { onMount } from 'svelte';
	import Switch from '$lib/components/ui/Switch.svelte';
	import SelectDropdown from '$lib/components/ui/SelectDropdown.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SettingsSection from '$lib/components/settings/SettingsSection.svelte';
	import SettingItem from '$lib/components/settings/SettingItem.svelte';
	import PermissionsList from '$lib/components/settings/PermissionsList.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import type { ClaudeSettings, PermissionMode } from '$lib/api-types';
	import { RETENTION_OPTIONS } from '$lib/api-types';
	import { API_BASE } from '$lib/config';

	// State
	let isLoading = $state(true);
	let settings = $state<ClaudeSettings>({});
	let savingField = $state<string | null>(null);
	let successField = $state<string | null>(null);
	let error = $state<string | null>(null);
	let showRawJson = $state(false);

	// Derived states
	let retentionValue = $derived(settings.cleanupPeriodDays ?? 30);
	let permissionMode = $derived(settings.permissions?.defaultMode ?? 'default');
	let permissions = $derived(settings.permissions?.allow ?? []);
	let plugins = $derived(Object.entries(settings.enabledPlugins ?? {}));
	let statusLineCommand = $derived(settings.statusLine?.command ?? '');

	// Load settings on mount
	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/settings/`);
			if (res.ok) {
				settings = await res.json();
			}
		} catch (e) {
			console.error('Error fetching settings:', e);
			error = 'Failed to load settings. Please ensure the backend is running.';
		} finally {
			isLoading = false;
		}
	});

	// Generic update function
	async function updateSetting(field: string, value: unknown) {
		savingField = field;
		successField = null;

		try {
			const res = await fetch(`${API_BASE}/settings/`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ [field]: value })
			});

			if (res.ok) {
				const updated = await res.json();
				settings = { ...settings, ...updated };
				successField = field;
				setTimeout(() => {
					if (successField === field) successField = null;
				}, 2000);
			} else {
				throw new Error('Failed to save');
			}
		} catch (e) {
			console.error(`Error saving ${field}:`, e);
			error = `Failed to save ${field}`;
		} finally {
			savingField = null;
		}
	}

	// Update nested permission settings
	async function updatePermissions(newPermissions: Partial<ClaudeSettings['permissions']>) {
		const currentPermissions = settings.permissions ?? {};
		const merged = { ...currentPermissions, ...newPermissions };
		await updateSetting('permissions', merged);
	}

	// Handlers
	function handleRetentionChange(value: string | number) {
		updateSetting('cleanupPeriodDays', Number(value));
	}

	function handleThinkingToggle(checked: boolean) {
		updateSetting('alwaysThinkingEnabled', checked);
	}

	function handlePermissionModeChange(value: string) {
		updatePermissions({ defaultMode: value as PermissionMode });
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

	{#if error}
		<div
			class="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400"
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
			<!-- GENERAL Section -->
			<SettingsSection title="General">
				<SettingItem
					title="Session Retention"
					description="How long to keep session history before automatic cleanup."
					saving={savingField === 'cleanupPeriodDays'}
					success={successField === 'cleanupPeriodDays' ? 'Saved' : null}
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
					description="Enable 'always thinking' mode for deeper reasoning. Uses more tokens but produces more thorough responses."
					saving={savingField === 'alwaysThinkingEnabled'}
					success={successField === 'alwaysThinkingEnabled' ? 'Saved' : null}
				>
					{#snippet control()}
						<Switch
							checked={settings.alwaysThinkingEnabled ?? false}
							onCheckedChange={handleThinkingToggle}
							disabled={savingField === 'alwaysThinkingEnabled'}
						/>
					{/snippet}
				</SettingItem>
			</SettingsSection>

			<!-- PERMISSIONS Section -->
			<SettingsSection title="Permissions">
				<SettingItem
					title="Default Permission Mode"
					description="How Claude handles permission requests for tools."
					saving={savingField === 'permissions'}
					success={successField === 'permissions' ? 'Saved' : null}
				>
					{#snippet control()}
						<SegmentedControl
							options={[
								{ label: 'Default', value: 'default' },
								{ label: 'Ask Before Edits', value: 'acceptEdits' },
								{ label: 'Bypass All', value: 'bypassPermissions' }
							]}
							value={permissionMode}
							onchange={handlePermissionModeChange}
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
							MCP tools that are granted permission automatically.
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
			{#if plugins.length > 0}
				<SettingsSection title="Plugins">
					{#each plugins as [pluginName, enabled]}
						<SettingItem
							title={pluginName}
							saving={savingField === 'enabledPlugins'}
							success={successField === 'enabledPlugins' ? 'Saved' : null}
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
				</SettingsSection>
			{/if}

			<!-- ADVANCED Section -->
			<SettingsSection title="Advanced">
				<SettingItem
					title="Status Line Command"
					description="Custom script for status line display. Script must be executable and output a single line."
					hint="Example: ~/.claude/statusline-command.sh"
					saving={savingField === 'statusLine'}
					success={successField === 'statusLine' ? 'Saved' : null}
				>
					{#snippet control()}
						<TextInput
							value={statusLineCommand}
							placeholder="~/.claude/statusline-command.sh"
							oninput={handleStatusLineChange}
							disabled={savingField === 'statusLine'}
							class="w-64 font-mono text-xs"
						/>
					{/snippet}
				</SettingItem>

				<!-- Raw JSON Viewer -->
				<div class="p-5">
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
