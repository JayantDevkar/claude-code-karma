<script lang="ts">
	import { browser } from '$app/environment';
	import {
		Check,
		FolderPlus,
		UserPlus,
		ArrowRightLeft,
		X,
		ChevronRight
	} from 'lucide-svelte';

	interface Props {
		memberCount: number;
		projectCount: number;
		isLeader: boolean;
		teamName: string;
		onShareProject: () => void;
		onAddMember: () => void;
	}

	let {
		memberCount,
		projectCount,
		isLeader,
		teamName,
		onShareProject,
		onAddMember
	}: Props = $props();

	// Dismiss persistence
	let dismissed = $state(false);
	const storageKey = $derived(`karma-getting-started-dismissed-${teamName}`);

	$effect(() => {
		if (browser) {
			dismissed = localStorage.getItem(storageKey) === 'true';
		}
	});

	function dismiss() {
		dismissed = true;
		if (browser) localStorage.setItem(storageKey, 'true');
	}

	// Step completion
	let projectsDone = $derived(projectCount > 0);
	let membersDone = $derived(memberCount > 0);
	let allDone = $derived(projectsDone && membersDone);

	// Determine which step is "active" (first incomplete)
	let activeStep = $derived.by(() => {
		if (!projectsDone) return 1;
		if (!membersDone) return 2;
		return 3;
	});

	// Should we render at all?
	let visible = $derived(isLeader && !allDone && !dismissed);

	type StepState = 'done' | 'active' | 'future';

	function stepState(step: number): StepState {
		if (step === 1 && projectsDone) return 'done';
		if (step === 2 && membersDone) return 'done';
		if (step === activeStep) return 'active';
		if (step < activeStep) return 'done';
		return 'future';
	}

	// Pre-compute step states as reactive derivations
	let s1 = $derived(stepState(1));
	let s2 = $derived(stepState(2));
	let s3 = $derived(stepState(3));
</script>

