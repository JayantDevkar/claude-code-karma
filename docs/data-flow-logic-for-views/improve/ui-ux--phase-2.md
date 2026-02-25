# UI/UX Improvement Plan - Phase 2: Data Sanitization & Display

**Priority**: Critical
**Effort**: Medium
**Impact**: High (directly affects user experience)

---

## Overview

This phase addresses the data display anomalies observed in session cards, timeline events, and headers. Raw XML/command tags, negative durations, and unformatted model names create a confusing user experience.

---

## Issue 1: XML Tags Visible in Initial Prompts

### Current State

```
| Session card initial_prompt | `<local-command-caveat>Caveat:...` |
| Timeline event content | `<command-name>/exit</command-name>` |
```

Users see raw XML markup instead of clean, parsed content.

### Root Cause

The `initial_prompt` field from the API contains raw JSONL content which may include Claude Code's internal XML tags.

### Solution: Create a Content Sanitizer Utility

```typescript
// apps/web/lib/content-sanitizer.ts

/**
 * XML tags used internally by Claude Code that should be hidden from users
 */
const INTERNAL_TAGS = [
  'local-command-caveat',
  'local-command-stdout',
  'command-name',
  'command-message',
  'synthetic',
  'system-reminder',
  'user-prompt-submit-hook',
] as const;

/**
 * Removes Claude Code internal XML tags from content
 * Preserves the text content within tags where meaningful
 */
export function sanitizePromptContent(content: string | null): string {
  if (!content) return '';

  let sanitized = content;

  // Remove caveat tags entirely (meta-content)
  sanitized = sanitized.replace(
    /<local-command-caveat>[\s\S]*?<\/local-command-caveat>/g,
    ''
  );

  // Extract command name for display
  sanitized = sanitized.replace(
    /<command-name>(.*?)<\/command-name>/g,
    (_, cmd) => `/${cmd.replace(/^\//, '')}`
  );

  // Extract command message
  sanitized = sanitized.replace(
    /<command-message>(.*?)<\/command-message>/g,
    '$1'
  );

  // Remove stdout wrappers, keep content
  sanitized = sanitized.replace(
    /<local-command-stdout>([\s\S]*?)<\/local-command-stdout>/g,
    '$1'
  );

  // Remove any remaining internal tags
  INTERNAL_TAGS.forEach(tag => {
    const regex = new RegExp(`</?${tag}[^>]*>`, 'g');
    sanitized = sanitized.replace(regex, '');
  });

  // Clean up excessive whitespace
  sanitized = sanitized.replace(/\n{3,}/g, '\n\n').trim();

  return sanitized;
}

/**
 * Checks if content is primarily system/meta content
 * Returns true if content should show a placeholder instead
 */
export function isSystemContent(content: string | null): boolean {
  if (!content) return false;

  const stripped = sanitizePromptContent(content);
  return stripped.length < 10 || /^(exit|goodbye!?|\s*)$/i.test(stripped);
}
```

### Implementation

| File | Change |
|------|--------|
| `apps/web/lib/content-sanitizer.ts` | Create new utility file |
| `apps/web/components/session-card.tsx` | Use `sanitizePromptContent()` on `initial_prompt` |
| `apps/web/components/expandable-prompt.tsx` | Use sanitizer on prompt content |
| `apps/web/components/timeline-rail.tsx` | Use sanitizer on event `summary` |

### Session Card Display Logic

```typescript
// session-card.tsx
const sanitizedPrompt = sanitizePromptContent(session.initial_prompt);
const isSystem = isSystemContent(session.initial_prompt);

return (
  <div>
    {isSystem ? (
      <span className="text-muted-foreground italic">
        System session (no user prompt)
      </span>
    ) : (
      <p className="line-clamp-2">{sanitizedPrompt}</p>
    )}
  </div>
);
```

---

## Issue 2: Negative Duration Display

### Current State

```
| Session card duration | `-1s` |
```

Negative durations appear when `end_time < start_time` or calculation errors occur.

### Solution: Duration Formatter with Edge Case Handling

```typescript
// apps/web/lib/format.ts

