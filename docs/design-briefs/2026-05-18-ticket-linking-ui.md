# Design Brief — Ticket Linking UI

**Date:** 2026-05-18
**Branch:** `feat/session-ticket-linking`
**PR:** [#73](https://github.com/JayantDevkar/claude-code-karma/pull/73)
**Tracking issue:** [#72](https://github.com/JayantDevkar/claude-code-karma/issues/72)
**Audience:** Claude Design (`claude.ai/design`)

---

## How to use this brief

Paste this entire document into a fresh claude.ai/design conversation. It is the only context you need. When you reply, please return **two or three rendered variants** (HTML or React in Artifacts) for each numbered question in §7, with rationale and Tailwind class strings I can lift directly.

---

## 1. Problem in one sentence

Claude Code Karma now lets users link a session to one or more tickets (Linear / Jira / GitHub Issues) and view the work-done-per-ticket from karma's dashboard — the underlying UI is functional but visually minimal, and we want a coherent visual system before the feature ships.

## 2. Goals

- A **provider visual language** that distinguishes Linear / Jira / GitHub at a glance without resorting to brand logos or new dependencies
- A **first-time empty state** on `/tickets` that teaches the three link paths (skill, branch-detect, dashboard)
- A **clear information hierarchy** on the ticket detail page
- A **micro-interaction system** for the link input (idle → typing → validating → error → success)
- A **decision about Tickets-section placement** on session detail pages

## 3. In-scope surfaces

All paths relative to the repo root.

| Surface | File | Variants today |
|---|---|---|
| `<TicketBadge>` | `frontend/src/lib/components/tickets/TicketBadge.svelte` | 3 variants: `inline`, `card`, `pill` |
| `<TicketLinkInput>` | `frontend/src/lib/components/tickets/TicketLinkInput.svelte` | Single input + smart provider dropdown |
| `<SessionTicketsSection>` | `frontend/src/lib/components/tickets/SessionTicketsSection.svelte` | Wraps badges + input |
| `/tickets` index page | `frontend/src/routes/tickets/+page.svelte` | Table layout with provider/search filters |
| `/tickets/[provider]/[external_key]` detail page | `frontend/src/routes/tickets/[provider]/[external_key]/+page.svelte` | Card header + linked-sessions list |

## 4. Constraints (must honor)

- **Framework:** SvelteKit 2 + Svelte 5 runes (`$state`, `$derived`, `$props`)
- **Styling:** Tailwind CSS 4 utility classes only; no new CSS-in-JS, no new component libraries
- **Existing primitives:** `bits-ui` for accessible primitives, `lucide-svelte` for icons (no new icon libraries; pick from lucide's ~1k catalog)
- **Design tokens** (CSS custom properties, defined in `frontend/src/app.css`):

  ```css
  /* Backgrounds */
  --bg-base       /* canvas */
  --bg-subtle     /* cards, sections */
  --bg-muted      /* nested inputs, table headers */

  /* Text */
  --text-primary  /* body */
  --text-secondary
  --text-muted
  --text-faint    /* timestamps, hints */

  /* Border */
  --border        /* rgba(0,0,0,0.08) light / rgba(255,255,255,0.08) dark */
  --border-subtle
  --border-hover

  /* Accent (brand violet) */
  --accent: #7c3aed       /* light; auto-flips in dark */
  --accent-hover: #6d28d9
  --accent-subtle: rgba(124,58,237,0.10)
  --accent-muted:  rgba(124,58,237,0.05)
  --accent-rgb: 124, 58, 237

  /* States */
  --error,   --error-subtle,   --error-rgb
  --warning, --warning-subtle, --warning-rgb
  ```

- **Must support light AND dark mode** automatically (CSS custom properties auto-flip via a `.dark` class on `<html>`)
- **Accessibility floor:** WCAG 2.1 AA contrast for all text, visible focus rings on every interactive element, screen reader labels preserved (currently `aria-label="Unlink ticket"` on the X button, `aria-labelledby="tickets-heading"` on the section, etc.)
- **Typography:** Inter (UI), JetBrains Mono (ticket keys and code-shaped tokens)
- **No new dependencies** — package.json should not change
- **Mobile:** the index page table should adapt below `md` breakpoint (today it just overflows-x)

## 5. Real data samples

These are the actual JSON shapes the UI receives. Variants must accommodate all of them, including missing fields and edge cases.

### 5a. `/tickets` index row (`TicketListItem`)

```json
{
  "id": 1,
  "provider": "github",
  "external_key": "JayantDevkar/claude-code-karma#72",
  "url": "https://github.com/JayantDevkar/claude-code-karma/issues/72",
  "title": "feat: session ↔ ticket linking (Linear / Jira / GitHub Issues)",
  "status": "open",
  "first_seen_at": "2026-05-18 23:11:42",
  "metadata_updated_at": "2026-05-18 23:11:42",
  "session_count": 1,
  "last_linked_at": "2026-05-18 23:11:42"
}
```

### 5b. Mixed-provider list (composed for variant exploration)

```json
[
  {
    "id": 1, "provider": "github",
    "external_key": "JayantDevkar/claude-code-karma#72",
    "title": "feat: session ↔ ticket linking (Linear / Jira / GitHub Issues)",
    "status": "open", "session_count": 1, "last_linked_at": "2026-05-18 23:11:42",
    "url": "https://github.com/JayantDevkar/claude-code-karma/issues/72"
  },
  {
    "id": 2, "provider": "linear",
    "external_key": "OCC-1284",
    "title": "Investigate flaky Airflow DAG on prod",
    "status": "In Progress", "session_count": 4, "last_linked_at": "2026-05-18 18:22:00",
    "url": "https://linear.app/occuspace/issue/OCC-1284"
  },
  {
    "id": 3, "provider": "jira",
    "external_key": "DATA-1027",
    "title": "Add quarterly export endpoint",
    "status": "Triage", "session_count": 12, "last_linked_at": "2026-05-17 09:14:55",
    "url": "https://occuspace.atlassian.net/browse/DATA-1027"
  },
  {
    "id": 4, "provider": "linear",
    "external_key": "PLAT-99",
    "title": null,
    "status": null, "session_count": 1, "last_linked_at": "2026-05-18 11:02:00",
    "url": "https://linear.app/search?q=PLAT-99"
  }
]
```

### 5c. `/sessions/{uuid}/tickets` row (`SessionTicketRow` — ticket + link inline)

```json
{
  "id": 1,
  "provider": "github",
  "external_key": "JayantDevkar/claude-code-karma#72",
  "url": "https://github.com/JayantDevkar/claude-code-karma/issues/72",
  "title": "feat: session ↔ ticket linking (Linear / Jira / GitHub Issues)",
  "status": "open",
  "metadata_json": null,
  "metadata_updated_at": "2026-05-18 23:11:42",
  "first_seen_at": "2026-05-18 23:11:42",
  "link_id": 1,
  "link_source": "slash_command",
  "linked_at": "2026-05-18 23:11:42",
  "session_slug": null
}
```

### 5d. `/tickets/{provider}/{external_key}/sessions` row (ticket detail — sessions list)

```json
[
  {
    "link_id": 1,
    "session_uuid": "48e228d6-a543-4172-8b6d-0146dd65ef82",
    "session_slug": "happy-pioneer",
    "link_source": "slash_command",
    "linked_at": "2026-05-18 23:11:42",
    "sessions_slug": "happy-pioneer",
    "project_encoded_name": "-Users-jayantdevkar-Documents-GitHub-claude-karma",
    "start_time": "2026-05-18 22:36:00",
    "end_time": null,
    "initial_prompt": "review the work done so far and what needs to be tested + cleaned before we can ship/merge it..."
  },
  {
    "link_id": 7,
    "session_uuid": "0913a1f0-ffff-0000-0000-aaaaaaaaaaaa",
    "session_slug": null,
    "link_source": "branch",
    "linked_at": "2026-05-16 09:00:00",
    "sessions_slug": null,
    "project_encoded_name": null,
    "start_time": null,
    "end_time": null,
    "initial_prompt": null
  }
]
```

### 5e. Edge cases the variants must handle

- **Long title** — 200+ chars, must truncate gracefully (today: `max-w-[24ch] truncate`)
- **Missing title and/or status** — branch-detect links and pre-MCP-fetch state both produce `title=null, status=null`. Provider key + URL are always present.
- **Orphan link** — `sessions_slug = null, project_encoded_name = null, start_time = null` — the linked session isn't in the index yet (e.g., branch-detect fired pre-index)
- **High session count** — `session_count: 12` for one ticket. The detail page should scale to dozens.
- **All-providers mixed** — list views must visually distinguish three providers without color-blind-hostile choices

## 6. Provider key shapes (visual treatment must accommodate)

| Provider | Shape | Example |
|---|---|---|
| `linear` | `[A-Z]+-\d+` | `LINEAR-123`, `OCC-1284` |
| `jira` | `[A-Z]+-\d+` (visually identical to linear) | `PROJ-45`, `DATA-1027` |
| `github` | `owner/repo#N` (contains `/` and `#`) | `JayantDevkar/claude-code-karma#72` |

Note that Linear and Jira keys are visually indistinguishable — the only differentiator is the provider treatment we apply.

## 7. Open questions — what we want design's opinion on

Please return 2–3 variants for each.

1. **Provider visual language**
   What's the coherent system across Linear / Jira / GitHub? Color treatment, icon/glyph, position, weight? The constraint is no brand logos and no new dependencies. Today: one inline color token per provider (`text-[var(--accent)]` for linear, `text-[#0052cc]` for jira, `text-[var(--text-primary)]` for github) — basically arbitrary. We want better. Should the system work color-blind?

2. **`/tickets` index empty state**
   When the user has no tickets linked yet, the index shows `"No tickets linked yet. Open a session and paste a ticket URL to link your first one."` It's flat. Three link paths exist (skill, branch-detect, dashboard) — the empty state could teach them. How should this onboard the first-time user?

3. **Ticket detail hierarchy**
   What's the focal point on `/tickets/[provider]/[external_key]`? Today: card with provider + key + click-through, then a list of sessions. Should the title be the largest element? Should the status be a prominent pill? Should the linked-sessions count be a callout? Where should "View on Linear/Jira/GitHub →" sit?

4. **`<TicketLinkInput>` micro-interactions**
   Today the input has: placeholder text, optional provider dropdown that appears when the input is a bare key, submit button with spinner, error message below on 400. The states are: **idle / typing / validating / error / success**. Design these as a system — focus ring, transitions, error treatment, what happens visually when the link succeeds.

5. **Session-page Tickets section**
   Today this section sits **above** `<ConversationView>` in the page flow. Is that the right position? Should it be **collapsible** (expanded by default if there are links, collapsed if empty)? **Pinned to the side** instead of full-width? **Inside a tab** of ConversationView? The signal-to-noise vs. discoverability tradeoff is the question.

6. **Unlink (X) button on pills**
   Today: small `X` icon in `text-[var(--text-muted)]`, hovers to `text-[var(--error)]`. Is that visual weight right for a destructive action that's reversible (you can always re-link)? Should it require a hover-to-reveal? A confirmation step? Or is the current treatment correct?

7. **Status display**
   Each provider returns its own native status strings: GitHub → `"open"`, `"closed"`; Linear → `"Backlog"`, `"In Progress"`, `"In Review"`, `"Done"`, `"Canceled"`; Jira → `"To Do"`, `"In Progress"`, `"Triage"`, `"Done"`, etc. Should we render them verbatim (today's behavior), normalize to a small set with mapping (e.g., `todo / active / review / done / closed`), or apply color/shape without normalizing the text?

8. **Mobile / narrow layout for `/tickets` index**
   The table overflows-x today. At what breakpoint should it switch to a card list? What does the mobile card look like — what fields stay, what go?

## 8. Non-goals (don't redesign these)

- The global header / navigation (Tickets link is already there)
- Route structure (`/tickets`, `/tickets/[provider]/[external_key]`, `/projects/[project_slug]/[session_slug]`)
- The data model or API contracts (those are locked by schema v11)
- Provider brand assets (no new logos, no SVG icons of Linear/Jira/GitHub marks — we want a tokens-only treatment)
- Animation libraries (use Tailwind transitions only — `transition-colors`, `transition-opacity`, `duration-150`, `ease-out`, etc.)
- The skill / hook / config sides — those are headless

## 9. Current state (text walkthrough — replace with screenshots when possible)

If you have the ability to render the existing components in an Artifact for reference, the component sources are:

- [`TicketBadge.svelte`](https://github.com/JayantDevkar/claude-code-karma/blob/feat/session-ticket-linking/frontend/src/lib/components/tickets/TicketBadge.svelte)
- [`TicketLinkInput.svelte`](https://github.com/JayantDevkar/claude-code-karma/blob/feat/session-ticket-linking/frontend/src/lib/components/tickets/TicketLinkInput.svelte)
- [`SessionTicketsSection.svelte`](https://github.com/JayantDevkar/claude-code-karma/blob/feat/session-ticket-linking/frontend/src/lib/components/tickets/SessionTicketsSection.svelte)
- [`/tickets/+page.svelte`](https://github.com/JayantDevkar/claude-code-karma/blob/feat/session-ticket-linking/frontend/src/routes/tickets/+page.svelte)
- [`/tickets/[provider]/[external_key]/+page.svelte`](https://github.com/JayantDevkar/claude-code-karma/blob/feat/session-ticket-linking/frontend/src/routes/tickets/[provider]/[external_key]/+page.svelte)

Verbal description of each surface today:

- **`<TicketBadge variant="pill">`** — rounded-full chip, ~20px high, monospace key + optional title (truncated at ~18ch), tiny external-link icon, optional X to unlink. Provider color is the only differentiator.
- **`<TicketBadge variant="inline">`** — used inside table cells; small provider label chip + monospace key + en-dash + title. No background.
- **`<TicketBadge variant="card">`** — header on detail page; provider label chip + monospace key + external-link icon + title on a second line + status on a third line. Sits in a `bg-subtle` card.
- **`<TicketLinkInput>`** — single-row input with placeholder `Paste URL or ref (e.g. LINEAR-123, owner/repo#42)`, conditional provider dropdown to the right of the input (only when input is bare alphanumeric), violet "Link" submit button with `+` icon. Errors render below in `--error` color.
- **`<SessionTicketsSection>`** — section card with title row (icon + "TICKETS" + count), wrapped list of pills, then the input below. Sits above `<ConversationView>` on session pages.
- **`/tickets` index** — full-width table inside max-w-6xl container. Columns: Ticket / Title / Status / Sessions (right-aligned) / Last linked.
- **`/tickets/[provider]/[external_key]`** — back link, card-variant badge, metadata line, then "LINKED SESSIONS (N)" heading and a list of cards (one per linked session).

## 10. Deliverables format I want back

For each question in §7:

1. **2–3 rendered variants** (HTML in an Artifact is fine)
2. **One-paragraph rationale per variant** — what it optimizes for, what it trades away
3. **Tailwind class strings** I can lift directly into the Svelte components (so I don't have to reverse-engineer your visuals)
4. **Tokens used** explicitly named from the §4 list — so I don't have to guess whether you meant `--bg-subtle` or `--bg-muted`
5. **Dark-mode parity** — at least one variant per question shown in dark mode, even if it's the same structure with token names swapped

For cross-cutting decisions (provider language, micro-interaction system) please also produce a **system spec page** — a single artifact showing all three providers / all five input states side-by-side so I can implement them coherently.

## 11. What I will return to you after implementing

Per the §3 contract for "Implementation Diff":

- Branch / PR URL with the changes
- Real screenshots: `/tickets` populated (1 row, 4 rows, 20+ rows), empty state, mobile breakpoint, session detail with section expanded
- Any place reality diverged from the mock and why (real data was longer, accessibility required a label, performance argued against an animation, etc.)

Then I'll ask you for a critique (severity-ranked), polish, ship.

## 12. Decision log

This brief will be paired with `docs/design-briefs/2026-05-18-ticket-linking-ui-log.md` (created lazily as decisions land). Each loop appends one section with date, what was decided, and rationale.
