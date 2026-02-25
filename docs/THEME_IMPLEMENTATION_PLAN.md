# Theme Implementation Plan - Refined

> **Reviewer:** Senior UI/UX Designer
> **Date:** January 2026
> **Status:** Ready for Implementation

---

## Executive Summary

This plan consolidates the design system to enable dark mode, improve data visualization consistency, and establish component token compliance. The implementation is structured in 6 phases with parallel execution where possible.

---

## Current State Analysis

### Token System Audit

**Defined in `app.css` (42 tokens):**

- Background: 3 tokens (`--bg-base`, `--bg-subtle`, `--bg-muted`)
- Text: 4 tokens (`--text-primary`, `--text-secondary`, `--text-muted`, `--text-faint`)
- Semantic: 9 tokens (accent, success, warning, error, info + subtle variants)
- Borders: 2 tokens (`--border`, `--border-subtle`)
- Spacing: 8 tokens (4px grid)
- Radius: 3 tokens (sm, md, lg)
- Shadow: 1 token (`--shadow-elevated`)
- Animation: 2 tokens + 1 easing curve
- Fonts: 2 tokens (sans, mono)

**Missing Tokens (referenced but undefined):**

```
--accent-primary    → used in ProjectCard.svelte
--border-hover      → used in SessionCard.svelte
--radius-xs         → used in ProjectCard.svelte
--duration-normal   → used in components
```

### Component Token Compliance

| Component                | CSS Vars | Hardcoded | Compliance |
| ------------------------ | -------- | --------- | ---------- |
| StatsCard.svelte         | 100%     | 0%        | Excellent  |
| Badge.svelte (semantic)  | 60%      | 40%       | Fair       |
| ProjectCard.svelte       | 80%      | 20%       | Good       |
| TimelineEventCard.svelte | 60%      | 40%       | Poor       |
| Header.svelte            | 0%       | 100%      | Critical   |
| NavigationCard.svelte    | 0%       | 100%      | Critical   |
| ModelBadge.svelte        | 0%       | 100%      | Critical   |
| tool-icons.ts            | 0%       | 100%      | Critical   |

### Hardcoded Color Inventory

**Header.svelte (28 instances):**

- `bg-white`, `border-slate-200`, `text-slate-900`, `text-slate-700`, `text-slate-600`, `text-slate-500`, `text-slate-400`
- `bg-emerald-50/50`, `border-emerald-100/60`, `bg-emerald-500`, `text-emerald-700/90`
- `bg-slate-100`, `hover:bg-slate-50`

**NavigationCard.svelte (6 color schemes):**

```typescript
blue: 'text-blue-600 bg-blue-50/50 border-blue-200/50';
green: 'text-emerald-600 bg-emerald-50/50 border-emerald-200/50';
orange: 'text-orange-600 bg-orange-50/50 border-orange-200/50';
purple: 'text-violet-600 bg-violet-50/50 border-violet-200/50';
gray: 'text-slate-600 bg-slate-50/50 border-slate-200/50';
red: 'text-rose-600 bg-rose-50/50 border-rose-200/50';
```

**ModelBadge.svelte (4 color schemes):**

```typescript
opus:    'bg-purple-100 text-purple-700 border-purple-200'
sonnet:  'bg-blue-100 text-blue-700 border-blue-200'
haiku:   'bg-emerald-100 text-emerald-700 border-emerald-200'
default: 'bg-slate-100 text-slate-700 border-slate-200'
```

**tool-icons.ts (6 event types):**

```typescript
prompt: ('text-blue-400', 'bg-blue-500/20', 'border-blue-500/40');
tool_call: ('text-emerald-400', 'bg-emerald-500/20', 'border-emerald-500/40');
subagent_spawn: ('text-purple-400', 'bg-purple-500/20', 'border-purple-500/40');
thinking: ('text-amber-400', 'bg-amber-500/20', 'border-amber-500/40');
response: ('text-slate-400', 'bg-slate-500/20', 'border-slate-500/40');
todo_update: ('text-violet-400', 'bg-violet-500/20', 'border-violet-500/40');
```

**TimelineEventCard.svelte (status badges):**

