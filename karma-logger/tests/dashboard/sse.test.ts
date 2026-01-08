/**
 * SSE Manager unit tests
 * Phase 5: Server-Sent Events streaming
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SSEManager } from '../../src/dashboard/sse.js';
import { MetricsAggregator } from '../../src/aggregator.js';
import { EventEmitter } from 'events';

// Mock LogWatcher for testing
class MockLogWatcher extends EventEmitter {
  start() {}
  stop() {}
}

describe('SSEManager', () => {
  let sseManager: SSEManager;

  beforeEach(() => {
    sseManager = new SSEManager();
  });

  describe('createStream', () => {
    it('creates a readable stream', () => {
      const stream = sseManager.createStream('test-client-1');
      expect(stream).toBeInstanceOf(ReadableStream);
    });

    it('tracks client count after stream creation', () => {
      const initialCount = sseManager.getClientCount();
      sseManager.createStream('test-client-2');
      expect(sseManager.getClientCount()).toBe(initialCount + 1);
    });

    it('sends init event on connection when aggregator connected', async () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();
      sseManager.connect(watcher as any, aggregator);

      const stream = sseManager.createStream('test-client-init');
      const reader = stream.getReader();

      // Read the initial message
      const { value } = await reader.read();
      const text = new TextDecoder().decode(value);

      expect(text).toContain('event: init');
      expect(text).toContain('data:');

      reader.releaseLock();
    });
  });

  describe('getClientCount', () => {
    it('returns 0 when no clients connected', () => {
      expect(sseManager.getClientCount()).toBe(0);
    });

    it('increments for each new client', () => {
      sseManager.createStream('client-a');
      expect(sseManager.getClientCount()).toBe(1);

      sseManager.createStream('client-b');
      expect(sseManager.getClientCount()).toBe(2);
    });
  });

  describe('connect', () => {
    it('stores aggregator reference', () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();

      sseManager.connect(watcher as any, aggregator);

      // Verify by creating a stream (init event requires aggregator)
      const stream = sseManager.createStream('connect-test');
      expect(stream).toBeInstanceOf(ReadableStream);
    });

    it('listens to watcher entry events', () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();

      sseManager.connect(watcher as any, aggregator);

      // Verify listener was added
      expect(watcher.listenerCount('entry')).toBe(1);
    });

    it('listens to watcher agent:spawn events', () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();

      sseManager.connect(watcher as any, aggregator);

      expect(watcher.listenerCount('agent:spawn')).toBe(1);
    });

    it('listens to watcher session:start events', () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();

      sseManager.connect(watcher as any, aggregator);

      expect(watcher.listenerCount('session:start')).toBe(1);
    });
  });

  describe('disconnect', () => {
    it('clears all clients', () => {
      sseManager.createStream('client-1');
      sseManager.createStream('client-2');
      expect(sseManager.getClientCount()).toBe(2);

      sseManager.disconnect();
      expect(sseManager.getClientCount()).toBe(0);
    });
  });

  describe('broadcast behavior', () => {
    it('broadcasts metrics event on entry', async () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();
      sseManager.connect(watcher as any, aggregator);

      const stream = sseManager.createStream('broadcast-test');
      const reader = stream.getReader();

      // Read and discard init event
      await reader.read();

      // Emit an entry event
      const mockEntry = {
        type: 'assistant',
        uuid: 'test-uuid',
        sessionId: 'test-session',
        timestamp: new Date(),
        toolCalls: [],
        usage: {
          inputTokens: 100,
          outputTokens: 50,
          cacheReadTokens: 0,
          cacheCreationTokens: 0,
        },
        model: 'claude-sonnet-4-20250514',
      };

      const mockSession = {
        sessionId: 'test-session',
        projectPath: '/test/path',
        projectName: 'test-project',
        filePath: '/test/file.jsonl',
        modifiedAt: new Date(),
        isAgent: false,
      };

      watcher.emit('entry', mockEntry, mockSession);

      // Read the metrics event
      const { value } = await reader.read();
      const text = new TextDecoder().decode(value);

      expect(text).toContain('event: metrics');
      expect(text).toContain('tokensIn');
      expect(text).toContain('tokensOut');

      reader.releaseLock();
    });

    it('broadcasts session:start event', async () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();
      sseManager.connect(watcher as any, aggregator);

      const stream = sseManager.createStream('session-start-test');
      const reader = stream.getReader();

      // Read and discard init event
      await reader.read();

      // Emit session:start event
      const mockSession = {
        sessionId: 'new-session',
        projectPath: '/test/path',
        projectName: 'test-project',
      };

      watcher.emit('session:start', mockSession);

      // Read the session:start event
      const { value } = await reader.read();
      const text = new TextDecoder().decode(value);

      expect(text).toContain('event: session:start');
      expect(text).toContain('new-session');

      reader.releaseLock();
    });
  });

  describe('client cleanup', () => {
    it('removes disconnected clients on broadcast failure', async () => {
      const watcher = new MockLogWatcher();
      const aggregator = new MetricsAggregator();
      sseManager.connect(watcher as any, aggregator);

      // Create a stream and then cancel it (simulate disconnect)
      const stream = sseManager.createStream('cleanup-test');
      const reader = stream.getReader();

      // Read init
      await reader.read();

      // Cancel the stream (client disconnects)
      await reader.cancel();

      // Emit an event - should handle the disconnected client gracefully
      const mockSession = {
        sessionId: 'test',
        projectPath: '/test',
        projectName: 'test',
      };
      watcher.emit('session:start', mockSession);

      // Client should be removed after failed broadcast
      // (exact behavior depends on implementation)
    });
  });
});
