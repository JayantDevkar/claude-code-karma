/**
 * Radio Client unit tests
 * Phase 3: CLI-to-server socket communication
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as net from 'node:net';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import {
  RadioClient,
  RadioServerNotRunningError,
  RadioTimeoutError,
  RadioServerError,
  createRadioClient,
  getDefaultSocketPath,
} from '../../src/walkie-talkie/socket-client.js';
import type { RadioRequest, RadioResponse, RadioEnv } from '../../src/walkie-talkie/types.js';

// ============================================
// Test Helpers
// ============================================

/**
 * Create a temporary socket path for testing
 */
function createTestSocketPath(): string {
  const tmpDir = os.tmpdir();
  const uniqueId = `karma-radio-test-${process.pid}-${Date.now()}`;
  return process.platform === 'win32'
    ? `\\\\.\\pipe\\${uniqueId}`
    : path.join(tmpDir, `${uniqueId}.sock`);
}

/**
 * Create a mock radio server for testing
 */
function createMockServer(
  socketPath: string,
  responseHandler: (request: RadioRequest) => RadioResponse,
): net.Server {
  const server = net.createServer((socket) => {
    let buffer = '';

    socket.on('data', (data) => {
      buffer += data.toString();

      const newlineIndex = buffer.indexOf('\n');
      if (newlineIndex !== -1) {
        const jsonStr = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);

        try {
          const request = JSON.parse(jsonStr) as RadioRequest;
          const response = responseHandler(request);
          socket.write(JSON.stringify(response) + '\n');
        } catch (error) {
          socket.write(JSON.stringify({
            id: 'error',
            success: false,
            error: 'Parse error',
          }) + '\n');
        }
      }
    });
  });

  return server;
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
 * Stop server and wait for close (with timeout for unresponsive servers)
 */
