import type { TimelineEvent } from '$lib/api-types';

/** One event of every type in the timeline contract, real backend shapes, and one unknown type. */
export const timelineFixture = [
	{
		id: 'evt-1',
		event_type: 'prompt',
		timestamp: '2026-11-18T10:00:00Z',
		actor: 'user',
		actor_type: 'user',
		title: 'User prompt',
		summary: 'Add pagination to the list endpoint',
		metadata: {
			full_content: 'Add pagination to the list endpoint',
			prompt_source: 'typed'
		}
	},
	{
		id: 'evt-2',
		event_type: 'system_context',
		timestamp: '2026-11-18T10:00:01Z',
		actor: 'system',
		actor_type: 'system',
		title: 'System reminder',
		summary: 'The user message contains a skill name',
		metadata: {
			kind: 'system_reminder',
			full_content:
				'<system-reminder>The user message contains a skill name</system-reminder>'
		}
	},
	{
		id: 'evt-3',
		event_type: 'skill_invocation',
		timestamp: '2026-11-18T10:00:05Z',
		actor: 'session',
		actor_type: 'session',
		title: 'Skill: /docs-tools:outline',
		summary: 'Invoked /docs-tools:outline',
		metadata: {
			tool_name: 'Skill',
			command_name: 'docs-tools:outline',
			has_result: true,
			result_content: 'Launching skill: docs-tools:outline',
			skill_body: '# Outline\n\nList the headings first.'
		}
	},
	{
		id: 'evt-4',
		event_type: 'subagent_spawn',
		timestamp: '2026-11-18T10:01:00Z',
		actor: 'session',
		actor_type: 'session',
		title: 'Agent',
		summary: 'Review the pagination change',
		metadata: {
			tool_name: 'Agent',
			subagent_type: 'general-purpose',
			prompt: 'You are reviewing the pagination change.',
			spawned_agent_id: 'a1c2d3e4f5a6b7c8d',
			spawned_agent_name: 'reviewer-a',
			spawned_agent_color: 'yellow',
			team_name: 'checkout-team',
			agent_model: 'opus',
			run_in_background: true,
			has_result: true
		}
	},
	{
		id: 'evt-5',
		event_type: 'message',
		timestamp: '2026-11-18T10:02:00Z',
		actor: 'session',
		actor_type: 'session',
		title: 'Message to reviewer-a',
		summary: 'Second round is ready',
		metadata: {
			direction: 'out',
			peer_kind: 'agent',
			peer_name: 'reviewer-a',
			peer_agent_id: 'a1c2d3e4f5a6b7c8d',
			peer_color: 'yellow',
			message_summary: 'Second round is ready',
			full_content: 'The second round is ready for your review. Please verify it.',
			tool_name: 'SendMessage',
			has_result: true,
			result_content: 'Message delivered',
			result_status: 'success'
		}
	},
	{
		id: 'evt-6',
		event_type: 'message',
		timestamp: '2026-11-18T10:03:00Z',
		actor: 'docs-site-2',
		actor_type: 'peer_session',
		actor_name: 'docs-site-2',
		title: 'Message from docs-site-2',
		summary: '[ASK] Which page size does the list endpoint use?',
		metadata: {
			direction: 'in',
			peer_kind: 'session',
			peer_name: 'docs-site-2',
			peer_address: 'uds:/tmp/cc-socks/4101.sock',
			full_content: '[ASK] Which page size does the list endpoint use?',
			queued: true,
			relayed: true
		}
	},
	{
		id: 'evt-7',
		event_type: 'task_notification',
		timestamp: '2026-11-18T10:04:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Background task completed',
		summary: 'Review the pagination change finished',
		metadata: {
			task_id: 'a1c2d3e4f5a6b7c8d',
			task_status: 'completed',
			task_summary: 'Review the pagination change finished',
			task_kind: 'agent',
			agent_id: 'a1c2d3e4f5a6b7c8d',
			agent_name: 'reviewer-a',
			agent_color: 'yellow',
			full_content: 'Fixes verified.'
		}
	},
	{
		id: 'evt-8',
		event_type: 'task_notification',
		timestamp: '2026-11-18T10:04:30Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Background task failed',
		summary: 'Wait until the build finishes',
		metadata: {
			task_id: 'b00000002',
			task_status: 'failed',
			task_summary: 'Wait until the build finishes',
			task_kind: 'shell'
		}
	},
	{
		id: 'evt-9',
		event_type: 'scheduled_fire',
		timestamp: '2026-11-18T10:05:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Scheduled task',
		summary: 'Hourly link check',
		metadata: { full_content: 'Hourly link check', cron: '0 * * * *', task_id: 't1' }
	},
	{
		id: 'evt-10',
		event_type: 'compaction',
		timestamp: '2026-11-18T10:06:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Conversation compacted',
		summary: null,
		metadata: {
			trigger: 'auto',
			pre_tokens: 150000,
			full_content: 'This session is being continued from a previous conversation.'
		}
	},
	{
		id: 'evt-11',
		event_type: 'shell_command',
		timestamp: '2026-11-18T10:07:00Z',
		actor: 'user',
		actor_type: 'user',
		title: 'Shell command',
		summary: 'npm run build',
		metadata: {
			command: 'npm run build -- --mode staging',
			result_content: 'Build finished',
			stderr: 'warning: beta'
		}
	},
	{
		id: 'evt-12',
		event_type: 'builtin_command',
		timestamp: '2026-11-18T10:08:00Z',
		actor: 'user',
		actor_type: 'user',
		title: 'Built-in: /reload-plugins',
		summary: 'Invoked /reload-plugins',
		metadata: { command_name: 'reload-plugins', result_content: 'Reloaded: 17 plugins' }
	},
	{
		id: 'evt-13',
		event_type: 'system_notice',
		timestamp: '2026-11-18T10:09:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Recap',
		summary: 'We were reviewing the pagination change.',
		metadata: {
			kind: 'away_summary',
			full_content: 'We were reviewing the pagination change.'
		}
	},
	{
		id: 'evt-14',
		event_type: 'prompt',
		timestamp: '2026-11-18T10:10:00Z',
		actor: 'user',
		actor_type: 'user',
		title: 'User prompt',
		summary: 'use the branch feature/pagination',
		metadata: {
			full_content: 'use the branch feature/pagination',
			prompt_source: 'queued',
			queued: true
		}
	},
	{
		id: 'evt-15',
		event_type: 'tool_call',
		timestamp: '2026-11-18T10:11:00Z',
		actor: 'a1c2d3e4f5a6b7c8d',
		actor_type: 'subagent',
		actor_name: 'reviewer-a',
		actor_color: 'yellow',
		title: 'Read file',
		summary: 'src/list/page.ts',
		metadata: {
			tool_name: 'Read',
			has_result: true,
			result_status: 'success',
			agent_id: 'a1c2d3e4f5a6b7c8d'
		}
	},
	// The shapes below are copied from real backend output, not from the contract.
	{
		id: 'evt-16',
		event_type: 'task_notification',
		timestamp: '2026-11-18T10:12:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Monitor update',
		summary: 'Monitor event: "build status"',
		metadata: {
			task_id: null,
			task_status: null,
			task_summary: 'Monitor event: "build status"',
			tool_use_id: null,
			task_kind: 'monitor',
			output_file: null,
			queued: true,
			full_content: 'checks: 3 passing, 1 pending'
		}
	},
	{
		id: 'evt-17',
		event_type: 'task_notification',
		timestamp: '2026-11-18T10:12:30Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Background command completed',
		summary: 'Background command "Run the unit tests" completed (exit code 0)',
		metadata: {
			task_id: 'b00000001',
			task_status: 'completed',
			task_summary: 'Background command "Run the unit tests" completed (exit code 0)',
			tool_use_id: 'toolu_example0001',
			task_kind: 'shell',
			output_file: '/tmp/tasks/b00000001.output',
			queued: true
		}
	},
	{
		id: 'evt-18',
		event_type: 'system_context',
		timestamp: '2026-11-18T10:13:00Z',
		actor: 'abuilder-b-0b0b0b0b0b0b0b0b',
		actor_type: 'subagent',
		actor_name: 'builder-b',
		actor_color: 'green',
		title: 'Agent idle',
		summary: 'builder-b is idle (available)',
		metadata: {
			kind: 'agent_idle',
			agent_id: 'abuilder-b-0b0b0b0b0b0b0b0b',
			full_content: 'Status: DONE'
		}
	},
	{
		id: 'evt-19',
		event_type: 'system_notice',
		timestamp: '2026-11-18T10:14:00Z',
		actor: 'user',
		actor_type: 'user',
		title: 'Interrupted by user',
		summary: '',
		metadata: {
			kind: 'interrupted',
			level: null,
			full_content: '[Request interrupted by user]'
		}
	},
	{
		id: 'evt-20',
		event_type: 'message',
		timestamp: '2026-11-18T10:15:00Z',
		actor: 'session',
		actor_type: 'session',
		title: 'Message from main session',
		summary: 'Also cover the retry path.',
		metadata: {
			direction: 'in',
			peer_kind: 'agent',
			peer_name: 'main',
			peer_address: null,
			peer_agent_id: null,
			peer_color: null,
			message_summary: null,
			full_content: 'Also cover the retry path.',
			queued: true,
			relayed: false
		}
	},
	{
		id: 'evt-21',
		event_type: 'system_notice',
		timestamp: '2026-11-18T10:16:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Model fallback',
		summary: "Fable 5.1's safeguards flagged this message. Switched to Opus 4.8.",
		metadata: {
			kind: 'model_refusal_fallback',
			level: 'warning',
			full_content: "Fable 5.1's safeguards flagged this message. Switched to Opus 4.8.",
			original_model: 'claude-fable-5-1',
			fallback_model: 'claude-opus-4-8'
		}
	},
	{
		id: 'evt-22',
		event_type: 'system_notice',
		timestamp: '2026-11-18T10:17:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Remote control',
		summary: '/remote-control is active',
		metadata: {
			kind: 'bridge_status',
			level: null,
			full_content: '/remote-control is active',
			url: 'https://claude.ai/code/session_example'
		}
	},
	{
		id: 'evt-23',
		event_type: 'brand_new_type',
		timestamp: '2026-11-18T10:18:00Z',
		actor: 'system',
		actor_type: 'system',
		title: 'Something Claude Code added later',
		summary: null,
		metadata: {}
	}
] as unknown as TimelineEvent[];
