---
description: Link the current Claude Code session to a ticket and cache its title/status in karma
argument-hint: <ticket-ref-or-url>
---

You are linking the current Claude Code session (`${CLAUDE_SESSION_ID}`) to ticket: **$ARGUMENTS**

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
   curl -s -X POST "http://localhost:8000/sessions/${CLAUDE_SESSION_ID}/tickets" \
        -H 'Content-Type: application/json' \
        -d '{"ref":"<key>","provider":"<provider>","url":"<url>","source":"slash_command"}'
   ```

5. **PUT the metadata** (only if you fetched title/status in step 3):

   ```bash
   curl -s -X PUT "http://localhost:8000/tickets/<provider>/<key>" \
        -H 'Content-Type: application/json' \
        -d '{"title":"<title>","status":"<status>"}'
   ```

   Note: for GitHub keys containing `/` and `#`, URL-encode the key
   (e.g. `octocat/repo#42` → `octocat%2Frepo%2342`).

6. **Confirm to the user** with a one-line summary like:
   `Linked session to LINEAR-123 (Fix login bug) — open at https://linear.app/...`

## Notes

- Karma is loopback-only — `http://localhost:8000` is the karma API.
- POST is idempotent on (session, ticket); re-running upgrades the
  link_source if previously set by branch-detect or dashboard.
- If the API is unreachable, tell the user "karma not running" — don't
  silently succeed.
