/**
 * Streaming JSONL parser for Claude Code session logs
 */

import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { basename } from 'node:path';

import type { RawLogEntry, LogEntry, ParsedSession } from './types/index.js';
import { isValidEntry } from './guards.js';
import { normalizeEntry, emptyUsage, addUsage } from './normalize.js';

/**
 * Parse a single JSONL line safely
 */
export function parseLine(line: string): RawLogEntry | null {
  try {
    const parsed = JSON.parse(line);
    if (isValidEntry(parsed)) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Extract session ID from file path
 * Files are named like: 0074cde8-b763-45ee-be32-cfc80f965b4d.jsonl
 */
export function extractSessionId(filePath: string): string {
  const filename = basename(filePath, '.jsonl');
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (uuidPattern.test(filename)) {
    return filename;
  }
  return filename;
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

  const projectPath = '';
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
