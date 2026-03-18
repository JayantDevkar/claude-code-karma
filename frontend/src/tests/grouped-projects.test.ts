import { describe, it, expect } from 'vitest';
import { groupProjects, getRelativePath } from '$lib/utils/grouped-projects';

// Minimal Project shape for tests
interface MockSession {
	start_time: string;
}

interface MockProject {
	encoded_name: string;
	path: string;
	git_root_path: string | null;
	is_nested_project: boolean;
	session_count: number;
	agent_count: number;
	sessions: MockSession[];
}

function makeProject(overrides: Partial<MockProject> & Pick<MockProject, 'encoded_name' | 'path'>): MockProject {
	return {
		git_root_path: null,
		is_nested_project: false,
		session_count: 0,
		agent_count: 0,
		sessions: [],
		...overrides
	};
}

// ============================================================
// groupProjects — empty input
// ============================================================
describe('groupProjects — empty input', () => {
	it('returns empty structure for empty array', () => {
		const result = groupProjects([]);
		expect(result.gitRoots).toEqual([]);
		expect(result.singleGitProjects).toEqual([]);
		expect(result.otherProjects).toEqual([]);
		expect(result.totalCount).toBe(0);
	});

	it('returns empty structure for null/undefined-like (empty array)', () => {
		const result = groupProjects([] as any);
		expect(result.totalCount).toBe(0);
	});
});

// ============================================================
// groupProjects — non-git projects
// ============================================================
describe('groupProjects — non-git projects', () => {
	it('places projects without git_root_path into otherProjects', () => {
		const projects = [
			makeProject({ encoded_name: 'proj1', path: '/tmp/proj1' })
		];
		const result = groupProjects(projects as any);
		expect(result.otherProjects).toHaveLength(1);
		expect(result.gitRoots).toHaveLength(0);
		expect(result.singleGitProjects).toHaveLength(0);
		expect(result.totalCount).toBe(1);
	});

	it('sorts otherProjects by latest session time (most recent first)', () => {
		const projects = [
			makeProject({
				encoded_name: 'older',
				path: '/tmp/older',
				sessions: [{ start_time: '2024-01-01T00:00:00Z' }]
			}),
			makeProject({
				encoded_name: 'newer',
				path: '/tmp/newer',
				sessions: [{ start_time: '2024-06-01T00:00:00Z' }]
			})
		];
		const result = groupProjects(projects as any);
		expect(result.otherProjects[0].encoded_name).toBe('newer');
		expect(result.otherProjects[1].encoded_name).toBe('older');
	});
});

// ============================================================
// groupProjects — single git project (flat card)
// ============================================================
describe('groupProjects — single git project', () => {
	it('places solo git project into singleGitProjects', () => {
		const projects = [
			makeProject({
				encoded_name: 'root-proj',
				path: '/Users/me/repo',
				git_root_path: '/Users/me/repo',
				is_nested_project: false
			})
		];
		const result = groupProjects(projects as any);
		expect(result.singleGitProjects).toHaveLength(1);
		expect(result.gitRoots).toHaveLength(0);
	});
});

