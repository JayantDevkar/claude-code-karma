# Claude Karma Frontend

A production-ready SvelteKit application for analyzing Claude Code usage, built with Svelte 5, TypeScript, and Tailwind CSS v4.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Component Library](#component-library)
- [Routing Structure](#routing-structure)
- [Svelte 5 Runes Guide](#svelte-5-runes-guide)
- [Design System](#design-system)
- [API Integration](#api-integration)
- [Coding Conventions](#coding-conventions)
- [Contributing](#contributing)

---

## Architecture Overview

The frontend follows a layered architecture pattern with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (SvelteKit)                     │
├─────────────────────────────────────────────────────────────┤
│  Routes Layer        │  Page components & data loading       │
│  (/src/routes/)      │  +page.svelte, +page.ts, +layout.svelte│
├──────────────────────┼───────────────────────────────────────┤
│  Components Layer    │  Reusable UI components               │
│  (/src/lib/)         │  Header, Cards, Lists, Viewers        │
├──────────────────────┼───────────────────────────────────────┤
│  API Layer           │  fetch() calls to backend             │
│  (inline)            │  REST endpoints on localhost:8000     │
└──────────────────────┴───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend (FastAPI :8000)                    │
│         Parses local ~/.claude logs and session data         │
└─────────────────────────────────────────────────────────────┘
```

**Key Architectural Decisions:**

1. **File-based routing** - SvelteKit's convention-based routing with `+page.svelte` files
2. **Component colocation** - Domain-specific components grouped in subdirectories (`agents/`, `skills/`)
3. **Server/client data loading** - Mix of `+page.ts` (universal) and `+page.server.ts` (server-only) load functions
4. **CSS-in-Svelte** - Tailwind utilities with CSS custom properties for theming

---

## Technology Stack

| Technology               | Version | Purpose                                    |
| ------------------------ | ------- | ------------------------------------------ |
| **SvelteKit**            | 2.49.1  | Application framework with SSR/SSG support |
| **Svelte**               | 5.45.6  | UI framework with runes reactivity         |
| **TypeScript**           | 5.9.3   | Type-safe development (strict mode)        |
| **Tailwind CSS**         | 4.1.18  | Utility-first CSS with Vite plugin         |
| **Vite**                 | 7.2.6   | Build tool and dev server                  |
| **Chart.js**             | 4.5.1   | Analytics visualizations                   |
| **date-fns**             | 4.1.0   | Date formatting utilities                  |
| **marked**               | 17.0.1  | Markdown parsing for agents/skills         |
| **lucide-svelte**        | 0.562.0 | Icon library                               |
| **isomorphic-dompurify** | 2.35.0  | HTML sanitization                          |

---

## Project Structure

```
├── src/
│   ├── lib/                          # Shared library code ($lib alias)
│   │   ├── assets/                   # Static assets
│   │   │   └── favicon.svg
│   │   ├── components/               # Reusable UI components
│   │   │   ├── agents/               # Agent-specific components
│   │   │   │   ├── AgentList.svelte      # Grid of agents with search/create
│   │   │   │   └── AgentViewer.svelte    # Markdown editor with preview
│   │   │   ├── skills/               # Skills browser components
│   │   │   │   ├── SkillList.svelte      # File browser with breadcrumbs
│   │   │   │   └── SkillViewer.svelte    # Skill editor with save
│   │   │   ├── Header.svelte             # Adaptive header component
│   │   │   ├── NavigationCard.svelte     # Homepage navigation tiles
│   │   │   ├── SessionCard.svelte        # Session display with metrics
│   │   │   └── TimeRangeFilter.svelte    # Date range picker
│   │   └── index.ts                  # Public exports (currently empty)
│   │
│   ├── routes/                       # SvelteKit file-based routing
│   │   ├── +layout.svelte            # Root layout (Header + main wrapper)
│   │   ├── +page.svelte              # Home page (/)
│   │   ├── projects/                 # /projects routes
│   │   │   ├── +page.svelte              # Projects list
│   │   │   ├── +page.ts                  # Load all projects
│   │   │   └── [encoded_name]/           # Dynamic project routes
│   │   │       ├── +page.svelte              # Project detail with tabs
│   │   │       ├── +page.ts                  # Load project + branches
│   │   │       ├── [session_slug]/           # Session detail
│   │   │       │   ├── +page.svelte
│   │   │       │   └── +page.server.ts
│   │   │       ├── agents/                   # Project-scoped agents
│   │   │       │   ├── +page.svelte
│   │   │       │   └── [name]/+page.svelte
│   │   │       └── skills/                   # Project-scoped skills
│   │   │           ├── +page.svelte
│   │   │           └── [...path]/+page.svelte
│   │   ├── analytics/                # /analytics route
│   │   │   ├── +page.svelte              # Bento grid dashboard
│   │   │   └── +page.ts                  # Load analytics data
│   │   ├── agents/                   # /agents (global)
│   │   │   ├── +page.svelte
│   │   │   └── [name]/+page.svelte
│   │   ├── skills/                   # /skills (global)
│   │   │   ├── +page.svelte
│   │   │   └── [...path]/+page.svelte
│   │   ├── history/                  # /history
│   │   │   └── +page.svelte
│   │   └── settings/                 # /settings
│   │       └── +page.svelte
│   │
│   ├── app.css                       # Global styles & design tokens
│   ├── app.d.ts                      # TypeScript ambient declarations
│   └── app.html                      # HTML shell template
│
├── static/                           # Static files (copied to build)
│   └── robots.txt
│
├── .prettierrc                       # Prettier configuration
├── eslint.config.js                  # ESLint flat config
├── svelte.config.js                  # SvelteKit configuration
├── tsconfig.json                     # TypeScript configuration
└── vite.config.ts                    # Vite + Tailwind configuration
```

---

## Getting Started

### Prerequisites

- **Node.js** 18.x or higher (tested with v22.13.0)
- **npm** 9.x or higher
- **Backend API** running on `http://localhost:8000` (see root SETUP.md)

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Open browser automatically
npm run dev -- --open
```

The app runs at `http://localhost:5173`

### Available Scripts

| Script                | Description                 |
| --------------------- | --------------------------- |
| `npm run dev`         | Start dev server with HMR   |
| `npm run build`       | Create production build     |
| `npm run preview`     | Preview production build    |
| `npm run check`       | Run Svelte type checking    |
| `npm run check:watch` | Type checking in watch mode |
| `npm run lint`        | Lint with ESLint            |
| `npm run format`      | Format with Prettier        |

---

## Component Library

### Shared Components

#### `Header.svelte`

Adaptive header that changes based on route:

- **Home (`/`)**: Large centered layout with branding
- **Other routes**: Compact sticky navbar with navigation

```svelte
<script lang="ts">
	import Header from '$lib/components/Header.svelte';
</script>

<!-- Used in +layout.svelte, adapts automatically -->
<Header />
```

**Key features:**

- Mobile hamburger menu with overlay
- Active route highlighting via `$page.url.pathname`
- Analytics tracking stats display

---

#### `NavigationCard.svelte`

Homepage navigation tiles with icons and color theming.

```svelte
<script lang="ts">
	import NavigationCard from '$lib/components/NavigationCard.svelte';
	import { FolderOpen } from 'lucide-svelte';
</script>

<NavigationCard
	title="Projects"
	description="Manage active workspaces"
	href="/projects"
	icon={FolderOpen}
	color="blue"
/>
```

**Props:**
| Prop | Type | Description |
|------|------|-------------|
| `title` | `string` | Card heading |
| `description` | `string` | Subtitle text |
| `href` | `string` | Navigation link |
| `icon` | `Component` | Lucide icon component |
| `color` | `'blue' \| 'green' \| 'orange' \| 'purple' \| 'gray' \| 'red'` | Theme color |

---

#### `SessionCard.svelte`

Displays a session with status indicators, metrics, and git branch info.

```svelte
<script lang="ts">
	import SessionCard from '$lib/components/SessionCard.svelte';
</script>

<SessionCard session={sessionData} projectEncodedName="my-project" />
```

**Props:**
| Prop | Type | Description |
|------|------|-------------|
| `session` | `Session` | Session object with uuid, slug, metrics |
| `projectEncodedName` | `string` | URL-encoded project identifier |

**Session status types:** `active`, `completed`, `error`

---

#### `TimeRangeFilter.svelte`

Date range filter with preset buttons and custom date picker.

```svelte
<script lang="ts">
	import TimeRangeFilter from '$lib/components/TimeRangeFilter.svelte';

	function handleFilterChange(filter) {
		console.log(filter.startDate, filter.endDate);
	}
</script>

<TimeRangeFilter onFilterChange={handleFilterChange} defaultValue="7d" />
```

**Presets:** 7D, 14D, 30D, 90D, All, Custom

---

### Domain Components

#### Agents (`$lib/components/agents/`)

| Component            | Purpose                                               |
| -------------------- | ----------------------------------------------------- |
| `AgentList.svelte`   | Grid view of agents with search and create modal      |
| `AgentViewer.svelte` | Markdown editor with live preview, save functionality |

#### Skills (`$lib/components/skills/`)

| Component            | Purpose                                        |
| -------------------- | ---------------------------------------------- |
| `SkillList.svelte`   | File/folder browser with breadcrumb navigation |
| `SkillViewer.svelte` | Skill content editor with preview toggle       |

---

## Routing Structure

### Route Map

| Route                          | Page                            | Data Loading      | Description                          |
| ------------------------------ | ------------------------------- | ----------------- | ------------------------------------ |
| `/`                            | `+page.svelte`                  | Client `onMount`  | Dashboard home with navigation cards |
| `/projects`                    | `projects/+page.svelte`         | `+page.ts`        | All projects grid                    |
| `/projects/[encoded_name]`     | `[encoded_name]/+page.svelte`   | `+page.ts`        | Project detail with sessions         |
| `/projects/.../[session_slug]` | `[session_slug]/+page.svelte`   | `+page.server.ts` | Full session view                    |
| `/analytics`                   | `analytics/+page.svelte`        | `+page.ts`        | Metrics dashboard                    |
| `/agents`                      | `agents/+page.svelte`           | Client fetch      | Global agents browser                |
| `/agents/[name]`               | `agents/[name]/+page.svelte`    | Client fetch      | Agent editor                         |
| `/skills`                      | `skills/+page.svelte`           | Client fetch      | Global skills browser                |
| `/skills/[...path]`            | `skills/[...path]/+page.svelte` | Client fetch      | Skill editor                         |
| `/history`                     | `history/+page.svelte`          | -                 | Session history                      |
| `/settings`                    | `settings/+page.svelte`         | -                 | App settings (coming soon)           |

### Data Loading Patterns

**Universal load (`+page.ts`)** - Runs on server and client:

```typescript
// projects/+page.ts
export async function load({ fetch }) {
	const response = await fetch('http://localhost:8000/projects');
	const projects = await response.json();
	return { projects };
}
```

**Server-only load (`+page.server.ts`)** - Runs only on server:

```typescript
// Used for session detail to keep API calls server-side
export async function load({ params, fetch }) {
	const res = await fetch(`http://localhost:8000/sessions/${params.session_slug}`);
	return { session: await res.json() };
}
```

**Client-side fetch** - In component lifecycle:

```svelte
<script lang="ts">
	import { onMount } from 'svelte';

	let data = $state([]);

	onMount(async () => {
		const res = await fetch('http://localhost:8000/agents');
		data = await res.json();
	});
</script>
```

---

## Svelte 5 Runes Guide

This codebase uses **Svelte 5 runes** for reactivity. Here's a reference for new engineers:

### `$state()` - Reactive State

Declares reactive state that triggers re-renders on mutation.

```svelte
<script lang="ts">
	// Simple state
	let count = $state(0);

	// Typed state
	let items = $state<string[]>([]);

	// Object state
	let user = $state({ name: '', email: '' });
</script>

<button onclick={() => count++}>Count: {count}</button>
```

### `$derived()` - Computed Values

Creates a reactive value derived from other reactive values.

```svelte
<script lang="ts">
	let items = $state([1, 2, 3]);

	// Simple derived
	let total = $derived(items.reduce((a, b) => a + b, 0));

	// Complex derived with $derived.by()
	let stats = $derived.by(() => {
		return {
			count: items.length,
			average: items.length ? total / items.length : 0
		};
	});
</script>

<p>Total: {total}, Average: {stats.average}</p>
```

### `$effect()` - Side Effects

Runs side effects when dependencies change (similar to `useEffect`).

```svelte
<script lang="ts">
	let searchQuery = $state('');
	let results = $state([]);

	$effect(() => {
		// Runs when searchQuery changes
		fetchResults(searchQuery).then((r) => (results = r));
	});
</script>
```

### `$props()` - Component Props

Declares component props with TypeScript support.

```svelte
<script lang="ts">
	interface Props {
		title: string;
		count?: number; // Optional with ?
		onClose: () => void;
	}

	let { title, count = 0, onClose }: Props = $props();
</script>

<h1>{title} ({count})</h1>
<button onclick={onClose}>Close</button>
```

### Patterns Used in This Codebase

**Fetching on mount with effect:**

```svelte
<script lang="ts">
	let data = $state<Item[]>([]);
	let loading = $state(true);

	$effect(() => {
		fetchData();
	});

	async function fetchData() {
		loading = true;
		const res = await fetch('/api/items');
		data = await res.json();
		loading = false;
	}
</script>
```

**Filtered/sorted derived lists:**

```svelte
<script lang="ts">
	let items = $state<Project[]>([]);
	let searchQuery = $state('');
	let sortBy = $state<'name' | 'date'>('date');

	let filtered = $derived.by(() => {
		let result = items.filter((i) => i.name.toLowerCase().includes(searchQuery.toLowerCase()));
		return sortBy === 'name'
			? result.sort((a, b) => a.name.localeCompare(b.name))
			: result.sort((a, b) => b.date.localeCompare(a.date));
	});
</script>
```

---

## Design System

### Design Tokens

All design tokens are defined in `src/app.css`:

#### Colors

```css
:root {
	/* Backgrounds */
	--bg-base: #ffffff;
	--bg-subtle: #f8fafc;
	--bg-muted: #f1f5f9;

	/* Text */
	--text-primary: #0f172a;
	--text-secondary: #475569;
	--text-muted: #64748b;
	--text-faint: #94a3b8;

	/* Accent (Violet - Claude brand) */
	--accent: #7c3aed;
	--accent-hover: #6d28d9;
	--accent-subtle: rgba(124, 58, 237, 0.1);

	/* Semantic */
	--success: #10b981;
	--error: #ef4444;
	--warning: #f59e0b;
	--info: #3b82f6;

	/* Borders */
	--border: rgba(0, 0, 0, 0.08);
	--border-subtle: rgba(0, 0, 0, 0.05);
}
```

#### Typography

```css
:root {
	--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
	--font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

#### Spacing (4px Grid)

```css
:root {
	--spacing-1: 4px;
	--spacing-2: 8px;
	--spacing-3: 12px;
	--spacing-4: 16px;
	--spacing-6: 24px;
	--spacing-8: 32px;
	--spacing-12: 48px;
}
```

#### Border Radius

```css
:root {
	--radius-sm: 4px;
	--radius-md: 6px;
	--radius-lg: 8px;
}
```

### Using Design Tokens

Mix CSS custom properties with Tailwind utilities:

```svelte
<!-- Using CSS variables directly -->
<div
	class="p-4 rounded-lg"
	style="
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    color: var(--text-primary);
  "
>
	Content
</div>

<!-- Using Tailwind with slate palette (matches tokens) -->
<div class="p-4 bg-slate-50 border border-slate-200 text-slate-900 rounded-lg">Content</div>
```

### Markdown Styling

The `.markdown-preview` class in `app.css` provides consistent styling for rendered markdown in agents and skills viewers.

---

## API Integration

### Backend Endpoints

The frontend communicates with a FastAPI backend on `http://localhost:8000`:

| Endpoint                            | Method   | Description                       |
| ----------------------------------- | -------- | --------------------------------- |
| `/projects`                         | GET      | List all projects                 |
| `/projects/{encoded_name}`          | GET      | Get project with sessions         |
| `/projects/{encoded_name}/branches` | GET      | Get git branches                  |
| `/analytics`                        | GET      | Get usage analytics               |
| `/agents`                           | GET      | List agents                       |
| `/agents/{name}`                    | GET/POST | Get or save agent                 |
| `/skills`                           | GET      | List skills (with `?path=` query) |
| `/skills/content`                   | GET/POST | Get or save skill content         |

### Fetch Patterns

**In load functions:**

```typescript
export async function load({ fetch, params }) {
	// Use the provided fetch for SSR compatibility
	const res = await fetch(`http://localhost:8000/projects/${params.id}`);
	return { project: await res.json() };
}
```

**In components:**

```typescript
async function saveAgent() {
	const res = await fetch(`http://localhost:8000/agents/${name}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ content })
	});
	if (!res.ok) throw new Error('Failed to save');
}
```

---

## Coding Conventions

### Formatting (Prettier)

From `.prettierrc`:

```json
{
	"useTabs": true,
	"singleQuote": true,
	"trailingComma": "none",
	"printWidth": 100
}
```

- **Indentation**: Tabs (not spaces)
- **Quotes**: Single quotes for strings
- **Trailing commas**: None
- **Line width**: 100 characters

### Linting (ESLint)

From `eslint.config.js`:

- TypeScript strict mode enabled
- Unused variables must be prefixed with `_` (e.g., `_unused`)
- Svelte-specific rules from `eslint-plugin-svelte`

### TypeScript Conventions

1. **Interface for props**: Always define a `Props` interface

```typescript
interface Props {
	title: string;
	items: Item[];
}
let { title, items }: Props = $props();
```

2. **Explicit types for state**: Use generics with `$state`

```typescript
let items = $state<Item[]>([]);
let selected = $state<string | null>(null);
```

3. **Inline interfaces**: Define interfaces in the component when not shared

### Component Conventions

1. **Script block first**: `<script lang="ts">` at top
2. **Markup second**: Template HTML
3. **Style last**: `<style>` block (rarely used, prefer Tailwind)

### Naming Conventions

| Type          | Convention         | Example                |
| ------------- | ------------------ | ---------------------- |
| Components    | PascalCase         | `SessionCard.svelte`   |
| Routes        | kebab-case folders | `[encoded_name]/`      |
| Functions     | camelCase          | `formatDateTime()`     |
| Interfaces    | PascalCase         | `interface Session {}` |
| CSS variables | kebab-case         | `--text-primary`       |

---

## Contributing

### Before Submitting

1. **Type check**: `npm run check`
2. **Lint**: `npm run lint`
3. **Format**: `npm run format`
4. **Test build**: `npm run build && npm run preview`

### Adding a New Route

1. Create folder in `src/routes/` matching URL path
2. Add `+page.svelte` for the page component
3. Add `+page.ts` if data loading is needed
4. Update navigation in `Header.svelte` if needed

### Adding a New Component

1. Create in `src/lib/components/` (or appropriate subfolder)
2. Define `Props` interface with TypeScript
3. Use design tokens for consistent styling
4. Export from `$lib/index.ts` if publicly reusable

### Common Tasks

**Add a new filter control:**
See `TimeRangeFilter.svelte` for the pattern of preset buttons with custom option.

**Add a new data list:**
See `AgentList.svelte` for the pattern of fetching, searching, and grid display.

**Add a new editor view:**
See `AgentViewer.svelte` for the pattern of code/preview toggle with markdown rendering.

---

## Learn More

- [SvelteKit Documentation](https://svelte.dev/docs/kit)
- [Svelte 5 Runes](https://svelte.dev/docs/svelte/runes)
- [Tailwind CSS v4](https://tailwindcss.com/docs)
- [Lucide Icons](https://lucide.dev/icons)
- [Chart.js](https://www.chartjs.org/docs)
