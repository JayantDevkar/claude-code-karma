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
	ZapIcon,
	TerminalSquareIcon
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
		case 'TaskOutput':
			return BotIcon;
		case 'TodoWrite':
			return ListTodoIcon;
		case 'WebSearch':
			return GlobeIcon;
		case 'AskQuestion':
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
	}
} as const;

export type EventTypeConfigKey = keyof typeof eventTypeConfig;
