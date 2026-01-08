/**
 * Tests for type converters
 * FLAW-007: Type Mismatch Between Memory and Database
 */

import { describe, it, expect } from 'vitest';
import {
  sessionMetricsToRecord,
  sessionRecordToMetrics,
  agentMetricsToRecord,
  agentRecordToMetrics,
  parseModelsJson,
  parseToolUsageJson,
  parseToolsUsedJson,
  serializeSetToJson,
  serializeMapToJson,
  reconstructCostBreakdown,
  extractCostColumns,
} from '../src/converters.js';
import type { SessionMetrics, AgentMetrics } from '../src/aggregator.js';
import type { SessionRecord, AgentRecord } from '../src/db.js';
import type { CostBreakdown } from '../src/cost.js';

describe('converters', () => {
  describe('sessionMetricsToRecord', () => {
    it('should convert SessionMetrics to SessionRecord', () => {
      const metrics: SessionMetrics = {
        sessionId: 'test-session-123',
        projectPath: '/path/to/project',
        projectName: 'test-project',
        startedAt: new Date('2024-01-15T10:00:00Z'),
        lastActivity: new Date('2024-01-15T11:30:00Z'),
        tokensIn: 10000,
        tokensOut: 5000,
        cacheReadTokens: 2000,
        cacheCreationTokens: 1000,
        cost: {
          inputCost: 0.03,
          outputCost: 0.075,
          cacheReadCost: 0.0006,
          cacheCreationCost: 0.00375,
          total: 0.10935,
          model: 'claude-3-5-sonnet-20241022',
        },
        models: new Set(['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022']),
        agentCount: 3,
        toolCalls: 50,
        toolUsage: new Map([
          ['Read', 20],
          ['Write', 15],
          ['Bash', 15],
        ]),
        entryCount: 100,
        assistantEntries: 60,
      };

      const record = sessionMetricsToRecord(metrics);

      expect(record.id).toBe('test-session-123');
      expect(record.projectPath).toBe('/path/to/project');
      expect(record.projectName).toBe('test-project');
      expect(record.startedAt).toBe('2024-01-15T10:00:00.000Z');
      expect(record.endedAt).toBe('2024-01-15T11:30:00.000Z');
      expect(record.tokensIn).toBe(10000);
      expect(record.tokensOut).toBe(5000);
      expect(record.cacheReadTokens).toBe(2000);
      expect(record.cacheCreationTokens).toBe(1000);
      expect(record.costTotal).toBe(0.10935);
      expect(record.costInput).toBe(0.03);
      expect(record.costOutput).toBe(0.075);
      expect(record.costCacheRead).toBe(0.0006);
      expect(record.costCacheCreation).toBe(0.00375);
      expect(record.agentCount).toBe(3);
      expect(record.toolCalls).toBe(50);

      // Verify JSON serialization
      const models = JSON.parse(record.models);
      expect(models).toContain('claude-3-5-sonnet-20241022');
      expect(models).toContain('claude-3-5-haiku-20241022');
      expect(models.length).toBe(2);

      const toolUsage = JSON.parse(record.toolUsage);
      expect(toolUsage.Read).toBe(20);
      expect(toolUsage.Write).toBe(15);
      expect(toolUsage.Bash).toBe(15);
    });
  });

  describe('sessionRecordToMetrics', () => {
    it('should convert SessionRecord to SessionMetrics', () => {
      const record: SessionRecord = {
        id: 'test-session-456',
        projectPath: '/another/project',
        projectName: 'another-project',
        startedAt: '2024-01-16T09:00:00.000Z',
        endedAt: '2024-01-16T10:00:00.000Z',
        models: '["claude-opus-4-5-20251101"]',
        tokensIn: 20000,
        tokensOut: 8000,
        cacheReadTokens: 3000,
        cacheCreationTokens: 1500,
        costTotal: 0.50,
        costInput: 0.30,
        costOutput: 0.15,
        costCacheRead: 0.03,
        costCacheCreation: 0.02,
        agentCount: 5,
        toolCalls: 100,
        toolUsage: '{"Edit":40,"Grep":35,"Glob":25}',
      };

      const metrics = sessionRecordToMetrics(record);

      expect(metrics.sessionId).toBe('test-session-456');
      expect(metrics.projectPath).toBe('/another/project');
      expect(metrics.projectName).toBe('another-project');
      expect(metrics.startedAt).toEqual(new Date('2024-01-16T09:00:00.000Z'));
      expect(metrics.lastActivity).toEqual(new Date('2024-01-16T10:00:00.000Z'));
      expect(metrics.tokensIn).toBe(20000);
      expect(metrics.tokensOut).toBe(8000);
      expect(metrics.cacheReadTokens).toBe(3000);
      expect(metrics.cacheCreationTokens).toBe(1500);
      expect(metrics.cost.total).toBe(0.50);
      expect(metrics.cost.inputCost).toBe(0.30);
      expect(metrics.cost.outputCost).toBe(0.15);
      expect(metrics.cost.cacheReadCost).toBe(0.03);
      expect(metrics.cost.cacheCreationCost).toBe(0.02);
      expect(metrics.agentCount).toBe(5);
      expect(metrics.toolCalls).toBe(100);

      // Verify Set conversion
      expect(metrics.models).toBeInstanceOf(Set);
      expect(metrics.models.has('claude-opus-4-5-20251101')).toBe(true);
      expect(metrics.models.size).toBe(1);

      // Verify Map conversion
      expect(metrics.toolUsage).toBeInstanceOf(Map);
      expect(metrics.toolUsage.get('Edit')).toBe(40);
      expect(metrics.toolUsage.get('Grep')).toBe(35);
      expect(metrics.toolUsage.get('Glob')).toBe(25);
    });

    it('should handle null endedAt', () => {
      const record: SessionRecord = {
        id: 'test-session',
        projectPath: '/path',
        projectName: 'project',
        startedAt: '2024-01-16T09:00:00.000Z',
        endedAt: null,
        models: '[]',
        tokensIn: 0,
        tokensOut: 0,
        cacheReadTokens: 0,
        cacheCreationTokens: 0,
        costTotal: 0,
        costInput: 0,
        costOutput: 0,
        costCacheRead: 0,
        costCacheCreation: 0,
        agentCount: 0,
        toolCalls: 0,
        toolUsage: '{}',
      };

      const metrics = sessionRecordToMetrics(record);
      expect(metrics.lastActivity).toEqual(new Date('2024-01-16T09:00:00.000Z'));
    });

    it('should handle invalid JSON gracefully', () => {
      const record: SessionRecord = {
        id: 'test-session',
        projectPath: '/path',
        projectName: 'project',
        startedAt: '2024-01-16T09:00:00.000Z',
        endedAt: null,
        models: 'invalid json',
        tokensIn: 0,
        tokensOut: 0,
        cacheReadTokens: 0,
        cacheCreationTokens: 0,
        costTotal: 0,
        costInput: 0,
        costOutput: 0,
        costCacheRead: 0,
        costCacheCreation: 0,
        agentCount: 0,
        toolCalls: 0,
        toolUsage: 'also invalid',
      };

      const metrics = sessionRecordToMetrics(record);
      expect(metrics.models).toBeInstanceOf(Set);
      expect(metrics.models.size).toBe(0);
      expect(metrics.toolUsage).toBeInstanceOf(Map);
      expect(metrics.toolUsage.size).toBe(0);
    });
  });

  describe('agentMetricsToRecord', () => {
    it('should convert AgentMetrics to AgentRecord', () => {
      const metrics: AgentMetrics = {
        agentId: 'agent-123',
        sessionId: 'session-456',
        parentId: 'parent-789',
        agentType: 'code-analysis',
        model: 'claude-sonnet-4-20250514',
        startedAt: new Date('2024-01-15T10:30:00Z'),
        lastActivity: new Date('2024-01-15T10:45:00Z'),
        tokensIn: 5000,
        tokensOut: 2000,
        cacheReadTokens: 1000,
        cacheCreationTokens: 500,
        cost: {
          inputCost: 0.015,
          outputCost: 0.03,
          cacheReadCost: 0.0003,
          cacheCreationCost: 0.001875,
          total: 0.047175,
          model: 'claude-sonnet-4-20250514',
        },
        toolsUsed: new Set(['Read', 'Grep', 'Edit']),
        toolCalls: 25,
        entryCount: 30,
      };

      const record = agentMetricsToRecord(metrics);

      expect(record.id).toBe('agent-123');
      expect(record.sessionId).toBe('session-456');
      expect(record.parentId).toBe('parent-789');
      expect(record.agentType).toBe('code-analysis');
      expect(record.model).toBe('claude-sonnet-4-20250514');
      expect(record.startedAt).toBe('2024-01-15T10:30:00.000Z');
      expect(record.endedAt).toBe('2024-01-15T10:45:00.000Z');
      expect(record.tokensIn).toBe(5000);
      expect(record.tokensOut).toBe(2000);
      expect(record.cacheReadTokens).toBe(1000);
      expect(record.cacheCreationTokens).toBe(500);
      expect(record.costTotal).toBe(0.047175);
      expect(record.toolCalls).toBe(25);

      const toolsUsed = JSON.parse(record.toolsUsed);
      expect(toolsUsed).toContain('Read');
      expect(toolsUsed).toContain('Grep');
      expect(toolsUsed).toContain('Edit');
    });

    it('should handle undefined parentId', () => {
      const metrics: AgentMetrics = {
        agentId: 'agent-123',
        sessionId: 'session-456',
        parentId: undefined,
        agentType: 'code-analysis',
        model: 'claude-sonnet-4-20250514',
        startedAt: new Date('2024-01-15T10:30:00Z'),
        lastActivity: new Date('2024-01-15T10:45:00Z'),
        tokensIn: 0,
        tokensOut: 0,
        cacheReadTokens: 0,
        cacheCreationTokens: 0,
        cost: {
          inputCost: 0,
          outputCost: 0,
          cacheReadCost: 0,
          cacheCreationCost: 0,
          total: 0,
          model: 'claude-sonnet-4-20250514',
        },
        toolsUsed: new Set(),
        toolCalls: 0,
        entryCount: 0,
      };

      const record = agentMetricsToRecord(metrics);
      expect(record.parentId).toBeNull();
    });
  });

  describe('agentRecordToMetrics', () => {
    it('should convert AgentRecord to AgentMetrics', () => {
      const record: AgentRecord = {
        id: 'agent-789',
        sessionId: 'session-123',
        parentId: 'parent-456',
        agentType: 'test-runner',
        model: 'claude-haiku-4-5-20251001',
        startedAt: '2024-01-17T14:00:00.000Z',
        endedAt: '2024-01-17T14:30:00.000Z',
        tokensIn: 3000,
        tokensOut: 1500,
        cacheReadTokens: 500,
        cacheCreationTokens: 200,
        costTotal: 0.01,
        toolsUsed: '["Bash","Read"]',
        toolCalls: 10,
      };

      const metrics = agentRecordToMetrics(record);

      expect(metrics.agentId).toBe('agent-789');
      expect(metrics.sessionId).toBe('session-123');
      expect(metrics.parentId).toBe('parent-456');
      expect(metrics.agentType).toBe('test-runner');
      expect(metrics.model).toBe('claude-haiku-4-5-20251001');
      expect(metrics.startedAt).toEqual(new Date('2024-01-17T14:00:00.000Z'));
      expect(metrics.lastActivity).toEqual(new Date('2024-01-17T14:30:00.000Z'));
      expect(metrics.tokensIn).toBe(3000);
      expect(metrics.tokensOut).toBe(1500);
      expect(metrics.cacheReadTokens).toBe(500);
      expect(metrics.cacheCreationTokens).toBe(200);
      expect(metrics.cost.total).toBe(0.01);
      expect(metrics.toolCalls).toBe(10);

      expect(metrics.toolsUsed).toBeInstanceOf(Set);
      expect(metrics.toolsUsed.has('Bash')).toBe(true);
      expect(metrics.toolsUsed.has('Read')).toBe(true);
    });

    it('should handle null parentId', () => {
      const record: AgentRecord = {
        id: 'agent-789',
        sessionId: 'session-123',
        parentId: null,
        agentType: 'test-runner',
        model: 'claude-haiku-4-5-20251001',
        startedAt: '2024-01-17T14:00:00.000Z',
        endedAt: null,
        tokensIn: 0,
        tokensOut: 0,
        cacheReadTokens: 0,
        cacheCreationTokens: 0,
        costTotal: 0,
        toolsUsed: '[]',
        toolCalls: 0,
      };

      const metrics = agentRecordToMetrics(record);
      expect(metrics.parentId).toBeUndefined();
    });
  });

  describe('round-trip conversions', () => {
    it('should preserve data through session round-trip', () => {
      const original: SessionMetrics = {
        sessionId: 'round-trip-test',
        projectPath: '/test/path',
        projectName: 'round-trip',
        startedAt: new Date('2024-01-15T10:00:00Z'),
        lastActivity: new Date('2024-01-15T11:00:00Z'),
        tokensIn: 12345,
        tokensOut: 6789,
        cacheReadTokens: 1111,
        cacheCreationTokens: 2222,
        cost: {
          inputCost: 0.12345,
          outputCost: 0.67890,
          cacheReadCost: 0.01111,
          cacheCreationCost: 0.02222,
          total: 0.83568,
          model: 'test-model',
        },
        models: new Set(['model-a', 'model-b']),
        agentCount: 7,
        toolCalls: 42,
        toolUsage: new Map([['ToolA', 10], ['ToolB', 20], ['ToolC', 12]]),
        entryCount: 100,
        assistantEntries: 50,
      };

      const record = sessionMetricsToRecord(original);
      const restored = sessionRecordToMetrics(record);

      expect(restored.sessionId).toBe(original.sessionId);
      expect(restored.projectPath).toBe(original.projectPath);
      expect(restored.projectName).toBe(original.projectName);
      expect(restored.startedAt.getTime()).toBe(original.startedAt.getTime());
      expect(restored.lastActivity.getTime()).toBe(original.lastActivity.getTime());
      expect(restored.tokensIn).toBe(original.tokensIn);
      expect(restored.tokensOut).toBe(original.tokensOut);
      expect(restored.cacheReadTokens).toBe(original.cacheReadTokens);
      expect(restored.cacheCreationTokens).toBe(original.cacheCreationTokens);
      expect(restored.cost.total).toBe(original.cost.total);
      expect(restored.cost.inputCost).toBe(original.cost.inputCost);
      expect(restored.cost.outputCost).toBe(original.cost.outputCost);
      expect(restored.cost.cacheReadCost).toBe(original.cost.cacheReadCost);
      expect(restored.cost.cacheCreationCost).toBe(original.cost.cacheCreationCost);
      expect(restored.agentCount).toBe(original.agentCount);
      expect(restored.toolCalls).toBe(original.toolCalls);

      // Set comparison
      expect(restored.models.size).toBe(original.models.size);
      for (const model of original.models) {
        expect(restored.models.has(model)).toBe(true);
      }

      // Map comparison
      expect(restored.toolUsage.size).toBe(original.toolUsage.size);
      for (const [tool, count] of original.toolUsage) {
        expect(restored.toolUsage.get(tool)).toBe(count);
      }
    });

    it('should preserve data through agent round-trip', () => {
      const original: AgentMetrics = {
        agentId: 'agent-round-trip',
        sessionId: 'session-test',
        parentId: 'parent-test',
        agentType: 'round-trip-agent',
        model: 'test-model',
        startedAt: new Date('2024-01-15T10:00:00Z'),
        lastActivity: new Date('2024-01-15T10:30:00Z'),
        tokensIn: 5555,
        tokensOut: 3333,
        cacheReadTokens: 1111,
        cacheCreationTokens: 2222,
        cost: {
          inputCost: 0.1,
          outputCost: 0.2,
          cacheReadCost: 0.01,
          cacheCreationCost: 0.02,
          total: 0.33,
          model: 'test-model',
        },
        toolsUsed: new Set(['Tool1', 'Tool2', 'Tool3']),
        toolCalls: 15,
        entryCount: 20,
      };

      const record = agentMetricsToRecord(original);
      const restored = agentRecordToMetrics(record);

      expect(restored.agentId).toBe(original.agentId);
      expect(restored.sessionId).toBe(original.sessionId);
      expect(restored.parentId).toBe(original.parentId);
      expect(restored.agentType).toBe(original.agentType);
      expect(restored.model).toBe(original.model);
      expect(restored.startedAt.getTime()).toBe(original.startedAt.getTime());
      expect(restored.lastActivity.getTime()).toBe(original.lastActivity.getTime());
      expect(restored.tokensIn).toBe(original.tokensIn);
      expect(restored.tokensOut).toBe(original.tokensOut);
      expect(restored.cacheReadTokens).toBe(original.cacheReadTokens);
      expect(restored.cacheCreationTokens).toBe(original.cacheCreationTokens);
      expect(restored.cost.total).toBe(original.cost.total);
      expect(restored.toolCalls).toBe(original.toolCalls);

      // Set comparison
      expect(restored.toolsUsed.size).toBe(original.toolsUsed.size);
      for (const tool of original.toolsUsed) {
        expect(restored.toolsUsed.has(tool)).toBe(true);
      }
    });
  });

  describe('utility functions', () => {
    describe('parseModelsJson', () => {
      it('should parse valid JSON array', () => {
        const result = parseModelsJson('["model1","model2"]');
        expect(result).toBeInstanceOf(Set);
        expect(result.has('model1')).toBe(true);
        expect(result.has('model2')).toBe(true);
      });

      it('should return empty Set for invalid JSON', () => {
        const result = parseModelsJson('invalid');
        expect(result).toBeInstanceOf(Set);
        expect(result.size).toBe(0);
      });
    });

    describe('parseToolUsageJson', () => {
      it('should parse valid JSON object', () => {
        const result = parseToolUsageJson('{"Read":10,"Write":5}');
        expect(result).toBeInstanceOf(Map);
        expect(result.get('Read')).toBe(10);
        expect(result.get('Write')).toBe(5);
      });

      it('should return empty Map for invalid JSON', () => {
        const result = parseToolUsageJson('not json');
        expect(result).toBeInstanceOf(Map);
        expect(result.size).toBe(0);
      });
    });

    describe('parseToolsUsedJson', () => {
      it('should parse valid JSON array', () => {
        const result = parseToolsUsedJson('["Bash","Grep"]');
        expect(result).toBeInstanceOf(Set);
        expect(result.has('Bash')).toBe(true);
        expect(result.has('Grep')).toBe(true);
      });

      it('should return empty Set for invalid JSON', () => {
        const result = parseToolsUsedJson('bad json');
        expect(result).toBeInstanceOf(Set);
        expect(result.size).toBe(0);
      });
    });

    describe('serializeSetToJson', () => {
      it('should serialize Set to JSON array', () => {
        const set = new Set(['a', 'b', 'c']);
        const json = serializeSetToJson(set);
        const parsed = JSON.parse(json);
        expect(parsed).toContain('a');
        expect(parsed).toContain('b');
        expect(parsed).toContain('c');
      });
    });

    describe('serializeMapToJson', () => {
      it('should serialize Map to JSON object', () => {
        const map = new Map<string, number>([['x', 1], ['y', 2]]);
        const json = serializeMapToJson(map);
        const parsed = JSON.parse(json);
        expect(parsed.x).toBe(1);
        expect(parsed.y).toBe(2);
      });
    });

    describe('reconstructCostBreakdown', () => {
      it('should create CostBreakdown from columns', () => {
        const cost = reconstructCostBreakdown(0.5, 0.2, 0.15, 0.1, 0.05, 'test-model');
        expect(cost.total).toBe(0.5);
        expect(cost.inputCost).toBe(0.2);
        expect(cost.outputCost).toBe(0.15);
        expect(cost.cacheReadCost).toBe(0.1);
        expect(cost.cacheCreationCost).toBe(0.05);
        expect(cost.model).toBe('test-model');
      });

      it('should use default model if not provided', () => {
        const cost = reconstructCostBreakdown(0.5, 0.2, 0.15, 0.1, 0.05);
        expect(cost.model).toBe('mixed');
      });
    });

    describe('extractCostColumns', () => {
      it('should extract columns from CostBreakdown', () => {
        const cost: CostBreakdown = {
          total: 0.5,
          inputCost: 0.2,
          outputCost: 0.15,
          cacheReadCost: 0.1,
          cacheCreationCost: 0.05,
          model: 'test',
        };
        const columns = extractCostColumns(cost);
        expect(columns.costTotal).toBe(0.5);
        expect(columns.costInput).toBe(0.2);
        expect(columns.costOutput).toBe(0.15);
        expect(columns.costCacheRead).toBe(0.1);
        expect(columns.costCacheCreation).toBe(0.05);
      });
    });
  });
});
