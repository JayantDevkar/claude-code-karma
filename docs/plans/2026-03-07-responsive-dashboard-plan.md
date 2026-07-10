# Responsive Dashboard Plan

**Date:** 2026-03-07
**Goal:** Make the entire Claude Code Karma dashboard fully responsive across all screen sizes (375px mobile to 2560px+ ultrawide).

## Current State

The list/index pages are mostly well-done (8.5/10) — they use proper Tailwind responsive prefixes (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`, `flex-col sm:flex-row`, etc.). The main problems are:

1. **Root layout container** caps content at 1200px with fixed padding
2. **Several detail pages** have hardcoded grids/sidebars that break on mobile
3. **CSS-only components** (LiveSessions, CommandFooter) have zero responsive classes
4. **No xl:/2xl: breakpoints** anywhere — large screens (1440px+) are ignored

## Breakpoint Strategy

| Prefix | Width | Target |
|--------|-------|--------|
| (none) | 0–639px | Mobile phones (375px–430px) |
| `sm:` | 640px+ | Large phones / small tablets |
| `md:` | 768px+ | Tablets |
| `lg:` | 1024px+ | Laptops |
| `xl:` | 1280px+ | Desktops |
| `2xl:` | 1536px+ | Large monitors / ultrawide |

## Phases

---

### Phase 1: Root Layout Shell (CRITICAL)

**Files:** `+layout.svelte`, `Header.svelte`, `CommandFooter.svelte`

#### 1.1 Main container (`+layout.svelte:123`)
```
Current:  class="flex-1 w-full max-w-[1200px] mx-auto px-6 py-8"
Target:   class="flex-1 w-full max-w-[1200px] xl:max-w-[1400px] 2xl:max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 py-6 sm:py-8"
```

- Mobile (375px): 375 - 32px = 343px content (was 327px with px-6)
- Desktop (1200px): same as before
- Large (1440px): expands to 1400px (was capped at 1200px)
- Ultrawide (1920px+): expands to 1600px

#### 1.2 Header container (`Header.svelte:57`)
```
Current:  class="w-full max-w-[1200px] mx-auto px-4 md:px-6 ..."
Target:   class="w-full max-w-[1200px] xl:max-w-[1400px] 2xl:max-w-[1600px] mx-auto px-4 md:px-6 lg:px-8 xl:px-10 ..."
```
Must match the main container max-width at each breakpoint.

#### 1.3 CommandFooter (`CommandFooter.svelte`)
- Replace CSS `@media (min-width: 640px)` with Tailwind `hidden sm:inline` on label spans
- Add responsive padding: `px-4 sm:px-6 lg:px-8`
- Ensure buttons don't overlap on 375px — use `flex-wrap gap-2`

**Estimated changes:** 3 files, ~15 lines each

---

### Phase 2: Detail Pages (HIGH PRIORITY)

#### 2.1 About page (`about/+page.svelte`) — CRITICAL
- **Line 46-47:** Fixed 224px sidebar doesn't collapse on mobile
- Fix: `flex flex-col lg:flex-row gap-6` with sidebar `w-full lg:w-56 lg:shrink-0`
- Sidebar becomes horizontal nav or collapsible on mobile
- Add sticky behavior only on desktop: `lg:sticky lg:top-20`

#### 2.2 Agent detail (`agents/[name]/+page.svelte`) — HIGH
- **~Line 800:** `grid grid-cols-3` → `grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3`
- **~Line 1100:** Add `xl:grid-cols-3` for large screens
- **~Line 1300:** `grid grid-cols-2` → `grid grid-cols-1 sm:grid-cols-2`

#### 2.3 Settings (`settings/+page.svelte`) — MEDIUM
- **Line 1:** `max-w-2xl` → `max-w-2xl lg:max-w-3xl xl:max-w-4xl`
- **Line 217:** `grid grid-cols-2` → `grid grid-cols-1 sm:grid-cols-2`

#### 2.4 Team page (`team/+page.svelte`) — MEDIUM
- **Line 64:** `max-w-5xl` → `max-w-5xl xl:max-w-6xl 2xl:max-w-7xl`
- **Line 79:** Add `xl:grid-cols-4` for large screens

#### 2.5 Sync page (`sync/+page.svelte`) — MEDIUM
- **Line 1:** `max-w-4xl` → `max-w-4xl xl:max-w-5xl 2xl:max-w-6xl`
- Header flex: add `flex-col sm:flex-row` for mobile stacking

**Estimated changes:** 5 files, ~5-20 lines each

---

### Phase 3: List Pages (QUICK WINS)

#### 3.1 Home page (`+page.svelte:23`)
- `max-w-[560px]` → `max-w-[560px] sm:max-w-xl md:max-w-2xl lg:max-w-3xl`
- The home page nav grid already uses responsive prefixes — just widen the container

#### 3.2 Analytics page (`analytics/+page.svelte:234`)
- `max-w-[1100px]` → remove (inherits from layout container which is now responsive)
- Or: `max-w-[1100px] xl:max-w-[1400px] 2xl:max-w-[1600px]`

#### 3.3 Add xl:/2xl: to grids across all list pages
For pages using `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`, add `xl:grid-cols-4` where it makes sense (cards that are narrow enough):
- `projects/+page.svelte`
- `agents/+page.svelte`
- `skills/+page.svelte`
- `hooks/+page.svelte`
- `plugins/+page.svelte`
- `commands/+page.svelte`
- `plans/+page.svelte`
- `tools/+page.svelte` (already has `xl:grid-cols-4`)

**Estimated changes:** ~10 files, ~1-3 lines each

---

### Phase 4: CSS-Only Components (MEDIUM PRIORITY)

These components use raw CSS with hardcoded pixel values and zero Tailwind responsive classes. They won't break on mobile but don't adapt well.

#### 4.1 LiveSessionsSection.svelte
- Convert hardcoded padding (`12px 16px`) to Tailwind responsive classes
- `.project max-width: 70%` → responsive with truncation
- Add responsive gap scaling

#### 4.2 LiveSessionsTerminal.svelte
- `.terminal-body max-height: 195px` → responsive height
- Convert padding from fixed CSS to Tailwind responsive classes
- `.project max-width: 70%` → responsive

#### 4.3 SessionChainView.svelte
- `min-width: 200px; max-width: 280px` → responsive card sizing
- Already has a `@media (max-width: 640px)` query — extend to `lg:` breakpoints
- Cards should expand on large screens

#### 4.4 TokenSearchInput.svelte
- Touch target: `.clear-all-btn` is 24x24px → needs 44px on mobile
- Already has `@media` queries — consolidate with Tailwind responsive classes
- `max-width: 200px` on tokens → responsive

**Estimated changes:** 4 files, 10-30 lines each

---

### Phase 5: ConversationView Component (INVESTIGATE)

The session detail pages (`projects/[project_slug]/[session_slug]/+page.svelte`) delegate to a `ConversationView` component which is a 70KB+ file. This needs a separate audit to identify:
- Timeline layout responsiveness
- Metadata sidebar stacking on mobile
- Message bubble width constraints

**Action:** Audit and plan separately — this may be the largest single component.

---

## Implementation Order

1. **Phase 1** (layout shell) — do first, affects every page
2. **Phase 3** (list pages) — quick wins, 1-3 line changes each
3. **Phase 2** (detail pages) — medium effort, high impact
4. **Phase 4** (CSS components) — refactor CSS to Tailwind responsive
5. **Phase 5** (ConversationView) — biggest effort, separate audit needed

## Testing Checklist

For each phase, verify at these widths:
- [ ] 375px (iPhone SE / small Android)
- [ ] 430px (iPhone Pro Max)
- [ ] 768px (iPad portrait)
- [ ] 1024px (iPad landscape / small laptop)
- [ ] 1280px (standard laptop)
- [ ] 1440px (desktop monitor)
- [ ] 1920px (full HD)
- [ ] 2560px (ultrawide / 2K)

## Risk Assessment

- **Low risk:** Phases 1-3 are additive Tailwind class changes — no breaking changes
- **Medium risk:** Phase 4 converts CSS to Tailwind — visual regression possible
- **High risk:** Phase 5 (ConversationView) is a massive component — needs careful handling
