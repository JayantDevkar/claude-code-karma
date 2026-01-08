# Phase 5: Aggregator Integration

## Objective

Integrate walkie-talkie cache into karma-logger's existing architecture. Enable real-time agent status in `karma watch` and dashboard without file polling.

## Dependencies

- **Phase 2**: AgentRadio (core communication)
- **Phase 3**: Socket server running (optional, enhances integration)

## Deliverables

```
src/
├── aggregator.ts           # Enhanced with radio support
├── commands/
│   └── watch.ts            # Radio-aware watch mode
└── dashboard/
    ├── api.ts              # New /api/radio/* endpoints
    └── sse.ts              # Agent status events
```

## Tasks

### 5.1 Enhance MetricsAggregator

```typescript
// src/aggregator.ts additions

import { CacheStore, MemoryCacheStore } from './walkie-talkie/cache-store';
import { AgentRadio, AgentRadioImpl, AgentStatus } from './walkie-talkie/agent-radio';

interface AggregatorOptions {
  enableRadio?: boolean;
  radioSocketPath?: string;
}

class MetricsAggregator {
  private cache: CacheStore | null = null;
  private agentRadios: Map<string, AgentRadio> = new Map();

  constructor(options: AggregatorOptions = {}) {
    // ... existing constructor ...

    if (options.enableRadio) {
      this.cache = new MemoryCacheStore();
    }
  }

  // Enhanced: Register agent with radio
  registerAgent(agent: SessionInfo, parentSession: SessionInfo): void {
    const metrics = this.getOrCreateAgentMetrics(agent, parentSession);

    if (this.cache) {
      const radio = new AgentRadioImpl(
        this.cache,
        agent.sessionId,
        parentSession.sessionId,
        agent.parentSessionId || null,
        agent.agentType || 'unknown',
        agent.model || 'unknown'
      );
      radio.setStatus('active');
      this.agentRadios.set(agent.sessionId, radio);
    }
  }

  // New: Get status from cache (faster than file parsing)
  getAgentStatus(agentId: string): AgentStatus | null {
    return this.cache?.get<AgentStatus>(`agent:${agentId}:status`) || null;
  }

  // New: Subscribe to all status changes
  onAgentStatusChange(
    callback: (agentId: string, status: AgentStatus) => void
  ): () => void {
    if (!this.cache) return () => {};

    return this.cache.subscribe('agent:*:status', (key, value) => {
      const agentId = key.split(':')[1];
      callback(agentId, value as AgentStatus);
    });
  }

  // New: Get radio for specific agent
  getAgentRadio(agentId: string): AgentRadio | null {
    return this.agentRadios.get(agentId) || null;
  }

  // New: Get cache for direct queries
  getCache(): CacheStore | null {
    return this.cache;
  }

  // Enhanced: cleanup radios for ended sessions
  clearEndedSessions(): void {
    // ... existing session cleanup ...

    // Clean up radios for ended sessions
    for (const [agentId, radio] of this.agentRadios) {
      if (/* agent session ended */) {
        radio.destroy();
        this.agentRadios.delete(agentId);
      }
    }
  }

  // Enhanced: cleanup
  destroy(): void {
    // ... existing cleanup ...

    for (const radio of this.agentRadios.values()) {
      radio.destroy();
    }
    this.agentRadios.clear();
    this.cache?.clear();
  }
}
```

### 5.2 Enhance Watch Command

