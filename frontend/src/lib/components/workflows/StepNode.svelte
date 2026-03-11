<script lang="ts">
	import { Handle, Position, type NodeProps } from '@xyflow/svelte';
	import { FileText, Terminal, Search, Globe, PenLine } from 'lucide-svelte';

	let { data }: NodeProps = $props();

	const modelColors: Record<string, { bg: string; text: string; border: string }> = {
		sonnet: { bg: 'rgba(139, 92, 246, 0.15)', text: '#a78bfa', border: '#8b5cf6' },
		opus: { bg: 'rgba(245, 158, 11, 0.15)', text: '#fbbf24', border: '#f59e0b' },
		haiku: { bg: 'rgba(16, 185, 129, 0.15)', text: '#34d399', border: '#10b981' }
	};

	let colors = $derived(modelColors[data.model as string] ?? modelColors.sonnet);
	let displayLabel = $derived((data.label as string) || (data.id as string));
	let promptPreview = $derived.by(() => {
		const tmpl = data.prompt_template as string;
		if (!tmpl) return '';
		const cleaned = tmpl.replace(/\{\{.*?\}\}/g, '...').trim();
		return cleaned.length > 50 ? cleaned.slice(0, 47) + '...' : cleaned;
	});

	let primaryTool = $derived.by(() => {
		const tools = (data.tools as string[]) || [];
		if (tools.includes('Bash')) return 'terminal';
		if (tools.includes('WebFetch') || tools.includes('WebSearch')) return 'globe';
		if (tools.includes('Grep') || tools.includes('Glob')) return 'search';
		if (tools.includes('Edit') || tools.includes('Write')) return 'edit';
		return 'file';
	});
</script>

<Handle type="target" position={Position.Top} />

<div class="step-node">
	<div class="node-icon">
		{#if primaryTool === 'terminal'}
			<Terminal size={14} />
		{:else if primaryTool === 'globe'}
			<Globe size={14} />
		{:else if primaryTool === 'search'}
			<Search size={14} />
		{:else if primaryTool === 'edit'}
			<PenLine size={14} />
		{:else}
			<FileText size={14} />
		{/if}
	</div>
	<div class="node-content">
		<div class="node-label">{displayLabel}</div>
		{#if promptPreview}
			<div class="node-preview">{promptPreview}</div>
		{/if}
	</div>
	{#if data.model}
		<span
			class="model-badge"
			style="background: {colors.bg}; color: {colors.text}; border-color: {colors.border};"
		>
			{data.model}
		</span>
	{/if}
</div>

<Handle type="source" position={Position.Bottom} />

<style>
	.step-node {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 10px 14px;
		min-width: 180px;
		max-width: 260px;
		display: flex;
		align-items: flex-start;
		gap: 10px;
		font-size: 13px;
		color: var(--text-primary);
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
		transition: border-color 0.15s ease;
	}

	.step-node:hover {
		border-color: var(--accent);
	}

	.node-icon {
		flex-shrink: 0;
		color: var(--text-muted);
		margin-top: 1px;
	}

	.node-content {
		flex: 1;
		min-width: 0;
	}

	.node-label {
		font-weight: 600;
		font-size: 13px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.node-preview {
		font-size: 11px;
		color: var(--text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		margin-top: 2px;
	}

	.model-badge {
		font-size: 9px;
		padding: 2px 6px;
		border-radius: 4px;
		border: 1px solid;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		flex-shrink: 0;
		margin-top: 1px;
	}
</style>
