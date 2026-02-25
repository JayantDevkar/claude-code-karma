# UI Sync Documentation

This directory contains reference documentation for frontend engineers implementing new features from the Claude Code data sync (API commit `4e0fb19`).

## Documents

| Document                                       | Feature               | Priority | Placement              |
| ---------------------------------------------- | --------------------- | -------- | ---------------------- |
| [01-TASKS.md](./01-TASKS.md)                   | Tasks System (Kanban) | High     | Session detail view    |
| [02-SESSIONS-INDEX.md](./02-SESSIONS-INDEX.md) | Session Summaries     | High     | Session cards          |
| [03-PLANS.md](./03-PLANS.md)                   | Plans Directory       | Medium   | Under project/sessions |
| [04-PLUGINS.md](./04-PLUGINS.md)               | Plugins               | Medium   | Dashboard extraction   |

## Context

Claude Code (versions 2.1.3 → 2.1.17+) has introduced new data structures that are now exposed via API endpoints. Each document describes:

- **API Implementation**: What was built on the backend
- **Data Structures**: TypeScript-compatible schemas
- **Existing Frontend Context**: Related components and patterns
- **Example Responses**: Real API data shapes

## Current Frontend Stack

- SvelteKit 2 + Svelte 5 (runes)
- Tailwind CSS 4
- bits-ui for primitives
- Chart.js for visualization
- TypeScript throughout

## Design Approach

- Desktop-first
- Follow existing patterns (Card, Badge, Tabs, etc.)
- New components when UX value justifies

## API Base URL

```
http://localhost:8000
```

## Related Files

- `src/lib/api-types.ts` - Type definitions
- `src/lib/components/ui/` - Base primitives
- `src/lib/components/skeleton/` - Loading states
- `src/app.css` - Design tokens