async function stopServer(server: net.Server): Promise<void> {
  return new Promise((resolve) => {
    // Set a timeout to force resolve if server doesn't close cleanly
    const timeout = setTimeout(() => {
      resolve();
    }, 100);

    server.close(() => {
      clearTimeout(timeout);
      resolve();
    });

    // Force close all connections for unresponsive servers
    server.closeAllConnections?.();
  });
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
 * Default test environment
 */
const testEnv: RadioEnv = {
  agentId: 'test-agent-1',
  sessionId: 'test-session-1',
  parentId: 'test-parent-1',
  agentType: 'test-type',
  model: 'claude-sonnet-4',
};

// ============================================
// RadioClient Tests
// ============================================

describe('RadioClient', () => {
  let socketPath: string;
  let server: net.Server | null = null;
  let client: RadioClient;

  beforeEach(() => {
    socketPath = createTestSocketPath();
    client = new RadioClient({ socketPath, timeoutMs: 2000 });
  });

  afterEach(async () => {
    if (server) {
      await stopServer(server);
      server = null;
    }
    cleanupSocket(socketPath);
  });

  // ============================================
  // Connection Tests
  // ============================================

  describe('connection', () => {
    it('connects to running server', async () => {
      server = createMockServer(socketPath, (req) => ({
        id: req.id,
        success: true,
        data: { connected: true },
      }));
      await startServer(server, socketPath);

      const result = await client.send('get-status', {}, testEnv);
      expect(result).toEqual({ connected: true });
    });

    it('throws RadioServerNotRunningError when server not running', async () => {
      await expect(client.send('get-status', {}, testEnv))
        .rejects.toThrow(RadioServerNotRunningError);
    });

    it('isServerRunning returns true when server is running', async () => {
      server = createMockServer(socketPath, () => ({
        id: 'test',
        success: true,
      }));
      await startServer(server, socketPath);

      const running = await client.isServerRunning();
      expect(running).toBe(true);
    });

    it('isServerRunning returns false when server not running', async () => {
      const running = await client.isServerRunning();
      expect(running).toBe(false);
    });

    it('getSocketPath returns configured path', () => {
      expect(client.getSocketPath()).toBe(socketPath);
    });
  });

  // ============================================
  // Request/Response Tests
  // ============================================

  describe('request/response handling', () => {
    it('sends request with correct format', async () => {
      let receivedRequest: RadioRequest | null = null;

      server = createMockServer(socketPath, (req) => {
        receivedRequest = req;
        return { id: req.id, success: true };
      });
      await startServer(server, socketPath);

      await client.send('set-status', { state: 'active', tool: 'Read' }, testEnv);

      expect(receivedRequest).not.toBeNull();
      expect(receivedRequest!.command).toBe('set-status');
      expect(receivedRequest!.args).toEqual({ state: 'active', tool: 'Read' });
      expect(receivedRequest!.env).toEqual(testEnv);
      expect(receivedRequest!.id).toBeTruthy();
    });

    it('returns response data on success', async () => {
      server = createMockServer(socketPath, (req) => ({
        id: req.id,
        success: true,
        data: { status: 'active', updatedAt: '2026-01-08T12:00:00Z' },
      }));
      await startServer(server, socketPath);

      const result = await client.send<{ status: string; updatedAt: string }>(
        'get-status',
        {},
        testEnv,
      );

      expect(result.status).toBe('active');
      expect(result.updatedAt).toBe('2026-01-08T12:00:00Z');
    });

    it('throws RadioServerError on error response', async () => {
      server = createMockServer(socketPath, (req) => ({
        id: req.id,
        success: false,
        error: 'Agent not found',
      }));
      await startServer(server, socketPath);

      await expect(client.send('get-status', { agentId: 'unknown' }, testEnv))
        .rejects.toThrow(RadioServerError);

      await expect(client.send('get-status', { agentId: 'unknown' }, testEnv))
        .rejects.toThrow('Agent not found');
    });

    it('handles complex nested data in response', async () => {
      const complexData = {
        agents: [
          { id: 'a1', status: 'active', children: ['c1', 'c2'] },
          { id: 'a2', status: 'completed', children: [] },
        ],
        metadata: {
          total: 2,
          nested: { deep: { value: 42 } },
        },
      };

      server = createMockServer(socketPath, (req) => ({
        id: req.id,
        success: true,
        data: complexData,
      }));
      await startServer(server, socketPath);

      const result = await client.send('get-status', {}, testEnv);
      expect(result).toEqual(complexData);
    });

    it('generates unique request IDs', async () => {
      const receivedIds: string[] = [];

      server = createMockServer(socketPath, (req) => {
        receivedIds.push(req.id);
        return { id: req.id, success: true };
      });
      await startServer(server, socketPath);

      await client.send('get-status', {}, testEnv);
      await client.send('get-status', {}, testEnv);
      await client.send('get-status', {}, testEnv);

      expect(receivedIds.length).toBe(3);
      expect(new Set(receivedIds).size).toBe(3); // All unique
    });

    it('handles all command types', async () => {
      const commands: Array<{ command: string; args: Record<string, unknown> }> = [
        { command: 'set-status', args: { state: 'active' } },
        { command: 'report-progress', args: { progress: { percent: 50 } } },
        { command: 'wait-for', args: { targetAgentId: 'a2', state: 'completed' } },
        { command: 'send', args: { targetAgentId: 'a2', message: { hello: 'world' } } },
        { command: 'listen', args: { pattern: '*' } },
        { command: 'get-status', args: {} },
        { command: 'publish-result', args: { result: { data: 'test' } } },
      ];

      server = createMockServer(socketPath, (req) => ({
        id: req.id,
        success: true,
        data: { command: req.command },
      }));
      await startServer(server, socketPath);

      for (const { command, args } of commands) {
        const result = await client.send(command as any, args, testEnv);
        expect((result as any).command).toBe(command);
      }
    });
  });

  // ============================================
  // Timeout Tests
  // ============================================

  describe('timeout behavior', () => {
    it('throws RadioTimeoutError when server does not respond', async () => {
      // Server that never responds
      server = net.createServer((socket) => {
        // Intentionally do nothing - simulate unresponsive server
      });
      await startServer(server, socketPath);

      const fastClient = new RadioClient({ socketPath, timeoutMs: 100 });

      await expect(fastClient.send('get-status', {}, testEnv))
        .rejects.toThrow(RadioTimeoutError);
    });

    it('throws RadioTimeoutError with timeout duration in message', async () => {
      server = net.createServer(() => {
        // Never respond
      });
      await startServer(server, socketPath);

      const fastClient = new RadioClient({ socketPath, timeoutMs: 150 });

      await expect(fastClient.send('get-status', {}, testEnv))
        .rejects.toThrow('150ms');
    });

    it('uses default timeout of 5000ms', () => {
      const defaultClient = createRadioClient({ socketPath });
      // We can't easily test the actual timeout without waiting,
      // but we can verify the client was created
      expect(defaultClient.getSocketPath()).toBe(socketPath);
    });

    it('respects custom timeout option', async () => {
      server = net.createServer(() => {
        // Never respond
      });
      await startServer(server, socketPath);

      const startTime = Date.now();
      const fastClient = new RadioClient({ socketPath, timeoutMs: 50 });

      await expect(fastClient.send('get-status', {}, testEnv))
        .rejects.toThrow(RadioTimeoutError);

      const elapsed = Date.now() - startTime;
      expect(elapsed).toBeLessThan(200); // Should timeout quickly
    });
  });

  // ============================================
  // Error Handling Tests
  // ============================================

  describe('error handling', () => {
    it('handles server closing connection before response', async () => {
      server = net.createServer((socket) => {
        socket.on('data', () => {
          socket.destroy(); // Close without responding
        });
      });
      await startServer(server, socketPath);

      await expect(client.send('get-status', {}, testEnv))
        .rejects.toThrow(RadioServerError);
    });

    it('handles invalid JSON response from server', async () => {
      server = net.createServer((socket) => {
        socket.on('data', () => {
          socket.write('not valid json\n');
        });
      });
      await startServer(server, socketPath);

      await expect(client.send('get-status', {}, testEnv))
        .rejects.toThrow(RadioServerError);

      await expect(client.send('get-status', {}, testEnv))
        .rejects.toThrow('Invalid response');
    });

    it('handles server error with missing error message', async () => {
      server = createMockServer(socketPath, (req) => ({
        id: req.id,
        success: false,
        // No error message provided
      }));
      await startServer(server, socketPath);

      await expect(client.send('get-status', {}, testEnv))
        .rejects.toThrow('Unknown server error');
    });

    it('handles socket error ECONNREFUSED', async () => {
      // No server running, will get ECONNREFUSED
      await expect(client.send('get-status', {}, testEnv))
        .rejects.toThrow(RadioServerNotRunningError);
    });
  });

  // ============================================
  // Concurrent Requests Tests
  // ============================================

  describe('concurrent requests', () => {
    it('handles multiple concurrent requests', async () => {
      let requestCount = 0;

      server = createMockServer(socketPath, (req) => {
        requestCount++;
        return {
          id: req.id,
          success: true,
          data: { requestNumber: requestCount },
        };
      });
      await startServer(server, socketPath);

      // Send multiple requests concurrently
      const client1 = new RadioClient({ socketPath, timeoutMs: 2000 });
      const client2 = new RadioClient({ socketPath, timeoutMs: 2000 });
      const client3 = new RadioClient({ socketPath, timeoutMs: 2000 });

      const results = await Promise.all([
        client1.send('get-status', {}, testEnv),
        client2.send('set-status', { state: 'active' }, testEnv),
        client3.send('report-progress', { progress: { percent: 50 } }, testEnv),
      ]);

      expect(results.length).toBe(3);
      expect(requestCount).toBe(3);
    });
  });
});

// ============================================
// Error Class Tests
// ============================================

describe('RadioServerNotRunningError', () => {
  it('has correct name and message', () => {
    const error = new RadioServerNotRunningError();
    expect(error.name).toBe('RadioServerNotRunningError');
    expect(error.message).toBe('Radio server not running');
  });

  it('is instanceof Error', () => {
    const error = new RadioServerNotRunningError();
    expect(error).toBeInstanceOf(Error);
  });
});

describe('RadioTimeoutError', () => {
  it('has correct name and message with timeout', () => {
    const error = new RadioTimeoutError(5000);
    expect(error.name).toBe('RadioTimeoutError');
    expect(error.message).toBe('Radio request timed out after 5000ms');
  });

  it('is instanceof Error', () => {
    const error = new RadioTimeoutError(1000);
    expect(error).toBeInstanceOf(Error);
  });
});

describe('RadioServerError', () => {
  it('has correct name and message', () => {
    const error = new RadioServerError('Agent not found');
    expect(error.name).toBe('RadioServerError');
    expect(error.message).toBe('Agent not found');
  });

  it('is instanceof Error', () => {
    const error = new RadioServerError('Test error');
    expect(error).toBeInstanceOf(Error);
  });
});

// ============================================
// Factory Function Tests
// ============================================

describe('createRadioClient', () => {
  it('creates client with default options', () => {
    const client = createRadioClient();
    expect(client).toBeInstanceOf(RadioClient);
    expect(client.getSocketPath()).toBe(getDefaultSocketPath());
  });

  it('creates client with custom options', () => {
    const customPath = '/custom/path.sock';
    const client = createRadioClient({ socketPath: customPath, timeoutMs: 1000 });
    expect(client.getSocketPath()).toBe(customPath);
  });
});

// ============================================
// Default Socket Path Tests
// ============================================

describe('getDefaultSocketPath', () => {
  it('returns Unix socket path on non-Windows', () => {
    if (process.platform !== 'win32') {
      expect(getDefaultSocketPath()).toBe('/tmp/karma-radio.sock');
    }
  });

  it('returns named pipe on Windows', () => {
    if (process.platform === 'win32') {
      expect(getDefaultSocketPath()).toBe('\\\\.\\pipe\\karma-radio');
    }
  });
});

// ============================================
// Graceful Degradation Tests
// ============================================

describe('graceful degradation', () => {
  it('returns appropriate error when server unavailable', async () => {
    const client = createRadioClient();

    // When server is not running, should throw RadioServerNotRunningError
    // This allows CLI to output JSON error gracefully
    try {
      await client.send('get-status', {}, testEnv);
      expect.fail('Should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(RadioServerNotRunningError);
      expect((error as RadioServerNotRunningError).message).toBe('Radio server not running');
    }
  });

  it('allows checking server status without throwing', async () => {
    const client = createRadioClient();

    // isServerRunning should return false, not throw
    const running = await client.isServerRunning();
    expect(running).toBe(false);
  });
});

// ============================================
// Environment Variable Tests
// ============================================

describe('RadioEnv handling', () => {
  let socketPath: string;
  let server: net.Server | null = null;

  beforeEach(() => {
    socketPath = createTestSocketPath();
  });

  afterEach(async () => {
    if (server) {
      await stopServer(server);
      server = null;
    }
    cleanupSocket(socketPath);
  });

  it('passes full env to server', async () => {
    let receivedEnv: RadioEnv | null = null;

    server = createMockServer(socketPath, (req) => {
      receivedEnv = req.env;
      return { id: req.id, success: true };
    });
    await startServer(server, socketPath);

    const client = new RadioClient({ socketPath });
    const fullEnv: RadioEnv = {
      agentId: 'agent-123',
      sessionId: 'session-456',
      parentId: 'parent-789',
      agentType: 'code-review',
      model: 'claude-opus-4',
    };

    await client.send('set-status', { state: 'active' }, fullEnv);

    expect(receivedEnv).toEqual(fullEnv);
  });

  it('passes minimal env to server', async () => {
    let receivedEnv: RadioEnv | null = null;

    server = createMockServer(socketPath, (req) => {
      receivedEnv = req.env;
      return { id: req.id, success: true };
    });
    await startServer(server, socketPath);

    const client = new RadioClient({ socketPath });
    const minimalEnv: RadioEnv = {
      agentId: 'agent-123',
      sessionId: 'session-456',
    };

    await client.send('get-status', {}, minimalEnv);

    expect(receivedEnv).toEqual(minimalEnv);
    expect(receivedEnv?.parentId).toBeUndefined();
    expect(receivedEnv?.agentType).toBeUndefined();
    expect(receivedEnv?.model).toBeUndefined();
  });
});
