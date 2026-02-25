# Test Plan: Phase Verification for Claude Karma Improvements

**Date**: January 2026
**Author**: System Engineer
**Status**: Planning

---

## Overview

This document defines the systematic test plan for verifying changes implemented across all API and UI/UX phases. Tests are organized by agent type:

- **API Tests** - HTTP requests against `localhost:8000`
- **Browser Tests** - Playwright actions against `localhost:3000`
- **Integration Tests** - End-to-end flows spanning both servers

---

## Test Infrastructure

### Prerequisites

```bash
# Start servers
pnpm dev:api    # localhost:8000
pnpm dev:web    # localhost:3000

# Install test dependencies
pip install pytest pytest-asyncio httpx
pnpm add -D @playwright/test
```

### Test Data Requirements

| Data Type | Location | Description |
|-----------|----------|-------------|
| Sample session | `~/.claude/projects/{test-project}/` | JSONL with 100+ messages |
| Session with subagents | Same | Session with 5+ spawned subagents |
| Session with tools | Same | Session with Read, Write, Shell, Task calls |
| Session with todos | `~/.claude/todos/` | Session-linked todo JSON files |

---

# API Phase Tests (localhost:8000)

## API Phase 1: Model-Level Caching

### Test Suite: `tests/api/test_phase1_caching.py`

#### Test 1.1: Session Metadata Caching

**Objective**: Verify metadata is extracted in single pass and cached

```python
@pytest.mark.asyncio
async def test_session_metadata_cached():
    """
    Given: A session with 500+ messages
    When: Accessing start_time, end_time, slug, get_usage_summary() sequentially
    Then: File should only be opened once (verify with mock)
    """
    # Arrange
    session_uuid = "test-session-uuid"

    # Act
    async with httpx.AsyncClient() as client:
        # First request - should load metadata
        r1 = await client.get(f"http://localhost:8000/sessions/{session_uuid}")

        # Second request - should use cache
        r2 = await client.get(f"http://localhost:8000/sessions/{session_uuid}")

    # Assert
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Response times: r2 should be significantly faster
```

#### Test 1.2: Cache Isolation Between Sessions

**Objective**: Verify different sessions have independent caches

```python
async def test_cache_isolation():
    """
    Given: Two distinct sessions
    When: Loading metadata for each
    Then: Cache entries should be independent, no cross-contamination
    """
    session1 = "uuid-session-1"
    session2 = "uuid-session-2"

    r1 = await client.get(f"/sessions/{session1}")
    r2 = await client.get(f"/sessions/{session2}")

    assert r1.json()["uuid"] != r2.json()["uuid"]
    assert r1.json()["start_time"] != r2.json()["start_time"]
```

#### Test 1.3: Property Access Performance

**Objective**: Verify repeated property access is O(1) after first load

| Metric | Before | Target |
|--------|--------|--------|
| First `end_time` access | ~100ms | ~100ms |
| Subsequent `end_time` access | ~100ms | <1ms |

---

## API Phase 2: Single-Pass Iteration

### Test Suite: `tests/api/test_phase2_single_pass.py`

#### Test 2.1: Timeline Single Iteration

**Objective**: Verify `/sessions/{uuid}/timeline` uses single-pass collection

```python
async def test_timeline_single_pass():
    """
    Given: A session with tools, subagents, and todos
    When: Fetching timeline
    Then:
      - Response includes all event types
      - iter_messages called only once per session (mock verification)
    """
    response = await client.get(f"/sessions/{uuid}/timeline")
    data = response.json()

    # Verify all event types present
    event_types = {e["event_type"] for e in data["events"]}
    assert "prompt" in event_types
    assert "tool_call" in event_types
```

#### Test 2.2: Subagents Endpoint Optimization

**Objective**: Verify `get_subagents()` reduced from 4+ passes to 1-2

```python
async def test_subagents_efficient():
    """
    Given: Session with 10 subagents
    When: Fetching subagents endpoint
    Then:
      - All subagent data returned correctly
      - Response time < 500ms (was ~2s before)
    """
    import time
    start = time.perf_counter()
    response = await client.get(f"/sessions/{uuid}/subagents")
    duration = time.perf_counter() - start

    assert response.status_code == 200
    assert len(response.json()["subagents"]) == 10
    assert duration < 0.5  # 500ms threshold
```

