import {
	FileIcon,
	FilePlusIcon,
	FilePenIcon,
	FileMinusIcon,
	TerminalIcon,
	SearchIcon,
	FolderIcon,
	BotIcon,
	ListTodoIcon,
	GlobeIcon,
	HelpCircleIcon,
	ToggleLeftIcon,
	FileTextIcon,
	AlertCircleIcon,
	PlugIcon,
	BookOpenIcon,
	SparklesIcon,
	MessageSquareIcon,
	BrainIcon,
	MessageCircleIcon,
	MapIcon,
	TerminalSquareIcon,
	PlusCircleIcon,
	RefreshCwIcon,
	ListIcon,
	ClipboardListIcon,
	CloudOffIcon,
	HourglassIcon,
	BanIcon,
	SendIcon,
	WorkflowIcon,
	ActivityIcon,
	PackageSearchIcon,
	GitBranchIcon,
	UsersIcon,
	CircleStopIcon,
	AlarmClockIcon,
	CalendarClockIcon,
	LayoutTemplateIcon,
	LinkIcon,
	BellIcon,
	FileUpIcon,
	ZapIcon,
	MessagesSquareIcon,
	BellRingIcon,
	FoldVerticalIcon,
	SquareTerminalIcon,
	InfoIcon,
	ScrollTextIcon
} from 'lucide-svelte';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type LucideIcon = any;

/**
 * Get the appropriate icon for a tool name
 */
export function getToolIcon(toolName: string | undefined): LucideIcon {
	if (!toolName) return TerminalIcon;

	switch (toolName) {
		case 'Read':
			return FileIcon;
		case 'Write':
			return FilePlusIcon;
		case 'Edit':
		case 'StrReplace':
			return FilePenIcon;
		case 'Delete':
			return FileMinusIcon;
		case 'Bash':
		case 'Shell':
			return TerminalIcon;
		case 'Glob':
		case 'Grep':
		case 'SemanticSearch':
			return SearchIcon;
		case 'LS':
			return FolderIcon;
		case 'Task':
		case 'Agent':
		case 'TaskOutput':
			return BotIcon;
		case 'SendMessage':
			return SendIcon;
		case 'ListAgents':
			return UsersIcon;
		case 'Workflow':
			return WorkflowIcon;
		case 'Monitor':
			return ActivityIcon;
		case 'ToolSearch':
			return PackageSearchIcon;
		case 'EnterWorktree':
		case 'ExitWorktree':
			return GitBranchIcon;
		case 'TaskStop':
			return CircleStopIcon;
		case 'ScheduleWakeup':
			return AlarmClockIcon;
		case 'CronCreate':
		case 'CronDelete':
		case 'CronList':
			return CalendarClockIcon;
		case 'Artifact':
			return LayoutTemplateIcon;
		case 'WebFetch':
			return LinkIcon;
		case 'PushNotification':
		case 'ReadNotifications':
			return BellIcon;
		case 'SendUserFile':
			return FileUpIcon;
		case 'Skill':
			return ZapIcon;
		case 'TaskCreate':
			return PlusCircleIcon;
		case 'TaskUpdate':
			return RefreshCwIcon;
		case 'TaskList':
			return ListIcon;
		case 'TaskGet':
			return ClipboardListIcon;
		case 'TodoWrite':
			return ListTodoIcon;
		case 'WebSearch':
			return GlobeIcon;
		case 'AskQuestion':
		case 'AskUserQuestion':
			return HelpCircleIcon;
		case 'SwitchMode':
			return ToggleLeftIcon;
		case 'CreatePlan':
			return FileTextIcon;
		case 'ReadLints':
			return AlertCircleIcon;
		case 'CallMcpTool':
			return PlugIcon;
		case 'EditNotebook':
			return BookOpenIcon;
		case 'ExitPlanMode':
		case 'EnterPlanMode':
			return MapIcon;
		default:
			return SparklesIcon;
	}
}

/**
 * Event type configuration for icons and colors
 * Uses CSS variable tokens for dark mode support
 */
