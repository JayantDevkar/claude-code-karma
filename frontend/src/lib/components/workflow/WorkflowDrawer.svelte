<script lang="ts">
	import { format } from 'date-fns';
	import {
		X,
		Quote,
		CornerUpLeft,
		GitCommitHorizontal,
		GitPullRequest,
		MessageSquare,
		Brain,
		FileCode2,
		ExternalLink
	} from 'lucide-svelte';
	import type { WorkflowNode } from './types';
	import { metaFor, TIER_NAMES } from './kinds';
	import NodeGlyph from './NodeGlyph.svelte';

	interface Props {
		node: WorkflowNode | null;
		projectEncodedName: string;
		onclose: () => void;
		onselectid: (id: string) => void;
	}

	let { node, projectEncodedName, onclose, onselectid }: Props = $props();

	const meta = $derived(node ? metaFor(node.kind) : null);

	function sessionHref(sessionId: string): string {
		return `/projects/${projectEncodedName}/${sessionId.slice(0, 12)}`;
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && node) onclose();
	}
</script>

<svelte:window on:keydown={onKeydown} />

<aside class="wf-drawer {node ? 'is-open' : ''}" aria-hidden={!node}>
	{#if node && meta}
		<div class="flex h-full flex-col">
			<!-- header / title section -->
			<div class="border-b border-[var(--border)] p-4">
				<div class="flex items-start gap-3">
					<NodeGlyph kind={node.kind} size={32} />
					<div class="min-w-0 flex-1">
						<div class="flex flex-wrap items-center gap-1.5">
							<span
								class="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
								style="color: {meta.color}; background: color-mix(in srgb, {meta.color} 15%, transparent)"
							>
								{meta.word}
							</span>
							<span
								class="text-[10px] uppercase tracking-wider text-[var(--text-faint)]"
							>
								{TIER_NAMES[node.tier - 1]}
							</span>
							{#if node.status === 'superseded'}
								<span
									class="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]"
								>
									superseded
								</span>
							{/if}
						</div>
						<div
							class="mt-1 font-mono text-sm font-semibold text-[var(--text-primary)]"
						>
							{node.label}
						</div>
						<div class="text-xs text-[var(--text-muted)]">
							{format(new Date(node.date), 'MMM d, yyyy · HH:mm')} ·
							{#if node.decided_by === 'human'}you decided{:else if node.decided_by === 'ai'}AI
								decided{:else}decided together{/if}
						</div>
					</div>
					<button
						class="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)]"
						onclick={onclose}
						aria-label="Close"
					>
						<X class="h-4 w-4" />
					</button>
				</div>

				<!-- Session — surfaced up here as a primary reference -->
				<div class="mt-3">
					{#if node.session_id}
						<a
							href={sessionHref(node.session_id)}
							class="inline-flex max-w-full items-center gap-1.5 rounded-md border border-[var(--accent)] bg-[var(--accent-subtle)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)] transition-colors hover:bg-[var(--accent-muted)]"
						>
							<MessageSquare class="h-3.5 w-3.5 shrink-0" />
							<span class="truncate">{node.session_title}</span>
						</a>
					{:else if node.session_title}
						<span
							class="inline-flex max-w-full items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-muted)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)]"
						>
							<MessageSquare class="h-3.5 w-3.5 shrink-0" />
							<span class="truncate">{node.session_title}</span>
						</span>
					{/if}
				</div>
			</div>

			<!-- body -->
			<div class="flex-1 space-y-5 overflow-y-auto p-4 text-sm">
				<h2 class="text-base font-semibold leading-snug text-[var(--text-primary)]">
					{node.title}
				</h2>

				<section>
					<h3 class="wf-label">Intent</h3>
					<p class="text-[var(--text-primary)]">{node.intent}</p>
				</section>

				{#if node.options && node.options.length > 0}
					<section>
						<h3 class="wf-label">Options weighed</h3>
						<ul class="space-y-1 text-[var(--text-secondary)]">
							{#each node.options as option (option)}
								<li class="flex gap-1.5">
									<span aria-hidden="true" class="text-[var(--text-faint)]"
										>·</span
									>{option}
								</li>
							{/each}
						</ul>
					</section>
				{/if}

				<section>
					<h3 class="wf-label">Decision</h3>
					<p
						class="rounded-md border-l-[3px] border-[var(--accent)] bg-[var(--accent-subtle)] px-3 py-2.5 font-medium text-[var(--text-primary)]"
					>
						{node.chosen}
					</p>
				</section>

				{#if node.why_quoted}
					<section>
						<h3 class="wf-label">Why — in your words</h3>
						<blockquote
							class="flex gap-2 rounded-md border-l-2 border-[var(--accent)] bg-[var(--bg-muted)] px-3 py-2 italic text-[var(--text-secondary)]"
						>
							<Quote class="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
							<span>{node.why_quoted}</span>
						</blockquote>
					</section>
				{:else if node.why_inferred}
					<section>
						<h3 class="wf-label">Why</h3>
						<p class="text-[13px] italic text-[var(--text-muted)]">
							<span class="font-semibold not-italic text-[var(--text-secondary)]"
								>inferred rationale:</span
							>
							{node.why_inferred}
						</p>
					</section>
				{/if}

				{#if node.supersedes}
					<button
						class="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] px-2.5 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]"
						onclick={() => onselectid(node.supersedes!)}
					>
						<CornerUpLeft class="h-3 w-3" />
						supersedes {node.supersedes_label ?? ''} — {node.supersedes_title ??
							node.supersedes}
					</button>
				{/if}

				{#if node.evidence.length > 0}
					<section class="border-t border-[var(--border)] pt-3">
						<h3 class="wf-label">Evidence</h3>
						<div class="flex flex-wrap gap-1.5">
							{#each node.evidence as ev (ev.label)}
								{#if ev.type === 'session' && ev.session_id}
									<a
										href={sessionHref(ev.session_id)}
										class="inline-flex items-center gap-1 rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs text-[var(--text-secondary)] hover:text-[var(--accent)]"
									>
										<MessageSquare class="h-3 w-3" />{ev.label}
									</a>
								{:else if ev.url}
									<a
										href={ev.url}
										target="_blank"
										rel="noopener noreferrer"
										class="inline-flex items-center gap-1 rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs text-[var(--text-secondary)] hover:text-[var(--accent)]"
									>
										{#if ev.type === 'pr'}<GitPullRequest
												class="h-3 w-3"
											/>{:else}<ExternalLink class="h-3 w-3" />{/if}{ev.label}
									</a>
								{:else}
									<span
										class="inline-flex items-center gap-1 rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs text-[var(--text-muted)]"
									>
										{#if ev.type === 'commit'}<GitCommitHorizontal
												class="h-3 w-3"
											/>{:else if ev.type === 'memory'}<Brain
												class="h-3 w-3"
											/>{:else}<FileCode2 class="h-3 w-3" />{/if}{ev.label}
									</span>
								{/if}
							{/each}
						</div>
					</section>
				{/if}
			</div>
		</div>
	{/if}
</aside>

<style>
	/* Fixed inspector on the right, full height below the app header, slides in. */
	.wf-drawer {
		position: fixed;
		top: 3.5rem;
		right: 0;
		bottom: 0;
		width: 400px;
		max-width: 92vw;
		background: var(--bg-subtle);
		border-left: 1px solid var(--border);
		box-shadow: -10px 0 30px -14px rgb(0 0 0 / 0.35);
		transform: translateX(100%);
		transition: transform 240ms var(--ease, cubic-bezier(0.4, 0, 0.2, 1));
		will-change: transform;
		z-index: 40;
	}
	.wf-drawer.is-open {
		transform: translateX(0);
	}
	/* Section headings — Karma accent so intent / decision / why read apart at a glance. */
	.wf-label {
		margin-bottom: 0.375rem;
		font-size: 0.6875rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.09em;
		color: var(--accent);
	}
	@media (prefers-reduced-motion: reduce) {
		.wf-drawer {
			transition: none;
		}
	}
	@media (max-width: 640px) {
		.wf-drawer {
			top: 0;
		}
	}
</style>
