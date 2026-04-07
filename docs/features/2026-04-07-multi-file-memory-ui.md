# Feature Definition: Multi-File Project Memory UI

**Status:** Design approved, pending implementation plan
**Owner:** Jayant
**Related:** `frontend/src/lib/components/memory/MemoryViewer.svelte`, `api/routers/projects.py`, `api/schemas.py`

## Section 1: Context & Motivation

Claude Code's auto-memory system has evolved from a single `MEMORY.md` file into a directory of related markdown files: one index (`MEMORY.md`) plus many topical children (e.g. `syncthing-sync-architecture.md`, `project_git_radio.md`). Each child has YAML frontmatter describing `name`, `description`, and `type` (one of `user | feedback | project | reference`). `MEMORY.md` is itself a narrative index that references children via standard markdown links: `- [Title](file.md) — one-line hook`.

The current Claude Karma UI was built for the single-file era. It reads only `memory/MEMORY.md` and renders it as a single markdown blob in `MemoryViewer.svelte`. The consequence:

- All of the user's topical memory files (4+ in the working example) are invisible in the dashboard.
- Index links render as broken `file.md` URLs the browser cannot resolve.
- Users have no way to inspect individual memories, see their types, or browse what Claude has remembered.

This feature reworks the memory view to embrace the new multi-file model while preserving the **reader-first** experience: the index narrative remains the centerpiece, and children are accessed contextually rather than as a separate navigation surface.

### User-facing goal

A user lands on a project's memory tab and sees the `MEMORY.md` index rendered cleanly. Links within the index now behave as first-class in-app references: hovering any link reveals a small popover with the linked file's type, description, word count, and last-modified time; clicking opens the full file in a side panel without leaving the index.

## Section 2: Scope & Sub-Features

### Sub-Features

1. **Backend enumeration** — Parse all `*.md` files in `~/.claude/projects/{encoded_name}/memory/`, extract YAML frontmatter, compute which files are referenced from the index.
2. **Backend per-file fetch** — Serve individual child file contents on demand with basename-only path validation.
3. **Index rewriting** — Post-process the rendered MEMORY.md DOM to convert `[text](file.md)` anchors into in-app interactive elements.
4. **Hover previews** — Show a Wikipedia-style popover with file metadata when the user hovers a rewritten link.
5. **Side panel reading** — Slide-in right drawer displaying the full content of a clicked memory file.
6. **Orphan file display** — A collapsible "Other memory files" section listing files in the directory that `MEMORY.md` does not reference, with the same hover/click behavior.
7. **Backwards compatibility** — Projects with only a single `MEMORY.md` (no children) render identically to today.

### Not In Scope (v1)

- Editing, creating, or deleting memory files from the UI.
- Full-text search across memory files.
- Type-based filtering tabs (all / user / feedback / project / reference).
- "Open in editor" or "copy file path" affordances inside the panel.
- Stale-memory detection or health warnings.
- Syncing memory state across devices (handled by the sync-v4 pipeline at the filesystem level).

## Section 3: Actors & Roles

| Actor | Capabilities | Restrictions |
|-------|--------------|--------------|
| Dashboard viewer | Read project memory index, hover links for previews, open any child file in a side panel, browse orphan files. | Read-only. No mutation, no search, no cross-project navigation from this view. |

## Section 4: Data Model

### On-disk layout (unchanged, consumed as-is)

```
~/.claude/projects/{encoded_name}/memory/
├── MEMORY.md                           # Index; plain markdown, no frontmatter
├── syncthing-sync-architecture.md      # Child; frontmatter + body
├── project_git_radio.md
└── ...
```

### Child file frontmatter (authored by Claude per the auto-memory spec)

```markdown
---
name: Syncthing v2 architecture
description: Folder IDs, member_tag format, reconciliation pipeline
type: project
---

# Body content here...
```

Frontmatter fields:
- `name` — human-readable title. Fallback: filename without extension, underscores replaced with spaces.
- `description` — one-line hook. Fallback: empty string.
- `type` — one of `user | feedback | project | reference`. Fallback: `null`.

The YAML block is optional. Legacy files without frontmatter must still render.

## Section 5: API Changes

### Endpoint 1 (upgraded): `GET /projects/{encoded_name}/memory`

Returns the index file plus metadata (no content) for every other `*.md` file in `memory/`.

**Response schema (`ProjectMemoryResponse` — breaking change):**

