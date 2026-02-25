<script lang="ts">
	import {
		Database,
		Globe,
		KanbanSquare,
		GitBranch,
		Github,
		BarChart3,
		HardDrive,
		Microscope,
		Plug,
		BookOpen
	} from 'lucide-svelte';

	interface Props {
		serverName: string;
		size?: number;
	}

	let { serverName, size = 20 }: Props = $props();

	const iconMap: Record<string, typeof Database> = {
		coderoots: Database,
		plugin_playwright_playwright: Globe,
		'plane-project-task-manager': KanbanSquare,
		'claude-flow': GitBranch,
		plugin_github_github: Github,
		plugin_linear_linear: BarChart3,
		filesystem: HardDrive,
		analyzer: Microscope,
		context7: BookOpen
	};

	let IconComponent = $derived(iconMap[serverName] ?? Plug);
</script>

<svelte:component this={IconComponent} {size} strokeWidth={2} />
