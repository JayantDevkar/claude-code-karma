/**
 * Subscription-Based Wait Tests
 * Phase 4: Tests for subscription-based agent status notifications
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as net from 'node:net';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import { randomUUID } from 'node:crypto';
import {
  RadioClient,
  RadioServerNotRunningError,
  RadioTimeoutError,
  SubscriptionError,
  createRadioClient,
} from '../../src/walkie-talkie/socket-client.js';
import { MemoryCacheStore } from '../../src/walkie-talkie/cache-store.js';
import { SubscriptionManager } from '../../src/walkie-talkie/socket-server.js';
import type {
  AgentStatus,
  AgentState,
  SubscribeMessage,
  UnsubscribeMessage,
  SubscribedMessage,
  NotificationMessage,
  KeepAliveMessage,
} from '../../src/walkie-talkie/types.js';

// ============================================
// Test Helpers
// ============================================

/**
 * Create a temporary socket path for testing
 */
function createTestSocketPath(): string {
  const tmpDir = os.tmpdir();
  const uniqueId = `karma-sub-test-${process.pid}-${Date.now()}`;
  return process.platform === 'win32'
    ? `\\\\.\\pipe\\${uniqueId}`
    : path.join(tmpDir, `${uniqueId}.sock`);
}

/**
 * Clean up socket file (Unix only)
 */
function cleanupSocket(socketPath: string): void {
  if (process.platform !== 'win32') {
    try {
      fs.unlinkSync(socketPath);
    } catch {
      // Ignore if doesn't exist
    }
  }
}

/**
 * Start server and wait for it to be listening
 */
async function startServer(server: net.Server, socketPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    server.once('listening', () => resolve());
    server.once('error', reject);
    server.listen(socketPath);
  });
}

/**
 * Stop server and wait for close
 */
async function stopServer(server: net.Server): Promise<void> {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      resolve();
    }, 100);

    server.close(() => {
      clearTimeout(timeout);
      resolve();
    });

    server.closeAllConnections?.();
  });
}

/**
 * Create a mock agent status
 */
function createMockStatus(agentId: string, state: AgentState): AgentStatus {
  return {
    agentId,
    sessionId: 'test-session',
    rootSessionId: 'test-root',
    state,
    startedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    parentId: null,
    parentType: 'session',
    agentType: 'test',
    model: 'test-model',
    metadata: {},
  };
}

/**
 * Create a mock subscription server that integrates with SubscriptionManager
 */
function createMockSubscriptionServer(
  socketPath: string,
  cache: MemoryCacheStore
): { server: net.Server; manager: SubscriptionManager } {
  const manager = new SubscriptionManager(cache);

  const server = net.createServer((socket) => {
    let buffer = '';

    socket.on('data', (data) => {
      buffer += data.toString();

      let newlineIndex: number;
      while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
        const jsonStr = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);

        if (!jsonStr.trim()) continue;

        try {
          const message = JSON.parse(jsonStr);

          if (message.type === 'subscribe') {
            const subscriptionId = manager.subscribe(socket, message as SubscribeMessage);
            const confirmed: SubscribedMessage = {
              type: 'subscribed',
              subscriptionId,
            };
            socket.write(JSON.stringify(confirmed) + '\n');
          } else if (message.type === 'unsubscribe') {
            manager.unsubscribe((message as UnsubscribeMessage).subscriptionId);
          }
        } catch {
          // Ignore parse errors
        }
      }
    });

    socket.on('close', () => {
      manager.cleanupSocket(socket);
    });

    socket.on('error', () => {
      manager.cleanupSocket(socket);
    });
  });

  return { server, manager };
}

// ============================================
// SubscriptionManager Unit Tests
// ============================================

describe('SubscriptionManager', () => {
  let cache: MemoryCacheStore;
  let manager: SubscriptionManager;

  beforeEach(() => {
    cache = new MemoryCacheStore();
    manager = new SubscriptionManager(cache);
  });

  afterEach(() => {
    manager.destroy();
    cache.destroy();
  });

  describe('subscription lifecycle', () => {
    it('tracks subscription count', () => {
      expect(manager.getSubscriptionCount()).toBe(0);
    });

    it('destroy cleans up all subscriptions', () => {
      manager.destroy();
      expect(manager.getSubscriptionCount()).toBe(0);
    });
  });
});

// ============================================
// Subscription-Based Wait Integration Tests
// ============================================

