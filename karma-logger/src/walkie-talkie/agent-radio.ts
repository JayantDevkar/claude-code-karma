/**
 * Agent Radio Implementation
 * Phase 2: High-level API for agent-to-agent communication
 */

import type {
  CacheStore,
  AgentRadio,
  AgentState,
  AgentStatus,
  AgentStatusWithProgress,
  ProgressUpdate,
  AgentMessage,
  AgentDiscoveryOptions,
  SetStatusOptions,
  ValidationMode,
  ValidationResult,
} from './types.js';
import { schemaRegistry, validateMetadata } from './schema-registry.js';

/** TTL constants in milliseconds */
const TTL = {
  STATUS: 300000,       // 5 minutes
  PROGRESS: 60000,      // 1 minute
  RESULT: 600000,       // 10 minutes
  SESSION_AGENTS: 3600000, // 1 hour
  INBOX: 300000,        // 5 minutes
} as const;

/** Default timeout for waitForAgent */
const DEFAULT_WAIT_TIMEOUT = 30000; // 30 seconds

/**
 * Implementation of AgentRadio interface
 * Wraps CacheStore with agent-aware semantics
 */
export class AgentRadioImpl implements AgentRadio {
  readonly agentId: string;
  readonly sessionId: string;
  readonly parentId: string | null;

  private readonly rootSessionId: string;
  private readonly parentType: 'session' | 'agent';
  private readonly agentType: string;
  private readonly model: string;
  private readonly cache: CacheStore;
  private readonly depth: number;
  private unsubscribers: Array<() => void> = [];
  private startedAt: string;
  private metadata: Record<string, unknown> = {};

  constructor(
    cache: CacheStore,
    agentId: string,
    sessionId: string,
    rootSessionId: string,
    parentId: string | null,
    parentType: 'session' | 'agent',
    agentType: string,
    model: string,
  ) {
    this.cache = cache;
    this.agentId = agentId;
    this.sessionId = sessionId;
    this.rootSessionId = rootSessionId;
    this.parentId = parentId;
    this.parentType = parentType;
    this.agentType = agentType;
    this.model = model;
    this.startedAt = new Date().toISOString();

    // Compute hierarchy depth: session children are depth 0, agent children are parent depth + 1
    if (parentType === 'session' || !parentId) {
      this.depth = 0;
    } else {
      const parentStatus = cache.get<AgentStatus>(`agent:${parentId}:status`);
      this.depth = (parentStatus?.depth ?? 0) + 1;
    }

    // Register in session agents list
    this.registerInSession();

    // Set initial pending status
    this.setStatus('pending');
  }

  /**
   * Register this agent in the session's agent list and parent's children list
   */
  private registerInSession(): void {
    // Register in session agents list
    const sessionKey = `session:${this.rootSessionId}:agents`;
    const agents = this.cache.get<string[]>(sessionKey) ?? [];
    if (!agents.includes(this.agentId)) {
      agents.push(this.agentId);
      this.cache.set(sessionKey, agents, TTL.SESSION_AGENTS);
    }

    // Register in parent's children list (reverse index for O(1) child lookup)
    if (this.parentId && this.parentType === 'agent') {
      const parentChildrenKey = `parent:${this.parentId}:children`;
      const children = this.cache.get<string[]>(parentChildrenKey) ?? [];
      if (!children.includes(this.agentId)) {
        children.push(this.agentId);
        this.cache.set(parentChildrenKey, children, TTL.SESSION_AGENTS);
      }
    }
  }

