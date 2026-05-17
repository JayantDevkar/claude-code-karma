"""
Pure URL/ref parser for ticket links.

No I/O, no git shell-outs. Resolving things like a bare `#N` to
`owner/repo#N` must be done by the caller (slash command from shell, hook
from git, dashboard via input form). The API server has no notion of
caller cwd, so this module never reaches outside its arguments.

See: docs/superpowers/specs/2026-05-13-session-ticket-linking-design.md
"""

from __future__ import annotations

import re
from typing import Optional

from models.ticket import Provider, TicketRef

# Linear: https://linear.app/<team>/issue/<KEY>[/...]
_LINEAR_URL = re.compile(
    r"^https?://linear\.app/[^/]+/issue/(?P<key>[A-Z][A-Z0-9_]+-\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)

# Jira Cloud: https://<host>.atlassian.net/browse/<KEY>
_JIRA_URL = re.compile(
    r"^https?://[^/]+\.atlassian\.net/browse/(?P<key>[A-Z][A-Z0-9_]+-\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)

# GitHub: https://github.com/<owner>/<repo>/issues/<N>  (or /pull/<N>)
_GITHUB_URL = re.compile(
    r"^https?://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/(?:issues|pull)/(?P<num>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)

# GitHub short ref: owner/repo#N
_GITHUB_SHORT = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)#(?P<num>\d+)$")

# Bare alphanumeric key: ABC-123 (Linear or Jira; ambiguous without hint).
# Case-insensitive to match URL parsing; we normalize to upper at output.
_BARE_KEY = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]+-\d+)$", re.IGNORECASE)


def parse_ticket_ref(s: str, hint_provider: Optional[Provider] = None) -> Optional[TicketRef]:
    """Parse a ticket reference into provider + external_key + canonical URL.

    Recognized inputs:
      - Linear URL    https://linear.app/<team>/issue/ABC-123
      - Jira URL      https://*.atlassian.net/browse/ABC-123
      - GitHub URL    https://github.com/<owner>/<repo>/issues/N (or /pull/N)
      - GitHub short  owner/repo#N
      - Bare key      ABC-123  (requires hint_provider='linear' or 'jira')

    Returns None for unrecognized input. A bare `#N` (no owner/repo) is
    explicitly unsupported: callers must qualify GitHub refs themselves
    because the API server cannot read the caller's git remote.
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None

    m = _LINEAR_URL.match(s)
    if m:
        key = m.group("key").upper()
        return TicketRef(provider="linear", external_key=key, url=s)

    m = _JIRA_URL.match(s)
    if m:
        key = m.group("key").upper()
        return TicketRef(provider="jira", external_key=key, url=s)

    m = _GITHUB_URL.match(s)
    if m:
        owner = m.group("owner")
        repo = m.group("repo")
        num = m.group("num")
        key = f"{owner}/{repo}#{num}"
        canonical = f"https://github.com/{owner}/{repo}/issues/{num}"
        return TicketRef(provider="github", external_key=key, url=canonical)

    m = _GITHUB_SHORT.match(s)
    if m:
        owner = m.group("owner")
        repo = m.group("repo")
        num = m.group("num")
        key = f"{owner}/{repo}#{num}"
        canonical = f"https://github.com/{owner}/{repo}/issues/{num}"
        return TicketRef(provider="github", external_key=key, url=canonical)

    m = _BARE_KEY.match(s)
    if m:
        if hint_provider not in ("linear", "jira"):
            # Ambiguous; caller must provide hint_provider for bare keys.
            return None
        key = m.group("key").upper()
        url = _build_url_for_bare(hint_provider, key)
        return TicketRef(provider=hint_provider, external_key=key, url=url)

    return None


def _build_url_for_bare(provider: Provider, key: str) -> str:
    """Best-effort URL when only a bare key + hint is given.

    We don't know the team/host, so use a search URL or a placeholder
    that's still clickable and useful. The slash command and dashboard
    will usually supply the full URL via LinkCreateRequest.url, which
    takes precedence at the router layer.
    """
    if provider == "linear":
        return f"https://linear.app/search?q={key}"
    if provider == "jira":
        return f"https://atlassian.net/browse/{key}"
    # github bare keys aren't reachable here (no owner/repo)
    return key