- Subagent: `bg-purple-500/20`, `text-purple-400`
- Pending: `bg-yellow-500/20`, `text-yellow-400`
- Error: `bg-red-500/20`, `text-red-400`
- Done: `bg-green-500/20`, `text-green-400`

**Badge.svelte (4 hardcoded variants):**

```typescript
purple: 'bg-purple-100 text-purple-700 border-purple-200';
blue: 'bg-blue-100 text-blue-700 border-blue-200';
emerald: 'bg-emerald-100 text-emerald-700 border-emerald-200';
slate: 'bg-slate-100 text-slate-700 border-slate-200';
```

---

## Phase 1: Token Foundation

### 1.1 Fix Missing Tokens

Add to `app.css` after line 34:

```css
/* Missing tokens (currently referenced but undefined) */
--accent-primary: var(--accent);
--border-hover: rgba(0, 0, 0, 0.12);
--radius-xs: 2px;
--duration-normal: 300ms;

/* RGB values for opacity control in gradients */
--accent-rgb: 124, 58, 237;
--success-rgb: 16, 185, 129;
--warning-rgb: 245, 158, 11;
--error-rgb: 239, 68, 68;
--info-rgb: 59, 130, 246;
```

### 1.2 Add Model Color Tokens

Add after semantic colors (line 47):

```css
/* Model Family Colors */
--model-opus: #7c3aed;
--model-opus-subtle: rgba(124, 58, 237, 0.1);
--model-sonnet: #3b82f6;
--model-sonnet-subtle: rgba(59, 130, 246, 0.1);
--model-haiku: #10b981;
--model-haiku-subtle: rgba(16, 185, 129, 0.1);
```

### 1.3 Add Event Type Color Tokens

Add after model colors:

```css
/* Event Type Colors */
--event-prompt: #3b82f6;
--event-prompt-subtle: rgba(59, 130, 246, 0.2);
--event-tool: #10b981;
--event-tool-subtle: rgba(16, 185, 129, 0.2);
--event-subagent: #8b5cf6;
--event-subagent-subtle: rgba(139, 92, 246, 0.2);
--event-thinking: #f59e0b;
--event-thinking-subtle: rgba(245, 158, 11, 0.2);
--event-response: #64748b;
--event-response-subtle: rgba(100, 116, 139, 0.2);
--event-todo: #7c3aed;
--event-todo-subtle: rgba(124, 58, 237, 0.2);
```

### 1.4 Add Data Visualization Tokens

Add after event colors:

```css
/* Data Visualization Palette */
--data-primary: var(--accent);
--data-secondary: var(--info);
--data-tertiary: var(--success);
--data-quaternary: var(--warning);
--data-quinary: var(--error);
```

### 1.5 Add Navigation Color Tokens

Add after data viz:

```css
/* Navigation Card Colors (for icon backgrounds) */
--nav-blue: #3b82f6;
--nav-blue-subtle: rgba(59, 130, 246, 0.08);
--nav-green: #10b981;
--nav-green-subtle: rgba(16, 185, 129, 0.08);
--nav-orange: #f97316;
--nav-orange-subtle: rgba(249, 115, 22, 0.08);
--nav-purple: #8b5cf6;
--nav-purple-subtle: rgba(139, 92, 246, 0.08);
--nav-gray: #64748b;
--nav-gray-subtle: rgba(100, 116, 139, 0.08);
--nav-red: #f43f5e;
--nav-red-subtle: rgba(244, 63, 94, 0.08);
```

### 1.6 Add Shadow Tokens

Add after shadows (line 67):

```css
/* Extended Shadow System */
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
--shadow-md: 0 2px 8px rgba(0, 0, 0, 0.08);
--shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.12);
```

---

## Phase 2: Dark Mode Foundation

### 2.1 Add Dark Mode Tokens

Add after the `:root` block (after line 73):

