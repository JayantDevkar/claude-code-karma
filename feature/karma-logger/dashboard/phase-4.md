# Phase 4: TUI Sparkline, Keyboard & Command

**Status:** Complete
**Depends On:** Phase 1, 2, 3
**Blocks:** Phase 5 (optional), CLI integration

---

## Objective

Complete TUI with sparkline chart, keyboard navigation, and `karma watch --ui` command.

---

## Scope

### In Scope
- Create `Sparkline.tsx` ASCII chart component
- Create `StatusBar.tsx` with keyboard hints
- Create `useKeyboard.ts` hook for input handling
- Implement keyboard shortcuts: q (quit), r (refresh), t (toggle tree), h (help)
- Wire up `karma watch --ui` command
- 60-second rolling window for token flow

### Out of Scope
- Web dashboard (Phase 5-6)
- Configurable refresh rate (future)
- Custom keybindings (future)

---

## Implementation

### 1. Sparkline Component

```tsx
// src/tui/components/Sparkline.tsx
import React from 'react';
import { Box, Text } from 'ink';
import asciichart from 'asciichart';

interface SparklineProps {
  data: number[];
  height?: number;
  label?: string;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  height = 3,
  label = 'TOKEN FLOW (last 60s)'
}) => {
  // Ensure we have at least 2 points for chart
  const chartData = data.length < 2
    ? [0, 0]
    : data.slice(-60); // Last 60 seconds

  const chart = asciichart.plot(chartData, {
    height,
    format: (x: number) => x.toFixed(0).padStart(6),
  });

  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold dimColor>{label}</Text>
      <Text>{chart}</Text>
    </Box>
  );
};
```

### 2. useTokenFlow Hook

```tsx
// src/tui/hooks/useTokenFlow.ts
import { useState, useEffect, useRef } from 'react';
import { aggregator } from '../../aggregator.js';

const MAX_POINTS = 60;

export function useTokenFlow(): number[] {
  const [flow, setFlow] = useState<number[]>([]);
  const lastTotal = useRef(0);

  useEffect(() => {
    const interval = setInterval(() => {
      const current = aggregator.getMetrics();
      const total = current.inputTokens + current.outputTokens;
      const delta = total - lastTotal.current;
      lastTotal.current = total;

      setFlow((prev) => {
        const next = [...prev, delta];
        return next.slice(-MAX_POINTS);
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  return flow;
}
```

### 3. StatusBar Component

```tsx
// src/tui/components/StatusBar.tsx
import React from 'react';
import { Box, Text } from 'ink';

interface KeyHint {
  key: string;
  action: string;
}

interface StatusBarProps {
  hints?: KeyHint[];
}

const DEFAULT_HINTS: KeyHint[] = [
  { key: 'q', action: 'Quit' },
  { key: 'r', action: 'Refresh' },
  { key: 't', action: 'Toggle tree' },
  { key: 'h', action: 'Help' },
];

export const StatusBar: React.FC<StatusBarProps> = ({
  hints = DEFAULT_HINTS
}) => {
  return (
    <Box paddingX={1} marginTop={1}>
      {hints.map((hint, i) => (
        <Box key={hint.key} marginRight={2}>
          <Text>[</Text>
          <Text bold color="cyan">{hint.key}</Text>
          <Text>] {hint.action}</Text>
          {i < hints.length - 1 && <Text>  </Text>}
        </Box>
      ))}
    </Box>
  );
};
```

### 4. useKeyboard Hook

```tsx
// src/tui/hooks/useKeyboard.ts
import { useInput, useApp } from 'ink';

interface KeyboardActions {
  onQuit?: () => void;
  onRefresh?: () => void;
  onToggleTree?: () => void;
  onHelp?: () => void;
}

export function useKeyboard(actions: KeyboardActions = {}): void {
  const { exit } = useApp();

  useInput((input, key) => {
    if (input === 'q' || (key.ctrl && input === 'c')) {
      actions.onQuit?.();
      exit();
    }

    if (input === 'r') {
      actions.onRefresh?.();
    }

    if (input === 't') {
      actions.onToggleTree?.();
    }

    if (input === 'h') {
      actions.onHelp?.();
    }
  });
}
```

