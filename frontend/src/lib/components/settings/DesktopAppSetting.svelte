<script lang="ts">
	/**
	 * Installs the desktop launcher without leaving the dashboard.
	 *
	 * Starting the servers by hand is a one-time cost when you first clone
	 * karma. Making the icon that removes that cost require *another* terminal
	 * command defeats the purpose, so the install lives here instead.
	 */
	import { onMount } from 'svelte';
	import { Loader2, Check, Monitor, AlertTriangle } from 'lucide-svelte';
	import SettingItem from './SettingItem.svelte';
	import Switch from '$lib/components/ui/Switch.svelte';
	import { API_BASE } from '$lib/config';

	interface DesktopAppStatus {
		supported: boolean;
		platform: string;
		installed: boolean;
		install_path: string | null;
		autostart_enabled: boolean;
		web_port: number;
		api_port: number;
		repo_root: string;
	}

	let status = $state<DesktopAppStatus | null>(null);
	let statusFailed = $state(false);
	let busy = $state(false);
	let messages = $state<string[]>([]);
	let error = $state<string | null>(null);
	let autostart = $state(false);
	let pinToDock = $state(true);

	let isMac = $derived(status?.platform === 'darwin');
	let placeName = $derived(isMac ? 'Dock' : 'Desktop');

	// Pinning the launcher only makes sense without autostart. When autostart is
	// on the servers come up at login and the PWA is the icon, so a reinstall
	// must not re-pin the launcher the autostart flow deliberately removed.
	$effect(() => {
		if (autostart) pinToDock = false;
	});

	async function loadStatus() {
		statusFailed = false;
		try {
			const res = await fetch(`${API_BASE}/desktop-app/status`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			status = await res.json();
			autostart = status?.autostart_enabled ?? false;
		} catch (e) {
			// Mark the check as failed so the UI shows an error with a retry,
			// rather than sitting on the "Checking…" spinner forever (which is
			// what a null status with no failure flag would render).
			statusFailed = true;
			error = 'Could not check desktop app status.';
			console.error(e);
		}
	}

	onMount(loadStatus);

	async function install() {
		busy = true;
		error = null;
		messages = [];
		try {
			const res = await fetch(`${API_BASE}/desktop-app/install`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				// Autostart is its own toggle below, not part of installing the icon.
				body: JSON.stringify({ dock: pinToDock, autostart: false })
			});
			const body = await res.json();
			if (!res.ok) throw new Error(body.detail ?? 'Install failed');
			messages = body.messages ?? [];
			await loadStatus();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Install failed.';
		} finally {
			busy = false;
		}
	}

	async function setAutostart(enabled: boolean) {
		busy = true;
		error = null;
		messages = [];
		try {
			const res = await fetch(`${API_BASE}/desktop-app/autostart`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled })
			});
			const body = await res.json();
			if (!res.ok) throw new Error(body.detail ?? 'Could not change the setting');
			messages = body.messages ?? [];
			// Trust the server's reading of the filesystem over the click, so the
			// toggle snaps back if the change did not actually take effect.
			autostart = body.enabled;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not change the setting.';
			await loadStatus();
		} finally {
			busy = false;
		}
	}

	async function uninstall() {
		// One click otherwise removes the app bundle, its Dock tile and the
		// login item together, so confirm first.
		if (
			!confirm(
				'Remove the Karma desktop app? This deletes the app, its Dock tile and any login item.'
			)
		) {
			return;
		}
		busy = true;
		error = null;
		messages = [];
		try {
			const res = await fetch(`${API_BASE}/desktop-app/install`, { method: 'DELETE' });
			const body = await res.json();
			if (!res.ok) throw new Error(body.detail ?? 'Uninstall failed');
			messages = body.messages ?? [];
			await loadStatus();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Uninstall failed.';
		} finally {
			busy = false;
		}
	}
</script>

{#if statusFailed}
	<SettingItem
		title="Desktop app"
		description="Couldn’t reach the API to check the desktop app status. Make sure the Karma API is running, then retry."
	>
		{#snippet control()}
			<button
				class="px-3 py-1.5 text-xs rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] disabled:opacity-50"
				onclick={loadStatus}
				disabled={busy}
			>
				Retry
			</button>
		{/snippet}
	</SettingItem>
{:else if status === null}
	<SettingItem
		title="Desktop app"
		description="Checking desktop app status…"
	>
		{#snippet control()}
			<Loader2 size={14} class="animate-spin text-[var(--text-muted)]" />
		{/snippet}
	</SettingItem>
{:else if !status?.supported}
	<SettingItem
		title="Desktop app"
		description="Only macOS and Windows have a desktop launcher so far. You can still start Karma from the command line."
	>
		{#snippet control()}
			<span class="text-xs text-[var(--text-muted)]">Not available on {status?.platform}</span>
		{/snippet}
	</SettingItem>
{:else}
	<SettingItem
		title="Desktop app"
		description={status?.installed
			? `Installed. Click the Karma icon to start both servers and open the dashboard.`
			: `Adds a Karma icon to your ${placeName}. Clicking it starts the API and frontend for you, so you never need two terminals again.`}
		hint={status?.installed && status.install_path ? status.install_path : undefined}
	>
		{#snippet control()}
			<div class="flex items-center gap-2">
				{#if status?.installed}
					<span
						class="inline-flex items-center gap-1 text-xs text-[var(--success)] font-medium"
					>
						<Check size={13} /> Installed
					</span>
					<button
						class="px-3 py-1.5 text-xs rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] disabled:opacity-50"
						onclick={uninstall}
						disabled={busy}
					>
						Remove
					</button>
					<button
						class="px-3 py-1.5 text-xs rounded-md bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-50"
						onclick={install}
						disabled={busy}
					>
						Reinstall
					</button>
				{:else}
					<button
						class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-50"
						onclick={install}
						disabled={busy}
					>
						{#if busy}
							<Loader2 size={13} class="animate-spin" />
							Installing…
						{:else}
							<Monitor size={13} />
							Install
						{/if}
					</button>
				{/if}
			</div>
		{/snippet}
	</SettingItem>

	{#if isMac && !autostart}
		<SettingItem
			title="Pin the launcher to the Dock"
			description="Adds one Karma tile you click to start the servers. Only useful without autostart — with autostart on, pin the browser-installed Karma instead, since the servers are already running. Note: pinning briefly restarts the Dock."
		>
			{#snippet control()}
				<Switch bind:checked={pinToDock} />
			{/snippet}
		</SettingItem>
	{/if}

	<SettingItem
		title="Start Karma at login"
		description="Brings the servers up when you log in, so the dashboard is simply always there — a browser-installed Karma window then works on its own, with no icon to click first. Costs roughly 150–350 MB of memory in the background and almost no CPU."
		saving={busy}
	>
		{#snippet control()}
			<Switch bind:checked={autostart} disabled={busy} onCheckedChange={(v) => setAutostart(v)} />
		{/snippet}
	</SettingItem>
{/if}

{#if messages.length > 0}
	<div class="px-5 py-3 bg-[var(--bg-subtle)] space-y-1">
		{#each messages as message}
			<p class="text-xs text-[var(--text-secondary)] font-mono">{message}</p>
		{/each}
	</div>
{/if}

{#if error}
	<div class="px-5 py-3 flex items-start gap-2 bg-[var(--bg-subtle)]">
		<AlertTriangle size={14} class="text-[var(--error)] mt-0.5 shrink-0" />
		<p class="text-xs text-[var(--error)]">{error}</p>
	</div>
{/if}
