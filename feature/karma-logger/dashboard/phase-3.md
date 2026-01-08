# Phase 3: TUI AgentTree Component

**Status:** Complete
**Depends On:** Phase 1 (TUI Core Setup)
**Blocks:** Phase 4

---

## Objective

Build AgentTree component showing agent hierarchy with status indicators.

---

## Scope

### In Scope
- Create `AgentTree.tsx` component
- Display parent-child agent relationships
- Show agent name, model, cost, status
- Status indicators: ✓ (complete), ⟳ (running), ✗ (error)
- Progress bar for active agents
- Total agent count

### Out of Scope
- Collapsible tree nodes (future)
- Sorting/filtering (future)
- Click to expand details (future)

---

## Implementation

### 1. Agent Node Types

```ts
// src/tui/types.ts
export interface AgentNode {
  id: string;
  name: string;
  model: string;
  cost: number;
  status: 'running' | 'complete' | 'error';
  progress?: number; // 0-100, only for running
  children: AgentNode[];
}
```

### 2. useAgentTree Hook

```tsx
// src/tui/hooks/useAgentTree.ts
import { useState, useEffect } from 'react';
import { aggregator } from '../../aggregator.js';
import type { AgentNode } from '../types.js';

export function useAgentTree(): { root: AgentNode | null; count: number } {
  const [tree, setTree] = useState<{ root: AgentNode | null; count: number }>({
    root: null,
    count: 0,
  });

  useEffect(() => {
    const unsubscribe = aggregator.subscribeTree((data) => {
      setTree({
        root: data.root,
        count: data.totalAgents,
      });
    });
    return () => unsubscribe();
  }, []);

  return tree;
}
```

### 3. AgentTree Component

```tsx
// src/tui/components/AgentTree.tsx
import React from 'react';
import { Box, Text } from 'ink';
import type { AgentNode } from '../types.js';
import { formatCost } from '../utils/format.js';

const STATUS_ICONS = {
  complete: '✓',
  running: '⟳',
  error: '✗',
};

const STATUS_COLORS = {
  complete: 'green',
  running: 'yellow',
  error: 'red',
};

interface AgentTreeProps {
  root: AgentNode | null;
  totalAgents: number;
}

export const AgentTree: React.FC<AgentTreeProps> = ({ root, totalAgents }) => {
  if (!root) {
    return (
      <Box paddingX={1}>
        <Text dimColor>No active agents</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold dimColor>AGENT TREE</Text>
      <AgentNodeRow node={root} prefix="" isLast={true} />
      <Text dimColor>└── total agents: {totalAgents}</Text>
    </Box>
  );
};

interface AgentNodeRowProps {
  node: AgentNode;
  prefix: string;
  isLast: boolean;
}

const AgentNodeRow: React.FC<AgentNodeRowProps> = ({ node, prefix, isLast }) => {
  const connector = isLast ? '└── ' : '├── ';
  const childPrefix = prefix + (isLast ? '    ' : '│   ');

  const icon = STATUS_ICONS[node.status];
  const color = STATUS_COLORS[node.status];

  return (
    <Box flexDirection="column">
      <Box>
        <Text>{prefix}{connector}</Text>
        <Text bold>{node.name}</Text>
        <Text dimColor> ({node.model})</Text>
        <Text>  {formatCost(node.cost)}</Text>
        {node.status === 'running' && node.progress !== undefined ? (
          <Text>  <ProgressBar progress={node.progress} /></Text>
        ) : (
          <Text color={color}>  {icon}</Text>
        )}
      </Box>
      {node.children.map((child, i) => (
        <AgentNodeRow
          key={child.id}
          node={child}
          prefix={childPrefix}
          isLast={i === node.children.length - 1}
        />
      ))}
    </Box>
  );
};

const ProgressBar: React.FC<{ progress: number }> = ({ progress }) => {
  const filled = Math.round(progress / 10);
  const empty = 10 - filled;
  return (
    <Text>
      [<Text color="green">{'█'.repeat(filled)}</Text>
      <Text dimColor>{'░'.repeat(empty)}</Text>] {progress}%
    </Text>
  );
};
```

### 4. Update App.tsx

```tsx
// In App.tsx - replace agent tree placeholder
import { AgentTree } from './components/AgentTree.js';
import { useAgentTree } from './hooks/useAgentTree.js';

// Inside component:
const { root, count } = useAgentTree();

// Replace agent tree box:
<Box
  flexDirection="column"
  borderStyle="single"
  marginTop={1}
  minHeight={8}
>
  <AgentTree root={root} totalAgents={count} />
</Box>
```

---

## Success Criteria

1. Tree renders with correct indentation
2. Parent-child relationships displayed accurately
3. Status icons show correct state
4. Progress bar renders for running agents
5. Empty state handled gracefully
6. Total agent count accurate

---

## Test Plan

```ts
// tests/tui/components/AgentTree.test.tsx
describe('AgentTree', () => {
  const mockTree: AgentNode = {
    id: 'main',
    name: 'main',
    model: 'sonnet',
    cost: 120,
    status: 'running',
    progress: 80,
    children: [
      {
        id: 'explore-a3b',
        name: 'explore-a3b',
        model: 'haiku',
        cost: 15,
        status: 'complete',
        children: [],
      },
    ],
  };

  it('renders tree structure', () => {
    const { lastFrame } = render(
      <AgentTree root={mockTree} totalAgents={2} />
    );
    expect(lastFrame()).toContain('main');
    expect(lastFrame()).toContain('explore-a3b');
    expect(lastFrame()).toContain('├──');
  });

  it('shows status icons', () => {
    const { lastFrame } = render(
      <AgentTree root={mockTree} totalAgents={2} />
    );
    expect(lastFrame()).toContain('✓');
  });

  it('handles empty state', () => {
    const { lastFrame } = render(
      <AgentTree root={null} totalAgents={0} />
    );
    expect(lastFrame()).toContain('No active agents');
  });
});
```

---

## Acceptance

- [x] AgentTree.tsx created
- [x] useAgentTree.ts hook created
- [x] Tree indentation correct
- [x] Status indicators working
- [x] Progress bar displays
- [x] Empty state handled
- [x] Tests pass
