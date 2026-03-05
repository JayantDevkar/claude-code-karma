/**
 * API Type Definitions for Claude Code Karma
 * These interfaces match the FastAPI backend response schemas
 */

// ============================================
// Timeline Events
// ============================================

export type TimelineEventType =
	| 'prompt'
	| 'tool_call'
	| 'subagent_spawn'
	| 'thinking'
	| 'response'
	| 'todo_update'
	| 'command_invocation'
	| 'skill_invocation'
	| 'builtin_command';

export type EventImportance = 'high' | 'medium' | 'low';

export interface TimelineEvent {
	id: string;
	timestamp: string;
	event_type: TimelineEventType;
	title: string;
	summary?: string;
	actor: string;
	actor_type: 'main' | 'subagent';
	metadata: TimelineEventMetadata;
}

export interface TimelineEventMetadata {
	tool_name?: string;
	tool_id?: string;
	has_result?: boolean;
	result_status?: 'success' | 'error';
	result_content?: string;
	spawned_agent_id?: string;
	spawned_agent_slug?: string;
	subagent_type?: string;
	full_content?: string;
	full_thinking?: string;
	full_text?: string;
	todos?: TodoItem[];
	action?: string;
	count?: number;
	agent_id?: string;
	agent_slug?: string;
	parsed_output?: Record<string, string>;
	command_name?: string;
	is_plugin?: boolean;
	plugin?: string;
	image_attachments?: ImageAttachment[];
	[key: string]: unknown;
}

// ============================================
// Image Attachments
// ============================================

export interface ImageAttachment {
	media_type: string;
	data: string;
}

// ============================================
// Todo Items
// ============================================

export type TodoStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';

export interface TodoItem {
	id: string;
	content: string;
	status: TodoStatus;
	activeForm?: string;
}

// ============================================
// File Activity
// ============================================

export type FileOperation = 'read' | 'write' | 'edit' | 'delete' | 'search';

export interface FileActivity {
	timestamp: string;
	path: string;
	operation: FileOperation;
	actor: string;
	actor_type: 'main' | 'subagent';
	tool_name: string;
}

// ============================================
// Tool Usage
// ============================================

export interface ToolUsage {
	tool_name: string;
	count: number;
	by_actor?: Record<string, number>;
}

// ============================================
// Skill Usage
// ============================================

export type SkillCategory = 'bundled_skill' | 'plugin_skill' | 'custom_skill';

export interface SkillUsage {
	name: string;
	count: number;
	is_plugin: boolean;
	plugin: string | null;
	last_used: string | null;
	session_count: number;
	category?: SkillCategory;
	description?: string | null;
}

export type CommandCategory =
	| 'builtin_command'
	| 'bundled_skill'
	| 'plugin_skill'
	| 'plugin_command'
	| 'custom_skill'
	| 'user_command';

export interface CommandUsage {
	name: string;
	count: number;
	source?: 'builtin' | 'plugin' | 'project' | 'user' | 'unknown';
	plugin?: string | null;
	is_plugin?: boolean;
	category?: CommandCategory;
	description?: string | null;
	last_used?: string | null;
	session_count?: number;
	invocation_source?: string;
}

export interface CommandDetailResponse {
	name: string;
	description: string | null;
	category: CommandCategory;
	content: string | null;
	is_plugin: boolean;
	plugin: string | null;
	file_path: string | null;
	calls: number;
	main_calls: number;
	subagent_calls: number;
	manual_calls: number;
	auto_calls: number;
	session_count: number;
	first_used: string | null;
	last_used: string | null;
	trend: Array<{ date: string; calls: number; sessions: number }>;
	sessions: SessionSummary[];
	sessions_total: number;
}

// ============================================
// Analytics
// ============================================

export interface ProjectAnalytics {
	total_sessions: number;
	total_tokens: number;
	total_input_tokens: number;
	total_output_tokens: number;
	total_duration_seconds: number;
	estimated_cost_usd: number;
	models_used: Record<string, number>;
	cache_hit_rate: number;
	tools_used: Record<string, number>;
	sessions_by_date: Record<string, number>;
	projects_active: number;
	temporal_heatmap: number[][];
	peak_hours: number[];
	models_categorized: Record<string, number>;
	time_distribution: TimeDistribution;
	work_mode_distribution: WorkModeDistribution;
}

export interface TimeDistribution {
	morning_pct: number;
	afternoon_pct: number;
	evening_pct: number;
	night_pct: number;
	dominant_period: string;
}

export interface WorkModeDistribution {
	exploration_pct: number;
	building_pct: number;
	testing_pct: number;
	primary_mode: string;
}

export interface SessionAnalytics {
	total_cost: number;
	total_input_tokens: number;
	total_output_tokens: number;
	duration_seconds: number;
	cache_hit_rate: number;
	tools_used: Record<string, number>;
}

// ============================================
// Session
// ============================================

/**
 * Lightweight chain info embedded in session summaries.
 * Provides just enough info to show chain badges and handle URL disambiguation.
 */