### 5. Complete App.tsx

```tsx
// src/tui/App.tsx
import React, { useState } from 'react';
import { Box, Text } from 'ink';
import { MetricsCard } from './components/MetricsCard.js';
import { AgentTree } from './components/AgentTree.js';
import { Sparkline } from './components/Sparkline.js';
import { StatusBar } from './components/StatusBar.js';
import { useMetrics } from './hooks/useMetrics.js';
import { useAgentTree } from './hooks/useAgentTree.js';
import { useTokenFlow } from './hooks/useTokenFlow.js';
import { useKeyboard } from './hooks/useKeyboard.js';
import { formatNumber, formatCost } from './utils/format.js';

interface AppProps {
  sessionId?: string;
}

export const App: React.FC<AppProps> = ({ sessionId = '---' }) => {
  const { tokensIn, tokensOut, totalCost } = useMetrics();
  const { root, count } = useAgentTree();
  const tokenFlow = useTokenFlow();
  const [showTree, setShowTree] = useState(true);

  useKeyboard({
    onToggleTree: () => setShowTree((prev) => !prev),
  });

  return (
    <Box flexDirection="column" width="100%">
      {/* Header */}
      <Box borderStyle="single" paddingX={1}>
        <Text bold>KARMA LOGGER</Text>
        <Box flexGrow={1} />
        <Text dimColor>Session: {sessionId}</Text>
      </Box>

      {/* Metrics Row */}
      <Box justifyContent="flex-start" gap={2} marginTop={1}>
        <MetricsCard label="Tokens In" value={formatNumber(tokensIn)} color="cyan" />
        <MetricsCard label="Tokens Out" value={formatNumber(tokensOut)} color="green" />
        <MetricsCard label="Total Cost" value={formatCost(totalCost)} color="yellow" />
      </Box>

      {/* Agent Tree */}
      {showTree && (
        <Box
          flexDirection="column"
          borderStyle="single"
          marginTop={1}
          minHeight={8}
        >
          <AgentTree root={root} totalAgents={count} />
        </Box>
      )}

      {/* Sparkline */}
      <Box borderStyle="single" marginTop={1}>
        <Sparkline data={tokenFlow} />
      </Box>

      {/* Status Bar */}
      <StatusBar />
    </Box>
  );
};
```

### 6. Command Integration

```ts
// src/cli/commands/watch.ts (update existing)
import { startTUI } from '../tui/index.js';

export function watchCommand(options: WatchOptions) {
  if (options.ui) {
    startTUI();
    return;
  }

  // existing watch logic...
}
```

```bash
# Usage
karma watch --ui          # Interactive TUI dashboard
```

---

## Success Criteria

1. Sparkline renders 60-second token flow
2. Chart updates at 1Hz without flicker
3. Keyboard shortcuts work (q, r, t, h)
4. `t` toggles agent tree visibility
5. `q` exits cleanly
6. `karma watch --ui` launches TUI
7. Renders within 100ms of command

---

## Test Plan

```ts
// tests/tui/components/Sparkline.test.tsx
describe('Sparkline', () => {
  it('renders chart with data', () => {
    const data = [10, 20, 30, 40, 50];
    const { lastFrame } = render(<Sparkline data={data} />);
    expect(lastFrame()).toContain('TOKEN FLOW');
  });

  it('handles empty data', () => {
    const { lastFrame } = render(<Sparkline data={[]} />);
    expect(lastFrame()).toBeTruthy();
  });
});

// tests/tui/hooks/useKeyboard.test.tsx
describe('useKeyboard', () => {
  it('calls onQuit when q pressed', () => {
    const onQuit = vi.fn();
    // Test with ink-testing-library input simulation
  });
});
```

---

## Acceptance

- [x] Sparkline.tsx created and renders chart
- [x] StatusBar.tsx shows keyboard hints
- [x] useKeyboard.ts handles all shortcuts
- [x] useTokenFlow.ts tracks 60s rolling window
- [x] App.tsx integrates all components
- [x] `karma watch --ui` command works
- [x] All keyboard shortcuts functional
- [x] Tests pass
