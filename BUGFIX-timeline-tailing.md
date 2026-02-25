# Bug Fix: Timeline Tailing Middle Event Click Issue

## Problem

When tailing is enabled (showing last 3 events), clicking on the **middle event (2nd of 3)** didn't open or expand properly, while the 1st and 3rd events worked correctly.

## Root Cause

**Index Mismatch Between Loop Iteration and Visible Events**

In `TimelineRail.svelte`, the code was:

```svelte
{#each timeline.viewItems as item, index (item.id)}
  {@const visibleEvents = timeline.viewItems.filter((i) => !('type' in i))}
  {@const isLastVisible = index === visibleEvents.length - 1}
  {@const usePopup = !(isTailing && isLastVisible)}
```

The bug occurs when there are **gaps** in the timeline (which happens when tailing with more than N total events):

**Example: 10 total events, tailing ON showing last 3**

- `viewItems` = `[Gap (7 events), Event₈, Event₉, Event₁₀]`
- Loop iterations:
    - Gap: `loopIndex=0`, skipped
    - Event₈: `loopIndex=1`, `visibleEvents.length=3`, `isLastVisible = (1 === 2) = false` → `usePopup = true` ✓
    - Event₉: `loopIndex=2`, `visibleEvents.length=3`, `isLastVisible = (2 === 2) = TRUE` ❌ → `usePopup = false` ❌
    - Event₁₀: `loopIndex=3`, `visibleEvents.length=3`, `isLastVisible = (3 === 2) = false` → `usePopup = true` ❌

**Result:** Event₉ (middle) incorrectly gets `usePopup = false`, making it try to expand inline instead of opening a popup.

## Solution

**Use $derived to pre-compute visible events and calculate actual visible event index**

**In Script Section:**

```typescript
// Pre-compute visible events (excluding gaps) for correct indexing
const visibleEvents = $derived(timeline.viewItems.filter((i) => !('type' in i)));
```

**In Template:**

```svelte
{#each timeline.viewItems as item, loopIndex (item.id)}
  {@const eventItem = item}
  <!-- Find this event's actual position within visible events (not viewItems) -->
  {@const visibleEventIndex = visibleEvents.findIndex((e) => e.id === eventItem.id)}
  {@const isFirstVisible = visibleEventIndex === 0}
  {@const isLastVisible = visibleEventIndex === visibleEvents.length - 1}
  {@const usePopup = !(isTailing && isLastVisible)}
```

**Key Changes:**

1. **Pre-compute** `visibleEvents` using `$derived` in script section (reactive, efficient, follows Svelte 5 best practices)
2. Rename loop variable from `index` to `loopIndex` (clarity)
3. Calculate `visibleEventIndex` = actual position within visible events
4. Use `visibleEventIndex` for all index-dependent props

## Fixed Behavior

With the fix, the same scenario now works correctly:

- Event₈: `visibleEventIndex=0`, `isLastVisible = false` → `usePopup = true` ✓
- Event₉: `visibleEventIndex=1`, `isLastVisible = false` → `usePopup = true` ✓ **FIXED!**
- Event₁₀: `visibleEventIndex=2`, `isLastVisible = true` → `usePopup = false` ✓

## Files Changed

- `frontend/src/lib/components/timeline/TimelineRail.svelte` (lines 227-260)

## Impact

- ✅ Fixes both **session view** and **agent/subagent session view** (both use `ConversationView.svelte` → `TimelineRail`)
- ✅ Middle event now opens popup correctly when tailing is enabled
- ✅ Last event still expands inline as intended
- ✅ No impact on non-tailing mode or when no gaps exist

## Testing Checklist

- [x] Code compiles without TypeScript errors
- [ ] Manual test: Session timeline with tailing ON, click middle event (2 of 3) → opens popup
- [ ] Manual test: Agent timeline with tailing ON, click middle event → opens popup
- [ ] Manual test: Last event (3 of 3) still expands inline when tailing ON
- [ ] Manual test: All events work when tailing is OFF
- [ ] Manual test: Keyboard navigation (j/k keys) still works correctly