export interface SessionChainInfoSummary {
	chain_id: string; // Chain identifier (slug)
	position: number; // Position in chain (0=first)
	total: number; // Total sessions in chain
	is_root: boolean; // First in chain
	is_latest: boolean; // Most recent in chain
}

export interface SessionSummary {
	uuid: string;
	slug: string;
	message_count: number;
	start_time: string;
	end_time?: string;
	duration_seconds?: number;
	models_used: string[];
	subagent_count: number;
	has_todos: boolean;
	todo_count?: number;
	initial_prompt?: string;
	git_branches: string[];
	status?: 'active' | 'completed' | 'error';
	error_message?: string;
	total_input_tokens?: number;
	total_output_tokens?: number;
	total_cost?: number;
	cache_hit_rate?: number;
	tools_used?: Record<string, number>;
	working_directories?: string[];
	project_path?: string;
	project_encoded_name?: string;
	project_slug?: string;
	project_display_name?: string;
	// Chain info - present when session is part of a resumed chain (multiple sessions with same slug)
	chain_info?: SessionChainInfoSummary;
	// Session titles - human-readable names generated by Claude (SessionTitleMessage)
	session_titles?: string[];
	chain_title?: string;
	/** Session origin: 'desktop' for Claude Desktop sessions, undefined for CLI */
	session_source?: 'desktop' | null;
	/** Session source: 'local' for this machine, 'remote' for synced from another machine */
	source?: 'local' | 'remote';
	/** User ID of the remote machine that produced this session */
	remote_user_id?: string;
	/** Machine ID of the remote machine that produced this session */
	remote_machine_id?: string;
}

export type SessionSourceFilter = 'all' | 'local' | 'remote';

/**
 * Structured compaction summary with trigger and token metadata.
 * Represents actual context compaction events (CompactBoundaryMessage).
 */
export interface CompactionSummary {
	summary: string;
	trigger?: 'auto' | 'manual';
	pre_tokens?: number;
	timestamp?: string;
}

export interface SessionDetail extends SessionSummary {
	timeline?: TimelineEvent[];
	files_accessed?: FileActivitySummary[];
	file_activity?: FileActivity[];
	subagents?: SubagentSummary[];
	messages?: Message[];
	todos?: TodoItem[];
	// Tasks (new task system with dependencies - v2.1.16+)
	tasks?: Task[];
	// Chain detection (lightweight flag)
	has_chain?: boolean;
	// Continuation session detection
	is_continuation_marker?: boolean;
	file_snapshot_count?: number;
	// Project context (summaries from PREVIOUS sessions loaded at session start)
	project_context_summaries?: string[];
	project_context_leaf_uuids?: string[];
	// Session titles (SessionTitleMessage - NOT compaction, just naming)
	session_titles?: string[];
	// Session compaction (TRUE compaction from CompactBoundaryMessage)
	was_compacted?: boolean;
	compaction_summary_count?: number;
	compaction_summaries?: CompactionSummary[];
	message_type_breakdown?: Record<string, number>;
	// Skill usage tracking
	skills_used?: SkillUsage[];
	// Command usage tracking (user-authored slash commands)
	commands_used?: CommandUsage[];
	// Image attachments from the initial prompt
	initial_prompt_images?: ImageAttachment[];
}

/**
 * Information about a session found by message UUID lookup.
 * Used to link continuation marker sessions to their continuation sessions.
 */
export interface ContinuationSessionInfo {
	session_uuid: string;
	project_encoded_name: string;
	slug: string | null;
}

export interface FileActivitySummary {
	path: string;
	operations: FileOperation[];
	read_count: number;
	write_count: number;
	edit_count: number;
}

/**
 * SubagentSummary matches the API response from /sessions/{uuid}/subagents
 */
export interface SubagentSummary {
	agent_id: string;
	slug: string | null;
	subagent_type: string | null;
	tools_used: Record<string, number>;
	message_count: number;
	initial_prompt: string | null;
}

/**
 * @deprecated Use SubagentSummary instead - this was the old transformed format
 */
export interface SubagentInfo {
	id: string;
	type: string;
	description?: string;
	start_time: string;
	end_time: string;
	duration_seconds: number;
}

export interface Message {
	role: 'user' | 'assistant';
	content: string;
	timestamp: string;
}

// ============================================
// Project
// ============================================

export interface Project {
	path: string;
	encoded_name: string;
	slug: string;
	display_name: string;
	session_count: number;
	agent_count: number;
	exists: boolean;
	is_git_repository: boolean;
	git_root_path?: string;
	is_nested_project: boolean;
	/** Start time of the most recent session (from project list API) */
	latest_session_time?: string;
	/** Sessions array (only populated in project detail API) */
	sessions?: SessionSummary[];
}

export interface BranchSummary {
	name: string;
	session_count: number;
	last_active?: string;
	is_active: boolean;
}

export interface BranchesData {
	branches: BranchSummary[];
	active_branches: string[];
	sessions_by_branch: Record<string, string[]>;
}

