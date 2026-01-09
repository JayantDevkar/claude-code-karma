import { describe, it, expect } from 'vitest';
import {
  filterAssistantEntries,
  getTotalUsage,
  buildHierarchy,
  getModels,
  getSessionDuration,
  filterByTimeRange,
  groupBySession,
  findRootEntries,
  findEntryByUuid,
} from '../src/index.js';
import type { LogEntry } from '../src/index.js';

const mockEntries: LogEntry[] = [
  {
    type: 'user',
    uuid: 'u1',
    parentUuid: null,
    sessionId: 's1',
    timestamp: new Date('2025-01-09T10:00:00Z'),
    toolCalls: [],
    hasThinking: false,
  },
  {
    type: 'assistant',
    uuid: 'a1',
    parentUuid: 'u1',
    sessionId: 's1',
    timestamp: new Date('2025-01-09T10:00:05Z'),
    model: 'claude-3-opus',
    usage: { inputTokens: 10, outputTokens: 5, cacheReadTokens: 0, cacheCreationTokens: 0 },
    toolCalls: ['Read'],
    hasThinking: false,
  },
  {
    type: 'user',
    uuid: 'u2',
    parentUuid: 'a1',
    sessionId: 's1',
    timestamp: new Date('2025-01-09T10:00:10Z'),
    toolCalls: [],
    hasThinking: false,
  },
  {
    type: 'assistant',
    uuid: 'a2',
    parentUuid: 'u2',
    sessionId: 's1',
    timestamp: new Date('2025-01-09T10:00:15Z'),
    model: 'claude-3-sonnet',
    usage: { inputTokens: 20, outputTokens: 10, cacheReadTokens: 5, cacheCreationTokens: 0 },
    toolCalls: ['Write', 'Bash'],
    hasThinking: true,
  },
];

describe('filterAssistantEntries', () => {
  it('filters to assistant entries with usage', () => {
    const result = filterAssistantEntries(mockEntries);
    expect(result).toHaveLength(2);
    expect(result.every(e => e.type === 'assistant')).toBe(true);
  });

  it('excludes assistant entries without usage', () => {
    const entries: LogEntry[] = [
      {
        type: 'assistant',
        uuid: 'a1',
        parentUuid: null,
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
        // No usage field
      },
    ];
    const result = filterAssistantEntries(entries);
    expect(result).toHaveLength(0);
  });

  it('returns empty array for empty input', () => {
    expect(filterAssistantEntries([])).toEqual([]);
  });
});

describe('getTotalUsage', () => {
  it('sums token usage across entries', () => {
    const total = getTotalUsage(mockEntries);
    expect(total.inputTokens).toBe(30);
    expect(total.outputTokens).toBe(15);
    expect(total.cacheReadTokens).toBe(5);
    expect(total.cacheCreationTokens).toBe(0);
  });

  it('handles entries without usage', () => {
    const entries: LogEntry[] = [
      {
        type: 'user',
        uuid: 'u1',
        parentUuid: null,
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
      },
    ];
    const total = getTotalUsage(entries);
    expect(total.inputTokens).toBe(0);
    expect(total.outputTokens).toBe(0);
  });

  it('returns zero for empty entries', () => {
    const total = getTotalUsage([]);
    expect(total.inputTokens).toBe(0);
    expect(total.outputTokens).toBe(0);
  });
});

describe('buildHierarchy', () => {
  it('builds parent-child map', () => {
    const hierarchy = buildHierarchy(mockEntries);
    expect(hierarchy.get('u1')).toEqual(['a1']);
    expect(hierarchy.get('a1')).toEqual(['u2']);
    expect(hierarchy.get('u2')).toEqual(['a2']);
  });

  it('returns empty map for entries without parents', () => {
    const entries: LogEntry[] = [
      {
        type: 'user',
        uuid: 'u1',
        parentUuid: null,
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
      },
    ];
    const hierarchy = buildHierarchy(entries);
    expect(hierarchy.size).toBe(0);
  });

  it('groups multiple children under same parent', () => {
    const entries: LogEntry[] = [
      {
        type: 'user',
        uuid: 'u1',
        parentUuid: null,
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
      },
      {
        type: 'assistant',
        uuid: 'a1',
        parentUuid: 'u1',
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
      },
      {
        type: 'assistant',
        uuid: 'a2',
        parentUuid: 'u1',
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
      },
    ];
    const hierarchy = buildHierarchy(entries);
    expect(hierarchy.get('u1')).toEqual(['a1', 'a2']);
  });
});

