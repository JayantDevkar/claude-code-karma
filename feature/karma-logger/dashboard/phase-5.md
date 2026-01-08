# Phase 5: Web Server & SSE

**Status:** Complete
**Depends On:** Phase 1-4 (TUI Complete), MVP_PLAN.md (CLI Core)
**Blocks:** Phase 6

---

## Objective

Set up Hono web server with SSE streaming and API routes for metrics.

---

## Scope

### In Scope
- Install Hono dependency
- Create `src/dashboard/server.ts` with routes
- Implement SSE endpoint for real-time updates
- API routes: `/api/session`, `/api/sessions`
- Serve static files from `public/`
- Integrate with existing aggregator

### Out of Scope
- Frontend UI (Phase 6)
- Charts and visualizations (Phase 6)
- `karma dashboard` command (Phase 6)

---

## Implementation

### 1. Dependencies

```bash
npm install hono@^4.0.0
```

### 2. Directory Structure

```
karma-logger/src/dashboard/
├── server.ts           # Hono routes
├── sse.ts              # Event streaming
├── api.ts              # API route handlers
└── public/             # Static files (created in Phase 6)
    └── .gitkeep
```

### 3. SSE Manager

```ts
// src/dashboard/sse.ts
import type { Context } from 'hono';
import { aggregator } from '../aggregator.js';

interface SSEClient {
  id: string;
  controller: ReadableStreamDefaultController;
}

class SSEManager {
  private clients: Map<string, SSEClient> = new Map();
  private unsubscribe: (() => void) | null = null;

  constructor() {
    this.startListening();
  }

  private startListening() {
    this.unsubscribe = aggregator.subscribe((data) => {
      this.broadcast({
        type: 'metrics',
        data: {
          tokensIn: data.inputTokens,
          tokensOut: data.outputTokens,
          cost: data.cost,
          timestamp: Date.now(),
        },
      });
    });

    aggregator.subscribeTree((tree) => {
      this.broadcast({
        type: 'agents',
        data: tree,
      });
    });
  }

  private broadcast(event: { type: string; data: unknown }) {
    const message = `event: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`;

    for (const client of this.clients.values()) {
      try {
        client.controller.enqueue(new TextEncoder().encode(message));
      } catch {
        this.clients.delete(client.id);
      }
    }
  }

  createStream(clientId: string): ReadableStream {
    return new ReadableStream({
      start: (controller) => {
        this.clients.set(clientId, { id: clientId, controller });

        // Send initial state
        const initial = aggregator.getMetrics();
        const message = `event: init\ndata: ${JSON.stringify(initial)}\n\n`;
        controller.enqueue(new TextEncoder().encode(message));
      },
      cancel: () => {
        this.clients.delete(clientId);
      },
    });
  }

  getClientCount(): number {
    return this.clients.size;
  }
}

export const sseManager = new SSEManager();
```

### 4. API Routes

```ts
// src/dashboard/api.ts
import { Hono } from 'hono';
import { aggregator } from '../aggregator.js';
import { sessionStore } from '../session.js';

export const apiRoutes = new Hono();

// Current session metrics
apiRoutes.get('/session', (c) => {
  const metrics = aggregator.getMetrics();
  const tree = aggregator.getAgentTree();

  return c.json({
    sessionId: aggregator.getSessionId(),
    metrics: {
      tokensIn: metrics.inputTokens,
      tokensOut: metrics.outputTokens,
      cost: metrics.cost,
    },
    agents: tree,
    startedAt: aggregator.getStartTime(),
  });
});

// Historical sessions
apiRoutes.get('/sessions', async (c) => {
  const limit = parseInt(c.req.query('limit') || '10');
  const sessions = await sessionStore.getRecent(limit);

  return c.json({
    sessions: sessions.map((s) => ({
      id: s.id,
      project: s.project,
      agentCount: s.agentCount,
      tokensTotal: s.inputTokens + s.outputTokens,
      cost: s.cost,
      startedAt: s.startedAt,
      endedAt: s.endedAt,
    })),
  });
});

// Health check
apiRoutes.get('/health', (c) => {
  return c.json({ status: 'ok', clients: sseManager.getClientCount() });
});
```

