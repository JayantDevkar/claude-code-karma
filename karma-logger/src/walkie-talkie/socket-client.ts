/**
 * Radio Socket Client
 * Phase 3: CLI-to-server communication for agent coordination
 * Phase 4: Subscription-based wait for agent status changes
 */

import * as net from 'node:net';
import * as path from 'node:path';
import { randomUUID } from 'node:crypto';
import type {
  RadioRequest,
  RadioResponse,
  RadioCommand,
  RadioEnv,
  AgentState,
  AgentStatus,
  SubscribeMessage,
  UnsubscribeMessage,
  SubscribedMessage,
  NotificationMessage,
  KeepAliveMessage,
  ServerPushMessage,
} from './types.js';

/** Default connection timeout in milliseconds */
const DEFAULT_TIMEOUT_MS = 5000;

/** Default subscription wait timeout (30 seconds) */
const DEFAULT_SUBSCRIPTION_TIMEOUT_MS = 30000;

/** Socket path for Unix or named pipe for Windows */
const SOCKET_PATH = process.platform === 'win32'
  ? '\\\\.\\pipe\\karma-radio'
  : '/tmp/karma-radio.sock';

/**
 * Error thrown when the radio server is not running
 */
export class RadioServerNotRunningError extends Error {
  constructor() {
    super('Radio server not running');
    this.name = 'RadioServerNotRunningError';
  }
}

/**
 * Error thrown when a radio request times out
 */
export class RadioTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`Radio request timed out after ${timeoutMs}ms`);
    this.name = 'RadioTimeoutError';
  }
}

/**
 * Error thrown when the radio server returns an error
 */
export class RadioServerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RadioServerError';
  }
}

/**
 * Error thrown when subscription-based wait fails
 */
export class SubscriptionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SubscriptionError';
  }
}

/**
 * Options for RadioClient
 */
export interface RadioClientOptions {
  /** Custom socket path (for testing) */
  socketPath?: string;
  /** Connection timeout in milliseconds */
  timeoutMs?: number;
}

/**
 * Client for communicating with the karma radio server
 * Provides a simple request-response API over Unix domain sockets
 */
export class RadioClient {
  private readonly socketPath: string;
  private readonly timeoutMs: number;
  private socket: net.Socket | null = null;

