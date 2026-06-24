# Claude Karma Design System — Design Spec

**Date:** 2026-06-23
**Status:** Approved (design) — pending implementation plan
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

Move the `:root` / `[data-theme='dark']` / `@media (prefers-color-scheme: dark)`
token blocks out of `app.css` into a standalone file that both sides import:

```
frontend/src/styles/tokens.css   ← all token declarations live here
frontend/src/app.css             ← `@import './styles/tokens.css';` + component/utility CSS
```

This is a pure extraction — no visual change to the app. It is the linchpin of
"map it in reality": tokens live in exactly one place, and the catalog reads from it.

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

### 5.3 Foundation cards (generated)

`generate-foundations.mjs` reads `tokens.css`, groups custom properties by prefix, and
emits one HTML card per group with the required first-line marker, e.g.
`<!-- @dsCard group="Colors" -->`. Groups map to existing token families:

- **Colors** → core (bg/text/border/accent), Semantic (success/error/warning/info),
  Domain (event / model / subagent / provider / status / nav / scope) — rendered as
  labeled swatches in both light and dark via a `data-theme` toggle.
- **Typography** (Inter / JetBrains Mono + a representative type scale), **Spacing**
  (`--spacing-1..12`), **Radius** (`--radius-xs..lg`), **Shadow**
  (`--shadow-sm..elevated`), **Motion** (`--duration-*` / `--ease`), **Focus** (live
  focus-ring demo), **Brand** (accent + `gradient-text`).

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
