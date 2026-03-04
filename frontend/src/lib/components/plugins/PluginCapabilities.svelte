<script lang="ts">
	import {
		Bot,
		Zap,
		Terminal,
		Wrench,
		Webhook,
		ChevronDown,
		ChevronRight
	} from 'lucide-svelte';
	import type { PluginCapabilities } from '$lib/api-types';

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
	let expandedSections = $state<Set<string>>(new Set(['agents', 'skills', 'commands']));

	function toggleSection(section: string) {
		if (expandedSections.has(section)) {
			expandedSections.delete(section);
		} else {
			expandedSections.add(section);
		}
		expandedSections = new Set(expandedSections);
	}

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
			linkPrefix: '/commands/',
			requiresPlugin: true
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
									{#if section.key === 'commands'}
										<Terminal size={11} class="flex-shrink-0 opacity-70" />
									{/if}
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
				</div>
			{/if}
		</div>
	{/each}
</div>
