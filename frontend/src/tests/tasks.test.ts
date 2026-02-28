import { describe, it, expect } from 'vitest';
import { enrichTasks, getActiveTask, getCompletedCount, createTaskSubjectLookup } from '$lib/utils/tasks';

// Minimal Task shape for tests — mirrors the real Task interface
type TaskStatus = 'pending' | 'in_progress' | 'completed';

interface MockTask {
	id: string;
	subject: string;
	description: string;
	status: TaskStatus;
	active_form: string | null;
	blocks: string[];
	blocked_by: string[];
}

function makeTask(overrides: Partial<MockTask> & Pick<MockTask, 'id' | 'subject'>): MockTask {
	return {
		description: '',
		status: 'pending',
		active_form: null,
		blocks: [],
		blocked_by: [],
		...overrides
	};
}

// ============================================================
// enrichTasks
// ============================================================
describe('enrichTasks', () => {
	it('returns empty array for empty input', () => {
		expect(enrichTasks([])).toEqual([]);
	});

	it('marks task with no blockers as not blocked and ready', () => {
		const tasks = [makeTask({ id: '1', subject: 'Task 1' })];
		const result = enrichTasks(tasks as any);
		expect(result[0].isBlocked).toBe(false);
		expect(result[0].isReady).toBe(true);
	});

	it('marks task blocked by incomplete task as blocked', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Blocker', status: 'pending' }),
			makeTask({ id: '2', subject: 'Blocked', status: 'pending', blocked_by: ['1'] })
		];
		const result = enrichTasks(tasks as any);
		expect(result[1].isBlocked).toBe(true);
		expect(result[1].isReady).toBe(false);
	});

	it('marks task as not blocked when blocker is completed', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Blocker', status: 'completed' }),
			makeTask({ id: '2', subject: 'Unblocked', status: 'pending', blocked_by: ['1'] })
		];
		const result = enrichTasks(tasks as any);
		expect(result[1].isBlocked).toBe(false);
		expect(result[1].isReady).toBe(true);
	});

	it('marks in_progress task as not ready even without blockers', () => {
		const tasks = [makeTask({ id: '1', subject: 'Active', status: 'in_progress' })];
		const result = enrichTasks(tasks as any);
		expect(result[0].isReady).toBe(false);
		expect(result[0].isBlocked).toBe(false);
	});

	it('marks completed task as not ready', () => {
		const tasks = [makeTask({ id: '1', subject: 'Done', status: 'completed' })];
		const result = enrichTasks(tasks as any);
		expect(result[0].isReady).toBe(false);
	});

	it('handles missing blocker id gracefully (blocker not in list)', () => {
		// blocked_by references a task that doesn't exist in the array
		const tasks = [
			makeTask({ id: '2', subject: 'Task', status: 'pending', blocked_by: ['999'] })
		];
		const result = enrichTasks(tasks as any);
		// Unknown blocker => treated as not blocking (blocker not found in map)
		expect(result[0].isBlocked).toBe(false);
		expect(result[0].isReady).toBe(true);
	});

	it('preserves all original task fields', () => {
		const tasks = [makeTask({ id: '1', subject: 'Keep fields', description: 'desc' })];
		const result = enrichTasks(tasks as any);
		expect(result[0].subject).toBe('Keep fields');
		expect(result[0].description).toBe('desc');
	});

	it('handles multiple blockers — blocked if any incomplete', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Done', status: 'completed' }),
			makeTask({ id: '2', subject: 'Pending', status: 'pending' }),
			makeTask({ id: '3', subject: 'Target', status: 'pending', blocked_by: ['1', '2'] })
		];
		const result = enrichTasks(tasks as any);
		expect(result[2].isBlocked).toBe(true);
	});

	it('handles multiple blockers — ready when all completed', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Done 1', status: 'completed' }),
			makeTask({ id: '2', subject: 'Done 2', status: 'completed' }),
			makeTask({ id: '3', subject: 'Target', status: 'pending', blocked_by: ['1', '2'] })
		];
		const result = enrichTasks(tasks as any);
		expect(result[2].isBlocked).toBe(false);
		expect(result[2].isReady).toBe(true);
	});
});

// ============================================================
// getActiveTask
// ============================================================
describe('getActiveTask', () => {
	it('returns null for empty array', () => {
		expect(getActiveTask([])).toBeNull();
	});

	it('returns the in_progress task', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Pending', status: 'pending' }),
			makeTask({ id: '2', subject: 'Active', status: 'in_progress' }),
			makeTask({ id: '3', subject: 'Done', status: 'completed' })
		];
		const result = getActiveTask(tasks as any);
		expect(result?.id).toBe('2');
	});

	it('returns null when no in_progress task', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Pending' }),
			makeTask({ id: '2', subject: 'Done', status: 'completed' })
		];
		expect(getActiveTask(tasks as any)).toBeNull();
	});

	it('returns first in_progress task when multiple exist', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'First active', status: 'in_progress' }),
			makeTask({ id: '2', subject: 'Second active', status: 'in_progress' })
		];
		const result = getActiveTask(tasks as any);
		expect(result?.id).toBe('1');
	});
});

// ============================================================
// getCompletedCount
// ============================================================
describe('getCompletedCount', () => {
	it('returns 0 for empty array', () => {
		expect(getCompletedCount([])).toBe(0);
	});

	it('counts completed tasks correctly', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Done 1', status: 'completed' }),
			makeTask({ id: '2', subject: 'Pending' }),
			makeTask({ id: '3', subject: 'Done 2', status: 'completed' }),
			makeTask({ id: '4', subject: 'Active', status: 'in_progress' })
		];
		expect(getCompletedCount(tasks as any)).toBe(2);
	});

	it('returns 0 when no completed tasks', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Pending' }),
			makeTask({ id: '2', subject: 'Active', status: 'in_progress' })
		];
		expect(getCompletedCount(tasks as any)).toBe(0);
	});

	it('returns total count when all completed', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'Done 1', status: 'completed' }),
			makeTask({ id: '2', subject: 'Done 2', status: 'completed' })
		];
		expect(getCompletedCount(tasks as any)).toBe(2);
	});
});

// ============================================================
// createTaskSubjectLookup
// ============================================================
describe('createTaskSubjectLookup', () => {
	it('returns subject for a known task id', () => {
		const tasks = [
			makeTask({ id: '1', subject: 'First task' }),
			makeTask({ id: '2', subject: 'Second task' })
		];
		const lookup = createTaskSubjectLookup(tasks as any);
		expect(lookup('1')).toBe('First task');
		expect(lookup('2')).toBe('Second task');
	});

	it('returns "Task {id}" for unknown id', () => {
		const tasks = [makeTask({ id: '1', subject: 'Only task' })];
		const lookup = createTaskSubjectLookup(tasks as any);
		expect(lookup('999')).toBe('Task 999');
	});

	it('returns lookup function for empty tasks', () => {
		const lookup = createTaskSubjectLookup([]);
		expect(lookup('1')).toBe('Task 1');
	});
});
