# karma-logger

Local metrics and cost tracking for Claude Code sessions.

## Features

- **Real-time metrics** - Track token usage and costs as you code
- **Session history** - Browse and export past session data
- **Cost breakdown** - See detailed pricing by input, output, and cache
- **Multiple views** - CLI, streaming watch mode, and web dashboard
- **Offline-first** - All data stays local in SQLite

## Installation

```bash
npm install -g karma-logger
```

Requires Node.js 20+.

## Quick Start

```bash
# Show current session metrics
karma status

# Watch sessions in real-time
karma watch

# View session history
karma report
```

## Commands

### karma status

Show metrics for the current or specified session.

```bash
karma status                  # Current project session
karma status --all            # All active sessions
karma status -p myproject     # Specific project
karma status --json           # JSON output
```

### karma watch

Monitor sessions in real-time with live updates.

```bash
karma watch                   # Streaming mode
karma watch --ui              # Interactive TUI
karma watch --compact         # Compact view
karma watch --activity-only   # Tool activity feed only
```

### karma report

View session history with filtering and export options.

```bash
karma report                  # List recent sessions
karma report <session-id>     # Session details
karma report --since 7d       # Last 7 days
karma report --json           # JSON export
karma report --csv            # CSV export
karma report --sync           # Sync before reporting
```

### karma dashboard

Launch a web-based metrics dashboard.

```bash
karma dashboard               # Open on port 3333
karma dashboard -p 8080       # Custom port
karma dashboard --no-open     # Don't open browser
```

### karma config

Manage configuration settings.

```bash
karma config                  # Show all settings
karma config get <key>        # Get a value
karma config set <key> <val>  # Set a value
karma config reset            # Reset to defaults
karma config list             # List available keys
```

## Configuration

Configuration is stored in `~/.karma/config.json`.

| Key | Description | Default |
|-----|-------------|---------|
| `logsDir` | Claude Code logs directory | `~/.claude/projects` |
| `dataDir` | Karma data directory | `~/.karma` |
| `retentionDays` | Days to retain history | `30` |
| `defaultProject` | Default project filter | `null` |
| `debug` | Enable debug output | `false` |
| `pricing.*` | Custom token pricing | Claude defaults |

### Environment Variables

| Variable | Config Key |
|----------|------------|
| `KARMA_LOGS_DIR` | `logsDir` |
| `KARMA_DATA_DIR` | `dataDir` |
| `KARMA_RETENTION_DAYS` | `retentionDays` |
| `KARMA_DEFAULT_PROJECT` | `defaultProject` |
| `KARMA_DEBUG` | `debug` |

## Data Storage

- **Logs**: Read from `~/.claude/projects/` (Claude Code default)
- **Database**: `~/.karma/karma.db` (SQLite)
- **Config**: `~/.karma/config.json`

## Metrics Tracked

- **Token Usage**
  - Input tokens
  - Output tokens
  - Cache read tokens
  - Cache creation tokens

- **Costs**
  - Per-request cost
  - Session totals
  - Cost breakdown by category

- **Activity**
  - Tool calls with timing
  - Model usage
  - Session duration

## Pricing

Default pricing (Claude 3.5 Sonnet):

| Type | Cost per 1M tokens |
|------|-------------------|
| Input | $3.00 |
| Output | $15.00 |
| Cache Read | $0.30 |
| Cache Creation | $3.75 |

Override with `karma config set pricing.inputTokenCost <value>`.

## Development

```bash
# Clone and install
git clone https://github.com/anthropics/karma-logger
cd karma-logger
npm install

# Development
npm run dev                   # Run with tsx
npm run test                  # Run tests
npm run test:watch            # Watch mode
npm run build                 # Build for distribution
```

## License

MIT
