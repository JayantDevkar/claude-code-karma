<script lang="ts">
	import {
		Bot,
		Zap,
		Terminal,
		Wrench,
		Webhook,
		ChevronDown,
		ChevronRight,
		Loader2,
		X,
		FileText
	} from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import type { PluginCapabilities, PluginCommandDetail } from '$lib/api-types';
	import { API_BASE } from '$lib/config';

	interface Props {
		capabilities: PluginCapabilities;
		pluginName: string;
		pluginColor?: string;
		pluginColorSubtle?: string;
	}

	let { capabilities, pluginName, pluginColor, pluginColorSubtle }: Props = $props();

	// Strip registry qualifier (e.g., "feature-dev@claude-plugins-official" -> "feature-dev")
	// to match the subagent_type stored in the database
	let pluginShortName = $derived(pluginName.split('@')[0]);

	// Track expanded sections
	let expandedSections = $state<Set<string>>(new Set(['agents', 'skills']));

	// Track which command is expanded for inline detail
	let expandedCommand = $state<string | null>(null);

	// Command content cache (fetched once, reused)
	let commandContents = $state<Record<string, string | null>>({});
	let commandsLoading = $state(false);
	let commandsFetched = $state(false);

	function toggleSection(section: string) {
		if (expandedSections.has(section)) {
			expandedSections.delete(section);
		} else {
			expandedSections.add(section);
		}
		expandedSections = new Set(expandedSections);
	}

	async function toggleCommand(commandName: string) {
		if (expandedCommand === commandName) {
			expandedCommand = null;
			return;
		}

		expandedCommand = commandName;

		// Fetch all command contents on first expand (single API call)
		if (!commandsFetched && !commandsLoading) {
			commandsLoading = true;
			try {
				const res = await fetch(
					`${API_BASE}/plugins/${encodeURIComponent(pluginName)}/commands`
				);
				if (res.ok) {
					const data = await res.json();
					const map: Record<string, string | null> = {};
					for (const cmd of data.commands as PluginCommandDetail[]) {
						map[cmd.name] = cmd.content;
					}
					commandContents = map;
				}
			} catch {
				// Silently fail — user sees "No content available"
			} finally {
				commandsLoading = false;
				commandsFetched = true;
			}
		}
	}

	// Render markdown for expanded command
	let renderedCommandContent = $state('');

	$effect(() => {
		if (expandedCommand && commandContents[expandedCommand]) {
			const parsed = marked.parse(commandContents[expandedCommand]!);
			if (parsed instanceof Promise) {
				parsed.then((html) => (renderedCommandContent = DOMPurify.sanitize(html)));
			} else {
				renderedCommandContent = DOMPurify.sanitize(parsed);
			}
		} else {
			renderedCommandContent = '';
		}
	});

	// Human-readable display name for MCP server identifiers
	// e.g. "plugin_playwright_playwright" -> "Playwright"
	function mcpDisplayName(name: string): string {
		let n = name;
		if (n.startsWith('plugin_')) {
			const parts = n.slice(7).split('_');
			if (parts.length >= 2 && parts[0] === parts[1]) n = parts[0];
			else n = parts.join('_');
		}
		return n.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
	}

	// Capability sections config - use $derived for reactivity
	let sections = $derived([
		{
			key: 'agents',
			label: 'Agents',
			items: capabilities.agents,
			linkPrefix: '/agents/',
			requiresPlugin: true
		},
		{
			key: 'skills',
			label: 'Skills',
			items: capabilities.skills,
			linkPrefix: '/skills/',
			requiresPlugin: true
		},
		{
			key: 'commands',
			label: 'Commands',
			items: capabilities.commands,
			linkPrefix: null as string | null,
			requiresPlugin: false
		},
		{
			key: 'mcp_tools',
			label: 'MCP Tools',
			items: capabilities.mcp_tools,
			linkPrefix: '/tools/' as string | null,
			requiresPlugin: false
		},
		{
			key: 'hooks',
			label: 'Hooks',
			items: capabilities.hooks,
			linkPrefix: null as string | null,
			requiresPlugin: false
		}
	]);

	// Total capabilities count
	let totalCount = $derived(
		capabilities.agents.length +
			capabilities.skills.length +
			capabilities.commands.length +
			capabilities.mcp_tools.length +
			capabilities.hooks.length
	);
</script>

