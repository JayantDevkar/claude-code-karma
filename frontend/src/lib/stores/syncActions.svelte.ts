/**
 * Client-side store for user-initiated sync actions.
 * Tabs push events here; ActivityTab reads and displays them
 * alongside Syncthing events.
 */

export interface SyncAction {
	id: number;
	type: 'member_added' | 'member_removed' | 'team_deleted' | 'project_added' | 'project_removed' | 'watch_started' | 'watch_stopped' | 'pending_accepted';
	title: string;
	detail: string;
	time: string;
}

let nextId = 1;
let actions = $state<SyncAction[]>([]);

export function pushSyncAction(type: SyncAction['type'], title: string, detail: string = '') {
	actions = [
		...actions,
		{
			id: nextId++,
			type,
			title,
			detail,
			time: new Date().toISOString()
		}
	].slice(-50); // keep last 50
}

export function getSyncActions(): SyncAction[] {
	return actions;
}
