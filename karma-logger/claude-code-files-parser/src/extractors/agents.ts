/**
 * Agent spawn extraction from Claude Code sessions
 */

import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';

/**
 * Agent spawn info extracted from Task tool calls
 */
export interface AgentSpawnInfo {
  agentId: string;
  subagentType: string;
  description: string;
  toolUseId: string;
}

/**
 * Extract agent spawn information from a session file
 */
export async function extractAgentSpawns(filePath: string): Promise<Map<string, AgentSpawnInfo>> {
  const spawns = new Map<string, AgentSpawnInfo>();
  const pendingTasks = new Map<string, { subagentType: string; description: string }>();

  const rl = createInterface({
    input: createReadStream(filePath),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    try {
      const entry = JSON.parse(line);

      if (entry.type === 'assistant' && entry.message?.content) {
        for (const block of entry.message.content) {
          if (block.type === 'tool_use' && block.name === 'Task' && block.input) {
            const subagentType = block.input.subagent_type || 'task';
            const description = block.input.description || '';
            pendingTasks.set(block.id, { subagentType, description });
          }
        }
      }

      if (entry.type === 'user' && entry.message?.content) {
        for (const block of entry.message.content) {
          if (block.type === 'tool_result' && block.tool_use_id) {
            const pending = pendingTasks.get(block.tool_use_id);
            if (pending) {
              const resultText = typeof block.content === 'string'
                ? block.content
                : JSON.stringify(block.content);

              const agentIdMatch = resultText.match(/agentId:\s*([a-f0-9]{7})/i);
              if (agentIdMatch) {
                const agentId = agentIdMatch[1];
                spawns.set(agentId, {
                  agentId,
                  subagentType: pending.subagentType,
                  description: pending.description,
                  toolUseId: block.tool_use_id,
                });
              }
              pendingTasks.delete(block.tool_use_id);
            }
          }
        }
      }
    } catch {
      // Skip malformed lines
    }
  }

  return spawns;
}
