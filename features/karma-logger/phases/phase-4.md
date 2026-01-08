# Phase 4: `karma status` Command

**Status:** Complete
**Estimated Effort:** Small
**Dependencies:** Phase 3
**Deliverable:** Working `karma status` command with formatted output

---

## Objective

Implement the first user-facing command that displays current session metrics in a clean, informative format.

---

## Tasks

### 4.1 Create Status Command Handler
- [x] Create `src/commands/status.ts`
- [x] Wire up to Commander in `cli.ts`
- [x] Accept optional `--project` flag
- [x] Accept optional `--all` flag for all sessions

### 4.2 Implement Output Formatting
- [x] Install chalk for colors (if not already)
- [x] Create `src/format.ts` for display utilities (reused from tui/utils)
- [x] Format token counts (K/M suffixes)
- [x] Format costs (currency, 2 decimals)

```typescript
// src/format.ts
export function formatTokens(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return count.toString();
}

export function formatCost(cost: number): string {
  return `$${cost.toFixed(2)}`;
}
```

### 4.3 Design Status Output
```
╭──────────────────────────────────────────────────────╮
│  KARMA STATUS                                        │
│  Session: abc1234                                    │
│  Project: claude-karma                               │
│  Started: 2 hours ago                                │
├──────────────────────────────────────────────────────┤
│  TOKENS                                              │
│    Input:   125.4K                                   │
│    Output:   42.1K                                   │
│    Cached:   89.2K                                   │
├──────────────────────────────────────────────────────┤
│  COST                                                │
│    Total:   $1.24                                    │
│    Input:   $0.38                                    │
│    Output:  $0.63                                    │
│    Cache:   $0.23 (saved)                            │
├──────────────────────────────────────────────────────┤
│  AGENTS                                              │
│    Active:  3                                        │
│    Total:   12                                       │
│    Tools:   47 calls                                 │
╰──────────────────────────────────────────────────────╯
```

### 4.4 Handle Edge Cases
- [x] No active session: Show helpful message
- [x] Multiple projects: List selection via --all flag
- [x] Stale session: Show warning indicator

### 4.5 Add Timing Display
- [x] Calculate session duration
- [x] Show "started X ago" relative time
- [x] Show last activity time (stale/active indicator)

---

## Command Interface

```bash
# Current project's active session
karma status

# Specific project
karma status --project claude-karma

# All active sessions
karma status --all

# JSON output for scripting
karma status --json
```

---

## Key Code

```typescript
// src/commands/status.ts
export async function statusCommand(options: StatusOptions): Promise<void> {
  const discovery = new SessionDiscovery();
  const session = await discovery.findActiveSession(options.project);

  if (!session) {
    console.log(chalk.yellow('No active session found.'));
    return;
  }

  const parser = new Parser();
  const entries = await parser.parseFile(session.filePath);

  const aggregator = new MetricsAggregator();
  entries.forEach((e) => aggregator.processEntry(e, session.id));

  const metrics = aggregator.getSessionMetrics(session.id);
  displayStatus(metrics);
}
```

---

## Acceptance Criteria

1. `karma status` shows current session within 1 second
2. Output is readable and well-formatted
3. Token and cost values match expectations
4. `--json` flag outputs valid JSON
5. Graceful handling when no session exists

---

## Exit Condition

Phase complete when `karma status` displays accurate metrics for the current Claude Code session.
