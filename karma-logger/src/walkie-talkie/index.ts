/**
 * Walkie-Talkie Module Exports
 * Phase 1: Core cache store for agent communication
 * Phase 2: Agent radio for status and messaging
 * Phase 3: Radio CLI socket client
 * Phase 4: Subscription-based wait for agent status
 * Phase 5: Socket server for aggregator integration
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
} from './types.js';
