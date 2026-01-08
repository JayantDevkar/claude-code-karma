# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-08

### Added

- **Core Features**
  - JSONL log parser with streaming support
  - Session discovery and file watching
  - Metrics aggregation engine
  - Cost calculation with Claude pricing

- **Commands**
  - `karma status` - Show current session metrics
  - `karma watch` - Real-time streaming view
  - `karma report` - Session history and exports
  - `karma dashboard` - Web-based metrics dashboard
  - `karma config` - Configuration management

- **Data Layer**
  - SQLite persistence for session history
  - JSON and CSV export formats
  - Configurable retention period

- **Configuration**
  - `~/.karma/config.json` support
  - Environment variable overrides
  - Custom pricing configuration

### Technical

- TypeScript with ESM modules
- Commander.js CLI framework
- Ink for TUI components
- Hono for web dashboard
- better-sqlite3 for persistence
- Chokidar for file watching
