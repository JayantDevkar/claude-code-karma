/**
 * Task utility functions for enriching and computing task states.
 */

import type { Task, TaskWithState } from '$lib/api-types';

/**
 * Enriches raw tasks with computed state (isBlocked, isReady).
 * @param tasks - Array of tasks from the API
 * @returns Array of tasks with computed state
 */
export function enrichTasks(tasks: Task[]): TaskWithState[] {
	const taskMap = new Map(tasks.map((t) => [t.id, t]));

	return tasks.map((task) => {
		// Check if any blocker is incomplete
		const isBlocked = task.blocked_by.some((id) => {
			const blocker = taskMap.get(id);
			return blocker && blocker.status !== 'completed';
		});

		const isReady = task.status === 'pending' && !isBlocked;

		return { ...task, isBlocked, isReady };
	});
}

/**
 * Gets the currently active (in_progress) task.
 * @param tasks - Array of tasks
 * @returns The active task or null
 */
export function getActiveTask(tasks: Task[]): Task | null {
	return tasks.find((t) => t.status === 'in_progress') || null;
}

/**
 * Counts completed tasks.
 * @param tasks - Array of tasks
 * @returns Number of completed tasks
 */
export function getCompletedCount(tasks: Task[]): number {
	return tasks.filter((t) => t.status === 'completed').length;
}

/**
 * Creates a lookup function to get task subjects by ID.
 * @param tasks - Array of tasks
 * @returns Function that returns subject for a task ID
 */
export function createTaskSubjectLookup(tasks: Task[]): (id: string) => string {
	const taskMap = new Map(tasks.map((t) => [t.id, t.subject]));
	return (id: string) => taskMap.get(id) || `Task ${id}`;
}
