#!/usr/bin/env python3
"""
Session title generator hook for Claude Karma.

Fires on SessionEnd, reads the session JSONL, extracts context,
calls Claude Haiku to generate a concise title, then POSTs it
to the Claude Karma API.

Logs title generation metadata into the live session state file
at ~/.claude_karma/live-sessions/{slug}.json for observability.

Cost: ~$0.001 per session using Claude Haiku.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# Reuse atomic write and slug extraction from live_session_tracker
from live_session_tracker import (
    extract_slug_from_jsonl,
    read_existing_state,
    write_state_atomic,
    get_state_path_by_slug,
    get_state_path_by_session_id,
)

# Config
API_BASE = os.environ.get("CLAUDE_KARMA_API", "http://localhost:8000")
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_PROMPT_LENGTH = 500
MAX_RESPONSE_LENGTH = 300
TITLE_MAX_WORDS = 10


def log_title_generation(
    session_id: str,
    slug: Optional[str],
    title: Optional[str],
    source: str,
    api_posted: bool,
    error: Optional[str] = None,
) -> None:
    """Write title generation metadata into the live session state file."""
    now = datetime.now(timezone.utc).isoformat()

    # Find the existing state file
    existing_path, existing = read_existing_state(slug, session_id)

    if not existing_path:
        # No live session file — use slug or session_id to create path
        if slug:
            existing_path = get_state_path_by_slug(slug)
        else:
            existing_path = get_state_path_by_session_id(session_id)

    def update_fn(state: dict) -> dict:
        state["title_generation"] = {
            "title": title,
            "source": source,  # "haiku", "fallback", or "skipped"
            "api_posted": api_posted,
            "generated_at": now,
        }
        if error:
            state["title_generation"]["error"] = error
        state["updated_at"] = now
        return state

    write_state_atomic(existing_path, update_fn)


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return

    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")
    cwd = data.get("cwd", "")
    reason = data.get("reason", "")

    # Extract slug for state file lookup
    slug = extract_slug_from_jsonl(transcript_path) if transcript_path else None

    # Skip if no transcript or if cleared (not meaningful sessions)
    if not transcript_path or not Path(transcript_path).exists():
        log_title_generation(session_id, slug, None, "skipped", False, "no transcript")
        return
    if reason in ("clear",):
        log_title_generation(session_id, slug, None, "skipped", False, f"reason={reason}")
        return

    # Extract context from JSONL
    initial_prompt, first_response = extract_session_context(transcript_path)
    if not initial_prompt:
        log_title_generation(session_id, slug, None, "skipped", False, "no initial prompt")
        return

    # Get git commits during session
    git_context = get_git_context(cwd, transcript_path)

    # Generate title via Haiku
    title, source = generate_title(initial_prompt, first_response, git_context)

    if title:
        api_posted = post_title(session_id, title)
        log_title_generation(session_id, slug, title, source, api_posted)
    else:
        log_title_generation(session_id, slug, None, "failed", False, "generation returned None")


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
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                        content = " ".join(texts)
                    if isinstance(content, str) and content.strip():
                        initial_prompt = content.strip()[:MAX_PROMPT_LENGTH]

                elif role == "assistant" and initial_prompt and first_response is None:
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                        content = " ".join(texts)
                    if isinstance(content, str) and content.strip():
                        first_response = content.strip()[:MAX_RESPONSE_LENGTH]
                        break
    except (OSError, IOError):
        pass

    return initial_prompt, first_response


def get_git_context(cwd: str, transcript_path: str) -> Optional[str]:
    """Get git commits made during the session timeframe."""
    if not cwd or not Path(cwd).exists():
        return None

    try:
        mtime = Path(transcript_path).stat().st_mtime
        start_time = datetime.fromtimestamp(mtime, tz=timezone.utc)

        result = subprocess.run(
            ["git", "log", "--oneline", "--since=1 hour ago", "--no-merges", "-10"],
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
    """Call Claude Haiku to generate a concise session title.

    Returns (title, source) where source is 'haiku' or 'fallback'.
    """
    parts = [f"User asked: {initial_prompt}"]
    if first_response:
        parts.append(f"Assistant did: {first_response}")
    if git_context:
        parts.append(f"Git commits: {git_context}")
    context = "\n".join(parts)

    prompt = f"""Generate a concise 5-{TITLE_MAX_WORDS} word title for this coding session.
The title should describe what was accomplished or attempted.
Return ONLY the title, no quotes, no explanation.

{context}

Title:"""

    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )

        title = response.content[0].text.strip()
        title = title.strip('"\'')
        words = title.split()
        if len(words) > TITLE_MAX_WORDS:
            title = " ".join(words[:TITLE_MAX_WORDS])
        return title, "haiku"

    except Exception:
        fallback = initial_prompt[:60]
        if len(initial_prompt) > 60:
            fallback += "..."
        return fallback, "fallback"


def post_title(session_id: str, title: str) -> bool:
    """POST the generated title to the Claude Karma API. Returns True on success."""
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
        return False


if __name__ == "__main__":
    main()
