<script lang="ts">
	import { toasts, dismissToast } from '$lib/stores/toast.svelte';
	import { X, CheckCircle2, AlertCircle, Info } from 'lucide-svelte';
</script>

{#if toasts.list.length > 0}
	<div class="toast-container" aria-live="polite">
		{#each toasts.list as toast (toast.id)}
			<div class="toast toast-{toast.type}" role="alert">
				<span class="toast-icon">
					{#if toast.type === 'success'}
						<CheckCircle2 size={16} />
					{:else if toast.type === 'error'}
						<AlertCircle size={16} />
					{:else}
						<Info size={16} />
					{/if}
				</span>
				<span class="toast-message">{toast.message}</span>
				<button
					class="toast-close"
					onclick={() => dismissToast(toast.id)}
					aria-label="Dismiss notification"
				>
					<X size={14} />
				</button>
			</div>
		{/each}
	</div>
{/if}

<style>
	.toast-container {
		position: fixed;
		bottom: 16px;
		right: 16px;
		z-index: 9999;
		display: flex;
		flex-direction: column;
		gap: 8px;
		max-width: 400px;
	}

	.toast {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 14px;
		border-radius: var(--radius-md, 6px);
		border: 1px solid var(--border);
		background: var(--bg-subtle);
		color: var(--text-primary);
		font-size: 13px;
		box-shadow: var(--shadow-elevated, 0 4px 12px rgba(0, 0, 0, 0.15));
		animation: toast-in 0.25s var(--ease, cubic-bezier(0.25, 1, 0.5, 1));
	}

	.toast-success {
		border-color: var(--success, #10b981);
	}
	.toast-success .toast-icon {
		color: var(--success, #10b981);
	}

	.toast-error {
		border-color: var(--error, #ef4444);
	}
	.toast-error .toast-icon {
		color: var(--error, #ef4444);
	}

	.toast-info {
		border-color: var(--info, #3b82f6);
	}
	.toast-info .toast-icon {
		color: var(--info, #3b82f6);
	}

	.toast-icon {
		flex-shrink: 0;
		display: flex;
	}

	.toast-message {
		flex: 1;
		line-height: 1.4;
	}

	.toast-close {
		flex-shrink: 0;
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		padding: 2px;
		border-radius: 4px;
		display: flex;
		transition: color 0.15s;
	}
	.toast-close:hover {
		color: var(--text-primary);
	}

	@keyframes toast-in {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