  constructor(options: RadioClientOptions = {}) {
    this.socketPath = options.socketPath ?? SOCKET_PATH;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  /**
   * Send a command to the radio server
   * @param command The command to execute
   * @param args Command arguments
   * @param env Agent environment context
   * @returns Response data from server
   * @throws RadioServerNotRunningError if server is not running
   * @throws RadioTimeoutError if request times out
   * @throws RadioServerError if server returns an error
   */
  async send<T = unknown>(
    command: RadioCommand,
    args: Record<string, unknown>,
    env: RadioEnv,
  ): Promise<T> {
    const request: RadioRequest = {
      id: randomUUID(),
      command,
      args,
      env,
    };

    const response = await this.sendRequest(request);

    if (!response.success) {
      throw new RadioServerError(response.error ?? 'Unknown server error');
    }

    return response.data as T;
  }

  /**
   * Check if the radio server is running
   * @returns true if server is accepting connections
   */
  async isServerRunning(): Promise<boolean> {
    try {
      const socket = await this.connect();
      socket.destroy();
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Send a raw request and get response
   */
  private async sendRequest(request: RadioRequest): Promise<RadioResponse> {
    return new Promise((resolve, reject) => {
      let socket: net.Socket;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;
      let responseBuffer = '';
      let isResolved = false;

      const cleanup = () => {
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
        if (socket && !socket.destroyed) {
          socket.destroy();
        }
      };

      const handleResolve = (response: RadioResponse) => {
        if (isResolved) return;
        isResolved = true;
        cleanup();
        resolve(response);
      };

      const handleReject = (error: Error) => {
        if (isResolved) return;
        isResolved = true;
        cleanup();
        reject(error);
      };

      // Set timeout
      timeoutId = setTimeout(() => {
        handleReject(new RadioTimeoutError(this.timeoutMs));
      }, this.timeoutMs);

      // Connect to socket
      socket = net.createConnection({ path: this.socketPath });

      socket.on('connect', () => {
        // Send request as JSON with newline delimiter
        const payload = JSON.stringify(request) + '\n';
        socket.write(payload);
      });

      socket.on('data', (data: Buffer) => {
        responseBuffer += data.toString();

        // Check for complete response (newline-delimited JSON)
        const newlineIndex = responseBuffer.indexOf('\n');
        if (newlineIndex !== -1) {
          const jsonStr = responseBuffer.slice(0, newlineIndex);
          try {
            const response = JSON.parse(jsonStr) as RadioResponse;
            handleResolve(response);
          } catch (parseError) {
            handleReject(new RadioServerError(`Invalid response: ${jsonStr}`));
          }
        }
      });

      socket.on('error', (err: NodeJS.ErrnoException) => {
        if (err.code === 'ENOENT' || err.code === 'ECONNREFUSED') {
          handleReject(new RadioServerNotRunningError());
        } else {
          handleReject(new RadioServerError(`Socket error: ${err.message}`));
        }
      });

      socket.on('close', () => {
        if (!isResolved) {
          // Connection closed before we got a response
          handleReject(new RadioServerError('Connection closed unexpectedly'));
        }
      });
    });
  }

  /**
   * Connect to the socket (for health checks)
   */
  private connect(): Promise<net.Socket> {
    return new Promise((resolve, reject) => {
      const socket = net.createConnection({ path: this.socketPath });

      const timeoutId = setTimeout(() => {
        socket.destroy();
        reject(new RadioTimeoutError(this.timeoutMs));
      }, this.timeoutMs);

      socket.on('connect', () => {
        clearTimeout(timeoutId);
        resolve(socket);
      });

      socket.on('error', (err: NodeJS.ErrnoException) => {
        clearTimeout(timeoutId);
        if (err.code === 'ENOENT' || err.code === 'ECONNREFUSED') {
          reject(new RadioServerNotRunningError());
        } else {
          reject(err);
        }
      });
    });
  }

  /**
   * Get the socket path being used
   */
  getSocketPath(): string {
    return this.socketPath;
  }

  // ============================================
  // Phase 4: Subscription-Based Wait
  // ============================================

  /**
   * Wait for an agent to reach a target state using subscription-based notifications
   *
   * Uses server-push notifications instead of polling for efficient waiting.
   * Falls back to polling if subscription fails.
   *
   * @param agentId The agent ID to wait for
   * @param targetState The state to wait for
   * @param timeoutMs Timeout in milliseconds (default: 30000)
   * @param usePoll Force polling mode instead of subscription
   * @returns AgentStatus when target state is reached
   * @throws RadioTimeoutError if timeout is reached
   * @throws RadioServerNotRunningError if server is not running
   * @throws SubscriptionError if subscription fails
   */
  async waitForAgent(
    agentId: string,
    targetState: AgentState,
    timeoutMs: number = DEFAULT_SUBSCRIPTION_TIMEOUT_MS,
    usePoll: boolean = false
  ): Promise<AgentStatus> {
    if (usePoll) {
      return this.waitForAgentPolling(agentId, targetState, timeoutMs);
    }

    try {
      return await this.waitForAgentSubscription(agentId, targetState, timeoutMs);
    } catch (error) {
      // Fall back to polling if subscription fails for non-fatal errors
      if (error instanceof SubscriptionError) {
        return this.waitForAgentPolling(agentId, targetState, timeoutMs);
      }
      throw error;
    }
  }

  /**
   * Wait for agent using subscription-based notifications
   */
  private async waitForAgentSubscription(
    agentId: string,
    targetState: AgentState,
    timeoutMs: number
  ): Promise<AgentStatus> {
    return new Promise((resolve, reject) => {
      let socket: net.Socket;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;
      let responseBuffer = '';
      let isResolved = false;
      let subscriptionId: string | null = null;

      const cleanup = () => {
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
        // Send unsubscribe if we have a subscription ID
        if (subscriptionId && socket && socket.writable) {
          const unsubscribeMsg: UnsubscribeMessage = {
            type: 'unsubscribe',
            subscriptionId,
          };
          try {
            socket.write(JSON.stringify(unsubscribeMsg) + '\n');
          } catch {
            // Ignore write errors during cleanup
          }
        }
        if (socket && !socket.destroyed) {
          socket.destroy();
        }
      };

      const handleResolve = (status: AgentStatus) => {
        if (isResolved) return;
        isResolved = true;
        cleanup();
        resolve(status);
      };

      const handleReject = (error: Error) => {
        if (isResolved) return;
        isResolved = true;
        cleanup();
        reject(error);
      };

      // Set timeout
      timeoutId = setTimeout(() => {
        handleReject(new RadioTimeoutError(timeoutMs));
      }, timeoutMs);

      // Connect to socket
      socket = net.createConnection({ path: this.socketPath });

      socket.on('connect', () => {
        // Send subscribe message
        const subscribeMsg: SubscribeMessage = {
          type: 'subscribe',
          agentId,
          targetState,
        };
        socket.write(JSON.stringify(subscribeMsg) + '\n');
      });

      socket.on('data', (data: Buffer) => {
        responseBuffer += data.toString();

        // Process complete messages (newline-delimited JSON)
        let newlineIndex: number;
        while ((newlineIndex = responseBuffer.indexOf('\n')) !== -1) {
          const jsonStr = responseBuffer.slice(0, newlineIndex);
          responseBuffer = responseBuffer.slice(newlineIndex + 1);

          if (!jsonStr.trim()) continue;

          try {
            const message = JSON.parse(jsonStr);

            // Handle different message types
            if (message.type === 'subscribed') {
              const subscribed = message as SubscribedMessage;
              subscriptionId = subscribed.subscriptionId;
              // Subscription confirmed, continue waiting
            } else if (message.type === 'notification') {
              const notification = message as NotificationMessage;
              // Target state reached!
              handleResolve(notification.status);
            } else if (message.type === 'keep-alive') {
              // Keep-alive received, ignore
            } else if (message.success === false) {
              // Error response
              handleReject(new SubscriptionError(message.error || 'Subscription failed'));
            }
          } catch (parseError) {
            // Ignore parse errors for individual messages
          }
        }
      });

      socket.on('error', (err: NodeJS.ErrnoException) => {
        if (err.code === 'ENOENT' || err.code === 'ECONNREFUSED') {
          handleReject(new RadioServerNotRunningError());
        } else {
          handleReject(new SubscriptionError(`Socket error: ${err.message}`));
        }
      });

      socket.on('close', () => {
        if (!isResolved) {
          handleReject(new SubscriptionError('Connection closed unexpectedly'));
        }
      });
    });
  }

  /**
   * Wait for agent using polling (fallback mode)
   */
  private async waitForAgentPolling(
    agentId: string,
    targetState: AgentState,
    timeoutMs: number
  ): Promise<AgentStatus> {
    const startTime = Date.now();
    const pollInterval = 500; // Poll every 500ms

    while (Date.now() - startTime < timeoutMs) {
      try {
        // Use a simple get request to check status
        const socket = await this.connectForPoll();
        const status = await this.pollAgentStatus(socket, agentId);

        if (status?.state === targetState) {
          return status;
        }

        // Wait before next poll
        await this.sleep(pollInterval);
      } catch (error) {
        if (error instanceof RadioServerNotRunningError) {
          throw error;
        }
        // For other errors, continue polling
        await this.sleep(pollInterval);
      }
    }

    throw new RadioTimeoutError(timeoutMs);
  }

  /**
   * Connect for a single poll request
   */
  private async connectForPoll(): Promise<net.Socket> {
    return new Promise((resolve, reject) => {
      const socket = net.createConnection({ path: this.socketPath });

      const timeoutId = setTimeout(() => {
        socket.destroy();
        reject(new RadioTimeoutError(this.timeoutMs));
      }, this.timeoutMs);

      socket.on('connect', () => {
        clearTimeout(timeoutId);
        resolve(socket);
      });

      socket.on('error', (err: NodeJS.ErrnoException) => {
        clearTimeout(timeoutId);
        if (err.code === 'ENOENT' || err.code === 'ECONNREFUSED') {
          reject(new RadioServerNotRunningError());
        } else {
          reject(new RadioServerError(`Socket error: ${err.message}`));
        }
      });
    });
  }

  /**
   * Poll for agent status over existing socket connection
   */
  private async pollAgentStatus(socket: net.Socket, agentId: string): Promise<AgentStatus | null> {
    return new Promise((resolve, reject) => {
      let responseBuffer = '';
      let isResolved = false;

      const cleanup = () => {
        if (!socket.destroyed) {
          socket.destroy();
        }
      };

      const handleResolve = (status: AgentStatus | null) => {
        if (isResolved) return;
        isResolved = true;
        cleanup();
        resolve(status);
      };

      const handleReject = (error: Error) => {
        if (isResolved) return;
        isResolved = true;
        cleanup();
        reject(error);
      };

      const request: RadioRequest = {
        id: randomUUID(),
        command: 'get-status',
        args: { agentId },
        env: {
          agentId: 'poll-client',
          sessionId: 'poll-session',
        },
      };

      socket.write(JSON.stringify(request) + '\n');

      socket.on('data', (data: Buffer) => {
        responseBuffer += data.toString();

        const newlineIndex = responseBuffer.indexOf('\n');
        if (newlineIndex !== -1) {
          const jsonStr = responseBuffer.slice(0, newlineIndex);
          try {
            const response = JSON.parse(jsonStr) as RadioResponse;
            if (response.success) {
              handleResolve(response.data as AgentStatus | null);
            } else {
              handleReject(new RadioServerError(response.error || 'Get status failed'));
            }
          } catch {
            handleReject(new RadioServerError(`Invalid response: ${jsonStr}`));
          }
        }
      });

      socket.on('error', (err) => {
        handleReject(new RadioServerError(`Poll error: ${err.message}`));
      });

      socket.on('close', () => {
        if (!isResolved) {
          handleReject(new RadioServerError('Connection closed during poll'));
        }
      });
    });
  }

  /**
   * Sleep helper for polling
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

/**
 * Create a RadioClient with default options
 */
export function createRadioClient(options?: RadioClientOptions): RadioClient {
  return new RadioClient(options);
}

/**
 * Get default socket path for current platform
 */
export function getDefaultSocketPath(): string {
  return SOCKET_PATH;
}
