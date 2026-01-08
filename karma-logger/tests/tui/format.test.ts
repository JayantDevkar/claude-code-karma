/**
 * Format utilities unit tests
 * Phase 2: TUI number and cost formatting tests
 */

import { describe, it, expect } from 'vitest';
import { formatNumber, formatCost, formatDuration } from '../../src/tui/utils/format.js';

describe('formatNumber', () => {
  it('formats thousands with K suffix', () => {
    expect(formatNumber(1000)).toBe('1.0K');
    expect(formatNumber(1234)).toBe('1.2K');
    expect(formatNumber(124500)).toBe('124.5K');
  });

  it('formats millions with M suffix', () => {
    expect(formatNumber(1000000)).toBe('1.0M');
    expect(formatNumber(1234567)).toBe('1.2M');
    expect(formatNumber(25_000_000)).toBe('25.0M');
  });

  it('formats billions with B suffix', () => {
    expect(formatNumber(1_000_000_000)).toBe('1.0B');
    expect(formatNumber(2_500_000_000)).toBe('2.5B');
  });

  it('returns raw number for small values', () => {
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(1)).toBe('1');
    expect(formatNumber(999)).toBe('999');
  });

  it('handles edge cases at boundaries', () => {
    expect(formatNumber(999)).toBe('999');
    expect(formatNumber(1000)).toBe('1.0K');
    expect(formatNumber(999999)).toBe('1000.0K');
    expect(formatNumber(1000000)).toBe('1.0M');
  });
});

describe('formatCost', () => {
  it('formats dollar amounts with 2 decimals for >= $1', () => {
    expect(formatCost(1.00)).toBe('$1.00');
    expect(formatCost(2.34)).toBe('$2.34');
    expect(formatCost(100.00)).toBe('$100.00');
    expect(formatCost(99.99)).toBe('$99.99');
  });

  it('formats cents with 3 decimals for >= $0.01', () => {
    expect(formatCost(0.01)).toBe('$0.010');
    expect(formatCost(0.05)).toBe('$0.050');
    expect(formatCost(0.123)).toBe('$0.123');
    expect(formatCost(0.999)).toBe('$0.999');
  });

  it('formats small amounts with 4 decimals for < $0.01', () => {
    expect(formatCost(0.001)).toBe('$0.0010');
    expect(formatCost(0.0001)).toBe('$0.0001');
    expect(formatCost(0.0099)).toBe('$0.0099');
  });

  it('handles zero', () => {
    expect(formatCost(0)).toBe('$0.0000');
  });
});

describe('formatDuration', () => {
  it('formats seconds only', () => {
    expect(formatDuration(0)).toBe('0s');
    expect(formatDuration(1000)).toBe('1s');
    expect(formatDuration(59000)).toBe('59s');
  });

  it('formats minutes and seconds', () => {
    expect(formatDuration(60000)).toBe('1m 0s');
    expect(formatDuration(90000)).toBe('1m 30s');
    expect(formatDuration(3599000)).toBe('59m 59s');
  });

  it('formats hours and minutes', () => {
    expect(formatDuration(3600000)).toBe('1h 0m');
    expect(formatDuration(5400000)).toBe('1h 30m');
    expect(formatDuration(7260000)).toBe('2h 1m');
  });
});
