/**
 * Radio Socket Server
 * Phase 5: Server-side socket handling for karma radio CLI
 *
 * Accepts connections from `karma radio` CLI commands and routes
 * requests to the appropriate AgentRadio instances via the aggregator.
 */

import * as net from 'node:net';
import * as fs from 'node:fs';
import { randomUUID } from 'node:crypto';
import type { Server, Socket } from 'node:net';
import type { MetricsAggregator } from '../aggregator.js';
import type {
  RadioRequest,
  RadioResponse,
  AgentStatus,
  AgentState,
  SubscribeMessage,
  UnsubscribeMessage,
  SubscribedMessage,
  NotificationMessage,
  KeepAliveMessage,
  CacheStore,
} from './types.js';

/** Default socket path for Unix */
const DEFAULT_SOCKET_PATH = '/tmp/karma-radio.sock';

/** Maximum message size (64KB) */
const MAX_MESSAGE_SIZE = 65536;

/** Socket timeout in milliseconds (5s) */
const SOCKET_TIMEOUT_MS = 5000;

/** Maximum concurrent connections */
const MAX_CONNECTIONS = 10;

/** Keep-alive interval for subscription connections (30s) */
const KEEP_ALIVE_INTERVAL_MS = 30000;

/** Extended socket timeout for subscription connections (5 minutes) */
const SUBSCRIPTION_SOCKET_TIMEOUT_MS = 300000;

// ============================================
// Phase 4: Subscription Manager
// ============================================

/**
 * Subscription entry tracking an active subscription
 */
interface Subscription {
  id: string;
  agentId: string;
  targetState: AgentState;
  socket: Socket;
  unsubscribe: () => void;
}

/**
 * Manages subscriptions for agent status changes
 * Handles pub/sub with CacheStore and pushes notifications to clients
 */
export class SubscriptionManager {
  private subscriptions: Map<string, Subscription> = new Map();
  private socketSubscriptions: Map<Socket, Set<string>> = new Map();
  private keepAliveIntervals: Map<Socket, ReturnType<typeof setInterval>> = new Map();
  private cache: CacheStore;

  constructor(cache: CacheStore) {
    this.cache = cache;
  }

  /**
   * Subscribe to agent status changes
   * @param socket Client socket to send notifications to
   * @param message Subscribe message with agentId and targetState
   * @returns Subscription ID
   */
  subscribe(socket: Socket, message: SubscribeMessage): string {
    const subscriptionId = randomUUID();
    const { agentId, targetState } = message;

    // Check if agent is already in target state
    const currentStatus = this.cache.get<AgentStatus>(`agent:${agentId}:status`);
    if (currentStatus?.state === targetState) {
      // Immediately notify - agent is already in target state
      const notification: NotificationMessage = {
        type: 'notification',
        subscriptionId,
        status: currentStatus,
      };
      socket.write(JSON.stringify(notification) + '\n');
      return subscriptionId;
    }

    // Subscribe to cache updates for this agent
    const unsubscribe = this.cache.subscribe(`agent:${agentId}:status`, (key, value) => {
      const status = value as AgentStatus;
      if (status?.state === targetState) {
        // Target state reached - notify and cleanup
        const notification: NotificationMessage = {
          type: 'notification',
          subscriptionId,
          status,
        };
        socket.write(JSON.stringify(notification) + '\n');
        this.unsubscribe(subscriptionId);
      }
    });

    // Store subscription
    const subscription: Subscription = {
      id: subscriptionId,
      agentId,
      targetState,
      socket,
      unsubscribe,
    };
    this.subscriptions.set(subscriptionId, subscription);

    // Track subscriptions by socket for cleanup
    if (!this.socketSubscriptions.has(socket)) {
      this.socketSubscriptions.set(socket, new Set());
      // Start keep-alive for this socket
      this.startKeepAlive(socket);
    }
    this.socketSubscriptions.get(socket)!.add(subscriptionId);

    // Extend socket timeout for subscription connections
    socket.setTimeout(SUBSCRIPTION_SOCKET_TIMEOUT_MS);

    return subscriptionId;
  }

