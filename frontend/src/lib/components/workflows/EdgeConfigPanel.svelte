<script lang="ts">
	import { Trash2 } from 'lucide-svelte';
	import type { Edge } from '@xyflow/svelte';

	let {
		edge = $bindable(),
		ondelete
	}: {
		edge: Edge;
		ondelete: () => void;
	} = $props();

	let condition = $state(edge.data?.condition ?? '');

	// Re-sync local state when the bound edge prop changes (e.g. different edge selected)
	$effect(() => {
		condition = edge.data?.condition ?? '';
	});

	function updateCondition() {
		edge = {
			...edge,
			data: { ...edge.data, condition: condition || null }
		};
	}
</script>

<div class="config-panel">
	<div class="panel-header">
		<h3>Edge Config</h3>
		<button class="delete-btn" onclick={ondelete} aria-label="Delete edge">
			<Trash2 size={14} />
			<span>Delete</span>
		</button>
	</div>

	<div class="field">
		<span class="field-label">Connection</span>
		<span class="field-value">{edge.source} &rarr; {edge.target}</span>
	</div>

	<label class="field">
		<span class="field-label">Condition (optional)</span>
		<textarea
			bind:value={condition}
			oninput={updateCondition}
			rows="3"
			class="field-input field-textarea"
			placeholder="e.g. {'{{ steps.step_1.output }}'} == success"
		></textarea>
		<span class="field-hint">
			Leave empty for unconditional execution. Supports <code>==</code> and <code>!=</code> operators.
		</span>
	</label>
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

	.field-hint {
		display: block;
		font-size: 11px;
		color: var(--text-faint);
		margin-top: 4px;
	}
</style>
