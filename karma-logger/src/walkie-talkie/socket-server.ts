/**
 * Radio Socket Server
 * Phase 5: Server-side socket handling for karma radio CLI
 *
 * Accepts connections from `karma radio` CLI commands and routes
 * requests to the appropriate AgentRadio instances via the aggregator.
 */

import * as net from 'node:net';
import * as fs from 'node:fs';
import type { Server } from 'node:net';
import type { MetricsAggregator } from '../aggregator.js';
import type { RadioRequest, RadioResponse, AgentStatus } from './types.js';

/** Default socket path for Unix */
const DEFAULT_SOCKET_PATH = '/tmp/karma-radio.sock';

/** Maximum message size (64KB) */
const MAX_MESSAGE_SIZE = 65536;

/** Socket timeout in milliseconds (5s) */
const SOCKET_TIMEOUT_MS = 5000;

/** Maximum concurrent connections */
const MAX_CONNECTIONS = 10;

/**
 * Options for starting the radio server
 */
export interface RadioServerOptions {
  /** Custom socket path (default: /tmp/karma-radio.sock) */
  socketPath?: string;
}

/**
 * Start the radio server for handling CLI connections
 *
 * @param aggregator The MetricsAggregator instance with radio enabled
 * @param options Server options
 * @returns The net.Server instance
 */
export function startRadioServer(
  aggregator: MetricsAggregator,
  options: RadioServerOptions = {}
): Server {
  const socketPath = options.socketPath ?? DEFAULT_SOCKET_PATH;

  // Remove stale socket file if exists
  try {
    fs.unlinkSync(socketPath);
  } catch {
    // Socket file doesn't exist - that's fine
  }

  const server = net.createServer((socket) => {
    let buffer = '';

    // Set socket timeout to prevent hung connections
    socket.setTimeout(SOCKET_TIMEOUT_MS);
    socket.on('timeout', () => {
      socket.destroy();
    });

    socket.on('data', (data) => {
      buffer += data.toString();

      // Reject oversized messages (>64KB)
      if (buffer.length > MAX_MESSAGE_SIZE) {
        const errorResponse: RadioResponse = {
          id: 'error',
          success: false,
          error: 'Message too large',
        };
        socket.write(JSON.stringify(errorResponse) + '\n');
        socket.destroy();
        return;
      }

      // Handle complete messages (newline-delimited JSON)
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;

        try {
          const request = JSON.parse(line) as RadioRequest;
          const response = handleRadioRequest(request, aggregator);
          socket.write(JSON.stringify(response) + '\n');
        } catch (e) {
          const errorResponse: RadioResponse = {
            id: 'error',
            success: false,
            error: 'Invalid request',
          };
          socket.write(JSON.stringify(errorResponse) + '\n');
        }
      }
    });

    socket.on('error', () => {
      // Socket error - connection will close
    });
  });

  // Limit concurrent clients
  server.maxConnections = MAX_CONNECTIONS;

  server.listen(socketPath);

  // Set socket permissions (Unix only) - owner-only access
  if (process.platform !== 'win32') {
    try {
      fs.chmodSync(socketPath, 0o600);
    } catch {
      // Permissions not set - continue anyway
    }
  }

  return server;
}

/**
 * Handle a radio request from a CLI client
 *
 * @param request The parsed radio request
 * @param aggregator The MetricsAggregator instance
 * @returns Response to send back to client
 */
export function handleRadioRequest(
  request: RadioRequest,
  aggregator: MetricsAggregator
): RadioResponse {
  const cache = aggregator.getCache();
  if (!cache) {
    return {
      id: request.id,
      success: false,
      error: 'Radio not enabled',
    };
  }

  const { agentId, sessionId, parentId, agentType, model } = request.env;

  // Validate required environment fields
  if (!agentId || !sessionId) {
    return {
      id: request.id,
      success: false,
      error: 'Missing required env: agentId and sessionId',
    };
  }

  // Get or create radio for this agent (registers with aggregator for persistence)
  const radio = aggregator.getOrCreateAgentRadio(
    agentId,
    sessionId,
    parentId,
    agentType,
    model
  );

  if (!radio) {
    return {
      id: request.id,
      success: false,
      error: 'Failed to create radio instance',
    };
  }

  try {
    switch (request.command) {
      case 'set-status': {
        const state = request.args.state as string;
        const metadata = request.args.metadata as Record<string, unknown> | undefined;
        radio.setStatus(state as any, metadata);
        return { id: request.id, success: true };
      }

      case 'report-progress': {
        radio.reportProgress(request.args as any);
        return { id: request.id, success: true };
      }

      case 'get-status': {
        const targetId = (request.args.agentId as string) || agentId;
        const status = cache.get<AgentStatus>(`agent:${targetId}:status`);
        return { id: request.id, success: true, data: status };
      }

      case 'wait-for': {
        // For wait-for, we return the current status and let the client poll
        // Full async support would require keeping the socket open
        const targetId = request.args.agentId as string;
        const targetState = request.args.state as string;
        const status = cache.get<AgentStatus>(`agent:${targetId}:status`);

        if (status?.state === targetState) {
          return { id: request.id, success: true, data: status };
        }

        return {
          id: request.id,
          success: true,
          data: { waiting: true, currentState: status?.state ?? 'unknown' },
        };
      }

      case 'send': {
        const targetAgentId = request.args.targetAgentId as string;
        const message = request.args.message;
        if (!targetAgentId) {
          return {
            id: request.id,
            success: false,
            error: 'Missing targetAgentId',
          };
        }
        radio.send(targetAgentId, message);
        return { id: request.id, success: true };
      }

      case 'listen': {
        // Return current inbox messages
        // Full streaming would require keeping socket open
        const inbox = cache.get<Array<{ fromAgentId: string; message: unknown; timestamp: string }>>(
          `agent:${agentId}:inbox`
        );
        return { id: request.id, success: true, data: inbox ?? [] };
      }

      case 'publish-result': {
        const result = request.args.result;
        radio.publishResult(result);
        return { id: request.id, success: true };
      }

      default:
        return {
          id: request.id,
          success: false,
          error: `Unknown command: ${request.command}`,
        };
    }
  } catch (error) {
    return {
      id: request.id,
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

/**
 * Get the default socket path for the current platform
 */
export function getDefaultRadioSocketPath(): string {
  return DEFAULT_SOCKET_PATH;
}