// ============================================
// UI Navigation Types
// ============================================

export interface Breadcrumb {
	label: string;
	href?: string;
}

// ============================================
// Filter Types
// ============================================

export type FilterCategory =
	| 'prompt'
	| 'tool_call'
	| 'subagent'
	| 'todo_update'
	| 'error'
	| 'thinking'
	| 'response'
	| 'big_response'
	| 'ask_user'
	| 'mcp_tool'
	| 'task'
	| 'skill'
	| 'command';

export interface FilterCounts {
	prompt: number;
	tool_call: number;
	subagent: number;
	todo_update: number;
	error: number;
	thinking: number;
	response: number;
	big_response: number;
	ask_user: number;
	mcp_tool: number;
	task: number;
	skill: number;
	command: number;
}

export interface TimeRangeFilter {
	type: 'preset' | 'custom';
	value: string;
	startDate?: Date;
	endDate?: Date;
}

// Analytics time filter types
export type AnalyticsFilterPeriod =
	| 'all'
	| '6h'
	| '12h'
	| '24h'
	| '48h'
	| 'this_week'
	| 'last_week'
	| '2_weeks_ago'
	| 'this_month'
	| 'last_month';

export interface AnalyticsFilterOption {
	id: AnalyticsFilterPeriod;
	label: string;
	group: 'Hours' | 'Weeks' | 'Months' | null;
}

// ============================================
// Stats Display
// ============================================

export type StatColor = 'blue' | 'green' | 'orange' | 'purple' | 'teal' | 'gray' | 'accent';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface StatItem {
	title: string;
	value: string | number;
	description?: string;
	// Using 'any' for icon to allow Lucide components which have complex signatures
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	icon?: any;
	color?: StatColor;
	tokenIn?: number;
	tokenOut?: number;
}

// ============================================
// Claude Code Settings (~/.claude/settings.json)
// ============================================

export type PermissionMode =
	| 'default'
	| 'acceptEdits'
	| 'plan'
	| 'bypassPermissions'
	| 'dontAsk';

export interface PermissionsConfig {
	allow?: string[];
	deny?: string[];
	defaultMode?: PermissionMode;
}

export interface StatusLineConfig {
	type: 'command' | 'disabled';
	command?: string;
	padding?: number;
}

export interface ClaudeSettings {
	permissions?: PermissionsConfig;
	statusLine?: StatusLineConfig;
	enabledPlugins?: Record<string, boolean>;
	alwaysThinkingEnabled?: boolean;
	cleanupPeriodDays?: number;
	env?: Record<string, string>;
	model?: string;
	hooks?: Record<string, unknown>;
}

// Permission mode options with labels and descriptions for the settings UI
export const PERMISSION_MODE_OPTIONS = [
	{
		label: 'Default',
		value: 'default' as PermissionMode,
		description: 'Prompts for permission on first use of each tool'
	},
	{
		label: 'Auto-accept Edits',
		value: 'acceptEdits' as PermissionMode,
		description: 'Auto-approves file edits; other tools still prompt'
	},
	{
		label: 'Plan Mode',
		value: 'plan' as PermissionMode,
		description: 'Read-only — Claude can analyze but not modify files or run commands'
	},
	{
		label: 'Pre-approved Only',
		value: 'dontAsk' as PermissionMode,
		description: 'Auto-denies tools unless explicitly allowed in the list below'
	},
	{
		label: 'Bypass All',
		value: 'bypassPermissions' as PermissionMode,
		description: 'Skips all permission checks. Only use in isolated environments'
	}
] as const;

// Retention period options for the settings UI
export const RETENTION_OPTIONS = [
	{ label: '30 days', value: 30 },
	{ label: '60 days', value: 60 },
	{ label: '90 days', value: 90 },
	{ label: 'Forever', value: 99999 }
] as const;

export type RetentionValue = (typeof RETENTION_OPTIONS)[number]['value'];

// ============================================
// Archived/History Types
// ============================================

export interface ArchivedPrompt {
	timestamp: string;
	display: string;
	session_id?: string;
}

export interface DateRange {
	start: string;
	end: string;
}

export interface ArchivedSession {
	session_id: string;
	first_prompt_preview: string;
	prompt_count: number;
	date_range: DateRange;
	is_orphan: boolean;
	prompts: ArchivedPrompt[];
}

export interface ArchivedProject {
	project_path: string;
	project_name: string;
	display_name?: string;
	encoded_name: string;
	session_count: number;
	prompt_count: number;
	date_range: DateRange;
	sessions: ArchivedSession[];
}

export interface ArchivedPromptsResponse {
	projects: ArchivedProject[];
	total_archived_sessions: number;
	total_archived_prompts: number;
}

export interface ProjectArchivedResponse {
	project_name: string;
	project_path: string;
	sessions: ArchivedSession[];
	total_sessions: number;
	total_prompts: number;
}

// ============================================
// Live Sessions
// ============================================

