/**
 * Integration Tests for Walkie-Talkie Phase 5
 * Tests aggregator + radio integration, socket server, and dashboard API
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as net from 'node:net';
import * as fs from 'node:fs';
import { MetricsAggregator } from '../../src/aggregator.js';
import { MemoryCacheStore } from '../../src/walkie-talkie/cache-store.js';
import { AgentRadioImpl } from '../../src/walkie-talkie/agent-radio.js';
import {
  startRadioServer,
  handleRadioRequest,
  getDefaultRadioSocketPath,
} from '../../src/walkie-talkie/socket-server.js';
import type { RadioRequest, RadioResponse, AgentStatus } from '../../src/walkie-talkie/types.js';
import type { SessionInfo } from '../../src/discovery.js';

// ============================================
// Aggregator + Radio Integration Tests
// ============================================

describe('Aggregator + Radio Integration', () => {
  let aggregator: MetricsAggregator;

  beforeEach(() => {
    vi.useFakeTimers();
    aggregator = new MetricsAggregator({ enableRadio: true });
  });

  afterEach(() => {
    aggregator.destroy();
    vi.useRealTimers();
  });

  describe('registerAgent creates radio instance', () => {
    it('creates radio instance when radio is enabled', () => {
      const agent: SessionInfo = {
        sessionId: 'agent-1',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: true,
        parentSessionId: 'parent-session',
        agentType: 'task',
        model: 'claude-sonnet-4',
        logFile: '/test/log.jsonl',
      };

      const parent: SessionInfo = {
        sessionId: 'parent-session',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: false,
        logFile: '/test/parent-log.jsonl',
      };

      aggregator.registerAgent(agent, parent);

      const radio = aggregator.getAgentRadio('agent-1');
      expect(radio).not.toBeNull();
      expect(radio?.agentId).toBe('agent-1');
    });

    it('sets radio status to active on registration', () => {
      const agent: SessionInfo = {
        sessionId: 'agent-1',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: true,
        parentSessionId: 'parent-session',
        agentType: 'task',
        model: 'claude-sonnet-4',
        logFile: '/test/log.jsonl',
      };

      const parent: SessionInfo = {
        sessionId: 'parent-session',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: false,
        logFile: '/test/parent-log.jsonl',
      };

      aggregator.registerAgent(agent, parent);

      const status = aggregator.getAgentStatus('agent-1');
      expect(status?.state).toBe('active');
    });

    it('does not create radio instance when radio is disabled', () => {
      const noRadioAggregator = new MetricsAggregator({ enableRadio: false });

      const agent: SessionInfo = {
        sessionId: 'agent-1',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: true,
        parentSessionId: 'parent-session',
        agentType: 'task',
        logFile: '/test/log.jsonl',
      };

      const parent: SessionInfo = {
        sessionId: 'parent-session',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: false,
        logFile: '/test/parent-log.jsonl',
      };

      noRadioAggregator.registerAgent(agent, parent);

      expect(noRadioAggregator.getAgentRadio('agent-1')).toBeNull();
      expect(noRadioAggregator.isRadioEnabled()).toBe(false);

      noRadioAggregator.destroy();
    });
  });

  describe('getAgentStatus returns from cache', () => {
    it('returns status from cache', () => {
      const cache = aggregator.getCache();
      expect(cache).not.toBeNull();

      // Manually set a status in cache
      const mockStatus: AgentStatus = {
        agentId: 'test-agent',
        sessionId: 'test-session',
        rootSessionId: 'root-session',
        state: 'active',
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        parentId: null,
        parentType: 'session',
        agentType: 'task',
        model: 'claude-sonnet-4',
        metadata: {},
      };

      cache!.set('agent:test-agent:status', mockStatus);

      const retrieved = aggregator.getAgentStatus('test-agent');
      expect(retrieved).toEqual(mockStatus);
    });

    it('returns null for non-existent agent', () => {
      const status = aggregator.getAgentStatus('non-existent');
      expect(status).toBeNull();
    });
  });

  describe('getAgentStatuses returns all statuses', () => {
    it('returns map of all agent statuses', () => {
      const cache = aggregator.getCache()!;

      const status1: AgentStatus = {
        agentId: 'agent-1',
        sessionId: 'session-1',
        rootSessionId: 'root-session',
        state: 'active',
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        parentId: null,
        parentType: 'session',
        agentType: 'task',
        model: 'claude-sonnet-4',
        metadata: {},
      };

      const status2: AgentStatus = {
        agentId: 'agent-2',
        sessionId: 'session-2',
        rootSessionId: 'root-session',
        state: 'completed',
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        parentId: null,
        parentType: 'session',
        agentType: 'task',
        model: 'claude-sonnet-4',
        metadata: {},
      };

      cache.set('agent:agent-1:status', status1);
      cache.set('agent:agent-2:status', status2);

      const statuses = aggregator.getAgentStatuses();
      expect(statuses.size).toBe(2);
      expect(statuses.get('agent-1')?.state).toBe('active');
      expect(statuses.get('agent-2')?.state).toBe('completed');
    });

    it('returns empty map when no agents', () => {
      const statuses = aggregator.getAgentStatuses();
      expect(statuses.size).toBe(0);
    });
  });

  describe('onAgentStatusChange fires on updates', () => {
    it('calls callback when status changes', () => {
      const callback = vi.fn();
      aggregator.onAgentStatusChange(callback);

      const cache = aggregator.getCache()!;
      const status: AgentStatus = {
        agentId: 'test-agent',
        sessionId: 'test-session',
        rootSessionId: 'root-session',
        state: 'active',
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        parentId: null,
        parentType: 'session',
        agentType: 'task',
        model: 'claude-sonnet-4',
        metadata: {},
      };

      cache.set('agent:test-agent:status', status);

      expect(callback).toHaveBeenCalledWith('test-agent', status);
    });

    it('returns unsubscribe function', () => {
      const callback = vi.fn();
      const unsub = aggregator.onAgentStatusChange(callback);

      unsub();

      const cache = aggregator.getCache()!;
      cache.set('agent:test-agent:status', { state: 'active' });

      expect(callback).not.toHaveBeenCalled();
    });
  });

  describe('destroy cleans up radios and cache', () => {
    it('destroys all radio instances', () => {
      const agent: SessionInfo = {
        sessionId: 'agent-1',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: true,
        parentSessionId: 'parent-session',
        agentType: 'task',
        logFile: '/test/log.jsonl',
      };

      const parent: SessionInfo = {
        sessionId: 'parent-session',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: false,
        logFile: '/test/parent-log.jsonl',
      };

      aggregator.registerAgent(agent, parent);

      const radioBefore = aggregator.getAgentRadio('agent-1');
      expect(radioBefore).not.toBeNull();

      aggregator.destroy();

      // After destroy, methods should return null/empty
      expect(aggregator.getAgentRadio('agent-1')).toBeNull();
      expect(aggregator.getCache()).toBeNull();
      expect(aggregator.isRadioEnabled()).toBe(false);
    });

    it('clears all data', () => {
      aggregator.destroy();

      expect(aggregator.getAllSessions().length).toBe(0);
      expect(aggregator.getAgentStatuses().size).toBe(0);
    });
  });

  describe('clearEndedSessions cleans up radios', () => {
    it('removes radios for agents in ended sessions', () => {
      const agent: SessionInfo = {
        sessionId: 'agent-1',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: true,
        parentSessionId: 'parent-session',
        agentType: 'task',
        logFile: '/test/log.jsonl',
      };

      const parent: SessionInfo = {
        sessionId: 'parent-session',
        projectPath: '/test/project',
        projectName: 'test-project',
        isAgent: false,
        logFile: '/test/parent-log.jsonl',
      };

      aggregator.registerAgent(agent, parent);

      // Get parent session and end it
      const sessions = aggregator.getAllSessions();
      expect(sessions.length).toBe(1);

      aggregator.endSession('parent-session');
      const clearedCount = aggregator.clearEndedSessions();

      expect(clearedCount).toBe(1);
      expect(aggregator.getAgentRadio('agent-1')).toBeNull();
    });
  });
});

// ============================================
// Socket Server Tests
// ============================================

describe('Socket Server', () => {
  let aggregator: MetricsAggregator;

  beforeEach(() => {
    aggregator = new MetricsAggregator({ enableRadio: true });
  });

  afterEach(() => {
    aggregator.destroy();
  });

  describe('handleRadioRequest', () => {
    it('handles set-status command', () => {
      const request: RadioRequest = {
        id: 'req-1',
        command: 'set-status',
        args: { state: 'active', metadata: { tool: 'Read' } },
        env: {
          agentId: 'agent-1',
          sessionId: 'session-1',
          agentType: 'task',
          model: 'claude-sonnet-4',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(true);
      expect(response.id).toBe('req-1');

      // Check status was set
      const status = aggregator.getAgentStatus('agent-1');
      expect(status?.state).toBe('active');
    });

    it('handles get-status command', () => {
      // First set a status
      const cache = aggregator.getCache()!;
      const mockStatus: AgentStatus = {
        agentId: 'agent-1',
        sessionId: 'session-1',
        rootSessionId: 'session-1',
        state: 'active',
        startedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        parentId: null,
        parentType: 'session',
        agentType: 'task',
        model: 'claude-sonnet-4',
        metadata: {},
      };
      cache.set('agent:agent-1:status', mockStatus);

      const request: RadioRequest = {
        id: 'req-2',
        command: 'get-status',
        args: { agentId: 'agent-1' },
        env: {
          agentId: 'requester',
          sessionId: 'session-1',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(true);
      expect((response.data as AgentStatus).state).toBe('active');
    });

    it('handles report-progress command', () => {
      const request: RadioRequest = {
        id: 'req-3',
        command: 'report-progress',
        args: { tool: 'Read', step: 'Reading file', percent: 50 },
        env: {
          agentId: 'agent-1',
          sessionId: 'session-1',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(true);

      // Check progress was set
      const cache = aggregator.getCache()!;
      const progress = cache.get('agent:agent-1:progress');
      expect(progress).toEqual({
        tool: 'Read',
        step: 'Reading file',
        percent: 50,
      });
    });

    it('handles publish-result command', () => {
      const request: RadioRequest = {
        id: 'req-4',
        command: 'publish-result',
        args: { result: { success: true, data: 'test' } },
        env: {
          agentId: 'agent-1',
          sessionId: 'session-1',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(true);

      // Check result was published
      const cache = aggregator.getCache()!;
      const result = cache.get('agent:agent-1:result');
      expect(result).toEqual({ success: true, data: 'test' });
    });

    it('handles send command', () => {
      const request: RadioRequest = {
        id: 'req-5',
        command: 'send',
        args: { targetAgentId: 'agent-2', message: { type: 'hello' } },
        env: {
          agentId: 'agent-1',
          sessionId: 'session-1',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(true);

      // Check message was sent to inbox
      const cache = aggregator.getCache()!;
      const inbox = cache.get<any[]>('agent:agent-2:inbox');
      expect(inbox).toHaveLength(1);
      expect(inbox![0].fromAgentId).toBe('agent-1');
    });

    it('handles listen command', () => {
      // Set up inbox
      const cache = aggregator.getCache()!;
      cache.set('agent:agent-1:inbox', [
        { fromAgentId: 'agent-2', message: { type: 'hello' }, timestamp: new Date().toISOString() },
      ]);

      const request: RadioRequest = {
        id: 'req-6',
        command: 'listen',
        args: {},
        env: {
          agentId: 'agent-1',
          sessionId: 'session-1',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(true);
      expect(Array.isArray(response.data)).toBe(true);
      expect((response.data as any[]).length).toBe(1);
    });

    it('returns error for unknown command', () => {
      const request: RadioRequest = {
        id: 'req-7',
        command: 'unknown' as any,
        args: {},
        env: {
          agentId: 'agent-1',
          sessionId: 'session-1',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(false);
      expect(response.error).toContain('Unknown command');
    });

    it('returns error when radio not enabled', () => {
      const noRadioAggregator = new MetricsAggregator({ enableRadio: false });

      const request: RadioRequest = {
        id: 'req-8',
        command: 'set-status',
        args: { state: 'active' },
        env: {
          agentId: 'agent-1',
          sessionId: 'session-1',
        },
      };

      const response = handleRadioRequest(request, noRadioAggregator);

      expect(response.success).toBe(false);
      expect(response.error).toBe('Radio not enabled');

      noRadioAggregator.destroy();
    });

    it('returns error for missing required env fields', () => {
      const request: RadioRequest = {
        id: 'req-9',
        command: 'set-status',
        args: { state: 'active' },
        env: {
          agentId: '',
          sessionId: '',
        },
      };

      const response = handleRadioRequest(request, aggregator);

      expect(response.success).toBe(false);
      expect(response.error).toContain('Missing required env');
    });
  });

  describe('getDefaultRadioSocketPath', () => {
    it('returns default socket path', () => {
      const path = getDefaultRadioSocketPath();
      expect(path).toBe('/tmp/karma-radio.sock');
    });
  });
});

// ============================================
// Dashboard Radio API Tests (unit-level)
// ============================================

describe('Dashboard Radio API Integration', () => {
  let aggregator: MetricsAggregator;

  beforeEach(() => {
    aggregator = new MetricsAggregator({ enableRadio: true });
  });

  afterEach(() => {
    aggregator.destroy();
  });

  it('getAgentStatuses returns statuses for API', () => {
    const cache = aggregator.getCache()!;

    const status: AgentStatus = {
      agentId: 'api-test-agent',
      sessionId: 'api-test-session',
      rootSessionId: 'api-test-session',
      state: 'active',
      startedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      parentId: null,
      parentType: 'session',
      agentType: 'task',
      model: 'claude-sonnet-4',
      metadata: {},
    };

    cache.set('agent:api-test-agent:status', status);

    const statuses = aggregator.getAgentStatuses();
    expect(Object.fromEntries(statuses)).toEqual({
      'api-test-agent': status,
    });
  });

  it('getCache returns cache for tree building', () => {
    const cache = aggregator.getCache();
    expect(cache).not.toBeNull();

    // Set up session agents
    cache!.set('session:test-session:agents', ['agent-1', 'agent-2']);

    const agents = cache!.get<string[]>('session:test-session:agents');
    expect(agents).toEqual(['agent-1', 'agent-2']);
  });
});
