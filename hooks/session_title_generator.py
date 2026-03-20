#!/usr/bin/env python3
"""
Session title generator hook for Claude Code Karma.

Fires on SessionEnd, reads the session JSONL, extracts context,
and generates a concise title. Prefers git commit messages when
available (free, no LLM). Falls back to Claude Haiku via
`claude -p --no-session-persistence` to avoid creating bloat sessions.

"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

API_BASE = os.environ.get("CLAUDE_KARMA_API", "http://localhost:8000")
MAX_PROMPT_LENGTH = 500
MAX_RESPONSE_LENGTH = 300
TITLE_MAX_WORDS = 10


def _strip_system_tags(text: str) -> str:
    """Remove XML system/skill tags, keeping any real user text around them."""
    cleaned = re.sub(
        r"<(?:command-message|system-reminder|command-name|user-prompt-submit-hook)[^>]*>.*?</(?:command-message|system-reminder|command-name|user-prompt-submit-hook)>",
        "",
        text,
        flags=re.DOTALL,
    )
    # Also strip self-closing variants
    cleaned = re.sub(r"<(?:command-message|system-reminder|command-name|user-prompt-submit-hook)[^/]*/?>", "", cleaned)
    return cleaned.strip()


def _extract_text(msg: dict) -> str:
    """Extract plain text from a message's content (handles string and list forms)."""
    content = msg.get("content", "")
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        content = " ".join(texts)
    return content.strip() if isinstance(content, str) else ""


def _get_session_start_iso(transcript_path: str) -> Optional[str]:
    """Extract the ISO timestamp of the first entry in a JSONL transcript."""
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp")
                    if ts:
                        return ts
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        pass
    return None


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return

    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")
    cwd = data.get("cwd", "")
    reason = data.get("reason", "")

    # Skip if no transcript or if cleared (not meaningful sessions)
    if not transcript_path or not Path(transcript_path).exists():
        return
    if reason in ("clear",):
        return

    # Extract context from JSONL
    initial_prompt, first_response = extract_session_context(transcript_path)
    if not initial_prompt:
        return

    # Get git commits during session
    git_context = get_git_context(cwd, transcript_path)

    # Generate title
    title, source = generate_title(initial_prompt, first_response, git_context)

    if title:
        post_title(session_id, title)
    elif source in ("rate_limited", "timeout"):
        # Enqueue for retry so the API can regenerate when limits reset
        enqueue_title_retry(session_id, transcript_path, initial_prompt, first_response, cwd)