```css
/* ============================================
   DARK MODE TOKENS
   ============================================ */

:root[data-theme='dark'] {
	/* Background (dark slate) */
	--bg-base: #0f1419;
	--bg-subtle: #1a1f26;
	--bg-muted: #242b35;

	/* Text (inverted) */
	--text-primary: #f1f5f9;
	--text-secondary: #94a3b8;
	--text-muted: #64748b;
	--text-faint: #475569;

	/* Borders (white-based for dark bg) */
	--border: rgba(255, 255, 255, 0.08);
	--border-subtle: rgba(255, 255, 255, 0.05);
	--border-hover: rgba(255, 255, 255, 0.15);

	/* Accent (lighter for dark mode) */
	--accent: #a78bfa;
	--accent-hover: #c4b5fd;
	--accent-subtle: rgba(167, 139, 250, 0.15);
	--accent-muted: rgba(167, 139, 250, 0.08);
	--accent-primary: var(--accent);

	/* Semantic (adjusted for contrast) */
	--success: #34d399;
	--success-subtle: rgba(52, 211, 153, 0.15);
	--error: #f87171;
	--error-subtle: rgba(248, 113, 113, 0.15);
	--warning: #fbbf24;
	--warning-subtle: rgba(251, 191, 36, 0.15);
	--info: #60a5fa;
	--info-subtle: rgba(96, 165, 250, 0.15);

	/* Model Colors (lighter for dark mode) */
	--model-opus: #a78bfa;
	--model-opus-subtle: rgba(167, 139, 250, 0.2);
	--model-sonnet: #60a5fa;
	--model-sonnet-subtle: rgba(96, 165, 250, 0.2);
	--model-haiku: #34d399;
	--model-haiku-subtle: rgba(52, 211, 153, 0.2);

	/* Event Colors (lighter) */
	--event-prompt: #60a5fa;
	--event-prompt-subtle: rgba(96, 165, 250, 0.25);
	--event-tool: #34d399;
	--event-tool-subtle: rgba(52, 211, 153, 0.25);
	--event-subagent: #a78bfa;
	--event-subagent-subtle: rgba(167, 139, 250, 0.25);
	--event-thinking: #fbbf24;
	--event-thinking-subtle: rgba(251, 191, 36, 0.25);
	--event-response: #94a3b8;
	--event-response-subtle: rgba(148, 163, 184, 0.25);
	--event-todo: #a78bfa;
	--event-todo-subtle: rgba(167, 139, 250, 0.25);

	/* Navigation Colors */
	--nav-blue: #60a5fa;
	--nav-blue-subtle: rgba(96, 165, 250, 0.15);
	--nav-green: #34d399;
	--nav-green-subtle: rgba(52, 211, 153, 0.15);
	--nav-orange: #fb923c;
	--nav-orange-subtle: rgba(251, 146, 60, 0.15);
	--nav-purple: #a78bfa;
	--nav-purple-subtle: rgba(167, 139, 250, 0.15);
	--nav-gray: #94a3b8;
	--nav-gray-subtle: rgba(148, 163, 184, 0.15);
	--nav-red: #fb7185;
	--nav-red-subtle: rgba(251, 113, 133, 0.15);

	/* Shadows (deeper for dark mode) */
	--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
	--shadow-md: 0 2px 8px rgba(0, 0, 0, 0.4);
	--shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.5);
	--shadow-elevated: 0 0 0 0.5px var(--border), 0 4px 12px rgba(0, 0, 0, 0.4);
}

/* System preference fallback */
@media (prefers-color-scheme: dark) {
	:root:not([data-theme='light']) {
		/* Inherits from [data-theme="dark"] above */
		--bg-base: #0f1419;
		--bg-subtle: #1a1f26;
		--bg-muted: #242b35;
		--text-primary: #f1f5f9;
		--text-secondary: #94a3b8;
		--text-muted: #64748b;
		--text-faint: #475569;
		--border: rgba(255, 255, 255, 0.08);
		--border-subtle: rgba(255, 255, 255, 0.05);
		--border-hover: rgba(255, 255, 255, 0.15);
		--accent: #a78bfa;
		--accent-hover: #c4b5fd;
		--accent-subtle: rgba(167, 139, 250, 0.15);
		--accent-muted: rgba(167, 139, 250, 0.08);
		--accent-primary: var(--accent);
	}
}
```

---

## Phase 3: Component Token Compliance

### 3.1 Header.svelte

**Current Issues:** 100% hardcoded Tailwind colors

**Required Changes:**

Replace all color classes with CSS variables:

