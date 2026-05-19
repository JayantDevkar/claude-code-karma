# Design Brief — Navigation Header Redesign

**Date:** 2026-05-19
**Audience:** Claude Design (`claude.ai/design`)
**Source repo:** [JayantDevkar/claude-code-karma](https://github.com/JayantDevkar/claude-code-karma)
**Branch context:** `feat/session-ticket-linking` — this brief is independent of that branch but reflects the current header state.

---

## How to use this brief

Paste this whole document into a fresh `claude.ai/design` conversation. It is self-contained. Return 2–3 rendered variants per numbered question in §7, with rationale, Tailwind classes I can lift directly, and dark-mode parity.

---

## 1. Problem in one sentence

The top navigation has grown from 7 → 12 link items as features shipped, and at typical viewport widths it now reads as a wall of densely-packed labels with no visual rhythm or grouping — the user has to *scan a sentence* to find a section.

## 2. Current state (the data behind the screenshot)

12 nav links in order, plus a Settings cog on the right:

`Projects · Sessions · Tickets · Plans · Agents · Skills · Commands · Tools · Hooks · Plugins · Analytics · Archived`

All items are visually identical: same font weight, same color, same spacing. The only differentiation is the active-route highlighting (the current page gets `text-[var(--text-primary)]`; everything else is `text-[var(--text-muted)]`).

At 1440px viewport, the row spans roughly **800px** of horizontal real estate between the logo and the settings cog — it dominates the page and pushes content below. At narrower viewports (~1100px) the items start to wrap or overflow.

This is the home/dashboard route screenshot the user shared:

```
[logo] Claude Code Karma    Projects  Sessions  Tickets  Plans  Agents  Skills  Commands  Tools  Hooks  Plugins  Analytics  Archived    [⚙]
```

## 3. Goals

- **Visual rhythm** — group related items so the eye lands instead of scans
- **Lower visual weight** — the nav should not feel like the protagonist of every page
- **Scale forward** — the next 3–5 items we ship shouldn't break the layout
- **Discoverability** — power users need fast access; new users need to know what's available
- **Keyboard navigability** — there's already a command palette (`⌘K`); the new nav must complement it, not duplicate it

## 4. Constraints (must honor)

- **Framework:** SvelteKit 2 + Svelte 5 runes; Tailwind 4
- **No new dependencies** — `bits-ui`, `lucide-svelte`, `date-fns` are already in. Adding to `package.json` is a no.
- **Existing tokens** in `frontend/src/app.css`:
  - `--bg-base / --bg-subtle / --bg-muted`
  - `--text-primary / --text-secondary / --text-muted / --text-faint`
  - `--border / --border-subtle / --border-hover`
  - `--accent` (violet `#7c3aed` light, `#a78bfa` dark)
  - `--shadow-sm / --shadow-md / --shadow-lg`
  - `--nav-{blue,green,orange,purple,gray,red,yellow,teal,violet,indigo,amber}` and `-subtle` companions (each section has a "brand color" used on the homepage navigation cards — already shipped, see [`frontend/src/lib/components/NavigationCard.svelte`](https://github.com/JayantDevkar/claude-code-karma/blob/feat/session-ticket-linking/frontend/src/lib/components/NavigationCard.svelte))
- **WCAG 2.1 AA** contrast required; visible focus rings; keyboard nav must work
- **Mobile**: there is already a mobile hamburger drawer below `md` breakpoint — your redesign needs a paired mobile treatment
- **Active-state**: the current implementation uses `aria-current="page"` plus a color change. Whatever you propose should preserve that semantic

## 5. The 12 items, semantically grouped (my reading — feel free to challenge)

| Group | Items | What they do |
|---|---|---|
| **Work** | Projects · Sessions · Tickets · Plans | The actual things the user is tracking. Tickets is the newest. |
| **Knowledge** | Agents · Skills · Commands | The reusable assets that get invoked inside sessions. |
| **Infra** | Tools · Hooks · Plugins | Plumbing — MCP servers, hook scripts, plugins. Power-user surfaces. |
| **Meta** | Analytics · Archived | Historical / cross-cutting views. Low traffic. |

If you accept this grouping (4 groups of 3, with one outlier "Tickets" added recently), the design becomes a question of *how to express groups visually* rather than "shrink everything."

## 6. Current code reference

The header lives at:
[`frontend/src/lib/components/Header.svelte`](https://github.com/JayantDevkar/claude-code-karma/blob/feat/session-ticket-linking/frontend/src/lib/components/Header.svelte)

Worth reading both the desktop nav (lines ~77–169) and the mobile drawer (lines ~203+) — your design needs both.

## 7. Open questions — what we want design's opinion on

Return 2–3 variants per question. For at least one variant per question, show the dark-mode treatment too.

### 7.1 — Overall structural approach

Which of these directions does the right thing for this app? Or propose a 4th.

- **A. Group with dividers.** Same 12 items, but visually clustered with thin `var(--border-subtle)` separators between the four groups. No interaction change.
- **B. Primary nav + overflow menu.** Show 4–6 "primary" items (Projects, Sessions, Tickets, Analytics, maybe Plans). Move the rest behind a "More ▾" dropdown.
- **C. Icon-first compact nav.** Replace text labels with icons (each item already has a homepage `NavigationCard` icon — Bot, Wrench, Webhook, Puzzle, etc.). Tooltips on hover. Active item shows its label. Roughly halves the horizontal footprint.
- **D. Sidebar.** Move nav into a collapsible left rail. Tradeoff: gives up horizontal space, gains vertical breathing room and group-headers.

### 7.2 — Active-state treatment

Today: the active route is `text-[var(--text-primary)]` while inactive is `text-[var(--text-muted)]`. That's a *very* subtle differentiator — easy to miss. Should the active state be louder (underline / pill background / accent bar)? Show 2 variants.

### 7.3 — Group differentiation

If we go with §7.1 A (or a variant), how do groups visually separate? Options:
- Thin vertical dividers
- A small gap between groups (whitespace alone)
- Tiny group labels above each cluster (`WORK` `KNOWLEDGE` `INFRA` `META`) in `text-faint` 9px caps
- Color-tinting within groups (Work uses `--nav-blue`-family tones, etc.)

### 7.4 — The command palette relationship

There's already a `⌘K` palette (see the footer bar: "Command Menu ⌘ K"). For power users, the nav doesn't need to surface every section — they'll palette. For first-time users, the nav IS the discovery surface. Design needs to decide: is the new nav optimized for discovery or for power-user speed? Or both via different affordances?

### 7.5 — Where does Settings go?

Currently the cog sits on the right, separated from the nav. Should it stay? Move into the nav as one of the items? Get a stronger separation (vertical divider before it)?

### 7.6 — Mobile

The current mobile drawer (lines ~203+ of `Header.svelte`) is a vertical stack of the same 12 items. Should the mobile drawer:
- Mirror the desktop grouping exactly?
- Use a different organization (e.g., search-first, recent-sections-first)?
- Compress into icon grid?

### 7.7 — Brand color expression

Each section already has a brand color shipped on the homepage's `NavigationCard` (Projects=blue, Sessions=teal, Tickets=amber, etc.). Should that color show up in the nav header at all? Where? On the icon background, the underline, the active-state, nothing?

## 8. Non-goals (don't redesign these)

- The logo on the left — stays
- The `⌘K` command palette — stays as-is
- The routes themselves — `/projects` `/sessions` etc. don't change
- The page-level `<PageHeader>` (just shipped, has icon-on-left + breadcrumb + subtitle) — that's a separate surface
- The homepage `NavigationCard` grid — that surface has its own treatment and is fine

## 9. What I want back from this design pass

For each question in §7:

1. **2–3 rendered variants** (HTML in Artifacts is fine; React if you prefer)
2. **One-paragraph rationale per variant** — what it optimizes for, what it trades
3. **Tailwind class strings** I can lift directly into `Header.svelte`
4. **Tokens used** explicitly named from §4 list
5. **Dark-mode parity** — at least one variant per question rendered in dark

For §7.1 (the big one), please also produce a **system spec page** showing the chosen direction on three viewports (mobile drawer, ~1024px tablet, 1440px desktop) so I can see how it scales together.

## 10. What I'll return to you after implementing

Per the workflow established for the ticket-linking feature:

- Branch URL with the changes
- Live screenshots: home, /projects, /sessions, /tickets — to verify the active-state and group-visibility on different routes
- Any place reality diverged from the mock and why
- Then a critique-and-polish round before merge

## 11. Decision log

Decisions land in `docs/design-briefs/2026-05-19-nav-header-redesign-log.md` (paired companion). Each iteration appends one section with date, what was decided, and rationale.
