import { render } from 'ink-testing-library';
import React from 'react';
import { describe, it, expect } from 'vitest';
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

  it('displays status bar with keybindings', () => {
    const { lastFrame } = render(<App />);
    expect(lastFrame()).toContain('[q] Quit');
    expect(lastFrame()).toContain('[r] Refresh');
    expect(lastFrame()).toContain('[h] Help');
  });
});