  /**
   * Unsubscribe from notifications
   * @param subscriptionId Subscription to remove
   */
  unsubscribe(subscriptionId: string): void {
    const subscription = this.subscriptions.get(subscriptionId);
    if (!subscription) {
      return;
    }

    // Call cache unsubscribe
    subscription.unsubscribe();

    // Remove from tracking maps
    this.subscriptions.delete(subscriptionId);
    const socketSubs = this.socketSubscriptions.get(subscription.socket);
    if (socketSubs) {
      socketSubs.delete(subscriptionId);
      if (socketSubs.size === 0) {
        this.socketSubscriptions.delete(subscription.socket);
        this.stopKeepAlive(subscription.socket);
      }
    }
  }

  /**
   * Clean up all subscriptions for a disconnected socket
   * @param socket Socket that disconnected
   */
  cleanupSocket(socket: Socket): void {
    const subscriptionIds = this.socketSubscriptions.get(socket);
    if (!subscriptionIds) {
      return;
    }

    // Unsubscribe all subscriptions for this socket
    for (const subscriptionId of subscriptionIds) {
      const subscription = this.subscriptions.get(subscriptionId);
      if (subscription) {
        subscription.unsubscribe();
        this.subscriptions.delete(subscriptionId);
      }
    }

    this.socketSubscriptions.delete(socket);
    this.stopKeepAlive(socket);
  }

  /**
   * Start sending keep-alive messages to a socket
   */
  private startKeepAlive(socket: Socket): void {
    const interval = setInterval(() => {
      if (socket.writable) {
        const keepAlive: KeepAliveMessage = { type: 'keep-alive' };
        socket.write(JSON.stringify(keepAlive) + '\n');
      }
    }, KEEP_ALIVE_INTERVAL_MS);
    this.keepAliveIntervals.set(socket, interval);
  }

  /**
   * Stop sending keep-alive messages to a socket
   */
  private stopKeepAlive(socket: Socket): void {
    const interval = this.keepAliveIntervals.get(socket);
    if (interval) {
      clearInterval(interval);
      this.keepAliveIntervals.delete(socket);
    }
  }

  /**
   * Destroy all subscriptions and intervals
   */
  destroy(): void {
    // Clear all keep-alive intervals
    for (const interval of this.keepAliveIntervals.values()) {
      clearInterval(interval);
    }
    this.keepAliveIntervals.clear();

    // Unsubscribe all subscriptions
    for (const subscription of this.subscriptions.values()) {
      subscription.unsubscribe();
    }
    this.subscriptions.clear();
    this.socketSubscriptions.clear();
  }

  /**
   * Get count of active subscriptions (for stats/testing)
   */
  getSubscriptionCount(): number {
    return this.subscriptions.size;
  }
}

/**
 * Options for starting the radio server
 */
export interface RadioServerOptions {
  /** Custom socket path (default: /tmp/karma-radio.sock) */
  socketPath?: string;
}

/**
 * Extended server with subscription manager
 */
export interface RadioServer extends Server {
  subscriptionManager?: SubscriptionManager;
}

/**
 * Start the radio server for handling CLI connections
 *
 * @param aggregator The MetricsAggregator instance with radio enabled
 * @param options Server options
 * @returns The net.Server instance with subscriptionManager attached
 */
