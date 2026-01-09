# Phase 1: Create Package Skeleton

**Status**: Complete
**Depends on**: None
**Unlocks**: Phase 2
**Completed**: 2026-01-09

## Objective

Set up the `claude-code-files-parser/` package structure with build tooling.

## Tasks

- [x] Create directory structure
- [x] Initialize `package.json`
- [x] Configure `tsconfig.json`
- [x] Create placeholder `src/index.ts`
- [x] Verify build works

## Directory Structure

```bash
mkdir -p claude-code-files-parser/src/{types,extractors}
mkdir -p claude-code-files-parser/tests/fixtures
```

```
claude-code-files-parser/
├── src/
│   ├── index.ts
│   ├── types/
│   └── extractors/
├── tests/
│   └── fixtures/
├── package.json
├── tsconfig.json
└── README.md
```

## Files to Create

### package.json

```json
{
  "name": "claude-code-files-parser",
  "version": "0.1.0",
  "description": "Streaming parser for Claude Code JSONL session logs",
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsc",
    "clean": "rm -rf dist",
    "test": "vitest run",
    "test:watch": "vitest",
    "prepublishOnly": "npm run build"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vitest": "^2.0.0"
  },
  "engines": {
    "node": ">=18"
  },
  "keywords": ["claude", "claude-code", "jsonl", "parser", "logs"],
  "license": "MIT"
}
```

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

### src/index.ts (placeholder)

```typescript
// Claude Code Files Parser
// Streaming parser for Claude Code JSONL session logs

export const VERSION = '0.1.0';

// Types will be exported here
// Parser functions will be exported here
// Extractors will be exported here
```

### README.md

```markdown
# claude-code-files-parser

Streaming parser for Claude Code JSONL session logs.

## Installation

```bash
npm install claude-code-files-parser
```

## Usage

```typescript
import { parseSessionFile } from 'claude-code-files-parser';

const entries = await parseSessionFile('/path/to/session.jsonl');
```

## API

Documentation coming soon.
```

## Validation

```bash
cd claude-code-files-parser
npm install
npm run build
# Should compile without errors
```

## Outputs

- [x] Package compiles with `npm run build`
- [x] `dist/index.js` and `dist/index.d.ts` generated
- [x] No TypeScript errors

## Implementation Notes

**Package Location**: `karma-logger/claude-code-files-parser/`

**Build Output**:
- `dist/index.js` - Compiled ESM module
- `dist/index.d.ts` - TypeScript declarations
- Source maps included for debugging

**Dependencies Installed**: 91 packages (typescript, vitest)

## Estimated Effort

~15 minutes (actual: ~5 minutes via automated agent)
