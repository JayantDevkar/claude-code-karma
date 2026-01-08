/**
 * Cost Calculation for Claude models
 * Phase 3: Model pricing and cost estimation
 *
 * Supports pricing overrides via configuration files:
 * - ~/.karma/pricing.json (global user config)
 * - .karma-pricing.json (project-level config)
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
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
 * Simplified pricing format for config files (per 1K tokens for easier reading)
 */
export interface ConfigModelPricing {
  inputPer1k: number;
  outputPer1k: number;
  cacheReadPer1k?: number;
  cacheCreationPer1k?: number;
}

/**
 * Pricing configuration file format
 */
export interface PricingConfigFile {
  models: Record<string, ConfigModelPricing>;
}

// ============================================
// Pricing Config File Paths
// ============================================

/** Global pricing config path (~/.karma/pricing.json) */
const GLOBAL_PRICING_PATH = path.join(os.homedir(), '.karma', 'pricing.json');

/** Project-level pricing config filename */
const PROJECT_PRICING_FILENAME = '.karma-pricing.json';

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

// ============================================
// Pricing Override System
// ============================================

/** Cached pricing overrides */
let _pricingOverrides: Record<string, ModelPricing> | null = null;

/** Current project path for config resolution */
let _currentProjectPath: string | null = null;

/**
 * Convert config pricing (per 1K) to internal pricing (per 1M)
 */
function configToModelPricing(config: ConfigModelPricing): ModelPricing {
  return {
    input: config.inputPer1k * 1000,
    output: config.outputPer1k * 1000,
    cacheRead: (config.cacheReadPer1k ?? config.inputPer1k * 0.1) * 1000,
    cacheCreation: (config.cacheCreationPer1k ?? config.inputPer1k * 1.25) * 1000,
  };
}

/**
 * Load and parse a pricing config file
 */
function loadPricingFile(filePath: string): Record<string, ModelPricing> | null {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    const content = fs.readFileSync(filePath, 'utf-8');
    const config = JSON.parse(content) as PricingConfigFile;

    if (!config.models || typeof config.models !== 'object') {
      return null;
    }

    const result: Record<string, ModelPricing> = {};
    for (const [model, pricing] of Object.entries(config.models)) {
      if (
        typeof pricing.inputPer1k === 'number' &&
        typeof pricing.outputPer1k === 'number'
      ) {
        result[model] = configToModelPricing(pricing);
      }
    }
    return Object.keys(result).length > 0 ? result : null;
  } catch {
    // Invalid JSON or read error, return null
    return null;
  }
}

/**
 * Load pricing overrides from config files
 * Priority: project-level > global > hardcoded defaults
 */
function loadPricingOverrides(projectPath?: string): Record<string, ModelPricing> {
  const overrides: Record<string, ModelPricing> = {};

  // Load global config first (lowest priority of overrides)
  const globalPricing = loadPricingFile(GLOBAL_PRICING_PATH);
  if (globalPricing) {
    Object.assign(overrides, globalPricing);
  }

  // Load project-level config (higher priority)
  if (projectPath) {
    const projectPricingPath = path.join(projectPath, PROJECT_PRICING_FILENAME);
    const projectPricing = loadPricingFile(projectPricingPath);
    if (projectPricing) {
      Object.assign(overrides, projectPricing);
    }
  }

  return overrides;
}

/**
 * Get merged pricing table (hardcoded + overrides)
 */
function getEffectivePricing(): Record<string, ModelPricing> {
  if (_pricingOverrides === null) {
    _pricingOverrides = loadPricingOverrides(_currentProjectPath ?? undefined);
  }

  return {
    ...MODEL_PRICING,
    ..._pricingOverrides,
  };
}

/**
 * Set the current project path for pricing config resolution
 */
export function setPricingProjectPath(projectPath: string | null): void {
  if (_currentProjectPath !== projectPath) {
    _currentProjectPath = projectPath;
    _pricingOverrides = null; // Clear cache to reload with new path
  }
}

/**
 * Clear pricing cache (useful after config changes or for testing)
 */
export function clearPricingCache(): void {
  _pricingOverrides = null;
}

/**
 * Get all pricing overrides currently in effect
 */
export function getPricingOverrides(): Record<string, ModelPricing> {
  if (_pricingOverrides === null) {
    _pricingOverrides = loadPricingOverrides(_currentProjectPath ?? undefined);
  }
  return { ..._pricingOverrides };
}

/**
 * Check if a model has a pricing override
 */
export function hasPricingOverride(model: string): boolean {
  const overrides = getPricingOverrides();
  return model in overrides;
}

/**
 * Get pricing for a model, with fallback for unknown models
 * Checks overrides first, then hardcoded prices, then family matching
 */
export function getPricingForModel(model: string): ModelPricing {
  const effectivePricing = getEffectivePricing();

  // Direct match (includes overrides)
  if (effectivePricing[model]) {
    return effectivePricing[model];
  }

  // Try prefix matching for model families
  const modelLower = model.toLowerCase();

  if (modelLower.includes('opus')) {
    return effectivePricing['claude-opus-4-5-20251101'] ?? MODEL_PRICING['claude-opus-4-5-20251101'];
  }
  if (modelLower.includes('haiku')) {
    return effectivePricing['claude-haiku-4-5-20251001'] ?? MODEL_PRICING['claude-haiku-4-5-20251001'];
  }
  if (modelLower.includes('sonnet')) {
    return effectivePricing['claude-sonnet-4-20250514'] ?? MODEL_PRICING['claude-sonnet-4-20250514'];
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
 * Get list of known models (including any from pricing overrides)
 */
export function getKnownModels(): string[] {
  const effectivePricing = getEffectivePricing();
  return Object.keys(effectivePricing);
}

/**
 * Check if a model is known (including any from pricing overrides)
 */
export function isKnownModel(model: string): boolean {
  const effectivePricing = getEffectivePricing();
  return model in effectivePricing;
}

/**
 * Get list of models with custom pricing overrides
 */
export function getOverriddenModels(): string[] {
  return Object.keys(getPricingOverrides());
}

/**
 * Get the pricing config file paths that would be checked
 */
export function getPricingConfigPaths(projectPath?: string): { global: string; project: string | null } {
  return {
    global: GLOBAL_PRICING_PATH,
    project: projectPath ? path.join(projectPath, PROJECT_PRICING_FILENAME) : null,
  };
}
