import { render } from 'ink-testing-library';
import React from 'react';
import { describe, it, expect } from 'vitest';
import { StatusBar } from '../../src/tui/components/StatusBar.js';

describe('StatusBar', () => {
  it('renders default keyboard hints', () => {
    const { lastFrame } = render(<StatusBar />);
    expect(lastFrame()).toContain('[q] Quit');
    expect(lastFrame()).toContain('[r] Refresh');
    expect(lastFrame()).toContain('[t] Toggle tree');
    expect(lastFrame()).toContain('[h] Help');
  });

  it('renders custom keyboard hints', () => {
    const customHints = [
      { key: 'a', action: 'Action A' },
      { key: 'b', action: 'Action B' },
    ];
    const { lastFrame } = render(<StatusBar hints={customHints} />);
    expect(lastFrame()).toContain('[a] Action A');
    expect(lastFrame()).toContain('[b] Action B');
    // Should not contain default hints
    expect(lastFrame()).not.toContain('[q] Quit');
  });

  it('renders empty with no hints', () => {
    const { lastFrame } = render(<StatusBar hints={[]} />);
    // Should not crash with empty hints
    // Empty render returns empty string which is valid
    expect(lastFrame()).not.toContain('[q]');
  });
});
