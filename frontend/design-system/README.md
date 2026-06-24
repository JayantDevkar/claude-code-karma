# Claude Karma Design-System Catalog

A token-derived, framework-free HTML catalog of every primitive in the app. It maps each preview card back to the real Svelte source it documents, so the catalog stays honest — it shows what the app actually renders, not aspirational mocks.

## Commands

```bash
# Build: generate foundations + validate all 23 cards
cd frontend && npm run ds:build

# Drift check: verify cards are newer than their mapped sources
cd frontend && npm run ds:drift
```

`ds:build` copies `tokens.css` into the bundle, generates `foundations/*.html`, validates every `@dsCard` marker, enforces the mapping.json contract, then writes `.render-check.json`. It outputs `catalog OK — 23 cards validated` on success with `{total, bad, thin}` counters. `thin` = cards whose body has fewer than 200 non-whitespace characters (a real signal). `bad` = cards with missing or malformed `@dsCard` markers.

`ds:drift` prints `no drift — all cards are current with their sources` when every card's mtime ≥ all its mapped source files. Drift is flagged when a source file's mtime exceeds its card's mtime — the card is stale and must be rebuilt. If it reports stale cards, re-run `ds:build` or touch the affected `.html` file after updating the source.

## What's committed vs. generated

| Path | Status |
|------|--------|
| `catalog/components/*.html` | committed — hand-authored preview cards |
| `catalog/mapping.json` | committed — source-of-truth for card↔Svelte mapping |
| `catalog/shared/preview.css` | committed — shared preview chrome (no app CSS) |
| `scripts/*.mjs` | committed — build, drift, and test scripts |
| `catalog/shared/tokens.css` | **generated** (gitignored) — copied from `src/styles/tokens.css` |
| `catalog/foundations/*.html` | **generated** (gitignored) — rendered by `generate-foundations.mjs` |
| `catalog/.render-check.json` | **generated** (gitignored) — validation manifest written by `ds:build` |

Run `ds:build` after any change before expecting foundations or the render manifest to be current.

## mapping.json round-trip contract

Every card must appear in `catalog/mapping.json` with at least one source path:

```json
"components/badge.html": ["src/lib/components/ui/Badge.svelte"]
```

`ds:build` enforces the contract bidirectionally: a card not listed in `mapping.json`, or a mapping entry pointing to a non-existent card, both cause a hard failure. `ds:drift` uses the same map to compare mtimes.

Foundation cards (`foundations/*.html`) are generated automatically; their mapping entries point to `src/styles/tokens.css`.

## Adding a new primitive card

1. Create `catalog/components/<name>.html`. The **first line must be** the marker comment:

   ```html
   <!-- @dsCard group="Components" -->
   ```

   Then a full standalone HTML document that links the shared CSS:

   ```html
   <!doctype html>
   <html lang="en" data-theme="light">
   <head>
     <meta charset="utf-8">
     <link rel="stylesheet" href="../shared/tokens.css">
     <link rel="stylesheet" href="../shared/preview.css">
   </head>
   <body>
     <!-- preview markup here -->
   </body>
   </html>
   ```

2. Add an entry to `catalog/mapping.json`:

   ```json
   "components/<name>.html": ["src/lib/components/ui/YourComponent.svelte"]
   ```

3. Run `cd frontend && npm run ds:build` to validate. The total count in the success message will increment by 1.

## Pages layer

The `catalog/pages/` directory mirrors whole application routes (not individual components). Each card is a full-page snapshot using the real design tokens, with realistic sample data, so it serves as the before-picture for redesign work.

| Card | Route | Key sources |
|------|-------|-------------|
| `pages/cron.html` | `/cron` | `+page.svelte`, `SystemCrontabSection.svelte`, `PageHeader.svelte`, `StatsGrid.svelte` |
| `pages/shells.html` | `/shells` | `+page.svelte`, `PageHeader.svelte`, `StatsGrid.svelte` |

Cards are annotated `<!-- @dsCard group="Pages" -->` and wired into `mapping.json` like any other card. Run `ds:build` after modifying a page card.

## Sync to claude.ai/design

The `catalog/` directory is the `localDir` used by the DesignSync step (Task 8). Sync is plan-gated and incremental — it pushes only changed cards to the remote design system and requires a one-time `claude.ai` authentication flow.

The sync step is intentionally separate from `ds:build`; running `ds:build` locally never touches the remote. See the task-8 brief for the auth + sync command sequence.

**Synced project:** `Claude Karma Design System` — projectId `5fdd2fba-3802-4151-98ba-586d685cebf5` (initial sync 2026-06-23, 24 files: 21 cards + `shared/{tokens,preview}.css` + `mapping.json`). For incremental re-syncs, run `npm run ds:build`, then `DesignSync` `list_files` → `finalize_plan` (writes: `foundations/*.html`, `components/*.html`, `shared/*.css`, `mapping.json`; `localDir` = this `catalog/`) → `write_files`.