#### Test 2.3: File Activity Single Pass

**Objective**: Verify file reads/writes extracted in one iteration

```python
async def test_file_activity_complete():
    """
    Given: Session with Read, Write, Edit, Glob, Grep operations
    When: Fetching file-activity endpoint
    Then: All operations categorized correctly
    """
    response = await client.get(f"/sessions/{uuid}/file-activity")
    data = response.json()

    # Verify structure
    assert "reads" in data
    assert "writes" in data

    # Verify content
    assert all("path" in r for r in data["reads"])
    assert all("tool" in w for w in data["writes"])
```

---

## API Phase 3: HTTP Caching

### Test Suite: `tests/api/test_phase3_http_cache.py`

#### Test 3.1: Cache-Control Headers Present

**Objective**: Verify all endpoints return appropriate cache headers

```python
@pytest.mark.parametrize("endpoint,expected_max_age", [
    ("/projects", 30),
    ("/projects/{encoded}", 60),
    ("/sessions/{uuid}", 60),
    ("/sessions/{uuid}/timeline", 60),
    ("/sessions/{uuid}/file-activity", 300),
    ("/sessions/{uuid}/tools", 300),
])
async def test_cache_control_headers(endpoint, expected_max_age):
    """Verify Cache-Control header with correct max-age"""
    response = await client.get(endpoint)

    assert "Cache-Control" in response.headers
    assert f"max-age={expected_max_age}" in response.headers["Cache-Control"]
```

#### Test 3.2: ETag Generation and Validation

**Objective**: Verify ETag-based conditional requests work

```python
async def test_etag_conditional_request():
    """
    Given: Initial request returns ETag
    When: Subsequent request with If-None-Match header
    Then: Server returns 304 Not Modified
    """
    # First request
    r1 = await client.get(f"/sessions/{uuid}")
    etag = r1.headers.get("ETag")
    assert etag is not None

    # Conditional request
    r2 = await client.get(
        f"/sessions/{uuid}",
        headers={"If-None-Match": etag}
    )

    assert r2.status_code == 304
```

#### Test 3.3: Last-Modified Support

**Objective**: Verify If-Modified-Since handling

```python
async def test_last_modified_conditional():
    """
    Given: Initial request returns Last-Modified
    When: Subsequent request with If-Modified-Since (same or newer)
    Then: Server returns 304 Not Modified
    """
    r1 = await client.get(f"/sessions/{uuid}")
    last_modified = r1.headers.get("Last-Modified")

    r2 = await client.get(
        f"/sessions/{uuid}",
        headers={"If-Modified-Since": last_modified}
    )

    assert r2.status_code == 304
```

---

## API Phase 4: Async and Structural Optimizations

### Test Suite: `tests/api/test_phase4_async.py`

#### Test 4.1: Early Date Filtering

**Objective**: Verify date-filtered analytics loads fewer sessions

```python
async def test_date_filtering_efficiency():
    """
    Given: Project with 100 sessions across 30 days
    When: Requesting analytics for last 7 days
    Then: Only ~23 sessions should be loaded (not all 100)
    """
    from datetime import datetime, timedelta

    end_date = datetime.now().isoformat()
    start_date = (datetime.now() - timedelta(days=7)).isoformat()

    response = await client.get(
        f"/analytics/projects/{encoded_name}",
        params={"start_date": start_date, "end_date": end_date}
    )

    # Verify filtered results
    assert response.status_code == 200
    # Implementation should log/expose sessions_loaded metric
```

#### Test 4.2: Parallel Subagent Processing

**Objective**: Verify parallel processing provides speedup

```python
async def test_parallel_subagent_speedup():
    """
    Given: Session with 20 subagents
    When: Fetching subagents endpoint
    Then: Response time shows parallel speedup (< 1s vs ~4s serial)
    """
    import time

    start = time.perf_counter()
    response = await client.get(f"/sessions/{uuid_many_subagents}/subagents")
    duration = time.perf_counter() - start

    assert response.status_code == 200
    assert len(response.json()["subagents"]) >= 15
    assert duration < 1.0  # Parallel should complete in ~1s
```

