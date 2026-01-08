/**
 * Quick test script for dashboard server
 */

import { createApp } from '../src/dashboard/server.js';
import { MetricsAggregator } from '../src/aggregator.js';

async function test() {
  console.log('Testing dashboard server...\n');

  // Create a mock aggregator
  const aggregator = new MetricsAggregator();

  // Create app
  const app = createApp(aggregator);

  // Test endpoints
  const tests = [
    { path: '/api/health', expect: 'status' },
    { path: '/api/session', expect: 'sessionId' },
    { path: '/api/sessions', expect: 'sessions' },
    { path: '/api/totals', expect: 'tokensIn' },
    { path: '/', expect: 'Karma Dashboard' },
  ];

  let passed = 0;
  let failed = 0;

  for (const { path, expect } of tests) {
    const res = await app.request(path);
    const body = await res.text();

    if (res.status === 200 && body.includes(expect)) {
      console.log(`  [PASS] GET ${path} -> ${res.status}`);
      passed++;
    } else {
      console.log(`  [FAIL] GET ${path} -> ${res.status}`);
      console.log(`    Expected to contain: "${expect}"`);
      console.log(`    Body: ${body.slice(0, 100)}...`);
      failed++;
    }
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

test().catch((err) => {
  console.error('Test error:', err);
  process.exit(1);
});
