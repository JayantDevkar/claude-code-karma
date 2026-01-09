/**
 * React Hook for Agent Radio Status
 * Phase 5 (Walkie-Talkie): Real-time agent status updates from cache
 */

import { useContext, useState, useEffect } from 'react';
import { AggregatorContext } from '../context/AggregatorContext.js';
import type { AgentStatus } from '../../walkie-talkie/types.js';

/**
 * Hook to get all agent statuses from the radio cache
 *
 * Provides real-time updates when agent statuses change.
 * Returns an empty Map if radio is not enabled.
 *
 * @returns Map of agentId to AgentStatus
 *
 * @example
 * ```tsx
 * const statuses = useAgentStatuses();
 *
 * for (const [agentId, status] of statuses) {
 *   console.log(`${agentId}: ${status.state}`);
 * }
 * ```
 */
export function useAgentStatuses(): Map<string, AgentStatus> {
  const context = useContext(AggregatorContext);
  const aggregator = context?.aggregator ?? null;

  const [statuses, setStatuses] = useState<Map<string, AgentStatus>>(new Map());

  useEffect(() => {
    if (!aggregator) {
      setStatuses(new Map());
      return;
    }

    // Initial load from cache
    const cache = aggregator.getCache();
    if (cache) {
      const initial = cache.getMany('agent:*:status');
      const parsed = new Map<string, AgentStatus>();
      for (const [key, value] of initial) {
        const agentId = key.split(':')[1];
        parsed.set(agentId, value as AgentStatus);
      }
      setStatuses(parsed);
    }

    // Subscribe to changes
    const unsub = aggregator.onAgentStatusChange((agentId: string, status: AgentStatus) => {
      setStatuses(prev => {
        const next = new Map(prev);
        next.set(agentId, status);
        return next;
      });
    });

    return () => {
      unsub();
    };
  }, [aggregator]);

  return statuses;
}

/**
 * Hook to get a specific agent's status
 *
 * Provides real-time updates when the agent's status changes.
 * Returns null if agent not found or radio not enabled.
 *
 * @param agentId The agent ID to watch
 * @returns AgentStatus or null
 *
 * @example
 * ```tsx
 * const status = useAgentStatus('agent-123');
 *
 * if (status) {
 *   console.log(`Agent is ${status.state}`);
 * }
 * ```
 */
export function useAgentStatus(agentId: string): AgentStatus | null {
  const context = useContext(AggregatorContext);
  const aggregator = context?.aggregator ?? null;

  const [status, setStatus] = useState<AgentStatus | null>(null);

  useEffect(() => {
    if (!aggregator || !agentId) {
      setStatus(null);
      return;
    }

    // Initial load
    const initial = aggregator.getAgentStatus(agentId);
    setStatus(initial);

    // Subscribe to changes
    const unsub = aggregator.onAgentStatusChange((changedAgentId: string, newStatus: AgentStatus) => {
      if (changedAgentId === agentId) {
        setStatus(newStatus);
      }
    });

    return () => {
      unsub();
    };
  }, [aggregator, agentId]);

  return status;
}

/**
 * Hook to check if radio is enabled
 *
 * @returns true if radio is enabled on the aggregator
 */
export function useRadioEnabled(): boolean {
  const context = useContext(AggregatorContext);
  const aggregator = context?.aggregator ?? null;

  return aggregator?.isRadioEnabled() ?? false;
}
