# Phase 1a: Import SocketServer in Dashboard

> **Priority:** High | **Complexity:** Low | **Type:** Code Implementation

## Objective

Add SocketServer import and instantiation scaffolding to `server.ts`.

## Prerequisites

- None (first phase)

## Files to Modify

| File | Action |
|------|--------|
| `src/dashboard/server.ts` | Add import, declare variable |

## Implementation

```typescript
// At top of server.ts
import { SocketServer } from '../walkie-talkie/socket-server.js';

// Module-level variable
let socketServer: SocketServer | null = null;
```

## Acceptance Criteria

- [x] Import statement added without build errors
- [x] TypeScript types resolve correctly
- [x] No runtime errors on dashboard start

**Status: COMPLETED** (2026-01-08)

## Testing

```bash
npm run build
npm run dev -- dashboard
```

## Next Phase

→ Phase 1b: Start socket server conditionally
