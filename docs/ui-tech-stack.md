## Overview

A practical, step-by-step guide for implementing Claude Karma UI, from setup to deployment.

## Technology Stack

### Core Technologies

yaml

```yaml
Frontend Framework:
  - React 18.x with TypeScript
  - Next.js 14.x (for SSG/SSR capabilities)
  
State Management:
  - Zustand (global state)
  - React Query/TanStack Query (server state)
  - React Hook Form (form state)
  
Styling:
  - Tailwind CSS 3.x
  - Radix UI (headless components)
  - Framer Motion (animations)
  
Charts & Visualization:
  - Recharts (primary charts)
  - D3.js (complex visualizations)
  - React Flow (node graphs)
  
Build Tools:
  - Vite (development)
  - Turbo (monorepo)
  - ESBuild (bundling)
  
Testing:
  - Vitest (unit tests)
  - Testing Library (component tests)
  - Playwright (E2E tests)
```

## Project Structure

```
claude-karma-ui/
├── apps/
│   ├── desktop/              # Electron app
│   │   ├── main/            # Main process
│   │   └── preload/         # Preload scripts
│   └── web/                 # Web app
│       ├── app/            # Next.js app directory
│       ├── components/     # React components
│       ├── hooks/         # Custom hooks
│       ├── lib/          # Core logic
│       ├── stores/       # Zustand stores
│       └── styles/       # Global styles
├── packages/
│   ├── parser/             # JSONL parser
│   │   ├── src/
│   │   ├── tests/
│   │   └── package.json
│   ├── ui/                # Shared UI components
│   │   ├── src/
│   │   └── package.json
│   └── types/             # TypeScript types
│       ├── src/
│       └── package.json
├── docs/                   # Documentation
├── scripts/               # Build scripts
└── turbo.json            # Turborepo config
```
