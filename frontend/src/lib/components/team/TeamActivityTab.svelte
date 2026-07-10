<script lang="ts">
	import type { SyncEvent, SyncTeamMember } from '$lib/api-types';
	import TeamActivityFeed from './TeamActivityFeed.svelte';

	interface Props {
		teamName: string;
		activity: SyncEvent[];
		members?: SyncTeamMember[];
	}

	let { teamName, activity, members = [] }: Props = $props();
</script>

<div class="space-y-6">
	<!-- Activity feed -->
	<TeamActivityFeed events={activity} {teamName} {members} />
</div>
