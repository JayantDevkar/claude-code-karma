/**
 * JSONL Parser for Claude Code session logs
 * Phase 1: Streaming parser that extracts metrics from Claude Code logs
 */

import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { basename } from 'node:path';
import type {
  RawLogEntry,
  LogEntry,
  TokenUsage,
  ParsedSession,
  AssistantMessage,
  ContentBlock,
  ToolUseBlock,
} from './types.js';

/**
 * Type guard to check if entry is a valid user or assistant entry
 */
export function isValidEntry(entry: unknown): entry is RawLogEntry {
  if (typeof entry !== 'object' || entry === null) return false;
  const e = entry as Record<string, unknown>;
  return (
    (e.type === 'user' || e.type === 'assistant') &&
    typeof e.uuid === 'string' &&
    typeof e.sessionId === 'string' &&
    typeof e.timestamp === 'string'
  );
}

/**
 * Type guard to check if message is an assistant message with usage
 */
export function isAssistantMessage(msg: unknown): msg is AssistantMessage {
  if (typeof msg !== 'object' || msg === null) return false;
  const m = msg as Record<string, unknown>;
  return m.role === 'assistant' && typeof m.usage === 'object';
}

/**
 * Extract tool call names from content blocks
 */
export function extractToolCalls(content: ContentBlock[]): string[] {
  return content
    .filter((block): block is ToolUseBlock => block.type === 'tool_use')
    .map(block => block.name);
}

/**
 * Check if content contains thinking blocks
 */
export function hasThinkingContent(content: ContentBlock[]): boolean {
  return content.some(block => block.type === 'thinking');
}

/**
 * Normalize raw usage to our internal format
 */
export function normalizeUsage(raw: AssistantMessage['usage']): TokenUsage {
  return {
    inputTokens: raw.input_tokens ?? 0,
    outputTokens: raw.output_tokens ?? 0,
    cacheReadTokens: raw.cache_read_input_tokens ?? 0,
    cacheCreationTokens: raw.cache_creation_input_tokens ?? 0,
  };
}

/**
 * Transform raw entry to normalized LogEntry
 */
export function normalizeEntry(raw: RawLogEntry): LogEntry {
  const entry: LogEntry = {
    type: raw.type as 'user' | 'assistant',
    uuid: raw.uuid,
    parentUuid: raw.parentUuid,
    sessionId: raw.sessionId,
    timestamp: new Date(raw.timestamp),
    toolCalls: [],
    hasThinking: false,
  };

  if (raw.type === 'assistant' && raw.message && isAssistantMessage(raw.message)) {
    entry.model = raw.message.model;
    entry.usage = normalizeUsage(raw.message.usage);
    entry.toolCalls = extractToolCalls(raw.message.content);
    entry.hasThinking = hasThinkingContent(raw.message.content);
  }

  return entry;
}

/**
 * Parse a single JSONL line safely
 */
function parseLine(line: string): RawLogEntry | null {
  try {
    const parsed = JSON.parse(line);
    if (isValidEntry(parsed)) {
      return parsed;
    }
    return null;
  } catch {
    // Skip malformed JSON lines
    return null;
  }
}

/**
 * Extract session ID from file path
 * Files are named like: 0074cde8-b763-45ee-be32-cfc80f965b4d.jsonl
 */
export function extractSessionId(filePath: string): string {
  const filename = basename(filePath, '.jsonl');
  // Validate UUID format
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (uuidPattern.test(filename)) {
    return filename;
  }
  return filename; // Return as-is if not UUID format
}

/**
 * Create empty token usage
 */
function emptyUsage(): TokenUsage {
  return {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheCreationTokens: 0,
  };
}

/**
 * Add two token usages together
 */
function addUsage(a: TokenUsage, b: TokenUsage): TokenUsage {
  return {
    inputTokens: a.inputTokens + b.inputTokens,
    outputTokens: a.outputTokens + b.outputTokens,
    cacheReadTokens: a.cacheReadTokens + b.cacheReadTokens,
    cacheCreationTokens: a.cacheCreationTokens + b.cacheCreationTokens,
  };
}

/**
 * Parse a JSONL session file and return normalized entries
 * Uses streaming to handle large files efficiently
 */
