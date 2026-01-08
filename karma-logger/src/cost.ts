/**
 * Cost Calculation for Claude models
 * Phase 3: Model pricing and cost estimation
 */

import type { TokenUsage } from './types.js';

/**
 * Pricing per 1 million tokens for each model
 */
export interface ModelPricing {
  input: number;
  output: number;
  cacheRead: number;
  cacheCreation: number;
}

/**
 * Cost breakdown for a usage calculation
 */
export interface CostBreakdown {
  inputCost: number;
  outputCost: number;
  cacheReadCost: number;
  cacheCreationCost: number;
  total: number;
  model: string;
}

/**
 * Model pricing table (per 1M tokens)
 * Updated for Claude 4.x models as of 2025
 */
export const MODEL_PRICING: Record<string, ModelPricing> = {
  // Claude 4.5 Opus
  'claude-opus-4-5-20251101': {
    input: 15.00,
    output: 75.00,
    cacheRead: 1.50,
    cacheCreation: 18.75,
  },
  // Claude 4 Opus
  'claude-opus-4-20250514': {
    input: 15.00,
    output: 75.00,
    cacheRead: 1.50,
    cacheCreation: 18.75,
  },
  // Claude 4 Sonnet
  'claude-sonnet-4-20250514': {
    input: 3.00,
    output: 15.00,
    cacheRead: 0.30,
    cacheCreation: 3.75,
  },
  // Claude 4.5 Haiku
  'claude-haiku-4-5-20251001': {
    input: 0.80,
    output: 4.00,
    cacheRead: 0.08,
    cacheCreation: 1.00,
  },
  // Legacy Claude 3.5 models
  'claude-3-5-sonnet-20241022': {
    input: 3.00,
    output: 15.00,
    cacheRead: 0.30,
    cacheCreation: 3.75,
  },
  'claude-3-5-haiku-20241022': {
    input: 0.80,
    output: 4.00,
    cacheRead: 0.08,
    cacheCreation: 1.00,
  },
};

/**
 * Default pricing for unknown models (uses Sonnet pricing as fallback)
 */
const DEFAULT_PRICING: ModelPricing = {
  input: 3.00,
  output: 15.00,
  cacheRead: 0.30,
  cacheCreation: 3.75,
};

/**
 * Get pricing for a model, with fallback for unknown models
 */
export function getPricingForModel(model: string): ModelPricing {
  // Direct match
  if (MODEL_PRICING[model]) {
    return MODEL_PRICING[model];
  }

  // Try prefix matching for model families
  const modelLower = model.toLowerCase();

  if (modelLower.includes('opus')) {
    return MODEL_PRICING['claude-opus-4-5-20251101'];
  }
  if (modelLower.includes('haiku')) {
    return MODEL_PRICING['claude-haiku-4-5-20251001'];
  }
  if (modelLower.includes('sonnet')) {
    return MODEL_PRICING['claude-sonnet-4-20250514'];
  }

  return DEFAULT_PRICING;
}

/**
 * Calculate cost from token usage
 */
export function calculateCost(model: string, usage: TokenUsage): CostBreakdown {
  const pricing = getPricingForModel(model);

  const inputCost = (usage.inputTokens / 1_000_000) * pricing.input;
  const outputCost = (usage.outputTokens / 1_000_000) * pricing.output;
  const cacheReadCost = (usage.cacheReadTokens / 1_000_000) * pricing.cacheRead;
  const cacheCreationCost = (usage.cacheCreationTokens / 1_000_000) * pricing.cacheCreation;

  return {
    inputCost,
    outputCost,
    cacheReadCost,
    cacheCreationCost,
    total: inputCost + outputCost + cacheReadCost + cacheCreationCost,
    model,
  };
}

/**
 * Format cost as currency string
 */
export function formatCost(cost: number, currency = 'USD'): string {
  if (cost < 0.01) {
    return `<$0.01`;
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(cost);
}

/**
 * Format token count with K/M suffixes
 */
export function formatTokens(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(2)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}K`;
  }
  return count.toString();
}

/**
 * Add two cost breakdowns together
 */
export function addCosts(a: CostBreakdown, b: CostBreakdown): CostBreakdown {
  return {
    inputCost: a.inputCost + b.inputCost,
    outputCost: a.outputCost + b.outputCost,
    cacheReadCost: a.cacheReadCost + b.cacheReadCost,
    cacheCreationCost: a.cacheCreationCost + b.cacheCreationCost,
    total: a.total + b.total,
    model: 'mixed',
  };
}

/**
 * Create an empty cost breakdown
 */
export function emptyCostBreakdown(): CostBreakdown {
  return {
    inputCost: 0,
    outputCost: 0,
    cacheReadCost: 0,
    cacheCreationCost: 0,
    total: 0,
    model: 'none',
  };
}

/**
 * Get list of known models
 */
export function getKnownModels(): string[] {
  return Object.keys(MODEL_PRICING);
}

/**
 * Check if a model is known
 */
export function isKnownModel(model: string): boolean {
  return model in MODEL_PRICING;
}
