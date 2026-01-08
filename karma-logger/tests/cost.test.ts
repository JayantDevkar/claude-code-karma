/**
 * Cost calculation unit tests
 * Phase 3: Cost and pricing tests
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
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
  setPricingProjectPath,
  clearPricingCache,
  getPricingOverrides,
  hasPricingOverride,
  getOverriddenModels,
  getPricingConfigPaths,
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

// ============================================
// Pricing Override Configuration Tests
// ============================================

describe('Pricing Override Configuration', () => {
  let testDir: string;
  let globalConfigDir: string;
  let originalHomedir: typeof os.homedir;

  beforeEach(() => {
    // Create temp directories for testing
    testDir = fs.mkdtempSync(path.join(os.tmpdir(), 'karma-pricing-test-'));
    globalConfigDir = path.join(testDir, '.karma');
    fs.mkdirSync(globalConfigDir, { recursive: true });

    // Clear any cached pricing
    clearPricingCache();
    setPricingProjectPath(null);
  });

  afterEach(() => {
    // Clean up temp directories
    fs.rmSync(testDir, { recursive: true, force: true });
    clearPricingCache();
    setPricingProjectPath(null);
  });

  describe('clearPricingCache', () => {
    it('clears the pricing cache', () => {
      // Get overrides to populate cache
      getPricingOverrides();

      // Clear and verify no errors
      clearPricingCache();

      // Should be able to get overrides again
      const overrides = getPricingOverrides();
      expect(overrides).toBeDefined();
    });
  });

  describe('setPricingProjectPath', () => {
    it('sets project path for config resolution', () => {
      // Create a project-level config
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      const customPricing = {
        models: {
          'custom-enterprise-model': {
            inputPer1k: 0.005,
            outputPer1k: 0.025,
          },
        },
      };
      fs.writeFileSync(projectPricingPath, JSON.stringify(customPricing));

      // Set project path
      setPricingProjectPath(testDir);

      // Verify custom model is now available
      const overrides = getPricingOverrides();
      expect(overrides['custom-enterprise-model']).toBeDefined();
      expect(overrides['custom-enterprise-model'].input).toBe(5.0); // 0.005 * 1000
      expect(overrides['custom-enterprise-model'].output).toBe(25.0); // 0.025 * 1000
    });

    it('clears cache when project path changes', () => {
      // Create config in first project
      const project1Dir = path.join(testDir, 'project1');
      fs.mkdirSync(project1Dir);
      fs.writeFileSync(
        path.join(project1Dir, '.karma-pricing.json'),
        JSON.stringify({
          models: { 'model-a': { inputPer1k: 0.001, outputPer1k: 0.002 } },
        })
      );

      // Create config in second project
      const project2Dir = path.join(testDir, 'project2');
      fs.mkdirSync(project2Dir);
      fs.writeFileSync(
        path.join(project2Dir, '.karma-pricing.json'),
        JSON.stringify({
          models: { 'model-b': { inputPer1k: 0.003, outputPer1k: 0.004 } },
        })
      );

      // Set to project 1
      setPricingProjectPath(project1Dir);
      expect(hasPricingOverride('model-a')).toBe(true);
      expect(hasPricingOverride('model-b')).toBe(false);

      // Switch to project 2
      setPricingProjectPath(project2Dir);
      expect(hasPricingOverride('model-a')).toBe(false);
      expect(hasPricingOverride('model-b')).toBe(true);
    });
  });

  describe('getPricingOverrides', () => {
    it('returns empty object when no config files exist', () => {
      const overrides = getPricingOverrides();
      expect(overrides).toEqual({});
    });

    it('loads pricing from project-level config', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      const customPricing = {
        models: {
          'claude-3-opus': {
            inputPer1k: 0.015,
            outputPer1k: 0.075,
          },
        },
      };
      fs.writeFileSync(projectPricingPath, JSON.stringify(customPricing));

      setPricingProjectPath(testDir);
      const overrides = getPricingOverrides();

      expect(overrides['claude-3-opus']).toBeDefined();
      expect(overrides['claude-3-opus'].input).toBe(15.0);
      expect(overrides['claude-3-opus'].output).toBe(75.0);
    });

    it('calculates cache pricing defaults when not specified', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      const customPricing = {
        models: {
          'enterprise-model': {
            inputPer1k: 0.010, // $10 per 1M
            outputPer1k: 0.050, // $50 per 1M
          },
        },
      };
      fs.writeFileSync(projectPricingPath, JSON.stringify(customPricing));

      setPricingProjectPath(testDir);
      const overrides = getPricingOverrides();

      // Cache read defaults to 10% of input
      expect(overrides['enterprise-model'].cacheRead).toBe(1.0);
      // Cache creation defaults to 125% of input
      expect(overrides['enterprise-model'].cacheCreation).toBe(12.5);
    });

    it('uses explicit cache pricing when specified', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      const customPricing = {
        models: {
          'custom-model': {
            inputPer1k: 0.010,
            outputPer1k: 0.050,
            cacheReadPer1k: 0.002,
            cacheCreationPer1k: 0.015,
          },
        },
      };
      fs.writeFileSync(projectPricingPath, JSON.stringify(customPricing));

      setPricingProjectPath(testDir);
      const overrides = getPricingOverrides();

      expect(overrides['custom-model'].cacheRead).toBe(2.0);
      expect(overrides['custom-model'].cacheCreation).toBe(15.0);
    });

    it('ignores invalid config files', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(projectPricingPath, 'not valid json');

      setPricingProjectPath(testDir);
      const overrides = getPricingOverrides();

      expect(overrides).toEqual({});
    });

    it('ignores config with invalid structure', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(projectPricingPath, JSON.stringify({ notModels: {} }));

      setPricingProjectPath(testDir);
      const overrides = getPricingOverrides();

      expect(overrides).toEqual({});
    });

    it('ignores models with missing required fields', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      const customPricing = {
        models: {
          'valid-model': { inputPer1k: 0.01, outputPer1k: 0.05 },
          'invalid-model-1': { inputPer1k: 0.01 }, // missing outputPer1k
          'invalid-model-2': { outputPer1k: 0.05 }, // missing inputPer1k
          'invalid-model-3': { inputPer1k: 'not a number', outputPer1k: 0.05 },
        },
      };
      fs.writeFileSync(projectPricingPath, JSON.stringify(customPricing));

      setPricingProjectPath(testDir);
      const overrides = getPricingOverrides();

      expect(overrides['valid-model']).toBeDefined();
      expect(overrides['invalid-model-1']).toBeUndefined();
      expect(overrides['invalid-model-2']).toBeUndefined();
      expect(overrides['invalid-model-3']).toBeUndefined();
    });
  });

  describe('hasPricingOverride', () => {
    it('returns true for models with overrides', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(
        projectPricingPath,
        JSON.stringify({
          models: { 'custom-model': { inputPer1k: 0.01, outputPer1k: 0.05 } },
        })
      );

      setPricingProjectPath(testDir);

      expect(hasPricingOverride('custom-model')).toBe(true);
      expect(hasPricingOverride('non-existent-model')).toBe(false);
    });
  });

  describe('getOverriddenModels', () => {
    it('returns list of models with overrides', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(
        projectPricingPath,
        JSON.stringify({
          models: {
            'model-a': { inputPer1k: 0.01, outputPer1k: 0.05 },
            'model-b': { inputPer1k: 0.02, outputPer1k: 0.10 },
          },
        })
      );

      setPricingProjectPath(testDir);
      const overriddenModels = getOverriddenModels();

      expect(overriddenModels).toContain('model-a');
      expect(overriddenModels).toContain('model-b');
      expect(overriddenModels.length).toBe(2);
    });
  });

  describe('getPricingConfigPaths', () => {
    it('returns correct global path', () => {
      const paths = getPricingConfigPaths();
      expect(paths.global).toBe(path.join(os.homedir(), '.karma', 'pricing.json'));
    });

    it('returns null project path when no project specified', () => {
      const paths = getPricingConfigPaths();
      expect(paths.project).toBeNull();
    });

    it('returns correct project path when specified', () => {
      const paths = getPricingConfigPaths('/some/project');
      expect(paths.project).toBe('/some/project/.karma-pricing.json');
    });
  });

  describe('integration with cost calculation', () => {
    it('uses overridden pricing in cost calculations', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(
        projectPricingPath,
        JSON.stringify({
          models: {
            'enterprise-sonnet': {
              inputPer1k: 0.001, // $1 per 1M (very cheap)
              outputPer1k: 0.005, // $5 per 1M
            },
          },
        })
      );

      setPricingProjectPath(testDir);

      const usage: TokenUsage = {
        inputTokens: 1_000_000,
        outputTokens: 100_000,
        cacheReadTokens: 0,
        cacheCreationTokens: 0,
      };

      const cost = calculateCost('enterprise-sonnet', usage);

      // Input: 1M * $1/1M = $1
      expect(cost.inputCost).toBeCloseTo(1.0, 2);
      // Output: 100K * $5/1M = $0.5
      expect(cost.outputCost).toBeCloseTo(0.5, 2);
    });

    it('overrides hardcoded model pricing', () => {
      // Override the standard sonnet model
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(
        projectPricingPath,
        JSON.stringify({
          models: {
            'claude-sonnet-4-20250514': {
              inputPer1k: 0.001, // Override to $1 per 1M
              outputPer1k: 0.005, // Override to $5 per 1M
            },
          },
        })
      );

      setPricingProjectPath(testDir);

      const pricing = getPricingForModel('claude-sonnet-4-20250514');

      // Should use overridden pricing, not hardcoded $3/$15
      expect(pricing.input).toBe(1.0);
      expect(pricing.output).toBe(5.0);
    });

    it('includes overridden models in getKnownModels', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(
        projectPricingPath,
        JSON.stringify({
          models: {
            'brand-new-enterprise-model': {
              inputPer1k: 0.020,
              outputPer1k: 0.100,
            },
          },
        })
      );

      setPricingProjectPath(testDir);

      const knownModels = getKnownModels();
      expect(knownModels).toContain('brand-new-enterprise-model');
    });

    it('recognizes overridden models with isKnownModel', () => {
      const projectPricingPath = path.join(testDir, '.karma-pricing.json');
      fs.writeFileSync(
        projectPricingPath,
        JSON.stringify({
          models: {
            'special-enterprise-model': {
              inputPer1k: 0.020,
              outputPer1k: 0.100,
            },
          },
        })
      );

      setPricingProjectPath(testDir);

      expect(isKnownModel('special-enterprise-model')).toBe(true);
    });
  });
});
