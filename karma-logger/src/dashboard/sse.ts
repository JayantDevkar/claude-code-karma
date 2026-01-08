/**
 * SSE Manager for real-time dashboard updates
 * Phase 5: Server-Sent Events streaming
 * Phase 5 (Walkie-Talkie): Radio event broadcasts for agent status
 */

import type { MetricsAggregator } from '../aggregator.js';
import type { LogWatcher } from '../watcher.js';
import type { AgentStatus } from '../walkie-talkie/types.js';

interface SSEClient {
  id: string;
  controller: ReadableStreamDefaultController;
}

interface SSEEvent {
  type: string;
  data: unknown;
}

/**
 * Manages Server-Sent Events connections and broadcasts
 */
export class SSEManager {
  private clients: Map<string, SSEClient> = new Map();
  private aggregator: MetricsAggregator | null = null;
  private watcher: LogWatcher | null = null;
  private sessionId: string | null = null;
  private radioStatusUnsubscriber: (() => void) | null = null;
  private radioProgressUnsubscriber: (() => void) | null = null;

  /**
   * Connect to a watcher and aggregator for real-time updates
   */
  connect(watcher: LogWatcher, aggregator: MetricsAggregator, sessionId?: string): void {
    this.watcher = watcher;
    this.aggregator = aggregator;
    this.sessionId = sessionId ?? null;

    // Listen to watcher events
    watcher.on('entry', (entry, session) => {
      // Get updated metrics
      const metrics = aggregator.getTotals();
      this.broadcast({
        type: 'metrics',
        data: {
          tokensIn: metrics.tokensIn,
          tokensOut: metrics.tokensOut,
          cost: metrics.totalCost,
          cacheRead: metrics.cacheReadTokens,
          cacheCreation: metrics.cacheCreationTokens,
          toolCalls: metrics.toolCalls,
          timestamp: Date.now(),
        },
      });
    });

    watcher.on('agent:spawn', (agent, parent) => {
      // Get updated agent tree
      const tree = sessionId
        ? aggregator.getAgentTree(sessionId)
        : aggregator.getAllSessions().flatMap(s => aggregator.getAgentTree(s.sessionId));

      this.broadcast({
        type: 'agents',
        data: tree,
      });
    });

    watcher.on('session:start', (session) => {
      this.broadcast({
        type: 'session:start',
        data: {
          sessionId: session.sessionId,
          projectName: session.projectName,
          projectPath: session.projectPath,
        },
      });
    });

    // Subscribe to radio events if radio is enabled
    this.setupRadioSubscriptions(aggregator);
  }

  /**
   * Setup radio event subscriptions for broadcasting agent status
   * Phase 5 (Walkie-Talkie)
   */
  private setupRadioSubscriptions(aggregator: MetricsAggregator): void {
    // Subscribe to agent status changes
    this.radioStatusUnsubscriber = aggregator.onAgentStatusChange(
      (agentId: string, status: AgentStatus) => {
        // Note: status already contains agentId, so we just pass status directly
        this.broadcast({
          type: 'agent:status',
          data: status,
        });
      }
    );

    // Subscribe to progress updates via cache
    const cache = aggregator.getCache();
    if (cache) {
      this.radioProgressUnsubscriber = cache.subscribe(
        'agent:*:progress',
        (key: string, value: unknown) => {
          const agentId = key.split(':')[1];
          this.broadcast({
            type: 'agent:progress',
            data: { agentId, ...(value as object) },
          });
        }
      );
    }
  }

  /**
   * Broadcast an event to all connected clients
   */
  private broadcast(event: SSEEvent): void {
    const message = `event: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`;
    const encoded = new TextEncoder().encode(message);

    for (const [clientId, client] of this.clients) {
      try {
        client.controller.enqueue(encoded);
      } catch {
        // Client disconnected, remove them
        this.clients.delete(clientId);
      }
    }
  }

  /**
   * Create a readable stream for a new SSE client
   */
  createStream(clientId: string): ReadableStream {
    return new ReadableStream({
      start: (controller) => {
        this.clients.set(clientId, { id: clientId, controller });

        // Send initial state
        if (this.aggregator) {
          const totals = this.aggregator.getTotals();
          const sessions = this.aggregator.getAllSessions();

          const initMessage = `event: init\ndata: ${JSON.stringify({
            metrics: {
              tokensIn: totals.tokensIn,
              tokensOut: totals.tokensOut,
              cost: totals.totalCost,
              cacheRead: totals.cacheReadTokens,
              cacheCreation: totals.cacheCreationTokens,
              toolCalls: totals.toolCalls,
              sessions: totals.sessions,
              agents: totals.agents,
            },
            sessions: sessions.map(s => ({
              id: s.sessionId,
              projectName: s.projectName,
              tokensIn: s.tokensIn,
              tokensOut: s.tokensOut,
              cost: s.cost.total,
              agentCount: s.agentCount,
            })),
          })}\n\n`;

          controller.enqueue(new TextEncoder().encode(initMessage));
        }
      },
      cancel: () => {
        this.clients.delete(clientId);
      },
    });
  }

  /**
   * Get number of connected clients
   */
  getClientCount(): number {
    return this.clients.size;
  }

  /**
   * Disconnect all clients and stop listening
   */
  disconnect(): void {
    // Clean up radio subscriptions
    if (this.radioStatusUnsubscriber) {
      this.radioStatusUnsubscriber();
      this.radioStatusUnsubscriber = null;
    }
    if (this.radioProgressUnsubscriber) {
      this.radioProgressUnsubscriber();
      this.radioProgressUnsubscriber = null;
    }

    // Close all client connections
    for (const client of this.clients.values()) {
      try {
        client.controller.close();
      } catch {
        // Already closed
      }
    }
    this.clients.clear();
    this.watcher = null;
    this.aggregator = null;
  }
}

// Singleton instance for server use
export const sseManager = new SSEManager();
