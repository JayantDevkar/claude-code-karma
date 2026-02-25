# Frontend: Display `subagent_type` in UI

## Goal
Display `subagent_type` in timeline events and subagent cards. Design for future filtering/grouping.

---

## Phase 1: Update TypeScript Types

**File:** `packages/types/src/index.ts`

### 1a. Update `SubagentSummary`

```typescript
// Line 64-70
export interface SubagentSummary {
  agent_id: string;
  slug: string | null;
  subagent_type: string | null;  // NEW
  tools_used: Record<string, number>;
  message_count: number;
  initial_prompt: string | null;
}
```

### 1b. Update `ToolCallMetadata`

```typescript
// Line 104-123, add to existing interface
export interface ToolCallMetadata {
  // ... existing fields ...

  // Subagent spawning (for Task tool)
  spawned_agent_id?: string;
  spawned_agent_slug?: string;
  is_spawn_task?: boolean;
  subagent_type?: string;  // NEW: "Explore", "Plan", "Bash", etc.

  // ... rest of fields ...
}
```

---

## Phase 2: Create Reusable Badge Component

**File:** `apps/web/components/subagent-type-badge.tsx` (NEW)

```tsx
import { cn } from "@/lib/utils";
import {
  SearchIcon,
  FileTextIcon,
  TerminalIcon,
  BotIcon,
  // Add more as needed
} from "lucide-react";

interface SubagentTypeBadgeProps {
  type: string | null | undefined;
  size?: "sm" | "md";
  className?: string;
}

// Icon mapping for known types - extensible
const typeConfig: Record<string, { icon: React.ElementType; color: string }> = {
  Explore: { icon: SearchIcon, color: "text-cyan-400 bg-cyan-500/20" },
  Plan: { icon: FileTextIcon, color: "text-amber-400 bg-amber-500/20" },
  Bash: { icon: TerminalIcon, color: "text-emerald-400 bg-emerald-500/20" },
  // Default fallback handled in component
};

export function SubagentTypeBadge({ type, size = "sm", className }: SubagentTypeBadgeProps) {
  if (!type) return null;

  const config = typeConfig[type] || { icon: BotIcon, color: "text-purple-400 bg-purple-500/20" };
  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full font-medium",
        config.color,
        size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs",
        className
      )}
    >
      <Icon className={size === "sm" ? "h-2.5 w-2.5" : "h-3 w-3"} />
      {type}
    </span>
  );
}
```

**Why reusable:** Same badge used in timeline, subagent cards, and future views.

---

## Phase 3: Update Timeline Rail

**File:** `apps/web/components/timeline-rail.tsx`

### 3a. Import Badge

```tsx
import { SubagentTypeBadge } from "./subagent-type-badge";
```

### 3b. Update `EventMetadataBadges` Component (~line 268-306)

Add `subagent_type` to props and render:

```tsx
interface EventMetadataBadgesProps {
  event: TimelineEvent;
  toolName?: string;
  hasToolResult?: boolean;
  spawnedAgentId?: string;
  spawnedAgentSlug?: string;
  subagentType?: string;  // NEW
}

function EventMetadataBadges({
  event,
  toolName,
  hasToolResult,
  spawnedAgentId,
  spawnedAgentSlug,
  subagentType,  // NEW
}: EventMetadataBadgesProps) {
  // ... existing code ...

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="font-medium text-foreground">{event.title}</span>
      {actorBadge}
      {/* NEW: Show subagent type badge */}
      {subagentType && <SubagentTypeBadge type={subagentType} />}
      {toolName && event.event_type === "tool_call" && (
        // ... existing tool badge ...
      )}
      {/* ... rest of badges ... */}
    </div>
  );
}
```

### 3c. Pass `subagentType` in `TimelineEventCard` (~line 416-422)

```tsx
<EventMetadataBadges
  event={event}
  toolName={toolName}
  hasToolResult={hasToolResult}
  spawnedAgentId={spawnedAgentId}
  spawnedAgentSlug={spawnedAgentSlug}
  subagentType={event.metadata?.subagent_type as string | undefined}  // NEW
/>
```

---

## Phase 4: Update Subagent Card

**File:** `apps/web/components/subagent-card.tsx`

### 4a. Import Badge

```tsx
import { SubagentTypeBadge } from "./subagent-type-badge";
```

### 4b. Add Badge to Header (~line 66-78)

After the slug badge, add type badge:

