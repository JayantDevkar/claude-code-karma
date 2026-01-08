# Phase 3: Metrics Aggregation & Cost Calculation

**Status:** Complete
**Estimated Effort:** Medium
**Dependencies:** Phase 1, Phase 2
**Deliverable:** In-memory metrics store with accurate cost calculation

---

## Objective

Build the metrics aggregation layer that accumulates token usage across entries and calculates costs based on model-specific pricing.

---

## Tasks

### 3.1 Define Pricing Constants
```typescript
// src/cost.ts
export const PRICING = {
  'claude-haiku-4-5-20251001': {
    input: 0.80,      // per 1M tokens
    output: 4.00,
    cacheRead: 0.08,  // 10% of input
  },
  'claude-sonnet-4-20250514': {
    input: 3.00,
    output: 15.00,
    cacheRead: 0.30,
  },
  'claude-opus-4-5-20251101': {
    input: 15.00,
    output: 75.00,
    cacheRead: 1.50,
  },
} as const;
```

### 3.2 Implement Cost Calculator
- [ ] Create `src/cost.ts`
- [ ] Model lookup by ID prefix
- [ ] Token to cost conversion
- [ ] Handle unknown models gracefully

```typescript
export function calculateCost(
  model: string,
  usage: TokenUsage
): CostBreakdown {
  const pricing = getPricingForModel(model);
  return {
    inputCost: (usage.input_tokens / 1_000_000) * pricing.input,
    outputCost: (usage.output_tokens / 1_000_000) * pricing.output,
    cacheCost: ((usage.cache_read_input_tokens ?? 0) / 1_000_000) * pricing.cacheRead,
    total: // sum of above
  };
}
```

### 3.3 Create Metrics Aggregator
- [ ] Create `src/aggregator.ts`
- [ ] In-memory session state
- [ ] Rolling totals per session
- [ ] Per-agent breakdowns

```typescript
// src/aggregator.ts
export class MetricsAggregator {
  private sessions: Map<string, SessionMetrics>;
  private agents: Map<string, AgentMetrics>;

  processEntry(entry: LogEntry, sessionId: string, agentId?: string): void;
  getSessionMetrics(sessionId: string): SessionMetrics;
  getAgentMetrics(agentId: string): AgentMetrics;
  getAgentTree(sessionId: string): AgentTreeNode;
}
```

### 3.4 Build Agent Hierarchy
- [ ] Track parentUuid relationships
- [ ] Build tree structure
- [ ] Calculate subtree totals

```typescript
interface AgentTreeNode {
  id: string;
  type: string;
  model: string;
  metrics: AgentMetrics;
  children: AgentTreeNode[];
}
```

### 3.5 Implement Tool Tracking
- [ ] Extract tool names from entries
- [ ] Count tool invocations per agent
- [ ] Track unique tools per session

### 3.6 Wire Up Watcher → Aggregator
- [ ] Subscribe to watcher events
- [ ] Route entries to aggregator
- [ ] Update metrics in real-time

---

## Data Structures

```typescript
interface SessionMetrics {
  sessionId: string;
  projectPath: string;
  startedAt: Date;
  tokensIn: number;
  tokensOut: number;
  tokensCached: number;
  cost: CostBreakdown;
  agentCount: number;
  toolCalls: number;
}

interface AgentMetrics {
  agentId: string;
  parentId?: string;
  agentType: string;
  model: string;
  startedAt: Date;
  tokensIn: number;
  tokensOut: number;
  tokensCached: number;
  cost: CostBreakdown;
  toolsUsed: string[];
}
```

---

## Acceptance Criteria

1. Cost calculation matches manual calculation within 0.1%
2. Token totals match raw JSONL counts
3. Agent hierarchy correctly represents parent-child relationships
4. Aggregator handles 100+ agents without performance degradation

---

## Exit Condition

Phase complete when `getSessionMetrics()` returns accurate totals for a live session.
