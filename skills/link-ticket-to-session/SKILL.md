---
name: link-ticket-to-session
description: Link the current Claude Code session to a ticket (Linear, Jira, or GitHub Issues) and cache its title/status in karma. Use when the user explicitly asks to link, attach, associate, or connect this session to a ticket, issue, or PR — e.g. "/link-ticket-to-session ABC-123", "link this session to LINEAR-42", "associate this work with issue #15". Do NOT auto-invoke from passing ticket-key mentions in normal conversation.
argument-hint: <ticket-ref-or-url>
allowed-tools: Bash, mcp__linear, mcp__claude_ai_Linear, mcp__plugin_github_github, mcp__atlassian
---

You are linking the current Claude Code session (`${CLAUDE_SESSION_ID}`) to ticket: **$ARGUMENTS**

Karma is a read-only observer running on the user's machine — it stores
the link and caches metadata, but never writes back to the ticket
provider. You (the agent) supply the title/status via the user's
already-configured MCP server.

Karma's API URL comes from the `KARMA_API_URL` env var (set by users who
run on a non-default port or remote host) and falls back to
`http://localhost:8000`. Inline `${KARMA_API_URL:-http://localhost:8000}`
in **every** curl below — bash variables do not persist across separate
Bash tool calls, so a top-of-script assignment would be empty by the
time the next curl runs.

## Steps

1. **Parse $ARGUMENTS.** It may be a URL or a short ref. Recognized forms:
   - Linear:  `LINEAR-123` or `https://linear.app/.../issue/ABC-123`
   - Jira:    `PROJ-45` or `https://*.atlassian.net/browse/PROJ-45`
   - GitHub:  `owner/repo#42` or `https://github.com/owner/repo/issues/42`
   A bare `#N` is **not** accepted — always qualify with `owner/repo`.

2. **Identify the provider** (`linear` | `jira` | `github`).

3. **Fetch ticket details via the appropriate MCP server**, when available:
   - `linear` → Linear MCP — search/fetch the issue by key
   - `jira` → Atlassian MCP — fetch by key
   - `github` → GitHub MCP — fetch the issue/PR
   Pull at minimum: `title`, `status` (or state), `url`. **Strip large
   fields** like description, comments, and labels arrays — the karma
   cache caps `metadata_json` at 64 KB. If the relevant MCP isn't
   installed, proceed without title/status.

4. **POST the link** (creates the link; does not touch metadata):

   ```bash
   curl -s -X POST "${KARMA_API_URL:-http://localhost:8000}/sessions/${CLAUDE_SESSION_ID}/tickets" \
        -H 'Content-Type: application/json' \
        -d '{"ref":"<key>","provider":"<provider>","url":"<url>","source":"slash_command"}'
   ```

5. **PUT the metadata** (only if you fetched title/status in step 3):

   ```bash
   curl -s -X PUT "${KARMA_API_URL:-http://localhost:8000}/tickets/<provider>/<key>" \
        -H 'Content-Type: application/json' \
        -d '{"title":"<title>","status":"<status>"}'
   ```

   Note: for GitHub keys containing `/` and `#`, URL-encode the key
   (e.g. `octocat/repo#42` → `octocat%2Frepo%2342`).

6. **Confirm to the user** with a one-line summary like:
   `Linked session to LINEAR-123 (Fix login bug) — open at https://linear.app/...`

## Notes

- Karma is loopback-only by default — `http://localhost:8000` is the
  fallback. Set `KARMA_API_URL` to override (custom port, remote host).
- POST is idempotent on (session, ticket); re-running upgrades the
  `link_source` if previously set by branch-detect or dashboard.
- If the API is unreachable, tell the user "karma not running at
  ${KARMA_API_URL:-http://localhost:8000}" so users on custom ports see
  what was tried. Don't silently succeed.
