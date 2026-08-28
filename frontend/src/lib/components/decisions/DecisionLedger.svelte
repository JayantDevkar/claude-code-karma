<script lang="ts">
	import { API_BASE } from '$lib/config';
	import {
		Milestone,
		User,
		Bot,
		Users,
		Quote,
		GitCommitHorizontal,
		GitPullRequest,
		ExternalLink,
		FileCode2,
		Brain,
		MessageSquare,
		CornerUpLeft,
		Loader2
	} from 'lucide-svelte';
	import { format } from 'date-fns';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';

	interface DecisionEvidence {
		type: 'commit' | 'pr' | 'session' | 'code' | 'memory' | 'link';
		label: string;
		url?: string;
		session_id?: string;
	}

	interface Decision {
		id: string;
		date: string;
		session_id: string;
		session_title: string;
		kind: string;
		decided_by: 'human' | 'ai' | 'both';
		status: 'active' | 'superseded' | 'reversed';
		title: string;
		intent: string;
		options?: string[];
		chosen: string;
		why_quoted?: string;
		why_inferred?: string;
		supersedes?: string;
		supersedes_title?: string;
		evidence: DecisionEvidence[];
	}

	interface DecisionLedgerData {
		project: string;
		period: string;
		curated_by?: string;
		decisions: Decision[];
	}

	interface Props {
		projectEncodedName: string;
	}

	let { projectEncodedName }: Props = $props();

	let ledger = $state<DecisionLedgerData | null>(null);
	let loading = $state(true);
	let notFound = $state(false);
	let error = $state(false);
	let kindFilter = $state<string | null>(null);

	async function fetchLedger() {
		loading = true;
		error = false;
		notFound = false;
		try {
			const res = await fetch(`${API_BASE}/projects/${projectEncodedName}/decisions`);
			if (res.status === 404) {
				notFound = true;
				return;
			}
			if (!res.ok) throw new Error('Failed to fetch');
			ledger = await res.json();
		} catch {
			error = true;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (projectEncodedName) fetchLedger();
	});

	const kinds = $derived.by<string[]>(() => {
		if (!ledger) return [];
		return [...new Set(ledger.decisions.map((d) => d.kind))];
	});

	const visibleDecisions = $derived.by<Decision[]>(() => {
		if (!ledger) return [];
		return kindFilter ? ledger.decisions.filter((d) => d.kind === kindFilter) : ledger.decisions;
	});

	// Group consecutive decisions by session so each work session reads as one
	// chapter of the ledger.
	interface SessionGroup {
		session_id: string;
		session_title: string;
		date: string;
		decisions: Decision[];
	}
	const groups = $derived.by<SessionGroup[]>(() => {
		const out: SessionGroup[] = [];
		for (const d of visibleDecisions) {
			const last = out[out.length - 1];
			if (last && last.session_id === d.session_id) {
				last.decisions.push(d);
			} else {
				out.push({
					session_id: d.session_id,
					session_title: d.session_title,
					date: d.date,
					decisions: [d]
				});
			}
		}
		return out;
	});

	const humanCount = $derived(ledger?.decisions.filter((d) => d.decided_by === 'human').length ?? 0);
	const sessionCount = $derived(new Set(ledger?.decisions.map((d) => d.session_id)).size);

	// Kind → tint. Structural roles: shipping (milestone) reads success-ish,
	// changes of mind (reversal/waiver/correction) read warm, the rest stay
	// on the accent/neutral axis so the warm ones stand out.
	const kindTint: Record<string, string> = {
		feature: 'var(--accent)',
		design: 'var(--accent)',
		scope: 'var(--text-secondary)',
		process: 'var(--text-secondary)',
		milestone: 'var(--success, #10b981)',
		reversal: 'var(--warning, #f59e0b)',
		waiver: 'var(--warning, #f59e0b)',
		correction: 'var(--warning, #f59e0b)'
	};
	const tintFor = (kind: string) => kindTint[kind] ?? 'var(--text-secondary)';

	function sessionHref(sessionId: string): string {
		return `/projects/${projectEncodedName}/${sessionId.slice(0, 12)}`;
	}

	function scrollToDecision(id: string) {
		document.getElementById(`decision-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
	}
</script>

{#if loading}
	<div class="flex items-center justify-center py-16 text-[var(--text-muted)]">
		<Loader2 class="h-5 w-5 animate-spin" />
	</div>
{:else if notFound}
	<EmptyState
		icon={Milestone}
		title="No decision ledger yet"
		description="No curated decisions exist for this project. Ledgers are hand-curated for now — automated extraction is a later phase."
	/>
{:else if error || !ledger}
	<EmptyState icon={Milestone} title="Couldn't load decisions" description="The API request for this project's decision ledger failed." />
{:else}
	<div class="space-y-6">
		<!-- Ledger header -->
		<div class="flex flex-wrap items-baseline justify-between gap-2">
			<div>
				<p class="text-sm text-[var(--text-secondary)]">
					<span class="font-medium text-[var(--text-primary)]">{ledger.decisions.length} decisions</span>
					across {sessionCount} sessions · {humanCount} called by you
				</p>
				{#if ledger.curated_by}
					<p class="mt-0.5 text-xs text-[var(--text-muted)]">{ledger.curated_by}</p>
				{/if}
			</div>
			<!-- Kind filter chips -->
			<div class="flex flex-wrap gap-1.5">
				<button
					class="rounded-full border px-2.5 py-0.5 text-xs transition-colors {kindFilter === null
						? 'border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--text-primary)]'
						: 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)]'}"
					onclick={() => (kindFilter = null)}
				>
					all
				</button>
				{#each kinds as kind (kind)}
					<button
						class="rounded-full border px-2.5 py-0.5 text-xs transition-colors {kindFilter === kind
							? 'border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--text-primary)]'
							: 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)]'}"
						onclick={() => (kindFilter = kindFilter === kind ? null : kind)}
					>
						{kind}
					</button>
				{/each}
			</div>
		</div>

		<!-- Session groups, newest first -->
		{#each groups as group (group.session_id + group.date)}
			<section>
				<!-- Session chapter header -->
				<div class="mb-3 flex items-baseline gap-2">
					<span class="font-mono text-xs text-[var(--text-muted)]">{format(new Date(group.date), 'MMM d')}</span>
					<a
						href={sessionHref(group.session_id)}
						class="truncate text-sm font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--accent)]"
					>
						{group.session_title}
					</a>
				</div>

				<!-- Cards on a left spine -->
				<div class="ml-1 space-y-3 border-l border-[var(--border)] pl-4">
					{#each group.decisions as d (d.id)}
						<article
							id={'decision-' + d.id}
							class="relative rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4 transition-colors {d.status ===
							'superseded'
								? 'opacity-70'
								: ''}"
						>
							<!-- Spine dot -->
							<span
								class="absolute -left-[21.5px] top-5 h-2 w-2 rounded-full"
								style="background: {tintFor(d.kind)}"
							></span>

							<!-- Meta row -->
							<div class="mb-1.5 flex flex-wrap items-center gap-2 text-xs">
								<span
									class="rounded px-1.5 py-0.5 font-medium uppercase tracking-wide"
									style="color: {tintFor(d.kind)}; background: color-mix(in srgb, {tintFor(d.kind)} 12%, transparent)"
								>
									{d.kind}
								</span>
								<span class="inline-flex items-center gap-1 text-[var(--text-muted)]">
									{#if d.decided_by === 'human'}
										<User class="h-3 w-3" /> you decided
									{:else if d.decided_by === 'ai'}
										<Bot class="h-3 w-3" /> AI decided
									{:else}
										<Users class="h-3 w-3" /> decided together
									{/if}
								</span>
								{#if d.status === 'superseded'}
									<span class="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 text-[var(--text-muted)]">superseded</span>
								{/if}
								<span class="ml-auto font-mono text-[var(--text-muted)]">{format(new Date(d.date), 'HH:mm')}</span>
							</div>

							<h3 class="text-sm font-semibold text-[var(--text-primary)]">{d.title}</h3>
							<p class="mt-1 text-sm text-[var(--text-secondary)]">{d.intent}</p>

							{#if d.options && d.options.length > 0}
								<ul class="mt-2 space-y-0.5 text-xs text-[var(--text-muted)]">
									{#each d.options as option (option)}
										<li class="flex gap-1.5"><span aria-hidden="true">·</span>{option}</li>
									{/each}
								</ul>
							{/if}

							<p class="mt-2 text-sm text-[var(--text-primary)]">
								<span class="font-medium" style="color: {tintFor(d.kind)}">Chosen —</span>
								{d.chosen}
							</p>

							<!-- The why: verbatim quotes get quote styling; inferences are
							     visibly weaker so a guessed rationale never reads as your words. -->
							{#if d.why_quoted}
								<blockquote
									class="mt-2.5 flex gap-2 rounded-md border-l-2 border-[var(--accent)] bg-[var(--accent-muted,var(--bg-muted))] px-3 py-2 text-sm italic text-[var(--text-secondary)]"
								>
									<Quote class="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
									<span>{d.why_quoted}</span>
								</blockquote>
							{:else if d.why_inferred}
								<p class="mt-2.5 text-xs italic text-[var(--text-muted)]">
									<span class="font-medium not-italic">inferred rationale:</span>
									{d.why_inferred}
								</p>
							{/if}

							{#if d.supersedes}
								<button
									class="mt-2.5 inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] px-2.5 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]"
									onclick={() => scrollToDecision(d.supersedes!)}
								>
									<CornerUpLeft class="h-3 w-3" />
									supersedes: {d.supersedes_title ?? d.supersedes}
								</button>
							{/if}

							<!-- Evidence chips: every claim sits next to its proof -->
							{#if d.evidence.length > 0}
								<div class="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--border-subtle,var(--border))] pt-2.5">
									{#each d.evidence as ev (ev.label)}
										{#if ev.type === 'session' && ev.session_id}
											<a
												href={sessionHref(ev.session_id)}
												class="inline-flex items-center gap-1 rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--accent)]"
											>
												<MessageSquare class="h-3 w-3" />{ev.label}
											</a>
										{:else if ev.url}
											<a
												href={ev.url}
												target="_blank"
												rel="noopener noreferrer"
												class="inline-flex items-center gap-1 rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--accent)]"
											>
												{#if ev.type === 'pr'}<GitPullRequest class="h-3 w-3" />{:else}<ExternalLink
														class="h-3 w-3"
													/>{/if}{ev.label}
											</a>
										{:else}
											<span
												class="inline-flex items-center gap-1 rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs text-[var(--text-muted)]"
											>
												{#if ev.type === 'commit'}<GitCommitHorizontal class="h-3 w-3" />{:else if ev.type === 'memory'}<Brain
														class="h-3 w-3"
													/>{:else}<FileCode2 class="h-3 w-3" />{/if}{ev.label}
											</span>
										{/if}
									{/each}
								</div>
							{/if}
						</article>
					{/each}
				</div>
			</section>
		{/each}
	</div>
{/if}