export type LiveSessionState = 'STARTING' | 'LIVE' | 'WAITING' | 'STOPPED' | 'STALE' | 'ENDED';
export type LiveSessionStatus =
	| 'starting'
	| 'active'
	| 'idle'
	| 'waiting'
	| 'stopped'
	| 'ended'
	| 'stale';

export type SubagentStatus = 'running' | 'completed' | 'error';

export interface SubagentState {
	agent_id: string;
	agent_type: string;
	status: SubagentStatus;
	transcript_path: string | null;
	started_at: string;
	completed_at: string | null;
}

export interface LiveSessionSummary {
	session_id: string;
	state: LiveSessionState;
	status: LiveSessionStatus;
	cwd: string;
	project_encoded_name: string | null;
	project_slug?: string;
	started_at: string;
	updated_at: string;
	duration_seconds: number;
	idle_seconds: number;
	last_hook: string;
	permission_mode: string;
	end_reason: string | null;
	// Session stats (from JSONL for live updates)
	message_count: number | null;
	subagent_count: number | null;
	slug: string | null;
	// Transcript validation
	transcript_exists: boolean;
	// Subagent tracking
	subagents: Record<string, SubagentState>;
	active_subagent_count: number;
	total_subagent_count: number;
}

// ============================================
// Agent Session View (Subagent Detail)
// ============================================

/**
 * Navigation context for both sessions and subagents.
 * Enables unified breadcrumb navigation and back links.
 */
export interface ConversationContext {
	project_encoded_name: string;
	parent_session_uuid?: string | null;
	parent_session_slug?: string | null;
}

/**
 * Detailed information about a subagent's conversation.
 * Mirrors SessionDetail but for subagent JSONL files.
 */
export interface SubagentSessionDetail {
	agent_id: string;
	slug: string | null;
	is_subagent: true;
	context: ConversationContext;

	// Conversation metrics
	message_count: number;
	start_time: string | null;
	end_time: string | null;
	duration_seconds: number | null;

	// Token analytics
	total_input_tokens: number;
	total_output_tokens: number;
	cache_hit_rate: number;
	total_cost: number;

	// Tool usage
	tools_used: Record<string, number>;

	// Context
	git_branches: string[];
	working_directories: string[];

	// Subagent-specific metadata
	subagent_type: string | null;
	initial_prompt: string | null;
}

/**
 * Union type for conversation entities that can be displayed
 * in the unified ConversationView component.
 */
export type ConversationEntity = SessionDetail | SubagentSessionDetail;

/**
 * Type guard to check if an entity is a subagent session.
 */
export function isSubagentSession(entity: ConversationEntity): entity is SubagentSessionDetail {
	return 'is_subagent' in entity && entity.is_subagent === true;
}

/**
 * Type guard to check if an entity is a main session.
 */
export function isMainSession(entity: ConversationEntity): entity is SessionDetail {
	return !('is_subagent' in entity) || entity.is_subagent !== true;
}

// ============================================================================
// Session Relationship Types
// ============================================================================

/**
 * Types of relationships between sessions.
 */
export type RelationshipType = 'resumed_from' | 'provided_context_to' | 'forked_from';

/**
 * Represents a directed relationship between two sessions.
 * Used for displaying session chains and context inheritance.
 */
export interface SessionRelationship {
	source_uuid: string;
	target_uuid: string;
	relationship_type: RelationshipType;
	source_slug?: string;
	target_slug?: string;
	detected_via: string;
	confidence: number;
	source_end_time?: string;
	target_start_time?: string;
}

/**
 * A node in a session chain, representing one session's position.
 * Used for frontend display of session chains/families.
 */
export interface SessionChainNode {
	uuid: string;
	slug?: string;
	start_time?: string;
	end_time?: string;
	is_current: boolean;
	chain_depth: number;
	parent_uuid?: string;
	children_uuids: string[];
	was_compacted: boolean;
	is_continuation_marker: boolean;
	message_count: number;
	initial_prompt?: string;
}

/**
 * Complete session chain for a given session.
 * Contains the full tree of related sessions from root ancestor to leaf descendants.
 */
export interface SessionChain {
	current_session_uuid: string;
	nodes: SessionChainNode[];
	root_uuid?: string;
	total_sessions: number;
	max_depth: number;
	total_compactions: number;
}

// ============================================================================
// Task Types (Claude Code v2.1.16+)
// ============================================================================

/**
 * Status of a task in the structured work plan.
 */
export type TaskStatus = 'pending' | 'in_progress' | 'completed';

/**
 * A task from Claude Code's structured task system.
 * Tasks represent planned work items with dependencies.
 */
export interface Task {
	id: string; // Numeric string: "1", "2", "3"
	subject: string; // Brief title (imperative form)
	description: string; // Detailed description
	status: TaskStatus;
	active_form: string | null; // Present-tense verb form (e.g., "Running tests")
	blocks: string[]; // Task IDs this task blocks
	blocked_by: string[]; // Task IDs blocking this task
	updated_at?: string; // ISO timestamp of last modification (for incremental fetching)
}