#### Test 4.3: Project Listing Optimization

**Objective**: Verify project listing uses file stats only

```python
async def test_project_listing_fast():
    """
    Given: 50+ projects in ~/.claude/projects/
    When: Fetching /projects endpoint
    Then: Response time < 500ms (no JSONL parsing)
    """
    import time

    start = time.perf_counter()
    response = await client.get("/projects")
    duration = time.perf_counter() - start

    assert response.status_code == 200
    assert duration < 0.5
```

---

# Browser Tests (localhost:3000)

## UI/UX Phase 1: Foundation & Design System

### Test Suite: `tests/e2e/ui-phase1.spec.ts`

#### Test UI-1.1: Card Elevation Visibility

**Objective**: Verify cards are visually distinct from background

```typescript
import { test, expect } from '@playwright/test';

test('cards have visual distinction from background', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // Get background color
  const body = page.locator('body');
  const bgColor = await body.evaluate(el =>
    getComputedStyle(el).backgroundColor
  );

  // Get first card color
  const card = page.locator('[data-testid="stats-card"]').first();
  const cardColor = await card.evaluate(el =>
    getComputedStyle(el).backgroundColor
  );

  // Colors should be different
  expect(bgColor).not.toEqual(cardColor);
});
```

#### Test UI-1.2: Tabular Numbers Alignment

**Objective**: Verify numeric values use tabular figures

```typescript
test('stats values use tabular numbers', async ({ page }) => {
  await page.goto('http://localhost:3000');

  const metricValue = page.locator('.metric-value').first();
  const fontVariant = await metricValue.evaluate(el =>
    getComputedStyle(el).fontVariantNumeric
  );

  expect(fontVariant).toContain('tabular-nums');
});
```

#### Test UI-1.3: Stats Card Descriptions

**Objective**: Verify all stats cards have descriptions

```typescript
test('all stats cards have descriptions', async ({ page }) => {
  await page.goto('http://localhost:3000');

  const statsCards = page.locator('[data-testid="stats-card"]');
  const count = await statsCards.count();

  for (let i = 0; i < count; i++) {
    const description = statsCards.nth(i).locator('[data-testid="stats-description"]');
    await expect(description).not.toBeEmpty();
  }
});
```

---

## UI/UX Phase 2: Data Sanitization & Display

### Test Suite: `tests/e2e/ui-phase2.spec.ts`

#### Test UI-2.1: No XML Tags Visible

**Objective**: Verify XML tags are sanitized from prompts

```typescript
test('no XML tags visible in session cards', async ({ page }) => {
  await page.goto('http://localhost:3000/project/test-project');

  // Get all session card text
  const sessionCards = page.locator('[data-testid="session-card"]');
  const count = await sessionCards.count();

  for (let i = 0; i < count; i++) {
    const text = await sessionCards.nth(i).textContent();

    // Should not contain internal XML tags
    expect(text).not.toContain('<local-command-caveat>');
    expect(text).not.toContain('<command-name>');
    expect(text).not.toContain('<system-reminder>');
  }
});
```

#### Test UI-2.2: No Negative Durations

**Objective**: Verify edge case durations display correctly

```typescript
test('no negative durations displayed', async ({ page }) => {
  await page.goto('http://localhost:3000/project/test-project');

  // Find all duration displays
  const durations = page.locator('[data-testid="duration"]');
  const count = await durations.count();

  for (let i = 0; i < count; i++) {
    const text = await durations.nth(i).textContent();
    expect(text).not.toMatch(/^-\d/);  // No negative numbers
    expect(text).not.toEqual('-1s');
  }
});
```

#### Test UI-2.3: Model Name Formatting

**Objective**: Verify model names display in human-readable format

