/**
 * Cost calculation unit tests
 * Phase 3: Cost and pricing tests
 */

import { describe, it, expect } from 'vitest';
import {
  getPricingForModel,
  calculateCost,
  formatCost,
  formatTokens,
  addCosts,
  emptyCostBreakdown,
  getKnownModels,
  isKnownModel,
  MODEL_PRICING,
} from '../src/cost.js';
import type { TokenUsage } from '../src/types.js';

describe('getPricingForModel', () => {
  it('returns exact pricing for known models', () => {
    const opusPricing = getPricingForModel('claude-opus-4-5-20251101');

    expect(opusPricing.input).toBe(15.0);
    expect(opusPricing.output).toBe(75.0);
    expect(opusPricing.cacheRead).toBe(1.5);
  });

  it('returns sonnet pricing for sonnet model variants', () => {
    const sonnetPricing = getPricingForModel('claude-sonnet-4-20250514');

    expect(sonnetPricing.input).toBe(3.0);
    expect(sonnetPricing.output).toBe(15.0);
  });

  it('returns haiku pricing for haiku model variants', () => {
    const haikuPricing = getPricingForModel('claude-haiku-4-5-20251001');

    expect(haikuPricing.input).toBe(0.8);
    expect(haikuPricing.output).toBe(4.0);
  });

  it('falls back to default for unknown models', () => {
    const unknownPricing = getPricingForModel('unknown-model-v1');

    // Default is sonnet pricing
    expect(unknownPricing.input).toBe(3.0);
    expect(unknownPricing.output).toBe(15.0);
  });

  it('matches model family by prefix for variants', () => {
    const opusVariant = getPricingForModel('some-opus-variant');
    expect(opusVariant.input).toBe(15.0);

    const haikuVariant = getPricingForModel('custom-haiku-model');
    expect(haikuVariant.input).toBe(0.8);
  });
});

describe('calculateCost', () => {
  it('calculates cost correctly for standard usage', () => {
    const usage: TokenUsage = {
      inputTokens: 1_000_000,
      outputTokens: 100_000,
      cacheReadTokens: 500_000,
      cacheCreationTokens: 0,
    };

    const cost = calculateCost('claude-sonnet-4-20250514', usage);

    // Input: 1M * $3/1M = $3
    expect(cost.inputCost).toBeCloseTo(3.0, 2);

    // Output: 100K * $15/1M = $1.5
    expect(cost.outputCost).toBeCloseTo(1.5, 2);

    // Cache read: 500K * $0.30/1M = $0.15
    expect(cost.cacheReadCost).toBeCloseTo(0.15, 2);

    // Total
    expect(cost.total).toBeCloseTo(4.65, 2);
  });

  it('calculates cost correctly for opus model', () => {
    const usage: TokenUsage = {
      inputTokens: 100_000,
      outputTokens: 50_000,
      cacheReadTokens: 200_000,
      cacheCreationTokens: 10_000,
    };

    const cost = calculateCost('claude-opus-4-5-20251101', usage);

    // Input: 100K * $15/1M = $1.5
    expect(cost.inputCost).toBeCloseTo(1.5, 2);

    // Output: 50K * $75/1M = $3.75
    expect(cost.outputCost).toBeCloseTo(3.75, 2);

    // Cache read: 200K * $1.50/1M = $0.30
    expect(cost.cacheReadCost).toBeCloseTo(0.3, 2);

    // Cache creation: 10K * $18.75/1M = $0.1875
    expect(cost.cacheCreationCost).toBeCloseTo(0.1875, 3);
  });

  it('handles zero usage', () => {
    const usage: TokenUsage = {
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheCreationTokens: 0,
    };

    const cost = calculateCost('claude-sonnet-4-20250514', usage);

    expect(cost.total).toBe(0);
  });

  it('includes model name in cost breakdown', () => {
    const usage: TokenUsage = {
      inputTokens: 1000,
      outputTokens: 100,
      cacheReadTokens: 0,
      cacheCreationTokens: 0,
    };

    const cost = calculateCost('claude-sonnet-4-20250514', usage);

    expect(cost.model).toBe('claude-sonnet-4-20250514');
  });
});

