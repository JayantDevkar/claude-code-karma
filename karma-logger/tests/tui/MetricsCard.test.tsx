/**
 * MetricsCard component unit tests
 * Phase 2: TUI metrics display component tests
 */

import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from 'ink-testing-library';
import { MetricsCard } from '../../src/tui/components/MetricsCard.js';

describe('MetricsCard', () => {
  it('renders label and value', () => {
    const { lastFrame } = render(
      <MetricsCard label="Tokens In" value="124.5K" />
    );

    expect(lastFrame()).toContain('Tokens In');
    expect(lastFrame()).toContain('124.5K');
  });

  it('renders with default white color', () => {
    const { lastFrame } = render(
      <MetricsCard label="Test" value="100" />
    );

    expect(lastFrame()).toContain('Test');
    expect(lastFrame()).toContain('100');
  });

  it('renders with custom color', () => {
    const { lastFrame } = render(
      <MetricsCard label="Cost" value="$2.34" color="yellow" />
    );

    expect(lastFrame()).toContain('Cost');
    expect(lastFrame()).toContain('$2.34');
  });

  it('renders multiple cards side by side', () => {
    const { lastFrame } = render(
      <>
        <MetricsCard label="Tokens In" value="100K" color="cyan" />
        <MetricsCard label="Tokens Out" value="50K" color="green" />
        <MetricsCard label="Total Cost" value="$1.50" color="yellow" />
      </>
    );

    const frame = lastFrame();
    expect(frame).toContain('Tokens In');
    expect(frame).toContain('100K');
    expect(frame).toContain('Tokens Out');
    expect(frame).toContain('50K');
    expect(frame).toContain('Total Cost');
    expect(frame).toContain('$1.50');
  });

  it('handles empty values', () => {
    const { lastFrame } = render(
      <MetricsCard label="Empty" value="" />
    );

    expect(lastFrame()).toContain('Empty');
  });

  it('handles long values', () => {
    const { lastFrame } = render(
      <MetricsCard label="Large" value="1,234,567,890" />
    );

    expect(lastFrame()).toContain('Large');
    expect(lastFrame()).toContain('1,234,567,890');
  });
});
