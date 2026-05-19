# Design Brief — `/tickets` Kanban Board

**Date:** 2026-05-19
**Branch:** `feat/session-ticket-linking` (post-v0.2.0)
**Builds on:** [Ticket Linking UI brief, 2026-05-18](./2026-05-18-ticket-linking-ui.md)
**Audience:** Claude Design (`claude.ai/design`)

---

## How to use this brief

Paste this entire document into a fresh `claude.ai/design` conversation. It is the only context you need. When you reply, please return **two or three rendered variants** (HTML or Svelte/Tailwind in Artifacts) for each numbered question in §8, with rationale and class strings I can lift directly into `frontend/src/routes/tickets/+page.svelte`.

---

## 1. Problem in one sentence

The `/tickets` page is a single dense table sorted by `last_linked_at` — fine for "what did I touch today?" but terrible for **"what's the state of my work?"**; we want to add a kanban-shaped *view* (read-only, board lives alongside the existing table behind a toggle) that surfaces ticket status at a glance without pretending karma can write back to Linear/Jira/GitHub.

## 2. Goals

- A **status-grouped board view** that is honestly read-only — drag affordances absent, "you're inspecting your work, not managing it" voice
- A **board ↔ table toggle** so power users with many tickets keep the scannable table
- A **canonical 5-column taxonomy** that maps cleanly onto provider-specific vocabularies (already half-implemented in `normalizeStatus()`)
- A **ticket card** that survives at any density — 4 tickets total (the typical user) and 50+ tickets (heavy users) both look intentional
- **Aesthetic continuity** with the existing terminal-flavored `/tickets` design (`$ tickets [N linked]` headers, mono, dashed borders) — or a deliberate alternative if the kanban metaphor benefits from a softer voice

## 3. Non-goals

- **No drag-and-drop.** Karma never writes to providers. Cards can be clicked through, not moved.
- **No new icon library, no new CSS framework, no new fonts.** Tailwind 4 + lucide-svelte only.
- **No backend changes.** All grouping happens client-side from the existing `GET /tickets` response.
- **No new status taxonomy.** Reuse the `StatusKey` already in `ticket-helpers.ts`.

## 4. In-scope surfaces

| Surface | File | Today |
|---|---|---|
| `/tickets` index page | `frontend/src/routes/tickets/+page.svelte` | Provider segmented filter + search + table |
| `/tickets` server load | `frontend/src/routes/tickets/+page.server.ts` | Reads `q`, `provider`, `project` query params |
| New: `<TicketsBoard>` component | `frontend/src/lib/components/tickets/TicketsBoard.svelte` | TO CREATE |
| New: `<TicketCard>` component | `frontend/src/lib/components/tickets/TicketCard.svelte` | TO CREATE — extracted from existing table-row markup |
| `<TicketBadge>` | `frontend/src/lib/components/tickets/TicketBadge.svelte` | Reused as-is for provider badges |
| Helpers | `frontend/src/lib/ticket-helpers.ts` | Reuses `normalizeStatus`, `statusColorVar`, `PROVIDER_META`, `formatRelative` |
| Project Tickets tab | `frontend/src/lib/components/tickets/ProjectTicketsTab.svelte` | OUT OF SCOPE this brief — table only. Possible future application. |

## 5. Constraints (must honor)

- **Framework:** SvelteKit 2 + Svelte 5 runes (`$state`, `$derived`, `$props`)
- **Styling:** Tailwind CSS 4 utilities only
- **Icons:** lucide-svelte (pick from existing set)
- **Read-only:** No drag, no in-place edit, no "create ticket" affordance
- **URL state:** view toggle persists via `?view=board` (kanban) or absence/`?view=table` (table, current default)
- **Design tokens** already defined in `frontend/src/app.css`:

  ```css
  /* Backgrounds */
  --bg-base       /* canvas */
  --bg-subtle     /* cards, sections */
  --bg-muted      /* nested inputs, table headers */
  --accent-subtle /* hover, active filter chips */

  /* Text */
  --text-primary
  --text-secondary
  --text-muted
  --text-faint    /* timestamps */

  /* Border */
  --border
  --border-subtle

  /* Status (semantic, already wired) */
  --status-todo
  --status-active
  --status-review
  --status-done
  --status-closed
  ```

- **Existing status keys** in `ticket-helpers.ts` (re-use verbatim):

  ```ts
  type StatusKey = 'todo' | 'active' | 'review' | 'done' | 'closed' | 'unknown';
  ```

