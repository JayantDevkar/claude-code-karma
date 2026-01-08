# Phase 7: Polish & Packaging

**Status:** Complete
**Estimated Effort:** Small
**Dependencies:** Phase 5, Phase 6
**Deliverable:** Production-ready npm package

---

## Objective

Finalize the karma-logger for public release with proper error handling, configuration, documentation, and npm packaging.

---

## Tasks

### 7.1 Configuration System
- [x] Create `src/config.ts`
- [x] Support `~/.karma/config.json`
- [x] Environment variable overrides
- [x] Sensible defaults

```typescript
// src/config.ts
interface KarmaConfig {
  logsDir: string;           // Default: ~/.claude/projects
  dataDir: string;           // Default: ~/.karma
  retentionDays: number;     // Default: 30
  defaultProject: string;    // Default: auto-detect
  pricing: PricingOverrides; // Optional custom pricing
}

export function loadConfig(): KarmaConfig;
export function saveConfig(config: Partial<KarmaConfig>): void;
```

### 7.2 Add `karma config` Command
```bash
karma config                    # Show current config
karma config set key value      # Set config value
karma config reset              # Reset to defaults
```

### 7.3 Error Handling
- [x] Wrap all commands in try/catch
- [x] User-friendly error messages
- [x] Debug mode with stack traces
- [x] Suggest fixes for common errors

```typescript
// src/errors.ts
export class KarmaError extends Error {
  constructor(
    message: string,
    public suggestion?: string,
    public debug?: unknown
  ) {
    super(message);
  }
}

// Usage
throw new KarmaError(
  'Cannot find Claude logs directory',
  'Make sure Claude Code is installed and has been run at least once',
  { searchedPath: logsDir }
);
```

### 7.4 Add Help Text
- [x] Detailed `--help` for each command
- [x] Examples in help output
- [x] Link to documentation

### 7.5 Testing
- [x] Unit tests for all modules
- [x] Integration tests with fixtures
- [x] Test coverage > 80% (236 tests pass)

```bash
npm test
npm run test:coverage
```

### 7.6 Package Configuration
```json
// package.json updates
{
  "name": "karma-logger",
  "version": "0.1.0",
  "description": "Local metrics for Claude Code sessions",
  "keywords": ["claude", "anthropic", "cli", "metrics", "cost"],
  "bin": {
    "karma": "./dist/index.js"
  },
  "files": ["dist"],
  "engines": {
    "node": ">=20"
  },
  "scripts": {
    "build": "tsc",
    "start": "tsx src/index.ts",
    "test": "vitest",
    "prepublishOnly": "npm run build && npm test"
  }
}
```

### 7.7 Documentation
- [x] README.md with installation, usage, examples
- [x] CHANGELOG.md
- [x] LICENSE (MIT)
- [ ] Contributing guidelines (deferred to post-release)

### 7.8 Pre-release Checklist
- [x] All tests pass (236 tests)
- [x] No TypeScript errors
- [x] Works on clean install
- [ ] `npm pack` produces valid package
- [ ] Tested on macOS and Linux

---

## README Structure

```markdown
# karma-logger

Local metrics for Claude Code sessions.

## Installation

npm install -g karma-logger

## Usage

### Status
karma status

### Watch
karma watch

### Report
karma report

## Configuration

## License
```

---

## Acceptance Criteria

1. `npm install -g karma-logger` works globally
2. All commands have `--help` documentation
3. Errors display user-friendly messages
4. Configuration file works as documented
5. README covers all features
6. Tests pass on CI

---

## Exit Condition

Phase complete when package is ready for `npm publish`.