| Current                               | Replace With                   |
| ------------------------------------- | ------------------------------ |
| `bg-white`                            | `bg-[var(--bg-base)]`          |
| `border-slate-200`                    | `border-[var(--border)]`       |
| `text-slate-900`                      | `text-[var(--text-primary)]`   |
| `text-slate-700`                      | `text-[var(--text-secondary)]` |
| `text-slate-600`                      | `text-[var(--text-secondary)]` |
| `text-slate-500`                      | `text-[var(--text-muted)]`     |
| `text-slate-400`                      | `text-[var(--text-muted)]`     |
| `bg-slate-100`                        | `bg-[var(--bg-muted)]`         |
| `bg-slate-50`                         | `bg-[var(--bg-subtle)]`        |
| `bg-emerald-50/50`                    | `bg-[var(--success-subtle)]`   |
| `border-emerald-100/60`               | `border-[var(--success)]/30`   |
| `bg-emerald-500`                      | `bg-[var(--success)]`          |
| `text-emerald-700/90`                 | `text-[var(--success)]`        |
| `hover:bg-slate-100`                  | `hover:bg-[var(--bg-muted)]`   |
| `hover:bg-slate-50`                   | `hover:bg-[var(--bg-subtle)]`  |
| `shadow-[0_2px_8px_rgba(0,0,0,0.02)]` | `shadow-[var(--shadow-sm)]`    |

**Lines to modify:** 57-227

### 3.2 NavigationCard.svelte

**Current Issues:** Hardcoded 6-color scheme

**Required Changes:**

Replace `colorClasses` object (lines 15-22):

```typescript
const colorClasses = {
	blue: 'text-[var(--nav-blue)] bg-[var(--nav-blue-subtle)] border-[var(--nav-blue)]/30',
	green: 'text-[var(--nav-green)] bg-[var(--nav-green-subtle)] border-[var(--nav-green)]/30',
	orange: 'text-[var(--nav-orange)] bg-[var(--nav-orange-subtle)] border-[var(--nav-orange)]/30',
	purple: 'text-[var(--nav-purple)] bg-[var(--nav-purple-subtle)] border-[var(--nav-purple)]/30',
	gray: 'text-[var(--nav-gray)] bg-[var(--nav-gray-subtle)] border-[var(--nav-gray)]/30',
	red: 'text-[var(--nav-red)] bg-[var(--nav-red-subtle)] border-[var(--nav-red)]/30'
};
```

Also replace (line 27):

- `bg-white` → `bg-[var(--bg-base)]`
- `border-slate-200` → `border-[var(--border)]`
- `hover:border-slate-300` → `hover:border-[var(--border-hover)]`
- `active:bg-slate-50/50` → `active:bg-[var(--bg-subtle)]`

Replace text classes (lines 37-43):

- `text-slate-900` → `text-[var(--text-primary)]`
- `text-slate-500` → `text-[var(--text-muted)]`
- `hover:text-slate-600` → `hover:text-[var(--text-secondary)]`

### 3.3 ModelBadge.svelte

**Current Issues:** 4 hardcoded color schemes

**Required Changes:**

Replace `colorClass` derived (lines 18-23):

```typescript
const colorClass = $derived.by(() => {
	if (modelName.includes('opus'))
		return 'bg-[var(--model-opus-subtle)] text-[var(--model-opus)] border-[var(--model-opus)]/40';
	if (modelName.includes('sonnet'))
		return 'bg-[var(--model-sonnet-subtle)] text-[var(--model-sonnet)] border-[var(--model-sonnet)]/40';
	if (modelName.includes('haiku'))
		return 'bg-[var(--model-haiku-subtle)] text-[var(--model-haiku)] border-[var(--model-haiku)]/40';
	return 'bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border)]';
});
```

### 3.4 tool-icons.ts

**Current Issues:** 6 event types with hardcoded colors

**Required Changes:**

Replace `eventTypeConfig` (lines 79-116):