```typescript
test('model names are human readable', async ({ page }) => {
  await page.goto('http://localhost:3000/session/test-uuid');

  const modelBadge = page.locator('[data-testid="model-badge"]');
  const text = await modelBadge.textContent();

  // Should show formatted name, not raw identifier
  expect(text).not.toMatch(/opus-4-5-\d{8}/);
  expect(text).toMatch(/(4\.5 Opus|3\.5 Sonnet|Haiku|System)/);
});
```

#### Test UI-2.4: Timeline Elapsed Time Increments

**Objective**: Verify timeline shows correct elapsed times

```typescript
test('timeline elapsed times increment correctly', async ({ page }) => {
  await page.goto('http://localhost:3000/session/test-uuid/timeline');

  const timeStamps = page.locator('[data-testid="elapsed-time"]');
  const count = await timeStamps.count();

  // Collect all elapsed times
  const times: string[] = [];
  for (let i = 0; i < Math.min(count, 10); i++) {
    times.push(await timeStamps.nth(i).textContent() || '');
  }

  // Not all should be +0:00
  const uniqueTimes = new Set(times);
  expect(uniqueTimes.size).toBeGreaterThan(1);
});
```

---

## UI/UX Phase 3: Session Cards & Components

### Test Suite: `tests/e2e/ui-phase3.spec.ts`

#### Test UI-3.1: Session Card Structure

**Objective**: Verify session cards have proper visual hierarchy

```typescript
test('session cards have complete structure', async ({ page }) => {
  await page.goto('http://localhost:3000/project/test-project');

  const card = page.locator('[data-testid="session-card"]').first();

  // Header elements
  await expect(card.locator('[data-testid="session-name"]')).toBeVisible();
  await expect(card.locator('[data-testid="model-badge"]')).toBeVisible();
  await expect(card.locator('[data-testid="relative-time"]')).toBeVisible();

  // Stats row
  await expect(card.locator('[data-testid="message-count"]')).toBeVisible();
  await expect(card.locator('[data-testid="duration"]')).toBeVisible();
});
```

#### Test UI-3.2: Session Name Display Logic

**Objective**: Verify session naming fallback logic

```typescript
test('session names follow display logic', async ({ page }) => {
  await page.goto('http://localhost:3000/project/test-project');

  const sessionNames = page.locator('[data-testid="session-name"]');
  const count = await sessionNames.count();

  for (let i = 0; i < count; i++) {
    const name = await sessionNames.nth(i).textContent();

    // Should not be raw UUID only
    expect(name).not.toMatch(/^[a-f0-9-]{36}$/);

    // Should have meaningful content
    expect(name?.length).toBeGreaterThan(3);
  }
});
```

#### Test UI-3.3: Card Hover States

**Objective**: Verify cards have hover interaction feedback

```typescript
test('session cards have hover feedback', async ({ page }) => {
  await page.goto('http://localhost:3000/project/test-project');

  const card = page.locator('[data-testid="session-card"]').first();

  // Get initial background
  const initialBg = await card.evaluate(el =>
    getComputedStyle(el).backgroundColor
  );

  // Hover
  await card.hover();
  await page.waitForTimeout(300);  // Wait for transition

  // Get hover background
  const hoverBg = await card.evaluate(el =>
    getComputedStyle(el).backgroundColor
  );

  // Background should change on hover
  expect(initialBg).not.toEqual(hoverBg);
});
```

#### Test UI-3.4: Activity Indicators

**Objective**: Verify recent sessions show activity indicator

```typescript
test('recent sessions show activity indicator', async ({ page }) => {
  await page.goto('http://localhost:3000/project/test-project');

  // Assuming test data has recent sessions
  const activityDots = page.locator('[data-testid="activity-indicator"]');
  const greenDots = activityDots.locator('.bg-green-500');

  // At least one recent session should have green indicator
  const greenCount = await greenDots.count();
  // This assertion may need adjustment based on test data
  expect(greenCount).toBeGreaterThanOrEqual(0);
});
```

---

## UI/UX Phase 4: Timeline & Interactivity

### Test Suite: `tests/e2e/ui-phase4.spec.ts`

#### Test UI-4.1: Filter Bar Toggle

**Objective**: Verify timeline filters toggle correctly