/**
 * Task with computed state for UI rendering.
 */
export interface TaskWithState extends Task {
	isBlocked: boolean; // Has incomplete blockers
	isReady: boolean; // Pending with no blockers
}

// ============================================================================
// Agent Usage Analytics Types
// ============================================================================

/**
 * Agent category for filtering in the UI.
 */
export type AgentCategory =
	| 'all'
	| 'builtin'
	| 'plugin'
	| 'custom'
	| 'project'
	| 'claude_tax'
	| 'unknown';

/**
 * Summary of an agent's usage across all sessions.
 */
export interface AgentUsageSummary {
	subagent_type: string;
	plugin_source: string | null;
	agent_name: string;
	category: string;
	total_runs: number;
	total_cost_usd: number;
	total_input_tokens: number;
	total_output_tokens: number;
	avg_duration_seconds: number;
	projects_used_in: string[];
	first_used: string | null;
	last_used: string | null;
	has_definition: boolean;
}

/**
 * Extended agent usage details including tool breakdown and project usage.
 */
export interface AgentUsageDetail extends AgentUsageSummary {
	top_tools: Record<string, number>;
	top_skills: Record<string, number>;
	top_commands: Record<string, number>;
	usage_by_project: Record<string, number>;
}

/**
 * Detailed information about an agent (including plugin agents).
 * From GET /agents/info/{agent_name}
 */
export interface AgentInfo {
	name: string;
	description: string | null;
	capabilities: string[] | null;
	content: string | null;
	is_plugin: boolean;
	plugin: string | null;
	file_path: string | null;
}

/**
 * Response from /agents/usage endpoint.
 */
export interface AgentUsageListResponse {
	agents: AgentUsageSummary[];
	total: number;
	page: number;
	per_page: number;
	total_pages: number;
	total_runs: number;
	total_cost_usd: number;
	by_category: Record<string, number>;
}

/**
 * Single agent invocation record from history endpoint.
 */
export interface AgentInvocation {
	agent_id: string;
	session_uuid: string;
	session_slug: string | null;
	project_encoded_name: string;
	project_display_name?: string;
	invoked_at: string | null;
	duration_seconds: number | null;
	input_tokens: number;
	output_tokens: number;
	cost_usd: number;
	description: string | null;
}

/**
 * Paginated response for agent invocation history.
 */
export interface AgentInvocationHistoryResponse {
	items: AgentInvocation[];
	total: number;
	page: number;
	per_page: number;
	total_pages: number;
}

// ============================================================================
// Plan Types
// ============================================================================

/**
 * Plan summary from /plans endpoint.
 * Represents basic metadata for a plan without full content.
 */
export interface PlanSummary {
	slug: string;
	title: string | null;
	preview: string;
	word_count: number;
	created: string;
	modified: string;
	size_bytes: number;
}

/**
 * Plan detail from /plans/{slug} or /sessions/{uuid}/plan endpoint.
 * Extends PlanSummary with full markdown content.
 */
export interface PlanDetail extends PlanSummary {
	content: string; // Full markdown content
}

/**
 * Session context for a plan - links plan to its origin session.
 */
export interface PlanSessionContext {
	session_uuid: string;
	session_slug: string;
	project_encoded_name: string;
	project_path: string;
	git_branches: string[];
}

/**
 * Plan with its associated session and project context.
 * Used by /plans/with-context endpoint.
 */
export interface PlanWithContext extends PlanSummary {
	session_context: PlanSessionContext | null;
}

/**
 * Paginated response for /plans/with-context endpoint.
 */
export interface PlanListResponse {
	plans: PlanWithContext[];
	total: number;
	page: number;
	per_page: number;
	total_pages: number;
}

/**
 * A session that interacted with a plan file (read/write/edit).
 * Used by /plans/{slug}/sessions endpoint.
 */
export interface PlanRelatedSession {
	session_uuid: string;
	session_slug: string;
	project_encoded_name: string;
	operation: 'read' | 'write' | 'edit';
	timestamp: string;
}

/**
 * Plan statistics from /plans/stats endpoint.
 */
export interface PlanStats {
	total_plans: number;
	total_words: number;
	total_size_bytes: number;
	oldest_plan: string | null;
	newest_plan: string | null;
}

/**
 * Response from /projects/{encoded_name}/memory endpoint.
 * Contains the project's MEMORY.md content.
 */
export interface ProjectMemory {
	content: string;
	word_count: number;
	size_bytes: number;
	modified: string;
	exists: boolean;
}

// ============================================================================
// Sessions List Types (for /sessions/all endpoint)
// ============================================================================

/**
 * Filter option for project dropdown in global sessions view.
 * Provides available projects with session counts for filtering.
 */
export interface ProjectFilterOption {
	encoded_name: string; // Encoded project directory name (e.g., "-Users-repo")
	slug: string; // URL-friendly slug
	display_name: string; // Human-readable display name
	path: string; // Original project path
	name: string; // Human-readable project name
	session_count: number; // Number of sessions in this project
}

