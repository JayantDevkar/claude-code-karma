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
		Ticket as TicketIcon,
		Search,
		Activity,
		AlarmClock,
		BarChart2,
		CheckSquare,
		Tag,
		Layers,
		Play,
		Calendar,
		GitBranch,
		Link2,
		Sparkles,
		ChevronRight,
		ChevronLeft,
		Copy,
		Check,
		Terminal
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
	import { SessionTicketsSection } from '$lib/components/tickets';
	import SessionShellsSection from '$lib/components/shells/SessionShellsSection.svelte';
	import SessionCronSection from '$lib/components/cron/SessionCronSection.svelte';
	import ConversationHeader from './ConversationHeader.svelte';
	import CustomIcon from '$lib/components/icons/Icon.svelte';
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
		PlanDetail,
		SessionTicketRow
	} from '$lib/api-types';
	import { isSubagentSession, isMainSession } from '$lib/api-types';
	import {
		formatDuration,
		formatTokens,
		formatCost,
		formatDateFull,
		getProjectName,
		getSubagentTypeDisplayName,
		getSessionDisplayName,
		getSubagentColorVars,
		cleanAgentIdForDisplay,
		calculateSubagentDuration,
		truncate
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
		/** Pre-loaded tickets linked to this session (Tickets tab seed). */
		tickets?: SessionTicketRow[];
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
		plan = null,
		tickets = []
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
	// svelte-ignore state_referenced_locally
	let entityData = $state<ConversationEntity | null>(initialEntity);

	// Derive entity for read access
	const entity = $derived(entityData);

	// Mutable state for live updates - initialize from props
	let timelineEvents = $state<TimelineEvent[]>(getInitialTimeline());
	let fileActivities = $state<FileActivity[]>(getInitialFileActivity());
	let toolsArray = $state<ToolUsage[]>(getInitialTools());
	// svelte-ignore state_referenced_locally
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
	// svelte-ignore state_referenced_locally
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

	// Track whether this specific subagent has completed (while parent may still be live)
	const isSubagentCompleted = $derived.by(() => {
		if (!entity || !isSubagentSession(entity) || !liveStatus) return false;
		const agentState = liveStatus.subagents?.[entity.agent_id];
		return agentState?.status === 'completed' || agentState?.status === 'error';
	});

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

		if (isSubagentCompleted || timeSinceLastChange >= IDLE_THRESHOLD) {
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
					// Skip data refresh if this specific subagent has completed
					// (parent session is still live, but this agent is done)
					if (!isSubagentCompleted) {
						await refreshData(signal);

						// Check for changes and update lastChangeTime (only if not aborted)
						if (!signal.aborted && detectChanges()) {
							lastChangeTime = Date.now();
						}
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
	// Tickets sits before analytics for main sessions, matching the
	// project-page tab pattern (Memory · Tickets · Analytics).
	let validTabs = $derived.by(() => {
		const base: string[] = ['overview'];
		if (plan) base.push('plan');
		base.push('timeline', 'tasks', 'files');
		if (entity && isMainSession(entity)) {
			base.push('agents');
			if (skillsArray.length > 0) base.push('skills');
			if (commandsArray.length > 0) base.push('commands');
			base.push('tickets', 'shells', 'cron');
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
				footnote: 'Pay-as-you-go API rate — not your subscription cost',
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

	// ── Rail + Drawer state (main sessions only) ────────────────────────────────
	type DrawerKey =
		| 'overview'
		| 'files'
		| 'analytics'
		| 'tasks'
		| 'agents'
		| 'plan'
		| 'skills'
		| 'commands'
		| 'shells'
		| 'tickets'
		| 'cron';

	let activeDrawer = $state<DrawerKey | null>(null);
	let drawerOpen = $state(false);
	let drawerWidth = $state(296);
	let resumeCopied = $state(false);
	let expandedAgentIds = $state<Set<string>>(new Set());

	// null = unknown (show icon by default), 0 = confirmed empty (hide icon), >0 = has shells
	let shellCount = $state<number | null>(null);
	let cronCount = $state<number | null>(null);

	$effect(() => {
		if (!browser || !sessionUuid || !entity || !isMainSession(entity)) return;
		const uuid = sessionUuid;
		fetch(`${API_BASE}/sessions/${uuid}/cron`)
			.then((r) => r.ok ? r.json() : null)
			.then((data) => { if (data) cronCount = (data.jobs ?? []).length; })
			.catch(() => {});
	});

	// Pre-fetch shell count so the rail item only appears for sessions that actually have shells.
	// Only hide the icon when we get a confirmed empty response — not on 404/error (e.g. live sessions
	// not yet in the DB will 404, but they may well have shells).
	$effect(() => {
		if (!browser || !sessionUuid || !entity || !isMainSession(entity)) return;
		const uuid = sessionUuid;
		fetch(`${API_BASE}/sessions/${uuid}/shells?include_polls=false`)
			.then((r) => {
				if (!r.ok) return; // Don't hide on 404 or other errors
				return r.json();
			})
			.then((data) => {
				if (data) shellCount = (data.shells ?? []).length;
			})
			.catch(() => {});
	});
	let resumeCopyTimeout: ReturnType<typeof setTimeout> | null = null;

	function toggleDrawer(key: DrawerKey) {
		if (activeDrawer === key) {
			drawerOpen = !drawerOpen;
		} else {
			activeDrawer = key;
			drawerOpen = true;
		}
	}

	type RailItem = { key: DrawerKey; icon: typeof Info | null; iconName?: string; label: string; disabled: boolean; disabledTip: string };

	const railItems = $derived.by<RailItem[]>(() => {
		const isMain = entity ? isMainSession(entity) : false;
		const items: RailItem[] = [
			{ key: 'overview',  icon: Info,        label: 'Overview',  disabled: false, disabledTip: '' },
			{ key: 'files',     icon: FileText,    label: 'Files',     disabled: fileActivities.length === 0, disabledTip: 'No file activity in this session' },
			{ key: 'analytics', icon: null, iconName: 'analytics', label: 'Analytics', disabled: false, disabledTip: '' },
			{ key: 'tasks',     icon: CheckSquare, label: 'Tasks',     disabled: tasksArray.length === 0, disabledTip: 'No tasks in this session' },
		];
		if (isMain) {
			const agentCount = (entity as { subagents?: unknown[] }).subagents?.length ?? 0;
			items.push({ key: 'agents',   icon: null, iconName: 'agents',  label: 'Agents',   disabled: agentCount === 0,          disabledTip: 'No agents in this session' });
			items.push({ key: 'plan',     icon: null, iconName: 'plans',   label: 'Plan',     disabled: !plan,                     disabledTip: 'No plan in this session' });
			items.push({ key: 'skills',   icon: null, iconName: 'skills',  label: 'Skills',   disabled: skillsArray.length === 0,  disabledTip: 'No skills in this session' });
			items.push({ key: 'commands', icon: Terminal,                  label: 'Commands', disabled: commandsArray.length === 0, disabledTip: 'No commands in this session' });
			items.push({ key: 'shells',   icon: null, iconName: 'shells',  label: 'Shells',   disabled: shellCount === 0,           disabledTip: 'No background shells in this session' });
			items.push({ key: 'cron',     icon: null, iconName: 'cron',    label: 'Cron',     disabled: cronCount === 0,            disabledTip: 'No cron jobs in this session' });
			items.push({ key: 'tickets',  icon: null, iconName: 'tickets', label: 'Tickets',  disabled: false,                     disabledTip: '' });
		}
		return items;
	});

	const enabledRailItems = $derived(railItems.filter((i) => !i.disabled));
	const drawerTitle = $derived(railItems.find((i) => i.key === activeDrawer)?.label ?? '');
	const activeDrawerIdx = $derived(enabledRailItems.findIndex((i) => i.key === activeDrawer));

	function cycleDrawer(dir: 1 | -1) {
		if (activeDrawer === null) return;
		const next = (activeDrawerIdx + dir + enabledRailItems.length) % enabledRailItems.length;
		activeDrawer = enabledRailItems[next].key;
		drawerOpen = true;
	}

	async function handleResumeCopy() {
		if (!entity || isSubagentSession(entity) || !entity.uuid) return;
		try {
			await navigator.clipboard.writeText(`claude --resume ${entity.uuid}`);
		} catch {
			// fallback: do nothing
		}
		resumeCopied = true;
		if (resumeCopyTimeout) clearTimeout(resumeCopyTimeout);
		resumeCopyTimeout = setTimeout(() => {
			resumeCopied = false;
		}, 1500);
	}
</script>

<!-- ═══════════════════════════════════════════════════════════════════
     MAIN SESSION — new timeline-first layout with rail + drawer
     ═══════════════════════════════════════════════════════════════════ -->
{#if !isStarting && entity && isMainSession(entity)}
	{@const sessionEntity = entity}
	{@const sessionTitle = getSessionDisplayName(
		sessionEntity.session_titles,
		sessionEntity.slug,
		sessionEntity.uuid,
		sessionEntity.chain_title
	)}
	{@const shortId = sessionEntity.uuid?.slice(0, 8) ?? ''}
	{@const primaryModel = sessionEntity.models_used?.[0] ?? null}
	{@const primaryBranch = sessionEntity.git_branches?.[0] ?? null}

	<!-- Full-viewport column: negate the layout's px-6 py-8 padding -->
	<div
		class="-mx-6 -my-8 flex flex-col overflow-hidden"
		style="height: calc(100vh - 56px);"
	>
		<!-- ── Session Header ─────────────────────────────────────────────── -->
		<div
			class="flex-shrink-0 bg-[var(--bg-base)]"
			style="padding: 13px 24px 14px;"
		>
			<!-- Breadcrumb row -->
			<div class="flex items-center gap-1 mb-2" style="font-size: 11px; color: var(--text-faint);">
				<a href="/" class="hover:text-[var(--text-muted)] transition-colors" style="color: var(--text-faint);">Dashboard</a>
				<span style="color: var(--border);">/</span>
				<a href="/projects" class="hover:text-[var(--text-muted)] transition-colors" style="color: var(--text-faint);">Projects</a>
				<span style="color: var(--border);">/</span>
				<a href="/projects/{encodedName}" class="hover:text-[var(--text-muted)] transition-colors" style="color: var(--text-faint);">{getProjectName(projectPath || '')}</a>
				<span style="color: var(--border);">/</span>
				<span style="color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">{shortId}</span>
			</div>

			<!-- Title row -->
			<div class="flex items-start justify-between gap-4">
				<div class="min-w-0 flex-1">
					<!-- Session title -->
					<h1
						class="leading-[1.3] text-[var(--text-primary)]"
						style="font-size: 17px; font-weight: 700; letter-spacing: -0.02em; text-wrap: pretty;"
					>
						{sessionTitle}
					</h1>

					<!-- Metadata chips row -->
					<div class="flex items-center flex-wrap mt-2" style="gap: 6px;">
						<!-- Session ID chip -->
						<span
							class="inline-flex items-center"
							style="font-size: 10.5px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 4px; padding: 2px 7px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;"
						>#{shortId}</span>

						<!-- Date -->
						{#if sessionEntity.start_time}
							<span class="inline-flex items-center gap-1" style="font-size: 11px; color: var(--text-muted);">
								<Calendar size={11} color="var(--text-faint)" />
								{formatDateFull(sessionEntity.start_time)}
							</span>
						{/if}

						<!-- Duration -->
						{#if sessionEntity.duration_seconds}
							<span class="inline-flex items-center gap-1" style="font-size: 11px; color: var(--text-muted);">
								<Clock size={11} color="var(--text-faint)" />
								{formatDuration(sessionEntity.duration_seconds)}
							</span>
						{/if}

						<!-- Model chip -->
						{#if primaryModel}
							<span
								class="inline-flex items-center gap-1"
								style="font-size: 10.5px; font-weight: 500; color: var(--nav-purple); background: var(--nav-purple-subtle); border: 1px solid color-mix(in srgb, var(--nav-purple) 25%, transparent); border-radius: 4px; padding: 2px 7px;"
							>
								<Sparkles size={10} color="var(--nav-purple)" />
								{primaryModel}
							</span>
						{/if}

						<!-- Git branch chip -->
						{#if primaryBranch}
							<span
								class="inline-flex items-center gap-1"
								style="font-size: 10.5px; font-weight: 500; color: var(--nav-teal); background: var(--nav-teal-subtle); border: 1px solid color-mix(in srgb, var(--nav-teal) 25%, transparent); border-radius: 4px; padding: 2px 7px;"
							>
								<GitBranch size={10} color="var(--nav-teal)" />
								{primaryBranch}
							</span>
						{/if}

						<!-- Chain position chip -->
						{#if sessionEntity.chain_info}
							{@const ci = sessionEntity.chain_info}
							<span
								class="inline-flex items-center gap-1"
								style="font-size: 10.5px; color: var(--text-muted); background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 4px; padding: 2px 7px;"
							>
								<Link2 size={10} color="var(--text-faint)" />
								Session {ci.position + 1} of {ci.total}
							</span>
						{/if}

						<!-- Cost -->
						{#if sessionEntity.total_cost}
							<span style="font-size: 11px; color: var(--text-muted);">{formatCost(sessionEntity.total_cost)}</span>
						{/if}

						<!-- Live status -->
						{#if liveStatus && liveStatus.status !== 'ended'}
							{@const liveColors: Record<string, string> = {
								starting: '#7c3aed', active: '#16a34a', idle: '#d97706',
								waiting: '#0891b2', stopped: '#94a3b8', stale: '#dc2626', ended: '#cbd5e1'
							}}
							{@const liveColor = liveColors[liveStatus.status] ?? '#94a3b8'}
							<span
								class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full"
								style="background: color-mix(in srgb, {liveColor} 10%, transparent); border: 1px solid color-mix(in srgb, {liveColor} 30%, transparent);"
							>
								<span
									class="w-1.5 h-1.5 rounded-full"
									class:animate-pulse={['starting','active'].includes(liveStatus.status)}
									style="background: {liveColor};"
								></span>
								<span style="font-size: 10.5px; font-weight: 500; color: {liveColor};">{liveStatus.status}</span>
							</span>
						{/if}

						<!-- Syncing indicator -->
						{#if isRefreshing}
							<span class="inline-flex items-center gap-1" style="font-size: 10.5px; color: var(--nav-teal);">
								<RefreshCw size={10} class="animate-spin" color="var(--nav-teal)" />
								Syncing
							</span>
						{/if}
					</div>
				</div>

				<!-- Right: tail toggle (live only) + Resume button -->
				<div class="flex items-center gap-2 flex-shrink-0">
					{#if isCurrentlyLive && timelineEvents.length > 0}
						<button
							onclick={toggleTailing}
							aria-pressed={isTailing}
							title={isTailing ? 'Stop tailing — show all events' : 'Tail live events'}
							class="inline-flex items-center gap-1 transition-all"
							style="
								padding: 5px 10px;
								border-radius: 7px;
								border: 1px solid {isTailing ? 'color-mix(in srgb, var(--nav-green) 30%, transparent)' : 'var(--border)'};
								background: {isTailing ? 'var(--nav-green-subtle)' : 'var(--bg-base)'};
								font-size: 11px;
								font-weight: 500;
								color: {isTailing ? 'var(--nav-green)' : 'var(--text-muted)'};
								box-shadow: 0 1px 2px rgba(0,0,0,0.04);
							"
						>
							<ArrowDown size={11} strokeWidth={2} class={isTailing ? 'animate-pulse' : ''} />
							Tail
						</button>
					{/if}

					<!-- Resume button -->
					<button
						onclick={handleResumeCopy}
						class="inline-flex items-center gap-1.5 transition-all"
						style="
							padding: 7px 14px;
							border: 1px solid var(--border);
							border-radius: 7px;
							background: var(--bg-base);
							font-size: 12px;
							font-weight: 500;
							color: {resumeCopied ? 'var(--nav-green)' : 'var(--text-primary)'};
							box-shadow: 0 1px 2px rgba(0,0,0,0.04);
							white-space: nowrap;
						"
						title="Copy: claude --resume {sessionEntity.uuid}"
					>
						{#if resumeCopied}
							<Check size={12} color="var(--nav-green)" />
							Copied!
						{:else}
							<Play size={12} />
							Resume
						{/if}
					</button>
				</div>
			</div>
		</div>

		<!-- ── Main content row ───────────────────────────────────────────── -->
		<div class="flex flex-1 min-h-0" style="gap: 10px; padding: 8px 0 8px; overflow: hidden; align-items: stretch;">

			<!-- ── Timeline column ─────────────────────────────────────────── -->
			<div class="flex-1 flex flex-col overflow-hidden min-w-0" style="background: var(--bg-base);">
				{#if timelineEvents.length > 0}
					<div class="flex-1 overflow-y-auto" style="scrollbar-width: none;">
						<TimelineRail
							events={timelineEvents}
							isLive={isCurrentlyLive}
							{isTailing}
							onToggleTailing={toggleTailing}
							{currentAgentId}
							{projectPath}
							projectEncoded={encodedName}
							{sessionSlug}
							searchQuery={showConversationSearch ? conversationSearchQuery : ''}
							onSearchMatchCount={(count) => { searchMatchCount = count; }}
							onCurrentMatchChange={(idx) => { currentSearchMatch = idx; }}
							contained={true}
						/>
					</div>
				{:else}
					<div class="flex-1 flex items-center justify-center">
						<EmptyState icon={Clock} title="No timeline events yet" description="Events will appear here as the session progresses" />
					</div>
				{/if}
			</div>

			<!-- ── Right group: drawer + rail, no gap between them ──────────── -->
			<div class="flex flex-shrink-0 overflow-hidden" style="border-radius: 12px; background: var(--bg-subtle);">

			<!-- ── Drawer ────────────────────────────────────────────────────── -->
			{#if drawerOpen && activeDrawer !== null}
				<div
					class="flex flex-col overflow-hidden flex-shrink-0"
					style="width: 350px; border-right: 1px solid var(--border);"
				>
					<!-- Drawer header -->
					<div class="flex items-center justify-between flex-shrink-0" style="height: 44px; padding: 0 16px; border-bottom: 1px solid var(--border);">
						<span style="font-size: 13px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em;">{drawerTitle}</span>
						<div class="flex items-center" style="gap: 2px;">
							<button onclick={() => cycleDrawer(-1)} disabled={activeDrawerIdx <= 0} style="width: 26px; height: 26px; border: none; background: none; color: var(--text-muted); opacity: {activeDrawerIdx <= 0 ? 0.25 : 1}; cursor: {activeDrawerIdx <= 0 ? 'default' : 'pointer'}; display: flex; align-items: center; justify-content: center; border-radius: 4px;" aria-label="Previous drawer"><ChevronLeft size={15} /></button>
							<button onclick={() => cycleDrawer(1)} disabled={activeDrawerIdx >= enabledRailItems.length - 1} style="width: 26px; height: 26px; border: none; background: none; color: var(--text-muted); opacity: {activeDrawerIdx >= enabledRailItems.length - 1 ? 0.25 : 1}; cursor: {activeDrawerIdx >= railItems.length - 1 ? 'default' : 'pointer'}; display: flex; align-items: center; justify-content: center; border-radius: 4px;" aria-label="Next drawer"><ChevronRight size={15} /></button>
							<button onclick={() => (drawerOpen = false)} style="width: 26px; height: 26px; border: none; background: none; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; justify-content: center; border-radius: 4px;" aria-label="Close drawer"><X size={15} /></button>
						</div>
					</div>
					<!-- Drawer body -->
					<div class="flex-1 overflow-y-auto" style="padding: 20px 20px 24px; scrollbar-width: none;">
						{#if activeDrawer === 'overview'}
							<ConversationOverview entity={sessionEntity} {toolsArray} {totalToolCalls} projectEncoded={encodedName} {continuationSession} {continuationLoading} {continuationError} />
						{:else if activeDrawer === 'files'}
							{#if fileActivities.length > 0}
								<FileActivityTable activities={fileActivities} {projectPath} {currentAgentId} {subagentTypes} />
							{:else}
								<EmptyState icon={FileText} title="No file activity" description="File operations will appear here" />
							{/if}
						{:else if activeDrawer === 'analytics'}
							{@const totalTokens = (entity?.total_input_tokens || 0) + (entity?.total_output_tokens || 0)}
							{@const inPct = totalTokens > 0 ? ((entity?.total_input_tokens || 0) / totalTokens) * 100 : 50}
							{@const outPct = totalTokens > 0 ? ((entity?.total_output_tokens || 0) / totalTokens) * 100 : 50}
							{@const maxToolCount = toolsArray.length > 0 ? Math.max(...toolsArray.map(t => t.count)) : 1}
							{@const sortedTools = [...toolsArray].sort((a, b) => b.count - a.count)}
							<div class="flex flex-col gap-4">

								<!-- Key metrics: 2-col grid -->
								<div class="grid grid-cols-2 gap-2">
									<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
										<p class="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1">Cost</p>
										<p class="text-base font-bold text-[var(--text-primary)]">{formatCost(entity?.total_cost)}</p>
										<p class="text-[10px] text-[var(--text-muted)] mt-0.5 leading-tight">API rate</p>
									</div>
									<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
										<p class="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1">Duration</p>
										<p class="text-base font-bold text-[var(--text-primary)]">{formatDuration(entity?.duration_seconds)}</p>
									</div>
									<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
										<p class="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1">Cache hits</p>
										<p class="text-base font-bold text-[var(--text-primary)]">{((entity?.cache_hit_rate || 0) * 100).toFixed(1)}%</p>
									</div>
									<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
										<p class="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1">Tools used</p>
										<p class="text-base font-bold text-[var(--text-primary)]">{toolsArray.length}</p>
										<p class="text-[10px] text-[var(--text-muted)] mt-0.5">{totalToolCalls} calls</p>
									</div>
								</div>

								<!-- Token breakdown -->
								<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
									<div class="flex items-baseline justify-between mb-2">
										<p class="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">Tokens</p>
										<p class="text-xs font-bold text-[var(--text-primary)] font-mono">{formatTokens(totalTokens)}</p>
									</div>
									<div class="flex h-2 rounded-full overflow-hidden bg-[var(--bg-muted)]">
										<div class="bg-[var(--accent)] transition-all" style="width: {inPct}%" title="Input"></div>
										<div class="bg-[var(--nav-teal)] transition-all" style="width: {outPct}%" title="Output"></div>
									</div>
									<div class="flex justify-between mt-1.5">
										<span class="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
											<span class="w-1.5 h-1.5 rounded-full bg-[var(--accent)]"></span>
											In · {formatTokens(entity?.total_input_tokens)}
										</span>
										<span class="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
											Out · {formatTokens(entity?.total_output_tokens)}
											<span class="w-1.5 h-1.5 rounded-full bg-[var(--nav-teal)]"></span>
										</span>
									</div>
								</div>

								<!-- Tool usage -->
								{#if sortedTools.length > 0}
									<div class="flex flex-col gap-1">
										<p class="text-[10px] uppercase tracking-wide text-[var(--text-muted)] font-medium mb-1">Tool usage</p>
										{#each sortedTools as tool}
											{@const pct = (tool.count / maxToolCount) * 100}
											<div class="flex items-center gap-2 group">
												<span class="w-28 shrink-0 text-[11px] font-mono text-[var(--text-secondary)] truncate" title={tool.tool_name}>{tool.tool_name}</span>
												<div class="flex-1 h-1.5 rounded-full bg-[var(--bg-muted)] overflow-hidden">
													<div class="h-full bg-[var(--accent)]/70 rounded-full transition-all" style="width: {pct}%"></div>
												</div>
												<span class="shrink-0 w-6 text-right font-mono text-[10px] text-[var(--text-muted)]">{tool.count}</span>
											</div>
										{/each}
									</div>
								{/if}

							</div>
						{:else if activeDrawer === 'tasks'}
							<TasksTab tasks={tasksArray} />
						{:else if activeDrawer === 'agents'}
							{@const allAgents = groupedSubagents.flatMap(([, agents]) => agents)}
							{#if allAgents.length > 0}
								<div class="flex flex-col gap-2">
									<span class="text-[10px] uppercase tracking-wide font-medium text-[var(--text-muted)]">{allAgents.length} agent{allAgents.length !== 1 ? 's' : ''}</span>
									{#each allAgents as agent}
										{@const cv = getSubagentColorVars(agent.subagent_type)}
										{@const live = liveStatus?.subagents?.[agent.agent_id]}
										{@const duration = calculateSubagentDuration(live?.started_at ?? null, live?.completed_at ?? null)}
										{@const totalCalls = Object.values(agent.tools_used).reduce((a, b) => a + b, 0)}
										{@const topTools = Object.entries(agent.tools_used).sort((a,b) => b[1]-a[1]).slice(0,3)}
										{@const displayId = cleanAgentIdForDisplay(agent.agent_id)}
										{@const agentHref = `/projects/${encodedName}/${sessionEntity?.uuid?.slice(0,8) || sessionSlug}/agents/${agent.agent_id}`}
										<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] overflow-hidden" style="border-left: 2px solid {cv.color};">
											<div class="px-3 py-2.5">
												<!-- Row 1: type badge + id + running dot + duration -->
												<div class="flex items-center gap-2">
													<span class="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full" style="background: {cv.subtle}; color: {cv.color};">{agent.subagent_type ?? 'Agent'}</span>
													{#if live?.status === 'running'}
														<span class="shrink-0 w-1.5 h-1.5 rounded-full animate-pulse" style="background: var(--success);"></span>
													{/if}
													<a href={agentHref} class="flex-1 min-w-0 font-mono text-[11px] text-[var(--accent)] hover:underline truncate">{displayId}</a>
													{#if duration !== null}
														<span class="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">{formatDuration(duration)}</span>
													{/if}
												</div>
												<!-- Row 2: prompt snippet (tap to expand) -->
												{#if agent.initial_prompt}
													{@const isAgentExpanded = expandedAgentIds.has(agent.agent_id)}
													{@const isLongPrompt = agent.initial_prompt.length > 160}
													<button
														type="button"
														onclick={() => {
															const next = new Set(expandedAgentIds);
															if (next.has(agent.agent_id)) next.delete(agent.agent_id);
															else next.add(agent.agent_id);
															expandedAgentIds = next;
														}}
														class="mt-1.5 text-left w-full"
													>
														<p class="text-[10px] text-[var(--text-muted)] leading-relaxed {isAgentExpanded ? 'whitespace-pre-wrap' : 'line-clamp-2'}">{agent.initial_prompt}</p>
														{#if isLongPrompt}
															<span class="text-[10px] text-[var(--accent)] hover:underline">{isAgentExpanded ? 'Show less' : 'Show more'}</span>
														{/if}
													</button>
												{/if}
												<!-- Row 3: stats + top tools -->
												<div class="mt-1.5 flex items-center gap-1.5 flex-wrap">
													<span class="text-[10px] text-[var(--text-muted)] font-mono">{agent.message_count} msgs</span>
													<span class="text-[10px] text-[var(--text-muted)]">·</span>
													<span class="text-[10px] text-[var(--text-muted)] font-mono">{totalCalls} calls</span>
													{#each topTools as [tool, count]}
														<span class="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border)]/60 font-mono text-[var(--text-secondary)]">{tool} ×{count}</span>
													{/each}
												</div>
											</div>
										</div>
									{/each}
								</div>
							{:else}
								<EmptyState icon={Cpu} title="No subagents" description="No agents were spawned" />
							{/if}
						{:else if activeDrawer === 'plan'}
							{#if plan}
								<PlanViewer {plan} embedded={true} />
							{:else}
								<EmptyState icon={FileEdit} title="No plan" description="No plan was created for this session" />
							{/if}
						{:else if activeDrawer === 'skills'}
							<SkillsPanel skills={skillsArray} projectEncodedName={encodedName} />
						{:else if activeDrawer === 'commands'}
							<CommandsPanel commands={commandsArray} projectEncodedName={encodedName} />
						{:else if activeDrawer === 'shells'}
							{#if sessionUuid}
								<SessionShellsSection {sessionUuid} onLoaded={(n) => (shellCount = n)} />
							{:else}
								<p class="text-sm text-[var(--text-muted)]">Session UUID unavailable.</p>
							{/if}
						{:else if activeDrawer === 'cron'}
							{#if sessionUuid}
								<SessionCronSection {sessionUuid} projectEncodedName={encodedName} />
							{:else}
								<p class="text-sm text-[var(--text-muted)]">Session UUID unavailable.</p>
							{/if}
						{:else if activeDrawer === 'tickets'}
							{#if sessionUuid}
								<SessionTicketsSection {sessionUuid} {sessionSlug} initial={tickets} />
							{:else}
								<p class="text-sm text-[var(--text-muted)]">Session UUID unavailable.</p>
							{/if}
						{/if}
					</div>
					<!-- Drawer footer legends -->
					{#if activeDrawer === 'shells'}
						<div class="flex-shrink-0 flex items-center gap-4 flex-wrap" style="padding: 10px 20px; border-top: 1px solid var(--border);">
							<span class="flex items-center gap-1.5 text-[10px] text-[var(--text-faint)]"><span class="w-1.5 h-1.5 rounded-full" style="background: var(--success);"></span>running</span>
							<span class="flex items-center gap-1.5 text-[10px] text-[var(--text-faint)]"><span class="w-1.5 h-1.5 rounded-full" style="background: var(--info);"></span>done</span>
							<span class="flex items-center gap-1.5 text-[10px] text-[var(--text-faint)]"><span class="w-1.5 h-1.5 rounded-full" style="background: var(--error);"></span>killed</span>
							<span class="flex items-center gap-1.5 text-[10px] text-[var(--text-faint)]"><span class="w-1.5 h-1.5 rounded-full" style="background: var(--warning);"></span>timeout</span>
							<span class="flex items-center gap-1.5 text-[10px] text-[var(--text-faint)]"><span class="w-1.5 h-1.5 rounded-full" style="background: var(--text-faint);"></span>ended</span>
						</div>
					{:else if activeDrawer === 'tasks'}
						<div class="flex-shrink-0 flex items-center justify-center gap-4 flex-wrap" style="padding: 10px 20px; border-top: 1px solid var(--border);">
							<span class="flex items-center gap-1.5 text-[10px] text-[var(--text-faint)]"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/></svg>Pending</span>
							<span class="flex items-center gap-1.5 text-[10px]" style="color: var(--nav-blue);"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>In Progress</span>
							<span class="flex items-center gap-1.5 text-[10px]" style="color: var(--success);"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>Completed</span>
						</div>
					{/if}
				</div>
			{/if}

			<!-- ── Rail: always at the right edge ───────────────────────────── -->
			<div
				class="flex flex-col items-center flex-shrink-0 overflow-y-auto"
				style="width: 68px; padding: 14px 0; gap: 6px; scrollbar-width: none;"
			>
				{#each railItems as item (item.key)}
					{@const isSelected = activeDrawer === item.key}
					{@const isOpen = isSelected && drawerOpen}
					{@const IconComponent = item.icon}
					{@const iconColor = isSelected ? 'var(--rail-active-icon)' : item.disabled ? 'var(--text-faint)' : 'var(--text-primary)'}
					<!-- Wrapper carries the tooltip — pointer-events on button are off when disabled so title fires from wrapper -->
					<span
						title={item.disabled ? item.disabledTip : item.label}
						style="display: flex; align-items: center; justify-content: center; width: 52px; height: 52px;"
					>
						<button
							onclick={() => toggleDrawer(item.key)}
							aria-pressed={isOpen}
							aria-disabled={item.disabled}
							class="relative flex items-center justify-center flex-shrink-0 transition-all duration-150"
							style="width: 52px; height: 52px; border-radius: 12px; border: none; cursor: {item.disabled ? 'default' : 'pointer'}; background: {isOpen ? 'var(--rail-active-bg)' : 'transparent'}; opacity: {isSelected ? 1 : item.disabled ? 0.3 : 0.85}; pointer-events: {item.disabled ? 'none' : 'auto'};"
						>
							{#if item.iconName}
								<CustomIcon name={item.iconName} size={22} strokeWidth={2} color={iconColor} />
							{:else if IconComponent}
								<IconComponent size={22} color={iconColor} strokeWidth={2.5} />
							{/if}
						</button>
					</span>
				{/each}
			</div>

			</div><!-- end right group -->
		</div>
	</div>

<!-- ═══════════════════════════════════════════════════════════════════
     STARTING SESSION placeholder
     ═══════════════════════════════════════════════════════════════════ -->
{:else if isStarting && liveSession}
	<div class="space-y-6">
		<PageHeader
			title={liveSession.session_id.slice(0, 8)}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/' },
				{ label: 'Projects', href: '/projects' },
				{ label: getProjectName(liveSession.cwd || ''), href: `/projects/${encodedName}` },
				{ label: liveSession.session_id.slice(0, 8) }
			]}
			subtitle="Session Starting"
			class="mb-0"
		/>
		<div class="flex flex-col items-center justify-center py-16 px-4 text-center rounded-lg border border-dashed border-[var(--nav-purple)]/40 bg-[var(--nav-purple-subtle)]">
			<div class="p-4 rounded-full bg-[var(--nav-purple)]/10 mb-4">
				<MessageCircle size={48} strokeWidth={1.5} class="text-[var(--nav-purple)]" />
			</div>
			<h3 class="text-lg font-medium text-[var(--text-primary)] mb-2">Waiting for First Message</h3>
			<p class="text-sm text-[var(--text-secondary)] max-w-md mb-6">
				This session has started but hasn't received its first prompt yet.
			</p>
			<div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--nav-purple)]/10 border border-[var(--nav-purple)]/30">
				<span class="w-2 h-2 rounded-full bg-[var(--nav-purple)] animate-pulse"></span>
				<span class="text-xs font-medium text-[var(--nav-purple)]">Starting</span>
			</div>
			<a
				href="/projects/{encodedName}"
				class="mt-6 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md border bg-[var(--bg-muted)] border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)] transition-colors"
			>
				<ArrowLeft size={16} strokeWidth={2} />
				Back to Project
			</a>
		</div>
	</div>

<!-- ═══════════════════════════════════════════════════════════════════
     SUBAGENT SESSION — keep original tab layout
     ═══════════════════════════════════════════════════════════════════ -->
{:else if entity && isSubagentSession(entity)}
	<div class="space-y-6">
		<ConversationHeader
			{entity}
			{encodedName}
			{sessionSlug}
			{projectPath}
			{parentSessionSlug}
			{liveStatus}
			{isRefreshing}
		/>

		{#if tabsReady}
			<Tabs.Root bind:value={activeTab} class="space-y-6">
				<Tabs.List class="flex items-center gap-1 p-1 bg-[var(--bg-subtle)] rounded-lg w-fit mx-auto border border-[var(--border)]">
					<TabsTrigger value="overview" icon={Info}>Overview</TabsTrigger>
					<TabsTrigger value="timeline" icon={Clock}>Timeline</TabsTrigger>
					<TabsTrigger value="tasks" icon={ListTodo}>
						Tasks
						{#if tasksArray.length > 0}
							<span class="text-xs font-mono text-[var(--text-muted)]">{tasksArray.filter((t) => t.status === 'completed').length}/{tasksArray.length}</span>
						{/if}
					</TabsTrigger>
					<TabsTrigger value="files" icon={FileText}>Files</TabsTrigger>
					<TabsTrigger value="analytics" icon={BarChart3}>Analytics</TabsTrigger>
				</Tabs.List>

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

				<Tabs.Content value="timeline" class="animate-fade-in">
					<div class="space-y-4">
						<div class="flex items-start justify-between gap-4">
							<div>
								<h2 class="text-lg font-semibold text-[var(--text-primary)]">Timeline</h2>
								<p class="text-sm text-[var(--text-muted)]">
									{#if isTailing && timelineEvents.length > TAIL_COUNT}
										Showing {TAIL_COUNT} of {timelineEvents.length} events
									{:else}
										Chronological sequence of events in this agent
									{/if}
								</p>
							</div>
							{#if isCurrentlyLive && timelineEvents.length > 0}
								<button
									onclick={toggleTailing}
									class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] border transition-all duration-150 shrink-0 {isTailing ? 'bg-[var(--success-subtle)] border-[var(--success)]/50 text-[var(--success)]' : 'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-muted)]'}"
									aria-pressed={isTailing}
								>
									<ArrowDown size={14} strokeWidth={2} class={isTailing ? 'animate-pulse' : ''} />
									Tail Events
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
								projectEncoded={encodedName}
								{sessionSlug}
								searchQuery={showConversationSearch ? conversationSearchQuery : ''}
								onSearchMatchCount={(count) => { searchMatchCount = count; }}
								onCurrentMatchChange={(idx) => { currentSearchMatch = idx; }}
							/>
						{:else}
							<EmptyState icon={Clock} title="No timeline events available" description="Timeline events will appear here as they occur" />
						{/if}
					</div>
				</Tabs.Content>

				<Tabs.Content value="tasks" class="animate-fade-in">
					<TasksTab tasks={tasksArray} />
				</Tabs.Content>

				<Tabs.Content value="files" class="animate-fade-in">
					{#if fileActivities.length > 0}
						<FileActivityTable activities={fileActivities} {projectPath} {currentAgentId} {subagentTypes} />
					{:else}
						<EmptyState icon={FileText} title="No file activity recorded" description="File operations will appear here when files are accessed" />
					{/if}
				</Tabs.Content>

				<Tabs.Content value="analytics" class="animate-fade-in">
					<div class="space-y-6">
						<StatsGrid stats={analyticsStats} columns={5} />
						{#if toolsArray.length > 0}
							<div class="grid gap-6 lg:grid-cols-2">
								<ToolUsageTable tools={toolsArray} totalCalls={totalToolCalls} />
								<ToolsChart toolsUsed={toolsUsedRecord} />
							</div>
						{:else}
							<EmptyState icon={BarChart3} title="No tools used" description="Tool usage statistics will appear here" />
						{/if}
					</div>
				</Tabs.Content>
			</Tabs.Root>
		{/if}
	</div>

<!-- ═══════════════════════════════════════════════════════════════════
     LOADING / ERROR state
     ═══════════════════════════════════════════════════════════════════ -->
{:else}
	<div class="space-y-6">
		<SessionDetailSkeleton />
	</div>
{/if}

<!-- Session Ended Toast Notification -->
{#if sessionEnded}
	<div
		class="fixed bottom-4 right-4 z-50 flex items-center gap-2.5 px-4 py-3 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg shadow-lg animate-fade-in"
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
