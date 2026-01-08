/**
 * Type Converters for Karma Logger
 * Handles conversion between in-memory types and database record types
 *
 * Fixes FLAW-007: Type Mismatch Between Memory and Database
 */

import type { SessionMetrics, AgentMetrics } from './aggregator.js';
import type { SessionRecord, AgentRecord } from './db.js';
import type { CostBreakdown } from './cost.js';
import { emptyCostBreakdown } from './cost.js';

// ============================================
// Session Converters
// ============================================

/**
 * Convert in-memory SessionMetrics to database SessionRecord
 *
 * Handles:
 * - Set<string> -> JSON string array
 * - Map<string, number> -> JSON object
 * - CostBreakdown object -> separate columns
 * - Date -> ISO 8601 string
 */
export function sessionMetricsToRecord(metrics: SessionMetrics): SessionRecord {
  return {
    id: metrics.sessionId,
    projectPath: metrics.projectPath,
    projectName: metrics.projectName,
    startedAt: metrics.startedAt.toISOString(),
    endedAt: metrics.lastActivity.toISOString(),
    models: JSON.stringify(Array.from(metrics.models)),
    tokensIn: metrics.tokensIn,
    tokensOut: metrics.tokensOut,
    cacheReadTokens: metrics.cacheReadTokens,
    cacheCreationTokens: metrics.cacheCreationTokens,
    costTotal: metrics.cost.total,
    costInput: metrics.cost.inputCost,
    costOutput: metrics.cost.outputCost,
    costCacheRead: metrics.cost.cacheReadCost,
    costCacheCreation: metrics.cost.cacheCreationCost,
    agentCount: metrics.agentCount,
    toolCalls: metrics.toolCalls,
    toolUsage: JSON.stringify(Object.fromEntries(metrics.toolUsage)),
  };
}

/**
 * Convert database SessionRecord to in-memory SessionMetrics
 *
 * Handles:
 * - JSON string array -> Set<string>
 * - JSON object -> Map<string, number>
 * - Separate columns -> CostBreakdown object
 * - ISO 8601 string -> Date
 */
export function sessionRecordToMetrics(record: SessionRecord): SessionMetrics {
  // Parse JSON fields with error handling
  let models: Set<string>;
  try {
    const modelsArray = JSON.parse(record.models) as string[];
    models = new Set(modelsArray);
  } catch {
    models = new Set();
  }

  let toolUsage: Map<string, number>;
  try {
    const toolUsageObj = JSON.parse(record.toolUsage) as Record<string, number>;
    toolUsage = new Map(Object.entries(toolUsageObj));
  } catch {
    toolUsage = new Map();
  }

  // Reconstruct CostBreakdown from separate columns
  const cost: CostBreakdown = {
    inputCost: record.costInput,
    outputCost: record.costOutput,
    cacheReadCost: record.costCacheRead,
    cacheCreationCost: record.costCacheCreation,
    total: record.costTotal,
    model: 'mixed', // Original model info is lost in aggregation
  };

  return {
    sessionId: record.id,
    projectPath: record.projectPath,
    projectName: record.projectName,
    startedAt: new Date(record.startedAt),
    lastActivity: record.endedAt ? new Date(record.endedAt) : new Date(record.startedAt),
    endedAt: record.endedAt ? new Date(record.endedAt) : undefined,
    status: record.endedAt ? 'ended' : 'active',
    tokensIn: record.tokensIn,
    tokensOut: record.tokensOut,
    cacheReadTokens: record.cacheReadTokens,
    cacheCreationTokens: record.cacheCreationTokens,
    cost,
    models,
    agentCount: record.agentCount,
    toolCalls: record.toolCalls,
    toolUsage,
    entryCount: 0, // Not stored in database
    assistantEntries: 0, // Not stored in database
  };
}

// ============================================
// Agent Converters
// ============================================

/**
 * Convert in-memory AgentMetrics to database AgentRecord
 *
 * Handles:
 * - Set<string> -> JSON string array
 * - CostBreakdown object -> single cost column
 * - Date -> ISO 8601 string
 */