```typescript
// src/commands/watch.ts additions

import { createServer, Server } from 'net';

interface WatchOptions {
  ui?: boolean;
  radio?: boolean;  // New flag
  // ... existing options
}

async function watch(options: WatchOptions): Promise<void> {
  const aggregator = new MetricsAggregator({
    enableRadio: options.radio !== false  // Default: enabled
  });

  let radioServer: Server | null = null;

  if (aggregator.getCache()) {
    // Start socket server for `karma radio` CLI
    radioServer = startRadioServer(aggregator);
    console.log('Radio server started at /tmp/karma-radio.sock');
  }

  // Subscribe to radio events for display
  aggregator.onAgentStatusChange((agentId, status) => {
    if (options.ui) {
      // TUI will receive via context
    } else {
      // Streaming mode: print status change
      console.log(`[${status.state}] Agent ${agentId} (${status.agentType})`);
    }
  });

  // ... existing watch logic ...

  // Cleanup on exit
  process.on('SIGINT', () => {
    radioServer?.close();
    aggregator.destroy();
    process.exit(0);
  });
}

function startRadioServer(aggregator: MetricsAggregator): Server {
  const socketPath = '/tmp/karma-radio.sock';

  // Remove stale socket
  try { fs.unlinkSync(socketPath); } catch {}

  const server = createServer((socket) => {
    let buffer = '';

    // Set socket timeout to prevent hung connections
    socket.setTimeout(5000);
    socket.on('timeout', () => socket.destroy());

    socket.on('data', (data) => {
      buffer += data.toString();

      // Reject oversized messages (>64KB)
      if (buffer.length > 65536) {
        socket.write(JSON.stringify({ error: 'Message too large' }) + '\n');
        socket.destroy();
        return;
      }

      // Handle complete messages (newline-delimited JSON)
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;

        try {
          const request = JSON.parse(line);
          const response = handleRadioRequest(request, aggregator);
          socket.write(JSON.stringify(response) + '\n');
        } catch (e) {
          socket.write(JSON.stringify({ error: 'Invalid request' }) + '\n');
        }
      }
    });
  });

  // Limit concurrent clients
  server.maxConnections = 10;

  server.listen(socketPath);

  // Set socket permissions (Unix only)
  if (process.platform !== 'win32') {
    fs.chmodSync(socketPath, 0o600); // Owner-only access
  }

  return server;
}

function handleRadioRequest(request: RadioRequest, aggregator: MetricsAggregator): RadioResponse {
  const cache = aggregator.getCache();
  if (!cache) {
    return { id: request.id, success: false, error: 'Radio not enabled' };
  }

  const { agentId, sessionId, parentId, agentType, model } = request.env;

  // Get or create radio for this agent
  let radio = aggregator.getAgentRadio(agentId);
  if (!radio) {
    radio = new AgentRadioImpl(cache, agentId, sessionId, parentId, agentType, model);
  }

  switch (request.command) {
    case 'set-status':
      radio.setStatus(request.args.state, request.args.metadata);
      return { id: request.id, success: true };

    case 'report-progress':
      radio.reportProgress(request.args);
      return { id: request.id, success: true };

    case 'get-status':
      const targetId = request.args.agentId || agentId;
      const status = cache.get(`agent:${targetId}:status`);
      return { id: request.id, success: true, data: status };

    case 'wait-for':
      // Async handled via socket staying open
      // ...

    default:
      return { id: request.id, success: false, error: 'Unknown command' };
  }
}
```

### 5.3 Dashboard API Additions

```typescript
// src/dashboard/api.ts additions

export function setupRadioRoutes(app: Hono, aggregator: MetricsAggregator): void {
  // Get all agent statuses
  app.get('/api/radio/agents', (c) => {
    const cache = aggregator.getCache();
    if (!cache) {
      return c.json({ error: 'Radio not enabled' }, 503);
    }

    const agents = cache.getMany('agent:*:status');
    return c.json(Object.fromEntries(agents));
  });

  // Get specific agent status
  app.get('/api/radio/agent/:id', (c) => {
    const agentId = c.req.param('id');
    const status = aggregator.getAgentStatus(agentId);

    if (!status) {
      return c.json({ error: 'Agent not found' }, 404);
    }

    return c.json(status);
  });

  // Get agent hierarchy for session
  app.get('/api/radio/session/:id/tree', (c) => {
    const cache = aggregator.getCache();
    const sessionId = c.req.param('id');

    const agents = cache?.get<string[]>(`session:${sessionId}:agents`) || [];
    const tree = buildAgentTree(agents, cache);

    return c.json(tree);
  });
}

function buildAgentTree(agentIds: string[], cache: CacheStore | null): AgentTreeNode[] {
  if (!cache) return [];

  const statuses = agentIds.map(id => cache.get<AgentStatus>(`agent:${id}:status`)).filter(Boolean);
  const roots = statuses.filter(s => !s.parentId);

  function buildNode(status: AgentStatus): AgentTreeNode {
    const children = statuses.filter(s => s.parentId === status.agentId);
    return {
      ...status,
      children: children.map(buildNode)
    };
  }

  return roots.map(buildNode);
}
```

### 5.4 SSE Integration

```typescript
// src/dashboard/sse.ts additions

export function setupRadioSSE(sseManager: SSEManager, aggregator: MetricsAggregator): void {
  // Broadcast agent status changes to all clients
  aggregator.onAgentStatusChange((agentId, status) => {
    sseManager.broadcast({
      event: 'agent:status',
      data: { agentId, ...status }
    });
  });

  // Broadcast progress updates
  aggregator.getCache()?.subscribe('agent:*:progress', (key, value) => {
    const agentId = key.split(':')[1];
    sseManager.broadcast({
      event: 'agent:progress',
      data: { agentId, ...value as object }
    });
  });
}
```

