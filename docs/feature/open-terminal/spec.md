# Open Terminal — Design & Spec

**Feature:** "Open terminal" button on the live session page
**Modules:** `hooks/`, `api/`, `frontend/`
**Status:** Implemented
**Branch:** `claude/session-terminal-button-c07rql`

---

## Overview

Add a button to the session detail page — shown only for **live** sessions —
that raises (focuses) the terminal window/pane the Claude Code session is
running in.

This is a convenience for users who have Karma open in a browser and want to
jump back to the actual terminal driving a running session.

---

## The core constraint

The literal request — "take me to the terminal window" — **cannot be done by a
browser link alone.** A web page has no ability to focus another application's
OS window.

However, **Claude Code Karma runs locally**: the FastAPI backend runs on the
same machine that owns `~/.claude/` and, therefore, the same machine the
terminals live on. That makes an OS-level approach viable: the browser button
calls the local API, and the API shells out to the platform's window manager to
bring the terminal forward.

Two pieces are required, neither of which existed before this feature:

1. **Capture** which terminal a session runs in (nothing in the pipeline
   recorded this).
2. **Act** on that identity from the API with an OS focus command.

---

## Scope

| Target | Mechanism | Works on |
|--------|-----------|----------|
| tmux | `tmux select-window` / `select-pane` (+ `switch-client`) | any host OS |
| Terminal.app / iTerm2 exact tab | pid → `ps -o tty=` → AppleScript tab match by tty | macOS |
| other macOS terminal apps | `osascript` → `tell application "<app>" to activate` | macOS |
| Linux X11 windows | `xdotool windowactivate` → fallback `wmctrl -i -a` | Linux (X11) |

Everything is **best-effort**: a missing tool or identifier yields a
`focused: false` result with an explanatory `detail`, never an exception.

### Explicit non-goals

- **Wayland** window focus (no reliable, generally-available CLI equivalent to
  `xdotool`/`wmctrl`).
- **Per-tab focus in macOS terminals other than Terminal.app / iTerm2.** For
  those two, the captured `pid` (the live `claude` process) is resolved to its
  tty at click time and AppleScript selects the exact window/tab; other apps
  fall back to activating the *application*. (tmux always selects the exact
  pane.)
- **Remote sessions.** Focus only makes sense when the API and the terminal
  share a machine, which is Karma's normal local deployment.
- ~~Retrofitting existing sessions.~~ Now handled: SessionStart resolves the
  identity fresh, and any other hook event **backfills** it when missing (the
  env and parent pid are identical on every hook invocation), so sessions that
  predate the feature become focusable on their next activity.

---

## Data flow

```
SessionStart hook (terminal env inherited from the user's shell)
    ↓  resolve_terminal()  →  {tmux, tmux_pane, term_program, term_session_id, window_id, pid}
~/.claude_karma/live-sessions/{session_id}.json   ("terminal" object)
    ↓  LiveSessionState.terminal (TerminalInfo)
    ↓  state_to_summary()  →  LiveSessionSummary.terminal + .can_focus_terminal
GET /live-sessions/{id}   (polled client-side by ConversationView)
    ↓  liveStatus.can_focus_terminal
ConversationHeader "terminal" button
    ↓  POST /live-sessions/{id}/focus-terminal
focus_terminal()  →  tmux / osascript / xdotool / wmctrl
```

---

## Captured terminal identity

Resolved once at **SessionStart** from the environment Claude Code inherits from
the user's shell (hooks run with that same environment).

| Field | Source env var | Used for |
|-------|----------------|----------|
| `tmux` | `TMUX` present | flag: session is inside tmux |
| `tmux_pane` | `TMUX_PANE` | tmux pane focus (e.g. `%3`) |
| `term_program` | `TERM_PROGRAM` | macOS app to activate (e.g. `iTerm.app`) |
| `term_session_id` | `TERM_SESSION_ID` | reserved for future per-window focus |
| `window_id` | `WINDOWID` | Linux X11 window activation |
| `pid` | `os.getppid()` | tty lookup for exact-tab focus (this is the `claude` process, **not** the terminal) |

`pid` is the hook's parent — the live `claude` process. While the session is
running (the only time the button shows), `ps -o tty= -p <pid>` yields the tty
of the tab it runs in, which Terminal.app and iTerm2 can select exactly via
AppleScript. If the lookup or tab match fails, focus falls back to activating
the application.

