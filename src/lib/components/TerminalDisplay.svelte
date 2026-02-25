<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { API_BASE } from '$lib/config';

	interface DashboardStats {
		period: string;
		start_date: string;
		end_date: string;
		sessions_count: number;
		projects_active: number;
		duration_seconds: number;
	}

	let currentMessage = $state('');
	let messageList: string[] = [];
	let messageIndex = $state(0);
	let charIndex = $state(0);
	let loading = $state(true);
	let isTyping = $state(false);

	let typewriterInterval: ReturnType<typeof setInterval> | null = null;
	let pauseTimeout: ReturnType<typeof setTimeout> | null = null;

	function formatDuration(seconds: number): string {
		if (seconds < 60) return `${Math.round(seconds)} seconds`;
		const hours = Math.floor(seconds / 3600);
		const mins = Math.round((seconds % 3600) / 60);
		if (hours > 0) return `${hours}h ${mins}m`;
		return `${mins} minutes`;
	}

	function typeNextCharacter() {
		if (messageList.length === 0) return;

		const targetMessage = messageList[messageIndex];

		if (charIndex < targetMessage.length) {
			currentMessage = targetMessage.slice(0, charIndex + 1);
			charIndex++;
		} else {
			// Message complete - pause then move to next
			if (typewriterInterval) {
				clearInterval(typewriterInterval);
				typewriterInterval = null;
			}
			isTyping = false;

			pauseTimeout = setTimeout(() => {
				// Move to next message
				messageIndex = (messageIndex + 1) % messageList.length;
				charIndex = 0;
				currentMessage = '';
				startTyping();
			}, 3000);
		}
	}

	function startTyping() {
		if (messageList.length === 0) return;
		isTyping = true;
		typewriterInterval = setInterval(typeNextCharacter, 40);
	}

	function startTypewriter(msgs: string[]) {
		messageList = msgs.length > 0 ? msgs : ['Welcome to Claude Karma'];
		charIndex = 0;
		currentMessage = '';
		messageIndex = 0;
		startTyping();
	}

	function getPeriodLabel(period: string): string {
		switch (period) {
			case 'today':
				return 'today';
			case 'yesterday':
				return 'yesterday';
			case 'this_week':
				return 'this week';
			default:
				return '';
		}
	}

	function buildMessages(stats: DashboardStats): string[] {
		// No activity - show welcome messages
		if (stats.period === 'none' || stats.sessions_count === 0) {
			return ['Welcome to Claude Karma'];
		}

		const msgs: string[] = [];
		const periodLabel = getPeriodLabel(stats.period);

		// Add messages based on stats
		if (stats.sessions_count > 0) {
			const word = stats.sessions_count === 1 ? 'session' : 'sessions';
			msgs.push(`You created ${stats.sessions_count} ${word} ${periodLabel}`);
		}

		if (stats.projects_active > 0) {
			const word = stats.projects_active === 1 ? 'project' : 'projects';
			msgs.push(`You worked on ${stats.projects_active} ${word} ${periodLabel}`);
		}

		if (stats.duration_seconds > 0) {
			msgs.push(
				`You spent ${formatDuration(stats.duration_seconds)} with agents ${periodLabel}`
			);
		}

		// Add encouraging closing message
		if (msgs.length > 0) {
			msgs.push('You got things done!');
		}

		return msgs;
	}

	onMount(async () => {
		let msgs: string[] = [];

		try {
			const res = await fetch(`${API_BASE}/analytics/dashboard`);
			if (res.ok) {
				const stats: DashboardStats = await res.json();
				msgs = buildMessages(stats);
			}
		} catch (e) {
			console.error('Failed to fetch dashboard stats:', e);
		}

		loading = false;
		startTypewriter(msgs);
	});

	onDestroy(() => {
		if (typewriterInterval) clearInterval(typewriterInterval);
		if (pauseTimeout) clearTimeout(pauseTimeout);
	});
</script>

{#if !loading}
	<div class="flex items-center justify-center h-8 font-mono text-sm text-[var(--text-muted)]">
		<span class="text-[var(--accent)] mr-2">&gt;</span>
		<span class="min-w-0">{currentMessage}</span>
		<span class="cursor" class:blink={!isTyping}>_</span>
	</div>
{/if}

<style>
	.cursor {
		margin-left: 1px;
	}

	.blink {
		animation: blink 1s step-end infinite;
	}

	@keyframes blink {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0;
		}
	}
</style>
