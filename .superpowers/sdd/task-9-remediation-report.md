# Task 9 Remediation Report

## Findings addressed

### 1. Enforce mapping.json contract in build-catalog.mjs (code-review Important)
**File:** `frontend/design-system/scripts/build-catalog.mjs`

Added bidirectional mapping.json enforcement:
- Loads `mapping.json` after `generate()` runs.
- Iterates all discovered `.html` files; any missing a mapping key is collected in `missingMappings`.
- Iterates all mapping keys; any pointing to a non-existent card file is collected in `missingFiles`.
- Both arrays cause `process.exit(1)` with offender lists printed.
- Existing marker validation retained unchanged.
- Current 21 cards all pass (8 foundation + 13 component keys all present).

### 2. colors.html generator fixes (H2, H3, M3, M4-count)
**File:** `frontend/design-system/scripts/generate-foundations.mjs`

- **(M3) Exclude shadow/focus tokens:** `buildColorSections()` pre-filter now excludes `--shadow*` and `--focus*` in addition to the prior `--font*`/`--plugin*`/`--data*` exclusions. These tokens have their own foundation cards.
- **(H2) Grouped sections:** Replaced the flat `auto-fill` grid with 10 labeled `ds-section` groups: Core, Semantic, Model, Event, Subagent, Provider, Ticket Status, Live Status, Nav, Scope. An "Other" section catches any future token not matching a family. Core's raw `*-rgb` values are rendered as a compact text note instead of chips (background: `124, 58, 237` is not a valid CSS color).
- **(H3) Chip borders:** Added `border-bottom: 1px solid var(--border)` on `.ds-swatch__chip` in `preview.css` so near-invisible low-alpha tints show their bounds. (The outer `.ds-swatch` already has a full border; the chip border provides an internal separator.)
- **(M4-count) Accurate subtitle:** Count is computed as `swatchCount` (actual chips rendered), currently 110. The stale hardcoded "115" is gone.

### 3. Honest render-check counters (UI/UX M4)
**File:** `frontend/design-system/scripts/build-catalog.mjs`

- `thin`: computed as number of cards where `body` inner content (tags stripped, whitespace removed) < 200 chars. Currently 6 (focus, brand, motion, typography, shadow, radius — all legitimately brief by design).
- `variantsIdentical`: removed entirely (was always `0`; not measured). README updated to match.
- Current output: `{ "total": 21, "bad": 0, "thin": 6 }`.

### 4. segmented-control.html fidelity fix (UI/UX M1)
**File:** `frontend/design-system/catalog/components/segmented-control.html`

Changed `.seg-btn[aria-checked="true"]` active label color from `#fff` to `var(--bg-base)`, matching the real `SegmentedControl.svelte` (`text-[var(--bg-base)]`). First-line `@dsCard` marker preserved.

### 5. Catalog chrome contrast fix (UI/UX M5)
**File:** `frontend/design-system/catalog/shared/preview.css`

- `.ds-section-label`: changed `color: var(--text-faint)` → `color: var(--text-secondary)`.
- `.ds-swatch__val`: changed `color: var(--text-muted)` → `color: var(--text-secondary)`.
Both are catalog-internal chrome only; no app token values changed.

## Verification output

```
$ cd frontend && npm run ds:build
catalog OK — 21 cards validated

$ cd frontend && node --test design-system/scripts/*.test.mjs
✔ parseTokens extracts light tokens (0.991208ms)
✔ parseTokens extracts dark overrides only from the data-theme block (0.102625ms)
✔ accepts a valid first-line marker (0.79925ms)
✔ rejects a marker not on the first line (0.12525ms)
✔ rejects a missing marker (0.066209ms)
ℹ tests 5, pass 5, fail 0

$ cd frontend && npm run ds:drift
no drift — all cards are current with their sources
```

## Scope confirmation

`git diff --name-only HEAD` shows only:
- `frontend/design-system/README.md`
- `frontend/design-system/catalog/components/segmented-control.html`
- `frontend/design-system/catalog/shared/preview.css`
- `frontend/design-system/scripts/build-catalog.mjs`
- `frontend/design-system/scripts/generate-foundations.mjs`

No changes to `frontend/src/styles/tokens.css` or any `frontend/src/lib/**` file.
