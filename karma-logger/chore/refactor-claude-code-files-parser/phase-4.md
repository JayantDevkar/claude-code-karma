# Phase 4: Extract Extractors

**Status**: Complete
**Depends on**: Phase 2
**Parallel with**: Phase 3, Phase 5
**Unlocks**: Phase 6

## Objective

Extract content extraction functions into dedicated modules.

## Tasks

- [x] Create `src/extractors/tool-calls.ts`
- [x] Create `src/extractors/thinking.ts`
- [x] Create `src/extractors/agents.ts`
- [x] Create `src/extractors/index.ts`
- [x] Update `src/index.ts` exports
- [x] Verify build

## Source Mapping

From `karma-logger/src/parser.ts`:

| Function | Target File |
|----------|-------------|
| `extractToolCalls()` | `extractors/tool-calls.ts` |
| `getToolUsageCounts()` | `extractors/tool-calls.ts` |
| `hasThinkingContent()` | `extractors/thinking.ts` |
| `extractAgentSpawns()` | `extractors/agents.ts` |
| `AgentSpawnInfo` interface | `extractors/agents.ts` |

## Files to Create

### src/extractors/tool-calls.ts

```typescript
/**
 * Tool call extraction from Claude Code content blocks
 */

import type { ContentBlock, ToolUseBlock, LogEntry } from '../types/index.js';

/**
 * Extract tool call names from content blocks
 */
export function extractToolCalls(content: ContentBlock[]): string[] {
  return content
    .filter((block): block is ToolUseBlock => block.type === 'tool_use')
    .map(block => block.name);
}

/**
 * Get tool usage counts from entries
 */
export function getToolUsageCounts(entries: LogEntry[]): Map<string, number> {
  const counts = new Map<string, number>();

  for (const entry of entries) {
    for (const tool of entry.toolCalls) {
      counts.set(tool, (counts.get(tool) ?? 0) + 1);
    }
  }

  return counts;
}
```

### src/extractors/thinking.ts

```typescript
/**
 * Thinking block detection in Claude Code content
 */

import type { ContentBlock } from '../types/index.js';

/**
 * Check if content contains thinking blocks
 */
export function hasThinkingContent(content: ContentBlock[]): boolean {
  return content.some(block => block.type === 'thinking');
}

/**
 * Extract thinking text from content blocks
 */
export function extractThinkingText(content: ContentBlock[]): string[] {
  return content
    .filter(block => block.type === 'thinking')
    .map(block => (block as { thinking: string }).thinking);
}
```

### src/extractors/agents.ts

```typescript
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
 *
 * Parses Task tool_use blocks (in assistant entries) to get subagent_type,
 * then matches with tool_result blocks (in user entries) to get agentId.
 *
 * Returns a map of agentId -> AgentSpawnInfo
 */
export async function extractAgentSpawns(filePath: string): Promise<Map<string, AgentSpawnInfo>> {
  const spawns = new Map<string, AgentSpawnInfo>();

  // Track Task tool calls by their tool_use_id
  const pendingTasks = new Map<string, { subagentType: string; description: string }>();

  const rl = createInterface({
    input: createReadStream(filePath),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    try {
      const entry = JSON.parse(line);

      // Look for Task tool_use in assistant entries
      if (entry.type === 'assistant' && entry.message?.content) {
        for (const block of entry.message.content) {
          if (block.type === 'tool_use' && block.name === 'Task' && block.input) {
            const subagentType = block.input.subagent_type || 'task';
            const description = block.input.description || '';
            pendingTasks.set(block.id, { subagentType, description });
          }
        }
      }

      // Look for tool_result in user entries to get agentId
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
```

### src/extractors/index.ts

```typescript
// Tool calls
export { extractToolCalls, getToolUsageCounts } from './tool-calls.js';

// Thinking
export { hasThinkingContent, extractThinkingText } from './thinking.js';

// Agents
export { extractAgentSpawns } from './agents.js';
export type { AgentSpawnInfo } from './agents.js';
```

### Update src/index.ts

Add to exports:

```typescript
// Extractors
export {
  extractToolCalls,
  getToolUsageCounts,
  hasThinkingContent,
  extractThinkingText,
  extractAgentSpawns,
} from './extractors/index.js';
export type { AgentSpawnInfo } from './extractors/index.js';
```

## Validation

```bash
npm run build
# All extractor functions should be importable
```

## Outputs

- [x] `src/extractors/tool-calls.ts` created
- [x] `src/extractors/thinking.ts` created
- [x] `src/extractors/agents.ts` created
- [x] `src/extractors/index.ts` created
- [x] All functions exported from main `index.ts`
- [x] Build passes

## Estimated Effort

~25 minutes
