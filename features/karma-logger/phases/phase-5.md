# Phase 5: `karma watch` Command

**Status:** Complete
**Estimated Effort:** Medium
**Dependencies:** Phase 4
**Deliverable:** Real-time streaming display of session activity

---

## Objective

Implement a live-updating watch mode that displays session activity as it happens, with running cost totals and agent hierarchy visualization.

---

## Tasks

### 5.1 Create Watch Command Handler
- [x] Create `src/commands/watch.ts`
- [x] Wire up to Commander in `cli.ts`
- [x] Handle Ctrl+C gracefully
- [x] Cleanup watchers on exit

### 5.2 Implement Live Output
- [x] Clear screen on start
- [x] Update display on new entries
- [x] Show running totals
- [x] Display activity feed

### 5.3 Design Watch Layout
```
┌─────────────────────────────────────────────────────────────┐
│  KARMA WATCH - claude-karma                    Cost: $1.24  │
│  Session: abc1234 | Agents: 3 active           ↑ Watching   │
├─────────────────────────────────────────────────────────────┤
│  TOKENS       In: 125.4K  Out: 42.1K  Cache: 89.2K          │
├─────────────────────────────────────────────────────────────┤
│  ACTIVITY                                                   │
│  14:32:05  [sonnet]  Read file: src/parser.ts               │
│  14:32:08  [haiku]   ├─ Agent spawned (explore)             │
│  14:32:12  [haiku]   │  Grep: "parseEntry"                  │
│  14:32:15  [haiku]   └─ Agent completed                     │
│  14:32:18  [sonnet]  Edit file: src/parser.ts               │
│  14:32:22  [sonnet]  Bash: npm test                         │
├─────────────────────────────────────────────────────────────┤
│  AGENT TREE                                                 │
│  ● main (sonnet) - $0.89                                    │
│    ├─ 7a3f2b1 explore (haiku) - $0.12                       │
│    ├─ 8b4e3c2 bash (sonnet) - $0.15                         │
│    └─ 9c5f4d3 refactor (sonnet) - $0.08  ← active           │
└─────────────────────────────────────────────────────────────┘
Press Ctrl+C to exit
```

### 5.4 Extract Tool Information
- [x] Parse tool names from entries
- [x] Show tool parameters (truncated)
- [x] Color-code by tool type

### 5.5 Build Agent Tree Display
- [x] ASCII tree rendering
- [x] Show agent type and model
- [x] Indicate active agents
- [x] Show per-agent cost

```typescript
// src/format.ts
export function renderAgentTree(tree: AgentTreeNode): string[] {
  const lines: string[] = [];
  function walk(node: AgentTreeNode, prefix: string, isLast: boolean) {
    const connector = isLast ? '└─' : '├─';
    const status = node.active ? ' ← active' : '';
    lines.push(`${prefix}${connector} ${node.id} ${node.type} (${node.model}) - ${formatCost(node.metrics.cost.total)}${status}`);
    const newPrefix = prefix + (isLast ? '   ' : '│  ');
    node.children.forEach((child, i) => {
      walk(child, newPrefix, i === node.children.length - 1);
    });
  }
  // ... render
  return lines;
}
```

### 5.6 Implement Screen Updates
- [x] Use ANSI escape codes for cursor control
- [x] Partial screen updates (not full clear)
- [x] Smooth scrolling for activity log
- [ ] Handle terminal resize (future enhancement)

### 5.7 Activity Ring Buffer
- [x] Keep last N activity entries
- [x] Format activity log lines
- [x] Show timestamps
- [x] Indicate hierarchy with indentation

### 5.8 Web Dashboard UI (Phase 6 Extension)
- [x] Create `src/dashboard/public/index.html` with Pico CSS, uPlot, Petite-Vue
- [x] Create `src/dashboard/public/style.css` with dark theme
- [x] Create `src/dashboard/public/app.js` with SSE integration
- [x] Update `src/dashboard/server.ts` for static file serving
- [x] Real-time metrics display (tokens in/out, cost)
- [x] Token usage chart with uPlot
- [x] Agent tree visualization
- [x] Recent sessions table

---

## Command Interface

```bash
# Watch current project
karma watch

# Watch specific project
karma watch --project claude-karma

# Compact mode (less detail)
karma watch --compact

# Activity only (no tree)
karma watch --activity-only

# Launch web dashboard
karma dashboard

# Web dashboard on custom port
karma dashboard --port 8080

# Web dashboard without auto-opening browser
karma dashboard --no-open
```

---

## Key Code

```typescript
// src/commands/watch.ts
export async function watchCommand(options: WatchOptions): Promise<void> {
  const watcher = new LogWatcher(findClaudeLogsDir());
  const aggregator = new MetricsAggregator();
  const display = new WatchDisplay();

  watcher.on('entry', (entry, sessionId, agentId) => {
    aggregator.processEntry(entry, sessionId, agentId);
    display.addActivity(formatActivity(entry));
    display.update(aggregator.getSessionMetrics(sessionId));
  });

  process.on('SIGINT', () => {
    watcher.stop();
    display.cleanup();
    process.exit(0);
  });

  watcher.watch(options.project);
  display.start();
}
```

---

## Acceptance Criteria

1. Updates display within 500ms of new activity
2. Agent tree accurately reflects hierarchy
3. Activity log shows last 20 entries
4. Ctrl+C exits cleanly without dangling processes
5. CPU usage < 1% when idle
6. No memory leaks over 30-minute session

---

## Exit Condition

Phase complete when `karma watch` provides real-time visibility into Claude Code activity.
