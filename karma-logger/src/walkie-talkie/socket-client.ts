/**
 * Radio Socket Client
 * Phase 3: CLI-to-server communication for agent coordination
 */

import * as net from 'node:net';
import * as path from 'node:path';
import { randomUUID } from 'node:crypto';
import type {
  RadioRequest,
  RadioResponse,
  RadioCommand,
  RadioEnv,
} from './types.js';

/** Default connection timeout in milliseconds */
const DEFAULT_TIMEOUT_MS = 5000;

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
