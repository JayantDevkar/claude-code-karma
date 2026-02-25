# UI/UX Improvement Plan - Phase 5: Navigation & Accessibility

**Priority**: Medium
**Effort**: Medium
**Impact**: High (inclusivity + power user features)

---

## Overview

This phase addresses navigation shortcomings and accessibility gaps identified in the UI/UX review. A command palette provides power users with quick access, while accessibility improvements ensure the dashboard is usable by everyone.

---

## Issue 1: No Command Palette

### Current State

Navigation requires clicking through menus. No keyboard-first navigation option.

### Solution: Command Palette (Cmd+K)

```typescript
// apps/web/components/command-palette.tsx

import { Command } from 'cmdk';

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter();
  const { data: projects } = useProjects();
  const recentSessions = useRecentSessions();

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command Menu"
      className={cn(
        'fixed inset-0 z-50 flex items-start justify-center pt-[20vh]',
        'bg-background/80 backdrop-blur-sm'
      )}
    >
      <div className={cn(
        'w-full max-w-lg rounded-xl border bg-card shadow-2xl overflow-hidden',
        'animate-in fade-in-0 zoom-in-95 duration-200'
      )}>
        {/* Search Input */}
        <div className="flex items-center border-b px-4">
          <SearchIcon className="h-5 w-5 text-muted-foreground shrink-0" />
          <Command.Input
            placeholder="Search projects, sessions, or type a command..."
            className={cn(
              'flex-1 h-14 bg-transparent text-lg outline-none',
              'placeholder:text-muted-foreground'
            )}
          />
          <kbd className="text-xs text-muted-foreground px-2 py-1 rounded bg-secondary">
            Esc
          </kbd>
        </div>

        {/* Results */}
        <Command.List className="max-h-[400px] overflow-y-auto p-2">
          <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
            No results found.
          </Command.Empty>

          {/* Quick Actions */}
          <Command.Group heading="Quick Actions">
            <CommandItem
              icon={HomeIcon}
              label="Go to Dashboard"
              shortcut="⌘H"
              onSelect={() => router.push('/')}
            />
            <CommandItem
              icon={FolderIcon}
              label="View All Projects"
              onSelect={() => router.push('/')}
            />
            <CommandItem
              icon={BarChart3Icon}
              label="Global Analytics"
              onSelect={() => router.push('/analytics')}
            />
          </Command.Group>

          {/* Recent Sessions */}
          {recentSessions.length > 0 && (
            <Command.Group heading="Recent Sessions">
              {recentSessions.slice(0, 5).map(session => (
                <CommandItem
                  key={session.uuid}
                  icon={LayersIcon}
                  label={session.slug || `Session ${session.uuid.slice(0, 8)}`}
                  description={formatRelativeTime(session.start_time)}
                  onSelect={() => router.push(`/session/${session.uuid}`)}
                />
              ))}
            </Command.Group>
          )}

          {/* Projects */}
          {projects && (
            <Command.Group heading="Projects">
              {projects.slice(0, 8).map(project => (
                <CommandItem
                  key={project.encoded_name}
                  icon={project.is_git_repository ? GitBranchIcon : FolderIcon}
                  label={getProjectDisplayName(project.path)}
                  description={`${project.session_count} sessions`}
                  onSelect={() => router.push(`/project/${project.encoded_name}`)}
                />
              ))}
            </Command.Group>
          )}

          {/* Theme Toggle */}
          <Command.Group heading="Preferences">
            <CommandItem
              icon={SunIcon}
              label="Toggle Light Mode"
              onSelect={() => setTheme('light')}
            />
            <CommandItem
              icon={MoonIcon}
              label="Toggle Dark Mode"
              onSelect={() => setTheme('dark')}
            />
          </Command.Group>
        </Command.List>
      </div>
    </Command.Dialog>
  );
}

interface CommandItemProps {
  icon: LucideIcon;
  label: string;
  description?: string;
  shortcut?: string;
  onSelect: () => void;
}

function CommandItem({ icon: Icon, label, description, shortcut, onSelect }: CommandItemProps) {
  return (
    <Command.Item
      onSelect={onSelect}
      className={cn(
        'flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer',
        'text-sm text-foreground',
        'aria-selected:bg-primary/10 aria-selected:text-primary',
        'transition-colors'
      )}
    >
      <Icon className="h-4 w-4 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <p className="truncate">{label}</p>
        {description && (
          <p className="text-xs text-muted-foreground truncate">{description}</p>
        )}
      </div>
      {shortcut && (
        <kbd className="text-xs text-muted-foreground px-1.5 py-0.5 rounded bg-secondary">
          {shortcut}
        </kbd>
      )}
    </Command.Item>
  );
}
```