  /**
   * Set agent status state with optional progress update
   * @param state The new agent state
   * @param options Optional SetStatusOptions with metadata and progress, or legacy metadata object
   */
  setStatus(state: AgentState, options?: SetStatusOptions | Record<string, unknown>): void {
    // Handle both new SetStatusOptions and legacy metadata-only format
    let metadata: Record<string, unknown> | undefined;
    let progress: ProgressUpdate | undefined;
    let validationMode: ValidationMode = 'none';

    if (options) {
      // Check if options is SetStatusOptions format
      // SetStatusOptions.progress is a ProgressUpdate object (with tool/step/percent/message)
      // SetStatusOptions.metadata is a Record<string, unknown>
      // SetStatusOptions.validateMetadata is a ValidationMode string
      // We detect SetStatusOptions by checking if 'progress' is an object with ProgressUpdate keys
      // or if 'metadata' is an object and options has no other keys besides 'metadata', 'progress', and 'validateMetadata'
      const hasProgressObject = 'progress' in options &&
        options.progress !== null &&
        typeof options.progress === 'object' &&
        !Array.isArray(options.progress);

      const hasValidateMetadata = 'validateMetadata' in options &&
        typeof options.validateMetadata === 'string';

      const hasMetadataOnly = 'metadata' in options &&
        options.metadata !== null &&
        typeof options.metadata === 'object' &&
        Object.keys(options).every(k => k === 'metadata' || k === 'progress' || k === 'validateMetadata');

      if (hasProgressObject || hasMetadataOnly || hasValidateMetadata) {
        const setStatusOptions = options as SetStatusOptions;
        metadata = setStatusOptions.metadata;
        progress = setStatusOptions.progress;
        validationMode = setStatusOptions.validateMetadata ?? 'none';
      } else {
        // Legacy format: treat entire options as metadata
        metadata = options as Record<string, unknown>;
      }
    }

    if (metadata) {
      this.metadata = { ...this.metadata, ...metadata };
    }

    // Phase 5: Validate metadata if validation mode is enabled
    if (validationMode !== 'none') {
      validateMetadata(this.agentType, this.metadata, validationMode, schemaRegistry);
    }

    const status: AgentStatus = {
      agentId: this.agentId,
      sessionId: this.sessionId,
      rootSessionId: this.rootSessionId,
      state,
      startedAt: this.startedAt,
      updatedAt: new Date().toISOString(),
      parentId: this.parentId,
      parentType: this.parentType,
      agentType: this.agentType,
      model: this.model,
      metadata: this.metadata,
      depth: this.depth,
    };

    this.cache.set(`agent:${this.agentId}:status`, status, TTL.STATUS);

    // Refresh SESSION_AGENTS TTL to keep session alive while agents are active
    this.refreshSessionTTL();

    // If progress is provided, update it atomically with status
    if (progress) {
      this.reportProgress(progress);
    }
  }

  /**
   * Refresh SESSION_AGENTS TTL to prevent expiration while agents are active
   */
  private refreshSessionTTL(): void {
    const sessionKey = `session:${this.rootSessionId}:agents`;
    const agents = this.cache.get<string[]>(sessionKey);
    if (agents) {
      this.cache.set(sessionKey, agents, TTL.SESSION_AGENTS);
    }

    // Also refresh parent's children list TTL
    if (this.parentId && this.parentType === 'agent') {
      const parentChildrenKey = `parent:${this.parentId}:children`;
      const children = this.cache.get<string[]>(parentChildrenKey);
      if (children) {
        this.cache.set(parentChildrenKey, children, TTL.SESSION_AGENTS);
      }
    }
  }

  /**
   * Get current agent status
   */
  getStatus(): AgentStatus {
    const status = this.cache.get<AgentStatus>(`agent:${this.agentId}:status`);
    if (!status) {
      // Return current state if not in cache
      return {
        agentId: this.agentId,
        sessionId: this.sessionId,
        rootSessionId: this.rootSessionId,
        state: 'pending',
        startedAt: this.startedAt,
        updatedAt: this.startedAt,
        parentId: this.parentId,
        parentType: this.parentType,
        agentType: this.agentType,
        model: this.model,
        metadata: this.metadata,
        depth: this.depth,
      };
    }
    return status;
  }

  /**
   * Get current agent status with progress included
   * Combines status and latest progress in a single response
   */
  getFullStatus(): AgentStatusWithProgress {
    const status = this.getStatus();
    const progress = this.cache.get<ProgressUpdate>(`agent:${this.agentId}:progress`);

    if (progress) {
      return { ...status, progress };
    }

    return status;
  }

  /**
   * Report progress update
   */
  reportProgress(progress: ProgressUpdate): void {
    this.cache.set(`agent:${this.agentId}:progress`, progress, TTL.PROGRESS);
  }

  /**
   * Publish final result
   */
  publishResult(result: unknown): void {
    this.cache.set(`agent:${this.agentId}:result`, result, TTL.RESULT);
  }

  /**
   * Subscribe to specific agent's status changes
   */
  onAgentStatus(agentId: string, cb: (status: AgentStatus) => void): () => void {
    const pattern = `agent:${agentId}:status`;
    const unsubscribe = this.cache.subscribe(pattern, (_key, value) => {
      cb(value as AgentStatus);
    });
    this.unsubscribers.push(unsubscribe);
    return unsubscribe;
  }