export async function parseSessionFile(filePath: string): Promise<LogEntry[]> {
  const entries: LogEntry[] = [];

  const rl = createInterface({
    input: createReadStream(filePath),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    const raw = parseLine(line);
    if (raw) {
      entries.push(normalizeEntry(raw));
    }
  }

  return entries;
}

/**
 * Parse a session file and return a complete ParsedSession
 */
export async function parseSession(filePath: string): Promise<ParsedSession> {
  const entries = await parseSessionFile(filePath);
  const sessionId = extractSessionId(filePath);

  // Extract project path from first entry with cwd
  const projectPath = '';  // Will be extracted from discovery in Phase 2

  // Calculate aggregates
  const models = new Set<string>();
  let totalUsage = emptyUsage();
  let startTime = new Date();
  let endTime = new Date();

  for (const entry of entries) {
    if (entry.model) {
      models.add(entry.model);
    }
    if (entry.usage) {
      totalUsage = addUsage(totalUsage, entry.usage);
    }
  }

  if (entries.length > 0) {
    startTime = entries[0].timestamp;
    endTime = entries[entries.length - 1].timestamp;
  }

  return {
    sessionId,
    projectPath,
    entries,
    startTime,
    endTime,
    models,
    totalUsage,
  };
}

/**
 * Filter entries to only assistant messages with usage data
 */
export function filterAssistantEntries(entries: LogEntry[]): LogEntry[] {
  return entries.filter(e => e.type === 'assistant' && e.usage);
}

/**
 * Get total token usage from entries
 */
export function getTotalUsage(entries: LogEntry[]): TokenUsage {
  return entries.reduce(
    (acc, entry) => entry.usage ? addUsage(acc, entry.usage) : acc,
    emptyUsage()
  );
}

/**
 * Build a parent-child hierarchy map from entries
 */
export function buildHierarchy(entries: LogEntry[]): Map<string, string[]> {
  const children = new Map<string, string[]>();

  for (const entry of entries) {
    if (entry.parentUuid) {
      const existing = children.get(entry.parentUuid) ?? [];
      existing.push(entry.uuid);
      children.set(entry.parentUuid, existing);
    }
  }

  return children;
}

/**
 * Get unique models used in a session
 */
export function getModels(entries: LogEntry[]): string[] {
  const models = new Set<string>();
  for (const entry of entries) {
    if (entry.model) {
      models.add(entry.model);
    }
  }
  return Array.from(models);
}

/**
 * Get tool usage counts
 */
export function getToolUsageCounts(entries: LogEntry[]): Map<string, number> {
  const counts = new Map<string, number>();

  for (const entry of entries) {
    for (const tool of entry.toolCalls) {
      counts.set(tool, (counts.get(tool) ?? 0) + 1);
    }
  }

  return counts;
}

/**
 * Agent spawn info extracted from Task tool calls
 */
export interface AgentSpawnInfo {
  agentId: string;
  subagentType: string;
  description: string;
  toolUseId: string;
}

/**
 * Extract agent spawn information from a session file
 * 
 * Parses Task tool_use blocks (in assistant entries) to get subagent_type,
 * then matches with tool_result blocks (in user entries) to get agentId.
 * 
 * Returns a map of agentId -> AgentSpawnInfo
 */
export async function extractAgentSpawns(filePath: string): Promise<Map<string, AgentSpawnInfo>> {
  const spawns = new Map<string, AgentSpawnInfo>();
  
  // Track Task tool calls by their tool_use_id
  const pendingTasks = new Map<string, { subagentType: string; description: string }>();

  const rl = createInterface({
    input: createReadStream(filePath),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    try {
      const entry = JSON.parse(line);
      
      // Look for Task tool_use in assistant entries
      if (entry.type === 'assistant' && entry.message?.content) {
        for (const block of entry.message.content) {
          if (block.type === 'tool_use' && block.name === 'Task' && block.input) {
            const subagentType = block.input.subagent_type || 'task';
            const description = block.input.description || '';
            pendingTasks.set(block.id, { subagentType, description });
          }
        }
      }
      
      // Look for tool_result in user entries to get agentId
      if (entry.type === 'user' && entry.message?.content) {
        for (const block of entry.message.content) {
          if (block.type === 'tool_result' && block.tool_use_id) {
            const pending = pendingTasks.get(block.tool_use_id);
            if (pending) {
              // Extract agentId from result text
              const resultText = typeof block.content === 'string' 
                ? block.content 
                : JSON.stringify(block.content);
              
              const agentIdMatch = resultText.match(/agentId:\s*([a-f0-9]{7})/i);
              if (agentIdMatch) {
                const agentId = agentIdMatch[1];
                spawns.set(agentId, {
                  agentId,
                  subagentType: pending.subagentType,
                  description: pending.description,
                  toolUseId: block.tool_use_id,
                });
              }
              pendingTasks.delete(block.tool_use_id);
            }
          }
        }
      }
    } catch {
      // Skip malformed lines
    }
  }

  return spawns;
}