---

## Backend

### Model — `api/models/live_session.py`

- New `TerminalInfo` Pydantic model.
- New `LiveSessionState.terminal: Optional[TerminalInfo]` field (loaded from the
  state file; `extra="allow"` already tolerated the raw dict, now it's typed).

### Schema — `api/schemas.py`

- `TerminalInfo` — mirrors the captured fields.
- `TerminalFocusResult` — `{ focused: bool, method: str, detail: str }`.
- `LiveSessionSummary` gains:
  - `terminal: Optional[TerminalInfo]`
  - `can_focus_terminal: bool` — computed by `services.terminal_focus.can_focus`,
    reflecting whether **the host running the API** has an actionable identifier
    (tmux pane on any OS; `term_program` on macOS; `window_id` on Linux).

### Service — `api/services/terminal_focus.py`

Pure, dependency-light, never-raises. Public API:

- `can_focus(terminal) -> bool`
- `focus_terminal(terminal) -> {focused, method, detail}`

Strategy inside `focus_terminal`: attempt the GUI window focus for the host OS
*and*, if the session is in tmux, select the correct pane. Returns the most
informative result (a successful GUI focus preferred, then successful tmux, then
any attempted result so the caller sees a useful `detail`).

### Endpoint — `api/routers/live_sessions.py`

```
POST /live-sessions/{session_id}/focus-terminal  →  TerminalFocusResult
```

- `404` if the session isn't tracked.
- `400` if no terminal identity was captured (predates the feature / no TTY).
- `200` otherwise, with `focused` indicating whether the raise actually
  succeeded. A known-but-failed method (e.g. `wmctrl` not installed) is a `200`
  with `focused: false`, not an error — the UI surfaces `detail`.

`state_to_summary` threads `terminal` + `can_focus_terminal` into every
`LiveSessionSummary` (list, active, project, and single-session responses).

---

## Frontend

### Types — `frontend/src/lib/api-types.ts`

- `LiveSessionSummary` gains optional `terminal` and `can_focus_terminal`.
- New `TerminalInfo` and `TerminalFocusResult` interfaces.

### UI — `frontend/src/lib/components/conversation/ConversationHeader.svelte`

- A "terminal" action button in the regular-session `headerRight` slot,
  alongside the existing "Copy session ID" / "resume" buttons.
- **Visibility gate:** `liveStatus && liveStatus.status !== 'ended' &&
  liveStatus.can_focus_terminal`.
- On click, `POST`s to the focus endpoint and shows transient feedback
  (`opened!` / `failed`), with the backend's `detail` in the tooltip.
- Data source: the `liveStatus` object already polled by `ConversationView` —
  no extra wiring needed.

Not added to the subagent-session header variant (subagents don't own a
terminal).

---

## Failure modes & messaging

| Situation | HTTP | Body / UI |
|-----------|------|-----------|
| Session not live / not tracked | 404 | button not shown (gate) |
| Live but no terminal captured | 400 | button not shown (`can_focus_terminal=false`) |
| Focus tool missing (e.g. no `wmctrl`) | 200 | `focused:false`, `detail` explains; UI shows `failed` |
| Focus succeeded | 200 | `focused:true`; UI shows `opened!` |
| API unreachable | — | UI shows `failed` + tooltip |

---

## Testing

- `api/tests/test_terminal_focus.py` — unit tests for the service: method
  selection per platform, tmux/macos/linux paths, hex conversion for `wmctrl`,
  missing-tool fallbacks, and the never-raises contract (all subprocess/platform
  calls mocked).
- `api/tests/api/test_live_sessions_terminal.py` — endpoint tests: `terminal` +
  `can_focus_terminal` surfaced on GET; focus success; failure-as-200; `400` for
  no terminal; `404` for unknown session.

Verification: full API suite passes (`pytest`); `frontend` type-checks
(`npm run check`); ruff clean.

---

## Future work

- Per-tab focus for more macOS terminals (WezTerm/kitty/Ghostty expose CLIs
  or scripting that could match by tty like Terminal.app/iTerm2 do today).
- Wayland support if/when a reliable focus CLI is broadly available.
- Expose the button in more surfaces (e.g. the live-sessions list / home page
  cards), reusing the same endpoint.