export function formatDuration(seconds: number | null | undefined): string {
  // Handle null/undefined
  if (seconds == null) return 'N/A';

  // Handle negative or zero (edge cases)
  if (seconds <= 0) return '< 1s';

  // Standard formatting
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  }

  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

export function formatDurationCompact(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return '--';
  // Same logic but returns shorter format
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}
```

---

## Issue 3: Raw Model Names Display

### Current State

```
| Model badge format | `opus-4-5-20251101` | Expected: "4.5 Opus" |
| Model badge | `<synthetic>` | Expected: hidden or styled badge |
```

### Solution: Enhanced Model Name Formatter

```typescript
// apps/web/lib/format.ts

interface ParsedModel {
  family: string;       // "Opus", "Sonnet", "Haiku"
  version: string;      // "4.5", "3.5"
  date?: string;        // "20251101"
  isOfficialModel: boolean;
  displayName: string;  // "4.5 Opus"
  fullName: string;     // "Claude 4.5 Opus (Nov 2025)"
}

const MODEL_PATTERNS = [
  // Claude 4.x models
  { regex: /claude-opus-4-5-(\d{8})/i, family: 'Opus', version: '4.5' },
  { regex: /opus-4-5-(\d{8})/i, family: 'Opus', version: '4.5' },
  { regex: /claude-4-opus/i, family: 'Opus', version: '4' },

  // Claude 3.x models
  { regex: /claude-3-5-sonnet-(\d{8})/i, family: 'Sonnet', version: '3.5' },
  { regex: /claude-3-opus-(\d{8})/i, family: 'Opus', version: '3' },
  { regex: /claude-3-sonnet-(\d{8})/i, family: 'Sonnet', version: '3' },
  { regex: /claude-3-haiku-(\d{8})/i, family: 'Haiku', version: '3' },
];

const SYNTHETIC_INDICATORS = ['<synthetic>', 'synthetic', 'system'];

export function parseModelName(raw: string | null): ParsedModel | null {
  if (!raw) return null;

  // Check for synthetic/system models
  if (SYNTHETIC_INDICATORS.some(s => raw.toLowerCase().includes(s))) {
    return {
      family: 'System',
      version: '',
      isOfficialModel: false,
      displayName: 'System',
      fullName: 'System Generated',
    };
  }

  // Try to match known patterns
  for (const pattern of MODEL_PATTERNS) {
    const match = raw.match(pattern.regex);
    if (match) {
      const date = match[1];
      const formattedDate = date ? formatModelDate(date) : undefined;

      return {
        family: pattern.family,
        version: pattern.version,
        date,
        isOfficialModel: true,
        displayName: `${pattern.version} ${pattern.family}`,
        fullName: formattedDate
          ? `Claude ${pattern.version} ${pattern.family} (${formattedDate})`
          : `Claude ${pattern.version} ${pattern.family}`,
      };
    }
  }

  // Fallback: return cleaned-up raw name
  return {
    family: 'Unknown',
    version: '',
    isOfficialModel: false,
    displayName: raw.replace(/^claude-?/i, '').replace(/-/g, ' '),
    fullName: raw,
  };
}

