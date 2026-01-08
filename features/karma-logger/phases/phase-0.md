# Phase 0: Project Scaffold

**Status:** Complete
**Estimated Effort:** Small
**Dependencies:** None
**Deliverable:** Buildable TypeScript project with CLI entry point

---

## Objective

Bootstrap the karma-logger project with a working TypeScript environment, ESM configuration, and basic CLI structure.

---

## Tasks

### 0.1 Initialize npm Project
- [ ] Create `package.json` with ESM configuration
- [ ] Set `"type": "module"`
- [ ] Define `"bin"` entry for `karma` command
- [ ] Add basic metadata (name, version, description)

### 0.2 TypeScript Configuration
- [ ] Create `tsconfig.json` with strict mode
- [ ] Target ES2022 / Node20
- [ ] Configure `outDir` to `dist/`
- [ ] Enable source maps

### 0.3 Install Core Dependencies
```bash
npm install commander chalk
npm install -D typescript @types/node tsx
```

### 0.4 Create Entry Point
- [ ] `src/index.ts` - shebang + main entry
- [ ] `src/cli.ts` - Commander program setup
- [ ] `src/types.ts` - Core TypeScript interfaces

### 0.5 Verify Build Pipeline
- [ ] `npm run build` compiles without errors
- [ ] `./dist/index.js status` outputs placeholder message
- [ ] `npm link` creates working `karma` command

---

## File Structure After Phase

```
karma-logger/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts
│   ├── cli.ts
│   └── types.ts
└── dist/           # Generated
```

---

## Acceptance Criteria

1. `npm run build` succeeds
2. `karma --version` prints version number
3. `karma --help` shows command list
4. `karma status` outputs "Not implemented" placeholder

---

## Exit Condition

Phase complete when `karma` CLI is installed globally via `npm link` and responds to basic commands.