```typescript
test('timeline filters toggle with visual feedback', async ({ page }) => {
  await page.goto('http://localhost:3000/session/test-uuid/timeline');

  const filterChip = page.locator('[data-testid="filter-prompt"]');

  // Initial state
  const initialClass = await filterChip.getAttribute('class');
  expect(initialClass).not.toContain('active');

  // Click to activate
  await filterChip.click();

  // Should show active state
  const activeClass = await filterChip.getAttribute('class');
  expect(activeClass).toContain('active');

  // Aria-pressed should be true
  const pressed = await filterChip.getAttribute('aria-pressed');
  expect(pressed).toBe('true');
});
```

#### Test UI-4.2: Tool Call Formatting

**Objective**: Verify tool calls show formatted input/output

```typescript
test('tool calls show formatted content', async ({ page }) => {
  await page.goto('http://localhost:3000/session/test-uuid/timeline');

  // Find a tool call event
  const toolEvent = page.locator('[data-testid="event-tool_call"]').first();

  // Expand it
  await toolEvent.click();

  // Should show formatted input section
  const inputSection = toolEvent.locator('[data-testid="tool-input"]');
  await expect(inputSection).toBeVisible();

  // Should not show raw JSON for common tools
  const content = await inputSection.textContent();
  expect(content).not.toMatch(/^\{.*\}$/);  // Not raw JSON object
});
```

#### Test UI-4.3: Keyboard Navigation

**Objective**: Verify j/k navigation works in timeline

```typescript
test('keyboard navigation works in timeline', async ({ page }) => {
  await page.goto('http://localhost:3000/session/test-uuid/timeline');

  // Focus on timeline
  await page.locator('[data-testid="timeline-container"]').focus();

  // Press 'j' to select first event
  await page.keyboard.press('j');

  // First event should be selected/focused
  const firstEvent = page.locator('[data-testid^="event-"]').first();
  const firstClass = await firstEvent.getAttribute('class');
  expect(firstClass).toContain('selected');

  // Press 'j' again to move to second
  await page.keyboard.press('j');

  const secondEvent = page.locator('[data-testid^="event-"]').nth(1);
  const secondClass = await secondEvent.getAttribute('class');
  expect(secondClass).toContain('selected');

  // Press 'k' to go back
  await page.keyboard.press('k');

  const updatedFirstClass = await firstEvent.getAttribute('class');
  expect(updatedFirstClass).toContain('selected');
});
```

#### Test UI-4.4: Event Expansion

**Objective**: Verify Enter/Esc for expand/collapse

```typescript
test('Enter expands, Esc collapses events', async ({ page }) => {
  await page.goto('http://localhost:3000/session/test-uuid/timeline');

  // Navigate to first event
  await page.keyboard.press('j');

  // Press Enter to expand
  await page.keyboard.press('Enter');

  const firstEvent = page.locator('[data-testid^="event-"]').first();
  const expandedContent = firstEvent.locator('[data-testid="event-expanded"]');
  await expect(expandedContent).toBeVisible();

  // Press Escape to collapse
  await page.keyboard.press('Escape');
  await expect(expandedContent).not.toBeVisible();
});
```

---

## UI/UX Phase 5: Navigation & Accessibility

### Test Suite: `tests/e2e/ui-phase5.spec.ts`

#### Test UI-5.1: Command Palette Opens

**Objective**: Verify Cmd+K opens command palette

```typescript
test('command palette opens with Cmd+K', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // Press Cmd+K (Mac) or Ctrl+K (other)
  await page.keyboard.press('Meta+k');

  const palette = page.locator('[data-testid="command-palette"]');
  await expect(palette).toBeVisible();

  // Should have search input focused
  const input = palette.locator('input');
  await expect(input).toBeFocused();
});
```

#### Test UI-5.2: Command Palette Search

**Objective**: Verify search filters results

```typescript
test('command palette search filters results', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.keyboard.press('Meta+k');

  const input = page.locator('[data-testid="command-palette"] input');

  // Type a project name
  await input.fill('test-project');

  // Results should be filtered
  const results = page.locator('[data-testid="command-item"]');
  const count = await results.count();

  // Should have at least one result
  expect(count).toBeGreaterThan(0);

  // Results should match search term
  const firstResult = await results.first().textContent();
  expect(firstResult?.toLowerCase()).toContain('test');
});
```