<div class="space-y-3">
	<div class="flex items-center justify-between mb-4">
		<h3 class="text-sm font-semibold text-[var(--text-primary)]">What This Plugin Provides</h3>
		<span class="text-xs text-[var(--text-muted)] bg-[var(--bg-subtle)] px-2 py-1 rounded-full">
			{totalCount} total
		</span>
	</div>

	{#each sections as section (section.key)}
		{@const isExpanded = expandedSections.has(section.key)}
		{@const hasItems = section.items.length > 0}

		<div class="border border-[var(--border)] rounded-lg overflow-hidden">
			<!-- Section header -->
			<button
				onclick={() => toggleSection(section.key)}
				class="w-full flex items-center justify-between px-4 py-3 bg-[var(--bg-subtle)] hover:bg-[var(--bg-muted)] transition-colors text-left"
				disabled={!hasItems}
			>
				<div class="flex items-center gap-3">
					{#if section.key === 'agents'}
						<Bot
							size={16}
							style={pluginColor ? `color: ${pluginColor};` : ''}
							class={pluginColor ? '' : 'text-[var(--text-muted)]'}
						/>
					{:else if section.key === 'skills'}
						<Zap
							size={16}
							style={pluginColor ? `color: ${pluginColor};` : ''}
							class={pluginColor ? '' : 'text-[var(--text-muted)]'}
						/>
					{:else if section.key === 'commands'}
						<Terminal
							size={16}
							style={pluginColor ? `color: ${pluginColor};` : ''}
							class={pluginColor ? '' : 'text-[var(--text-muted)]'}
						/>
					{:else if section.key === 'mcp_tools'}
						<Wrench
							size={16}
							style={pluginColor ? `color: ${pluginColor};` : ''}
							class={pluginColor ? '' : 'text-[var(--text-muted)]'}
						/>
					{:else}
						<Webhook
							size={16}
							style={pluginColor ? `color: ${pluginColor};` : ''}
							class={pluginColor ? '' : 'text-[var(--text-muted)]'}
						/>
					{/if}
					<span class="text-sm font-medium text-[var(--text-primary)]"
						>{section.label}</span
					>
					<span
						class="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-base)] text-[var(--text-muted)]"
					>
						{section.items.length}
					</span>
				</div>
				{#if hasItems}
					{#if isExpanded}
						<ChevronDown size={16} class="text-[var(--text-muted)]" />
					{:else}
						<ChevronRight size={16} class="text-[var(--text-muted)]" />
					{/if}
				{/if}
			</button>

			<!-- Section content -->
			{#if isExpanded && hasItems}
				<div class="p-4 bg-[var(--bg-base)] border-t border-[var(--border)]">
					{#if section.key === 'commands'}
						<!-- Commands get special interactive card treatment -->
						<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
							{#each section.items as item}
								{@const isActive = expandedCommand === item}
								<button
									onclick={() => toggleCommand(item)}
									class="
										flex items-center gap-2.5 px-4 py-3
										text-left
										border rounded-lg
										transition-all duration-200
										group/cmd
										{isActive
										? 'bg-[var(--accent-muted)] border-l-[3px] border-l-[var(--accent)] border-t-[var(--accent)]/20 border-r-[var(--accent)]/20 border-b-[var(--accent)]/20 shadow-[0_0_12px_rgba(var(--accent-rgb),0.08)]'
										: 'bg-[var(--bg-subtle)] hover:bg-[var(--bg-muted)] border-[var(--border-subtle)] hover:border-[var(--border)]'}
									"
								>
									<span
										class="
											inline-flex items-center justify-center
											w-6 h-6 rounded-md
											text-[10px] font-bold font-mono
											flex-shrink-0
											transition-colors duration-200
											{isActive ? 'bg-[var(--accent)] text-white' : 'bg-[var(--accent-subtle)] text-[var(--accent)]'}
										">/</span
									>
									<span
										class="text-sm font-medium truncate font-mono transition-colors duration-200 {isActive
											? 'text-[var(--accent)]'
											: 'text-[var(--text-primary)]'}"
									>
										{item}
									</span>
									<ChevronRight
										size={14}
										class="
											ml-auto flex-shrink-0
											transition-transform duration-200
											{isActive
											? 'rotate-90 text-[var(--accent)]'
											: 'text-[var(--text-faint)] group-hover/cmd:text-[var(--text-muted)]'}
										"
									/>
								</button>
							{/each}
						</div>

						<!-- Expanded command documentation panel -->
						{#if expandedCommand}
							<div
								class="cmd-doc-panel mt-4 rounded-xl overflow-hidden border border-[var(--accent)]/20 shadow-[0_2px_20px_rgba(var(--accent-rgb),0.06)]"
							>
								<!-- Accent top stripe -->
								<div
									class="h-[3px] bg-gradient-to-r from-[var(--accent)] via-[var(--accent-hover)] to-[var(--accent)]/40"
								></div>

								<!-- Panel header -->
								<div
									class="flex items-start justify-between gap-4 px-5 py-4 bg-gradient-to-b from-[var(--accent-muted)] to-[var(--bg-base)]"
								>
									<div class="flex items-start gap-3.5 min-w-0">
										<span
											class="
												inline-flex items-center justify-center
												w-10 h-10 rounded-lg flex-shrink-0
												bg-[var(--accent)] text-white
												text-lg font-bold font-mono
												shadow-[0_2px_8px_rgba(var(--accent-rgb),0.3)]
											">/</span
										>
										<div class="min-w-0">
											<h4
												class="text-lg font-semibold font-mono text-[var(--text-primary)] truncate leading-tight"
											>
												/{expandedCommand}
											</h4>
											<div class="flex items-center gap-1.5 mt-1">
												<FileText
													size={12}
													class="text-[var(--accent)] flex-shrink-0"
												/>
												<span
													class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider"
												>
													Command Documentation
												</span>
											</div>
										</div>
									</div>
									<button
										onclick={() => (expandedCommand = null)}
										aria-label="Close command documentation"
										class="
											flex items-center justify-center
											w-8 h-8 rounded-lg flex-shrink-0
											text-[var(--text-muted)] hover:text-[var(--text-primary)]
											bg-[var(--bg-subtle)] hover:bg-[var(--bg-muted)]
											border border-[var(--border-subtle)] hover:border-[var(--border)]
											transition-all duration-150
										"
									>
										<X size={14} strokeWidth={2.5} />
									</button>
								</div>

								<!-- Divider -->
								<div class="h-px bg-[var(--border)]"></div>

								<!-- Content body -->
								<div class="px-6 py-5 bg-[var(--bg-base)]">
									{#if commandsLoading}
										<div
											class="flex flex-col items-center justify-center py-10 gap-3"
										>
											<div
												class="w-10 h-10 rounded-full bg-[var(--accent-subtle)] flex items-center justify-center"
											>
												<Loader2
													size={20}
													class="animate-spin text-[var(--accent)]"
												/>
											</div>
											<span class="text-sm text-[var(--text-muted)]"
												>Loading documentation...</span
											>
										</div>
									{:else if renderedCommandContent}
										<div
											class="markdown-preview prose prose-slate max-w-none text-sm"
										>
											{@html renderedCommandContent}
										</div>
									{:else}
										<div
											class="flex flex-col items-center justify-center py-10 gap-2 text-center"
										>
											<FileText size={24} class="text-[var(--text-faint)]" />
											<p class="text-sm text-[var(--text-muted)]">
												No documentation available for this command.
											</p>
										</div>
									{/if}
								</div>
							</div>
						{/if}
					{:else}
						<div class="flex flex-wrap gap-2">
							{#each section.items as item}
								{#if section.linkPrefix}
									{@const fullName = section.requiresPlugin
										? pluginShortName + ':' + item
										: item}
									{@const displayName =
										section.key === 'mcp_tools' ? mcpDisplayName(item) : item}
									<a
										href="{section.linkPrefix}{encodeURIComponent(fullName)}"
										class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full transition-all duration-200 hover:scale-[1.03] hover:shadow-sm"
										style="background-color: {pluginColorSubtle ||
											'var(--bg-subtle)'}; color: {pluginColor ||
											'var(--text-secondary)'}; border: 1px solid transparent;"
										onmouseenter={(e) => {
											e.currentTarget.style.borderColor =
												pluginColor || 'var(--border)';
										}}
										onmouseleave={(e) => {
											e.currentTarget.style.borderColor = 'transparent';
										}}
									>
										{displayName}
									</a>
								{:else}
									<span
										class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full transition-colors cursor-default"
										style="background-color: {pluginColorSubtle ||
											'var(--bg-subtle)'}; color: {pluginColor ||
											'var(--text-secondary)'};"
									>
										{item}
									</span>
								{/if}
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/each}
</div>
