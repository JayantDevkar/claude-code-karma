import { render } from 'ink-testing-library';
import React from 'react';
import { describe, it, expect } from 'vitest';
import { App } from '../../src/tui/App.js';

describe('TUI App', () => {
  it('renders without crashing', () => {
    const { lastFrame } = render(<App />);
    expect(lastFrame()).toContain('KARMA LOGGER');
  });

  it('shows main sections', () => {
    const { lastFrame } = render(<App />);
    // Phase 2: MetricsCard components
    expect(lastFrame()).toContain('Tokens In');
    expect(lastFrame()).toContain('Tokens Out');
    expect(lastFrame()).toContain('Total Cost');
    // Phase 3: Agent Tree section
    expect(lastFrame()).toContain('AGENT TREE');
    // Phase 4: Token Flow section
    expect(lastFrame()).toContain('TOKEN FLOW');
  });

  it('displays status bar with keybindings', () => {
    const { lastFrame } = render(<App />);
    expect(lastFrame()).toContain('[q] Quit');
    expect(lastFrame()).toContain('[r] Refresh');
    expect(lastFrame()).toContain('[h] Help');
  });
});