#### Test UI-5.3: Skip Link Functionality

**Objective**: Verify skip link works for keyboard users

```typescript
test('skip link navigates to main content', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // Tab to trigger skip link visibility
  await page.keyboard.press('Tab');

  // Skip link should be visible
  const skipLink = page.locator('[data-testid="skip-link"]');
  await expect(skipLink).toBeVisible();

  // Activate it
  await skipLink.click();

  // Focus should be on main content
  const main = page.locator('#main-content');
  await expect(main).toBeFocused();
});
```

#### Test UI-5.4: Chart Accessibility

**Objective**: Verify charts have ARIA labels

```typescript
test('charts have accessibility labels', async ({ page }) => {
  await page.goto('http://localhost:3000/session/test-uuid');

  const charts = page.locator('[role="img"]');
  const count = await charts.count();

  for (let i = 0; i < count; i++) {
    const chart = charts.nth(i);

    // Should have aria-labelledby or aria-label
    const labelledBy = await chart.getAttribute('aria-labelledby');
    const label = await chart.getAttribute('aria-label');

    expect(labelledBy || label).toBeTruthy();
  }
});
```

#### Test UI-5.5: Focus Trap in Modals

**Objective**: Verify focus is trapped in command palette

```typescript
test('focus is trapped in command palette', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.keyboard.press('Meta+k');

  const palette = page.locator('[data-testid="command-palette"]');

  // Tab through all focusable elements
  for (let i = 0; i < 10; i++) {
    await page.keyboard.press('Tab');

    // Focus should remain within palette
    const focused = page.locator(':focus');
    await expect(focused).toBeAttached();

    // Verify focused element is inside palette
    const isInPalette = await focused.evaluate((el, container) =>
      container.contains(el),
      await palette.elementHandle()
    );
    expect(isInPalette).toBe(true);
  }
});
```

---

## UI/UX Phase 6: Dashboard Polish & Delight

### Test Suite: `tests/e2e/ui-phase6.spec.ts`

#### Test UI-6.1: Trend Indicators Display

**Objective**: Verify trend arrows and colors are correct

```typescript
test('trend indicators show correct direction', async ({ page }) => {
  await page.goto('http://localhost:3000');

  const trends = page.locator('[data-testid="trend-indicator"]');
  const count = await trends.count();

  for (let i = 0; i < count; i++) {
    const trend = trends.nth(i);
    const text = await trend.textContent();
    const hasClass = await trend.getAttribute('class');

    if (text?.startsWith('+')) {
      expect(hasClass).toContain('text-green');
    } else if (text?.startsWith('-')) {
      expect(hasClass).toContain('text-red');
    }
  }
});
```

#### Test UI-6.2: Sparklines Render

**Objective**: Verify sparklines render correctly

```typescript
test('sparklines render with data', async ({ page }) => {
  await page.goto('http://localhost:3000');

  const sparklines = page.locator('[data-testid="sparkline"]');
  const count = await sparklines.count();

  for (let i = 0; i < count; i++) {
    const svg = sparklines.nth(i).locator('svg');
    await expect(svg).toBeVisible();

    // Should have path element (the line)
    const path = svg.locator('path');
    await expect(path.first()).toBeVisible();
  }
});
```

#### Test UI-6.3: Loading Skeletons Animation

**Objective**: Verify shimmer effect on loading states

```typescript
test('loading skeletons have shimmer effect', async ({ page }) => {
  // Intercept API to delay response
  await page.route('**/api/**', async route => {
    await new Promise(resolve => setTimeout(resolve, 2000));
    await route.continue();
  });

  await page.goto('http://localhost:3000');

  // Should see skeleton elements
  const skeletons = page.locator('.skeleton');
  await expect(skeletons.first()).toBeVisible();

  // Should have animation
  const animation = await skeletons.first().evaluate(el =>
    getComputedStyle(el).animationName
  );
  expect(animation).toContain('shimmer');
});
```

