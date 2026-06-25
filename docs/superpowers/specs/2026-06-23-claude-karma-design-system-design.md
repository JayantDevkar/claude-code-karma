# Claude Karma Design System — Design Spec

**Date:** 2026-06-23
**Status:** Approved (design); feature-dev review incorporated — pending implementation plan
**Branch:** `feat/design-system`

## 1. Goal

Build a design system for Claude Karma that (a) reflects the real code ("map it in
reality") and (b) is mirrored into **claude.ai/design** so UI/UX changes can be
iterated visually and ported back to code. Decision: build an **in-repo catalog as
the source of truth, then sync it to a Claude Design project**.

## 2. Background: what "Claude design" is and expects

"Claude design" = **claude.ai/design**, Anthropic's hosted Design System feature,
accessed in this environment through the `DesignSync` tool and its companion
`/design-sync` skill (which keeps a local component library in sync with a Claude
Design project, incrementally, one component at a time — never a wholesale replace).

Conventions Claude Design expects of a design system:

1. **A dedicated design-system project** — type `PROJECT_TYPE_DESIGN_SYSTEM`, set at
   creation and immutable.
2. **Components as self-contained preview HTML files** — one file per component or
   variant set. Claude Design renders HTML; it does not execute Svelte.
3. **Card markers** — each preview's first line carries
   `<!-- @dsCard group="…" -->`. These compile into a `_ds_manifest.json` that powers
   the card index in the Design System pane.
4. **Grouping** into foundational sections — canonical labels are **Type, Colors,
   Spacing, Components, Brand** (or domain categories).
5. **A render-check quality bar** (`.render-check.json` with counts for
   `total / bad / thin / variantsIdentical`): every card must render, not be too
   sparse ("thin"), and variants must be genuinely different.
6. **Plan-gated, incremental sync** — flow is always
   `list/read → finalize_plan → write/delete`.

## 3. Current state of Claude Karma (frontend)

- **Strong token layer** — `frontend/src/app.css` (~980 lines): typography
  (Inter / JetBrains Mono), full light + dark + system color modes, deep domain
  palette (event types, model families, subagent types, ticket providers, statuses,
  nav cards, scopes), a 4px spacing grid, radius/shadow/motion tokens, a focus-ring
  system, a skeleton system.
- **150 Svelte components** across ~28 feature folders; **13 distinct `ui/`
  primitives** (the `Tabs*` files are one family): Badge, Card, CollapsibleGroup,
  EmptyState, KeyIndicator, Modal, SegmentedControl, SelectDropdown, Switch, Tabs,
  TextInput, ThemeToggle, TierBadge.
- Tooling: Tailwind CSS 4 (CSS-based `@theme`, no `tailwind.config`), Vite, Node,
  vitest. No `tailwind.config.*`.

**Gap:** tokens and components exist only as code. No canonical catalog, no visual
inventory, no Claude Design mirror, no mapping that lets a design change round-trip.

## 4. Decisions

| Decision | Choice |
| --- | --- |
| Primary outcome | Both: in-repo catalog → synced to Claude Design |
| First-iteration scope | Foundations + the 13 `ui/` primitives |
| Build/maintenance approach | **B** — generated foundations + hand-authored primitive previews + mapping manifest |

Approach C (render real Svelte → static HTML) is deferred; the layout leaves room to
graduate the `components/` layer to it later without redoing foundations.

## 5. Architecture

### 5.1 Single source of truth: extract `tokens.css`

Move the three token blocks out of `app.css` — verified line ranges:
`:root {}` (lines 12–211), `:root[data-theme='dark'] {}` (264–403), and
`@media (prefers-color-scheme: dark) { :root:not([data-theme='light']) {} }`
(406–539) — into a standalone file both sides import:

```
frontend/src/styles/tokens.css   ← the 3 token blocks, copied VERBATIM
frontend/src/app.css             ← keeps everything else; @imports tokens.css
```

**What stays in `app.css`** (do NOT move): `@import 'tailwindcss'` (line 1), the
`@theme {}` block (lines 3–6 — it registers `--font-sans` / `--font-mono` as Tailwind
utilities), and all non-token CSS (`body`, `.markdown-preview` `@apply` blocks, focus
selectors, skeleton, `.gradient-text` and other utilities).

**Import order matters** (Tailwind 4 inserts its cascade at its `@import`):

```css
@import 'tailwindcss';
@theme { --font-sans: …; --font-mono: …; }
@import './styles/tokens.css';
/* …remaining non-token CSS… */
```

This is a pure, verbatim extraction — no visual change to the app. Verify with
`npm run check` + a light/dark browser pass before continuing. It is the linchpin of
"map it in reality": tokens live in exactly one place, and the catalog reads from it.

> **Known token inconsistencies (preserve verbatim, do NOT fix here):** the two dark
> blocks diverge — `--*-rgb` and `--nav-amber/--nav-cyan` exist in `[data-theme='dark']`
> but not the media block; `--subagent-*` exists in the media block but not
> `[data-theme='dark']`. Copy as-is to avoid regressions; tracked as a future cleanup
> (§9), not part of this work.

### 5.2 Catalog layout (the synced bundle)

```
frontend/design-system/
  catalog/                    ← directory synced to claude.ai/design (DesignSync localDir)
    shared/
      tokens.css              ← copied from src/styles/tokens.css at build time
      preview.css             ← reset + card frame + theme-toggle styling
    foundations/              ← GENERATED: color.html, typography.html, spacing.html,
                                 radius.html, shadow.html, motion.html, focus.html, brand.html
    components/               ← AUTHORED: badge.html, card.html, tabs.html, … (13 files)
    mapping.json              ← card path → Svelte source file(s)
  scripts/
    generate-foundations.mjs  ← parses tokens.css → emits foundations/*.html
    build-catalog.mjs         ← copy tokens, run generator, validate every card has @dsCard
```

`npm run ds:build` runs `build-catalog.mjs`. Every preview `<link>`s to
`shared/tokens.css`, so the bundle renders identically in the dev server and in the
Claude Design pane. `shared/tokens.css` is copied from the live `src/styles/tokens.css`
on every build, so the synced cards always reflect current code.

**Git strategy (resolves the two reviews' conflict):** commit the *authored* sources —
`components/*.html`, `mapping.json`, `shared/preview.css`, and the three `scripts/*.mjs`.
**Gitignore the pure-derived artifacts** — `catalog/shared/tokens.css` (a 1:1 copy of
the canonical token file; committing it would reintroduce drift), `catalog/foundations/`
(generated), and `catalog/.render-check.json`. `ds:build` regenerates all of these
deterministically and the sync workflow always runs it first, so the on-disk bundle is
complete at upload time. Each preview HTML sets `<html data-theme="light">` as its
default so a system-dark OS doesn't bleed into previews (the `prefers-color-scheme`
block keys off `:root:not([data-theme='light'])`); a per-preview toggle button flips it.

### 5.3 Foundation cards (generated)

`generate-foundations.mjs` reads `tokens.css` with a **pure-Node, zero-dependency
line-by-line state-machine parser** (not regex — the blocks span 200 lines; a state
machine over `{`/`}` depth is robust to comments). It builds a `Map<name,{light,dark}>`,
groups by prefix, and emits one HTML card per group with the required first-line marker,
e.g. `<!-- @dsCard group="Colors" -->`.

Use **descriptive `group` labels** (the field is free-form; the pane groups by whatever
you send — the canonical Type/Colors/Spacing/Components/Brand set is just a baseline):
`Colors`, `Type`, `Spacing`, `Radius`, `Shadow`, `Motion`, `Focus`, `Brand`.

Cards (~147 tokens total across these families):

- **Colors** → Core (bg/text/border/accent ~17), Semantic (success/error/warning/info
  ×2 = 8), Domain (event 18 / model 6 / subagent 10 / provider 9 / ticket-status 5 /
  scope 4), Navigation (`--nav-*` ×24), Live-Status tints (`--status-*-bg` ×7) —
  labeled swatches in light + dark via the toggle.
- **Type** (Inter / JetBrains Mono + a representative scale), **Spacing** (the **8**
  tokens: 1,2,3,4,5,6,8,12 — not 12 consecutive), **Radius** (`--radius-xs..lg`),
  **Shadow** (`--shadow-sm..elevated`), **Motion** (`--duration-*` + `--ease`),
  **Focus** (live focus-ring demo), **Brand** (accent + `gradient-text`).

**Generator exceptions** (from review): skip `--plugin-*` swatches — they're OKLCH
params consumed by JS (`memoryTypeBadge.ts`), so render a "computed at runtime" callout
instead. Render `--data-*` as *aliases* (e.g. `--data-primary → var(--accent)`), not
standalone swatches. `--radius-xs` / `--duration-normal` were retroactively added and
have no dark override — that's expected.

Because foundations are generated from the live token file each build, a new or
changed token automatically shows up correctly — the foundation layer cannot drift.

### 5.4 Primitive previews + mapping manifest

Each of the 13 primitives gets one hand-authored HTML preview under
`catalog/components/`, built against the shared tokens, showing all meaningful
variants (to clear the render-check's "thin" / "variantsIdentical" bar). Each starts
with `<!-- @dsCard group="Components" -->`.

`mapping.json` is the "map it in reality" contract — every card names the exact Svelte
file(s) it represents:

```json
{
  "components/badge.html": ["src/lib/components/ui/Badge.svelte"],
  "components/tabs.html":  ["src/lib/components/ui/Tabs.svelte",
                            "src/lib/components/ui/TabsList.svelte",
                            "src/lib/components/ui/TabsTrigger.svelte",
                            "src/lib/components/ui/TabsContent.svelte"]
}
```

Each preview is authored by reading the primitive's actual props/variants from its
`.svelte` source, so the HTML reflects what the component renders today.

**Per-primitive authoring notes (from the codebase review):**

- **`bits-ui`-backed components** — `Modal` (Dialog), `Switch`, `Tabs`/`TabsList`/
  `TabsTrigger`/`TabsContent` — cannot use `bits-ui` in static HTML. Replicate the
  rendered DOM and **hardcode the state attributes** the library sets at runtime:
  `data-state="active|inactive"` on tab triggers, `data-state="checked|unchecked"` (or
  `aria-checked`) on the switch, `role="dialog"` for the modal. `Modal` also has a local
  `<style>` with `@keyframes` — inline those.
- **`TierBadge` is the one primitive that bypasses tokens** — its colors come from
  hardcoded hex/rgba in `tierConfigs` (`src/lib/utils.ts` ~1210–1233), and it renders
  **nothing** for `tier='low'`. Inline those exact values in the preview (read utils.ts
  first); show very-high / high / medium and note low is intentionally empty.
- **`EmptyState`** uses an internal `KarmaIcon` — substitute an inline SVG stand-in.
- **`CollapsibleGroup`** uses a Svelte `slide` transition + a free-form `accentColor`
  string — show open + closed states statically with a hardcoded accent value.
- **`Switch`** references Tailwind `ring-*` vars (not the app's `--focus-ring-*`); use
  `var(--accent)` for the ring in the preview.
- **`Badge`** matrix = 10 variants × 2 sizes × 2 radii — render enough to clear "thin".

Foundation `mapping.json` entries point at `src/styles/tokens.css` as their source.

### 5.5 Claude Design sync (`/design-sync` + `DesignSync`)

1. **First time:** `list_projects` (prompts once to grant design-system access to the
   claude.ai login; `/design-login` is the alternative), then `create_project` →
   `PROJECT_TYPE_DESIGN_SYSTEM` named "Claude Karma Design System."
2. **Each sync:** `npm run ds:build` → `list_files` (remote) to diff against
   `catalog/` → `finalize_plan` (locks exact write/delete paths + `localDir = catalog/`)
   → `write_files` (reads from disk; contents never enter the model context).
3. Claude Design compiles `@dsCard` markers into its card index, runs the
   render-check, and shows cards grouped in the Design System pane.
4. **Incremental forever after** — one component at a time; change Badge → only
   `badge.html` re-syncs.

### 5.6 Round-trip workflow

**Code → Design:** `npm run ds:build` regenerates foundations from live tokens and
rebuilds the bundle → sync. Foundations are automatically true; for primitives,
`ds:drift` flags any `mapping.json` entry whose Svelte source changed more recently
than its preview, so you know which card to refresh.

**Design → Code:** a visually-iterated change (incl. via `frontend-design` /
`impeccable` skills) lands in the preview HTML / tokens first; `mapping.json` names the
Svelte file(s) to port it into. Token-level changes often need only a `tokens.css`
edit — and because the app imports the same file, the app updates with zero component
edits.

### 5.7 Build hygiene & tooling integration (from review)

- **`.prettierignore` — critical.** Prettier would reformat `catalog/*.html` and can push
  the `<!-- @dsCard -->` comment off line 1, breaking the render-check. Add
  `design-system/catalog/**` to `frontend/.prettierignore`. The validator in
  `build-catalog.mjs` also asserts the marker is the literal first line (no BOM, no blank
  line) and exits non-zero listing offenders.
- **`frontend/.gitignore`** — add `design-system/catalog/shared/tokens.css`,
  `design-system/catalog/foundations/`, `design-system/catalog/.render-check.json`.
- **ESLint** — `frontend/eslint.config.js` lints `.mjs` under the base JS config; add the
  three `design-system/scripts/*.mjs` to its `ignores` (or keep them lint-clean).
- **No `vite.config.ts` / `svelte.config.js` changes** — the catalog is framework-free
  static HTML run by `node`; it is not processed by Vite or SvelteKit.
- Package is already `"type": "module"`, so `.mjs` runs directly via `node`.

## 6. Scope guardrails (YAGNI)

- v1 = foundations + 13 `ui/` primitives only. Domain components (timeline, charts,
  conversation, ticket/status, nav cards) are **out** of the first iteration.
- No render harness (Approach C) yet; layout allows graduating `components/` later.
- `ds:drift` is a lightweight mtime/git check, not a visual differ.

## 7. Risks & mitigations

- **Token extraction regression** — the `:root` move could subtly change cascade
  order. Mitigation: extract verbatim, import at the top of `app.css`, verify the app
  visually + `npm run check` before proceeding.
- **Primitive preview drift** — hand-authored HTML can diverge from Svelte.
  Mitigation: `mapping.json` + `ds:drift`; graduate to Approach C if drift becomes a
  burden.
- **Auth friction** — first `DesignSync` call prompts for design-system scope.
  Mitigation: build + catalog are fully local; only the sync step needs the grant, and
  it is requested explicitly.
- **Render-check rejections** ("thin" / identical variants) — Mitigation: author
  previews with full variant matrices (all colors × sizes × states, light + dark).

## 8. Success criteria

- `tokens.css` extracted; app renders unchanged; `npm run check` passes.
- `npm run ds:build` produces a self-contained `catalog/` where every card has a valid
  `@dsCard` marker and renders in a browser (light + dark).
- A "Claude Karma Design System" project exists in claude.ai/design with foundation +
  primitive cards grouped correctly and passing the render-check.
- `mapping.json` covers all 13 primitives; `ds:drift` reports clean immediately after
  a build.
- A documented round-trip: changing one token updates both app and a foundation card;
  changing one primitive is traceable via the manifest.

## 9. Out of scope / future

- Domain component cards (timeline, charts, conversation, etc.).
- Approach C render harness.
- Automated visual regression / CI gating of the catalog.
- **Reconcile the dark-block token inconsistencies** noted in §5.1 (`--*-rgb`,
  `--subagent-*`, `--nav-amber/cyan` divergence between `[data-theme='dark']` and the
  `prefers-color-scheme` block) — a separate, isolated token-cleanup task.
- Migrate `TierBadge` onto the token system (it currently hardcodes `tierConfigs` hex).
