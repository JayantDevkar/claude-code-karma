# Security Policy

## Scope

Claude Code Karma is a **local-only** dashboard that reads Claude Code session data from `~/.claude/` and serves it via a local FastAPI server. It does not expose any public-facing services by default.

Security concerns for this project primarily involve:

- **Local data exposure** — Session transcripts may contain sensitive code, API keys, or credentials that were part of Claude Code conversations
- **CORS configuration** — The API allows cross-origin requests from localhost by default
- **Hook script execution** — Hook scripts run with the user's permissions during Claude Code sessions
- **SQLite database** — Metadata is stored at `~/.claude_karma/metadata.db`

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest on `main` | Yes |
| Older releases | Best effort |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public GitHub issue** for security vulnerabilities
2. **Email:** Open a private security advisory at [GitHub Security Advisories](https://github.com/JayantDevkar/claude-karma/security/advisories/new)
3. **Include:**
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

You can expect an initial response within **72 hours**.

## Security Considerations for Users

### Session Data Privacy

Claude Code Karma reads your Claude Code session transcripts, which may contain:

- Source code from your projects
- API keys or secrets if they appeared in conversations
- File paths and system information
- Tool outputs and error messages

**Recommendations:**

- Run Claude Code Karma only on your local machine
- Do not expose the API (port 8000) or frontend (port 5173) to the public internet
- Review CORS settings if changing the default configuration (`CLAUDE_KARMA_CORS_ORIGINS`)

### Hook Scripts

The hooks in `hooks/` run as subprocesses during Claude Code sessions:

- `live_session_tracker.py` — Writes session state to `~/.claude_karma/live-sessions/`
- `session_title_generator.py` — Reads session data and POSTs titles to the local API

Both scripts only communicate with localhost and the local filesystem. Review them before installing if you have concerns.

### Dependencies

- **API:** Python packages listed in `api/requirements.txt`
- **Frontend:** Node packages listed in `frontend/package.json`

Keep dependencies up to date to avoid known vulnerabilities:

```bash
# Check Python dependencies
cd api && pip audit

# Check Node dependencies
cd frontend && npm audit
```