```typescript
export const eventTypeConfig = {
	prompt: {
		icon: MessageSquareIcon,
		color: 'text-[var(--event-prompt)]',
		bgColor: 'bg-[var(--event-prompt-subtle)]',
		borderColor: 'border-[var(--event-prompt)]/40'
	},
	tool_call: {
		icon: TerminalIcon,
		color: 'text-[var(--event-tool)]',
		bgColor: 'bg-[var(--event-tool-subtle)]',
		borderColor: 'border-[var(--event-tool)]/40'
	},
	subagent_spawn: {
		icon: BotIcon,
		color: 'text-[var(--event-subagent)]',
		bgColor: 'bg-[var(--event-subagent-subtle)]',
		borderColor: 'border-[var(--event-subagent)]/40'
	},
	thinking: {
		icon: BrainIcon,
		color: 'text-[var(--event-thinking)]',
		bgColor: 'bg-[var(--event-thinking-subtle)]',
		borderColor: 'border-[var(--event-thinking)]/40'
	},
	response: {
		icon: MessageCircleIcon,
		color: 'text-[var(--event-response)]',
		bgColor: 'bg-[var(--event-response-subtle)]',
		borderColor: 'border-[var(--event-response)]/40'
	},
	todo_update: {
		icon: ListTodoIcon,
		color: 'text-[var(--event-todo)]',
		bgColor: 'bg-[var(--event-todo-subtle)]',
		borderColor: 'border-[var(--event-todo)]/40'
	}
} as const;
```

### 3.5 TimelineEventCard.svelte

**Current Issues:** Status badges with hardcoded colors

**Required Changes:**

Lines 146-151 (subagent badge):

```svelte
<span class="inline-flex items-center gap-1 rounded-full bg-[var(--event-subagent-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--event-subagent)]">
```

Lines 165-169 (pending badge):

```svelte
<span class="inline-flex items-center gap-1 rounded-full bg-[var(--warning-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--warning)]">
```

Lines 171-177 (error badge):

```svelte
<span class="inline-flex items-center gap-1 rounded-full bg-[var(--error-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--error)]">
```

Lines 178-184 (done badge):

```svelte
<span class="inline-flex items-center gap-1 rounded-full bg-[var(--success-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--success)]">
```

Lines 189-196 (spawned agent badge):

```svelte
<span class="inline-flex items-center gap-1 rounded-full bg-[var(--event-subagent-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--event-subagent)]">
```

Line 267 (copy check icon):

```svelte
<Check size={14} class="text-[var(--success)]" />
```

### 3.6 Badge.svelte

**Current Issues:** 4 hardcoded specialty variants mixed with token-compliant semantic variants

**Required Changes:**

Replace `variantClasses` lines 32-43:

```typescript
const variantClasses = {
	default: 'bg-[var(--bg-muted)] text-[var(--text-primary)] border-[var(--border)]',
	accent: 'bg-[var(--accent-subtle)] text-[var(--accent)] border-[var(--accent)]',
	success: 'bg-[var(--success-subtle)] text-[var(--success)] border-[var(--success)]',
	warning: 'bg-[var(--warning-subtle)] text-[var(--warning)] border-[var(--warning)]',
	error: 'bg-[var(--error-subtle)] text-[var(--error)] border-[var(--error)]',
	info: 'bg-[var(--info-subtle)] text-[var(--info)] border-[var(--info)]',
	purple: 'bg-[var(--model-opus-subtle)] text-[var(--model-opus)] border-[var(--model-opus)]/40',
	blue: 'bg-[var(--model-sonnet-subtle)] text-[var(--model-sonnet)] border-[var(--model-sonnet)]/40',
	emerald:
		'bg-[var(--model-haiku-subtle)] text-[var(--model-haiku)] border-[var(--model-haiku)]/40',
	slate: 'bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border)]'
};
```

---

## Phase 4: Chart System Update

### 4.1 chartConfig.ts

**Current Issues:** Hardcoded hex palette

**Required Changes:**

Replace `chartColorPalette` (lines 109-120):

