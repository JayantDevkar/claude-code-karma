/**
 * Walkie-Talkie Cache Store Types
 * Phase 1: Core cache interfaces for agent communication
 */

/**
 * Callback function for pub/sub subscriptions
 */
export type SubscriberCallback = (key: string, value: unknown) => void;

/**
 * Statistics about cache state
 */
export interface CacheStats {
  keys: number;
  subscribers: number;
  memoryBytes: number;
}

/**
 * Core cache store interface for agent communication
 * Provides key-value storage with TTL, pattern matching, and pub/sub
 */
export interface CacheStore {
  /**
   * Set a value with optional TTL
   * @param key Cache key
   * @param value Value to store
   * @param ttlMs Time-to-live in milliseconds (-1 for infinite, defaults to 5 minutes)
   */
  set(key: string, value: unknown, ttlMs?: number): void;

  /**
   * Get a value by key
   * @param key Cache key
   * @returns Value or null if not found/expired
   */
  get<T>(key: string): T | null;

  /**
   * Delete a key from the cache
   * @param key Cache key
   * @returns true if key existed and was deleted
   */
  delete(key: string): boolean;

  /**
   * Get all keys matching a pattern
   * @param pattern Glob pattern (* matches any chars except :)
   * @returns Array of matching keys
   */
  keys(pattern: string): string[];

  /**
   * Get multiple values matching a pattern
   * @param pattern Glob pattern (* matches any chars except :)
   * @returns Map of matching key-value pairs
   */
  getMany(pattern: string): Map<string, unknown>;

  /**
   * Subscribe to key changes matching a pattern
   * @param pattern Glob pattern (* matches any chars except :)
   * @param cb Callback invoked when matching key changes
   * @returns Unsubscribe function
   */
  subscribe(pattern: string, cb: SubscriberCallback): () => void;

  /**
   * Publish a value change notification
   * @param key Key that changed
   * @param value New value
   */
  publish(key: string, value: unknown): void;

  /**
   * Clear all keys from the cache
   */
  clear(): void;

  /**
   * Get cache statistics
   * @returns Current cache stats
   */
  stats(): CacheStats;

  /**
   * Destroy the cache store, clearing intervals and subscribers
   */
  destroy(): void;
}

// ============================================
// Phase 2: Agent Radio Types
// ============================================

/**
 * Agent state in lifecycle
 */
export type AgentState = 'pending' | 'active' | 'waiting' | 'completed' | 'failed' | 'cancelled';

/**
 * Agent status information
 */
export interface AgentStatus {
  agentId: string;
  sessionId: string;
  rootSessionId: string;
  state: AgentState;
  startedAt: string;
  updatedAt: string;
  parentId: string | null;
  parentType: 'session' | 'agent';
  agentType: string;
  model: string;
  metadata: Record<string, unknown>;
}

/**
 * Progress update for ongoing work
 */
export interface ProgressUpdate {
  tool?: string;
  step?: string;
  percent?: number;
  message?: string;
}

/**
 * Combined status with optional progress
 * Used when querying full agent state in a single request
 */
export interface AgentStatusWithProgress extends AgentStatus {
  progress?: ProgressUpdate;
}

/**
 * Message in agent inbox
 */
export interface AgentMessage {
  fromAgentId: string;
  message: unknown;
  timestamp: string;
}

/**
 * Options for setStatus method
 * Enables batch operations: set status + progress in a single call
 */
export interface SetStatusOptions {
  metadata?: Record<string, unknown>;
  progress?: ProgressUpdate;
}

/**
 * High-level API for agent-to-agent communication
 */
export interface AgentRadio {
  readonly agentId: string;
  readonly sessionId: string;
  readonly parentId: string | null;

  setStatus(state: AgentState, options?: SetStatusOptions | Record<string, unknown>): void;
  getStatus(): AgentStatus;
  getFullStatus(): AgentStatusWithProgress;
  reportProgress(progress: ProgressUpdate): void;
  publishResult(result: unknown): void;
  onAgentStatus(agentId: string, cb: (status: AgentStatus) => void): () => void;
  onChildStatus(cb: (agentId: string, status: AgentStatus) => void): () => void;
  onSiblingStatus(cb: (agentId: string, status: AgentStatus) => void): () => void;
  getParentStatus(): AgentStatus | null;
  getChildStatuses(): Map<string, AgentStatus>;
  getSiblingStatuses(): Map<string, AgentStatus>;
  listAgents(options?: AgentDiscoveryOptions): AgentStatus[];
  waitForAgent(agentId: string, state: AgentState, timeoutMs?: number): Promise<AgentStatus>;
  send(targetAgentId: string, message: unknown): void;
  onMessage(cb: (fromAgentId: string, message: unknown) => void): () => void;
  destroy(): void;
}

// ============================================
// Phase 3: Radio CLI Protocol Types
// ============================================

/**
 * Commands available through the radio CLI
 */
export type RadioCommand =
  | 'set-status'
  | 'report-progress'
  | 'wait-for'
  | 'send'
  | 'listen'
  | 'get-status'
  | 'publish-result'
  | 'list-agents';

/**
 * Environment context for radio requests
 * Read from environment variables by CLI
 */
export interface RadioEnv {
  agentId: string;
  sessionId: string;
  parentId?: string;
  agentType?: string;
  model?: string;
}

/**
 * Request from CLI to radio server
 */
export interface RadioRequest {
  id: string;
  command: RadioCommand;
  args: Record<string, unknown>;
  env: RadioEnv;
}

/**
 * Response from radio server to CLI
 */
export interface RadioResponse {
  id: string;
  success: boolean;
  data?: unknown;
  error?: string;
}

/**
 * Options for agent discovery
 */
export interface AgentDiscoveryOptions {
  filter?: 'children' | 'siblings' | 'parent' | 'all';
  status?: AgentState;
}

// ============================================
// Phase 4: Subscription-Based Wait Types
// ============================================

/** Subscribe to agent status changes */
export interface SubscribeMessage {
  type: 'subscribe';
  agentId: string;
  targetState: AgentState;
}

/** Unsubscribe from notifications */
export interface UnsubscribeMessage {
  type: 'unsubscribe';
  subscriptionId: string;
}

/** Subscription confirmed */
export interface SubscribedMessage {
  type: 'subscribed';
  subscriptionId: string;
}

/** Status change notification */
export interface NotificationMessage {
  type: 'notification';
  subscriptionId: string;
  status: AgentStatus;
}

/** Keep-alive ping */
export interface KeepAliveMessage {
  type: 'keep-alive';
}

/** Server push message types */
export type ServerPushMessage = SubscribedMessage | NotificationMessage | KeepAliveMessage;
