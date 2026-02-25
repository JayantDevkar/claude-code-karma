<script lang="ts">
	import { CheckCircle2, Circle, Loader2 } from 'lucide-svelte';
	import type { TaskStatus } from '$lib/api-types';

	interface Props {
		status: TaskStatus;
		isBlocked?: boolean;
		size?: number;
	}

	let { status, isBlocked = false, size = 18 }: Props = $props();
</script>

{#if status === 'completed'}
	<CheckCircle2 {size} class="text-[var(--success)]" />
{:else if status === 'in_progress'}
	<Loader2 {size} class="text-[var(--nav-blue)] animate-spin" />
{:else if isBlocked}
	<Circle {size} class="text-[var(--text-muted)]/50" />
{:else}
	<Circle {size} class="text-[var(--text-muted)]" />
{/if}