export const eventTypeConfig = {
	prompt: {
		icon: MessageSquareIcon,
		color: 'text-[var(--event-prompt)]',
		bgColor: 'bg-[var(--event-prompt-subtle)]',
		borderColor: 'border-[var(--event-prompt)]/60',
		leftAccent: 'border-l-[var(--event-prompt)]'
	},
	tool_call: {
		icon: TerminalIcon,
		color: 'text-[var(--event-tool)]',
		bgColor: 'bg-[var(--event-tool-subtle)]',
		borderColor: 'border-[var(--event-tool)]/60',
		leftAccent: 'border-l-[var(--event-tool)]'
	},
	subagent_spawn: {
		icon: BotIcon,
		color: 'text-[var(--event-subagent)]',
		bgColor: 'bg-[var(--event-subagent-subtle)]',
		borderColor: 'border-[var(--event-subagent)]/60',
		leftAccent: 'border-l-[var(--event-subagent)]'
	},
	thinking: {
		icon: BrainIcon,
		color: 'text-[var(--event-thinking)]',
		bgColor: 'bg-[var(--event-thinking-subtle)]',
		borderColor: 'border-[var(--event-thinking)]/60',
		leftAccent: 'border-l-[var(--event-thinking)]'
	},
	response: {
		icon: MessageCircleIcon,
		color: 'text-[var(--event-response)]',
		bgColor: 'bg-[var(--event-response-subtle)]',
		borderColor: 'border-[var(--event-response)]/60',
		leftAccent: 'border-l-[var(--event-response)]'
	},
	todo_update: {
		icon: ListTodoIcon,
		color: 'text-[var(--event-todo)]',
		bgColor: 'bg-[var(--event-todo-subtle)]',
		borderColor: 'border-[var(--event-todo)]/60',
		leftAccent: 'border-l-[var(--event-todo)]'
	},
	command_invocation: {
		icon: TerminalSquareIcon,
		color: 'text-[var(--event-command)]',
		bgColor: 'bg-[var(--event-command-subtle)]',
		borderColor: 'border-[var(--event-command)]/60',
		leftAccent: 'border-l-[var(--event-command)]'
	},
	skill_invocation: {
		icon: TerminalSquareIcon,
		color: 'text-[var(--accent)]',
		bgColor: 'bg-[var(--accent)]/10',
		borderColor: 'border-[var(--accent)]/60',
		leftAccent: 'border-l-[var(--accent)]'
	},
	builtin_command: {
		icon: TerminalSquareIcon,
		color: 'text-gray-400',
		bgColor: 'bg-gray-500/10',
		borderColor: 'border-gray-500/60',
		leftAccent: 'border-l-gray-500'
	},
	// Muted by default; loud variants live in apiErrorToneConfig.
	api_error: {
		icon: CloudOffIcon,
		color: 'text-[var(--text-muted)]',
		bgColor: 'bg-[var(--bg-muted)]',
		borderColor: 'border-[var(--border)]',
		leftAccent: 'border-l-[var(--text-muted)]'
	},
	message: {
		icon: MessagesSquareIcon,
		color: 'text-[var(--event-message)]',
		bgColor: 'bg-[var(--event-message-subtle)]',
		borderColor: 'border-[var(--event-message)]/60',
		leftAccent: 'border-l-[var(--event-message)]'
	},
	task_notification: {
		icon: BellRingIcon,
		color: 'text-[var(--event-background)]',
		bgColor: 'bg-[var(--event-background-subtle)]',
		borderColor: 'border-[var(--event-background)]/60',
		leftAccent: 'border-l-[var(--event-background)]'
	},
	scheduled_fire: {
		icon: AlarmClockIcon,
		color: 'text-[var(--event-background)]',
		bgColor: 'bg-[var(--event-background-subtle)]',
		borderColor: 'border-[var(--event-background)]/60',
		leftAccent: 'border-l-[var(--event-background)]'
	},
	compaction: {
		icon: FoldVerticalIcon,
		color: 'text-[var(--event-system)]',
		bgColor: 'bg-[var(--bg-base)]',
		borderColor: 'border-[var(--event-system)]/60',
		leftAccent: 'border-l-[var(--event-system)]'
	},
	shell_command: {
		icon: SquareTerminalIcon,
		color: 'text-[var(--event-command)]',
		bgColor: 'bg-[var(--event-command-subtle)]',
		borderColor: 'border-[var(--event-command)]/60',
		leftAccent: 'border-l-[var(--event-command)]'
	},
	system_notice: {
		icon: InfoIcon,
		color: 'text-[var(--event-system)]',
		bgColor: 'bg-[var(--event-system-subtle)]',
		borderColor: 'border-[var(--event-system)]/60',
		leftAccent: 'border-l-[var(--event-system)]'
	},
	system_context: {
		icon: ScrollTextIcon,
		color: 'text-[var(--event-system)]',
		bgColor: 'bg-[var(--event-system-subtle)]',
		borderColor: 'border-[var(--event-system)]/60',
		leftAccent: 'border-l-[var(--event-system)]'
	}
} as const;

// Neutral look for event types this build does not know yet.
export const unknownEventConfig = {
	icon: SparklesIcon,
	color: 'text-[var(--text-muted)]',
	bgColor: 'bg-[var(--bg-muted)]',
	borderColor: 'border-[var(--border)]',
	leftAccent: 'border-l-[var(--text-muted)]'
} as const;

export interface EventConfig {
	icon: LucideIcon;
	color: string;
	bgColor: string;
	borderColor: string;
	leftAccent: string;
}

/** Icon and colours for an event type, with a neutral fallback for unknown types. */
export function getEventConfig(eventType: string): EventConfig {
	return (eventTypeConfig as Record<string, EventConfig>)[eventType] ?? unknownEventConfig;
}

// Loud styling for unhealed limit/refusal api_error events.
export const apiErrorToneConfig = {
	warning: {
		icon: HourglassIcon,
		color: 'text-[var(--warning)]',
		bgColor: 'bg-[var(--warning-subtle)]',
		borderColor: 'border-[var(--warning)]/60',
		leftAccent: 'border-l-[var(--warning)]'
	},
	error: {
		icon: BanIcon,
		color: 'text-[var(--error)]',
		bgColor: 'bg-[var(--error-subtle)]',
		borderColor: 'border-[var(--error)]/60',
		leftAccent: 'border-l-[var(--error)]'
	}
} as const;

export type EventTypeConfigKey = keyof typeof eventTypeConfig;
