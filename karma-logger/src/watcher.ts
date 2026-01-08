/**
 * File Watcher for Claude Code session logs
 * Phase 2: Watch for new entries and tail files in real-time
 */

import { EventEmitter } from 'node:events';
import { open, stat } from 'node:fs/promises';
import { createReadStream, existsSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { join } from 'node:path';
import chokidar from 'chokidar';
import type { FSWatcher } from 'chokidar';

import { findClaudeLogsDir, parseSessionPath, type SessionInfo } from './discovery.js';
import { isValidEntry, normalizeEntry } from './parser.js';
import type { LogEntry } from './types.js';

/**
 * Events emitted by LogWatcher
 */
export interface WatcherEvents {
  entry: (entry: LogEntry, session: SessionInfo) => void;
  'session:start': (session: SessionInfo) => void;
  'session:update': (session: SessionInfo) => void;
  'agent:spawn': (agent: SessionInfo, parentSession: SessionInfo) => void;
  error: (error: Error) => void;
  ready: () => void;
}

/**
 * Watcher options
 */
export interface WatcherOptions {
  /** Watch only a specific project path */
  projectPath?: string;
  /** Watch only a specific session ID */
  sessionId?: string;
  /** Process existing entries on start */
  processExisting?: boolean;
  /** Custom logs directory (for testing) */
  logsDir?: string;
  /** Stability threshold in ms before processing changes */
  stabilityThreshold?: number;
}

/**
 * File watcher for Claude Code logs
 * Emits events for new log entries, sessions, and agents
 */
export class LogWatcher extends EventEmitter {
  private watcher: FSWatcher | null = null;
  private filePositions: Map<string, number> = new Map();
  private knownSessions: Map<string, SessionInfo> = new Map();
  private logsDir: string;
  private options: WatcherOptions;

  constructor(options: WatcherOptions = {}) {
    super();
    this.options = options;
    this.logsDir = options.logsDir ?? findClaudeLogsDir();
  }

  /**
   * Start watching for log changes
   */
  watch(): void {
    if (this.watcher) {
      return; // Already watching
    }

    if (!existsSync(this.logsDir)) {
      this.emit('error', new Error(`Claude logs directory not found: ${this.logsDir}`));
      return;
    }

    const watchPath = this.buildWatchPath();
    const watchPattern = `${watchPath}/**/*.jsonl`;

    this.watcher = chokidar.watch(watchPattern, {
      persistent: true,
      ignoreInitial: !this.options.processExisting,
      awaitWriteFinish: {
        stabilityThreshold: this.options.stabilityThreshold ?? 100,
        pollInterval: 50,
      },
      usePolling: false,
      followSymlinks: true, // Follow symlinked .claude directories
      depth: 3, // project/session/agent.jsonl
    });

    this.watcher.on('add', (filePath) => this.handleNewFile(filePath));
    this.watcher.on('change', (filePath) => this.handleFileChange(filePath));
    this.watcher.on('error', (error) => this.emit('error', error));
    this.watcher.on('ready', () => this.emit('ready'));
  }

  /**
   * Stop watching
   */
  async stop(): Promise<void> {
    if (this.watcher) {
      await this.watcher.close();
      this.watcher = null;
    }
    this.filePositions.clear();
    this.knownSessions.clear();
  }

  /**
   * Check if currently watching
   */
  isWatching(): boolean {
    return this.watcher !== null;
  }

  /**
   * Get current file positions (for debugging/testing)
   */
  getFilePositions(): Map<string, number> {
    return new Map(this.filePositions);
  }

  /**
   * Build the watch path based on options
   */
  private buildWatchPath(): string {
    let path = this.logsDir;

    if (this.options.projectPath) {
      path = join(path, this.options.projectPath);

      if (this.options.sessionId) {
        // Watch specific session and its agents
        path = join(path, this.options.sessionId);
      }
    }

    return path;
  }

  /**
   * Handle a new file being detected
   */
  private async handleNewFile(filePath: string): Promise<void> {
    const sessionInfo = parseSessionPath(filePath, this.logsDir);
    if (!sessionInfo) return;

    try {
      const stats = await stat(filePath);
      sessionInfo.modifiedAt = stats.mtime;
    } catch {
      return; // File might have been deleted
    }

    // Track this session
    this.knownSessions.set(filePath, sessionInfo);

    if (sessionInfo.isAgent && sessionInfo.parentSessionId) {
      // Find parent session
      const parentPath = this.findParentSessionPath(sessionInfo);
      const parentSession = parentPath ? this.knownSessions.get(parentPath) : undefined;

      if (parentSession) {
        this.emit('agent:spawn', sessionInfo, parentSession);
      }
    } else {
      this.emit('session:start', sessionInfo);
    }

    // Initialize file position
    if (this.options.processExisting) {
      this.filePositions.set(filePath, 0);
      await this.readNewEntries(filePath, sessionInfo);
    } else {
      // Start from end of file
      try {
        const stats = await stat(filePath);
        this.filePositions.set(filePath, stats.size);
      } catch {
        this.filePositions.set(filePath, 0);
      }
    }
  }

  /**
   * Handle a file change (new content)
   */
  private async handleFileChange(filePath: string): Promise<void> {
    const sessionInfo = this.knownSessions.get(filePath);
    if (!sessionInfo) {
      // New file we haven't seen - treat as new
      await this.handleNewFile(filePath);
      return;
    }

    // Update modification time
    try {
      const stats = await stat(filePath);
      sessionInfo.modifiedAt = stats.mtime;
    } catch {
      return;
    }

    this.emit('session:update', sessionInfo);
    await this.readNewEntries(filePath, sessionInfo);
  }

  /**
   * Read new entries from a file since last position
   */
  private async readNewEntries(filePath: string, sessionInfo: SessionInfo): Promise<void> {
    const startPosition = this.filePositions.get(filePath) ?? 0;

    try {
      const stats = await stat(filePath);

      // File was truncated - reset position
      if (stats.size < startPosition) {
        this.filePositions.set(filePath, 0);
        return;
      }

      // No new content
      if (stats.size === startPosition) {
        return;
      }

      // Read new content
      const fileHandle = await open(filePath, 'r');

      try {
        const stream = fileHandle.createReadStream({
          start: startPosition,
          encoding: 'utf8',
        });

        const rl = createInterface({
          input: stream,
          crlfDelay: Infinity,
        });

        let newPosition = startPosition;

        for await (const line of rl) {
          newPosition += Buffer.byteLength(line, 'utf8') + 1; // +1 for newline

          if (!line.trim()) continue;

          try {
            const parsed = JSON.parse(line);
            if (isValidEntry(parsed)) {
              const entry = normalizeEntry(parsed);
              this.emit('entry', entry, sessionInfo);
            }
          } catch {
            // Skip malformed JSON
          }
        }

        this.filePositions.set(filePath, newPosition);
      } finally {
        await fileHandle.close();
      }
    } catch (error) {
      this.emit('error', error as Error);
    }
  }

  /**
   * Find the file path for a parent session
   */
  private findParentSessionPath(agentInfo: SessionInfo): string | null {
    // Parent session file should be at: project/session-id.jsonl
    const parentFilename = `${agentInfo.parentSessionId}.jsonl`;
    const parentPath = join(this.logsDir, agentInfo.projectPath, parentFilename);

    for (const [path] of this.knownSessions) {
      if (path === parentPath) {
        return path;
      }
    }

    return null;
  }
}

/**
 * Create a watcher with typed event handlers
 */
export function createWatcher(options?: WatcherOptions): LogWatcher {
  return new LogWatcher(options);
}

/**
 * Watch a specific project
 */
export function watchProject(projectPath: string, options?: Omit<WatcherOptions, 'projectPath'>): LogWatcher {
  return new LogWatcher({ ...options, projectPath });
}

/**
 * Watch a specific session (including its agents)
 */
export function watchSession(
  projectPath: string,
  sessionId: string,
  options?: Omit<WatcherOptions, 'projectPath' | 'sessionId'>
): LogWatcher {
  return new LogWatcher({ ...options, projectPath, sessionId });
}
