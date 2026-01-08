/**
 * Walkie-Talkie Module Exports
 * Phase 1: Core cache store for agent communication
 * Phase 2: Agent radio for status and messaging
 * Phase 3: Radio CLI socket client
 * Phase 5: Socket server for aggregator integration
 */

export { MemoryCacheStore } from './cache-store.js';
export { AgentRadioImpl } from './agent-radio.js';
export {
  RadioClient,
  RadioServerNotRunningError,
  RadioTimeoutError,
  RadioServerError,
  createRadioClient,
  getDefaultSocketPath,
} from './socket-client.js';
export {
  startRadioServer,
  handleRadioRequest,
  getDefaultRadioSocketPath,
  type RadioServerOptions,
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
} from './types.js';
