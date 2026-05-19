# Decision log — Ticket linking UI

Paired companion to `2026-05-18-ticket-linking-ui.md`. Each design iteration
appends one section here with the locked decisions and a one-line rationale.

---

## Iteration 1 — 2026-05-18 (Claude Design)

**Deliverables received:**

- `iterations/2026-05-18/critique-notes.png` — 5-minute audit of current UI (2 keeps, 4 tensions, 1 fix)
- `iterations/2026-05-18/Q1-…` through `Q9b-…` — rendered variants per brief question
- `iterations/2026-05-18/tickets-populated-interactive-v{1,2}.png` — populated `/tickets` screenshots
- `iterations/2026-05-18/ticket-ui-review.html` — shell that would host the React artboards (not standalone; screenshots are the renders)
- A complete drop-in patch under `implementation/` (5 Svelte files + `lib/ticket-helpers.ts` + app.css token diff)

### Locked decisions

| # | Question | Decision | Rationale |
|---|---|---|---|
| Q1 | Provider visual language | **Direction C** — industry-color square with letter-mark (`LIN` / `JIR` / `GH`) | Solves color-blind-only-differentiator problem from current state; no brand logos / new deps; works at 10–13px scales (pill, table, hero); a single token group `--provider-*` |
| Q2 | `/tickets` empty state | **Variant A** — terminal-flavored card teaching all three link paths with inline `<code>` snippets | Worst regression risk is "feature looks off"; the three numbered rows (skill / branch / paste) are self-documenting; matches dashboard's `$ live-sessions` voice |
| Q3 | Ticket detail hierarchy | **V2** — stats-first hero (small ticket card + 4-up stat row: Projects · Sessions · First seen · Metadata) | Lead with the rollup numbers the user actually wants ("what work was done on this thing?"); ticket card stays present but compact |
| Q4 | Link input state system | **Full 5-state machine** — idle / typing / validating / error / success, with rich below-input feedback | Closes the "no real state system" tension; auto-detects provider for URLs and `owner/repo#N`, only shows the dropdown for ambiguous bare keys; idle state teaches `/link` and `feat/...` paths |
| Q5 | Session-page section placement | **Variant A** — full-width strip above ConversationView with terminal-style `$ tickets [N linked]` header | Matches existing dashboard voice (Critique #6); pre-existing position confirmed; just the styling changes |
| Q6 | Unlink button treatment | **C + D combined** — kebab menu (Open / Copy / Unlink) on pill variant, 5-second undo toast inside `SessionTicketsSection` | Calibrated to the action's true cost (reversible); kebab shrinks visual weight; undo toast is local to the section (no global toast slot) |
| Q7 | Status display | **Normalized dot + verbatim label** | `normalizeStatus()` maps each provider's vocabulary to `todo / active / review / done / closed / unknown`; verbatim string preserved next to the colored dot |
| Q9b | Ticket detail → sessions by project | **Variant A** — tabs (All + per-project), conditional on ≥2 projects; "Projects" count in the stats row | Replaces the grouped-headers approach shipped earlier in this branch. Tabs scale better to many projects; "All" stays default; orphans bucket into an "Unindexed" tab last |

### Deferred / not in this patch

| # | Question | Status | Notes |
|---|---|---|---|
| Q8 | Mobile / narrow layout for index | **Deferred** | Index ships with overflow-x today; design didn't address this iteration. Worth a follow-up. |
| Q9a | Project page → tickets surface | **Deferred to next iteration** | Design's README: *"Not in this patch — that's a project-page edit, separate concern."* My `<ProjectTicketsCard>` (shipped earlier in this session) stays as the v1 surface; design will iterate it next round, likely as a tab on the project page. |

### Critique highlights (kept)

From `critique-notes.png`:

- ✅ **Data model shape is clean** — one badge component, three variants, API contract stays
- ✅ **Dark/light token discipline is already there** — no new tokens that aren't already in `app.css`, EXCEPT the new `--provider-*` and `--status-*` groups (additive)

### Net-new tokens this patch introduces

In `:root { … }`:

```css
/* Provider identity */
--provider-linear: #5e6ad2;            --provider-linear-subtle: rgba(94, 106, 210, 0.12);
--provider-jira: #0052cc;              --provider-jira-subtle: rgba(0, 82, 204, 0.10);
--provider-github: #1f2937;            --provider-github-subtle: rgba(31, 41, 55, 0.08);

/* Normalized ticket status */
--status-todo: #94a3b8;
--status-active: #3b82f6;
--status-review: #f59e0b;
--status-done: #10b981;
--status-closed: #64748b;
```

Plus matched dark-mode variants in `:root[data-theme='dark']` (and the `prefers-color-scheme: dark` block).

### Conflicts with code shipped earlier in this session

| File | Status | Action |
|---|---|---|
| `frontend/src/lib/components/tickets/TicketBadge.svelte` | conflict | Replace — design adds provider chip + status dot + kebab menu |
| `frontend/src/lib/components/tickets/TicketLinkInput.svelte` | conflict | Replace — design adds 5-state machine |
| `frontend/src/lib/components/tickets/SessionTicketsSection.svelte` | conflict | Replace — design adds undo toast + terminal header |
| `frontend/src/routes/tickets/+page.svelte` | conflict | Replace — design rebuilds with grid table, segmented filter, terminal empty state |
| `frontend/src/routes/tickets/[provider]/[external_key]/+page.svelte` | conflict | Replace — design's tabs-based Q9b A supersedes my grouped-headers approach |
| `frontend/src/lib/components/tickets/ProjectTicketsCard.svelte` | **keep** | Q9a is deferred — my v1 surface stays |
| `frontend/src/routes/projects/[project_slug]/+page.svelte` | **keep** | Only references `<ProjectTicketsCard>`; no design change yet |
| `frontend/src/app.css` | additive | Append 11 new tokens × 2 (light + dark) |
| `frontend/src/lib/ticket-helpers.ts` | new | Add — shared PROVIDER_META + normalizeStatus + helpers |

### Verification plan (post-application)

- `npm run check` 0 errors
- `npm run lint` no new warnings beyond what existed
- Smoke (from design's README checklist):
  - [ ] Light + dark mode both look right (toggle `html.dark`)
  - [ ] Long ticket title truncates with ellipsis in pill, inline, and table contexts
  - [ ] Missing title renders italic "title not yet fetched"
  - [ ] Missing status renders an em-dash (no dot)
  - [ ] Paste GitHub URL, Linear URL, bare `OCC-1284` (provider dropdown should appear only for the bare key)
  - [ ] Submit a key that 404s on backend → error state renders with API's hint inline
  - [ ] Unlink → 5s undo toast → click Undo → ticket reappears with same `link_id`
  - [ ] Detail page with 1 project (no tabs) vs ≥2 projects (tabs visible)
  - [ ] `mcp__plugin_github_github__issue_read` against #72 returns title used in the populated views
