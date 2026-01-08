# Phase 1: TUI Core Setup

**Status:** Complete
**Depends On:** MVP_PLAN.md (CLI Core complete)
**Blocks:** Phase 2-4

---

## Objective

Establish Ink foundation with base App component and layout skeleton.

---

## Scope

### In Scope
- Install Ink v5 and core dependencies
- Create `src/tui/` directory structure
- Build base `App.tsx` with Flexbox layout
- Render empty layout boxes for future components
- Basic render test (component mounts without error)

### Out of Scope
- Actual metrics display (Phase 2)
- Agent tree rendering (Phase 3)
- Charts and keyboard navigation (Phase 4)
- Command integration (Phase 4)

---

## Implementation

### 1. Dependencies

```bash
npm install ink@^5.0.0 ink-spinner@^5.0.0 @inkjs/ui@^2.0.0 asciichart@^1.5.0
npm install -D @types/asciichart
```

### 2. Directory Structure

```
karma-logger/src/tui/
├── App.tsx              # Main Ink component
├── index.ts             # Entry point
├── components/          # (empty, populated in later phases)
└── hooks/               # (empty, populated in later phases)
```

### 3. App.tsx Layout

```tsx
import React from 'react';
import { Box, Text } from 'ink';

export const App: React.FC = () => {
  return (
    <Box flexDirection="column" width="100%">
      {/* Header */}
      <Box borderStyle="single" paddingX={1}>
        <Text bold>KARMA LOGGER</Text>
        <Box flexGrow={1} />
        <Text dimColor>Session: ---</Text>
      </Box>

      {/* Metrics Row - placeholder */}
      <Box height={5} borderStyle="single" marginTop={1}>
        <Text dimColor>[ Metrics Cards ]</Text>
      </Box>

      {/* Agent Tree - placeholder */}
      <Box height={8} borderStyle="single" marginTop={1}>
        <Text dimColor>[ Agent Tree ]</Text>
      </Box>

      {/* Sparkline - placeholder */}
      <Box height={4} borderStyle="single" marginTop={1}>
        <Text dimColor>[ Token Flow ]</Text>
      </Box>

      {/* Status Bar - placeholder */}
      <Box paddingX={1} marginTop={1}>
        <Text dimColor>[q] Quit  [r] Refresh  [h] Help</Text>
      </Box>
    </Box>
  );
};
```

### 4. Entry Point

```ts
// src/tui/index.ts
import { render } from 'ink';
import React from 'react';
import { App } from './App.js';

export function startTUI(): void {
  render(React.createElement(App));
}
```

---

## Success Criteria

1. `npm install` completes without errors
2. `src/tui/App.tsx` compiles without TypeScript errors
3. Calling `startTUI()` renders layout to terminal
4. Layout displays header, 4 placeholder boxes, status bar
5. No flicker on initial render

---

## Test Plan

```ts
// tests/tui/App.test.tsx
import { render } from 'ink-testing-library';
import { App } from '../../src/tui/App.js';

describe('TUI App', () => {
  it('renders without crashing', () => {
    const { lastFrame } = render(<App />);
    expect(lastFrame()).toContain('KARMA LOGGER');
  });

  it('shows placeholder sections', () => {
    const { lastFrame } = render(<App />);
    expect(lastFrame()).toContain('Metrics Cards');
    expect(lastFrame()).toContain('Agent Tree');
    expect(lastFrame()).toContain('Token Flow');
  });
});
```

---

## Acceptance

- [x] Dependencies installed
- [x] Directory structure created
- [x] App.tsx renders layout skeleton
- [x] Tests pass
- [x] No TypeScript errors