  /**
   * Subscribe to child agent status changes
   */
  onChildStatus(cb: (agentId: string, status: AgentStatus) => void): () => void {
    const pattern = 'agent:*:status';
    const unsubscribe = this.cache.subscribe(pattern, (_key, value) => {
      const status = value as AgentStatus;
      if (status.parentId === this.agentId) {
        cb(status.agentId, status);
      }
    });
    this.unsubscribers.push(unsubscribe);
    return unsubscribe;
  }

  /**
   * Subscribe to sibling agent status changes
   */
  onSiblingStatus(cb: (agentId: string, status: AgentStatus) => void): () => void {
    const pattern = 'agent:*:status';
    const unsubscribe = this.cache.subscribe(pattern, (_key, value) => {
      const status = value as AgentStatus;
      // Same parent, different agent, same parentType
      if (
        status.agentId !== this.agentId &&
        status.parentId === this.parentId &&
        status.parentType === this.parentType
      ) {
        cb(status.agentId, status);
      }
    });
    this.unsubscribers.push(unsubscribe);
    return unsubscribe;
  }

  /**
   * Get parent agent's status (null if parent is session)
   */
  getParentStatus(): AgentStatus | null {
    if (this.parentType === 'session' || !this.parentId) {
      return null;
    }
    return this.cache.get<AgentStatus>(`agent:${this.parentId}:status`);
  }

  /**
   * Get all child agent statuses
   * Uses parent→children reverse index for O(1) child lookup
   */
  getChildStatuses(): Map<string, AgentStatus> {
    const result = new Map<string, AgentStatus>();

    // Use the parent→children reverse index for O(1) lookup
    const parentChildrenKey = `parent:${this.agentId}:children`;
    const childIds = this.cache.get<string[]>(parentChildrenKey) ?? [];

    for (const agentId of childIds) {
      const status = this.cache.get<AgentStatus>(`agent:${agentId}:status`);
      if (status) {
        result.set(agentId, status);
      }
    }

    return result;
  }

  /**
   * Get all sibling agent statuses (excluding self)
   */
  getSiblingStatuses(): Map<string, AgentStatus> {
    const result = new Map<string, AgentStatus>();
    const sessionAgents = this.cache.get<string[]>(`session:${this.rootSessionId}:agents`) ?? [];

    for (const agentId of sessionAgents) {
      if (agentId === this.agentId) continue;

      const status = this.cache.get<AgentStatus>(`agent:${agentId}:status`);
      if (
        status &&
        status.parentId === this.parentId &&
        status.parentType === this.parentType
      ) {
        result.set(agentId, status);
      }
    }

    return result;
  }

  /**
   * List agents with optional filtering
   * @param options Filter options: children, siblings, parent, all; and status filter
   * @returns Array of agent statuses
   */
  listAgents(options?: AgentDiscoveryOptions): AgentStatus[] {
    const filter = options?.filter ?? 'all';
    const statusFilter = options?.status;

    let agents: AgentStatus[] = [];

    switch (filter) {
      case 'children':
        agents = Array.from(this.getChildStatuses().values());
        break;
      case 'siblings':
        agents = Array.from(this.getSiblingStatuses().values());
        break;
      case 'parent':
        const parent = this.getParentStatus();
        agents = parent ? [parent] : [];
        break;
      case 'all':
      default:
        // Get all agents in session
        const sessionAgents = this.cache.get<string[]>(`session:${this.rootSessionId}:agents`) ?? [];
        for (const agentId of sessionAgents) {
          const status = this.cache.get<AgentStatus>(`agent:${agentId}:status`);
          if (status) {
            agents.push(status);
          }
        }
        break;
    }

    // Apply status filter if provided
    if (statusFilter) {
      agents = agents.filter(a => a.state === statusFilter);
    }

    return agents;
  }

