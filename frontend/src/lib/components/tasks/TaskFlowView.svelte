<script lang="ts">
	import type { TaskWithState } from '$lib/api-types';
	import { Check, Circle, Loader2, ChevronDown, ChevronRight } from 'lucide-svelte';

	interface Props {
		tasks: TaskWithState[];
		getTaskSubject: (id: string) => string;
	}

	let { tasks, getTaskSubject }: Props = $props();

	// Track expanded task IDs
	let expandedIds = $state<Set<string>>(new Set());

	function toggleExpanded(id: string) {
		if (expandedIds.has(id)) {
			expandedIds.delete(id);
		} else {
			expandedIds.add(id);
		}
		expandedIds = new Set(expandedIds);
	}

	// Build tree structure based on dependencies
	interface TreeNode {
		task: TaskWithState;
		level: number;
		children: string[]; // IDs of tasks this one blocks
	}

	const treeData = $derived.by(() => {
		const taskMap = new Map(tasks.map((t) => [t.id, t]));
		const nodes: TreeNode[] = [];

		// Calculate level for each task (max depth from any root)
		function getLevel(taskId: string, visited: Set<string> = new Set()): number {
			if (visited.has(taskId)) return 0; // Cycle detection
			visited.add(taskId);

			const task = taskMap.get(taskId);
			if (!task || task.blocked_by.length === 0) return 0;

			let maxParentLevel = 0;
			for (const parentId of task.blocked_by) {
				const parentLevel = getLevel(parentId, new Set(visited));
				maxParentLevel = Math.max(maxParentLevel, parentLevel + 1);
			}
			return maxParentLevel;
		}

		// Build nodes with levels
		for (const task of tasks) {
			const level = getLevel(task.id);
			const children = tasks.filter((t) => t.blocked_by.includes(task.id)).map((t) => t.id);
			nodes.push({ task, level, children });
		}

		// Sort by level, then by ID
		nodes.sort((a, b) => {
			if (a.level !== b.level) return a.level - b.level;
			return parseInt(a.task.id) - parseInt(b.task.id);
		});

		return nodes;
	});

	// Group nodes by level for display
	const levelGroups = $derived.by(() => {
		const groups: Map<number, TreeNode[]> = new Map();
		for (const node of treeData) {
			if (!groups.has(node.level)) {
				groups.set(node.level, []);
			}
			groups.get(node.level)!.push(node);
		}
		return Array.from(groups.entries()).sort((a, b) => a[0] - b[0]);
	});

	function getStatusIcon(task: TaskWithState) {
		if (task.status === 'completed') return Check;
		if (task.status === 'in_progress') return Loader2;
		return Circle;
	}

	function getStatusColor(task: TaskWithState) {
		if (task.status === 'completed') return 'text-[var(--success)]';
		if (task.status === 'in_progress') return 'text-[var(--nav-blue)]';
		if (task.isBlocked) return 'text-[var(--text-muted)]';
		return 'text-[var(--text-secondary)]';
	}

	function getLevelLabel(level: number): string {
		if (level === 0) return 'Independent';
		return `Depends on Level ${level - 1}`;
	}
</script>

