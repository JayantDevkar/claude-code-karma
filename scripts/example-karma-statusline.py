#!/usr/bin/env python3
"""Example status-line segment: a "see this in Karma" link for the current session.

This is a REFERENCE you copy from, not something Karma installs for you.
Claude Code's `statusLine` is a personal, global setting in
`~/.claude/settings.json` shared across every project you use Claude Code
in — only you should decide what goes into it, so Karma never touches it
automatically.

Two ways to use this:
  1. You have no statusLine yet: point `statusLine.command` straight at this
     file (see the settings.json snippet in SETUP.md).
  2. You already have a custom statusLine script: copy the `karma_segment()`
     function into it and print its result alongside whatever else you show.

Prerequisite: Karma's API needs to be reachable when the link is clicked —
either the dev servers are running, or the desktop app's autostart-at-login
is on. Without that, the link opens to nothing.
"""

from __future__ import annotations

import json
import os
import sys

KARMA_URL = os.environ.get("KARMA_URL", "http://localhost:5180")

# Terminals that render OSC 8 hyperlinks as clickable text (Cmd/Ctrl+click).
# Apple's Terminal.app is deliberately absent: it has never implemented OSC
# 8, so it can only make a *visible* URL clickable, never a short label with
# a different URL hidden underneath it.
OSC8_TERMS = {"iTerm.app", "WezTerm", "ghostty", "kitty", "Hyper", "vscode"}

RESET, DIM, CYAN = "\x1b[0m", "\x1b[2m", "\x1b[36m"


def karma_segment(session_id: str | None) -> str | None:
    """A "see this in Karma" link for the current session, or None."""
    if not session_id:
        return None
    url = f"{KARMA_URL}/s/{session_id[:8]}"
    label = f"{CYAN}see this in karma?{RESET}"
    if os.environ.get("TERM_PROGRAM") in OSC8_TERMS:
        # Real OSC 8 hyperlink: the label is the only visible text, the url
        # is invisible metadata underneath it. Cmd+click opens it on macOS.
        return f"\x1b]8;;{url}\x07{label}\x1b]8;;\x07"
    # Terminal.app can't hide a url behind a label, so both stay visible;
    # a plain click does nothing there. Apple has never documented a fixed
    # modifier for opening it — try Cmd+double-click or right-click it and
    # choose "Open URL" (found to vary by machine).
    return f"{label}  {DIM}{url}{RESET}"


def main() -> None:
    data = {} if sys.stdin.isatty() else json.load(sys.stdin)
    segment = karma_segment(data.get("session_id"))
    if segment:
        print(segment)


if __name__ == "__main__":
    main()