describe('formatCost', () => {
  it('formats cost as USD currency', () => {
    expect(formatCost(1.5)).toBe('$1.50');
    expect(formatCost(100.00)).toBe('$100.00');
  });

  it('shows <$0.01 for very small amounts', () => {
    expect(formatCost(0.001)).toBe('<$0.01');
    expect(formatCost(0.009)).toBe('<$0.01');
  });

  it('shows precision up to 4 decimal places when needed', () => {
    const formatted = formatCost(1.2345);
    expect(formatted).toContain('1.23');
  });
});

describe('formatTokens', () => {
  it('formats millions correctly', () => {
    expect(formatTokens(1_000_000)).toBe('1.00M');
    expect(formatTokens(2_500_000)).toBe('2.50M');
  });

  it('formats thousands correctly', () => {
    expect(formatTokens(1_000)).toBe('1.0K');
    expect(formatTokens(50_000)).toBe('50.0K');
  });

  it('shows raw number for small counts', () => {
    expect(formatTokens(999)).toBe('999');
    expect(formatTokens(0)).toBe('0');
  });
});

describe('addCosts', () => {
  it('adds two cost breakdowns correctly', () => {
    const cost1 = calculateCost('claude-sonnet-4-20250514', {
      inputTokens: 100_000,
      outputTokens: 10_000,
      cacheReadTokens: 0,
      cacheCreationTokens: 0,
    });

    const cost2 = calculateCost('claude-sonnet-4-20250514', {
      inputTokens: 50_000,
      outputTokens: 5_000,
      cacheReadTokens: 0,
      cacheCreationTokens: 0,
    });

    const combined = addCosts(cost1, cost2);

    expect(combined.inputCost).toBeCloseTo(cost1.inputCost + cost2.inputCost, 4);
    expect(combined.outputCost).toBeCloseTo(cost1.outputCost + cost2.outputCost, 4);
    expect(combined.total).toBeCloseTo(cost1.total + cost2.total, 4);
    expect(combined.model).toBe('mixed');
  });
});

describe('emptyCostBreakdown', () => {
  it('returns zero cost breakdown', () => {
    const empty = emptyCostBreakdown();

    expect(empty.inputCost).toBe(0);
    expect(empty.outputCost).toBe(0);
    expect(empty.cacheReadCost).toBe(0);
    expect(empty.cacheCreationCost).toBe(0);
    expect(empty.total).toBe(0);
    expect(empty.model).toBe('none');
  });
});

describe('getKnownModels', () => {
  it('returns list of known models', () => {
    const models = getKnownModels();

    expect(models).toContain('claude-opus-4-5-20251101');
    expect(models).toContain('claude-sonnet-4-20250514');
    expect(models).toContain('claude-haiku-4-5-20251001');
    expect(models.length).toBeGreaterThan(0);
  });
});

describe('isKnownModel', () => {
  it('returns true for known models', () => {
    expect(isKnownModel('claude-opus-4-5-20251101')).toBe(true);
    expect(isKnownModel('claude-sonnet-4-20250514')).toBe(true);
  });

  it('returns false for unknown models', () => {
    expect(isKnownModel('unknown-model')).toBe(false);
    expect(isKnownModel('gpt-4')).toBe(false);
  });
});

describe('MODEL_PRICING', () => {
  it('has correct pricing tiers', () => {
    // Opus is most expensive
    expect(MODEL_PRICING['claude-opus-4-5-20251101'].input)
      .toBeGreaterThan(MODEL_PRICING['claude-sonnet-4-20250514'].input);

    // Sonnet is more expensive than Haiku
    expect(MODEL_PRICING['claude-sonnet-4-20250514'].input)
      .toBeGreaterThan(MODEL_PRICING['claude-haiku-4-5-20251001'].input);

    // Cache read is cheaper than regular input
    for (const pricing of Object.values(MODEL_PRICING)) {
      expect(pricing.cacheRead).toBeLessThan(pricing.input);
    }
  });
});
