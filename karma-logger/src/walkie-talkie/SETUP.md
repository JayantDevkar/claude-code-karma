# Walkie-Talkie Setup Guide

Quick setup guide for running the Agent Walkie-Talkie communication layer with Claude Code.

## Prerequisites

- Node.js 18+
- `karma-logger` package installed
- Claude Code CLI configured

## Quick Start

### 1. Install karma-logger globally

```bash
cd /path/to/karma-logger
npm install
npm link
```

Verify installation:
```bash
karma --version
```

### 2. Start the Radio Server

```bash
# Basic (in-memory, clears on restart)
karma watch

# With persistence (survives restarts) - RECOMMENDED
karma watch --persist-radio
```

The server creates:
- Unix socket: `/tmp/karma-radio.sock`
- Persistent storage: `~/.karma/radio/` (WAL + snapshots)

### 3. Test the connection

```bash
# In a new terminal
export KARMA_AGENT_ID="test-agent"
export KARMA_SESSION_ID="test-session"

karma radio set-status active
karma radio get-status
# Should output: {"success":true,"status":{...}}
```

---

## Running as a Service

For production use, run the radio server as a background service that starts automatically.

### Option A: launchd (macOS)

Create `~/Library/LaunchAgents/com.karma.radio.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.karma.radio</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/karma</string>
        <string>watch</string>
        <string>--persist-radio</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/karma-radio.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/karma-radio.error.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME</string>
</dict>
</plist>
```

Load the service:
```bash
# Replace YOUR_USERNAME in the plist first
launchctl load ~/Library/LaunchAgents/com.karma.radio.plist

# Check status
launchctl list | grep karma

# View logs
tail -f /tmp/karma-radio.log
```

Unload when needed:
```bash
launchctl unload ~/Library/LaunchAgents/com.karma.radio.plist
```

### Option B: systemd (Linux)

Create `/etc/systemd/user/karma-radio.service`:

```ini
[Unit]
Description=Karma Radio Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/karma watch --persist-radio
Restart=always
RestartSec=5
WorkingDirectory=%h

[Install]
WantedBy=default.target
```

Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable karma-radio
systemctl --user start karma-radio

# Check status
systemctl --user status karma-radio

# View logs
journalctl --user -u karma-radio -f
```

### Option C: pm2 (Cross-platform)

```bash
# Install pm2
npm install -g pm2

# Start karma radio
pm2 start "karma watch --persist-radio" --name karma-radio

# Auto-start on boot
pm2 startup
pm2 save

# View logs
pm2 logs karma-radio

# Restart/stop
pm2 restart karma-radio
pm2 stop karma-radio
```

### Option D: Simple Background Process

For quick testing (not recommended for production):

```bash
# Start in background
nohup karma watch --persist-radio > /tmp/karma-radio.log 2>&1 &

# Save PID for later
echo $! > /tmp/karma-radio.pid

# Stop later
kill $(cat /tmp/karma-radio.pid)
```

---

## Claude Code Integration

### Hook Configuration

Create `.claude/hooks.yaml` in your project root:

```yaml
hooks:
  # Called before each tool execution
  PreToolUse:
    - command: |
        karma radio set-status active --tool "$TOOL_NAME" 2>/dev/null || true
      env:
        KARMA_AGENT_ID: "{{sessionId}}"
        KARMA_SESSION_ID: "{{rootSessionId}}"
        KARMA_PARENT_ID: "{{parentSessionId}}"
        KARMA_AGENT_TYPE: "{{agentType}}"

  # Called after each tool execution
  PostToolUse:
    - command: |
        karma radio report-progress --tool "$TOOL_NAME" --message "Done" 2>/dev/null || true
      env:
        KARMA_AGENT_ID: "{{sessionId}}"
        KARMA_SESSION_ID: "{{rootSessionId}}"

  # Called when agent/session ends
  Stop:
    - command: |
        karma radio set-status completed 2>/dev/null || true
      env:
        KARMA_AGENT_ID: "{{sessionId}}"
        KARMA_SESSION_ID: "{{rootSessionId}}"
```

> **Note**: The `2>/dev/null || true` ensures hooks don't fail if the radio server isn't running.

### Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `KARMA_AGENT_ID` | Yes | Unique identifier for this agent |
| `KARMA_SESSION_ID` | Yes | Root session identifier |
| `KARMA_PARENT_ID` | No | Parent agent ID (for hierarchy tracking) |
| `KARMA_AGENT_TYPE` | No | Type: `task`, `explore`, `plan`, etc. |
| `KARMA_MODEL` | No | Model name: `claude-sonnet-4`, `claude-opus-4`, etc. |

---

## CLI Commands Reference

### Status Management

```bash
# Set status (required: KARMA_AGENT_ID, KARMA_SESSION_ID)
karma radio set-status <state>

# States: pending | active | waiting | completed | failed | cancelled

# With options
karma radio set-status active --tool Read
karma radio set-status active --tool Bash --percent 50 --message "Running tests"
karma radio set-status completed --metadata '{"files_modified": 3}'
```

### Progress Reporting

```bash
karma radio report-progress --tool Bash --percent 75 --message "Building..."
```

### Querying Status

```bash
# Get own status
karma radio get-status

# Get specific agent
karma radio get-status --agent other-agent-id