### Global Keyboard Handler

```typescript
// apps/web/hooks/use-command-palette.ts

export function useCommandPalette() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(prev => !prev);
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return { open, setOpen };
}
```

### Integration in Root Layout

```typescript
// apps/web/app/layout.tsx

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const { open, setOpen } = useCommandPalette();

  return (
    <html lang="en">
      <body>
        {children}
        <CommandPalette open={open} onOpenChange={setOpen} />
      </body>
    </html>
  );
}
```

---

## Issue 2: No Skip-to-Content Link

### Current State

No way to skip navigation for keyboard/screen reader users.

### Solution: Skip Link Component

```typescript
// apps/web/components/skip-link.tsx

export function SkipLink() {
  return (
    <a
      href="#main-content"
      className={cn(
        'sr-only focus:not-sr-only',
        'fixed top-4 left-4 z-[100]',
        'px-4 py-2 rounded-lg',
        'bg-primary text-primary-foreground',
        'focus:outline-none focus:ring-2 focus:ring-ring',
        'transition-transform',
        '-translate-y-16 focus:translate-y-0'
      )}
    >
      Skip to main content
    </a>
  );
}

// Usage in layout:
<body>
  <SkipLink />
  <nav>{/* ... */}</nav>
  <main id="main-content">
    {children}
  </main>
</body>
```

---

## Issue 3: Missing ARIA Labels on Charts

### Current State

```
| Absent | No `aria-label` on chart containers |
| Absent | No `role="img"` with alt text on data visualizations |
```

### Solution: Accessible Chart Wrapper

```typescript
// apps/web/components/accessible-chart.tsx

interface AccessibleChartProps {
  title: string;
  description: string;
  children: React.ReactNode;
}

export function AccessibleChart({ title, description, children }: AccessibleChartProps) {
  const chartId = useId();

  return (
    <figure
      role="img"
      aria-labelledby={`${chartId}-title`}
      aria-describedby={`${chartId}-desc`}
      className="relative"
    >
      {/* Screen reader only description */}
      <figcaption className="sr-only">
        <span id={`${chartId}-title`}>{title}</span>
        <span id={`${chartId}-desc`}>{description}</span>
      </figcaption>

      {/* Visual chart */}
      {children}
    </figure>
  );
}

// Usage:
<AccessibleChart
  title="Token Usage Distribution"
  description="Pie chart showing input tokens at 67% and output tokens at 33%"
>
  <TokenPieChart data={tokenData} />
</AccessibleChart>
```

---

## Issue 4: No Live Region for Filter Updates

### Current State

When filtering timeline events, the count updates silently.

### Solution: ARIA Live Region

```typescript
// apps/web/components/timeline-filter-bar.tsx

export function TimelineFilterBar({ /* ... */ }) {
  const filteredCount = /* calculated */;

  return (
    <div>
      {/* ... filter chips ... */}

      {/* Live region announces filter changes */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {hasActiveFilters
          ? `Showing ${filteredCount} of ${totalEvents} events`
          : `Showing all ${totalEvents} events`
        }
      </div>

      {/* Visual count (non-live) */}
      <span className="text-sm text-muted-foreground tabular-nums">
        {filteredCount} events
      </span>
    </div>
  );
}
```

---

## Issue 5: Focus Management

### Current State

Focus is not managed when navigating between views or opening modals.

### Solution: Focus Management Hooks