```jsonc
{
  "index": {
    "content": "string",         // full MEMORY.md body
    "word_count": 0,
    "size_bytes": 0,
    "modified": "2026-04-07T00:00:00Z",
    "exists": true
  },
  "files": [                     // [] when no children exist
    {
      "filename": "syncthing-sync-architecture.md",
      "name": "Syncthing v2 architecture",
      "description": "Folder IDs, member_tag format, reconciliation pipeline",
      "type": "project",         // string | null
      "word_count": 4812,
      "size_bytes": 28630,
      "modified": "2026-03-13T22:34:00Z",
      "linked_from_index": true
    }
  ]
}
```

Backend logic:
1. List `memory/*.md`.
2. If `MEMORY.md` is absent → return `{ index: { exists: false, ... }, files: [] }`.
3. For each non-index file: read → parse frontmatter → stat → compute `word_count`.
4. Parse `MEMORY.md` for markdown link targets matching `*.md`. For each child file, set `linked_from_index = filename in index_link_targets`.
5. Frontmatter parser: accept `---\n...yaml...\n---` prefix; on any parse error, treat the file as having no frontmatter (do not fail the whole response).
6. Response is cached via the existing `@cacheable(max_age=30, stale_while_revalidate=60)` decorator.

### Endpoint 2 (new): `GET /projects/{encoded_name}/memory/files/{filename}`

Returns one child file's full content. Path component `files/` in the URL disambiguates from the index route and avoids a trailing-segment collision.