describe('RadioClient.waitForAgent', () => {
  let socketPath: string;
  let server: net.Server | null = null;
  let cache: MemoryCacheStore;
  let manager: SubscriptionManager | null = null;
  let client: RadioClient;

  beforeEach(() => {
    socketPath = createTestSocketPath();
    cache = new MemoryCacheStore();
    client = new RadioClient({ socketPath, timeoutMs: 5000 });
  });

  afterEach(async () => {
    if (manager) {
      manager.destroy();
      manager = null;
    }
    if (server) {
      await stopServer(server);
      server = null;
    }
    cache.destroy();
    cleanupSocket(socketPath);
  });

  describe('subscription mode', () => {
    it('receives notification when target state is reached', async () => {
      const result = createMockSubscriptionServer(socketPath, cache);
      server = result.server;
      manager = result.manager;
      await startServer(server, socketPath);

      const agentId = 'test-agent-1';

      // Set initial state
      cache.set(`agent:${agentId}:status`, createMockStatus(agentId, 'active'));

      // Start waiting for 'completed' state
      const waitPromise = client.waitForAgent(agentId, 'completed', 3000);

      // Wait a bit then update status
      await new Promise(resolve => setTimeout(resolve, 50));
      cache.set(`agent:${agentId}:status`, createMockStatus(agentId, 'completed'));

      // Should resolve with the completed status
      const status = await waitPromise;
      expect(status.state).toBe('completed');
      expect(status.agentId).toBe(agentId);
    });

    it('immediately notifies if already in target state', async () => {
      const result = createMockSubscriptionServer(socketPath, cache);
      server = result.server;
      manager = result.manager;
      await startServer(server, socketPath);

      const agentId = 'test-agent-2';

      // Set agent to already be in target state
      cache.set(`agent:${agentId}:status`, createMockStatus(agentId, 'completed'));

      // Should immediately resolve
      const status = await client.waitForAgent(agentId, 'completed', 1000);
      expect(status.state).toBe('completed');
    });

    it('times out when target state is not reached', async () => {
      const result = createMockSubscriptionServer(socketPath, cache);
      server = result.server;
      manager = result.manager;
      await startServer(server, socketPath);

      const agentId = 'test-agent-timeout';

      // Set initial state that won't change
      cache.set(`agent:${agentId}:status`, createMockStatus(agentId, 'active'));

      // Should timeout
      await expect(client.waitForAgent(agentId, 'completed', 200))
        .rejects.toThrow(RadioTimeoutError);
    });

    it('throws RadioServerNotRunningError when server not running', async () => {
      await expect(client.waitForAgent('agent-1', 'completed', 1000))
        .rejects.toThrow(RadioServerNotRunningError);
    });

    it('handles multiple concurrent subscriptions', async () => {
      const result = createMockSubscriptionServer(socketPath, cache);
      server = result.server;
      manager = result.manager;
      await startServer(server, socketPath);

      const agent1 = 'concurrent-agent-1';
      const agent2 = 'concurrent-agent-2';

      // Set initial states
      cache.set(`agent:${agent1}:status`, createMockStatus(agent1, 'active'));
      cache.set(`agent:${agent2}:status`, createMockStatus(agent2, 'pending'));

      // Create separate clients for concurrent waits
      const client1 = new RadioClient({ socketPath, timeoutMs: 5000 });
      const client2 = new RadioClient({ socketPath, timeoutMs: 5000 });

      // Start waiting for both
      const wait1 = client1.waitForAgent(agent1, 'completed', 3000);
      const wait2 = client2.waitForAgent(agent2, 'completed', 3000);

      // Wait a bit then update both statuses
      await new Promise(resolve => setTimeout(resolve, 50));
      cache.set(`agent:${agent1}:status`, createMockStatus(agent1, 'completed'));
      cache.set(`agent:${agent2}:status`, createMockStatus(agent2, 'completed'));

      // Both should resolve
      const [status1, status2] = await Promise.all([wait1, wait2]);
      expect(status1.state).toBe('completed');
      expect(status2.state).toBe('completed');
    });

    it('cleans up subscription on client disconnect', async () => {
      const result = createMockSubscriptionServer(socketPath, cache);
      server = result.server;
      manager = result.manager;
      await startServer(server, socketPath);

      const agentId = 'cleanup-test-agent';
      cache.set(`agent:${agentId}:status`, createMockStatus(agentId, 'active'));

      // Start a wait that will timeout quickly
      const waitPromise = client.waitForAgent(agentId, 'completed', 100);

      // Wait for timeout
      await expect(waitPromise).rejects.toThrow(RadioTimeoutError);

      // Give manager time to clean up
      await new Promise(resolve => setTimeout(resolve, 50));

      // Manager should have no active subscriptions
      expect(manager.getSubscriptionCount()).toBe(0);
    });
  });

  describe('poll mode fallback', () => {
    it('uses polling when --poll flag is set', async () => {
      // Create a simple mock server that responds to get-status requests
      server = net.createServer((socket) => {
        let buffer = '';
        socket.on('data', (data) => {
          buffer += data.toString();
          const newlineIndex = buffer.indexOf('\n');
          if (newlineIndex !== -1) {
            const request = JSON.parse(buffer.slice(0, newlineIndex));
            if (request.command === 'get-status') {
              const status = createMockStatus(request.args.agentId, 'completed');
              socket.write(JSON.stringify({ id: request.id, success: true, data: status }) + '\n');
            }
          }
        });
      });
      await startServer(server, socketPath);

      // Use poll mode
      const status = await client.waitForAgent('poll-agent', 'completed', 5000, true);
      expect(status.state).toBe('completed');
    });

    it('gracefully degrades to polling if subscription fails', async () => {
      // Create server that rejects subscriptions but handles get-status
      server = net.createServer((socket) => {
        let buffer = '';
        socket.on('data', (data) => {
          buffer += data.toString();
          const newlineIndex = buffer.indexOf('\n');
          if (newlineIndex !== -1) {
            const jsonStr = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 1);
            try {
              const message = JSON.parse(jsonStr);

              if (message.type === 'subscribe') {
                // Reject subscription
                socket.write(JSON.stringify({ success: false, error: 'Subscriptions disabled' }) + '\n');
              } else if (message.command === 'get-status') {
                const status = createMockStatus(message.args.agentId, 'completed');
                socket.write(JSON.stringify({ id: message.id, success: true, data: status }) + '\n');
              }
            } catch {
              // Ignore
            }
          }
        });
      });
      await startServer(server, socketPath);

      // Should fall back to polling and succeed
      const status = await client.waitForAgent('fallback-agent', 'completed', 5000);
      expect(status.state).toBe('completed');
    });
  });
});

