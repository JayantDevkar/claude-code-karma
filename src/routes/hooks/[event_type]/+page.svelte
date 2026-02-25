<script lang="ts">
	import { Webhook, Code, FileCode, ArrowRight, Clock, Target, Shield } from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import { getHookSourceColorVars } from '$lib/utils';

	let { data } = $props();

	let detail = $derived(data.detail);
	let event = $derived(detail.event);
	let schemaInfo = $derived(detail.schema_info);
	let relatedEvents = $derived(detail.related_events);

	// Badge variants for phases
	const phaseVariants: Record<string, 'accent' | 'blue' | 'success' | 'purple'> = {
		pre: 'blue',
		post: 'success',
		notification: 'purple',
		permission: 'accent'
	};

	// Language badge colors
	const languageColors: Record<string, string> = {
		python: '#3776ab',
		javascript: '#f7df1e',
		typescript: '#3178c6',
		bash: '#4eaa25',
		shell: '#4eaa25'
	};
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<PageHeader
		title={data.event_type}
		icon={Webhook}
		iconColor="--nav-amber"
		breadcrumbs={[
			{ label: 'Dashboard', href: '/' },
			{ label: 'Hooks', href: '/hooks' },
			{ label: data.event_type }
		]}
	>
		{#snippet badges()}
			{#if event.can_block}
				<Badge variant="error" icon={Shield}>CAN BLOCK</Badge>
			{/if}
			{#if event.phase}
				<Badge variant={phaseVariants[event.phase.toLowerCase()] || 'slate'}>
					{event.phase}
				</Badge>
			{/if}
		{/snippet}
	</PageHeader>

	<!-- Description Card -->
	{#if event.description}
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-lg p-6 shadow-sm">
			<p class="text-sm text-[var(--text-secondary)] leading-relaxed">
				{event.description}
			</p>
		</div>
	{/if}

	<!-- Active Registrations Section -->
	{#if event.registrations.length > 0}
		<div class="space-y-4">
			<div class="flex items-center gap-3">
				<h2 class="text-lg font-bold text-[var(--text-primary)]">Active Registrations</h2>
				<span
					class="inline-flex items-center justify-center min-w-[24px] h-[24px] px-2 bg-[var(--accent-subtle)] text-[var(--accent)] rounded-full text-xs font-bold tabular-nums"
				>
					{event.registrations.length}
				</span>
			</div>

			<div class="grid grid-cols-1 gap-4">
				{#each event.registrations as registration}
					{@const sourceColors = getHookSourceColorVars(
						registration.source_type,
						registration.source_name
					)}
					<div
						class="bg-[var(--bg-base)] border border-[var(--border)] rounded-lg p-5 hover:shadow-md transition-shadow"
					>
						<!-- Source Header -->
						<div
							class="flex items-start justify-between mb-4 pb-4 border-b border-[var(--border)]"
						>
							<div class="flex items-center gap-3">
								<div
									class="w-3 h-3 rounded-full flex-shrink-0"
									style="background-color: {sourceColors.color};"
								></div>
								<div>
									<a
										href="/hooks/sources/{registration.source_id}"
										class="text-base font-semibold text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
									>
										{registration.source_name}
									</a>
									{#if registration.description}
										<p class="text-xs text-[var(--text-muted)] mt-1">
											{registration.description}
										</p>
									{/if}
								</div>
							</div>
							<Badge variant="slate" class="flex-shrink-0">
								{registration.source_type}
							</Badge>
						</div>

						<!-- Script Info -->
						{#if registration.script_filename}
							<div class="mb-4 flex items-center gap-2">
								<FileCode size={14} class="text-[var(--text-muted)]" />
								<code class="text-sm font-mono text-[var(--text-secondary)]">
									{registration.script_filename}
								</code>
								<span
									class="px-2 py-0.5 rounded text-xs font-medium text-white"
									style="background-color: {languageColors[
										registration.script_language.toLowerCase()
									] || 'var(--text-muted)'};"
								>
									{registration.script_language}
								</span>
							</div>
						{/if}

						<!-- Command -->
						<div class="mb-4">
							<div class="flex items-center gap-2 mb-2">
								<Code size={14} class="text-[var(--text-muted)]" />
								<span
									class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider"
								>
									Command
								</span>
							</div>
							<pre
								class="bg-[var(--bg-muted)] border border-[var(--border)] rounded p-3 text-xs font-mono text-[var(--text-secondary)] overflow-x-auto"><code
									>{registration.command}</code
								></pre>
						</div>

						<!-- Metadata Row -->
						<div
							class="flex items-center gap-4 flex-wrap text-xs text-[var(--text-muted)]"
						>
							{#if registration.matcher && registration.matcher !== '*'}
								<div class="flex items-center gap-1.5">
									<Target size={12} />
									<span
										>Matcher: <code class="text-[var(--text-secondary)]"
											>{registration.matcher}</code
										></span
									>
								</div>
							{/if}
							{#if registration.timeout_ms}
								<div class="flex items-center gap-1.5">
									<Clock size={12} />
									<span
										>Timeout: <span
											class="text-[var(--text-secondary)] tabular-nums"
											>{registration.timeout_ms}ms</span
										></span
									>
								</div>
							{/if}
							{#if registration.can_block}
								<div class="flex items-center gap-1.5">
									<Shield size={12} class="text-[var(--red)]" />
									<span class="text-[var(--red)] font-medium"
										>Can block execution</span
									>
								</div>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}
		<div
			class="flex items-center gap-3 px-5 py-4 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
		>
			<Webhook size={20} class="text-[var(--text-muted)] flex-shrink-0" />
			<div>
				<p class="text-sm text-[var(--text-secondary)] font-medium">
					No active registrations
				</p>
				<p class="text-xs text-[var(--text-muted)]">
					This hook event has no registered handlers
				</p>
			</div>
		</div>
	{/if}

	<!-- Event Schema Section -->
	{#if schemaInfo}
		<CollapsibleGroup title="Event Schema" open={false}>
			{#snippet icon()}
				<Code size={16} style="color: var(--nav-amber);" />
			{/snippet}

			{#snippet children()}
				<div class="space-y-6">
					<!-- Input Fields -->
					{#if schemaInfo.input_fields.length > 0}
						<div>
							<h4
								class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3"
							>
								Input Fields
							</h4>
							<div class="overflow-x-auto">
								<table class="w-full text-sm">
									<thead
										class="bg-[var(--bg-subtle)] border-b border-[var(--border)]"
									>
										<tr>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Name
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Type
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Required
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Description
											</th>
										</tr>
									</thead>
									<tbody class="divide-y divide-[var(--border)]">
										{#each schemaInfo.input_fields as field}
											<tr
												class="hover:bg-[var(--bg-subtle)] transition-colors"
											>
												<td
													class="px-3 py-2.5 font-mono text-xs text-[var(--text-primary)]"
												>
													{field.name}
												</td>
												<td class="px-3 py-2.5">
													<code
														class="px-2 py-0.5 bg-[var(--bg-muted)] text-[var(--accent)] rounded text-xs"
													>
														{field.type}
													</code>
												</td>
												<td class="px-3 py-2.5">
													{#if field.required}
														<Badge variant="error" class="text-xs"
															>Yes</Badge
														>
													{:else}
														<Badge variant="slate" class="text-xs"
															>No</Badge
														>
													{/if}
												</td>
												<td
													class="px-3 py-2.5 text-[var(--text-muted)] text-xs"
												>
													{field.description || '—'}
												</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						</div>
					{/if}

					<!-- Output Fields -->
					{#if schemaInfo.output_fields.length > 0}
						<div>
							<h4
								class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3"
							>
								Output Fields
							</h4>
							<div class="overflow-x-auto">
								<table class="w-full text-sm">
									<thead
										class="bg-[var(--bg-subtle)] border-b border-[var(--border)]"
									>
										<tr>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Name
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Type
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Required
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Description
											</th>
										</tr>
									</thead>
									<tbody class="divide-y divide-[var(--border)]">
										{#each schemaInfo.output_fields as field}
											<tr
												class="hover:bg-[var(--bg-subtle)] transition-colors"
											>
												<td
													class="px-3 py-2.5 font-mono text-xs text-[var(--text-primary)]"
												>
													{field.name}
												</td>
												<td class="px-3 py-2.5">
													<code
														class="px-2 py-0.5 bg-[var(--bg-muted)] text-[var(--accent)] rounded text-xs"
													>
														{field.type}
													</code>
												</td>
												<td class="px-3 py-2.5">
													{#if field.required}
														<Badge variant="error" class="text-xs"
															>Yes</Badge
														>
													{:else}
														<Badge variant="slate" class="text-xs"
															>No</Badge
														>
													{/if}
												</td>
												<td
													class="px-3 py-2.5 text-[var(--text-muted)] text-xs"
												>
													{field.description || '—'}
												</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						</div>
					{/if}

					<!-- Base Fields -->
					{#if schemaInfo.base_fields.length > 0}
						<div>
							<h4
								class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3"
							>
								Base Fields (All Hooks)
							</h4>
							<div class="overflow-x-auto">
								<table class="w-full text-sm">
									<thead
										class="bg-[var(--bg-subtle)] border-b border-[var(--border)]"
									>
										<tr>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Name
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Type
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Required
											</th>
											<th
												class="px-3 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider"
											>
												Description
											</th>
										</tr>
									</thead>
									<tbody class="divide-y divide-[var(--border)]">
										{#each schemaInfo.base_fields as field}
											<tr
												class="hover:bg-[var(--bg-subtle)] transition-colors"
											>
												<td
													class="px-3 py-2.5 font-mono text-xs text-[var(--text-primary)]"
												>
													{field.name}
												</td>
												<td class="px-3 py-2.5">
													<code
														class="px-2 py-0.5 bg-[var(--bg-muted)] text-[var(--text-secondary)] rounded text-xs"
													>
														{field.type}
													</code>
												</td>
												<td class="px-3 py-2.5">
													{#if field.required}
														<Badge variant="error" class="text-xs"
															>Yes</Badge
														>
													{:else}
														<Badge variant="slate" class="text-xs"
															>No</Badge
														>
													{/if}
												</td>
												<td
													class="px-3 py-2.5 text-[var(--text-muted)] text-xs"
												>
													{field.description || '—'}
												</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						</div>
					{/if}
				</div>
			{/snippet}
		</CollapsibleGroup>
	{/if}

	<!-- Related Events Section -->
	{#if relatedEvents.length > 0}
		<div class="space-y-4">
			<h2 class="text-lg font-bold text-[var(--text-primary)]">Related Events</h2>
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
				{#each relatedEvents as relatedEvent}
					<a
						href="/hooks/{encodeURIComponent(relatedEvent.event_type)}"
						class="group bg-[var(--bg-base)] border border-[var(--border)] rounded-lg p-4 hover:shadow-md hover:border-[var(--accent)] transition-all"
					>
						<div class="flex items-start justify-between mb-2">
							<div class="flex items-center gap-2">
								<ArrowRight
									size={14}
									class="text-[var(--text-muted)] group-hover:text-[var(--accent)] transition-colors"
								/>
								<h3
									class="text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors"
								>
									{relatedEvent.event_type}
								</h3>
							</div>
							{#if relatedEvent.can_block}
								<Shield size={12} class="text-[var(--red)]" />
							{/if}
						</div>
						<div class="flex items-center gap-2 flex-wrap">
							<Badge
								variant={phaseVariants[relatedEvent.phase.toLowerCase()] || 'slate'}
								class="text-xs"
							>
								{relatedEvent.phase}
							</Badge>
							<span class="text-xs text-[var(--text-muted)]">
								{relatedEvent.position}
							</span>
						</div>
						{#if relatedEvent.description}
							<p class="mt-2 text-xs text-[var(--text-muted)] line-clamp-2">
								{relatedEvent.description}
							</p>
						{/if}
					</a>
				{/each}
			</div>
		</div>
	{/if}
</div>