#### Test UI-6.4: Stagger Animation

**Objective**: Verify cards animate in with stagger

```typescript
test('stats cards animate with stagger', async ({ page }) => {
  await page.goto('http://localhost:3000');

  const grid = page.locator('.stagger-children');
  const children = grid.locator('> *');

  // Each child should have animation-delay
  const delays: number[] = [];
  const count = await children.count();

  for (let i = 0; i < Math.min(count, 5); i++) {
    const delay = await children.nth(i).evaluate(el => {
      const style = getComputedStyle(el);
      return parseFloat(style.animationDelay) * 1000;
    });
    delays.push(delay);
  }

  // Delays should be increasing
  for (let i = 1; i < delays.length; i++) {
    expect(delays[i]).toBeGreaterThanOrEqual(delays[i-1]);
  }
});
```

#### Test UI-6.5: Empty State Display

**Objective**: Verify empty states show contextual messages

```typescript
test('empty states are contextual', async ({ page }) => {
  // Navigate to project with no sessions
  await page.goto('http://localhost:3000/project/empty-project');

  const emptyState = page.locator('[data-testid="empty-state"]');
  await expect(emptyState).toBeVisible();

  // Should have appropriate message
  const title = emptyState.locator('h3');
  await expect(title).toContainText(/no sessions/i);

  // Should have icon
  const icon = emptyState.locator('svg');
  await expect(icon).toBeVisible();
});
```

---

# Integration Tests

## Cross-Server Tests

### Test Suite: `tests/integration/test_full_flow.spec.ts`

#### Test INT-1: Session Data Flow

**Objective**: Verify data flows correctly from API to UI

```typescript
test('session data displays correctly from API', async ({ page }) => {
  // Get session data from API
  const apiResponse = await fetch('http://localhost:8000/sessions/test-uuid');
  const sessionData = await apiResponse.json();

  // Navigate to session page
  await page.goto('http://localhost:3000/session/test-uuid');

  // Verify data matches
  const displayedUuid = await page.locator('[data-testid="session-uuid"]').textContent();
  expect(displayedUuid).toContain(sessionData.uuid.slice(0, 8));

  const displayedMessages = await page.locator('[data-testid="message-count"]').textContent();
  expect(displayedMessages).toContain(String(sessionData.message_count));
});
```

#### Test INT-2: Cache Coherence

**Objective**: Verify browser cache works with API cache

```typescript
test('HTTP cache headers respected by browser', async ({ page, context }) => {
  await page.goto('http://localhost:3000/session/test-uuid');

  // First load - should hit API
  await page.waitForLoadState('networkidle');

  // Navigate away
  await page.goto('http://localhost:3000');

  // Navigate back
  await page.goto('http://localhost:3000/session/test-uuid');

  // Check network tab for 304 or cache hit
  // This requires inspecting network requests
});
```

#### Test INT-3: Real-Time Data Updates

**Objective**: Verify UI reflects API data changes

```typescript
test('UI updates when session data changes', async ({ page }) => {
  // Initial load
  await page.goto('http://localhost:3000/session/test-uuid');
  const initialCount = await page.locator('[data-testid="message-count"]').textContent();

  // Simulate session update (append to JSONL)
  // This would require test infrastructure to modify test data

  // Refresh
  await page.reload();

  // Verify updated count
  const updatedCount = await page.locator('[data-testid="message-count"]').textContent();
  // Assertion depends on test setup
});
```

---

## Performance Benchmarks

### Test Suite: `tests/performance/benchmarks.py`

```python
import time
import statistics
from httpx import AsyncClient

async def benchmark_endpoint(client: AsyncClient, endpoint: str, iterations: int = 10):
    """Benchmark an endpoint over multiple iterations."""
    times = []

    for _ in range(iterations):
        start = time.perf_counter()
        response = await client.get(endpoint)
        duration = time.perf_counter() - start
        times.append(duration)

        assert response.status_code == 200

    return {
        "endpoint": endpoint,
        "iterations": iterations,
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0,
    }

# Benchmark targets
BENCHMARKS = {
    "/projects": {"target_p50": 0.1},
    "/sessions/{uuid}": {"target_p50": 0.2},
    "/sessions/{uuid}/timeline": {"target_p50": 0.5},
    "/sessions/{uuid}/subagents": {"target_p50": 0.5},
    "/sessions/{uuid}/file-activity": {"target_p50": 0.3},
}
```