```tsx
<div className="flex items-center gap-2 min-w-0">
  <h4 className="font-medium text-foreground flex items-center gap-1.5">
    <span className="text-muted-foreground">Agent</span>
    <code className="font-mono text-primary">{subagent.agent_id}</code>
  </h4>
  {/* NEW: Subagent type badge */}
  {subagent.subagent_type && (
    <SubagentTypeBadge type={subagent.subagent_type} size="sm" />
  )}
  {subagent.slug && (
    <span className="rounded-full bg-secondary px-2 py-0.5 text-xs ...">
      {subagent.slug}
    </span>
  )}
</div>
```

---

## Phase 5: Update API Client Types (if separate)

**File:** `apps/web/lib/api.ts` (if types are re-exported)

Ensure `SubagentSummary` import/re-export includes new field. Usually just:

```typescript
export type { SubagentSummary } from "@claude-karma/types";
```

No change needed if types are imported directly from `@claude-karma/types`.

---

## Files Changed

| File | Change |
|------|--------|
| `packages/types/src/index.ts` | Add `subagent_type` to `SubagentSummary`, `ToolCallMetadata` |
| `apps/web/components/subagent-type-badge.tsx` | NEW - reusable badge component |
| `apps/web/components/timeline-rail.tsx` | Display badge in `EventMetadataBadges` |
| `apps/web/components/subagent-card.tsx` | Display badge in card header |

---

## Design Notes for Designer

- Badge uses icon + text format for scannability
- Color-coded by type (cyan=Explore, amber=Plan, green=Bash)
- Unknown types fall back to purple with generic bot icon
- Two sizes: `sm` (timeline) and `md` (cards, future expanded views)
- No filtering UI yet - just display

---

## Future Considerations

1. **Filtering:** Add `SubagentTypeFilter` component with multi-select
2. **Grouping:** Group subagent cards by type in agents page
3. **Stats:** Show type distribution in session summary
4. **Search:** Add `subagent_type:Explore` to search syntax

---

## Code Review (2026-01-10)

**Reviewer:** Senior System Architect

### Verdict: ✅ APPROVE - Types ready, UI pending

| Criteria | Status | Notes |
|----------|--------|-------|
| Type Correctness | ✅ PASS | `string \| null` matches backend `Optional[str]` |
| Interface Placement | ✅ PASS | Both `SubagentSummary` and `ToolCallMetadata` updated |
| Breaking Changes | ✅ PASS | Properly optional, backward-compatible |
| Test Mocks | ✅ PASS | Both populated and null cases covered |
| Documentation | ⚠️ CONCERN | Missing JSDoc comments |
| UI Display | ⚠️ CONCERN | SubagentCard doesn't show the field |

### ❌ Blockers
None

### ⚠️ Concerns (Non-Blocking)

1. **Missing JSDoc** (`packages/types/src/index.ts:67,118`)
   ```typescript
   // Current: No explanation
   subagent_type: string | null;

   // Recommended:
   /** Type of subagent: 'Explore', 'Plan', 'Bash', or custom name. Null if not specified. */
   subagent_type: string | null;
   ```

2. **UI Component Not Updated** (`apps/web/components/subagent-card.tsx`)
   - Backend serves `subagent_type` but UI doesn't display it
   - Users can't see the benefit of this feature yet

### 💡 Priority Follow-ups

| Priority | Action | Effort |
|----------|--------|--------|
| High | Add JSDoc comments to type definitions | 10min |
| High | Create `SubagentTypeBadge` component (Phase 2) | 30min |
| Medium | Update SubagentCard to display badge (Phase 4) | 20min |
| Low | Add union type for known values | 15min |

### JSDoc Fix

```typescript
// packages/types/src/index.ts

export interface SubagentSummary {
  agent_id: string;
  slug: string | null;
  /** Type of subagent: 'Explore', 'Plan', 'Bash', or custom agent name. Null if not specified or not matched. */
  subagent_type: string | null;
  tools_used: Record<string, number>;
  message_count: number;
  initial_prompt: string | null;
}

export interface ToolCallMetadata {
  // ... existing fields ...
  /** Type of subagent spawned by Task tool (e.g., 'Explore', 'Plan', 'Bash'). */
  subagent_type?: string;
  // ... rest of fields ...
}
```

### Status Check

```
Phase 1: TypeScript types     ✅ COMPLETE
Phase 2: Badge component      ✅ COMPLETE
Phase 3: Timeline rail        ✅ COMPLETE
Phase 4: Subagent card        ✅ COMPLETE
```

### Implementation Verified (2026-01-10)

| Phase | File | Status |
|-------|------|--------|
| 2 | `components/subagent-type-badge.tsx` | ✅ Created with icon mapping (Explore=cyan, Plan=amber, Bash=green) |
| 3 | `components/timeline-rail.tsx` | ✅ Imports badge, passes `event.metadata?.subagent_type` |
| 4 | `components/subagent-card.tsx` | ✅ Renders badge when `subagent.subagent_type` exists |