/**
 * Session with full project context for global sessions view.
 * Extends SessionSummary with project information for display.
 */
export interface SessionWithContext extends SessionSummary {
	project_path: string; // Original project path (for display)
	project_name: string; // Human-readable project name (last path component)
}

/**
 * Response from GET /sessions/all endpoint.
 * Provides paginated sessions with project filter options.
 */
export interface AllSessionsResponse {
	sessions: SessionWithContext[];
	total: number; // Total matching filtered results
	page: number; // Current page number (1-indexed)
	per_page: number; // Items per page (default 200)
	total_pages: number; // Total number of pages
	projects: ProjectFilterOption[]; // Available projects for filtering
}

// ============================================================================
// Skill Detail Types
// ============================================================================

/**
 * Information about a skill's definition and metadata.
 */
export interface SkillInfo {
	name: string;
	description: string | null;
	content: string | null;
	is_plugin: boolean;
	plugin: string | null;
	file_path: string | null;
}

/**
 * Response from GET /skills/{skill_name}/sessions endpoint.
 */
export interface SkillSessionsResponse {
	skill_name: string;
	sessions: SessionWithContext[];
	total_count: number;
}

// ============================================================================
// Plan Annotation Types
// ============================================================================

/**
 * Type of annotation that can be applied to plan text.
 */
export type AnnotationType =
	| 'DELETION'
	| 'INSERTION'
	| 'REPLACEMENT'
	| 'COMMENT'
	| 'GLOBAL_COMMENT';

/**
 * An annotation on a plan, representing feedback or requested changes.
 */
export interface PlanAnnotation {
	id: string;
	type: AnnotationType;
	original_text: string;
	new_text?: string;
	comment?: string;
	created: string;
	creator?: string;
	line_start?: number;
	line_end?: number;
}

/**
 * Response from GET /plans/{slug}/annotations endpoint.
 */
export interface PlanAnnotationsResponse {
	annotations: PlanAnnotation[];
}

/**
 * Request body for POST /plans/{slug}/annotations endpoint.
 */
export interface CreateAnnotationRequest {
	type: AnnotationType;
	original_text: string;
	new_text?: string;
	comment?: string;
	line_start?: number;
	line_end?: number;
}

// ============================================================================
// Plan Decision Types
// ============================================================================

/**
 * Type of decision made on a plan.
 */
export type DecisionType = 'APPROVED' | 'CHANGES_REQUESTED';

/**
 * A decision made on a plan (approve or request changes).
 */
export interface PlanDecision {
	id: string;
	type: DecisionType;
	feedback?: string;
	created: string;
	creator?: string;
	annotation_ids: string[];
}

/**
 * Current status of a plan's review state.
 */
export interface PlanStatus {
	status: 'pending' | 'approved' | 'changes_requested';
	latest_decision?: PlanDecision;
	total_decisions: number;
	approved_count: number;
	changes_requested_count: number;
}

/**
 * Request body for POST /plans/{slug}/decision endpoint.
 */
export interface CreateDecisionRequest {
	type: DecisionType;
	feedback?: string;
	annotation_ids?: string[];
}

// ============================================================================
// Session Search Types
// ============================================================================

/**
 * Search scope for session search.
 * Matches API SearchScope enum for serialization.
 */
export type SearchScope = 'both' | 'titles' | 'prompts';

/**
 * Multi-select search scope for UI.
 * Both can be true (default), but at least one must be true.
 */
export interface SearchScopeSelection {
	titles: boolean;
	prompts: boolean;
}

/**
 * Convert multi-select scope to API scope string.
 */
export function scopeSelectionToApi(selection: SearchScopeSelection): SearchScope {
	if (selection.titles && selection.prompts) return 'both';
	if (selection.titles) return 'titles';
	return 'prompts';
}

/**
 * Convert API scope string to multi-select scope.
 */
export function apiToScopeSelection(scope: SearchScope): SearchScopeSelection {
	return {
		titles: scope === 'both' || scope === 'titles',
		prompts: scope === 'both' || scope === 'prompts'
	};
}

/**
 * Session status filter for unified filtering.
 * 'live' shows sessions from LiveSessionsSection, 'completed' shows historical.
 */
export type SessionStatusFilter = 'all' | 'live' | 'completed';

/**
 * Live session sub-status for granular filtering.
 * Maps to LiveSessionStatus values including 'starting' and 'ended' (recently ended within 45min).
 */
export type LiveSubStatus =
	| 'starting'
	| 'active'
	| 'idle'
	| 'waiting'
	| 'stopped'
	| 'stale'
	| 'ended';

/**
 * All live sub-statuses for default state.
 */
export const ALL_LIVE_SUB_STATUSES: LiveSubStatus[] = [
	'starting',
	'active',
	'idle',
	'waiting',
	'stopped',
	'stale',
	'ended'
];

/**
 * Counts for each live sub-status.
 */
export interface LiveStatusCounts {
	total: number;
	starting: number;
	active: number;
	idle: number;
	waiting: number;
	stopped: number;
	stale: number;
	ended: number;
}

