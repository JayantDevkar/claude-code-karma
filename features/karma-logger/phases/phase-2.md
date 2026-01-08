# Phase 2: Log Discovery & Watcher

**Status:** Complete
**Estimated Effort:** Medium
**Dependencies:** Phase 1
**Deliverable:** File watcher that detects and tails active Claude Code sessions

---

## Objective

Implement log discovery to find active sessions and a file watcher to tail new entries in real-time.

---

## Tasks

### 2.1 Install Dependencies
```bash
npm install chokidar
npm install -D @types/chokidar
```

### 2.2 Implement Session Discovery
- [ ] Create `src/discovery.ts`
- [ ] Locate `~/.claude/projects/` directory
- [ ] Identify project directories
- [ ] Find most recent session file per project

```typescript
// src/discovery.ts
export function findClaudeLogsDir(): string {
  return path.join(os.homedir(), '.claude', 'projects');
}

export async function discoverSessions(): Promise<SessionInfo[]> {
  // Find all *.jsonl files
  // Group by project
  // Return sorted by modification time
}
```

### 2.3 Distinguish Session Types
- [ ] Main session: `<session-id>.jsonl`
- [ ] Agent files: `<session-id>/<agent-id>.jsonl`
- [ ] Build file path parser

### 2.4 Implement File Watcher
- [ ] Create `src/watcher.ts`
- [ ] Use chokidar for cross-platform watching
- [ ] Watch for file changes and new files
- [ ] Emit events for new entries

```typescript
// src/watcher.ts
export class LogWatcher extends EventEmitter {
  private watcher: FSWatcher;
  private filePositions: Map<string, number>;

  watch(projectPath?: string): void;
  stop(): void;

  // Events:
  // 'entry' - new log entry parsed
  // 'session:start' - new session detected
  // 'agent:spawn' - new agent file created
}
```

### 2.5 Handle File Tailing
- [ ] Track read position per file
- [ ] Read only new content on change
- [ ] Handle file rotation/truncation

### 2.6 Current Project Detection
- [ ] Parse `git remote get-url origin`
- [ ] Map remote URL to project directory
- [ ] Default to watching current project

---

## Key Code

```typescript
// src/watcher.ts
export class LogWatcher extends EventEmitter {
  constructor(private logsDir: string) {
    super();
    this.filePositions = new Map();
  }

  watch(projectPath?: string): void {
    const watchPath = projectPath
      ? path.join(this.logsDir, projectPath)
      : this.logsDir;

    this.watcher = chokidar.watch(`${watchPath}/**/*.jsonl`, {
      persistent: true,
      ignoreInitial: false,
      awaitWriteFinish: { stabilityThreshold: 100 },
    });

    this.watcher.on('add', (fp) => this.handleNewFile(fp));
    this.watcher.on('change', (fp) => this.tailFile(fp));
  }
}
```

---

## Acceptance Criteria

1. `discoverSessions()` finds all sessions in `~/.claude/projects/`
2. Watcher detects new entries within 500ms of write
3. Agent files correctly associated with parent session
4. Works on macOS and Linux

---

## Exit Condition

Phase complete when watcher emits `entry` events for live Claude Code activity.
