/**
 * Project Grouping Utility
 * Groups projects by git root path into collapsible sections
 * Ports the grouping logic from React's use-grouped-projects.ts
 */

import type { Project } from '$lib/api-types';

export interface GitRootGroup {
	rootPath: string;
	displayName: string;
	rootProject: Project | null;
	nestedProjects: Project[];
	totalSessions: number;
	totalAgents: number;
}

export interface GroupedProjects {
	gitRoots: GitRootGroup[];
	singleGitProjects: Project[];
	otherProjects: Project[];
	totalCount: number;
}

/**
 * Groups projects by git root path
 *
 * Algorithm:
 * 1. Separate projects into git projects and non-git projects
 * 2. Group git projects by git_root_path
 * 3. Within each group, identify root project and nested projects
 * 4. Route single-project groups to singleGitProjects, multi-project groups to gitRoots
 * 5. Sort all arrays by latest session time
 */
export function groupProjects(projects: Project[]): GroupedProjects {
	if (!projects || projects.length === 0) {
		return {
			gitRoots: [],
			singleGitProjects: [],
			otherProjects: [],
			totalCount: 0
		};
	}

	// Step 1: Separate git projects from non-git projects
	const gitProjects = projects.filter(
		(p) => p.git_root_path !== null && p.git_root_path !== undefined
	);
	const nonGitProjects = projects.filter((p) => !p.git_root_path);

	// Step 2: Group git projects by git_root_path
	const groupMap = new Map<string, Project[]>();
	for (const project of gitProjects) {
		const rootPath = project.git_root_path!;
		if (!groupMap.has(rootPath)) {
			groupMap.set(rootPath, []);
		}
		groupMap.get(rootPath)!.push(project);
	}

	// Step 3 & 4: Process each group and classify by size
	const gitRoots: GitRootGroup[] = [];
	const singleGitProjects: Project[] = [];

	for (const [rootPath, groupProjects] of groupMap.entries()) {
		// Identify root project (where path === git_root_path and is_nested_project === false)
		const rootProject =
			groupProjects.find((p) => p.path === rootPath && !p.is_nested_project) || null;

		// Identify nested projects (where is_nested_project === true)
		const nestedProjects = groupProjects
			.filter((p) => p.is_nested_project)
			.sort((a, b) => {
				const timeA = getLatestSessionTime(a);
				const timeB = getLatestSessionTime(b);
				return timeB - timeA; // Most recent first
			});

		const totalProjects = (rootProject ? 1 : 0) + nestedProjects.length;

		// Route based on group size
		if (totalProjects === 1) {
			// Single project in this git repo -> flat card
			if (rootProject) {
				singleGitProjects.push(rootProject);
			} else if (nestedProjects.length === 1) {
				singleGitProjects.push(nestedProjects[0]);
			}
		} else {
			// Multiple projects -> collapsible group
			const totalSessions =
				(rootProject?.session_count || 0) +
				nestedProjects.reduce((sum, p) => sum + p.session_count, 0);
			const totalAgents =
				(rootProject?.agent_count || 0) +
				nestedProjects.reduce((sum, p) => sum + p.agent_count, 0);

			gitRoots.push({
				rootPath,
				displayName: getDisplayName(rootPath),
				rootProject,
				nestedProjects,
				totalSessions,
				totalAgents
			});
		}
	}

	// Step 5: Sort all arrays by latest session time
	gitRoots.sort((a, b) => getGroupLatestTime(b) - getGroupLatestTime(a));
	singleGitProjects.sort((a, b) => getLatestSessionTime(b) - getLatestSessionTime(a));
	nonGitProjects.sort((a, b) => getLatestSessionTime(b) - getLatestSessionTime(a));

	return {
		gitRoots,
		singleGitProjects,
		otherProjects: nonGitProjects,
		totalCount: projects.length
	};
}

/**
 * Get the latest session time from a project
 */
function getLatestSessionTime(project: Project): number {
	if (!project.sessions || project.sessions.length === 0) {
		return 0;
	}

	const times = project.sessions
		.map((s) => s.start_time)
		.filter((t): t is string => t !== null && t !== undefined)
		.map((t) => new Date(t).getTime());

	return times.length > 0 ? Math.max(...times) : 0;
}

/**
 * Get the latest session time from a git root group
 */
function getGroupLatestTime(group: GitRootGroup): number {
	const allProjects = [
		...(group.rootProject ? [group.rootProject] : []),
		...group.nestedProjects
	];

	const times = allProjects.map((p) => getLatestSessionTime(p)).filter((t) => t > 0);

	return times.length > 0 ? Math.max(...times) : 0;
}

/**
 * Extract display name from absolute path
 * /Users/me/repo -> "repo"
 */
function getDisplayName(path: string): string {
	const segments = path.split('/').filter(Boolean);
	return segments[segments.length - 1] || path;
}

/**
 * Calculate relative path for nested projects
 * /Users/me/repo/packages/api -> "./packages/api"
 */
export function getRelativePath(projectPath: string, rootPath: string): string {
	if (projectPath === rootPath) {
		return '';
	}
	if (projectPath.startsWith(rootPath + '/')) {
		return './' + projectPath.slice(rootPath.length + 1);
	}
	return projectPath;
}
