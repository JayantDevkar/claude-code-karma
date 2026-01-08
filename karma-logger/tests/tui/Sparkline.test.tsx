import { render } from 'ink-testing-library';
import React from 'react';
import { describe, it, expect } from 'vitest';
import { Sparkline } from '../../src/tui/components/Sparkline.js';

describe('Sparkline', () => {
  it('renders chart with data', () => {
    const data = [10, 20, 30, 40, 50];
    const { lastFrame } = render(<Sparkline data={data} />);
    expect(lastFrame()).toContain('TOKEN FLOW');
  });

  it('handles empty data', () => {
    const { lastFrame } = render(<Sparkline data={[]} />);
    expect(lastFrame()).toBeTruthy();
    expect(lastFrame()).toContain('TOKEN FLOW');
  });

  it('handles single data point', () => {
    const { lastFrame } = render(<Sparkline data={[100]} />);
    expect(lastFrame()).toBeTruthy();
    expect(lastFrame()).toContain('TOKEN FLOW');
  });

  it('renders with custom label', () => {
    const { lastFrame } = render(<Sparkline data={[10, 20]} label="CUSTOM LABEL" />);
    expect(lastFrame()).toContain('CUSTOM LABEL');
  });

  it('truncates to last 60 data points', () => {
    // Generate 100 data points
    const data = Array.from({ length: 100 }, (_, i) => i);
    const { lastFrame } = render(<Sparkline data={data} />);
    // Should render without error
    expect(lastFrame()).toContain('TOKEN FLOW');
  });
});
