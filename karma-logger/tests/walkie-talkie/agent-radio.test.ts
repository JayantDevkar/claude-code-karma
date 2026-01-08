/**
 * Agent Radio unit tests
 * Phase 2: Agent communication and status management
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MemoryCacheStore } from '../../src/walkie-talkie/cache-store.js';
import { AgentRadioImpl } from '../../src/walkie-talkie/agent-radio.js';
import type { AgentRadio, AgentStatus } from '../../src/walkie-talkie/types.js';

describe('AgentRadioImpl', () => {
  let cache: MemoryCacheStore;
  let agent: AgentRadioImpl;

  beforeEach(() => {
    vi.useFakeTimers();
    cache = new MemoryCacheStore();
    agent = new AgentRadioImpl(
      cache,
      'agent-1',
      'session-1',
      'root-session-1',
      null,
      'session',
      'test-agent',
      'claude-sonnet-4',
    );
  });

  afterEach(() => {
    agent.destroy();
    cache.destroy();
    vi.useRealTimers();
  });

  // ============================================
  // Status Management
  // ============================================

  describe('status management', () => {
    it('sets initial pending status on creation', () => {
      const status = agent.getStatus();
      expect(status.state).toBe('pending');
      expect(status.agentId).toBe('agent-1');
      expect(status.sessionId).toBe('session-1');
      expect(status.rootSessionId).toBe('root-session-1');
      expect(status.parentId).toBeNull();
      expect(status.parentType).toBe('session');
      expect(status.agentType).toBe('test-agent');
      expect(status.model).toBe('claude-sonnet-4');
    });

    it('updates status preserving startedAt', () => {
      const initialStatus = agent.getStatus();
      const startedAt = initialStatus.startedAt;

      vi.advanceTimersByTime(1000);
      agent.setStatus('active');

      const updatedStatus = agent.getStatus();
      expect(updatedStatus.startedAt).toBe(startedAt);
      expect(updatedStatus.updatedAt).not.toBe(startedAt);
      expect(updatedStatus.state).toBe('active');
    });

    it('getStatus returns current state', () => {
      agent.setStatus('active');
      expect(agent.getStatus().state).toBe('active');

      agent.setStatus('completed');
      expect(agent.getStatus().state).toBe('completed');
    });

    it('transitions through full lifecycle', () => {
      expect(agent.getStatus().state).toBe('pending');

      agent.setStatus('active');
      expect(agent.getStatus().state).toBe('active');

      agent.setStatus('waiting');
      expect(agent.getStatus().state).toBe('waiting');

      agent.setStatus('completed');
      expect(agent.getStatus().state).toBe('completed');
    });

    it('merges metadata across updates', () => {
      agent.setStatus('active', { phase: 1, tool: 'Read' });
      agent.setStatus('active', { progress: 50 });

      const status = agent.getStatus();
      expect(status.metadata).toEqual({
        phase: 1,
        tool: 'Read',
        progress: 50,
      });
    });

    it('registers in session agent list', () => {
      const sessionAgents = cache.get<string[]>('session:root-session-1:agents');
      expect(sessionAgents).toContain('agent-1');
    });
  });

  // ============================================
  // Progress
  // ============================================

  describe('progress', () => {
    it('reportProgress writes timestamped update', () => {
      agent.reportProgress({ tool: 'Read', step: 'Reading file', percent: 50 });

      const progress = cache.get('agent:agent-1:progress');
      expect(progress).toEqual({
        tool: 'Read',
        step: 'Reading file',
        percent: 50,
      });
    });

    it('progress has short TTL (1 minute)', () => {
      agent.reportProgress({ percent: 75 });

      vi.advanceTimersByTime(59999);
      expect(cache.get('agent:agent-1:progress')).not.toBeNull();

      vi.advanceTimersByTime(2);
      expect(cache.get('agent:agent-1:progress')).toBeNull();
    });
  });

  // ============================================
  // Full Status (Status + Progress)
  // ============================================

  describe('getFullStatus', () => {
    it('returns status only when no progress reported', () => {
      agent.setStatus('active');

      const fullStatus = agent.getFullStatus();
      expect(fullStatus.state).toBe('active');
      expect(fullStatus.agentId).toBe('agent-1');
      expect(fullStatus.progress).toBeUndefined();
    });

    it('includes progress when progress has been reported', () => {
      agent.setStatus('active');
      agent.reportProgress({ tool: 'Bash', percent: 50, message: 'Running tests...' });

      const fullStatus = agent.getFullStatus();
      expect(fullStatus.state).toBe('active');
      expect(fullStatus.progress).toEqual({
        tool: 'Bash',
        percent: 50,
        message: 'Running tests...',
      });
    });

    it('returns latest progress update', () => {
      agent.setStatus('active');
      agent.reportProgress({ tool: 'Read', percent: 25 });
      agent.reportProgress({ tool: 'Edit', percent: 75, message: 'Almost done' });

      const fullStatus = agent.getFullStatus();
      expect(fullStatus.progress).toEqual({
        tool: 'Edit',
        percent: 75,
        message: 'Almost done',
      });
    });

    it('progress becomes undefined after TTL expires', () => {
      agent.setStatus('active');
      agent.reportProgress({ percent: 50 });

      expect(agent.getFullStatus().progress).not.toBeUndefined();

      vi.advanceTimersByTime(60001);

      expect(agent.getFullStatus().progress).toBeUndefined();
      expect(agent.getFullStatus().state).toBe('active');
    });
  });

  // ============================================
  // Results
  // ============================================

  describe('results', () => {
    it('publishResult stores data', () => {
      const result = { data: 'test', count: 42 };
      agent.publishResult(result);

      const published = cache.get('agent:agent-1:result');
      expect(published).toEqual(result);
    });

    it('result expires after 10 minutes', () => {
      agent.publishResult({ value: 'test' });

      vi.advanceTimersByTime(599999);
      expect(cache.get('agent:agent-1:result')).not.toBeNull();

      vi.advanceTimersByTime(2);
      expect(cache.get('agent:agent-1:result')).toBeNull();
    });
  });

  // ============================================
  // Parent-Child Relationships
  // ============================================

  describe('parent-child relationships', () => {
    it('registers in session agent list', () => {
      const agents = cache.get<string[]>('session:root-session-1:agents');
      expect(agents).toContain('agent-1');
    });

    it('getChildStatuses returns only children', () => {
      const child1 = new AgentRadioImpl(
        cache, 'child-1', 'session-c1', 'root-session-1',
        'agent-1', 'agent', 'child-agent', 'claude-sonnet-4',
      );
      const child2 = new AgentRadioImpl(
        cache, 'child-2', 'session-c2', 'root-session-1',
        'agent-1', 'agent', 'child-agent', 'claude-sonnet-4',
      );
      const other = new AgentRadioImpl(
        cache, 'other-1', 'session-o1', 'root-session-1',
        null, 'session', 'other-agent', 'claude-sonnet-4',
      );

      child1.setStatus('active');
      child2.setStatus('completed');
      other.setStatus('active');

      const children = agent.getChildStatuses();
      expect(children.size).toBe(2);
      expect(children.get('child-1')?.state).toBe('active');
      expect(children.get('child-2')?.state).toBe('completed');
      expect(children.has('other-1')).toBe(false);

      child1.destroy();
      child2.destroy();
      other.destroy();
    });

    it('onChildStatus fires for child updates only', () => {
      const callback = vi.fn();
      agent.onChildStatus(callback);

      const child = new AgentRadioImpl(
        cache, 'child-1', 'session-c1', 'root-session-1',
        'agent-1', 'agent', 'child-agent', 'claude-sonnet-4',
      );
      const other = new AgentRadioImpl(
        cache, 'other-1', 'session-o1', 'root-session-1',
        'different-parent', 'agent', 'other-agent', 'claude-sonnet-4',
      );

      // Child's initial pending status fires callback
      expect(callback).toHaveBeenCalledWith('child-1', expect.objectContaining({
        agentId: 'child-1',
        state: 'pending',
        parentId: 'agent-1',
      }));

      callback.mockClear();
      child.setStatus('active');
      expect(callback).toHaveBeenCalledWith('child-1', expect.objectContaining({
        state: 'active',
      }));

      callback.mockClear();
      other.setStatus('active');
      expect(callback).not.toHaveBeenCalled();

      child.destroy();
      other.destroy();
    });

    it('getParentStatus returns parent agent status', () => {
      const parent = new AgentRadioImpl(
        cache, 'parent-1', 'session-p1', 'root-session-1',
        null, 'session', 'parent-agent', 'claude-sonnet-4',
      );
      const child = new AgentRadioImpl(
        cache, 'child-1', 'session-c1', 'root-session-1',
        'parent-1', 'agent', 'child-agent', 'claude-sonnet-4',
      );

      parent.setStatus('active', { phase: 'running' });

      const parentStatus = child.getParentStatus();
      expect(parentStatus?.agentId).toBe('parent-1');
      expect(parentStatus?.state).toBe('active');
      expect(parentStatus?.metadata.phase).toBe('running');

      parent.destroy();
      child.destroy();
    });

    it('getParentStatus returns null for session parent', () => {
      expect(agent.getParentStatus()).toBeNull();
    });
  });

  // ============================================
  // Sibling Awareness
  // ============================================

  describe('sibling awareness', () => {
    it('getSiblingStatuses excludes self', () => {
      const sibling1 = new AgentRadioImpl(
        cache, 'sibling-1', 'session-s1', 'root-session-1',
        null, 'session', 'sibling-agent', 'claude-sonnet-4',
      );
      const sibling2 = new AgentRadioImpl(
        cache, 'sibling-2', 'session-s2', 'root-session-1',
        null, 'session', 'sibling-agent', 'claude-sonnet-4',
      );

      sibling1.setStatus('active');
      sibling2.setStatus('waiting');

      const siblings = agent.getSiblingStatuses();
      expect(siblings.size).toBe(2);
      expect(siblings.get('sibling-1')?.state).toBe('active');
      expect(siblings.get('sibling-2')?.state).toBe('waiting');
      expect(siblings.has('agent-1')).toBe(false);

      sibling1.destroy();
      sibling2.destroy();
    });

    it('onSiblingStatus fires for siblings only', () => {
      const callback = vi.fn();
      agent.onSiblingStatus(callback);

      const sibling = new AgentRadioImpl(
        cache, 'sibling-1', 'session-s1', 'root-session-1',
        null, 'session', 'sibling-agent', 'claude-sonnet-4',
      );

      // Sibling's initial pending fires callback
      expect(callback).toHaveBeenCalledWith('sibling-1', expect.objectContaining({
        agentId: 'sibling-1',
        state: 'pending',
      }));

      callback.mockClear();
      sibling.setStatus('active');
      expect(callback).toHaveBeenCalledWith('sibling-1', expect.objectContaining({
        state: 'active',
      }));

      sibling.destroy();
    });

    it('onSiblingStatus does not fire for self', () => {
      const callback = vi.fn();
      agent.onSiblingStatus(callback);

      agent.setStatus('active');
      expect(callback).not.toHaveBeenCalled();
    });
  });

  // ============================================
  // waitForAgent
  // ============================================

  describe('waitForAgent', () => {
    it('resolves immediately if state matches', async () => {
      const agent2 = new AgentRadioImpl(
        cache, 'agent-2', 'session-2', 'root-session-1',
        null, 'session', 'test-agent', 'claude-sonnet-4',
      );
      agent2.setStatus('completed');

      const status = await agent.waitForAgent('agent-2', 'completed', 1000);
      expect(status.state).toBe('completed');
      expect(status.agentId).toBe('agent-2');

      agent2.destroy();
    });

    it('resolves when state changes', async () => {
      const agent2 = new AgentRadioImpl(
        cache, 'agent-2', 'session-2', 'root-session-1',
        null, 'session', 'test-agent', 'claude-sonnet-4',
      );

      const waitPromise = agent.waitForAgent('agent-2', 'completed', 5000);

      setTimeout(() => {
        agent2.setStatus('active');
      }, 100);
      setTimeout(() => {
        agent2.setStatus('completed');
      }, 200);

      vi.advanceTimersByTime(200);

      const status = await waitPromise;
      expect(status.state).toBe('completed');

      agent2.destroy();
    });

    it('rejects on timeout', async () => {
      const agent2 = new AgentRadioImpl(
        cache, 'agent-2', 'session-2', 'root-session-1',
        null, 'session', 'test-agent', 'claude-sonnet-4',
      );

      const waitPromise = agent.waitForAgent('agent-2', 'completed', 1000);

      vi.advanceTimersByTime(1001);

      await expect(waitPromise).rejects.toThrow(
        'Timeout waiting for agent agent-2 to reach state completed',
      );

      agent2.destroy();
    });

    it('uses default timeout of 30 seconds', async () => {
      const agent2 = new AgentRadioImpl(
        cache, 'agent-2', 'session-2', 'root-session-1',
        null, 'session', 'test-agent', 'claude-sonnet-4',
      );

      const waitPromise = agent.waitForAgent('agent-2', 'completed');

      vi.advanceTimersByTime(30001);

      await expect(waitPromise).rejects.toThrow('Timeout');

      agent2.destroy();
    });
  });

  // ============================================
  // Messaging
  // ============================================

  describe('messaging', () => {
    it('send appends to target inbox', () => {
      agent.send('agent-2', { type: 'request', data: 'test' });

      const inbox = cache.get<any[]>('agent:agent-2:inbox');
      expect(inbox).toHaveLength(1);
      expect(inbox![0].fromAgentId).toBe('agent-1');
      expect(inbox![0].message).toEqual({ type: 'request', data: 'test' });
      expect(inbox![0].timestamp).toBeTruthy();
    });

    it('onMessage receives new messages', () => {
      const callback = vi.fn();
      agent.onMessage(callback);

      const agent2 = new AgentRadioImpl(
        cache, 'agent-2', 'session-2', 'root-session-1',
        null, 'session', 'test-agent', 'claude-sonnet-4',
      );

      agent2.send('agent-1', { hello: 'world' });

      expect(callback).toHaveBeenCalledWith('agent-2', { hello: 'world' });

      agent2.destroy();
    });

    it('message has from/timestamp metadata', () => {
      agent.send('agent-2', 'test-message');

      const inbox = cache.get<any[]>('agent:agent-2:inbox');
      expect(inbox![0]).toHaveProperty('fromAgentId', 'agent-1');
      expect(inbox![0]).toHaveProperty('timestamp');
      expect(inbox![0]).toHaveProperty('message', 'test-message');
    });

    it('inbox expires after 5 minutes', () => {
      agent.send('agent-2', 'test');

      vi.advanceTimersByTime(299999);
      expect(cache.get('agent:agent-2:inbox')).not.toBeNull();

      vi.advanceTimersByTime(2);
      expect(cache.get('agent:agent-2:inbox')).toBeNull();
    });
  });

  // ============================================
  // Cleanup
  // ============================================

  describe('cleanup', () => {
    it('destroy removes all subscriptions', () => {
      const callback = vi.fn();
      agent.onChildStatus(callback);

      const child = new AgentRadioImpl(
        cache, 'child-1', 'session-c1', 'root-session-1',
        'agent-1', 'agent', 'child-agent', 'claude-sonnet-4',
      );

      // Initial status triggers callback
      expect(callback).toHaveBeenCalledTimes(1);

      callback.mockClear();
      agent.destroy();

      child.setStatus('active');
      expect(callback).not.toHaveBeenCalled();

      child.destroy();
    });

    it('destroy cleans up agent data', () => {
      agent.setStatus('active');
      agent.reportProgress({ percent: 50 });
      agent.publishResult({ value: 'test' });

      agent.destroy();

      expect(cache.get('agent:agent-1:status')).toBeNull();
      expect(cache.get('agent:agent-1:progress')).toBeNull();
      expect(cache.get('agent:agent-1:result')).toBeNull();
    });
  });
});

// ============================================
// Interface Compliance
// ============================================

describe('AgentRadio interface compliance', () => {
  it('AgentRadioImpl implements AgentRadio interface', () => {
    const cache = new MemoryCacheStore();
    const agentRadio: AgentRadio = new AgentRadioImpl(
      cache, 'test-agent', 'test-session', 'root-session',
      null, 'session', 'test-type', 'claude-sonnet-4',
    );

    // Verify all interface properties and methods exist
    expect(agentRadio.agentId).toBe('test-agent');
    expect(agentRadio.sessionId).toBe('test-session');
    expect(agentRadio.parentId).toBeNull();
    expect(typeof agentRadio.setStatus).toBe('function');
    expect(typeof agentRadio.getStatus).toBe('function');
    expect(typeof agentRadio.getFullStatus).toBe('function');
    expect(typeof agentRadio.reportProgress).toBe('function');
    expect(typeof agentRadio.publishResult).toBe('function');
    expect(typeof agentRadio.onAgentStatus).toBe('function');
    expect(typeof agentRadio.onChildStatus).toBe('function');
    expect(typeof agentRadio.onSiblingStatus).toBe('function');
    expect(typeof agentRadio.getParentStatus).toBe('function');
    expect(typeof agentRadio.getChildStatuses).toBe('function');
    expect(typeof agentRadio.getSiblingStatuses).toBe('function');
    expect(typeof agentRadio.waitForAgent).toBe('function');
    expect(typeof agentRadio.send).toBe('function');
    expect(typeof agentRadio.onMessage).toBe('function');
    expect(typeof agentRadio.destroy).toBe('function');

    agentRadio.destroy();
    cache.destroy();
  });
});