```typescript
/**
 * Get chart colors from CSS variables (for dynamic theme support)
 * Call this in onMount or use getComputedStyle for live values
 */
export function getChartColorPalette(): string[] {
	if (typeof window === 'undefined') {
		// SSR fallback
		return ['#7c3aed', '#3b82f6', '#10b981', '#f59e0b', '#ef4444'];
	}

	const style = getComputedStyle(document.documentElement);
	return [
		style.getPropertyValue('--data-primary').trim() || '#7c3aed',
		style.getPropertyValue('--data-secondary').trim() || '#3b82f6',
		style.getPropertyValue('--data-tertiary').trim() || '#10b981',
		style.getPropertyValue('--data-quaternary').trim() || '#f59e0b',
		style.getPropertyValue('--data-quinary').trim() || '#ef4444'
	];
}

// Legacy export for backwards compatibility
export const chartColorPalette = [
	'var(--data-primary)',
	'var(--data-secondary)',
	'var(--data-tertiary)',
	'var(--data-quaternary)',
	'var(--data-quinary)'
];
```

**Note:** Chart.js may not resolve CSS variables directly. Components using charts should call `getChartColorPalette()` in `onMount` to get computed values.

---

## Phase 5: Markdown Preview Dark Mode

### 5.1 app.css - Markdown Styles

**Current Issues:** All hardcoded slate/emerald colors

**Required Changes:**

Replace `.markdown-preview` styles (lines 82-141):

```css
/* Markdown Preview Styles */
.markdown-preview {
	@apply leading-relaxed;
	color: var(--text-primary);
}

.markdown-preview h1 {
	@apply text-2xl font-semibold mt-8 mb-4 tracking-tight pb-2;
	color: var(--text-primary);
	border-bottom: 1px solid var(--border);
}

.markdown-preview h2 {
	@apply text-xl font-semibold mt-8 mb-3 tracking-tight;
	color: var(--text-primary);
}

.markdown-preview h3 {
	@apply text-lg font-medium mt-6 mb-2;
	color: var(--text-primary);
}

.markdown-preview p {
	@apply mb-4 leading-7;
	color: var(--text-secondary);
}

.markdown-preview ul {
	@apply list-disc list-outside ml-5 mb-4 space-y-1;
	color: var(--text-secondary);
}

.markdown-preview ol {
	@apply list-decimal list-outside ml-5 mb-4 space-y-1;
	color: var(--text-secondary);
}

.markdown-preview li {
	@apply pl-1;
}

.markdown-preview code {
	@apply font-mono text-sm px-1.5 py-0.5 rounded;
	background-color: var(--bg-muted);
	color: var(--text-primary);
	border: 1px solid var(--border-subtle);
}

.markdown-preview pre {
	@apply p-4 rounded-lg overflow-auto mb-6;
	background-color: var(--bg-subtle);
	border: 1px solid var(--border);
}

.markdown-preview pre code {
	@apply p-0 border-none block;
	background-color: transparent;
	color: var(--text-primary);
}

.markdown-preview blockquote {
	@apply pl-4 py-1 my-6 italic rounded-r-lg;
	border-left: 4px solid var(--accent);
	color: var(--text-muted);
	background-color: var(--accent-muted);
}

.markdown-preview a {
	@apply hover:underline font-medium decoration-1 underline-offset-2;
	color: var(--accent);
}

.markdown-preview strong {
	@apply font-semibold;
	color: var(--text-primary);
}

.markdown-preview hr {
	@apply my-8;
	border-color: var(--border);
}
```

---

## Phase 6: Theme Toggle Component

### 6.1 Create ThemeToggle.svelte

**File:** `frontend/src/lib/components/ui/ThemeToggle.svelte`

```svelte
<script lang="ts">
	import { Sun, Moon, Monitor } from 'lucide-svelte';
	import { onMount } from 'svelte';

	type Theme = 'light' | 'dark' | 'system';

	let theme = $state<Theme>('system');

	onMount(() => {
		// Get stored preference
		const stored = localStorage.getItem('theme') as Theme | null;
		if (stored) {
			theme = stored;
			applyTheme(stored);
		}
	});

	function applyTheme(newTheme: Theme) {
		const root = document.documentElement;

		if (newTheme === 'system') {
			root.removeAttribute('data-theme');
		} else {
			root.setAttribute('data-theme', newTheme);
		}

		localStorage.setItem('theme', newTheme);
	}

	function cycleTheme() {
		const themes: Theme[] = ['light', 'dark', 'system'];
		const currentIndex = themes.indexOf(theme);
		const nextIndex = (currentIndex + 1) % themes.length;
		theme = themes[nextIndex];
		applyTheme(theme);
	}
</script>

<button
	onclick={cycleTheme}
	class="
        p-2 rounded-lg
        text-[var(--text-muted)]
        hover:text-[var(--text-primary)]
        hover:bg-[var(--bg-muted)]
        transition-colors duration-200
    "
	title="Toggle theme ({theme})"
	aria-label="Toggle theme, currently {theme}"
>
	{#if theme === 'light'}
		<Sun size={16} strokeWidth={2} />
	{:else if theme === 'dark'}
		<Moon size={16} strokeWidth={2} />
	{:else}
		<Monitor size={16} strokeWidth={2} />
	{/if}
</button>
```

