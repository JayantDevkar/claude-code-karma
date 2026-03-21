<script lang="ts">
	import type { WorkflowStep } from '$lib/api-types';
	import { Trash2 } from 'lucide-svelte';

	let {
		step = $bindable(),
		ondelete
	}: {
		step: WorkflowStep;
		ondelete: () => void;
	} = $props();

	const availableTools = [
		'Read',
		'Edit',
		'Write',
		'Bash',
		'Glob',
		'Grep',
		'WebFetch',
		'WebSearch'
	];

	function toggleTool(tool: string) {
		if (step.tools.includes(tool)) {
			step = { ...step, tools: step.tools.filter((t) => t !== tool) };
		} else {
			step = { ...step, tools: [...step.tools, tool] };
		}
	}
</script>

<div class="config-panel">
	<div class="panel-header">
		<h3>Step Config</h3>
		<button class="delete-btn" onclick={ondelete} aria-label="Delete step">
			<Trash2 size={14} />
			<span>Delete</span>
		</button>
	</div>

	<div class="field">
		<span class="field-label">ID</span>
		<span class="field-value">{step.id}</span>
	</div>

	<label class="field">
		<span class="field-label">Label</span>
		<input
			type="text"
			value={step.label || ''}
			oninput={(e) => (step = { ...step, label: e.currentTarget.value || null })}
			class="field-input"
			placeholder="e.g. Analyze Code, Write Tests..."
		/>
	</label>

	<label class="field">
		<span class="field-label">Model</span>
		<select bind:value={step.model} class="field-input">
			<option value="haiku">haiku</option>
			<option value="sonnet">sonnet</option>
			<option value="opus">opus</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Prompt Template</span>
		<textarea
			bind:value={step.prompt_template}
			rows="6"
			class="field-input field-textarea"
			placeholder="Use {'{{'}  inputs.name {'}}'}  or {'{{'}  steps.prev.output {'}}'}"
		></textarea>
	</label>

	<label class="field">
		<span class="field-label">Max Turns</span>
		<input type="number" bind:value={step.max_turns} min="1" max="100" class="field-input" />
	</label>

	<div class="field">
		<span class="field-label">Tools</span>
		<div class="tools-grid">
			{#each availableTools as tool}
				<button
					onclick={() => toggleTool(tool)}
					class="tool-chip"
					class:tool-active={step.tools.includes(tool)}
					aria-pressed={step.tools.includes(tool)}
				>
					{tool}
				</button>
			{/each}
		</div>
	</div>
</div>

<style>
	.config-panel {
		padding: 16px;
		border-left: 1px solid var(--border);
		background: var(--bg-subtle);
		width: 320px;
		overflow-y: auto;
	}

	.panel-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 16px;
	}

	.panel-header h3 {
		font-weight: 600;
		font-size: 14px;
		color: var(--text-primary);
		margin: 0;
	}

	.delete-btn {
		display: flex;
		align-items: center;
		gap: 4px;
		font-size: 12px;
		color: var(--error, #ef4444);
		background: none;
		border: 1px solid transparent;
		cursor: pointer;
		padding: 4px 8px;
		border-radius: 4px;
		transition:
			background 0.15s ease,
			border-color 0.15s ease;
	}

	.delete-btn:hover {
		background: var(--error-subtle, rgba(239, 68, 68, 0.1));
		border-color: var(--error, #ef4444);
	}

	.field {
		display: block;
		margin-bottom: 12px;
	}

	.field-label {
		display: block;
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-bottom: 4px;
	}

	.field-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		color: var(--text-secondary);
		padding: 4px 0;
	}

	.field-input {
		width: 100%;
		padding: 6px 12px;
		border-radius: 4px;
		border: 1px solid var(--border);
		background: var(--bg-base);
		font-size: 13px;
		color: var(--text-primary);
		box-sizing: border-box;
	}

	.field-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.field-textarea {
		font-family: 'JetBrains Mono', monospace;
		resize: vertical;
	}

	.tools-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.tool-chip {
		font-size: 11px;
		padding: 4px 8px;
		border-radius: 4px;
		border: 1px solid var(--border);
		color: var(--text-secondary);
		background: none;
		cursor: pointer;
		transition:
			border-color 0.15s ease,
			background 0.15s ease,
			color 0.15s ease;
	}

	.tool-chip:hover {
		border-color: var(--accent);
	}

	.tool-active {
		background: var(--accent);
		color: white;
		border-color: var(--accent);
	}
</style>