```typescript
// apps/web/hooks/use-focus-management.ts

export function useFocusOnMount(ref: RefObject<HTMLElement>) {
  useEffect(() => {
    // Delay to ensure element is rendered
    const timer = setTimeout(() => {
      ref.current?.focus();
    }, 100);

    return () => clearTimeout(timer);
  }, [ref]);
}

export function useTrapFocus(ref: RefObject<HTMLElement>, active: boolean) {
  useEffect(() => {
    if (!active || !ref.current) return;

    const element = ref.current;
    const focusableElements = element.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    }

    element.addEventListener('keydown', handleKeyDown);
    firstElement?.focus();

    return () => element.removeEventListener('keydown', handleKeyDown);
  }, [ref, active]);
}
```

---

## Issue 6: Breadcrumb Navigation Enhancement

### Current State

```
| Breadcrumb pattern: "← Back to projects" / "← Back to project" |
```

Simple back links without full navigation context.

### Solution: Full Breadcrumb Component

```typescript
// apps/web/components/breadcrumb.tsx

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex items-center gap-2 text-sm text-muted-foreground">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;

          return (
            <li key={item.label} className="flex items-center gap-2">
              {index > 0 && (
                <ChevronRightIcon className="h-4 w-4" aria-hidden="true" />
              )}
              {isLast ? (
                <span aria-current="page" className="text-foreground font-medium">
                  {item.label}
                </span>
              ) : (
                <Link
                  href={item.href!}
                  className="hover:text-foreground transition-colors"
                >
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// Usage:
<Breadcrumb items={[
  { label: 'Projects', href: '/' },
  { label: 'claude-karma', href: '/project/...' },
  { label: 'Session abc123' },
]} />
```

---

## Issue 7: Color Contrast Verification

### Current State

Some text combinations may not meet WCAG AA contrast requirements.

### Solution: Contrast Audit & Fixes

```css
/* Ensure muted text has sufficient contrast */
.dark {
  /* Increased from 215 20% 65% to 215 20% 70% */
  --muted-foreground: 215 20% 70%;
}

/* Badge text on colored backgrounds */
.badge-text-on-color {
  /* Use pure white/black for best contrast */
  color: hsl(0 0% 100%);
}
```

### Contrast Testing Script

```bash
# Add to package.json scripts
"test:contrast": "npx @axe-core/cli http://localhost:3000 --tags wcag2aa"
```

---

## Implementation Checklist

### New Files

- [ ] `apps/web/components/command-palette.tsx`
- [ ] `apps/web/components/skip-link.tsx`
- [ ] `apps/web/components/accessible-chart.tsx`
- [ ] `apps/web/components/breadcrumb.tsx`
- [ ] `apps/web/hooks/use-command-palette.ts`
- [ ] `apps/web/hooks/use-focus-management.ts`

### Modified Files

- [ ] `apps/web/app/layout.tsx` - Add command palette, skip link
- [ ] `apps/web/app/globals.css` - Contrast adjustments
- [ ] `apps/web/components/timeline-filter-bar.tsx` - Add live region
- [ ] `apps/web/components/token-chart.tsx` - Wrap with AccessibleChart

### Dependencies

- [ ] Install `cmdk` package: `pnpm add cmdk`

---

## Verification Steps

1. **Command Palette**: Press Cmd+K, verify it opens and searches work
2. **Skip Link**: Tab from page load, verify skip link appears
3. **Screen Reader**: Test with VoiceOver/NVDA on key flows
4. **Keyboard Navigation**: Complete full flow without mouse
5. **Contrast Checker**: Run axe-core audit, no contrast violations

---

## Accessibility Checklist

- [ ] All interactive elements have visible focus states
- [ ] All images/charts have alt text or aria-labels
- [ ] Color is not the only means of conveying information
- [ ] Text contrast meets WCAG AA (4.5:1 for normal, 3:1 for large)
- [ ] Keyboard navigation works for all features
- [ ] Live regions announce dynamic content changes
- [ ] Skip link available for keyboard users

---

## Next Phase

Phase 6: Dashboard Polish & Delight - adds visual polish, micro-animations, and delight features.