// ============================================================
// groupProjects — multi-project git root (collapsible group)
// ============================================================
describe('groupProjects — multi-project git root', () => {
	it('groups root + nested project into gitRoots', () => {
		const projects = [
			makeProject({
				encoded_name: 'root',
				path: '/Users/me/monorepo',
				git_root_path: '/Users/me/monorepo',
				is_nested_project: false,
				session_count: 3,
				agent_count: 1
			}),
			makeProject({
				encoded_name: 'pkg-api',
				path: '/Users/me/monorepo/packages/api',
				git_root_path: '/Users/me/monorepo',
				is_nested_project: true,
				session_count: 2,
				agent_count: 4
			})
		];
		const result = groupProjects(projects as any);
		expect(result.gitRoots).toHaveLength(1);
		expect(result.singleGitProjects).toHaveLength(0);

		const group = result.gitRoots[0];
		expect(group.rootPath).toBe('/Users/me/monorepo');
		expect(group.displayName).toBe('monorepo');
		expect(group.rootProject?.encoded_name).toBe('root');
		expect(group.nestedProjects).toHaveLength(1);
		expect(group.nestedProjects[0].encoded_name).toBe('pkg-api');
		expect(group.totalSessions).toBe(5); // 3 + 2
		expect(group.totalAgents).toBe(5); // 1 + 4
	});

	it('groups multiple nested projects without a root project', () => {
		const projects = [
			makeProject({
				encoded_name: 'pkg-a',
				path: '/repo/packages/a',
				git_root_path: '/repo',
				is_nested_project: true,
				session_count: 1,
				agent_count: 0
			}),
			makeProject({
				encoded_name: 'pkg-b',
				path: '/repo/packages/b',
				git_root_path: '/repo',
				is_nested_project: true,
				session_count: 2,
				agent_count: 0
			})
		];
		const result = groupProjects(projects as any);
		expect(result.gitRoots).toHaveLength(1);
		const group = result.gitRoots[0];
		expect(group.rootProject).toBeNull();
		expect(group.nestedProjects).toHaveLength(2);
		expect(group.totalSessions).toBe(3);
	});

	it('totalCount equals number of input projects', () => {
		const projects = [
			makeProject({ encoded_name: 'a', path: '/repo', git_root_path: '/repo', is_nested_project: false }),
			makeProject({ encoded_name: 'b', path: '/repo/pkg', git_root_path: '/repo', is_nested_project: true }),
			makeProject({ encoded_name: 'c', path: '/other' })
		];
		const result = groupProjects(projects as any);
		expect(result.totalCount).toBe(3);
	});
});

// ============================================================
// getRelativePath
// ============================================================
describe('getRelativePath', () => {
	it('returns empty string when projectPath equals rootPath', () => {
		expect(getRelativePath('/Users/me/repo', '/Users/me/repo')).toBe('');
	});

	it('returns relative path with ./ prefix', () => {
		expect(getRelativePath('/Users/me/repo/packages/api', '/Users/me/repo')).toBe('./packages/api');
	});

	it('returns projectPath unchanged when not under rootPath', () => {
		expect(getRelativePath('/other/path', '/Users/me/repo')).toBe('/other/path');
	});

	it('handles deeply nested paths', () => {
		expect(getRelativePath('/root/a/b/c/d', '/root')).toBe('./a/b/c/d');
	});

	// Windows path tests
	it('handles Windows forward-slash paths', () => {
		expect(getRelativePath('C:/Users/me/repo/packages/api', 'C:/Users/me/repo')).toBe(
			'./packages/api'
		);
	});

	it('handles Windows backslash paths via normalization', () => {
		expect(
			getRelativePath('C:\\Users\\me\\repo\\packages\\api', 'C:\\Users\\me\\repo')
		).toBe('./packages/api');
	});

	it('returns empty for matching Windows paths', () => {
		expect(getRelativePath('C:/Users/me/repo', 'C:/Users/me/repo')).toBe('');
	});
});

// ============================================================
// groupProjects — Windows paths
// ============================================================
describe('groupProjects — Windows paths', () => {
	it('groups Windows projects by git root with correct display name', () => {
		const projects = [
			makeProject({
				encoded_name: 'C--Users-me-monorepo',
				path: 'C:/Users/me/monorepo',
				git_root_path: 'C:/Users/me/monorepo',
				is_nested_project: false,
				session_count: 3
			}),
			makeProject({
				encoded_name: 'C--Users-me-monorepo-packages-api',
				path: 'C:/Users/me/monorepo/packages/api',
				git_root_path: 'C:/Users/me/monorepo',
				is_nested_project: true,
				session_count: 2
			})
		];
		const result = groupProjects(projects as any);
		expect(result.gitRoots).toHaveLength(1);
		const group = result.gitRoots[0];
		expect(group.displayName).toBe('monorepo');
		expect(group.totalSessions).toBe(5);
	});

	it('places single Windows git project into singleGitProjects', () => {
		const projects = [
			makeProject({
				encoded_name: 'D--Projects-myapp',
				path: 'D:/Projects/myapp',
				git_root_path: 'D:/Projects/myapp',
				is_nested_project: false
			})
		];
		const result = groupProjects(projects as any);
		expect(result.singleGitProjects).toHaveLength(1);
	});
});