{#if tasks.length > 0}
	<div class="task-tree">
		{#each levelGroups as [level, nodes] (level)}
			<div class="level-group">
				<div class="level-header">
					<span class="level-badge">L{level}</span>
					<span class="level-label">{getLevelLabel(level)}</span>
				</div>

				<div class="level-nodes">
					{#each nodes as node (node.task.id)}
						{@const task = node.task}
						{@const isExpanded = expandedIds.has(task.id)}
						{@const StatusIcon = getStatusIcon(task)}

						<div class="task-node" class:expanded={isExpanded}>
							<!-- Compact header -->
							<button class="node-header" onclick={() => toggleExpanded(task.id)}>
								<span class="expand-icon">
									{#if isExpanded}
										<ChevronDown size={14} />
									{:else}
										<ChevronRight size={14} />
									{/if}
								</span>

								<span class="task-number">{task.id}</span>

								<span class="status-icon {getStatusColor(task)}">
									<StatusIcon
										size={14}
										class={task.status === 'in_progress' ? 'animate-spin' : ''}
									/>
								</span>

								<span class="task-title">{task.subject}</span>

								{#if task.status === 'in_progress'}
									<span class="status-badge in-progress">In Progress</span>
								{:else if task.isBlocked}
									<span class="status-badge blocked">Blocked</span>
								{/if}
							</button>

							<!-- Expanded details -->
							{#if isExpanded}
								<div class="node-details">
									<p class="description">{task.description}</p>

									{#if task.status === 'in_progress' && task.active_form}
										<div class="active-status">
											<span class="pulse"></span>
											{task.active_form}
										</div>
									{/if}

									{#if task.blocked_by.length > 0}
										<div class="dependency-info">
											<span class="dep-label">Waiting on:</span>
											{#each task.blocked_by as depId}
												<span class="dep-tag">{depId}</span>
											{/each}
										</div>
									{/if}

									{#if node.children.length > 0}
										<div class="dependency-info">
											<span class="dep-label">Blocks:</span>
											{#each node.children as childId}
												<span class="dep-tag">{childId}</span>
											{/each}
										</div>
									{/if}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/each}

		<!-- Legend -->
		<div class="legend">
			<div class="legend-item">
				<Circle size={12} class="text-[var(--text-muted)]" />
				<span>Pending</span>
			</div>
			<div class="legend-item">
				<Loader2 size={12} class="text-[var(--nav-blue)]" />
				<span>In Progress</span>
			</div>
			<div class="legend-item">
				<Check size={12} class="text-[var(--success)]" />
				<span>Completed</span>
			</div>
		</div>
	</div>
{/if}

<style>
	.task-tree {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.level-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.level-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding-bottom: 0.25rem;
		border-bottom: 1px dashed var(--border);
	}

	.level-badge {
		font-size: 0.65rem;
		font-weight: 600;
		font-family: var(--font-mono);
		padding: 0.125rem 0.375rem;
		border-radius: 4px;
		background: var(--bg-muted);
		color: var(--text-muted);
	}

	.level-label {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.level-nodes {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding-left: 0.5rem;
		border-left: 2px solid var(--border);
		margin-left: 0.75rem;
	}

	.task-node {
		position: relative;
	}

	.task-node::before {
		content: '';
		position: absolute;
		left: -0.5rem;
		top: 0.875rem;
		width: 0.5rem;
		height: 2px;
		background: var(--border);
	}

	.node-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.5rem 0.75rem;
		border-radius: 6px;
		border: 1px solid var(--border);
		background: var(--bg-base);
		cursor: pointer;
		transition: all 0.15s ease;
		text-align: left;
	}

	.node-header:hover {
		border-color: var(--border-hover);
		background: var(--bg-subtle);
	}

	.task-node.expanded .node-header {
		border-color: var(--nav-blue);
		background: var(--bg-subtle);
		border-bottom-left-radius: 0;
		border-bottom-right-radius: 0;
	}

	.expand-icon {
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.task-number {
		font-size: 0.7rem;
		font-weight: 600;
		font-family: var(--font-mono);
		padding: 0.125rem 0.35rem;
		border-radius: 4px;
		background: var(--bg-muted);
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.status-icon {
		flex-shrink: 0;
		display: flex;
		align-items: center;
	}

	.task-title {
		flex: 1;
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.status-badge {
		font-size: 0.65rem;
		font-weight: 600;
		padding: 0.125rem 0.375rem;
		border-radius: 4px;
		flex-shrink: 0;
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}

	.status-badge.in-progress {
		background: var(--nav-blue-subtle);
		color: var(--nav-blue);
	}

	.status-badge.blocked {
		background: rgba(245, 158, 11, 0.1);
		color: var(--warning);
	}

	.node-details {
		padding: 0.75rem;
		border: 1px solid var(--nav-blue);
		border-top: none;
		border-radius: 0 0 6px 6px;
		background: var(--bg-subtle);
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.description {
		font-size: 0.8rem;
		color: var(--text-secondary);
		line-height: 1.5;
	}

	.active-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
		color: var(--nav-blue);
	}

	.pulse {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--nav-blue);
		animation: pulse 1.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.4;
		}
	}

	.dependency-info {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		flex-wrap: wrap;
	}

	.dep-label {
		font-size: 0.7rem;
		color: var(--text-muted);
	}

	.dep-tag {
		font-size: 0.65rem;
		font-family: var(--font-mono);
		font-weight: 500;
		padding: 0.125rem 0.35rem;
		border-radius: 4px;
		background: var(--bg-muted);
		color: var(--text-secondary);
	}

	.legend {
		display: flex;
		gap: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border);
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.7rem;
		color: var(--text-muted);
	}
</style>