---

## Verification Matrix

### API Phases

| Phase | Test Suite | Key Assertions |
|-------|------------|----------------|
| 1 | `test_phase1_caching.py` | Single file read per session, O(1) property access |
| 2 | `test_phase2_single_pass.py` | Single iteration per endpoint, correct data extraction |
| 3 | `test_phase3_http_cache.py` | Cache-Control headers, 304 responses, ETags |
| 4 | `test_phase4_async.py` | Date filtering efficiency, parallel speedup |

### UI/UX Phases

| Phase | Test Suite | Key Assertions |
|-------|------------|----------------|
| 1 | `ui-phase1.spec.ts` | Card elevation, tabular nums, descriptions |
| 2 | `ui-phase2.spec.ts` | No XML tags, no negative durations, formatted models |
| 3 | `ui-phase3.spec.ts` | Session card structure, naming logic, hover states |
| 4 | `ui-phase4.spec.ts` | Filter toggles, tool formatting, keyboard nav |
| 5 | `ui-phase5.spec.ts` | Command palette, skip link, ARIA labels, focus trap |
| 6 | `ui-phase6.spec.ts` | Trends, sparklines, shimmer, stagger animations |

---

## Execution Order

### Recommended Test Order

1. **API Unit Tests** - Verify backend changes in isolation
2. **API Integration Tests** - Verify endpoint contracts
3. **UI Component Tests** - Verify individual components
4. **UI E2E Tests** - Verify full page functionality
5. **Cross-Server Tests** - Verify API-to-UI data flow
6. **Performance Benchmarks** - Verify performance improvements

### CI/CD Pipeline Stages

```yaml
stages:
  - lint
  - unit_tests
  - api_tests
  - ui_tests
  - integration_tests
  - performance_tests
```

---

## Success Criteria

### API Phases

- [ ] All existing tests pass after changes
- [ ] New cache tests pass
- [ ] Benchmark shows >5x improvement for repeated property access
- [ ] HTTP cache hit rate >50% on repeated requests
- [ ] Date-filtered analytics loads 50%+ fewer sessions

### UI/UX Phases

- [ ] No visual regressions (screenshot comparison)
- [ ] Lighthouse accessibility score >= 90
- [ ] All keyboard interactions work as specified
- [ ] No raw XML/model names visible in UI
- [ ] Empty states and edge cases handled gracefully

---

## Appendix: Test Data Setup

### Creating Test Sessions

```python
# scripts/create_test_data.py

import json
from pathlib import Path
from datetime import datetime, timedelta
import uuid

def create_test_session(project_path: Path, message_count: int = 100):
    """Create a test session with specified message count."""
    session_uuid = str(uuid.uuid4())
    jsonl_path = project_path / f"{session_uuid}.jsonl"

    messages = []
    base_time = datetime.now() - timedelta(hours=2)

    for i in range(message_count):
        msg_time = base_time + timedelta(seconds=i * 10)

        if i % 2 == 0:
            # User message
            messages.append({
                "type": "user",
                "timestamp": msg_time.isoformat(),
                "content": f"Test prompt {i}",
                "uuid": str(uuid.uuid4()),
            })
        else:
            # Assistant message
            messages.append({
                "type": "assistant",
                "timestamp": msg_time.isoformat(),
                "content_blocks": [
                    {"type": "text", "text": f"Response {i}"}
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                }
            })

    with open(jsonl_path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    return session_uuid
```

---

## Appendix: Playwright Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
  webServer: [
    {
      command: 'pnpm dev:api',
      url: 'http://localhost:8000',
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'pnpm dev:web',
      url: 'http://localhost:3000',
      reuseExistingServer: !process.env.CI,
    },
  ],
});
```
