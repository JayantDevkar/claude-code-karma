<script lang="ts">
	import NavigationCard from '$lib/components/NavigationCard.svelte';
	import TerminalDisplay from '$lib/components/TerminalDisplay.svelte';
	import LiveSessionsTerminal from '$lib/components/LiveSessionsTerminal.svelte';
	import {
		FolderOpen,
		LineChart,
		Bot,
		Wrench,
		History,
		Settings,
		FileText,
		MessageSquare,
		Puzzle,
		Cable,
		Webhook,
		Terminal
	} from 'lucide-svelte';
</script>

<div
	class="max-w-[560px] mx-auto flex flex-col items-center justify-center scale-120 origin-top w-full px-4"
>
	<div class="grid grid-cols-2 sm:grid-cols-3 gap-3 w-full">
		<NavigationCard title="Projects" href="/projects" icon={FolderOpen} color="blue" />
		<NavigationCard title="Sessions" href="/sessions" icon={MessageSquare} color="teal" />
		<NavigationCard title="Analytics" href="/analytics" icon={LineChart} color="green" />
		<NavigationCard title="Plans" href="/plans" icon={FileText} color="yellow" />
		<NavigationCard title="Skills" href="/skills" icon={Wrench} color="orange" />
		<NavigationCard title="Agents" href="/agents" icon={Bot} color="purple" />
		<NavigationCard title="Tools" href="/tools" icon={Cable} color="teal" />
		<NavigationCard title="Hooks" href="/hooks" icon={Webhook} color="amber" />
		<NavigationCard title="Commands" href="/commands" icon={Terminal} color="red" />
		<NavigationCard title="Plugins" href="/plugins" icon={Puzzle} color="violet" />
		<NavigationCard title="Archived" href="/archived" icon={History} color="gray" />
		<NavigationCard title="Settings" href="/settings" icon={Settings} color="indigo" />
	</div>

	<!-- Live Sessions Terminal -->
	<div class="mt-6 w-full">
		<LiveSessionsTerminal />
	</div>

	<!-- Terminal Stats Display -->
	<div class="mt-4 w-full">
		<TerminalDisplay />
	</div>
</div>
