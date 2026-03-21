<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import type { WorkflowInput } from '$lib/api-types';
	import { Play } from 'lucide-svelte';

	let {
		open = $bindable(false),
		inputs,
		onrun
	}: {
		open: boolean;
		inputs: WorkflowInput[];
		onrun: (inputValues: Record<string, unknown>) => void;
	} = $props();

	let values = $state<Record<string, string>>({});

	// Initialize defaults when modal opens
	$effect(() => {
		if (open) {
			const defaults: Record<string, string> = {};
			for (const inp of inputs) {
				defaults[inp.name] = inp.default || '';
			}
			values = defaults;
		}
	});

	function handleSubmit() {
		// Convert types
		const result: Record<string, unknown> = {};
		for (const inp of inputs) {
			const raw = values[inp.name] ?? '';
			if (inp.type === 'number') {
				result[inp.name] = raw ? Number(raw) : null;
			} else if (inp.type === 'boolean') {
				result[inp.name] = raw === 'true' || raw === '1';
			} else {
				result[inp.name] = raw || null;
			}
		}
		onrun(result);
		open = false;
	}

	let hasRequiredEmpty = $derived(
		inputs.some((inp) => inp.required && !values[inp.name]?.trim())
	);
</script>

<Modal {open} onOpenChange={(v) => (open = v)} title="Run Workflow">
	{#snippet children()}
		<div class="run-form">
			{#if inputs.length === 0}
				<p class="no-inputs">This workflow has no inputs. Click Run to execute.</p>
			{:else}
				<p class="form-hint">Provide values for the workflow inputs:</p>
				{#each inputs as inp (inp.name)}
					<label class="field">
						<span class="field-label">
							{inp.name}
							{#if inp.required}<span class="required">*</span>{/if}
						</span>
						{#if inp.description}
							<span class="field-desc">{inp.description}</span>
						{/if}
						{#if inp.type === 'boolean'}
							<select
								bind:value={values[inp.name]}
								class="field-input"
							>
								<option value="">-- select --</option>
								<option value="true">true</option>
								<option value="false">false</option>
							</select>
						{:else}
							<input
								type={inp.type === 'number' ? 'number' : 'text'}
								bind:value={values[inp.name]}
								class="field-input"
								placeholder={inp.default ? `Default: ${inp.default}` : ''}
							/>
						{/if}
					</label>
				{/each}
			{/if}
		</div>
	{/snippet}
	{#snippet footer()}
		<div class="modal-footer">
			<button class="btn-cancel" onclick={() => (open = false)}>Cancel</button>
			<button class="btn-run" onclick={handleSubmit} disabled={hasRequiredEmpty}>
				<Play size={14} />
				Run
			</button>
		</div>
	{/snippet}
</Modal>

<style>
	.run-form {
		padding: 4px 0;
	}

	.no-inputs {
		font-size: 13px;
		color: var(--text-secondary);
		margin: 0;
	}

	.form-hint {
		font-size: 13px;
		color: var(--text-muted);
		margin: 0 0 12px;
	}

	.field {
		display: block;
		margin-bottom: 12px;
	}

	.field-label {
		display: block;
		font-size: 12px;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 4px;
	}

	.required {
		color: var(--error, #ef4444);
	}

	.field-desc {
		display: block;
		font-size: 11px;
		color: var(--text-muted);
		margin-bottom: 4px;
	}

	.field-input {
		width: 100%;
		padding: 7px 12px;
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

	.modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
	}

	.btn-cancel {
		padding: 6px 14px;
		border-radius: 4px;
		border: 1px solid var(--border);
		background: var(--bg-base);
		color: var(--text-secondary);
		font-size: 13px;
		cursor: pointer;
		transition: border-color 0.15s;
	}
	.btn-cancel:hover {
		border-color: var(--border-hover);
	}

	.btn-run {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 16px;
		border-radius: 4px;
		border: none;
		background: #10b981;
		color: white;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: opacity 0.15s;
	}
	.btn-run:hover {
		opacity: 0.9;
	}
	.btn-run:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
