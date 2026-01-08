/**
 * Hono Web Server for Dashboard
 * Phase 5: Main server with SSE and API routes
 */

import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { randomUUID } from 'node:crypto';
import { createApiRoutes } from './api.js';
import { sseManager, SSEManager } from './sse.js';
import type { MetricsAggregator } from '../aggregator.js';
import type { LogWatcher } from '../watcher.js';

export interface ServerOptions {
  port?: number;
  open?: boolean;
  watcher?: LogWatcher;
  aggregator?: MetricsAggregator;
  sessionId?: string;
}

interface ServerInstance {
  app: Hono;
  server: ReturnType<typeof import('@hono/node-server').serve> | null;
  sseManager: SSEManager;
  stop: () => Promise<void>;
}

/**
 * Create the Hono app with all routes
 */
export function createApp(aggregator: MetricsAggregator): Hono {
  const app = new Hono();

  // CORS middleware
  app.use('/*', cors({
    origin: '*',
    allowMethods: ['GET', 'POST', 'OPTIONS'],
    allowHeaders: ['Content-Type'],
  }));

  // SSE endpoint for real-time updates
  app.get('/events', (c) => {
    const clientId = randomUUID();
    const stream = sseManager.createStream(clientId);

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no', // Disable nginx buffering
      },
    });
  });

  // API routes
  const apiRoutes = createApiRoutes(aggregator);
  app.route('/api', apiRoutes);

  // Root route - show basic info until Phase 6 adds UI
  app.get('/', (c) => {
    const totals = aggregator.getTotals();
    return c.html(`
<!DOCTYPE html>
<html>
<head>
  <title>Karma Dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 2rem auto; padding: 0 1rem; }
    h1 { color: #333; }
    .metric { margin: 1rem 0; padding: 1rem; background: #f5f5f5; border-radius: 8px; }
    .label { color: #666; font-size: 0.875rem; }
    .value { font-size: 1.5rem; font-weight: bold; color: #333; }
    code { background: #e5e5e5; padding: 0.2rem 0.4rem; border-radius: 4px; }
    .endpoints { margin-top: 2rem; }
    .endpoints li { margin: 0.5rem 0; }
  </style>
</head>
<body>
  <h1>Karma Dashboard</h1>
  <p>Real-time metrics for Claude Code sessions.</p>

  <div class="metric">
    <div class="label">Sessions</div>
    <div class="value">${totals.sessions}</div>
  </div>

  <div class="metric">
    <div class="label">Total Tokens</div>
    <div class="value">${(totals.tokensIn + totals.tokensOut).toLocaleString()}</div>
  </div>

  <div class="metric">
    <div class="label">Estimated Cost</div>
    <div class="value">$${(totals.totalCost / 100).toFixed(4)}</div>
  </div>

  <div class="endpoints">
    <h2>API Endpoints</h2>
    <ul>
      <li><code>GET /api/session</code> - Current session metrics</li>
      <li><code>GET /api/sessions</code> - All sessions</li>
      <li><code>GET /api/totals</code> - Aggregated totals</li>
      <li><code>GET /api/health</code> - Health check</li>
      <li><code>GET /events</code> - SSE stream</li>
    </ul>
  </div>

  <p style="margin-top: 2rem; color: #666;">
    Full UI coming in Phase 6. For now, use <code>karma watch --ui</code> for TUI.
  </p>
</body>
</html>
    `);
  });

  return app;
}

/**
 * Start the dashboard server
 */
export async function startServer(options: ServerOptions = {}): Promise<ServerInstance> {
  const port = options.port ?? 3333;

  // Validate we have required dependencies
  if (!options.watcher || !options.aggregator) {
    throw new Error('Dashboard server requires watcher and aggregator');
  }

  // Connect SSE manager to watcher/aggregator
  sseManager.connect(options.watcher, options.aggregator, options.sessionId);

  // Create app
  const app = createApp(options.aggregator);

  // Start server
  const { serve } = await import('@hono/node-server');
  const server = serve({
    fetch: app.fetch,
    port,
  });

  console.log(`Karma Dashboard running at http://localhost:${port}`);

  // Open browser if requested
  if (options.open) {
    const { exec } = await import('node:child_process');
    const platform = process.platform;
    const cmd = platform === 'darwin' ? 'open' :
                platform === 'win32' ? 'start' : 'xdg-open';
    exec(`${cmd} http://localhost:${port}`);
  }

  return {
    app,
    server,
    sseManager,
    stop: async () => {
      sseManager.disconnect();
      if (server && typeof server.close === 'function') {
        server.close();
      }
    },
  };
}

export { sseManager };
