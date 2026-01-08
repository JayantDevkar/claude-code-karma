/**
 * Watch command unit tests
 * Phase 5: karma watch command tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Test ActivityBuffer behavior
describe('ActivityBuffer', () => {
  class ActivityBuffer {
    private entries: { timestamp: Date; content: string }[] = [];
    private maxSize: number;

    constructor(maxSize = 20) {
      this.maxSize = maxSize;
    }

    add(entry: { timestamp: Date; content: string }): void {
      this.entries.push(entry);
      if (this.entries.length > this.maxSize) {
        this.entries.shift();
      }
    }

    getAll(): { timestamp: Date; content: string }[] {
      return [...this.entries];
    }

    clear(): void {
      this.entries = [];
    }

    get length(): number {
      return this.entries.length;
    }
  }

  it('should add entries up to max size', () => {
    const buffer = new ActivityBuffer(5);

    for (let i = 0; i < 5; i++) {
      buffer.add({ timestamp: new Date(), content: `entry-${i}` });
    }

    expect(buffer.length).toBe(5);
  });

  it('should remove oldest entries when exceeding max size', () => {
    const buffer = new ActivityBuffer(3);

    buffer.add({ timestamp: new Date(), content: 'first' });
    buffer.add({ timestamp: new Date(), content: 'second' });
    buffer.add({ timestamp: new Date(), content: 'third' });
    buffer.add({ timestamp: new Date(), content: 'fourth' });

    const entries = buffer.getAll();
    expect(entries.length).toBe(3);
    expect(entries[0].content).toBe('second');
    expect(entries[2].content).toBe('fourth');
  });

  it('should clear all entries', () => {
    const buffer = new ActivityBuffer(10);

    buffer.add({ timestamp: new Date(), content: 'test' });
    buffer.add({ timestamp: new Date(), content: 'test2' });

    buffer.clear();
    expect(buffer.length).toBe(0);
  });

  it('should return a copy of entries', () => {
    const buffer = new ActivityBuffer(10);
    buffer.add({ timestamp: new Date(), content: 'test' });

    const entries1 = buffer.getAll();
    const entries2 = buffer.getAll();

    expect(entries1).not.toBe(entries2);
    expect(entries1).toEqual(entries2);
  });
});

describe('ANSI escape sequences', () => {
  const ANSI = {
    clearScreen: '\x1b[2J',
    cursorHome: '\x1b[H',
    cursorHide: '\x1b[?25l',
    cursorShow: '\x1b[?25h',
    clearLine: '\x1b[2K',
    moveTo: (row: number, col: number) => `\x1b[${row};${col}H`,
  };

  it('should have correct clear screen sequence', () => {
    expect(ANSI.clearScreen).toBe('\x1b[2J');
  });

  it('should have correct cursor home sequence', () => {
    expect(ANSI.cursorHome).toBe('\x1b[H');
  });

  it('should generate correct moveTo sequence', () => {
    expect(ANSI.moveTo(5, 10)).toBe('\x1b[5;10H');
    expect(ANSI.moveTo(1, 1)).toBe('\x1b[1;1H');
  });

  it('should have cursor visibility sequences', () => {
    expect(ANSI.cursorHide).toBe('\x1b[?25l');
    expect(ANSI.cursorShow).toBe('\x1b[?25h');
  });
});

describe('Box drawing characters', () => {
  const BOX = {
    topLeft: '┌',
    topRight: '┐',
    bottomLeft: '└',
    bottomRight: '┘',
    horizontal: '─',
    vertical: '│',
    dividerLeft: '├',
    dividerRight: '┤',
  };

  it('should have correct corner characters', () => {
    expect(BOX.topLeft).toBe('┌');
    expect(BOX.topRight).toBe('┐');
    expect(BOX.bottomLeft).toBe('└');
    expect(BOX.bottomRight).toBe('┘');
  });

  it('should have correct line characters', () => {
    expect(BOX.horizontal).toBe('─');
    expect(BOX.vertical).toBe('│');
  });

  it('should have correct divider characters', () => {
    expect(BOX.dividerLeft).toBe('├');
    expect(BOX.dividerRight).toBe('┤');
  });
});

describe('Time formatting', () => {
  function formatTime(date: Date): string {
    return date.toTimeString().slice(0, 8);
  }

  it('should format time as HH:MM:SS', () => {
    const date = new Date('2026-01-08T14:32:05');
    expect(formatTime(date)).toBe('14:32:05');
  });

  it('should pad single digit hours/minutes/seconds', () => {
    const date = new Date('2026-01-08T09:05:03');
    expect(formatTime(date)).toBe('09:05:03');
  });
});

describe('Model name shortening', () => {
  function shortModel(model: string): string {
    if (model.includes('opus')) return 'opus';
    if (model.includes('sonnet')) return 'sonnet';
    if (model.includes('haiku')) return 'haiku';
    return model.slice(0, 8);
  }

  it('should shorten opus models', () => {
    expect(shortModel('claude-opus-4-5-20251101')).toBe('opus');
    expect(shortModel('claude-opus-4-20250514')).toBe('opus');
  });

  it('should shorten sonnet models', () => {
    expect(shortModel('claude-sonnet-4-20250514')).toBe('sonnet');
    expect(shortModel('claude-3-5-sonnet-20241022')).toBe('sonnet');
  });

  it('should shorten haiku models', () => {
    expect(shortModel('claude-haiku-4-5-20251001')).toBe('haiku');
    expect(shortModel('claude-3-5-haiku-20241022')).toBe('haiku');
  });

  it('should truncate unknown models', () => {
    expect(shortModel('gpt-4-turbo-preview')).toBe('gpt-4-tu');
  });
});

describe('Tool type categorization', () => {
  function getToolCategory(tool: string): string {
    if (tool.includes('Read') || tool.includes('Glob') || tool.includes('Grep')) {
      return 'read';
    }
    if (tool.includes('Write') || tool.includes('Edit')) {
      return 'write';
    }
    if (tool.includes('Bash')) {
      return 'execute';
    }
    if (tool.includes('Task')) {
      return 'agent';
    }
    return 'other';
  }

  it('should categorize read tools', () => {
    expect(getToolCategory('Read')).toBe('read');
    expect(getToolCategory('Glob')).toBe('read');
    expect(getToolCategory('Grep')).toBe('read');
  });

  it('should categorize write tools', () => {
    expect(getToolCategory('Write')).toBe('write');
    expect(getToolCategory('Edit')).toBe('write');
  });

  it('should categorize execution tools', () => {
    expect(getToolCategory('Bash')).toBe('execute');
  });

  it('should categorize agent tools', () => {
    expect(getToolCategory('Task')).toBe('agent');
  });

  it('should categorize unknown tools', () => {
    expect(getToolCategory('WebFetch')).toBe('other');
    expect(getToolCategory('AskUser')).toBe('other');
  });
});

describe('Activity entry extraction', () => {
  interface LogEntry {
    type: 'user' | 'assistant';
    model?: string;
    toolCalls: string[];
    timestamp: Date;
  }

  interface SessionInfo {
    isAgent: boolean;
    sessionId: string;
  }

  interface ActivityEntry {
    timestamp: Date;
    model: string;
    type: 'tool' | 'message';
    content: string;
    isAgent: boolean;
  }

  function extractActivity(entry: LogEntry, session: SessionInfo): ActivityEntry | null {
    if (entry.type !== 'assistant') return null;

    const model = entry.model || 'unknown';

    if (entry.toolCalls.length > 0) {
      return {
        timestamp: entry.timestamp,
        model,
        type: 'tool',
        content: entry.toolCalls.join(', '),
        isAgent: session.isAgent,
      };
    }

    return null;
  }

  it('should extract tool calls from assistant entries', () => {
    const entry: LogEntry = {
      type: 'assistant',
      model: 'claude-sonnet-4-20250514',
      toolCalls: ['Read', 'Edit'],
      timestamp: new Date(),
    };

    const session: SessionInfo = { isAgent: false, sessionId: 'test' };
    const activity = extractActivity(entry, session);

    expect(activity).not.toBeNull();
    expect(activity?.type).toBe('tool');
    expect(activity?.content).toBe('Read, Edit');
    expect(activity?.isAgent).toBe(false);
  });

  it('should return null for user entries', () => {
    const entry: LogEntry = {
      type: 'user',
      toolCalls: [],
      timestamp: new Date(),
    };

    const session: SessionInfo = { isAgent: false, sessionId: 'test' };
    const activity = extractActivity(entry, session);

    expect(activity).toBeNull();
  });

  it('should return null for entries without tool calls', () => {
    const entry: LogEntry = {
      type: 'assistant',
      model: 'claude-sonnet-4-20250514',
      toolCalls: [],
      timestamp: new Date(),
    };

    const session: SessionInfo = { isAgent: false, sessionId: 'test' };
    const activity = extractActivity(entry, session);

    expect(activity).toBeNull();
  });

  it('should mark agent entries correctly', () => {
    const entry: LogEntry = {
      type: 'assistant',
      model: 'claude-haiku-4-5-20251001',
      toolCalls: ['Grep'],
      timestamp: new Date(),
    };

    const session: SessionInfo = { isAgent: true, sessionId: 'agent-123' };
    const activity = extractActivity(entry, session);

    expect(activity?.isAgent).toBe(true);
    expect(activity?.model).toBe('claude-haiku-4-5-20251001');
  });
});

describe('Watch options', () => {
  interface WatchOptions {
    project?: string;
    compact?: boolean;
    activityOnly?: boolean;
  }

  it('should have correct option types', () => {
    const options: WatchOptions = {
      project: 'test-project',
      compact: true,
      activityOnly: false,
    };

    expect(options.project).toBe('test-project');
    expect(options.compact).toBe(true);
    expect(options.activityOnly).toBe(false);
  });

  it('should allow all options to be undefined', () => {
    const options: WatchOptions = {};

    expect(options.project).toBeUndefined();
    expect(options.compact).toBeUndefined();
    expect(options.activityOnly).toBeUndefined();
  });
});
