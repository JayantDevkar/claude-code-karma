# Phase 2: TUI MetricsCard Component

**Status:** Complete
**Depends On:** Phase 1 (TUI Core Setup)
**Blocks:** Phase 4
**Completed:** 2025-01-08

---

## Objective

Build MetricsCard component displaying live token counts and cost.

---

## Scope

### In Scope
- Create `MetricsCard.tsx` component
- Display: Tokens In, Tokens Out, Total Cost
- Create `useMetrics.ts` hook for data subscription
- Connect to existing aggregator service
- Format numbers (e.g., 124,500 → "124.5K")

### Out of Scope
- Agent tree (Phase 3)
- Sparkline charts (Phase 4)
- Rate display (+2.3k/s) — future enhancement

---

## Implementation

### 1. MetricsCard Component

```tsx
// src/tui/components/MetricsCard.tsx
import React from 'react';
import { Box, Text } from 'ink';

interface MetricsCardProps {
  label: string;
  value: string;
  color?: string;
}

export const MetricsCard: React.FC<MetricsCardProps> = ({
  label,
  value,
  color = 'white'
}) => {
  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      paddingX={2}
      paddingY={1}
      minWidth={15}
    >
      <Text dimColor>{label}</Text>
      <Text bold color={color}>{value}</Text>
    </Box>
  );
};
```

### 2. useMetrics Hook

```tsx
// src/tui/hooks/useMetrics.ts
import { useState, useEffect } from 'react';
import { aggregator } from '../../aggregator.js';

interface Metrics {
  tokensIn: number;
  tokensOut: number;
  totalCost: number;
}

export function useMetrics(): Metrics {
  const [metrics, setMetrics] = useState<Metrics>({
    tokensIn: 0,
    tokensOut: 0,
    totalCost: 0,
  });

  useEffect(() => {
    const unsubscribe = aggregator.subscribe((data) => {
      setMetrics({
        tokensIn: data.inputTokens,
        tokensOut: data.outputTokens,
        totalCost: data.cost,
      });
    });
    return () => unsubscribe();
  }, []);

  return metrics;
}
```

### 3. Format Utilities

```tsx
// src/tui/utils/format.ts
export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

export function formatCost(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}
```

### 4. Update App.tsx

```tsx
// In App.tsx - replace metrics placeholder
import { MetricsCard } from './components/MetricsCard.js';
import { useMetrics } from './hooks/useMetrics.js';
import { formatNumber, formatCost } from './utils/format.js';

// Inside component:
const { tokensIn, tokensOut, totalCost } = useMetrics();

// Replace metrics box:
<Box justifyContent="flex-start" gap={2} marginTop={1}>
  <MetricsCard label="Tokens In" value={formatNumber(tokensIn)} color="cyan" />
  <MetricsCard label="Tokens Out" value={formatNumber(tokensOut)} color="green" />
  <MetricsCard label="Total Cost" value={formatCost(totalCost)} color="yellow" />
</Box>
```

---

## Success Criteria

1. MetricsCard renders with label and value
2. Three cards display side-by-side
3. Numbers format correctly (1234 → "1.2K")
4. Cost shows dollar format ($2.34)
5. Metrics update when aggregator emits

---

## Test Plan

```ts
// tests/tui/components/MetricsCard.test.tsx
describe('MetricsCard', () => {
  it('renders label and value', () => {
    const { lastFrame } = render(
      <MetricsCard label="Tokens In" value="124.5K" />
    );
    expect(lastFrame()).toContain('Tokens In');
    expect(lastFrame()).toContain('124.5K');
  });
});

// tests/tui/utils/format.test.ts
describe('formatNumber', () => {
  it('formats thousands', () => {
    expect(formatNumber(1234)).toBe('1.2K');
    expect(formatNumber(124500)).toBe('124.5K');
  });

  it('formats millions', () => {
    expect(formatNumber(1234567)).toBe('1.2M');
  });
});
```

---

## Acceptance

- [x] MetricsCard.tsx created
- [x] useMetrics.ts hook created
- [x] Format utilities work correctly
- [x] App.tsx updated to use components
- [x] Live metrics display in TUI
- [x] Tests pass

## Implementation Notes

### Context-Based Architecture
Added `AggregatorContext` to provide the MetricsAggregator to all TUI components:
- `src/tui/context/AggregatorContext.tsx` - React Context provider
- `src/tui/index.ts` - Updated to accept `aggregator` option and wrap in provider

### useMetrics Hook
Updated to use context + polling (1Hz refresh):
- Uses `useAggregator()` hook to get aggregator from context
- Polls `aggregator.getTotals()` every 1000ms
- Returns `MetricsState` with tokens, cost, sessions, agents

### Tests Added
- `tests/tui/format.test.ts` - 12 tests for formatNumber, formatCost, formatDuration
- `tests/tui/MetricsCard.test.tsx` - 6 tests for component rendering