export function agentMetricsToRecord(metrics: AgentMetrics): AgentRecord {
  return {
    id: metrics.agentId,
    sessionId: metrics.sessionId,
    parentId: metrics.parentId ?? null,
    agentType: metrics.agentType,
    model: metrics.model,
    startedAt: metrics.startedAt.toISOString(),
    endedAt: metrics.lastActivity.toISOString(),
    tokensIn: metrics.tokensIn,
    tokensOut: metrics.tokensOut,
    cacheReadTokens: metrics.cacheReadTokens,
    cacheCreationTokens: metrics.cacheCreationTokens,
    costTotal: metrics.cost.total,
    toolsUsed: JSON.stringify(Array.from(metrics.toolsUsed)),
    toolCalls: metrics.toolCalls,
  };
}

/**
 * Convert database AgentRecord to in-memory AgentMetrics
 *
 * Handles:
 * - JSON string array -> Set<string>
 * - Single cost column -> CostBreakdown object (partial)
 * - ISO 8601 string -> Date
 */
export function agentRecordToMetrics(record: AgentRecord): AgentMetrics {
  // Parse JSON fields with error handling
  let toolsUsed: Set<string>;
  try {
    const toolsArray = JSON.parse(record.toolsUsed) as string[];
    toolsUsed = new Set(toolsArray);
  } catch {
    toolsUsed = new Set();
  }

  // Reconstruct partial CostBreakdown (only total is stored for agents)
  const cost: CostBreakdown = {
    inputCost: 0, // Not stored for agents
    outputCost: 0, // Not stored for agents
    cacheReadCost: 0, // Not stored for agents
    cacheCreationCost: 0, // Not stored for agents
    total: record.costTotal,
    model: record.model,
  };

  return {
    agentId: record.id,
    sessionId: record.sessionId,
    parentId: record.parentId ?? undefined,
    agentType: record.agentType,
    model: record.model,
    startedAt: new Date(record.startedAt),
    lastActivity: record.endedAt ? new Date(record.endedAt) : new Date(record.startedAt),
    tokensIn: record.tokensIn,
    tokensOut: record.tokensOut,
    cacheReadTokens: record.cacheReadTokens,
    cacheCreationTokens: record.cacheCreationTokens,
    cost,
    toolsUsed,
    toolCalls: record.toolCalls,
    entryCount: 0, // Not stored in database
  };
}

// ============================================
// Utility Functions
// ============================================

/**
 * Parse models JSON string to Set<string>
 * Returns empty Set on parse error
 */
export function parseModelsJson(json: string): Set<string> {
  try {
    const arr = JSON.parse(json) as string[];
    return new Set(arr);
  } catch {
    return new Set();
  }
}

/**
 * Parse toolUsage JSON string to Map<string, number>
 * Returns empty Map on parse error
 */
export function parseToolUsageJson(json: string): Map<string, number> {
  try {
    const obj = JSON.parse(json) as Record<string, number>;
    return new Map(Object.entries(obj));
  } catch {
    return new Map();
  }
}

/**
 * Parse toolsUsed JSON string to Set<string>
 * Returns empty Set on parse error
 */
export function parseToolsUsedJson(json: string): Set<string> {
  try {
    const arr = JSON.parse(json) as string[];
    return new Set(arr);
  } catch {
    return new Set();
  }
}

/**
 * Serialize Set<string> to JSON string
 */
export function serializeSetToJson(set: Set<string>): string {
  return JSON.stringify(Array.from(set));
}

/**
 * Serialize Map<string, number> to JSON string
 */
export function serializeMapToJson(map: Map<string, number>): string {
  return JSON.stringify(Object.fromEntries(map));
}

/**
 * Reconstruct CostBreakdown from separate database columns
 */
export function reconstructCostBreakdown(
  costTotal: number,
  costInput: number,
  costOutput: number,
  costCacheRead: number,
  costCacheCreation: number,
  model = 'mixed'
): CostBreakdown {
  return {
    inputCost: costInput,
    outputCost: costOutput,
    cacheReadCost: costCacheRead,
    cacheCreationCost: costCacheCreation,
    total: costTotal,
    model,
  };
}

/**
 * Extract cost columns from CostBreakdown for database storage
 */
export function extractCostColumns(cost: CostBreakdown): {
  costTotal: number;
  costInput: number;
  costOutput: number;
  costCacheRead: number;
  costCacheCreation: number;
} {
  return {
    costTotal: cost.total,
    costInput: cost.inputCost,
    costOutput: cost.outputCost,
    costCacheRead: cost.cacheReadCost,
    costCacheCreation: cost.cacheCreationCost,
  };
}