  /**
   * Wait for agent to reach a specific state
   */
  waitForAgent(
    agentId: string,
    state: AgentState,
    timeoutMs: number = DEFAULT_WAIT_TIMEOUT,
  ): Promise<AgentStatus> {
    return new Promise((resolve, reject) => {
      // Check if already in desired state
      const currentStatus = this.cache.get<AgentStatus>(`agent:${agentId}:status`);
      if (currentStatus?.state === state) {
        resolve(currentStatus);
        return;
      }

      let unsubscribe: (() => void) | null = null;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;

      const cleanup = () => {
        if (unsubscribe) unsubscribe();
        if (timeoutId) clearTimeout(timeoutId);
      };

      // Set timeout
      timeoutId = setTimeout(() => {
        cleanup();
        reject(new Error(`Timeout waiting for agent ${agentId} to reach state ${state}`));
      }, timeoutMs);

      // Subscribe to status changes
      unsubscribe = this.cache.subscribe(`agent:${agentId}:status`, (_key, value) => {
        const status = value as AgentStatus;
        if (status.state === state) {
          cleanup();
          resolve(status);
        }
      });
    });
  }

  /**
   * Send message to another agent
   */
  send(targetAgentId: string, message: unknown): void {
    const key = `agent:${targetAgentId}:inbox`;
    const inbox = this.cache.get<AgentMessage[]>(key) ?? [];

    const msg: AgentMessage = {
      fromAgentId: this.agentId,
      message,
      timestamp: new Date().toISOString(),
    };

    inbox.push(msg);
    this.cache.set(key, inbox, TTL.INBOX);
  }

  /**
   * Subscribe to incoming messages
   */
  onMessage(cb: (fromAgentId: string, message: unknown) => void): () => void {
    const pattern = `agent:${this.agentId}:inbox`;
    let lastMessageCount = 0;

    // Get initial count
    const currentInbox = this.cache.get<AgentMessage[]>(pattern);
    if (currentInbox) {
      lastMessageCount = currentInbox.length;
    }

    const unsubscribe = this.cache.subscribe(pattern, (_key, value) => {
      const inbox = value as AgentMessage[];
      if (inbox && inbox.length > lastMessageCount) {
        const newMessages = inbox.slice(lastMessageCount);
        for (const msg of newMessages) {
          cb(msg.fromAgentId, msg.message);
        }
        lastMessageCount = inbox.length;
      }
    });

    this.unsubscribers.push(unsubscribe);
    return unsubscribe;
  }

  /**
   * Destroy the agent radio and clean up
   */
  destroy(): void {
    // Unsubscribe from all subscriptions
    for (const unsubscribe of this.unsubscribers) {
      unsubscribe();
    }
    this.unsubscribers = [];

    // Remove from session agents list
    const sessionKey = `session:${this.rootSessionId}:agents`;
    const sessionAgents = this.cache.get<string[]>(sessionKey);
    if (sessionAgents) {
      const filteredAgents = sessionAgents.filter(id => id !== this.agentId);
      if (filteredAgents.length > 0) {
        this.cache.set(sessionKey, filteredAgents, TTL.SESSION_AGENTS);
      } else {
        this.cache.delete(sessionKey);
      }
    }

    // Remove from parent's children list
    if (this.parentId && this.parentType === 'agent') {
      const parentChildrenKey = `parent:${this.parentId}:children`;
      const children = this.cache.get<string[]>(parentChildrenKey);
      if (children) {
        const filteredChildren = children.filter(id => id !== this.agentId);
        if (filteredChildren.length > 0) {
          this.cache.set(parentChildrenKey, filteredChildren, TTL.SESSION_AGENTS);
        } else {
          this.cache.delete(parentChildrenKey);
        }
      }

      // Notify parent of child destruction by sending a message
      const destructionMessage = {
        type: 'child_destroyed',
        childAgentId: this.agentId,
        timestamp: new Date().toISOString(),
      };
      const parentInboxKey = `agent:${this.parentId}:inbox`;
      const parentInbox = this.cache.get<AgentMessage[]>(parentInboxKey) ?? [];
      parentInbox.push({
        fromAgentId: this.agentId,
        message: destructionMessage,
        timestamp: new Date().toISOString(),
      });
      this.cache.set(parentInboxKey, parentInbox, TTL.INBOX);
    }

    // Clean up this agent's own children list (if any)
    this.cache.delete(`parent:${this.agentId}:children`);

    // Clean up agent data
    this.cache.delete(`agent:${this.agentId}:status`);
    this.cache.delete(`agent:${this.agentId}:progress`);
    this.cache.delete(`agent:${this.agentId}:result`);
    this.cache.delete(`agent:${this.agentId}:inbox`);
  }
}