export function startRadioServer(
  aggregator: MetricsAggregator,
  options: RadioServerOptions = {}
): RadioServer {
  const socketPath = options.socketPath ?? DEFAULT_SOCKET_PATH;

  // Remove stale socket file if exists
  try {
    fs.unlinkSync(socketPath);
  } catch {
    // Socket file doesn't exist - that's fine
  }

  // Create subscription manager for Phase 4 support
  const cache = aggregator.getCache();
  const subscriptionManager = cache ? new SubscriptionManager(cache) : undefined;

  const server: RadioServer = net.createServer((socket) => {
    let buffer = '';

    // Set socket timeout to prevent hung connections
    socket.setTimeout(SOCKET_TIMEOUT_MS);
    socket.on('timeout', () => {
      // Cleanup subscriptions before destroying
      subscriptionManager?.cleanupSocket(socket);
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
        subscriptionManager?.cleanupSocket(socket);
        socket.destroy();
        return;
      }

      // Handle complete messages (newline-delimited JSON)
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;

        try {
          const parsed = JSON.parse(line);

          // Phase 4: Handle subscription messages
          if (parsed.type === 'subscribe') {
            handleSubscribeMessage(socket, parsed as SubscribeMessage, subscriptionManager);
            continue;
          }

          if (parsed.type === 'unsubscribe') {
            handleUnsubscribeMessage(parsed as UnsubscribeMessage, subscriptionManager);
            continue;
          }

          // Standard radio request
          const request = parsed as RadioRequest;
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
      // Socket error - cleanup subscriptions
      subscriptionManager?.cleanupSocket(socket);
    });

    socket.on('close', () => {
      // Clean up subscriptions on disconnect
      subscriptionManager?.cleanupSocket(socket);
    });
  });

  // Attach subscription manager to server for cleanup
  server.subscriptionManager = subscriptionManager;

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
 * Handle subscribe message for Phase 4 subscription-based wait
 */
function handleSubscribeMessage(
  socket: Socket,
  message: SubscribeMessage,
  subscriptionManager?: SubscriptionManager
): void {
  if (!subscriptionManager) {
    const errorResponse: RadioResponse = {
      id: 'subscribe-error',
      success: false,
      error: 'Subscriptions not available (radio not enabled)',
    };
    socket.write(JSON.stringify(errorResponse) + '\n');
    return;
  }

  const subscriptionId = subscriptionManager.subscribe(socket, message);

  // Send subscription confirmation
  const confirmed: SubscribedMessage = {
    type: 'subscribed',
    subscriptionId,
  };
  socket.write(JSON.stringify(confirmed) + '\n');
}

/**
 * Handle unsubscribe message
 */
function handleUnsubscribeMessage(
  message: UnsubscribeMessage,
  subscriptionManager?: SubscriptionManager
): void {
  subscriptionManager?.unsubscribe(message.subscriptionId);
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
        const progress = request.args.progress as { tool?: string; percent?: number; message?: string; step?: string } | undefined;

        // Use SetStatusOptions if progress is provided, otherwise use legacy metadata format
        if (progress) {
          radio.setStatus(state as any, { metadata, progress });
        } else if (metadata) {
          radio.setStatus(state as any, { metadata });
        } else {
          radio.setStatus(state as any);
        }
        return { id: request.id, success: true };
      }

      case 'report-progress': {
        radio.reportProgress(request.args as any);
        return { id: request.id, success: true };
      }

      case 'get-status': {
        const targetId = (request.args.agentId as string) || agentId;
        const includeProgress = request.args.includeProgress as boolean;

        if (includeProgress && targetId === agentId) {
          // Use getFullStatus for self with progress
          const fullStatus = radio.getFullStatus();
          return { id: request.id, success: true, data: fullStatus };
        }

        // For other agents or when not including progress, use cache directly
        const status = cache.get<AgentStatus>(`agent:${targetId}:status`);

        if (includeProgress && status) {
          // Manually attach progress for other agents
          const progress = cache.get(`agent:${targetId}:progress`);
          if (progress) {
            return { id: request.id, success: true, data: { ...status, progress } };
          }
        }

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

      case 'list-agents': {
        const filter = request.args.filter as 'children' | 'siblings' | 'parent' | 'all' | undefined;
        const status = request.args.status as AgentState | undefined;
        const agents = radio.listAgents({ filter, status });
        return { id: request.id, success: true, data: agents };
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