describe('getModels', () => {
  it('returns unique models', () => {
    const models = getModels(mockEntries);
    expect(models).toContain('claude-3-opus');
    expect(models).toContain('claude-3-sonnet');
    expect(models).toHaveLength(2);
  });

  it('handles entries without models', () => {
    const entries: LogEntry[] = [
      {
        type: 'user',
        uuid: 'u1',
        parentUuid: null,
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
      },
    ];
    const models = getModels(entries);
    expect(models).toHaveLength(0);
  });

  it('deduplicates same model', () => {
    const entries: LogEntry[] = [
      {
        type: 'assistant',
        uuid: 'a1',
        parentUuid: null,
        sessionId: 's1',
        timestamp: new Date(),
        model: 'claude-3-opus',
        toolCalls: [],
        hasThinking: false,
      },
      {
        type: 'assistant',
        uuid: 'a2',
        parentUuid: 'a1',
        sessionId: 's1',
        timestamp: new Date(),
        model: 'claude-3-opus',
        toolCalls: [],
        hasThinking: false,
      },
    ];
    const models = getModels(entries);
    expect(models).toEqual(['claude-3-opus']);
  });
});

describe('getSessionDuration', () => {
  it('calculates duration in milliseconds', () => {
    const duration = getSessionDuration(mockEntries);
    expect(duration).toBe(15000); // 15 seconds
  });

  it('returns 0 for single entry', () => {
    const entries = [mockEntries[0]];
    expect(getSessionDuration(entries)).toBe(0);
  });

  it('returns 0 for empty entries', () => {
    expect(getSessionDuration([])).toBe(0);
  });
});

describe('filterByTimeRange', () => {
  it('filters entries within time range', () => {
    const start = new Date('2025-01-09T10:00:04Z');
    const end = new Date('2025-01-09T10:00:11Z');
    const filtered = filterByTimeRange(mockEntries, start, end);
    expect(filtered).toHaveLength(2);
    expect(filtered.map(e => e.uuid)).toEqual(['a1', 'u2']);
  });

  it('includes boundary timestamps', () => {
    const start = new Date('2025-01-09T10:00:00Z');
    const end = new Date('2025-01-09T10:00:05Z');
    const filtered = filterByTimeRange(mockEntries, start, end);
    expect(filtered).toHaveLength(2);
  });

  it('returns empty for non-overlapping range', () => {
    const start = new Date('2025-01-09T11:00:00Z');
    const end = new Date('2025-01-09T12:00:00Z');
    const filtered = filterByTimeRange(mockEntries, start, end);
    expect(filtered).toHaveLength(0);
  });
});

describe('groupBySession', () => {
  it('groups entries by session ID', () => {
    const entries: LogEntry[] = [
      { ...mockEntries[0], sessionId: 's1' },
      { ...mockEntries[1], sessionId: 's2' },
      { ...mockEntries[2], sessionId: 's1' },
    ];
    const grouped = groupBySession(entries);
    expect(grouped.size).toBe(2);
    expect(grouped.get('s1')).toHaveLength(2);
    expect(grouped.get('s2')).toHaveLength(1);
  });

  it('returns empty map for empty entries', () => {
    const grouped = groupBySession([]);
    expect(grouped.size).toBe(0);
  });
});

describe('findRootEntries', () => {
  it('finds entries with no parent', () => {
    const roots = findRootEntries(mockEntries);
    expect(roots).toHaveLength(1);
    expect(roots[0].uuid).toBe('u1');
  });

  it('returns empty for no roots', () => {
    const entries: LogEntry[] = [
      {
        type: 'assistant',
        uuid: 'a1',
        parentUuid: 'u1', // has parent
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: [],
        hasThinking: false,
      },
    ];
    const roots = findRootEntries(entries);
    expect(roots).toHaveLength(0);
  });
});

describe('findEntryByUuid', () => {
  it('finds entry by UUID', () => {
    const entry = findEntryByUuid(mockEntries, 'a1');
    expect(entry).toBeDefined();
    expect(entry?.uuid).toBe('a1');
    expect(entry?.type).toBe('assistant');
  });

  it('returns undefined for unknown UUID', () => {
    const entry = findEntryByUuid(mockEntries, 'unknown');
    expect(entry).toBeUndefined();
  });

  it('returns undefined for empty entries', () => {
    const entry = findEntryByUuid([], 'a1');
    expect(entry).toBeUndefined();
  });
});