### 6.2 Integrate into Header.svelte

Add import at top of script:

```typescript
import ThemeToggle from './ui/ThemeToggle.svelte';
```

Add in the right section of the compact header (line 147-158 area):

```svelte
<div class="flex items-center gap-2">
	<ThemeToggle />
	<!-- existing timeline stats -->
</div>
```

---

## Implementation Order & Dependencies

```
Phase 1 (Foundation)     ─────┐
  ├─ 1.1 Missing tokens      │
  ├─ 1.2 Model tokens        ├─→ Can run in parallel
  ├─ 1.3 Event tokens        │
  ├─ 1.4 Data viz tokens     │
  ├─ 1.5 Nav tokens          │
  └─ 1.6 Shadow tokens       ┘

Phase 2 (Dark Mode)      ─────→ Depends on Phase 1

Phase 3 (Components)     ─────┐
  ├─ 3.1 Header              │
  ├─ 3.2 NavigationCard      │
  ├─ 3.3 ModelBadge          ├─→ Can run in parallel (after Phase 1)
  ├─ 3.4 tool-icons.ts       │
  ├─ 3.5 TimelineEventCard   │
  └─ 3.6 Badge               ┘

Phase 4 (Charts)         ─────→ Can run parallel to Phase 3 (after Phase 1)

Phase 5 (Markdown)       ─────→ Can run parallel to Phase 3 (after Phase 2)

Phase 6 (Toggle)         ─────→ Depends on Phase 2
```

---

## Testing Checklist

### Visual Regression

- [ ] Light mode renders identically to current state
- [ ] Dark mode has WCAG AA contrast ratios
- [ ] Charts render correctly in both modes
- [ ] Timeline events are distinguishable by type
- [ ] Model badges are readable
- [ ] Navigation cards maintain visual hierarchy

### Functional

- [ ] Theme toggle cycles: light → dark → system
- [ ] Theme persists across page refresh
- [ ] System preference detection works
- [ ] No flash of incorrect theme on load

### Edge Cases

- [ ] Very long session timelines render correctly
- [ ] Charts with many data points don't lose color distinction
- [ ] Nested components inherit theme correctly

---

## Risk Mitigation

| Risk                               | Impact | Mitigation                                 |
| ---------------------------------- | ------ | ------------------------------------------ |
| Chart.js CSS var incompatibility   | High   | Use `getComputedStyle()` in `onMount`      |
| Tailwind purge removes var classes | Medium | Add safelist in tailwind.config            |
| Flash of unstyled content          | Low    | Inline theme script in `app.html` `<head>` |
| Contrast violations                | Medium | Test with axe-core / Lighthouse            |

---

## Post-Implementation

1. **Add FOUC prevention script** to `app.html`:

```html
<script>
	(function () {
		const theme = localStorage.getItem('theme');
		if (theme && theme !== 'system') {
			document.documentElement.setAttribute('data-theme', theme);
		}
	})();
</script>
```

2. **Add Tailwind safelist** to prevent purging:

```javascript
// tailwind.config.js
safelist: [
	{ pattern: /bg-\[var\(--.*\)\]/ },
	{ pattern: /text-\[var\(--.*\)\]/ },
	{ pattern: /border-\[var\(--.*\)\]/ }
];
```

---

## Summary

This refined plan:

- Fixes 4 missing token definitions
- Adds 36 new tokens for comprehensive coverage
- Updates 7 files with 100+ line changes
- Creates 1 new component (ThemeToggle)
- Enables full dark mode support
- Maintains backwards compatibility
- Provides clear testing criteria

Ready for implementation approval.
