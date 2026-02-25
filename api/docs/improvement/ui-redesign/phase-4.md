# Phase 4: Time-Boxing Analytics

## Agents

| Agent Type | Purpose |
|------------|---------|
| `feature-dev:code-architect` | Design date range selection UX and state management approach |
| `feature-dev:code-explorer` | Analyze current chart components and data fetching patterns |
| `Explore` | Find date picker components in UI library, identify API query patterns |

---

## Objective

Add date range selection controls to analytics charts, enabling users to time-box data views.

---

## Current State

- Charts show fixed time windows (e.g., Sessions Over Time: 14 days)
- No date range selectors present on any page
- Stats cards show "total" (all-time) values
- No parameterized date queries in API hooks

## Target State

- Analytics sections have date range controls
- Users can select: Last 7 days, Last 14 days, Last 30 days, Custom range
- Charts and stats update based on selection
- Applies to both Project Analytics and Session Analytics

---

## Tasks

### 1. Date Range Selector Component
- Design date range picker UI
- Options: 7d, 14d, 30d, 90d, Custom
- Custom: date picker for start/end
- Consistent styling with existing UI

### 2. State Management
- Determine state location: URL params, Zustand store, or component state
- Consider: should date range persist across navigation?
- Consider: should Project and Session have independent ranges?

### 3. API Integration
- Investigate current API endpoints for date filtering support
- `/analytics/projects/{encoded_name}` - check query params
- `/sessions/{uuid}` - check if timeline data supports filtering
- Add date params to API if not present

### 4. Project Analytics Time-Boxing
- Add date selector to Project Analytics tab
- Update queries: sessions count, tokens, cost, duration by date range
- Update charts: Sessions Over Time respects selected range
- Stats cards: show "in selected period" vs "all time"

### 5. Session Analytics Time-Boxing
- Add date selector to Session Analytics tab
- Scope: within session's lifetime only
- Update charts to filter by selected range
- Consider: sessions are typically short, is this needed?

### 6. Chart Component Updates
- Modify `SessionsChart` to accept date range params
- Modify `TokenChart` if time-series view added
- Modify `ToolsChart` if time filtering applies

---

## Files to Modify/Create

| Action | Path |
|--------|------|
| Create | `apps/web/components/date-range-picker.tsx` |
| Modify | `apps/web/app/project/[encodedName]/analytics/page.tsx` |
| Modify | `apps/web/app/session/[uuid]/analytics/page.tsx` |
| Modify | `apps/web/components/token-chart.tsx` (SessionsChart) |
| Modify | `apps/web/hooks/use-project-analytics.ts` (add date params) |
| Possibly modify | `apps/api/main.py` (add date query params) |

---

## Dependencies

- Phase 1 (Project Analytics tab must exist)
- Phase 3 (Session Analytics tab must exist)

## Blocks

- None (final phase)

---

## Design Considerations

### Date Range UX Options

**Option A: Dropdown Preset**
```
[Last 14 days ▼]
```
Simple, minimal UI, covers common cases.

**Option B: Segmented Control**
```
[ 7d | 14d | 30d | 90d | Custom ]
```
All options visible, quick switching.

**Option C: Date Picker with Presets**
```
[Jan 1, 2026] - [Jan 11, 2026]  [7d] [14d] [30d]
```
Full flexibility with quick presets.

### Stats Display

Consider dual display for stats:
```
Total Tokens: 1.2M (245K in last 14 days)
```
Or toggle between "All Time" and "Selected Period" views.
