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
		summary: 'Review the timeline categories and find the gaps',
		metadata: {
			full_content: 'Review the timeline categories and find the gaps',
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
		title: 'Skill: /superpowers:systematic-debugging',
		summary: 'Invoked /superpowers:systematic-debugging',
		metadata: {
			tool_name: 'Skill',
			command_name: 'superpowers:systematic-debugging',
			has_result: true,
			result_content: 'Launching skill: superpowers:systematic-debugging',
			skill_body: '# Systematic Debugging\n\nFind the root cause first.'
		}
	},
	{
		id: 'evt-4',
		event_type: 'subagent_spawn',
		timestamp: '2026-11-18T10:01:00Z',
		actor: 'session',
		actor_type: 'session',
		title: 'Agent',
		summary: 'Review plan-2 Task 6',
		metadata: {
			tool_name: 'Agent',
			subagent_type: 'general-purpose',
			prompt: 'You are reviewing Task 6 of plan-2.',
			spawned_agent_id: 'a0ae946093e2cb8e5',
			spawned_agent_name: 'rev-m6',
			spawned_agent_color: 'yellow',
			team_name: 'wind-tunnel',
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
		title: 'Message to rev-m6',
		summary: 'Fix round is at 3161b7d',
		metadata: {
			direction: 'out',
			peer_kind: 'agent',
			peer_name: 'rev-m6',
			peer_agent_id: 'a0ae946093e2cb8e5',
			peer_color: 'yellow',
			message_summary: 'Fix round is at 3161b7d',
			full_content: 'Fix round for your review is at 3161b7d. Please verify it.',
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
		actor: 'occu-orchestration-airflow-72',
		actor_type: 'peer_session',
		actor_name: 'occu-orchestration-airflow-72',
		title: 'Message from occu-orchestration-airflow-72',
		summary: '[ASK] Why did the triage blame the wrong lines?',
		metadata: {
			direction: 'in',
			peer_kind: 'session',
			peer_name: 'occu-orchestration-airflow-72',
			peer_address: 'uds:/tmp/cc-socks/10999.sock',
			full_content: '[ASK] Why did the triage blame the wrong lines?',
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
		summary: 'Review plan-2 Task 6 finished',
		metadata: {
			task_id: 'a0ae946093e2cb8e5',
			task_status: 'completed',
			task_summary: 'Review plan-2 Task 6 finished',
			task_kind: 'agent',
			agent_id: 'a0ae946093e2cb8e5',
			agent_name: 'rev-m6',
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
		summary: 'Wait until PR #6 is merged',
		metadata: {
			task_id: 'bblmd3xw1',
			task_status: 'failed',
			task_summary: 'Wait until PR #6 is merged',
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
		summary: 'Hourly check (DE-346)',
		metadata: { full_content: 'Hourly check (DE-346)', cron: '0 * * * *', task_id: 't1' }
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
			pre_tokens: 155206,
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
		summary: 'slack app install',
		metadata: {
			command: 'slack app install --team T3 -E deployed',
			result_content: 'App installed',
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
		summary: 'We were reviewing the incident-first work.',
		metadata: {
			kind: 'away_summary',
			full_content: 'We were reviewing the incident-first work.'
		}
	},
	{
		id: 'evt-14',
		event_type: 'prompt',
		timestamp: '2026-11-18T10:10:00Z',
		actor: 'user',
		actor_type: 'user',
		title: 'User prompt',
		summary: 'use the branch jay/wt-reply-shape',
		metadata: {
			full_content: 'use the branch jay/wt-reply-shape',
			prompt_source: 'queued',
			queued: true
		}
	},
	{
		id: 'evt-15',
		event_type: 'tool_call',
		timestamp: '2026-11-18T10:11:00Z',
		actor: 'a0ae946093e2cb8e5',
		actor_type: 'subagent',
		actor_name: 'rev-m6',
		actor_color: 'yellow',
		title: 'Read file',
		summary: 'api/models/message.py',
		metadata: {
			tool_name: 'Read',
			has_result: true,
			result_status: 'success',
			agent_id: 'a0ae946093e2cb8e5'
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
		summary: 'Monitor event: "PR #6 checks"',
		metadata: {
			task_id: null,
			task_status: null,
			task_summary: 'Monitor event: "PR #6 checks"',
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
		summary: 'Background command "Run all five test suites" completed (exit code 0)',
		metadata: {
			task_id: 'b46fd4ed7',
			task_status: 'completed',
			task_summary: 'Background command "Run all five test suites" completed (exit code 0)',
			tool_use_id: 'toolu_012eVX8ooGXMsSHo8Ze8sP5N',
			task_kind: 'shell',
			output_file: '/private/tmp/tasks/b46fd4ed7.output',
			queued: true
		}
	},
	{
		id: 'evt-18',
		event_type: 'system_context',
		timestamp: '2026-11-18T10:13:00Z',
		actor: 'aimpl-t28-e4a00898e0a882a3',
		actor_type: 'subagent',
		actor_name: 'impl-t28',
		actor_color: 'green',
		title: 'Agent idle',
		summary: 'impl-t28 is idle (available)',
		metadata: {
			kind: 'agent_idle',
			agent_id: 'aimpl-t28-e4a00898e0a882a3',
			full_content: 'Status: DONE_WITH_CONCERNS'
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
			url: 'https://claude.ai/code/session_01D8zmUuZXUA6CccYva1F8du'
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
