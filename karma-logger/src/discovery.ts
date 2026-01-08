/**
 * Log Discovery for Claude Code sessions
 * Phase 2: Find and enumerate active sessions in ~/.claude/projects/
 */

import { homedir } from 'node:os';
import { join, basename, dirname, relative } from 'node:path';
import { readdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';

/**
 * Information about a discovered session
 */
export interface SessionInfo {
  sessionId: string;
  projectPath: string;
  projectName: string;
  filePath: string;
  modifiedAt: Date;
  isAgent: boolean;
  parentSessionId?: string;
}

/**
 * Project with its sessions
 */
export interface ProjectInfo {
  projectPath: string;
  projectName: string;
  sessions: SessionInfo[];
  lastActivity: Date;
}

/**
 * Get the Claude logs directory
 */
export function findClaudeLogsDir(): string {
  return join(homedir(), '.claude', 'projects');
}

/**
 * Check if Claude logs directory exists
 */
export function claudeLogsDirExists(): boolean {
  return existsSync(findClaudeLogsDir());
}

/**
 * Parse a JSONL file path to extract session info
 *
 * Patterns:
 * - Main session: <project-path>/<session-id>.jsonl
 * - Agent file: <project-path>/<session-id>/<agent-id>.jsonl
 */
export function parseSessionPath(filePath: string, logsDir: string): SessionInfo | null {
  const relativePath = relative(logsDir, filePath);
  const parts = relativePath.split('/');

  if (parts.length < 2) return null;

  const filename = basename(filePath, '.jsonl');
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  // Agent file: project/session-id/agent-id.jsonl
  if (parts.length >= 3 && uuidPattern.test(parts[parts.length - 2])) {
    const projectPath = parts.slice(0, -2).join('/');
    const parentSessionId = parts[parts.length - 2];
    return {
      sessionId: filename,
      projectPath,
      projectName: extractProjectName(projectPath),
      filePath,
      modifiedAt: new Date(),
      isAgent: true,
      parentSessionId,
    };
  }

  // Main session: project/session-id.jsonl
  if (uuidPattern.test(filename)) {
    const projectPath = parts.slice(0, -1).join('/');
    return {
      sessionId: filename,
      projectPath,
      projectName: extractProjectName(projectPath),
      filePath,
      modifiedAt: new Date(),
      isAgent: false,
    };
  }

  return null;
}

/**
 * Extract a readable project name from path
 */
function extractProjectName(projectPath: string): string {
  // Path is URL-encoded like: Users-jayant-Documents-GitHub-project
  const parts = projectPath.split('-');
  return parts[parts.length - 1] || projectPath;
}

/**
 * Recursively find all JSONL files in a directory
 */
async function findJsonlFiles(dir: string): Promise<string[]> {
  const files: string[] = [];

  try {
    const entries = await readdir(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = join(dir, entry.name);

      if (entry.isDirectory()) {
        const subFiles = await findJsonlFiles(fullPath);
        files.push(...subFiles);
      } else if (entry.isFile() && entry.name.endsWith('.jsonl')) {
        files.push(fullPath);
      }
    }
  } catch {
    // Directory might not exist or be accessible
  }

  return files;
}

/**
 * Discover all sessions in the Claude logs directory
 */
export async function discoverSessions(logsDir?: string): Promise<SessionInfo[]> {
  const dir = logsDir ?? findClaudeLogsDir();

  if (!existsSync(dir)) {
    return [];
  }

  const files = await findJsonlFiles(dir);
  const sessions: SessionInfo[] = [];

  for (const filePath of files) {
    const info = parseSessionPath(filePath, dir);
    if (info) {
      try {
        const stats = await stat(filePath);
        info.modifiedAt = stats.mtime;
        sessions.push(info);
      } catch {
        // File might have been deleted
      }
    }
  }

  // Sort by modification time, newest first
  return sessions.sort((a, b) => b.modifiedAt.getTime() - a.modifiedAt.getTime());
}

/**
 * Discover sessions for a specific project path
 */
export async function discoverProjectSessions(projectPath: string): Promise<SessionInfo[]> {
  const logsDir = findClaudeLogsDir();
  const projectDir = join(logsDir, projectPath);

  if (!existsSync(projectDir)) {
    return [];
  }

  const files = await findJsonlFiles(projectDir);
  const sessions: SessionInfo[] = [];

  for (const filePath of files) {
    const info = parseSessionPath(filePath, logsDir);
    if (info) {
      try {
        const stats = await stat(filePath);
        info.modifiedAt = stats.mtime;
        sessions.push(info);
      } catch {
        // Skip inaccessible files
      }
    }
  }

  return sessions.sort((a, b) => b.modifiedAt.getTime() - a.modifiedAt.getTime());
}

/**
 * Get the most recent session for a project
 */
export async function getLatestSession(projectPath?: string): Promise<SessionInfo | null> {
  const sessions = projectPath
    ? await discoverProjectSessions(projectPath)
    : await discoverSessions();

  // Find most recent non-agent session
  const mainSessions = sessions.filter(s => !s.isAgent);
  return mainSessions[0] ?? null;
}

/**
 * Group sessions by project
 */
export async function discoverProjects(logsDir?: string): Promise<ProjectInfo[]> {
  const sessions = await discoverSessions(logsDir);
  const projectMap = new Map<string, SessionInfo[]>();

  for (const session of sessions) {
    const existing = projectMap.get(session.projectPath) ?? [];
    existing.push(session);
    projectMap.set(session.projectPath, existing);
  }

  const projects: ProjectInfo[] = [];

  for (const [projectPath, projectSessions] of projectMap) {
    projects.push({
      projectPath,
      projectName: projectSessions[0]?.projectName ?? projectPath,
      sessions: projectSessions,
      lastActivity: projectSessions[0]?.modifiedAt ?? new Date(0),
    });
  }

  // Sort by last activity
  return projects.sort((a, b) => b.lastActivity.getTime() - a.lastActivity.getTime());
}

/**
 * Get all agent files for a session
 */
export async function getSessionAgents(
  projectPath: string,
  sessionId: string
): Promise<SessionInfo[]> {
  const logsDir = findClaudeLogsDir();
  const agentDir = join(logsDir, projectPath, sessionId);

  if (!existsSync(agentDir)) {
    return [];
  }

  const files = await findJsonlFiles(agentDir);
  const agents: SessionInfo[] = [];

  for (const filePath of files) {
    const info = parseSessionPath(filePath, logsDir);
    if (info && info.isAgent) {
      try {
        const stats = await stat(filePath);
        info.modifiedAt = stats.mtime;
        agents.push(info);
      } catch {
        // Skip inaccessible
      }
    }
  }

  return agents.sort((a, b) => b.modifiedAt.getTime() - a.modifiedAt.getTime());
}