**Path validation (security-critical):**
- `filename` must match `^[a-zA-Z0-9._-]+\.md$` (basename only, `.md` required).
- Reject anything containing `/`, `\`, `..`, leading `.`, or null bytes.
- After validation, resolve to `memory_dir / filename` and assert the resolved absolute path is still inside `memory_dir` (defense in depth against symlink escapes).
- 404 on not-found, 400 on invalid filename, 403 on path escape.

**Response schema (`ProjectMemoryFileResponse`):**

```jsonc
{
  "filename": "syncthing-sync-architecture.md",
  "name": "Syncthing v2 architecture",
  "description": "Folder IDs, member_tag format...",
  "type": "project",
  "content": "string",           // body only; frontmatter stripped
  "word_count": 4812,
  "size_bytes": 28630,
  "modified": "2026-03-13T22:34:00Z"
}
```

### New Pydantic schemas (`api/schemas.py`)

- `MemoryFileMeta` — one entry in the `files[]` array of the index response.
- `MemoryIndexEntry` — the `index` object on the list response (same fields as the legacy `ProjectMemoryResponse`).
- `ProjectMemoryResponse` (replaced) — `{ index: MemoryIndexEntry, files: list[MemoryFileMeta] }`.
- `ProjectMemoryFileResponse` — per-file detail response.

## Section 6: Frontend Changes

### Component tree (new files)

```
frontend/src/lib/components/memory/
├── MemoryViewer.svelte           # shell, refactored — orchestrates everything below
├── MemoryIndex.svelte             # renders MEMORY.md with rewritten links (NEW)
├── MemoryHoverCard.svelte         # bits-ui Popover wrapper (NEW)
├── MemoryFilePanel.svelte         # bits-ui Dialog (sheet variant) for reading (NEW)
└── MemoryOrphanList.svelte        # collapsible "Other memory files" section (NEW)
```

Plus one Svelte action:

```
frontend/src/lib/actions/rewriteMemoryLinks.ts   # DOM post-processor
```

### Component responsibilities

**`MemoryViewer.svelte` (shell — existing file, rewritten)**
- Fetches `/projects/{encoded_name}/memory` on mount via `$effect`.
- State: `loading`, `error`, `indexPayload`, `files`, `selectedFilename`, `hoveredFilename`, `hoverAnchorRect`.
- Renders empty state (no `MEMORY.md` and no children), error state, or the layout.
- Layout: `MemoryIndex` with header card (reused from current UI), then `MemoryOrphanList` below, then `MemoryFilePanel` as an overlay.

**`MemoryIndex.svelte`**
- Props: `content: string`, `files: MemoryFileMeta[]`, `onLinkHover(filename, rect)`, `onLinkLeave()`, `onLinkSelect(filename)`.
- Renders markdown via the existing `marked` + `DOMPurify` pipeline.
- Applies the `rewriteMemoryLinks` action to the container div.
- The action walks all `<a>` elements, checks if `href` ends in `.md`, and if the basename matches a known filename in `files`, marks the anchor with `data-memory-file="..."` and attaches hover/leave/click listeners that call the prop callbacks.
- Unknown `.md` links (pointing to files not in `files`) get a muted visual treatment (dashed underline, tooltip "file not found") but remain non-interactive.

**`MemoryHoverCard.svelte`**
- Props: `file: MemoryFileMeta | null`, `anchorRect: DOMRect | null`.
- Wraps `bits-ui` `Popover.Root` / `Popover.Content` with manual open control driven by `file !== null`.
- Positioned via `anchorRect` using a virtual reference element (bits-ui supports this).
- Shows: name, type badge (color-coded per type), description, word count, relative modified time.
- 150ms open delay handled in the shell before setting `hoveredFilename` (prevents flicker on casual mouse movement).

**`MemoryFilePanel.svelte`**
- Props: `filename: string | null`, `projectEncodedName: string`, `onClose()`.
- Wraps `bits-ui` `Dialog.Root` configured as a right-side sheet (560px desktop / full-width mobile).
- `$effect` on `filename` triggers a fetch to `/projects/{encoded_name}/memory/files/{filename}`.
- Internal state: `loading`, `error`, `fileData: ProjectMemoryFileResponse | null`, `renderedContent`.
- Layout: sticky header (type badge, file name, modified relative time, close button) + scrollable body (rendered markdown reusing the same pipeline and the existing `markdownCopyButtons` action).
- Swapping filenames while open: fetches new content, replaces the body, keeps the panel open (no animation flicker).
- Closes on Esc or click-outside (bits-ui default behavior).

**`MemoryOrphanList.svelte`**
- Props: `files: MemoryFileMeta[]`, same hover/click callbacks as `MemoryIndex`.
- Only renders if `files.length > 0`.
- Collapsible section header: icon + "Other memory files (N)" + chevron.
- Collapsed by default; remembers expanded state via URL search param `?orphans=open` for shareable links.
- Each row: type badge, name, description preview (truncated), modified relative time, word count.

**`rewriteMemoryLinks` Svelte action (`frontend/src/lib/actions/rewriteMemoryLinks.ts`)**
- Signature: `rewriteMemoryLinks(node: HTMLElement, params: { files: MemoryFileMeta[], onHover, onLeave, onSelect })`.
- On mount and on content change (via `update`): query `node.querySelectorAll('a[href$=".md"]')`, classify each, attach listeners.
- On destroy: remove all listeners it attached.
- Stores listener references on a `WeakMap` so re-runs don't leak.

### TypeScript interfaces (`frontend/src/lib/api-types.ts`)

- Replace `ProjectMemory` with:
  - `MemoryFileMeta` — mirrors the backend schema.
  - `ProjectMemoryIndexEntry` — the `index` field.
  - `ProjectMemory` — `{ index: ProjectMemoryIndexEntry, files: MemoryFileMeta[] }`.
  - `ProjectMemoryFile` — per-file response.

### Integration point

`frontend/src/routes/projects/[project_slug]/+page.svelte:1725` continues to render `<MemoryViewer projectEncodedName={project.encoded_name} />`. No route or page changes.

## Section 7: UX Details

### Rewritten link styling

In-app links (those resolving to a known child file) are styled distinctly from regular markdown links so the user understands they're interactive previews, not navigations:

- Accent-colored underline, 1px.
- Subtle chevron icon (⤴ or Lucide `arrow-up-right`) appended after the text, half-opacity.
- Cursor: pointer.
- Hover: 100% opacity chevron + slight background tint.
- Broken links (`.md` hrefs not in `files[]`): dashed muted underline, `title` attribute "file not found in memory directory", cursor default.

### Type badges

Small pill badges with semantic colors (used in hover card, file panel header, and orphan list rows):

| Type | Color (CSS var) | Label |
|------|-----------------|-------|
| `user` | `--accent-blue` | User |
| `feedback` | `--accent-amber` | Feedback |
| `project` | `--accent-violet` | Project |
| `reference` | `--accent-emerald` | Reference |
| `null` | `--text-muted` | — |

Colors reuse existing design tokens where possible; new tokens added to `app.css` only if a needed color is missing.

### Hover card

- Width: 320px max, auto height.
- Border: 1px `--border`, background `--bg-subtle`, shadow `--shadow-lg`.
- Content order: type badge (top-left) + modified relative time (top-right) → name (semibold) → description (muted, truncated to 3 lines) → footer row with word count.
- Position: below the anchor by default; flips above if it would overflow the viewport (bits-ui handles this).
- Delay: 150ms on show, instant on hide.

### Side panel

- Slide-in from right, 300ms cubic-bezier ease-out.
- Dim overlay at 40% opacity over the rest of the page.
- Width: 560px desktop, 100vw mobile.
- Sticky header within the panel (remains visible as body scrolls).
- Content uses the same `markdown-preview` + `prose` classes as the index for consistent typography.
- Opening a different file while panel is open: header and body fade out briefly, new content fades in; no full re-open animation.

### Orphan list

- Collapsed by default; shows count in header: "Other memory files (3)".
- Visual weight intentionally low — orphans are either leftovers or new files Claude hasn't woven into the index yet.

## Section 8: Error Handling

| Condition | Backend response | Frontend treatment |
|-----------|------------------|--------------------|
| No `memory/` directory | `{ index: { exists: false, ... }, files: [] }` | Existing "No Project Memory Yet" empty state. |
| `memory/` exists but `MEMORY.md` missing, children present | `{ index: { exists: false, ... }, files: [...] }` | Render a synthetic header "Orphan memory files" and show only `MemoryOrphanList` with children. |
| `MEMORY.md` exists, no children | `{ index: {...}, files: [] }` | Render index only. Identical to current UI (backwards compat). |
| Malformed YAML frontmatter in a child | File still listed; `name`=filename-derived, `description`=``, `type`=null. | Rendered normally; type badge shows as `—`. |
| Individual file fetch fails (network, 500) | n/a | Panel shows inline error with "Retry" button; panel does not close automatically. |
| Individual file not found (404) | 404 | Panel shows "This memory file no longer exists" message; closes on user dismissal. |
| Invalid filename parameter | 400 with clear message | Panel shows "Invalid memory file" error; logs to console; surfaces as toast if toast system exists. |
| Path escape attempt | 403 | Same as 400 treatment; logged server-side. |

## Section 9: Backwards Compatibility

- Any project with only `MEMORY.md` and no children returns `files: []`. The UI renders an index-only view that matches the current experience (same card, same markdown rendering, same empty state for missing memory).
- Old URLs linking to the project page remain valid; no route changes.
- The `ProjectMemoryResponse` schema is a **breaking change** on the wire, but the API is consumed only by our frontend, and both land in the same commit. No external API contract concern.

## Section 10: Testing Strategy

### Backend (`api/tests/`)

- `test_memory_router.py` (new file):
  - Fixture: temp `memory/` dirs with various shapes (no dir, only index, index+children, children without index, malformed frontmatter, orphan files, non-.md files to ignore).
  - Endpoint tests for both `/memory` and `/memory/files/{filename}`.
  - Security: path traversal (`../etc/passwd`, `foo/bar.md`, `.hidden.md`, empty, non-`.md`, null byte) must all return 400/403.
  - Frontmatter parsing: valid YAML, malformed YAML, missing fields, unknown fields, empty frontmatter block.
  - `linked_from_index` computation: matches exact filename, ignores fragment/query, doesn't match false positives.

### Frontend (`frontend/src/lib/components/memory/__tests__/`)

- `MemoryViewer.test.ts` — mount with mocked fetch, assert loading → loaded → empty states; assert panel opens on link click.
- `rewriteMemoryLinks.test.ts` — action unit test with a DOM fixture; assert link rewriting and listener attach/detach.
- `MemoryHoverCard.test.ts` — snapshot for rendered popover content per file type.
- `MemoryFilePanel.test.ts` — fetches on filename change, handles loading/error states, swaps content when filename changes while open.

### Manual QA checklist

- [ ] Visit project with multi-file memory → index renders, links visible.
- [ ] Hover a link → popover appears after 150ms with correct metadata.
- [ ] Click a link → panel opens, full content loads, markdown renders.
- [ ] Click a different link while panel is open → content swaps.
- [ ] Esc closes panel; click-outside closes panel.
- [ ] Click an orphan file row → panel opens.
- [ ] Visit project with only MEMORY.md → renders exactly as before.
- [ ] Visit project with no memory → empty state unchanged.
- [ ] Visit project with malformed frontmatter in one child → other files unaffected.
- [ ] Mobile viewport: panel goes full-width, hover becomes tap-to-preview (or simply opens panel directly on tap — hover interactions on touch are a known limitation; acceptable for v1).

## Section 11: Open Questions

None remaining for v1. Items explicitly deferred to v2:
- Search across memory files.
- Type-based filtering.
- Edit-in-place or "open in editor" integration.
- Stale-memory detection (files older than N days without references).

## Section 12: Success Criteria

A user with a populated multi-file memory directory loads the project memory tab and can:
1. See the index narrative rendered with visually distinct in-app links.
2. Hover any link to preview the target file's metadata without opening it.
3. Click any link to read the full file in a side panel without losing the index position.
4. See orphan files in a dedicated section and read them the same way.
5. Return to the default (only-index) experience when the project has no child files.

The implementation must not regress the existing empty-state, single-file, or loading-state rendering.
