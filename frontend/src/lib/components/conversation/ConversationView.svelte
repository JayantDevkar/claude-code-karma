<script lang="ts">
	import { browser } from '$app/environment';
	import { replaceState } from '$app/navigation';
	import { Tabs } from 'bits-ui';
	import { onMount, onDestroy } from 'svelte';
	import {
		ArrowLeft,
		ArrowDown,
		MessageCircle,
		Clock,
		Users,
		FileText,
		BarChart3,
		Info,
		DollarSign,
		Cpu,
		Percent,
		Wrench,
		X,
		ListTodo,
		FileEdit,
		RefreshCw,
		Zap,
		TerminalSquare,
		Search
	} from 'lucide-svelte';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import { SessionDetailSkeleton } from '$lib/components/skeleton';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import { TimelineRail } from '$lib/components/timeline/index';
	import FileActivityTable from '$lib/components/FileActivityTable.svelte';
	import ToolUsageTable from '$lib/components/ToolUsageTable.svelte';
	import { API_BASE } from '$lib/config';
	import { ToolsChart } from '$lib/components/charts/index';
	import { SubagentGroup } from '$lib/components/subagents';
	import { TasksTab } from '$lib/components/tasks';
	import { PlanViewer } from '$lib/components/plan';
	import SkillsPanel from '$lib/components/skills/SkillsPanel.svelte';
	import CommandsPanel from '$lib/components/commands/CommandsPanel.svelte';
	import ConversationHeader from './ConversationHeader.svelte';
	import ConversationOverview from './ConversationOverview.svelte';
	import type {
		StatItem,
		ConversationEntity,
		SessionDetail,
		SubagentSessionDetail,
		TimelineEvent,
		FileActivity,
		ToolUsage,
		SkillUsage,
		CommandUsage,
		SubagentSummary,
		ContinuationSessionInfo,
		LiveSessionSummary,
		LiveSessionStatus,
		Task,
		PlanDetail
	} from '$lib/api-types';
	import { isSubagentSession, isMainSession } from '$lib/api-types';
	import {
		formatDuration,
		formatTokens,
		formatCost,
		getProjectName,
		getSubagentTypeDisplayName
	} from '$lib/utils';

	interface Props {
		/** The conversation entity (SessionDetail or SubagentSessionDetail) */
		entity: ConversationEntity | null;
		/** Encoded project name for navigation */
		encodedName: string;
		/** Session slug for navigation */
		sessionSlug: string;
		/** Project path for display */
		projectPath?: string;
		/** Live session info (for "starting" sessions) */
		liveSession?: LiveSessionSummary | null;
		/** Whether session is in "starting" state */
		isStarting?: boolean;
		/** Parent session slug (for subagents) */
		parentSessionSlug?: string;
		/** Session UUID (for subagent polling) */
		sessionUuid?: string;
		/** Pre-loaded timeline events */
		timeline?: TimelineEvent[];
		/** Pre-loaded file activity */
		fileActivity?: FileActivity[];
		/** Pre-loaded tools data */
		tools?: ToolUsage[];
		/** Pre-loaded tasks data */
		tasks?: Task[];
		/** Pre-loaded plan data (optional, may be null if no plan exists) */
		plan?: PlanDetail | null;
	}

	let {
		entity: initialEntity,
		encodedName,
		sessionSlug,
		projectPath,
		liveSession = null,
		isStarting = false,
		parentSessionSlug,
		sessionUuid,
		timeline: initialTimeline = [],
		fileActivity: initialFileActivity = [],
		tools: initialTools = [],
		tasks: initialTasks = [],
		plan = null
	}: Props = $props();

	// Helper functions to compute initial values from props or entity
	function getInitialTools(): ToolUsage[] {
		if (initialTools && initialTools.length > 0) return initialTools;
		if (initialEntity && isMainSession(initialEntity) && initialEntity.tools_used) {
			const sessionTools = initialEntity.tools_used;
			if (Array.isArray(sessionTools)) {
				return sessionTools.map((t: any) => ({
					tool_name: t.tool_name || t.name || 'Unknown',
					count: typeof t.count === 'number' ? t.count : 1
				}));
			}
		}
		return [];
	}

	function getInitialTimeline(): TimelineEvent[] {
		if (initialTimeline && initialTimeline.length > 0) return initialTimeline;
		if (initialEntity && isMainSession(initialEntity) && initialEntity.timeline) {
			return initialEntity.timeline;
		}
		return [];
	}

	function getInitialFileActivity(): FileActivity[] {
		if (initialFileActivity && initialFileActivity.length > 0) return initialFileActivity;
		if (initialEntity && isMainSession(initialEntity) && initialEntity.file_activity) {
			return initialEntity.file_activity;
		}
		return [];
	}

	// Make entity data mutable for live updates - initialize directly from props
	let entityData = $state<ConversationEntity | null>(initialEntity);

	// Derive entity for read access
	const entity = $derived(entityData);

	// Mutable state for live updates - initialize from props
	let timelineEvents = $state<TimelineEvent[]>(getInitialTimeline());
	let fileActivities = $state<FileActivity[]>(getInitialFileActivity());
	let toolsArray = $state<ToolUsage[]>(getInitialTools());
	let tasksArray = $state<Task[]>(initialTasks);

	// Skills used - derived from entity (not live-updated separately)
	let skillsArray = $derived.by<SkillUsage[]>(() => {
		if (!entityData || !isMainSession(entityData)) return [];
		return entityData.skills_used || [];
	});

	// Commands used - derived from entity
	let commandsArray = $derived.by<CommandUsage[]>(() => {
		if (!entityData || !isMainSession(entityData)) return [];
		return entityData.commands_used || [];
	});

	// Track last tasks fetch time for incremental fetching
	// null means we haven't done the first fetch yet (or need a full refresh)
	let lastTasksFetchTime = $state<string | null>(null);

	// Track which session we've initialized for to detect navigation (use sessionSlug as identifier)
	// Plain variable (not $state) to avoid reactive loop when read+written in $effect
	let initializedForSession: string | null = sessionSlug;

	// Sync state when navigating to a different session (prop identity changes)
	$effect(() => {
		// Only re-initialize if we navigated to a different session
		if (sessionSlug !== initializedForSession) {
			// Stop any existing polling for the previous session
			stopPolling();
			// Reset state for new session
			entityData = initialEntity;
			timelineEvents = getInitialTimeline();
			fileActivities = getInitialFileActivity();
			toolsArray = getInitialTools();
			tasksArray = initialTasks;
			lastTasksFetchTime = null;
			liveStatus = null;
			sessionEnded = false;
			hasAutoEnabledTailing = false;
			isTailing = false;
			initializedForSession = sessionSlug;
		}
	});

	/**
	 * Merge new/updated tasks into the existing tasks array.
	 * Uses task.id as the key - updates existing tasks, adds new ones.
	 */
	function mergeTasks(existingTasks: Task[], newTasks: Task[]): Task[] {
		const taskMap = new Map<string, Task>();

		// Add existing tasks to map
		for (const task of existingTasks) {
			taskMap.set(task.id, task);
		}

		// Merge in new/updated tasks
		for (const task of newTasks) {
			taskMap.set(task.id, task);
		}

		// Return sorted by ID (numeric sort for proper ordering)
		return Array.from(taskMap.values()).sort((a, b) => {
			const aNum = parseInt(a.id, 10);
			const bNum = parseInt(b.id, 10);
			if (!isNaN(aNum) && !isNaN(bNum)) {
				return aNum - bNum;
			}
			return a.id.localeCompare(b.id);
		});
	}

	// Live session polling state
	let liveStatus = $state<LiveSessionSummary | null>(null);
	let sessionEnded = $state(false);
	let pollTimeout: ReturnType<typeof setTimeout> | null = null;
	let isRefreshing = $state(false);

	// Race condition guards
	let abortController: AbortController | null = $state(null);
	let isPolling = $state(false);

	// Adaptive polling state
	let lastChangeTime = $state<number>(Date.now());
	let lastPollData = $state<{
		taskCount: number;
		timelineLength: number;
		toolCount: number;
	} | null>(null);

	// Polling interval constants
	const POLL_INTERVAL_ACTIVE = 1000; // 1 second when actively changing
	const POLL_INTERVAL_IDLE = 5000; // 5 seconds when idle
	const IDLE_THRESHOLD = 30000; // 30 seconds to consider idle

	const isCurrentlyLive = $derived(liveStatus !== null && liveStatus.status !== 'ended');

	// Timeline tailing state
	let isTailing = $state(false);
	let hasAutoEnabledTailing = $state(false);
	const TAIL_COUNT = 3;

	// In-conversation search (Cmd+F)
	let conversationSearchQuery = $state('');
	let showConversationSearch = $state(false);
	let searchMatchCount = $state(0);
	let currentSearchMatch = $state(0);

	$effect(() => {
		if (!browser) return;
		if (isCurrentlyLive && !hasAutoEnabledTailing) {
			// Defer state mutation to avoid unsafe_state_mutation during render
			queueMicrotask(() => {
				isTailing = true;
				hasAutoEnabledTailing = true;
			});
		}
	});

	// Polling watchdog: restart polling if it stopped while session is still live
	$effect(() => {
		if (!browser || !isCurrentlyLive) return;

		// Check every 10 seconds if polling has stopped unexpectedly
		const watchdogInterval = setInterval(() => {
			// If session is live but no poll is scheduled or in progress, restart
			if (isCurrentlyLive && !pollTimeout && !isPolling) {
				console.log('[Polling Watchdog] Restarting stopped polling for live session');
				startPolling();
			}
		}, 10000);

		return () => {
			clearInterval(watchdogInterval);
		};
	});

	function toggleTailing() {
		isTailing = !isTailing;
	}

	// Determine the UUID for polling
	const pollUuid = $derived.by(() => {
		if (!entity) return null;
		if (isSubagentSession(entity)) {
			return sessionUuid || null;
		}
		return entity.uuid || null;
	});

	// Poll live session status
	async function pollLiveStatus(signal?: AbortSignal) {
		if (!pollUuid) return;

		try {
			const res = await fetch(`${API_BASE}/live-sessions/${pollUuid}`, { signal });
			if (res.ok) {
				const newStatus: LiveSessionSummary = await res.json();
				const wasLive = isCurrentlyLive;
				liveStatus = newStatus;

				if (wasLive && newStatus.status === 'ended') {
					sessionEnded = true;
					await refreshData();
					stopPolling();
				}
			} else if (res.status === 404) {
				liveStatus = null;
				stopPolling();
			}
		} catch (e) {
			// Ignore AbortError - expected when navigation occurs
			if (e instanceof Error && e.name === 'AbortError') return;
			console.error('Failed to poll live status:', e);
		}
	}

	// Refresh data from API
	async function refreshData(signal?: AbortSignal) {
		if (!entity) return;
		if (isSubagentSession(entity)) {
			await refreshAgentData(signal);
		} else {
			await refreshSessionData(signal);
		}
	}

	async function refreshSessionData(signal?: AbortSignal) {
		if (!entity || isSubagentSession(entity)) return;
		const uuid = entity.uuid;

		isRefreshing = true;

		// Build tasks URL with optional since parameter for incremental fetching
		const tasksUrl = lastTasksFetchTime
			? `${API_BASE}/sessions/${uuid}/tasks?fresh=1&since=${encodeURIComponent(lastTasksFetchTime)}`
			: `${API_BASE}/sessions/${uuid}/tasks?fresh=1`;

		// Record fetch time before making the request
		const fetchStartTime = new Date().toISOString();

		try {
			const [sessionRes, timelineRes, fileActivityRes, subagentsRes, toolsRes, tasksRes] =
				await Promise.all([
					fetch(`${API_BASE}/sessions/${uuid}?fresh=1`, { signal }),
					fetch(`${API_BASE}/sessions/${uuid}/timeline?fresh=1`, { signal }),
					fetch(`${API_BASE}/sessions/${uuid}/file-activity?fresh=1`, {
						signal
					}),
					fetch(`${API_BASE}/sessions/${uuid}/subagents?fresh=1`, { signal }),
					fetch(`${API_BASE}/sessions/${uuid}/tools?fresh=1`, { signal }),
					fetch(tasksUrl, { signal })
				]);

			if (!sessionRes.ok) return;

			const sessionDetail = await sessionRes.json();
			const newTimeline = timelineRes.ok ? await timelineRes.json() : [];
			const newFileActivity = fileActivityRes.ok ? await fileActivityRes.json() : [];
			const newSubagents = subagentsRes.ok ? await subagentsRes.json() : [];
			const toolsData = toolsRes.ok ? await toolsRes.json() : [];
			const fetchedTasks: Task[] = tasksRes.ok ? await tasksRes.json() : [];

			const tools_used = toolsData.map((t: any) => ({
				tool_name: t.tool_name,
				count: t.count
			}));

			entityData = {
				...sessionDetail,
				project_path: projectPath,
				tools_used,
				file_activity: newFileActivity,
				timeline: newTimeline,
				subagents: newSubagents
			};
			timelineEvents = newTimeline;
			fileActivities = newFileActivity;
			toolsArray = tools_used;

			// Use incremental merging for tasks if we have a lastTasksFetchTime,
			// otherwise replace the entire array (first fetch)
			if (lastTasksFetchTime && fetchedTasks.length > 0) {
				// Merge new/updated tasks into existing array
				tasksArray = mergeTasks(tasksArray, fetchedTasks);
			} else if (!lastTasksFetchTime) {
				// First fetch - replace entire array
				tasksArray = fetchedTasks;
			}
			// If lastTasksFetchTime is set but fetchedTasks is empty, keep existing tasks

			// Update lastTasksFetchTime for next incremental fetch
			lastTasksFetchTime = fetchStartTime;
		} catch (e) {
			// Ignore AbortError - expected when navigation occurs
			if (e instanceof Error && e.name === 'AbortError') return;
			console.error('Failed to refresh session data:', e);
		} finally {
			isRefreshing = false;
		}
	}

	async function refreshAgentData(signal?: AbortSignal) {
		if (!entity || !isSubagentSession(entity) || !sessionUuid) return;
		const agentId = entity.agent_id;

		isRefreshing = true;

		// Build tasks URL with optional since parameter for incremental fetching
		const baseTasksUrl = `${API_BASE}/agents/${encodedName}/${sessionUuid}/agents/${agentId}/tasks`;
		const tasksUrl = lastTasksFetchTime
			? `${baseTasksUrl}?fresh=1&since=${encodeURIComponent(lastTasksFetchTime)}`
			: `${baseTasksUrl}?fresh=1`;

		// Record fetch time before making the request
		const fetchStartTime = new Date().toISOString();

		try {
			const [agentRes, timelineRes, fileActivityRes, toolsRes, tasksRes] = await Promise.all([
				fetch(
					`${API_BASE}/agents/${encodedName}/${sessionUuid}/agents/${agentId}?fresh=1`,
					{ signal }
				),
				fetch(
					`${API_BASE}/agents/${encodedName}/${sessionUuid}/agents/${agentId}/timeline?fresh=1`,
					{ signal }
				),
				fetch(
					`${API_BASE}/agents/${encodedName}/${sessionUuid}/agents/${agentId}/file-activity?fresh=1`,
					{ signal }
				),
				fetch(
					`${API_BASE}/agents/${encodedName}/${sessionUuid}/agents/${agentId}/tools?fresh=1`,
					{ signal }
				),
				fetch(tasksUrl, { signal })
			]);

			if (!agentRes.ok) return;

			const agentDetail = await agentRes.json();
			const newTimeline = timelineRes.ok ? await timelineRes.json() : [];
			const newFileActivity = fileActivityRes.ok ? await fileActivityRes.json() : [];
			const toolsData = toolsRes.ok ? await toolsRes.json() : [];
			const fetchedTasks: Task[] = tasksRes.ok ? await tasksRes.json() : [];

			entityData = agentDetail;
			timelineEvents = newTimeline;
			fileActivities = newFileActivity;
			toolsArray = toolsData.map((t: any) => ({
				tool_name: t.tool_name,
				count: t.count
			}));

			// Use incremental merging for tasks if we have a lastTasksFetchTime,
			// otherwise replace the entire array (first fetch)
			if (lastTasksFetchTime && fetchedTasks.length > 0) {
				// Merge new/updated tasks into existing array
				tasksArray = mergeTasks(tasksArray, fetchedTasks);
			} else if (!lastTasksFetchTime) {
				// First fetch - replace entire array
				tasksArray = fetchedTasks;
			}
			// If lastTasksFetchTime is set but fetchedTasks is empty, keep existing tasks

			// Update lastTasksFetchTime for next incremental fetch
			lastTasksFetchTime = fetchStartTime;
		} catch (e) {
			// Ignore AbortError - expected when navigation occurs
			if (e instanceof Error && e.name === 'AbortError') return;
			console.error('Failed to refresh agent data:', e);
		} finally {
			isRefreshing = false;
		}
	}

	// Compute current poll data for change detection
	function getCurrentPollData() {
		return {
			taskCount: tasksArray.length,
			timelineLength: timelineEvents.length,
			toolCount: toolsArray.reduce((sum, t) => sum + t.count, 0)
		};
	}

	// Detect if data changed since last poll
	function detectChanges(): boolean {
		const currentData = getCurrentPollData();

		if (!lastPollData) {
			lastPollData = currentData;
			return true; // First poll, consider it a change
		}

		const hasChanged =
			currentData.taskCount !== lastPollData.taskCount ||
			currentData.timelineLength !== lastPollData.timelineLength ||
			currentData.toolCount !== lastPollData.toolCount;

		lastPollData = currentData;
		return hasChanged;
	}

	// Calculate adaptive polling interval
	function getPollingInterval(): number {
		const now = Date.now();
		const timeSinceLastChange = now - lastChangeTime;

		if (timeSinceLastChange >= IDLE_THRESHOLD) {
			return POLL_INTERVAL_IDLE;
		}
		return POLL_INTERVAL_ACTIVE;
	}

	// Schedule next poll with adaptive timing
	function scheduleNextPoll() {
		if (pollTimeout || isPolling) return; // Already scheduled or poll in progress

		const interval = getPollingInterval();
		pollTimeout = setTimeout(async () => {
			pollTimeout = null;

			// Guard against concurrent polls
			if (isPolling) return;
			isPolling = true;

			// Create new abort controller for this poll cycle
			abortController = new AbortController();
			const signal = abortController.signal;

			// Track whether we should continue polling after this cycle
			let shouldContinuePolling = false;

			try {
				await pollLiveStatus(signal);
				if (isCurrentlyLive && !signal.aborted) {
					await refreshData(signal);

					// Check for changes and update lastChangeTime (only if not aborted)
					if (!signal.aborted && detectChanges()) {
						lastChangeTime = Date.now();
					}

					// Mark that we should continue polling if still live and not aborted
					if (!signal.aborted && isCurrentlyLive) {
						shouldContinuePolling = true;
					}
				}
			} finally {
				// Reset polling flag FIRST
				isPolling = false;

				// Schedule next poll AFTER isPolling is reset (fixes the guard check)
				if (shouldContinuePolling) {
					scheduleNextPoll();
				}
			}
		}, interval);
	}

	function startPolling() {
		if (pollTimeout) return;
		// Initialize poll data for change detection
		lastPollData = getCurrentPollData();
		lastChangeTime = Date.now();
		scheduleNextPoll();
	}

	function stopPolling() {
		if (pollTimeout) {
			clearTimeout(pollTimeout);
			pollTimeout = null;
		}
		if (abortController) {
			abortController.abort();
			abortController = null;
		}
		isPolling = false;
	}

	// Tab state - dynamic based on plan presence and skills
	// Plan appears at position 2 (after overview) when it exists
	let validTabs = $derived.by(() => {
		const base: string[] = ['overview'];
		if (plan) base.push('plan');
		base.push('timeline', 'tasks', 'files');
		if (entity && isMainSession(entity)) {
			base.push('agents');
			if (skillsArray.length > 0) base.push('skills');
			if (commandsArray.length > 0) base.push('commands');
		}
		base.push('analytics');
		return base;
	});
	let activeTab = $state('overview');
	let tabsReady = $state(true); // Initialize to true for SSR rendering
	let isMounted = $state(false); // Track if component is mounted (router ready)

	// Continuation session linking state (sessions only)
	let continuationSession = $state<ContinuationSessionInfo | null>(null);
	let continuationLoading = $state(false);
	let continuationError = $state<string | null>(null);

	// Fetch continuation session info for continuation marker sessions
	$effect(() => {
		if (!browser) return;

		// Skip if entity doesn't need continuation info
		if (!entity || isSubagentSession(entity) || !entity.is_continuation_marker) {
			// Only reset if there's something to reset, and defer to avoid unsafe mutation
			if (continuationSession !== null || continuationError !== null) {
				queueMicrotask(() => {
					continuationSession = null;
					continuationError = null;
				});
			}
			return;
		}

		// Capture values we need for the async operation
		const currentEntity = entity;
		const leafUuids = currentEntity.project_context_leaf_uuids;
		const entityUuid = currentEntity.uuid;

		// Defer all state mutations to avoid unsafe mutation during render
		queueMicrotask(() => {
			continuationLoading = true;
			continuationError = null;
		});

		if (leafUuids && leafUuids.length > 0) {
			const messageUuid = leafUuids[0];
			fetch(`${API_BASE}/sessions/by-message/${messageUuid}`)
				.then((res) => {
					if (!res.ok) throw new Error('not_found');
					return res.json();
				})
				.then((data: ContinuationSessionInfo) => {
					continuationSession = data;
					continuationLoading = false;
				})
				.catch(() => {
					fetchBySlugFallback();
				});
		} else {
			fetchBySlugFallback();
		}

		function fetchBySlugFallback() {
			fetch(`${API_BASE}/sessions/continuation/${entityUuid}`)
				.then((res) => {
					if (!res.ok) throw new Error('Could not find continuation session');
					return res.json();
				})
				.then((data: ContinuationSessionInfo) => {
					continuationSession = data;
					continuationLoading = false;
				})
				.catch((err) => {
					continuationSession = null;
					continuationError = err.message;
					continuationLoading = false;
				});
		}
	});

	onMount(() => {
		// Mark as mounted (router is now ready)
		isMounted = true;

		// Read tab from URL on mount (client-side only)
		const params = new URLSearchParams(window.location.search);
		const tabParam = params.get('tab');
		if (tabParam && validTabs.includes(tabParam)) {
			activeTab = tabParam;
		}

		const handlePopState = () => {
			const params = new URLSearchParams(window.location.search);
			const tabParam = params.get('tab');
			if (tabParam && validTabs.includes(tabParam)) {
				activeTab = tabParam;
			} else {
				activeTab = 'overview';
			}
		};

		function handleKeydown(e: KeyboardEvent) {
			if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
				e.preventDefault();
				showConversationSearch = true;
			}
			if (e.key === 'Escape' && showConversationSearch) {
				showConversationSearch = false;
				conversationSearchQuery = '';
			}
		}
		window.addEventListener('keydown', handleKeydown);

		window.addEventListener('popstate', handlePopState);

		(async () => {
			if (pollUuid) {
				await pollLiveStatus();
				if (isCurrentlyLive) {
					startPolling();
				}
			}
		})();

		return () => {
			window.removeEventListener('keydown', handleKeydown);
			window.removeEventListener('popstate', handlePopState);
		};
	});

	onDestroy(() => {
		stopPolling();
	});

	// Sync activeTab changes to URL (only after mounted)
	$effect(() => {
		if (!browser || !tabsReady || !isMounted) return;

		// Capture activeTab to track only this dependency (not $page.state)
		const tab = activeTab;

		const url = new URL(window.location.href);

		if (tab === 'overview') {
			url.searchParams.delete('tab');
		} else {
			url.searchParams.set('tab', tab);
		}

		try {
			replaceState(url.toString(), {});
		} catch {
			// Router may not be initialized yet during hydration
		}
	});

	// Derived values
	let toolsUsedRecord = $derived.by<Record<string, number>>(() => {
		return Object.fromEntries(toolsArray.map((t) => [t.tool_name, t.count]));
	});

	let totalToolCalls = $derived(toolsArray.reduce((acc, t) => acc + t.count, 0));

	// Analytics stats
	let analyticsStats = $derived.by<StatItem[]>(() => {
		if (!entity) return [];
		const totalTokens = (entity.total_input_tokens || 0) + (entity.total_output_tokens || 0);
		const toolsCount = isSubagentSession(entity)
			? Object.keys(entity.tools_used || {}).length
			: toolsArray.length;

		return [
			{
				title: 'Total Cost',
				value: formatCost(entity.total_cost),
				icon: DollarSign,
				color: 'purple'
			},
			{
				title: 'Total Tokens',
				value: formatTokens(totalTokens),
				icon: Cpu,
				color: 'teal',
				tokenIn: entity.total_input_tokens,
				tokenOut: entity.total_output_tokens
			},
			{
				title: 'Duration',
				value: formatDuration(entity.duration_seconds),
				icon: Clock,
				color: 'orange'
			},
			{
				title: 'Tools Used',
				value: toolsCount,
				icon: Wrench,
				color: 'blue'
			},
			{
				title: 'Cache Hit Rate',
				value: `${((entity.cache_hit_rate || 0) * 100).toFixed(1)}%`,
				icon: Percent,
				color: 'accent'
			}
		];
	});

	// Group subagents by type (sessions only)
	let groupedSubagents = $derived.by<[string, SubagentSummary[]][]>(() => {
		if (!entity || isSubagentSession(entity)) return [];
		const subagents = entity.subagents as SubagentSummary[] | undefined;
		if (!subagents) return [];

		const groups: Record<string, SubagentSummary[]> = {};

		subagents.forEach((agent) => {
			const type = agent.subagent_type || 'Other';
			if (!groups[type]) groups[type] = [];
			groups[type].push(agent);
		});

		return Object.entries(groups).sort(([a], [b]) => {
			if (a === 'Other') return 1;
			if (b === 'Other') return -1;
			return a.localeCompare(b);
		});
	});

	// Determine entity label for descriptions
	let entityLabel = $derived(entity && isSubagentSession(entity) ? 'agent' : 'session');

	// Current agent ID for hiding "current agent" badges in agent views
	// When viewing an agent's timeline, we don't need to show badges for that agent's own events
	let currentAgentId = $derived.by<string | null>(() => {
		if (!entity) return null;
		if (isSubagentSession(entity)) {
			return entity.agent_id;
		}
		return null;
	});

	// Map of agent_id -> subagent_type for color lookup in file activity table
	let subagentTypes = $derived.by<Record<string, string | null>>(() => {
		if (!entity || !isMainSession(entity)) return {};
		const subagents = entity.subagents;
		if (!subagents) return {};
		return Object.fromEntries(subagents.map((a) => [a.agent_id, a.subagent_type]));
	});
