/**
 * Utility functions for Claude Code session analysis
 */

import type { LogEntry, TokenUsage } from './types/index.js';
import { emptyUsage, addUsage } from './normalize.js';

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
 * Returns Map<parentUuid, childUuids[]>
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
 * Get unique models used in entries
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
 * Get session duration in milliseconds
 */
export function getSessionDuration(entries: LogEntry[]): number {
  if (entries.length < 2) return 0;
  const start = entries[0].timestamp.getTime();
  const end = entries[entries.length - 1].timestamp.getTime();
  return end - start;
}

/**
 * Get entries within a time range
 */
export function filterByTimeRange(
  entries: LogEntry[],
  start: Date,
  end: Date
): LogEntry[] {
  const startTime = start.getTime();
  const endTime = end.getTime();
  return entries.filter(e => {
    const time = e.timestamp.getTime();
    return time >= startTime && time <= endTime;
  });
}

/**
 * Group entries by session ID
 */
export function groupBySession(entries: LogEntry[]): Map<string, LogEntry[]> {
  const sessions = new Map<string, LogEntry[]>();

  for (const entry of entries) {
    const existing = sessions.get(entry.sessionId) ?? [];
    existing.push(entry);
    sessions.set(entry.sessionId, existing);
  }

  return sessions;
}

/**
 * Find root entries (entries with no parent)
 */
export function findRootEntries(entries: LogEntry[]): LogEntry[] {
  return entries.filter(e => e.parentUuid === null);
}

/**
 * Get entry by UUID
 */
export function findEntryByUuid(entries: LogEntry[], uuid: string): LogEntry | undefined {
  return entries.find(e => e.uuid === uuid);
}