def extract_session_context(transcript_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract initial prompt and first assistant response from JSONL."""
    initial_prompt = None
    first_response = None

    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = entry.get("message", {})
                role = msg.get("role", "")

                # Skip sidechain messages (subagents)
                if entry.get("isSidechain"):
                    continue

                if role == "user" and initial_prompt is None:
                    text = _strip_system_tags(_extract_text(msg))
                    if text:
                        initial_prompt = text[:MAX_PROMPT_LENGTH]

                elif role == "assistant" and initial_prompt and first_response is None:
                    text = _extract_text(msg)
                    if text:
                        first_response = text[:MAX_RESPONSE_LENGTH]
                        break
    except (OSError, IOError):
        pass

    return initial_prompt, first_response


def get_git_context(cwd: str, transcript_path: str) -> Optional[str]:
    """Get git commits made during the session timeframe.

    Uses the JSONL transcript's first timestamp to scope the git log to
    the actual session duration rather than an arbitrary fixed window.
    Falls back to 1 hour if the timestamp can't be extracted.
    """
    if not cwd or not Path(cwd).exists():
        return None

    since_arg = "1 hour ago"
    start_ts = _get_session_start_iso(transcript_path)
    if start_ts:
        since_arg = start_ts

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={since_arg}", "--no-merges", "-10"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:300]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return None


def generate_title(
    initial_prompt: str,
    first_response: Optional[str],
    git_context: Optional[str],
) -> Tuple[Optional[str], str]:
    """Generate a concise session title.

    Priority:
    1. Git commit messages (if available) — free, no LLM needed
    2. Claude Haiku via `claude -p` with --no-session-persistence to avoid bloat
    3. Fallback: truncated initial prompt

    Returns (title, source) where source is 'git', 'haiku', or 'fallback'.
    """
    # 1. Use most recent git commit message as title if available
    if git_context:
        # git_context is "hash msg\nhash msg\n..." — take the first (most recent) line
        first_commit = git_context.split("\n")[0].strip()
        if first_commit:
            # Strip the short hash prefix (e.g. "a1b2c3d fix: something" → "fix: something")
            parts = first_commit.split(" ", 1)
            title = parts[1] if len(parts) > 1 else parts[0]
            words = title.split()
            if len(words) > TITLE_MAX_WORDS:
                title = " ".join(words[:TITLE_MAX_WORDS])
            return title, "git"

    # 2. Fall back to Haiku (with --no-session-persistence to avoid session bloat)
    parts = [f"User asked: {initial_prompt}"]
    if first_response:
        parts.append(f"Assistant did: {first_response}")
    context = "\n".join(parts)

    prompt = f"""Generate a concise 5-{TITLE_MAX_WORDS} word title for this coding session.
The title should describe what was accomplished or attempted.
Return ONLY the title, no quotes, no explanation.

{context}

Title:"""

    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # Allow nested claude invocation

        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku", "--no-session-persistence", "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0 and result.stdout.strip():
            title = result.stdout.strip()
            title = title.strip('"\'')
            words = title.split()
            if len(words) > TITLE_MAX_WORDS:
                title = " ".join(words[:TITLE_MAX_WORDS])
            return title, "haiku"

        # Non-zero exit — check if it was a usage/rate limit error
        stderr_lower = (result.stderr or "").lower()
        if _is_rate_limit_error(stderr_lower):
            return None, "rate_limited"

    except subprocess.TimeoutExpired:
        # Timeout likely means the system is under heavy load (e.g. active session)
        # Return None so the caller can queue for retry rather than storing a bad title
        return None, "timeout"
    except (FileNotFoundError, OSError):
        pass

    # 3. Fallback: truncated initial prompt
    fallback = initial_prompt[:60]
    if len(initial_prompt) > 60:
        fallback += "..."
    return fallback, "fallback"


_RATE_LIMIT_PHRASES = (
    "usage limit",
    "rate limit",
    "too many requests",
    "quota exceeded",
    "overloaded",
    "context window",
)


def _is_rate_limit_error(stderr: str) -> bool:
    stderr_lower = stderr.lower()
    return any(phrase in stderr_lower for phrase in _RATE_LIMIT_PHRASES)


def enqueue_title_retry(
    session_id: str,
    transcript_path: str,
    initial_prompt: str,
    first_response: Optional[str],
    cwd: str,
) -> None:
    """
    Save session context to the retry queue so the API can regenerate the
    title later (e.g. after a usage limit resets or system load drops).

    Written to ~/.claude_karma/title-retry/{uuid}.json.
    """
    try:
        retry_dir = KARMA_BASE / "title-retry"
        retry_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": session_id,
            "transcript_path": transcript_path,
            "initial_prompt": initial_prompt,
            "first_response": first_response,
            "cwd": cwd,
        }
        (retry_dir / f"{session_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


KARMA_BASE = Path(os.path.expanduser("~/.claude_karma"))
PENDING_TITLES_DIR = KARMA_BASE / "session-titles"


def save_title_locally(session_id: str, title: str) -> None:
    """Save title to a local file as fallback when API is unavailable."""
    try:
        PENDING_TITLES_DIR.mkdir(parents=True, exist_ok=True)
        (PENDING_TITLES_DIR / f"{session_id}.txt").write_text(title, encoding="utf-8")
    except OSError:
        pass


def post_title(session_id: str, title: str) -> bool:
    """POST the generated title to the Claude Code Karma API. Returns True on success."""
    import urllib.request
    import urllib.error

    url = f"{API_BASE}/sessions/{session_id}/title"
    data = json.dumps({"title": title}).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except (urllib.error.URLError, OSError):
        # API unavailable — persist locally so the cache can pick it up later
        save_title_locally(session_id, title)
        return False


if __name__ == "__main__":
    main()