</script>

<div class="space-y-6">
	{#if isStarting && liveSession}
		<!-- Starting Session Placeholder -->
		<PageHeader
			title={liveSession.session_id.slice(0, 8)}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/' },
				{ label: 'Projects', href: '/projects' },
				{
					label: getProjectName(liveSession.cwd || ''),
					href: `/projects/${encodedName}`
				},
				{ label: liveSession.session_id.slice(0, 8) }
			]}
			subtitle="Session Starting"
			class="mb-0"
		/>

		<div
			class="flex flex-col items-center justify-center py-16 px-4 text-center rounded-lg border border-dashed border-[var(--nav-purple)]/40 bg-[var(--nav-purple-subtle)]"
		>
			<div class="p-4 rounded-full bg-[var(--nav-purple)]/10 mb-4">
				<MessageCircle size={48} strokeWidth={1.5} class="text-[var(--nav-purple)]" />
			</div>
			<h3 class="text-lg font-medium text-[var(--text-primary)] mb-2">
				Waiting for First Message
			</h3>
			<p class="text-sm text-[var(--text-secondary)] max-w-md mb-6">
				This session has started but hasn't received its first prompt yet. Send your first
				message to Claude to view the session details.
			</p>

			<div
				class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--nav-purple)]/10 border border-[var(--nav-purple)]/30"
			>
				<span class="w-2 h-2 rounded-full bg-[var(--nav-purple)] animate-pulse"></span>
				<span class="text-xs font-medium text-[var(--nav-purple)]">Starting</span>
			</div>

			<a
				href="/projects/{encodedName}"
				class="
					mt-6 inline-flex items-center gap-2
					px-4 py-2
					text-sm font-medium
					rounded-md border
					bg-[var(--bg-muted)] border-[var(--border)] text-[var(--text-secondary)]
					hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)]
					transition-colors
				"
			>
				<ArrowLeft size={16} strokeWidth={2} />
				Back to Project
			</a>
		</div>
	{:else if entity}
		<!-- Header -->
		<ConversationHeader
			{entity}
			{encodedName}
			{sessionSlug}
			{projectPath}
			{parentSessionSlug}
			{liveStatus}
			{isRefreshing}
		/>

		<!-- Tabs -->
		{#if tabsReady}
			<Tabs.Root bind:value={activeTab} class="space-y-6">
				<Tabs.List
					class="flex items-center gap-1 p-1 bg-[var(--bg-subtle)] rounded-lg w-fit mx-auto border border-[var(--border)]"
				>
					<TabsTrigger value="overview" icon={Info}>Overview</TabsTrigger>
					<TabsTrigger value="timeline" icon={Clock}>Timeline</TabsTrigger>
					<TabsTrigger value="tasks" icon={ListTodo}>
						Tasks
						{#if tasksArray.length > 0}
							<span class="text-xs font-mono text-[var(--text-muted)]">
								{tasksArray.filter((t) => t.status === 'completed')
									.length}/{tasksArray.length}
							</span>
						{/if}
					</TabsTrigger>
					{#if plan}
						<TabsTrigger value="plan" icon={FileEdit}>Plan</TabsTrigger>
					{/if}
					<TabsTrigger value="files" icon={FileText}>Files</TabsTrigger>
					{#if isMainSession(entity)}
						<TabsTrigger value="agents" icon={Users}>
							Subagents
							{#if entity.subagent_count}
								<span class="text-xs font-mono text-[var(--text-muted)]"
									>{entity.subagent_count}</span
								>
							{/if}
						</TabsTrigger>
						{#if skillsArray.length > 0}
							<TabsTrigger value="skills" icon={Zap}>
								Skills
								<span class="text-xs font-mono text-[var(--text-muted)]"
									>{skillsArray.length}</span
								>
							</TabsTrigger>
						{/if}
						{#if commandsArray.length > 0}
							<TabsTrigger value="commands" icon={TerminalSquare}>
								Commands
								<span class="text-xs font-mono text-[var(--text-muted)]"
									>{commandsArray.length}</span
								>
							</TabsTrigger>
						{/if}
					{/if}
					<TabsTrigger value="analytics" icon={BarChart3}>Analytics</TabsTrigger>
				</Tabs.List>

				<!-- Overview Tab -->
				<Tabs.Content value="overview">
					<ConversationOverview
						{entity}
						{toolsArray}
						{totalToolCalls}
						projectEncoded={encodedName}
						{continuationSession}
						{continuationLoading}
						{continuationError}
					/>
				</Tabs.Content>

				<!-- Timeline Tab -->
				<Tabs.Content value="timeline" class="animate-fade-in">
					<div class="space-y-4">
						<div class="flex items-start justify-between gap-4">
							<div>
								<h2 class="text-lg font-semibold text-[var(--text-primary)]">
									Timeline
								</h2>
								<p class="text-sm text-[var(--text-muted)]">
									{#if isTailing && timelineEvents.length > TAIL_COUNT}
										Showing {TAIL_COUNT} of {timelineEvents.length} events
									{:else}
										Chronological sequence of events in this {entityLabel}
									{/if}
								</p>
							</div>

							{#if isCurrentlyLive && timelineEvents.length > 0}
								<button
									onclick={toggleTailing}
									class="
										inline-flex items-center gap-1.5 px-3 py-1.5
										text-xs font-medium rounded-[var(--radius-md)] border
										transition-all duration-150 shrink-0
										{isTailing
										? 'bg-[var(--success-subtle)] border-[var(--success)]/50 text-[var(--success)]'
										: 'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--success)]/30 hover:bg-[var(--success-subtle)]/50'}
									"
									title={isTailing
										? 'Showing last 3 events - click to show all'
										: 'Click to show only last 3 events'}
									aria-pressed={isTailing}
								>
									<ArrowDown
										size={14}
										strokeWidth={2}
										class={isTailing ? 'animate-pulse' : ''}
									/>
									<span>Tail Events</span>
								</button>
							{/if}
						</div>

						{#if timelineEvents.length > 0}
							<TimelineRail
								events={timelineEvents}
								isLive={isCurrentlyLive}
								{isTailing}
								onToggleTailing={toggleTailing}
								{currentAgentId}
								{projectPath}
								searchQuery={showConversationSearch ? conversationSearchQuery : ''}
								onSearchMatchCount={(count) => {
									searchMatchCount = count;
								}}
								onCurrentMatchChange={(idx) => {
									currentSearchMatch = idx;
								}}
							/>
						{:else}
							<EmptyState
								icon={Clock}
								title="No timeline events available"
								description="Timeline events will appear here as they occur"
							/>
						{/if}
					</div>
				</Tabs.Content>

				<!-- Tasks Tab -->
				<Tabs.Content value="tasks" class="animate-fade-in">
					<TasksTab tasks={tasksArray} />
				</Tabs.Content>

				<!-- Plan Tab -->
				{#if plan}
					<Tabs.Content value="plan" class="animate-fade-in">
						<PlanViewer {plan} embedded={true} />
					</Tabs.Content>
				{/if}

				<!-- Files Tab -->
				<Tabs.Content value="files" class="animate-fade-in">
					<div class="space-y-4">
						<div>
							<h2 class="text-lg font-semibold text-[var(--text-primary)]">
								File Activity
							</h2>
							<p class="text-sm text-[var(--text-muted)]">
								All file operations performed during this {entityLabel}
							</p>
						</div>

						{#if fileActivities.length > 0}
							<FileActivityTable
								activities={fileActivities}
								{projectPath}
								{currentAgentId}
								{subagentTypes}
							/>
						{:else}
							<EmptyState
								icon={FileText}
								title="No file activity recorded"
								description="File operations will appear here when files are accessed"
							/>
						{/if}
					</div>
				</Tabs.Content>

				<!-- Subagents Tab (sessions only) -->
				{#if isMainSession(entity)}
					<Tabs.Content value="agents" class="animate-fade-in">
						<div class="space-y-4">
							<div>
								<h2 class="text-lg font-semibold text-[var(--text-primary)]">
									Subagents ({entity.subagents?.length || 0})
								</h2>
								<p class="text-sm text-[var(--text-muted)]">
									Agents spawned during this session, grouped by type
								</p>
							</div>

							{#if groupedSubagents.length > 0}
								<div class="space-y-4">
									{#each groupedSubagents as [type, agents] (type)}
										<SubagentGroup
											{type}
											{agents}
											projectEncoded={encodedName}
											sessionSlug={entity?.uuid?.slice(0, 8) || sessionSlug}
											liveSubagents={liveStatus?.subagents ?? {}}
										/>
									{/each}
								</div>
							{:else}
								<div
									class="flex flex-col items-center justify-center rounded-lg border border-dashed border-[var(--border)] py-12"
								>
									<Users
										size={32}
										strokeWidth={1.5}
										class="text-[var(--text-muted)]/50"
									/>
									<p class="mt-2 text-sm text-[var(--text-muted)]">
										No subagents were spawned during this session
									</p>
								</div>
							{/if}
						</div>
					</Tabs.Content>

					<!-- Skills Tab (sessions only, when skills exist) -->
					{#if skillsArray.length > 0}
						<Tabs.Content value="skills" class="animate-fade-in">
							<SkillsPanel skills={skillsArray} projectEncodedName={encodedName} />
						</Tabs.Content>
					{/if}

					<!-- Commands Tab (sessions only, when commands exist) -->
					{#if commandsArray.length > 0}
						<Tabs.Content value="commands" class="animate-fade-in">
							<CommandsPanel
								commands={commandsArray}
								projectEncodedName={encodedName}
							/>
						</Tabs.Content>
					{/if}
				{/if}

				<!-- Analytics Tab -->
				<Tabs.Content value="analytics" class="animate-fade-in">
					<div class="space-y-6">
						<div>
							<h2 class="text-lg font-semibold text-[var(--text-primary)]">
								{isSubagentSession(entity) ? 'Agent' : 'Session'} Analytics
							</h2>
							<p class="text-sm text-[var(--text-muted)]">
								Detailed usage metrics for this {entityLabel}
							</p>
						</div>

						<StatsGrid stats={analyticsStats} columns={5} />

						{#if toolsArray.length > 0}
							<div class="grid gap-6 lg:grid-cols-2">
								<ToolUsageTable tools={toolsArray} totalCalls={totalToolCalls} />
								<ToolsChart toolsUsed={toolsUsedRecord} />
							</div>
						{:else}
							<EmptyState
								icon={BarChart3}
								title="No tools used during this {entityLabel}"
								description="Tool usage statistics will appear here when tools are used"
							/>
						{/if}
					</div>
				</Tabs.Content>
			</Tabs.Root>
		{/if}
	{:else}
		<SessionDetailSkeleton />
	{/if}
</div>

<!-- Session Ended Toast Notification -->
{#if sessionEnded}
	<div
		class="
			fixed bottom-4 right-4 z-50
			flex items-center gap-2.5
			px-4 py-3
			bg-[var(--bg-subtle)]
			border border-[var(--border)]
			rounded-lg shadow-lg
			animate-fade-in
		"
	>
		<div class="w-2.5 h-2.5 rounded-full bg-[var(--text-muted)]"></div>
		<span class="text-sm font-medium text-[var(--text-primary)]">
			{entity && isSubagentSession(entity) ? 'Agent' : 'Session'} Ended
		</span>
		<button
			onclick={() => (sessionEnded = false)}
			class="ml-2 p-0.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors rounded"
			aria-label="Dismiss"
		>
			<X size={14} strokeWidth={2} />
		</button>
	</div>
{/if}
