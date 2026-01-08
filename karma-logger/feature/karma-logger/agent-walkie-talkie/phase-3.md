# Phase 3: CLI Tool (`karma radio` subcommand)

## Objective

Thin CLI wrapper for cache operations. Enables Claude Code hooks to broadcast status without Node.js runtime in hook scripts.

## Dependencies

- **Phase 2**: AgentRadio must be complete

## Deliverables

```
src/commands/radio.ts        # Radio command implementations (following existing pattern)
src/walkie-talkie/socket-client.ts  # Socket client for CLI-to-server communication
```

## Architecture Alignment

This phase follows existing CLI patterns:
- Command file: `src/commands/radio.ts` (like `status.ts`, `watch.ts`)
- Registered via `cli.ts` as subcommand of main `karma` program
- Single binary: `karma` (no separate `karma-radio` binary)

Example integration in `cli.ts`:
```typescript
program
  .command('radio')
  .description('Agent coordination commands (for hooks)')
  .addCommand(setStatusCmd)
  .addCommand(waitForCmd)
  // etc.
```

## Tasks

### 3.1 CLI Commands

```bash
karma radio set-status <state> [options]
karma radio report-progress [options]
karma radio publish-result <json-file>
karma radio wait-for <agent-id> <state> [--timeout <ms>]
karma radio send <target-agent-id> <message-json>
karma radio listen [--agent <id>] [--pattern <glob>]
karma radio get-status [--agent <id>]
```

### 3.2 Environment Variables

CLI reads agent context from env vars (set by Claude Code):

| Variable | Description | Required |
|----------|-------------|----------|
| `KARMA_AGENT_ID` | Current agent's ID | Yes |
| `KARMA_SESSION_ID` | Parent session ID | Yes |
| `KARMA_PARENT_ID` | Parent agent ID | No |
| `KARMA_AGENT_TYPE` | Agent type (Explore, Plan, etc.) | No |
| `KARMA_MODEL` | Model being used | No |

### 3.3 Command Implementations

#### `set-status`
```bash
karma radio set-status active --tool "Grep" --metadata '{"query":"pattern"}'
```
```typescript
// Implementation
const radio = getRadioFromEnv();
radio.setStatus(state, { tool, ...JSON.parse(metadata) });
```

#### `report-progress`
```bash
karma radio report-progress --tool "Read" --percent 50 --message "Reading files"
```
```typescript
radio.reportProgress({ tool, percent, message });
```

#### `publish-result`
```bash
karma radio publish-result ./result.json
```
```typescript
const result = JSON.parse(fs.readFileSync(file, 'utf-8'));
radio.publishResult(result);
```

#### `wait-for`
```bash
karma radio wait-for agent-123 completed --timeout 30000
# Exit code: 0 = success, 1 = timeout, 2 = error
```
```typescript
try {
  const status = await radio.waitForAgent(agentId, state, timeout);
  console.log(JSON.stringify(status));
  process.exit(0);
} catch (e) {
  process.exit(1);
}
```

#### `send`
```bash
karma radio send agent-456 '{"action":"proceed","data":{"ready":true}}'
```

#### `listen`
```bash
karma radio listen --pattern "agent:*:status"
# Outputs JSON lines as events arrive
```
```typescript
cache.subscribe(pattern, (key, value) => {
  console.log(JSON.stringify({ key, value, timestamp: new Date().toISOString() }));
});
// Keep process alive until Ctrl+C
```

#### `get-status`
```bash
karma radio get-status                    # Own status
karma radio get-status --agent agent-123  # Specific agent
```

### 3.4 Cache Connection Strategy

**Challenge**: CLI is short-lived process, cache is in-memory.

**Solutions** (implement in order of preference):

1. **Unix Domain Socket Server**
   ```
   karma watch         →  starts socket server at /tmp/karma-radio.sock
   karma radio *       →  connects to socket, sends command, receives response
   ```

2. **File-backed Cache** (fallback)
   ```
   ~/.karma/radio-cache.json  →  JSON file updated atomically
   ```

3. **HTTP API** (if dashboard running)
   ```
   POST http://localhost:3333/api/radio/set-status
   ```

### 3.5 Socket Protocol

```typescript
// Request
interface RadioRequest {
  id: string;
  command: 'set-status' | 'report-progress' | 'wait-for' | ...;
  args: Record<string, unknown>;
  env: { agentId, sessionId, parentId, agentType, model };
}

// Response
interface RadioResponse {
  id: string;
  success: boolean;
  data?: unknown;
  error?: string;
}
```

### 3.6 Implement Socket Server

Socket server runs independently or auto-starts when needed. Decoupled from `karma watch` for flexibility.

```typescript
// In src/walkie-talkie/socket-server.ts
import { createServer } from 'net';

const SOCKET_PATH = process.platform === 'win32'
  ? '\\\\.\\pipe\\karma-radio'
  : '/tmp/karma-radio.sock';

function startRadioServer(cache: CacheStore, aggregator: MetricsAggregator) {
  const server = createServer((socket) => {
    socket.on('data', (data) => {
      const request = JSON.parse(data.toString()) as RadioRequest;
      const response = handleRadioRequest(request, cache, aggregator);
      socket.write(JSON.stringify(response));
    });
  });
  server.listen(SOCKET_PATH);
  return server;
}
```

## Tests

```typescript
describe('karma radio CLI', () => {
  describe('set-status', () => {
    test('sets status with metadata');
    test('requires KARMA_AGENT_ID env');
    test('validates state enum');
  });

  describe('wait-for', () => {
    test('exits 0 on success');
    test('exits 1 on timeout');
    test('outputs status JSON');
  });

  describe('socket connection', () => {
    test('connects to running server');
    test('fails gracefully if no server');
  });
});
```

## Acceptance Criteria

- [ ] All commands work with env vars set
- [ ] Proper exit codes for scripting
- [ ] JSON output for machine parsing
- [ ] Graceful degradation if server not running
- [ ] Socket server starts with `karma watch`
- [ ] <50ms latency for commands

## package.json Updates

```json
{
  "bin": {
    "karma": "./dist/index.js"
  }
}
```

## Estimated Complexity

- Lines of code: ~300 (CLI) + ~100 (socket server)
- Test lines: ~150
- Risk: Medium (IPC complexity, cross-platform sockets - addressed with platform detection)