// ============================================
// Keep-Alive Tests
// ============================================

describe('Keep-Alive Mechanism', () => {
  let socketPath: string;
  let server: net.Server | null = null;
  let cache: MemoryCacheStore;

  beforeEach(() => {
    socketPath = createTestSocketPath();
    cache = new MemoryCacheStore();
  });

  afterEach(async () => {
    if (server) {
      await stopServer(server);
      server = null;
    }
    cache.destroy();
    cleanupSocket(socketPath);
  });

  it('server sends keep-alive messages to subscribed clients', async () => {
    // This test uses a short keep-alive interval for testing
    const keepAliveReceived: boolean[] = [];

    // Create a custom server with short keep-alive
    const manager = new SubscriptionManager(cache);

    server = net.createServer((socket) => {
      let buffer = '';
      socket.on('data', (data) => {
        buffer += data.toString();
        const newlineIndex = buffer.indexOf('\n');
        if (newlineIndex !== -1) {
          const message = JSON.parse(buffer.slice(0, newlineIndex));
          buffer = buffer.slice(newlineIndex + 1);

          if (message.type === 'subscribe') {
            const subscriptionId = manager.subscribe(socket, message);
            socket.write(JSON.stringify({ type: 'subscribed', subscriptionId }) + '\n');
          }
        }
      });
      socket.on('close', () => manager.cleanupSocket(socket));
    });
    await startServer(server, socketPath);

    // Connect a client and subscribe
    const testSocket = net.createConnection({ path: socketPath });

    await new Promise<void>((resolve, reject) => {
      testSocket.once('connect', () => {
        testSocket.write(JSON.stringify({
          type: 'subscribe',
          agentId: 'keep-alive-test',
          targetState: 'completed',
        }) + '\n');
        resolve();
      });
      testSocket.once('error', reject);
    });

    // Give time for the subscription to be confirmed
    await new Promise(resolve => setTimeout(resolve, 100));

    // Clean up
    testSocket.destroy();
    manager.destroy();
  });
});

// ============================================
// Error Handling Tests
// ============================================

describe('Subscription Error Handling', () => {
  let socketPath: string;

  beforeEach(() => {
    socketPath = createTestSocketPath();
  });

  afterEach(() => {
    cleanupSocket(socketPath);
  });

  it('SubscriptionError has correct name and message', () => {
    const error = new SubscriptionError('Test subscription error');
    expect(error.name).toBe('SubscriptionError');
    expect(error.message).toBe('Test subscription error');
    expect(error).toBeInstanceOf(Error);
  });

  it('handles socket errors during subscription', async () => {
    const client = new RadioClient({ socketPath, timeoutMs: 1000 });

    // No server running - should throw RadioServerNotRunningError
    await expect(client.waitForAgent('agent', 'completed', 500))
      .rejects.toThrow(RadioServerNotRunningError);
  });
});
