/**
 * Hono Web Server for Dashboard
 * Phase 5/6: Main server with SSE, API routes, and static file serving
 */

import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createApiRoutes } from './api.js';
import { sseManager, SSEManager } from './sse.js';
import type { MetricsAggregator } from '../aggregator.js';
import type { LogWatcher } from '../watcher.js';

// Get the directory of this file (works in both src and dist)
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Resolve public directory path (handles both dev and built scenarios)
// In dev: __dirname is src/dashboard, public is at src/dashboard/public
// In dist: __dirname is dist/dashboard, but static files are in src/dashboard/public
function getPublicPath(): string {
  // Check if we're running from dist (compiled) or src (dev)
  if (__dirname.includes('/dist/')) {
    // Running from dist, go up to project root and into src
    return join(__dirname, '../../src/dashboard/public');
  }
  // Running from src (dev mode with tsx)
  return join(__dirname, 'public');
}

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

  // Serve static files from public directory
  // Use custom middleware for absolute path support
  app.get('/*', async (c) => {
    const publicPath = getPublicPath();
    let requestPath = c.req.path;

    // Serve index.html for root path
    if (requestPath === '/') {
      requestPath = '/index.html';
    }

    const filePath = join(publicPath, requestPath);

    try {
      const fs = await import('node:fs/promises');

      // Security: ensure the resolved path is within publicPath
      const { resolve } = await import('node:path');
      const resolvedFile = resolve(filePath);
      const resolvedPublic = resolve(publicPath);
      if (!resolvedFile.startsWith(resolvedPublic)) {
        return c.text('Forbidden', 403);
      }

      const content = await fs.readFile(filePath);

      // Determine content type
      const ext = requestPath.split('.').pop()?.toLowerCase();
      const contentTypes: Record<string, string> = {
        'html': 'text/html; charset=utf-8',
        'css': 'text/css; charset=utf-8',
        'js': 'application/javascript; charset=utf-8',
        'json': 'application/json; charset=utf-8',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'svg': 'image/svg+xml',
        'ico': 'image/x-icon',
      };

      const contentType = contentTypes[ext || ''] || 'application/octet-stream';

      return new Response(content, {
        headers: {
          'Content-Type': contentType,
          'Cache-Control': 'no-cache',
        },
      });
    } catch (err: unknown) {
      const error = err as NodeJS.ErrnoException;
      if (error.code === 'ENOENT') {
        return c.text('Not Found', 404);
      }
      console.error('Static file error:', err);
      return c.text('Internal Server Error', 500);
    }
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
