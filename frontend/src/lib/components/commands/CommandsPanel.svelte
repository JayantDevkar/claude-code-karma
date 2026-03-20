<script lang="ts">
	import { TerminalSquare, Zap } from 'lucide-svelte';
	import type { CommandUsage } from '$lib/api-types';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import { cleanSkillName, getCommandColorVars, getCommandCategoryColorVars, getCommandCategoryLabel } from '$lib/utils';

	interface Props {
		commands: CommandUsage[];
		projectEncodedName?: string;
	}

	let { commands }: Props = $props();

	// Deduplicate commands by name (same command can appear multiple times with different invocation_source)
	let sortedCommands = $derived.by(() => {
		const merged = new Map<string, CommandUsage>();
		for (const cmd of commands) {
			const existing = merged.get(cmd.name);
			if (existing) {
				merged.set(cmd.name, { ...existing, count: existing.count + cmd.count });
			} else {
				merged.set(cmd.name, { ...cmd });
			}
		}
		return [...merged.values()].sort((a, b) => b.count - a.count);
	});

	function isPluginCommand(command: CommandUsage): boolean {
		if (command.category) {
			return command.category === 'plugin_skill' || command.category === 'plugin_command';
		}
		return command.source === 'plugin';
	}

	function isBuiltinCommand(command: CommandUsage): boolean {
		if (command.category) {
			return command.category === 'builtin_command';
		}
		return command.source === 'builtin' || command.source === 'unknown';
	}

	function getCommandColors(command: CommandUsage): { color: string; subtle: string } {
		if (command.category) {
			return getCommandCategoryColorVars(command.category);
		}
		return getCommandColorVars(command.source ?? 'unknown', command.plugin);
	}

	function getBadgeLabel(command: CommandUsage): string {
		if (command.category) {
			return getCommandCategoryLabel(command.category);
		}
		switch (command.source) {
			case 'builtin':
				return 'Built-in';
			case 'plugin':
				return 'Plugin';
			case 'project':
				return 'Project';
			case 'user':
				return 'User';
			default:
				return 'Unknown';
		}
	}
</script>

<div class="space-y-4">
	<div>
		<h2 class="text-lg font-semibold text-[var(--text-primary)]">
			Commands ({commands.length})
		</h2>
		<p class="text-sm text-[var(--text-muted)]">Slash commands invoked during this session</p>
	</div>

	{#if sortedCommands.length > 0}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each sortedCommands as command (command.name)}
				{@const cmdColors = getCommandColors(command)}
				{@const Icon = isPluginCommand(command) ? Zap : TerminalSquare}
				{@const isClickable = !isBuiltinCommand(command)}

				<a
					href="/commands/{encodeURIComponent(command.name)}"
					class="group flex items-start gap-4 p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-xl transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 text-left no-underline {isClickable
						? 'cursor-pointer hover:border-[var(--accent)]/50 hover:shadow-sm'
						: 'cursor-default opacity-75'}"
				>
					<div
						class="p-2.5 rounded-lg shrink-0 transition-colors"
						style="background-color: {cmdColors.subtle}; color: {cmdColors.color};"
					>
						<Icon size={20} />
					</div>

					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<span
								class="font-medium text-[var(--text-primary)] truncate"
								title={command.name}
							>
								/{isPluginCommand(command)
									? cleanSkillName(command.name, true)
									: command.name}
							</span>
						</div>
						<div class="flex items-center gap-2 text-xs text-[var(--text-muted)] mt-1">
							<span
								class="px-1.5 py-0.5 rounded text-[10px] uppercase font-medium"
								style="background-color: {cmdColors.subtle}; color: {cmdColors.color};"
							>
								{getBadgeLabel(command)}
							</span>
							{#if command.plugin}
								<span class="text-[var(--text-faint)]">{command.plugin}</span>
							{/if}
						</div>
					</div>

					<div
						class="shrink-0 px-2.5 py-1 rounded-full text-xs font-medium"
						style="background-color: {cmdColors.subtle}; color: {cmdColors.color};"
					>
						{command.count}x
					</div>
				</a>
			{/each}
		</div>
	{:else}
		<EmptyState
			icon={TerminalSquare}
			title="No commands used"
			description="Slash commands invoked during this session will appear here"
		/>
	{/if}
</div>
