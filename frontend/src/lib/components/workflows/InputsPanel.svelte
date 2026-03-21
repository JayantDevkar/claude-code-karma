<script lang="ts">
	import type { WorkflowInput } from '$lib/api-types';
	import { Plus, Trash2, X } from 'lucide-svelte';

	let {
		inputs = $bindable(),
		onclose
	}: {
		inputs: WorkflowInput[];
		onclose: () => void;
	} = $props();

	function addInput() {
		inputs = [
			...inputs,
			{
				name: `input_${inputs.length + 1}`,
				type: 'string',
				required: true,
				default: null,
				description: null
			}
		];
	}

	function removeInput(index: number) {
		inputs = inputs.filter((_, i) => i !== index);
	}

	function updateInput(index: number, field: keyof WorkflowInput, value: unknown) {
		inputs = inputs.map((inp, i) => (i === index ? { ...inp, [field]: value } : inp));
	}
</script>

<div class="inputs-panel">
	<div class="panel-header">
		<h3>Workflow Inputs</h3>
		<div class="header-actions">
			<button class="add-btn" onclick={addInput}>
				<Plus size={14} />
				<span>Add</span>
			</button>
			<button class="close-btn" onclick={onclose} aria-label="Close inputs panel">
				<X size={16} />
			</button>
		</div>
	</div>

	{#if inputs.length === 0}
		<div class="empty">
			<p class="empty-text">No inputs defined.</p>
			<p class="empty-hint">
				Inputs let you parameterize workflows. Reference them in prompts with
				<code>{'{{ inputs.name }}'}</code>
			</p>
		</div>
	{:else}
		<div class="input-list">
			{#each inputs as inp, i (inp.name || i)}
				<div class="input-card">
					<div class="input-row">
						<label class="field field-name">
							<span class="field-label">Name</span>
							<input
								type="text"
								value={inp.name}
								oninput={(e) => updateInput(i, 'name', e.currentTarget.value)}
								class="field-input"
								placeholder="my_input"
							/>
						</label>
						<label class="field field-type">
							<span class="field-label">Type</span>
							<select
								value={inp.type}
								onchange={(e) => updateInput(i, 'type', e.currentTarget.value)}
								class="field-input"
							>
								<option value="string">string</option>
								<option value="number">number</option>
								<option value="boolean">boolean</option>
							</select>
						</label>
						<button
							class="remove-btn"
							onclick={() => removeInput(i)}
							aria-label="Remove input"
						>
							<Trash2 size={14} />
						</button>
					</div>
					<div class="input-row">
						<label class="field field-grow">
							<span class="field-label">Description</span>
							<input
								type="text"
								value={inp.description || ''}
								oninput={(e) =>
									updateInput(i, 'description', e.currentTarget.value || null)}
								class="field-input"
								placeholder="What this input is for..."
							/>
						</label>
					</div>
					<div class="input-row">
						<label class="field field-default">
							<span class="field-label">Default</span>
							<input
								type="text"
								value={inp.default || ''}
								oninput={(e) =>
									updateInput(i, 'default', e.currentTarget.value || null)}
								class="field-input"
								placeholder="(none)"
							/>
						</label>
						<label class="field-inline">
							<input
								type="checkbox"
								checked={inp.required}
								onchange={(e) => updateInput(i, 'required', e.currentTarget.checked)}
							/>
							<span class="field-label-inline">Required</span>
						</label>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.inputs-panel {
		padding: 16px;
		border-left: 1px solid var(--border);
		background: var(--bg-subtle);
		width: 380px;
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

	.header-actions {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.add-btn {
		display: flex;
		align-items: center;
		gap: 4px;
		font-size: 12px;
		padding: 4px 10px;
		border-radius: 4px;
		border: 1px solid var(--accent);
		background: var(--accent);
		color: white;
		cursor: pointer;
		transition: opacity 0.15s;
	}
	.add-btn:hover {
		opacity: 0.9;
	}

	.close-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		padding: 2px;
		border-radius: 4px;
		display: flex;
	}
	.close-btn:hover {
		color: var(--text-primary);
	}

	.empty {
		text-align: center;
		padding: 24px 0;
	}
	.empty-text {
		font-size: 13px;
		color: var(--text-muted);
		margin: 0 0 4px;
	}
	.empty-hint {
		font-size: 12px;
		color: var(--text-faint);
		margin: 0;
	}
	.empty-hint code {
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		background: var(--bg-muted);
		padding: 1px 4px;
		border-radius: 3px;
	}

	.input-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.input-card {
		padding: 10px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-base);
	}

	.input-row {
		display: flex;
		gap: 8px;
		align-items: flex-end;
		margin-bottom: 8px;
	}
	.input-row:last-child {
		margin-bottom: 0;
	}

	.field {
		display: flex;
		flex-direction: column;
	}
	.field-name {
		flex: 1;
	}
	.field-type {
		width: 90px;
	}
	.field-grow {
		flex: 1;
	}
	.field-default {
		flex: 1;
	}

	.field-label {
		font-size: 10px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-bottom: 3px;
	}

	.field-input {
		padding: 5px 8px;
		border-radius: 4px;
		border: 1px solid var(--border);
		background: var(--bg-subtle);
		font-size: 12px;
		color: var(--text-primary);
		box-sizing: border-box;
		width: 100%;
	}
	.field-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.field-inline {
		display: flex;
		align-items: center;
		gap: 6px;
		padding-bottom: 2px;
		white-space: nowrap;
	}
	.field-inline input[type='checkbox'] {
		accent-color: var(--accent);
	}
	.field-label-inline {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.remove-btn {
		background: none;
		border: none;
		color: var(--text-faint);
		cursor: pointer;
		padding: 4px;
		border-radius: 4px;
		display: flex;
		align-self: flex-end;
		margin-bottom: 2px;
		transition: color 0.15s;
	}
	.remove-btn:hover {
		color: var(--error, #ef4444);
	}
</style>