### 5. Main Server

```ts
// src/dashboard/server.ts
import { Hono } from 'hono';
import { serveStatic } from 'hono/serve-static';
import { cors } from 'hono/cors';
import { apiRoutes } from './api.js';
import { sseManager } from './sse.js';
import { randomUUID } from 'crypto';

const app = new Hono();

// Middleware
app.use('/*', cors());

// SSE endpoint
app.get('/events', (c) => {
  const clientId = randomUUID();
  const stream = sseManager.createStream(clientId);

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
});

// API routes
app.route('/api', apiRoutes);

// Static files (Phase 6)
app.get('/*', serveStatic({ root: './src/dashboard/public' }));

export interface ServerOptions {
  port?: number;
  open?: boolean;
}

export async function startServer(options: ServerOptions = {}): Promise<void> {
  const port = options.port || 3333;

  console.log(`Starting Karma Dashboard at http://localhost:${port}`);

  // Using Node.js built-in fetch-compatible serve
  const { serve } = await import('@hono/node-server');
  serve({ fetch: app.fetch, port });

  if (options.open) {
    const { exec } = await import('child_process');
    exec(`open http://localhost:${port}`);
  }
}

export { app };
```

### 6. Integration Hook

```ts
// src/dashboard/index.ts
export { startServer } from './server.js';
export { sseManager } from './sse.js';
```

---

## Success Criteria

1. Hono server starts in <200ms
2. `/api/session` returns current metrics
3. `/api/sessions` returns historical data
4. `/events` establishes SSE connection
5. SSE pushes updates on aggregator changes
6. Clients receive `init`, `metrics`, `agents` events
7. Server handles multiple concurrent clients

---

## Test Plan

```ts
// tests/dashboard/server.test.ts
import { app } from '../../src/dashboard/server.js';

describe('Dashboard Server', () => {
  it('GET /api/session returns metrics', async () => {
    const res = await app.request('/api/session');
    expect(res.status).toBe(200);

    const data = await res.json();
    expect(data).toHaveProperty('sessionId');
    expect(data).toHaveProperty('metrics');
  });

  it('GET /api/health returns ok', async () => {
    const res = await app.request('/api/health');
    const data = await res.json();
    expect(data.status).toBe('ok');
  });
});

// tests/dashboard/sse.test.ts
describe('SSE Manager', () => {
  it('creates readable stream', () => {
    const stream = sseManager.createStream('test-client');
    expect(stream).toBeInstanceOf(ReadableStream);
  });

  it('tracks client count', () => {
    const initial = sseManager.getClientCount();
    sseManager.createStream('test-client-2');
    expect(sseManager.getClientCount()).toBe(initial + 1);
  });
});
```

---

## API Reference

### GET /api/session

Returns current session metrics.

```json
{
  "sessionId": "abc123",
  "metrics": {
    "tokensIn": 124500,
    "tokensOut": 45200,
    "cost": 234
  },
  "agents": { /* agent tree */ },
  "startedAt": "2026-01-08T10:00:00Z"
}
```

### GET /api/sessions?limit=10

Returns recent session history.

```json
{
  "sessions": [
    {
      "id": "abc123",
      "project": "karma-logger",
      "agentCount": 4,
      "tokensTotal": 169700,
      "cost": 234,
      "startedAt": "2026-01-08T10:00:00Z",
      "endedAt": "2026-01-08T10:30:00Z"
    }
  ]
}
```

### GET /events

SSE stream with events:
- `init` - Initial state on connect
- `metrics` - Real-time metric updates
- `agents` - Agent tree changes

---

## Acceptance

- [x] Hono installed
- [x] server.ts created with routes
- [x] sse.ts implements SSE streaming
- [x] api.ts handles session endpoints
- [x] Server starts and responds
- [x] SSE connection works
- [x] Tests pass
