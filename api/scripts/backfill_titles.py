#!/usr/bin/env python3
"""
Backfill session titles for sessions that don't have them.

Queries SQLite for sessions with NULL or empty session_titles,
extracts context from their JSONL files, generates titles via
Claude Haiku API, and POSTs them to the Claude Code Karma API.

Usage:
    python scripts/backfill_titles.py
    python scripts/backfill_titles.py --dry-run
    python scripts/backfill_titles.py --limit 10
    python scripts/backfill_titles.py --project -Users-me-repo
    python scripts/backfill_titles.py --synced --dry-run
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# Add api/ to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Config
API_BASE = os.environ.get("CLAUDE_KARMA_API", "http://localhost:8020")
MAX_PROMPT_LENGTH = 500
MAX_RESPONSE_LENGTH = 300
RATE_LIMIT_DELAY = 0.5  # seconds between Haiku calls


def main():
    parser = argparse.ArgumentParser(description="Backfill session titles")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be titled without making changes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of sessions to process",
    )
    parser.add_argument(
        "--project",
        help="Filter by project encoded name (e.g., -Users-me-repo)",
    )
    parser.add_argument(
        "--synced",
        action="store_true",
        help="Only sessions synced from other machines (extra roots), any age",
    )
    args = parser.parse_args()

    # Get DB path
    karma_base = Path.home() / ".claude_karma"
    db_path = karma_base / "metadata.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        print("Run the API server first to create the database.")
        sys.exit(1)

    # Query titleless sessions
    sessions = get_titleless_sessions(db_path, args.project, args.limit, synced_only=args.synced)

    if not sessions:
        print("No sessions need titles.")
        return

    print(f"Found {len(sessions)} sessions without titles")

    if args.dry_run:
        print("\nDry run - would process:")
        for uuid, encoded_name, initial_prompt in sessions:
            prompt_preview = (initial_prompt or "")[:60]
            print(f"  {uuid} ({encoded_name}): {prompt_preview}...")
        return

    from services.synced_titles import load_title_generator

    generate_title = load_title_generator()
    if generate_title is None:
        print("Error: cannot load hooks/session_title_generator.py")
        sys.exit(1)

    # Process each session
    processed = 0
    errors = 0

    for uuid, encoded_name, initial_prompt in sessions:
        try:
            if args.synced:
                # Synced sessions: indexed prompt only, no git context (see the design spec)
                user_prompt, assistant_response, git_context = initial_prompt, None, None
            else:
                # JSONL path: local file, else a copy synced from another machine
                from services.session_roots import session_jsonl_path

                jsonl_path = session_jsonl_path(encoded_name, uuid)

                if not jsonl_path.exists():
                    print(f"⚠ Skipping {uuid}: JSONL not found")
                    errors += 1
                    continue

                # Extract context from JSONL
                user_prompt, assistant_response = extract_session_context(jsonl_path)

                if not user_prompt:
                    # Fallback to DB initial_prompt if JSONL extraction failed
                    user_prompt = initial_prompt

                # Get git context (optional, may be None)
                git_context = get_git_context(jsonl_path)

            if not user_prompt:
                print(f"⚠ Skipping {uuid}: No prompt found")
                errors += 1
                continue

            # Generate title; the hook's truncated-prompt fallback is not stored
            title, source = generate_title(user_prompt, assistant_response, git_context)

            if not title or source == "fallback":
                print(f"⚠ Skipping {uuid}: Title generation failed")
                errors += 1
                continue

            # POST to API
            success = post_title(uuid, title)

            if success:
                print(f"✓ {uuid}: {title}")
                processed += 1
            else:
                print(f"✗ {uuid}: API POST failed")
                errors += 1

            # Rate limiting
            if processed < len(sessions):
                time.sleep(RATE_LIMIT_DELAY)

        except Exception as e:
            print(f"✗ {uuid}: {e}")
            errors += 1

    print(f"\nProcessed: {processed}, Errors: {errors}")


def get_titleless_sessions(
    db_path: Path,
    project_filter: Optional[str] = None,
    limit: Optional[int] = None,
    synced_only: bool = False,
) -> list[Tuple[str, str, Optional[str]]]:
    """
    Query SQLite for sessions without titles.

    Returns:
        List of (uuid, encoded_name, initial_prompt) tuples
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT uuid, project_encoded_name, initial_prompt
        FROM sessions
        WHERE (session_titles IS NULL OR session_titles = '' OR session_titles = '[]')
        AND message_count > 0
    """

    params = []

    if project_filter:
        query += " AND project_encoded_name = ?"
        params.append(project_filter)

    if synced_only:
        query += " AND source_root IS NOT NULL"

    query += " ORDER BY start_time DESC"

    if limit:
        query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [(row["uuid"], row["project_encoded_name"], row["initial_prompt"]) for row in rows]


def extract_session_context(jsonl_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract initial prompt and first assistant response from JSONL.

    This is the same logic used in session_title_generator.py hook.
    """
    initial_prompt = None
    first_response = None

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
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
                    # Extract user message content
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # Extract text from content blocks
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
                        break  # Got both, stop scanning

    except (OSError, IOError) as e:
        print(f"  Error reading {jsonl_path.name}: {e}")

    return initial_prompt, first_response


def get_git_context(jsonl_path: Path) -> Optional[str]:
    """
    Get git commits during session timeframe (optional).

    Returns None if git is unavailable or no commits found.
    """
    try:
        # Get file modification time as session approximation
        mtime = jsonl_path.stat().st_mtime
        _start_time = datetime.fromtimestamp(mtime, tz=timezone.utc)  # noqa: F841

        # Try to get git log from parent directory
        cwd = jsonl_path.parent.parent.parent  # Up from projects/{encoded}/

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


def post_title(session_uuid: str, title: str) -> bool:
    """
    POST the generated title to the Claude Code Karma API.

    Returns:
        True if successful, False otherwise
    """
    url = f"{API_BASE}/sessions/{session_uuid}/title"
    data = json.dumps({"title": title}).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = urllib.request.urlopen(req, timeout=5)
        return response.status == 200

    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.reason}")
        return False
    except (urllib.error.URLError, OSError) as e:
        print(f"  Network error: {e}")
        return False


if __name__ == "__main__":
    main()