### 5.5 TUI Integration

```typescript
// src/tui/hooks/useAgentRadio.ts

import { useContext, useState, useEffect } from 'react';
import { AggregatorContext } from '../context/AggregatorContext';
import { AgentStatus } from '../../walkie-talkie/types';

export function useAgentStatuses(): Map<string, AgentStatus> {
  const aggregator = useContext(AggregatorContext);
  const [statuses, setStatuses] = useState<Map<string, AgentStatus>>(new Map());

  useEffect(() => {
    // Initial load
    const cache = aggregator?.getCache();
    if (cache) {
      const initial = cache.getMany('agent:*:status');
      setStatuses(new Map(initial as Map<string, AgentStatus>));
    }

    // Subscribe to changes
    const unsub = aggregator?.onAgentStatusChange((agentId, status) => {
      setStatuses(prev => new Map(prev).set(agentId, status));
    });

    return () => unsub?.();
  }, [aggregator]);

  return statuses;
}
```

## TUI Integration Note

Current `karma watch` uses terminal display class (not React).
The `useAgentStatuses()` hook applies to:
- Future React-based TUI (`karma watch --ui`)
- Dashboard frontend (if implemented with React)

For current watch mode, access via `aggregator.getAgentStatuses()` directly.

## Tests

```typescript
// tests/walkie-talkie/integration.test.ts

describe('Aggregator + Radio Integration', () => {
  test('registerAgent creates radio instance');
  test('getAgentStatus returns from cache');
  test('onAgentStatusChange fires on updates');
  test('socket server handles set-status');
  test('socket server handles get-status');
  test('destroy cleans up radios and cache');
});

describe('Dashboard Radio API', () => {
  test('GET /api/radio/agents returns all statuses');
  test('GET /api/radio/agent/:id returns specific status');
  test('GET /api/radio/session/:id/tree builds hierarchy');
  test('SSE broadcasts agent:status events');
});
```

## Acceptance Criteria

- [ ] `karma watch` shows radio status updates in real-time
- [ ] Socket server accepts `karma radio` CLI connections
- [ ] Dashboard API exposes /api/radio/* endpoints
- [ ] SSE broadcasts agent status changes
- [ ] TUI displays radio-powered agent tree
- [ ] No breaking changes to existing functionality
- [ ] Radio can be disabled via flag if needed
- [ ] Radio cleanup runs on session end
- [ ] Socket permissions set to owner-only (Unix)
- [ ] Socket timeout prevents hung connections
- [ ] registerAgent() returns void (not AgentMetrics)

## Migration Notes

- Radio is **opt-in by default** (enabled with `--radio` flag initially)
- Once stable, flip to **opt-out** (`--no-radio` to disable)
- Existing file-based watching continues to work in parallel
- Cache supplements but doesn't replace JSONL parsing

## Migration Timeline

| Version | Radio Status | Flag |
|---------|--------------|------|
| v1.0.0 | Opt-in | `--radio` to enable |
| v1.1.0 | Default on | `--no-radio` to disable |
| v1.2.0 | Always on | Flag removed |

### Stability Gates for v1.1.0
- [ ] 100 watch sessions without radio crashes
- [ ] Dashboard API <20ms p95 for 1 week
- [ ] Zero memory leaks in 24-hour watch session
- [ ] All integration tests passing

## Socket Server Security

### Hardening
```typescript
// In startRadioServer():
server.maxConnections = 10;  // Limit concurrent clients
socket.setTimeout(5000);      // 5s request timeout
socket.on('timeout', () => socket.destroy());

// Set socket permissions (Unix only)
if (process.platform !== 'win32') {
  fs.chmodSync(socketPath, 0o600); // Owner-only access
}
```

### Request Validation
- Validate JSON structure before processing
- Reject oversized messages (>64KB)
- Log failed authentication attempts

## Performance Targets

| Metric | Target |
|--------|--------|
| Socket latency | <5ms |
| Status update propagation | <10ms |
| Memory overhead | <50MB for 100 agents |
| Dashboard API response | <20ms |

## Estimated Complexity

- Lines of code: ~400
- Test lines: ~300
- Risk: Medium (integration touchpoints, socket handling)
