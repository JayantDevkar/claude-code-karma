/**
 * Walkie-Talkie Module Exports
 * Phase 1: Core cache store for agent communication
 * Phase 2: Agent radio for status and messaging
 * Phase 3: Radio CLI socket client
 * Phase 4: Subscription-based wait for agent status
 * Phase 5: Socket server for aggregator integration + Metadata Schema Validation
 * Phase 6: Cache persistence (6.1: Write-Ahead Log, 6.2: Snapshot, 6.3: Recovery)
 */

export { MemoryCacheStore } from './cache-store.js';
export { AgentRadioImpl } from './agent-radio.js';
export {
  RadioClient,
  RadioServerNotRunningError,
  RadioTimeoutError,
  RadioServerError,
  SubscriptionError,
  createRadioClient,
  getDefaultSocketPath,
} from './socket-client.js';
export {
  startRadioServer,
  handleRadioRequest,
  getDefaultRadioSocketPath,
  SubscriptionManager,
  type RadioServerOptions,
  type RadioServer,
} from './socket-server.js';
// Phase 5: Schema Registry exports
export {
  SchemaRegistry,
  schemaRegistry,
  validateMetadata,
  TASK_AGENT_SCHEMA,
  EXPLORE_AGENT_SCHEMA,
} from './schema-registry.js';
// Phase 6.1: Write-Ahead Log exports
export { WriteAheadLog } from './wal.js';
export type { WALEntry, WALOptions } from './wal.js';
// Phase 6.2: Snapshot mechanism exports
export { SnapshotManager } from './snapshot.js';
export type { SnapshotMeta, SnapshotEntry, SnapshotData } from './snapshot.js';
// Phase 6.3: Persistent Cache Store exports
export { PersistentCacheStore } from './persistent-cache.js';
export type { PersistentCacheOptions } from './persistent-cache.js';

export type {
  CacheStore,
  CacheStats,
  SubscriberCallback,
  AgentState,
  AgentStatus,
  ProgressUpdate,
  AgentMessage,
  AgentRadio,
  RadioCommand,
  RadioEnv,
  RadioRequest,
  RadioResponse,
  // Phase 4: Subscription types
  SubscribeMessage,
  UnsubscribeMessage,
  SubscribedMessage,
  NotificationMessage,
  KeepAliveMessage,
  ServerPushMessage,
  // Phase 5: Schema Validation types
  MetadataSchema,
  MetadataPropertyType,
  MetadataPropertySpec,
  ValidationResult,
  ValidationMode,
} from './types.js';
