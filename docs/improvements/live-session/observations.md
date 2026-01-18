# Live Session Tailing Feature - Observations

*Date: Jan 18, 2026*

## Overview

This document captures observations from testing the live session "tailing" feature implementation for timeline events. The feature was implemented across the frontend and API.

---

## Code Changes Reviewed

### Frontend Changes (4 files modified)

1. **`src/routes/projects/[encoded_name]/[session_slug]/+page.svelte`**
   - Added tailing state management (`isTailing`, `hasAutoEnabledTailing`)
   - Auto-enables tailing when session first becomes live
   - Provides `toggleTailing` function
   - Passes `isTailing` and `onToggleTailing` props to `TimelineRail`
   - Shows "Tail Events" button in timeline header for live sessions
   - Shows event count summary: "Showing 3 of N events"

2. **`src/lib/components/timeline/TimelineRail.svelte`**
   - Accepts `isLive`, `isTailing`, `onToggleTailing` props
   - Auto-scroll to last event when:
     - New events arrive while tailing is enabled
     - Tailing is first toggled on
   - Auto-expands the last event when tailing is active
   - Memory leak fix: Cleanup for `userScrollTimeout` and `scrollRafId` in `onMount` return

3. **`src/lib/utils/timelineLogic.svelte.ts`**
   - New `TimelineLogicOptions` interface with `isTailingGetter` and `tailCount`
   - `viewItems` derived state handles both filter-based visibility AND tailing mode
   - When tailing ON + no filter: only show last N events
   - When tailing ON + filter active: show filter matches + last N events
   - Introduces `TimelineGap` type for representing hidden events
   - Gap component can expand hidden events via `expandGap()` function

4. **`src/lib/components/timeline/TimelineGap.svelte`**
   - Type import fix (moved to `import type`)

### API Changes (1 file modified)

**`routers/sessions.py`**
- When `fresh=True` parameter is passed, clears in-memory `SessionCache`
- Ensures `message_count`, `duration`, `tokens`, `cost`, `cache_hit_rate` are recomputed from JSONL file
- Previously, `fresh` only affected HTTP cache headers, not Python-level cache

---

## Browser Testing Observations

### Session Header
- **ACTIVE status badge** displays in top-right corner with green pulsing indicator
- Badge uses consistent coloring from `statusConfig`
- Session metadata (UUID, start time, duration) shows correctly
- Duration updates in real-time (observed: 2m 15s → 2m 38s → 2m 51s → 3m 6s)

### Tailing Mode UI
- **"Tail Events" button** appears in timeline header only for live sessions
- Button has green/teal styling with down-arrow icon
- Button has `[pressed]` state when active (visual toggle feedback)
- Subtitle changes based on mode:
  - Tailing ON: "Showing 3 of N events"
  - Tailing OFF: "Chronological sequence of events in this session"

### Gap Indicator
- When tailing is active, hidden events shown as compact gap:
  - `hidden (54)` → `hidden (57)` → `hidden (62)` → `hidden (63)` as session progresses
- Gap shows clickable event type buttons: "Prompt", "Tool Bash", "Response", etc.
- "Show context" button ("+") allows expanding hidden events
- Individual hidden events can be clicked to reveal them

### Event Display
- Last 3 events shown when tailing is enabled
- Most recent event is auto-expanded
- Events update in real-time (2-second polling interval)
- Tool calls show tool name, status (done/pending/error), and relative timestamp

### Filter Interaction
- Filter bar is sticky at top during scrolling
- Filters remain functional during tailing:
  - Prompts: 2
  - Tools: count increases (36 → 39 → 42 → 45)
  - Todos: 2
  - Errors: 2
  - Response: count increases (15 → 17 → 19 → 20)
- Total event count visible (55 → 57 → 60 → 65 → 69 events)

### Keyboard Shortcuts
- Keyboard shortcuts hint hidden when tailing is active
- Hint visible when tailing is OFF: "j/k to navigate, Enter to expand, gg/G first/last"

### Toggle Behavior
- Clicking "Tail Events" button OFF shows full chronological timeline
- Full timeline starts from first event (User prompt at +0:00)
- All 69+ events visible when tailing disabled
- Clicking "Tail Events" back ON returns to showing last 3 events

---

## Real-time Update Observations

- Event counts increment as session progresses
- New events appear at bottom of tailing view
- Auto-scroll keeps most recent events visible
- Session duration updates continuously
- Status badge remains "ACTIVE" throughout session

---

## Screenshots Captured

1. `live-session-timeline-no-tailing.png` - Initial view with tailing active (confusing filename)
2. `live-session-with-status-badge.png` - Tailing active, gap visible with hidden events
3. `live-session-header-view.png` - Full header with ACTIVE badge, tailing button
4. `live-session-no-tailing.png` - Full timeline with tailing disabled

---

## Technical Implementation Details

### Tailing Logic (`timelineLogic.svelte.ts:210-278`)
```
1. If no filter AND not tailing: show all events
2. For each event, check visibility:
   - Is event in last N (tailCount)? → `isInLastN`
   - Tailing ON + no filter: show only `isInLastN` OR manually revealed
   - Tailing ON + filter: show matches + `isInLastN` OR manually revealed
   - Tailing OFF: show based on filter/search only
3. Hidden events accumulate into `TimelineGap` objects
4. Gaps can be expanded via `expandGap()` adding to `manuallyRevealedIds`
```

### Auto-scroll Logic (`TimelineRail.svelte:106-140`)
```
1. Track `prevEventsLength` and `prevIsTailing`
2. New events arrived while tailing? → RAF → scroll to last event (smooth)
3. Tailing just enabled? → setTimeout(100ms) → scroll to last event (smooth)
4. Update tracking state after each check
5. Cleanup RAF on effect cleanup
```

### Cache Clearing Logic (`sessions.py:491-495`)
```python
if fresh:
    session.clear_cache()
```

---

## Questions Arising From Observations

1. The gap shows individual event type buttons - are these intended to be clickable to reveal that specific event?
2. Is the auto-expand of the last event desirable when rapidly receiving events (could cause visual "jumping")?
3. Should the keyboard shortcut hint reappear if user scrolls up while tailing?
4. What happens to tailing state when navigating away and back to the session?
5. Is `TAIL_COUNT = 3` the optimal number, or should it be configurable?
6. What happens when a filter is active and fewer than 3 events match?
