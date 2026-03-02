<script lang="ts">
	import type { WorkflowStep } from '$lib/api-types';

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
		<button class="delete-btn" onclick={ondelete}>Delete</button>
	</div>

	<label class="field">
		<span class="field-label">Name</span>
		<span class="field-value">{step.id}</span>
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
		font-size: 12px;
		color: #ef4444;
		background: none;
		border: none;
		cursor: pointer;
		padding: 2px 4px;
		border-radius: 4px;
		transition: color 0.15s ease;
	}

	.delete-btn:hover {
		color: #f87171;
	}

	.field {
		display: block;
		margin-bottom: 12px;
	}

	.field-label {
		display: block;
		font-size: 11px;
		color: var(--text-muted);
		margin-bottom: 4px;
	}

	.field-value {
		font-family: monospace;
		font-size: 0.85rem;
		color: var(--text-secondary, #888);
		padding: 0.25rem 0;
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