## 6. Pre-resolved decisions (do NOT re-litigate)

| Q | Decision |
|---|---|
| Replace the table or add a toggle? | **Toggle.** Segmented control top-right. URL state `?view=board`. Table is default to preserve existing bookmark behavior. |
| Status taxonomy | **5 canonical columns** matching existing `StatusKey`: `todo` · `active` · `review` · `done` · `closed`. Tickets with `unknown` status (no status data yet) go into a 6th implicit column called **Unsorted** that auto-hides when empty. |
| Drag-and-drop? | **No.** Karma is read-only. The voice ("inspect", "audit", "trace") should reinforce that. |
| Empty-column behavior | **Show empty columns by default** so the taxonomy is visible. Provide a "Hide empty" affordance (toggle / chip) that persists in localStorage. |
| Counts in column headers | **Yes.** Every column header shows `[N]` even when 0. |
| Provider mixing within columns | **Yes.** A `done` column contains Linear-Done + Jira-Done + GitHub-Closed cards mixed, sorted by `last_linked_at`. |

## 7. Three direction options

The kanban metaphor is generic; your three options differ in **voice**, not in functionality. Pick one to lead with (variants on it are welcome). The other two are sketched for context.

### Direction A — Terminal Kanban (recommended starting point)

Matches the existing `/tickets` page aesthetic. Columns are presented as labeled groups in the terminal output of a fictional `karma tickets --group-by status` command.

```
┌─ $ tickets --group-by status ─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                               │
│  todo · 3       active · 1         review · 0       done · 5                          closed · 2              │
│  ─────────      ──────────         ──────────       ────────                          ─────────               │
│  ▸ LIN AB-9     ▸ GH foo/bar#42                     ▸ LIN DE-246  Backlog→Done        ▸ GH foo/bar#99         │
│    Fix login      Refactor auth                       Airflow Slack Bot                  Won't fix            │
│    2 sess · 2h    8 sess · live                       2 sess · 4 projects · 3h           1 sess · 1d          │
│                                                                                                               │
│  ▸ JIRA PROJ-42                                     ▸ GH foo/bar#7   merged                                   │
│    Migrate DB                                         Provider colors                                         │
│    1 sess · 5h                                        1 sess · 6h                                             │
│                                                                                                               │
│  ▸ LIN AB-10                                        ▸ ...                                                     │
│    …                                                                                                          │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Visual rules:**
- Mono-spaced section headers (`todo · 3`) in `var(--text-muted)`, underlined with `─` to evoke `tabulate`
- Cards are flat divs with `border-l-2` colored by `--status-{key}` — no card shadows
- Column width: fixed `min-w-[280px]`, horizontal scroll if needed on narrow viewports
- Vertical lane separators: faint `border-l border-dashed`
- No background fill on columns — let `--bg-base` show through
- Card hover: `bg-[var(--accent-subtle)]` only; no transform/scale
- Live session indicator (when applicable): a small green pulsing dot in the right of the card row

### Direction B — Editorial Inbox

Departs from the terminal voice. Cards become more "blog-card" — bigger title, generous whitespace, status as a small uppercase tag in the corner. Reads like Linear's own board view but quieter.

```
┌─────────────────────────────────┐ ┌─────────────────────────────────┐
│  TODO                       3   │ │  ACTIVE                     1   │
│                                 │ │                                 │
│  ┌───────────────────────────┐  │ │  ┌───────────────────────────┐  │
│  │ Fix login bug             │  │ │  │ Refactor auth middleware  │  │
│  │ LINEAR · AB-9             │  │ │  │ GITHUB · foo/bar#42       │  │
│  │ 2 sessions · 2h ago       │  │ │  │ 8 sessions · live now     │  │
│  └───────────────────────────┘  │ │  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │ │                                 │
│  │ Migrate DB to Postgres    │  │ │                                 │
│  │ JIRA · PROJ-42            │  │ │                                 │
│  │ 1 session · 5h ago        │  │ │                                 │
│  └───────────────────────────┘  │ │                                 │
└─────────────────────────────────┘ └─────────────────────────────────┘
```

**Trade-off:** clearer at low density, but breaks the existing aesthetic. Adds visual weight that's already heavy from the project Tickets tab.

### Direction C — Status Strip + Persistent Table

Hybrid. The table stays — but above it sits a horizontal strip with 5 cells showing canonical-status counts and a top-3 list per status. Click a cell → filters the table below.

```
┌── todo ─── 3 ─┐ ┌─ active ── 1 ─┐ ┌─ review ─ 0 ─┐ ┌── done ── 5 ─┐ ┌─ closed ─ 2 ─┐
│ AB-9 Fix lo… │ │ foo/bar#42    │ │              │ │ DE-246 Airfl…│ │ foo/bar#99   │
│ PROJ-42 Migr…│ │               │ │              │ │ foo/bar#7    │ │ PROJ-9 Won't…│
│ AB-10 …      │ │               │ │              │ │ AB-3 …       │ │              │
└──────────────┘ └───────────────┘ └──────────────┘ └──────────────┘ └──────────────┘