/**
 * Date range presets for session search.
 */
export type SearchDateRange = 'all' | 'today' | '7d' | '30d' | 'custom';

/**
 * Search filters state for session search UI.
 */
export interface SearchFilters {
	query: string;
	/** Search tokens for multi-term AND search (max 7) */
	tokens: string[];
	scope: SearchScope;
	status: SessionStatusFilter;
	dateRange: SearchDateRange;
	customStart?: Date;
	customEnd?: Date;
	/** Live sub-statuses to show when status is 'live' or 'all' */
	liveSubStatuses?: LiveSubStatus[];
	/** Filter by session source: local, remote, or all */
	source?: SessionSourceFilter;
}

/**
 * Status filter option from API response.
 * Provides status counts for filter dropdown.
 */
export interface StatusFilterOption {
	value: string;
	label: string;
	count: number;
}

/**
 * Filter chip for displaying active filters.
 */
export interface FilterChip {
	key: keyof SearchFilters;
	label: string;
	value: string;
}

/**
 * Extended AllSessionsResponse with search enhancements.
 */
export interface AllSessionsResponseWithFilters extends AllSessionsResponse {
	status_options: StatusFilterOption[];
	applied_filters: {
		search?: string;
		scope?: SearchScope;
		status?: SessionStatusFilter;
		start_ts?: number;
		end_ts?: number;
	};
}

// ============================================================================
// Usage Trend Types (shared by skills & agents trend endpoints)
// ============================================================================

/**
 * Single data point in a usage trend.
 */
export interface UsageTrendItem {
	date: string;
	count: number;
}

/**
 * Generic usage trend response for skills and agents.
 * Returned by GET /skills/usage/trend and GET /agents/usage/trend.
 */
export interface UsageTrendResponse {
	total: number;
	by_item: Record<string, number>;
	trend: UsageTrendItem[];
	trend_by_item?: Record<string, UsageTrendItem[]>;
	first_used: string | null;
	last_used: string | null;
}

// ============================================================================
// Plugin Types
// ============================================================================

/**
 * Daily usage data point for trend charts.
 */
export interface DailyUsage {
	date: string;
	agent_runs: number;
	skill_invocations: number;
	command_invocations: number;
	mcp_tool_calls: number;
	cost_usd: number;
}

/**
 * Capabilities provided by a plugin.
 */
export interface PluginCapabilities {
	plugin_name: string;
	agents: string[];
	skills: string[];
	commands: string[];
	mcp_tools: string[];
	hooks: string[];
}

/**
 * Usage analytics for a plugin.
 */
export interface PluginUsageStats {
	plugin_name: string;
	total_agent_runs: number;
	total_skill_invocations: number;
	total_command_invocations: number;
	total_mcp_tool_calls: number;
	estimated_cost_usd: number;
	by_agent: Record<string, number>;
	by_skill: Record<string, number>;
	by_command: Record<string, number>;
	by_mcp_tool: Record<string, number>;
	by_agent_daily: Record<string, Record<string, number>>;
	by_skill_daily: Record<string, Record<string, number>>;
	by_command_daily: Record<string, Record<string, number>>;
	by_mcp_tool_daily: Record<string, Record<string, number>>;
	trend: DailyUsage[];
	first_used: string | null;
	last_used: string | null;
}

/**
 * Plugin summary for listing page.
 */
export interface PluginSummary {
	name: string;
	installation_count: number;
	scopes: string[];
	latest_version: string;
	latest_update: string | null;
	agent_count: number;
	skill_count: number;
	command_count: number;
	total_runs: number;
	estimated_cost_usd: number;
	days_since_update: number;
	description: string | null;
	is_official: boolean;
}

/**
 * Plugin installation details.
 */
export interface PluginInstallation {
	plugin_name: string;
	scope: string;
	install_path: string;
	version: string;
	installed_at: string;
	last_updated: string;
}

/**
 * Plugin detail for detail page.
 */
export interface PluginDetail {
	name: string;
	description: string | null;
	installations: PluginInstallation[];
	capabilities: PluginCapabilities | null;
	usage: PluginUsageStats | null;
}

/**
 * Response from GET /plugins endpoint.
 */
export interface PluginsOverview {
	version: number;
	total_plugins: number;
	total_installations: number;
	plugins: PluginSummary[];
}

/**
 * Detail for a single plugin command with markdown content.
 */
export interface PluginCommandDetail {
	name: string;
	content: string | null;
}

/**
 * Response from GET /plugins/{name}/commands endpoint.
 */
export interface PluginCommandsResponse {
	plugin_name: string;
	commands: PluginCommandDetail[];
}

// ============================================================================
// MCP Tools Types
// ============================================================================

/**
 * Summary of a single MCP tool within a server.
 */
export interface McpToolSummary {
	name: string;
	full_name: string;
	calls: number;
	session_count: number;
	main_calls: number;
	subagent_calls: number;
}

/**
 * Summary of an MCP server and its tools.
 */
