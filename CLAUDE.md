# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Karma Frontend** — SvelteKit + Svelte 5 web interface for monitoring and analyzing Claude Code sessions. Connects to the FastAPI backend on port 8000.

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server
npm run dev
```

## Commands

```bash
# Development
npm run dev              # Start dev server (port 5173)
npm run build            # Production build
npm run preview          # Preview production build

# Code Quality
npm run check            # Type check with svelte-check
npm run check:watch      # Type check in watch mode
npm run lint             # ESLint
npm run format           # Prettier formatting
```

## Architecture

### Tech Stack

- **SvelteKit 2** - Full-stack framework
- **Svelte 5** - UI with runes (`$state`, `$derived`, `$effect`, `$props`)
- **Tailwind CSS 4** - Styling
- **Chart.js** - Data visualization
- **TypeScript** - Type safety
- **bits-ui** - Accessible UI primitives
- **lucide-svelte** - Icons

### Directory Structure

```
frontend/
├── src/
│   ├── routes/                    # SvelteKit file-based routing
│   │   ├── +layout.svelte         # Root layout with header
│   │   ├── +page.svelte           # Home page (/)
│   │   ├── projects/              # /projects routes
│   │   │   └── [encoded_name]/    # Dynamic project routes
│   │   ├── agents/                # /agents routes
│   │   ├── analytics/             # /analytics
│   │   ├── history/               # /history
│   │   ├── settings/              # /settings
│   │   └── skills/                # /skills routes
│   ├── lib/
│   │   ├── components/            # Reusable components
│   │   │   ├── charts/            # Chart.js visualizations
│   │   │   ├── agents/            # Agent components
│   │   │   ├── skills/            # Skills components
│   │   │   ├── timeline/          # Session timeline
│   │   │   ├── conversation/      # Conversation view
│   │   │   ├── subagents/         # Subagent components
│   │   │   ├── skeleton/          # Loading skeletons
│   │   │   ├── settings/          # Settings components
│   │   │   ├── ui/                # Base UI components
│   │   │   ├── layout/            # Layout components
│   │   │   └── command-palette/   # Command palette
│   │   ├── actions/               # Svelte actions
│   │   │   ├── globalKeyboard.ts  # Global keyboard shortcuts
│   │   │   ├── globalShortcuts.ts # Shortcut registry
│   │   │   └── listNavigation.ts  # List keyboard nav
│   │   ├── stores/                # Svelte stores
│   │   │   ├── commandPalette.ts  # Command palette state
│   │   │   └── project-tree-store.ts
│   │   ├── utils/                 # Utility functions
│   │   └── api-types.ts           # TypeScript interfaces
│   └── app.css                    # Global styles & design tokens
├── static/                        # Static assets
├── svelte.config.js               # SvelteKit config (adapter-node)
├── vite.config.ts                 # Vite config
└── tsconfig.json                  # TypeScript config
```

### Data Flow

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl
    ↓
FastAPI Backend (port 8000)
    ↓
SvelteKit load functions (+page.server.ts)
    ↓
Svelte components
```

## Key Patterns

### Svelte 5 Runes

```svelte
<script lang="ts">
	let count = $state(0); // Reactive state
	let doubled = $derived(count * 2); // Computed value
	let { data } = $props(); // Component props

	$effect(() => {
		// Side effects
		console.log('count changed:', count);
	});
</script>
```

### Server/Client Loading

- `+page.server.ts` - Server-side data loading (API calls)
- `+page.ts` - Universal load functions
- `+page.svelte` - Component rendering

### URL State

Filters and view state persisted via URL search params for shareable links.

### Component Organization

- `lib/components/ui/` - Base primitives (Badge, Card, Tabs, Modal, etc.)
- `lib/components/layout/` - Page layout (PageHeader)
- `lib/components/skeleton/` - Loading states
- Feature-specific folders for domain components

## Routes

| Route                                       | Description                  |
| ------------------------------------------- | ---------------------------- |
| `/`                                         | Home page                    |
| `/projects`                                 | Project listing              |
| `/projects/[encoded_name]`                  | Project detail with sessions |
| `/projects/[encoded_name]/agents`           | Project agents               |
| `/projects/[encoded_name]/agents/[name]`    | Agent detail                 |
| `/projects/[encoded_name]/skills`           | Project skills               |
| `/projects/[encoded_name]/skills/[...path]` | Skill detail                 |
| `/agents`                                   | Global agents view           |
| `/analytics`                                | Global analytics             |
| `/history`                                  | File history                 |
| `/settings`                                 | User settings                |
| `/skills`                                   | Global skills view           |
| `/skills/[...path]`                         | Skill detail                 |

## API Integration

Backend runs on `http://localhost:8000`. Key endpoints:

| Endpoint                                 | Description             |
| ---------------------------------------- | ----------------------- |
| `GET /projects`                          | List all projects       |
| `GET /projects/{encoded_name}`           | Project with sessions   |
| `GET /analytics`                         | Global analytics        |
| `GET /analytics/projects/{encoded_name}` | Project analytics       |
| `GET /sessions/{uuid}`                   | Session details         |
| `GET /sessions/{uuid}/timeline`          | Session timeline events |
| `GET /sessions/{uuid}/tools`             | Tool usage breakdown    |

## Design System

CSS custom properties defined in `app.css`:

### Colors

- `--bg-base`, `--bg-subtle`, `--bg-muted` - Backgrounds
- `--text-primary`, `--text-secondary`, `--text-muted` - Text
- `--accent` - Brand color (violet)
- `--border` - Border color

### Typography

- **Inter** - UI text
- **JetBrains Mono** - Code/monospace

### Components

- Uses `bits-ui` for accessible primitives
- Tailwind CSS 4 for utility classes
- Custom design tokens for consistency

## Key Components

| Component          | Path                                               | Purpose                    |
| ------------------ | -------------------------------------------------- | -------------------------- |
| `Header`           | `components/Header.svelte`                         | App header with navigation |
| `ProjectCard`      | `components/ProjectCard.svelte`                    | Project list item          |
| `TimelineRail`     | `components/timeline/TimelineRail.svelte`          | Session timeline           |
| `ConversationView` | `components/conversation/ConversationView.svelte`  | Message display            |
| `CommandPalette`   | `components/command-palette/CommandPalette.svelte` | Quick actions              |
| `AgentViewer`      | `components/agents/AgentViewer.svelte`             | Agent details              |
| `SkillViewer`      | `components/skills/SkillViewer.svelte`             | Skill details              |
| `StatsGrid`        | `components/StatsGrid.svelte`                      | Stats display              |
| `ToolsChart`       | `components/charts/ToolsChart.svelte`              | Tool usage chart           |
| `SessionsChart`    | `components/charts/SessionsChart.svelte`           | Sessions over time         |

## Keyboard Shortcuts

Global shortcuts managed via `globalKeyboard.ts` and `globalShortcuts.ts` actions. Command palette accessible via keyboard.

## Dependencies

- **SvelteKit 2** with **adapter-node**
- **Svelte 5** with runes
- **Tailwind CSS 4** (via `@tailwindcss/vite`)
- **Chart.js 4** - Charts
- **bits-ui** - UI primitives
- **lucide-svelte** - Icons
- **date-fns** - Date formatting
- **marked** + **isomorphic-dompurify** - Markdown rendering