[same table as today, optionally pre-filtered by clicked strip cell]
```

**Trade-off:** ~zero new design surface, but doesn't really feel like a kanban. Useful as a fallback if the toggle is over-engineering.

## 8. Variant questions for Claude Design

For each, return 2–3 alternatives I can lift directly into Svelte/Tailwind.

### Q1 — Column header treatment

Three variants for the `todo · 3` header in Direction A. Goals: scannable, on-aesthetic, communicates status semantics without color overload.

### Q2 — Card row

Variants for a single ticket card. Required content: provider badge · external_key (mono) · title (1-2 lines, truncated) · session_count + last_linked relative time. Optional: project chip(s) for cross-project tickets (we just shipped this — DE-246 spans 2 projects on the dashboard right now). Status dot is implicit via the column it lives in.

### Q3 — The toggle control

Where does `[Board] [Table]` live? Top-right of `PageHeader` actions? Inline with the search bar? Separate row? Three options ranked by discoverability.

### Q4 — Live-session affordance

When a ticket has a live session (currently active), where does the indicator go on the card? A green dot is the obvious answer but feels noisy if every Active ticket has one. Variants for "discreet" vs "loud".

### Q5 — Empty-column placeholder

In Direction A's terminal voice, what does an empty `review · 0` column look like? Plain empty space feels cold. A subtle hint (e.g., `# no tickets in review`) might work but risks looking like comments-as-content.

### Q6 — Cross-provider mixing aesthetic

A `done` column might show a mix of Linear-Done (green-blue), Jira-Done (typically green), GitHub-Closed/Merged (purple/red). The provider badge already encodes color; the card border-left is the canonical status color. Variants for "do they fight or harmonize?"

### Q7 — Density mode

For users with 50+ tickets in a single column, do we collapse to a more compact one-line view, paginate, or virtualize? The existing table handles density trivially; the board does not.

## 9. Out-of-scope follow-ups (mention if you see opportunities, don't design)

- Same kanban applied to `ProjectTicketsTab` — likely future iteration
- Per-column sort (currently fixed: `last_linked_at` desc) — let users pick? probably yes, post-v1
- Saved board views / filters — out of scope
- Drag to multi-select for bulk operations (unlink, copy URLs) — out of scope

## 10. Implementation notes (for the agent, not Claude Design)

When implementation lands:

```ts
// 1. URL state in +page.svelte (Svelte 5 runes)
let view = $derived(($page.url.searchParams.get('view') as 'board' | 'table') ?? 'table');
function setView(v: 'board' | 'table') {
  const sp = new URLSearchParams($page.url.searchParams);
  if (v === 'table') sp.delete('view'); else sp.set('view', v);
  goto(`/tickets?${sp.toString()}`);
}

// 2. Group tickets client-side from data.tickets
const COLUMN_ORDER = ['todo','active','review','done','closed'] as const;
let grouped = $derived.by(() => {
  const map: Record<StatusKey, TicketListItem[]> = {
    todo:[], active:[], review:[], done:[], closed:[], unknown:[]
  };
  for (const t of data.tickets) {
    const k = normalizeStatus(t.status).key;
    map[k].push(t);
  }
  return map;
});
```

No backend changes. No new endpoints. No new fields on the API response.

## 11. References / inspiration

- Linear's "Board" view (`linear.app/.../board`) — the cleanest read-write kanban
- Height.app's "List" view — group-by-status without true kanban affordance
- GitHub Projects (the new beta) — read-mostly status board with high information density
- The existing karma `/tickets` page — the design we're extending, not replacing

---

**Send me back:** 2–3 rendered variants for each of Q1–Q7, with Tailwind classes I can lift. Lead with Direction A. If Direction B or C is clearly better for any specific question, say so and show.