export interface McpServer {
	name: string;
	display_name: string;
	source: 'plugin' | 'standalone' | 'custom' | 'builtin';
	plugin_name: string | null;
	tool_count: number;
	total_calls: number;
	session_count: number;
	main_calls: number;
	subagent_calls: number;
	first_used: string | null;
	last_used: string | null;
	tools: McpToolSummary[];
}

/**
 * Overview of all MCP servers and tools.
 */
export interface McpToolsOverview {
	total_servers: number;
	total_tools: number;
	total_calls: number;
	total_sessions: number;
	servers: McpServer[];
}

/**
 * Daily usage data point for an MCP server.
 */
export interface McpServerTrend {
	date: string;
	calls: number;
	sessions: number;
	main_calls?: number;
	subagent_calls?: number;
}

/**
 * Session summary returned by MCP tools endpoints.
 */
export interface McpSessionSummary {
	uuid: string;
	slug: string | null;
	project_encoded_name: string | null;
	project_display_name?: string;
	message_count: number;
	start_time: string | null;
	end_time: string | null;
	duration_seconds: number | null;
	models_used: string[];
	subagent_count: number;
	initial_prompt: string | null;
	git_branches: string[];
	session_titles: string[];
	tool_source?: 'main' | 'subagent' | 'both';
	subagent_agent_ids?: string[];
	invocation_sources?: string[];
}

/**
 * Detailed MCP server info with trend and session list.
 */
export interface McpServerDetail extends McpServer {
	trend: McpServerTrend[];
	sessions: McpSessionSummary[];
	sessions_total: number;
}

/**
 * Detailed stats for a single MCP tool.
 */
export interface McpToolDetail {
	name: string;
	full_name: string;
	server_name: string;
	server_display_name: string;
	source: 'plugin' | 'standalone' | 'builtin';
	plugin_name: string | null;
	calls: number;
	main_calls: number;
	subagent_calls: number;
	session_count: number;
	first_used: string | null;
	last_used: string | null;
	trend: McpServerTrend[];
	sessions: McpSessionSummary[];
	sessions_total: number;
}

// ============================================================================
// Skill Detail Types
// ============================================================================

export interface SkillTrendItem {
	date: string;
	calls: number;
	sessions: number;
}

export interface SkillDetailResponse {
	name: string;
	description: string | null;
	content: string | null;
	is_plugin: boolean;
	plugin: string | null;
	file_path: string | null;
	calls: number;
	main_calls: number;
	subagent_calls: number;
	manual_calls: number;
	auto_calls: number;
	mentioned_calls: number;
	command_triggered_calls?: number;
	category?: SkillCategory;
	mention_session_count: number;
	session_count: number;
	first_used: string | null;
	last_used: string | null;
	trend: SkillTrendItem[];
	sessions: McpSessionSummary[];
	sessions_total: number;
}

// ============================================================================
// Hook Types
// ============================================================================

export interface HookRegistration {
	event_type: string;
	source_type: 'global' | 'project' | 'plugin';
	source_name: string;
	source_id: string;
	plugin_id?: string | null;
	description?: string | null;
	matcher: string;
	command: string;
	script_filename?: string | null;
	script_language: string;
	timeout_ms?: number | null;
	can_block: boolean;
}

export interface HookScript {
	filename: string;
	full_path?: string | null;
	language: string;
	source_name: string;
	event_types: string[];
	registrations: number;
	is_symlink: boolean;
	symlink_target?: string | null;
}

export interface HookSource {
	source_type: string;
	source_name: string;
	source_id: string;
	plugin_id?: string | null;
	scripts: HookScript[];
	total_registrations: number;
	event_types_covered: string[];
	blocking_hooks_count: number;
}

export interface HookEventSummary {
	event_type: string;
	phase: string;
	can_block: boolean;
	description: string;
	total_registrations: number;
	sources: string[];
	registrations: HookRegistration[];
}

export interface HookFieldInfo {
	name: string;
	type: string;
	required: boolean;
	description?: string | null;
}

export interface HookEventSchema {
	input_fields: HookFieldInfo[];
	output_fields: HookFieldInfo[];
	base_fields: HookFieldInfo[];
}

export interface HooksOverview {
	sources: HookSource[];
	event_summaries: HookEventSummary[];
	registrations: HookRegistration[];
	stats: {
		total_sources: number;
		total_registrations: number;
		blocking_hooks: number;
	};
}

export interface HookEventDetail {
	event: HookEventSummary;
	schema_info?: HookEventSchema | null;
	related_events: Array<{
		event_type: string;
		phase: string;
		can_block: boolean;
		description: string;
		position: string;
	}>;
}

export interface HookSourceDetail {
	source: HookSource;
	scripts: HookScript[];
	coverage_matrix: Record<string, boolean>;
}

export interface HookScriptDetail {
	script: HookScript;
	source_type: string;
	content: string | null;
	size_bytes: number | null;
	modified_at: string | null;
	line_count: number | null;
	error: string | null;
}