# Include progress info
karma radio get-status --include-progress
```

### Agent Discovery

```bash
# List all agents in session
karma radio list-agents

# Filter by relationship
karma radio list-agents --children
karma radio list-agents --siblings
karma radio list-agents --parent

# Filter by state
karma radio list-agents --status active
```

### Waiting for Agents

```bash
# Wait for agent to complete (subscription-based, instant notification)
karma radio wait-for agent-123 completed --timeout 30000

# Fallback to polling mode
karma radio wait-for agent-123 completed --timeout 30000 --poll
```

### Messaging

```bash
# Send message to another agent
karma radio send target-agent '{"type": "data", "payload": {...}}'

# Listen for incoming messages
karma radio listen
karma radio listen --agent specific-sender
```

### Publish Results

```bash
# Publish final result from JSON file
karma radio publish-result ./result.json
```

---

## Data Storage

### Storage Location

```
~/.karma/radio/
├── wal.log          # Write-ahead log (append-only)
└── snapshot.json    # Periodic full cache dump
```

### TTL (Time-to-Live) Values

| Data Type | TTL | Description |
|-----------|-----|-------------|
| Status | 5 min | Agent state expires if not refreshed |
| Progress | 1 min | Ephemeral; only latest matters |
| Result | 10 min | Available after completion |
| Inbox | 5 min | Messages consumed quickly |
| Session agents | 1 hr | Session reference |

### Key Schema

```
agent:{agentId}:status    → AgentStatus object
agent:{agentId}:progress  → ProgressUpdate object
agent:{agentId}:result    → Any JSON value
agent:{agentId}:inbox     → Array of messages
session:{sessionId}:agents → Array of agent IDs
```

---

## Troubleshooting

### "Server not running" error

```bash
# Check if socket exists
ls -la /tmp/karma-radio.sock

# Check if karma watch is running
ps aux | grep "karma watch"

# Start the server
karma watch --persist-radio
```

### Socket permission denied

```bash
# Socket should have 0600 permissions
ls -la /tmp/karma-radio.sock
# srw------- 1 user user 0 ... /tmp/karma-radio.sock

# If wrong permissions, restart the server
rm /tmp/karma-radio.sock
karma watch --persist-radio
```

### Stale socket file

```bash
# Remove stale socket and restart
rm /tmp/karma-radio.sock
karma watch --persist-radio
```

### Cache not persisting

```bash
# Ensure using --persist-radio flag
karma watch --persist-radio

# Check storage directory
ls -la ~/.karma/radio/

# Verify WAL is being written
tail ~/.karma/radio/wal.log
```

### High memory usage

```bash
# Clear ended sessions (if using programmatically)
aggregator.clearEndedSessions();

# Or restart the server to clear in-memory data
# (persistent data will be restored from disk)
```

### Debug mode

```bash
# Run with verbose logging
DEBUG=karma:* karma watch --persist-radio
```

---

## Programmatic Usage

For custom integrations beyond CLI hooks:

```typescript
import { MetricsAggregator } from 'karma-logger';
import { startRadioServer } from 'karma-logger/walkie-talkie';

// Create aggregator with radio enabled
const aggregator = new MetricsAggregator({
  enableRadio: true,
  persistRadio: true,  // Enable persistence
});

// Initialize (required for persistent mode)
await aggregator.initRadio();

// Start socket server
const server = startRadioServer(aggregator);

// Get agent statuses
const statuses = aggregator.getAgentStatuses();

// Subscribe to status changes
aggregator.onAgentStatusChange((agentId, status) => {
  console.log(`Agent ${agentId}: ${status.state}`);
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  await aggregator.destroy();
  server.close();
});
```

---

## Security Notes

- **Socket permissions**: Unix socket uses `0600` (owner-only read/write)
- **Message size limit**: 64KB maximum per message
- **Connection limit**: 10 concurrent connections max
- **Request timeout**: 5 seconds (5 minutes for subscriptions)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application                          │
│  (Dashboard, TUI, monitoring)                               │
└─────────────────────────────────────────────────────────────┘
                            │ Subscribe to status changes
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   MetricsAggregator                          │
│            enableRadio: true, persistRadio: true            │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
┌───────────────────┐           ┌───────────────────┐
│   AgentRadio      │           │   SocketServer    │
│  (per-agent API)  │           │  Unix domain IPC  │
└───────────────────┘           └───────────────────┘
            │                               │
            └───────────────┬───────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    CacheStore                                │
│  ┌─────────────────┐    ┌─────────────────────────┐        │
│  │MemoryCacheStore │ OR │ PersistentCacheStore    │        │
│  │  (ephemeral)    │    │ (WAL + Snapshot)        │        │
│  └─────────────────┘    └─────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ Unix socket IPC
┌─────────────────────────────────────────────────────────────┐
│                   karma radio CLI                            │
│              (called from Claude Code hooks)                 │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ Environment variables
┌─────────────────────────────────────────────────────────────┐
│                   Claude Code Hooks                          │
│            PreToolUse, PostToolUse, Stop                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Start the server**: `karma watch --persist-radio`
2. **Configure hooks**: Create `.claude/hooks.yaml`
3. **Monitor agents**: Use `karma radio list-agents` or build a dashboard
4. **Set up service**: Use launchd/systemd/pm2 for production

For detailed API documentation, see [README.md](./README.md).