function formatModelDate(dateStr: string): string {
  // "20251101" -> "Nov 2025"
  const year = dateStr.slice(0, 4);
  const month = parseInt(dateStr.slice(4, 6), 10);
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${monthNames[month - 1]} ${year}`;
}
```

### Model Badge Component

```typescript
// apps/web/components/model-badge.tsx

interface ModelBadgeProps {
  modelName: string | null;
  showVersion?: boolean;  // Show date in tooltip
}

export function ModelBadge({ modelName, showVersion = true }: ModelBadgeProps) {
  const parsed = parseModelName(modelName);

  if (!parsed) return null;

  // Hide synthetic/system badges (or show differently)
  if (!parsed.isOfficialModel) {
    return (
      <span className="text-xs text-muted-foreground italic">
        {parsed.displayName}
      </span>
    );
  }

  // Color based on family
  const colorClass = {
    Opus: 'bg-violet-500/20 text-violet-400 border-violet-500/30',
    Sonnet: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    Haiku: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  }[parsed.family] || 'bg-slate-500/20 text-slate-400 border-slate-500/30';

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border',
        colorClass
      )}
      title={showVersion ? parsed.fullName : undefined}
    >
      {parsed.displayName}
    </span>
  );
}
```

---

## Issue 4: Session Header Shows "Session" Instead of Slug

### Current State

```
| Session header title | "Session" | Expected: Slug or formatted UUID |
```

### Solution

```typescript
// apps/web/app/session/[uuid]/layout.tsx

function SessionHeader({ session }: { session: SessionDetail }) {
  // Prefer slug, fall back to truncated UUID
  const displayName = session.slug || `Session ${session.uuid.slice(0, 8)}`;

  return (
    <div>
      <h1 className="text-2xl font-bold">
        {session.slug ? (
          session.slug
        ) : (
          <>
            Session <code className="font-mono text-lg">{session.uuid.slice(0, 8)}</code>
          </>
        )}
      </h1>
      {session.slug && (
        <p className="text-sm text-muted-foreground font-mono">
          {session.uuid}
        </p>
      )}
    </div>
  );
}
```

---

## Issue 5: "0 tokens" Display

### Current State

Header shows "0 tokens" when usage data is unavailable or being loaded.

### Solution

```typescript
// apps/web/lib/format.ts

export function formatTokenCount(count: number | null | undefined): string {
  if (count == null || count === 0) return '--';

  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}K`;
  }
  return count.toLocaleString();
}
```

### Component Usage

```typescript
// Show placeholder instead of 0
const tokenDisplay = formatTokenCount(totalTokens);
const showTokens = tokenDisplay !== '--';

{showTokens && (
  <MetricBadge icon={CpuIcon} label="tokens" value={tokenDisplay} />
)}
```

---

## Issue 6: Timeline Shows +0:00 for All Events

### Current State

All timeline events show `+0:00` elapsed time even when they occur at different times.

### Root Cause

Elapsed time calculation may be using the wrong reference point or timestamps are identical.

### Solution

```typescript
// apps/web/components/timeline-rail.tsx

function formatElapsedTime(eventTime: string, sessionStartTime: string): string {
  const start = new Date(sessionStartTime).getTime();
  const event = new Date(eventTime).getTime();

  const elapsedMs = event - start;

  // Handle edge case: event before session start
  if (elapsedMs < 0) return '+0:00';

  const totalSeconds = Math.floor(elapsedMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `+${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  }
  return `+${minutes}:${seconds.toString().padStart(2, '0')}`;
}

// Use session.start_time as reference, not first event time
const sessionStartTime = session.start_time || events[0]?.timestamp;
```

---

## Implementation Checklist

### New Files

- [ ] `apps/web/lib/content-sanitizer.ts`
- [ ] `apps/web/components/model-badge.tsx`

### Modified Files

- [ ] `apps/web/lib/format.ts` - Add duration/token/model formatters
- [ ] `apps/web/components/session-card.tsx` - Use sanitizer and model badge
- [ ] `apps/web/components/expandable-prompt.tsx` - Use sanitizer
- [ ] `apps/web/components/timeline-rail.tsx` - Use sanitizer, fix elapsed time
- [ ] `apps/web/app/session/[uuid]/layout.tsx` - Fix header display

---

## Verification Steps

1. **Session Cards**: Verify no XML tags visible in initial prompts
2. **System Sessions**: Verify "System session" placeholder appears for command-only sessions
3. **Model Badges**: Verify "4.5 Opus" format instead of "opus-4-5-20251101"
4. **Durations**: Verify no negative durations, edge cases show "< 1s"
5. **Timeline**: Verify elapsed times increment correctly from session start

---

## Dependencies

Phase 1 (Foundation) should be completed first to ensure consistent styling.

---

## Next Phase

Phase 3: Session Cards & Components - enhances the overall card experience with better visual hierarchy and interactivity.