{#if visible}
	<aside
		aria-label="Team setup guide"
		class="getting-started-banner"
	>
		<!-- Header row -->
		<div class="banner-header">
			<div class="header-label">
				<span class="label-dot"></span>
				<span class="label-text">Getting Started</span>
			</div>
			<button
				onclick={dismiss}
				class="dismiss-btn"
				aria-label="Dismiss getting started guide"
			>
				<X size={14} />
			</button>
		</div>

		<!-- Steps -->
		<div class="steps-container">
			<!-- Step 1: Share a project -->
			<div class="step" data-state={s1}>
				<div class="step-rail">
					<div class="step-circle" data-state={s1}>
						{#if s1 === 'done'}
							<Check size={13} strokeWidth={2.5} />
						{:else}
							<FolderPlus size={13} />
						{/if}
					</div>
					<div class="step-line" data-state={stepState(2)}></div>
				</div>
				<div class="step-body">
					<div class="step-title" data-state={s1}>Share a project</div>
					<p class="step-desc">Pick which repos to sync with this team</p>
					{#if s1 === 'done'}
						<span class="step-done-badge">
							<Check size={11} strokeWidth={2.5} />
							Done
						</span>
					{:else if s1 === 'active'}
						<button onclick={onShareProject} class="step-action-btn">
							Add Project
							<ChevronRight size={13} />
						</button>
					{/if}
				</div>
			</div>

			<!-- Step 2: Add team members -->
			<div class="step" data-state={s2}>
				<div class="step-rail">
					<div class="step-circle" data-state={s2}>
						{#if s2 === 'done'}
							<Check size={13} strokeWidth={2.5} />
						{:else}
							<UserPlus size={13} />
						{/if}
					</div>
					<div class="step-line" data-state={stepState(3)}></div>
				</div>
				<div class="step-body">
					<div class="step-title" data-state={s2}>Add team members</div>
					<p class="step-desc">Paste their pairing code to connect</p>
					{#if s2 === 'done'}
						<span class="step-done-badge">
							<Check size={11} strokeWidth={2.5} />
							Done
						</span>
					{:else if s2 === 'active'}
						<button onclick={onAddMember} class="step-action-btn">
							Add Member
							<ChevronRight size={13} />
						</button>
					{/if}
				</div>
			</div>

			<!-- Step 3: They accept & sync -->
			<div class="step" data-state={s3}>
				<div class="step-rail">
					<div class="step-circle" data-state={s3}>
						{#if s3 === 'done'}
							<Check size={13} strokeWidth={2.5} />
						{:else}
							<ArrowRightLeft size={13} />
						{/if}
					</div>
				</div>
				<div class="step-body">
					<div class="step-title" data-state={s3}>They accept & start syncing</div>
					<p class="step-desc">Members choose their sync direction: send, receive, or both</p>
				</div>
			</div>
		</div>
	</aside>
{/if}

<style>
	/* Banner container */
	.getting-started-banner {
		position: relative;
		padding: 20px 20px 16px;
		border-radius: var(--radius-lg);
		border: 1px solid var(--border);
		background:
			linear-gradient(
				135deg,
				rgba(var(--accent-rgb), 0.03) 0%,
				transparent 60%
			),
			var(--bg-subtle);
	}

	/* Header */
	.banner-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 16px;
	}

	.header-label {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.label-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 6px rgba(var(--accent-rgb), 0.4);
	}

	.label-text {
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.dismiss-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		border-radius: var(--radius-sm);
		color: var(--text-muted);
		background: transparent;
		border: none;
		cursor: pointer;
		transition: all var(--duration-fast) ease;
	}
	.dismiss-btn:hover {
		background: var(--bg-muted);
		color: var(--text-secondary);
	}

	/* Steps layout */
	.steps-container {
		display: flex;
		flex-direction: column;
	}

	.step {
		display: flex;
		gap: 14px;
		position: relative;
	}

	/* Rail: circle + connecting line */
	.step-rail {
		display: flex;
		flex-direction: column;
		align-items: center;
		flex-shrink: 0;
	}

	.step-circle {
		width: 28px;
		height: 28px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		transition: all var(--duration-base) ease;
	}
	.step-circle[data-state='done'] {
		background: var(--success);
		color: white;
	}
	.step-circle[data-state='active'] {
		background: var(--accent);
		color: white;
		box-shadow: 0 0 0 3px rgba(var(--accent-rgb), 0.15);
	}
	.step-circle[data-state='future'] {
		background: var(--bg-muted);
		color: var(--text-muted);
		border: 1px solid var(--border);
	}

	.step-line {
		width: 2px;
		flex: 1;
		min-height: 12px;
		margin: 4px 0;
		border-radius: 1px;
		transition: background var(--duration-base) ease;
	}
	.step-line[data-state='done'] {
		background: var(--success);
		opacity: 0.5;
	}
	.step-line[data-state='active'] {
		background: var(--accent);
		opacity: 0.35;
	}
	.step-line[data-state='future'] {
		background: var(--border);
	}

	/* Step body */
	.step-body {
		padding-bottom: 16px;
		min-height: 52px;
	}
	.step:last-child .step-body {
		padding-bottom: 0;
	}

	.step-title {
		font-size: 13px;
		font-weight: 600;
		line-height: 28px; /* match circle height for alignment */
		transition: color var(--duration-fast) ease;
	}
	.step-title[data-state='done'] {
		color: var(--success);
	}
	.step-title[data-state='active'] {
		color: var(--text-primary);
	}
	.step-title[data-state='future'] {
		color: var(--text-muted);
	}

	.step-desc {
		font-size: 12px;
		color: var(--text-muted);
		line-height: 1.5;
		margin: 2px 0 0;
	}

	/* Done badge */
	.step-done-badge {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		margin-top: 6px;
		font-size: 11px;
		font-weight: 500;
		color: var(--success);
	}

	/* Action button */
	.step-action-btn {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		margin-top: 8px;
		padding: 5px 12px;
		font-size: 12px;
		font-weight: 500;
		color: white;
		background: var(--accent);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: all var(--duration-fast) ease;
	}
	.step-action-btn:hover {
		background: var(--accent-hover);
	}

	/* Reduced motion */
	@media (prefers-reduced-motion: reduce) {
		.step-circle,
		.step-line,
		.step-title,
		.step-action-btn,
		.dismiss-btn {
			transition: none;
		}
	}
</style>
