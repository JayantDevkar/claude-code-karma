"""
Per-project cache of session titles and slugs.

Eliminates N+1 JSONL loading during search by pre-extracting title and slug
data once and caching to disk at ~/.claude_karma/cache/titles/{encoded_name}.json.

Thread-safe singleton with per-project locking. Titles are extracted via a
lightweight JSONL scanner that avoids full Session parsing overhead.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from config import settings
from models.project import get_cached_jsonl_count
from models.session_index import SessionIndex

logger = logging.getLogger(__name__)


@dataclass
class TitleEntry:
    """Cached title and slug data for a single session."""

    titles: list[str]
    slug: Optional[str]
    mtime: int = 0  # JSONL file mtime in milliseconds for staleness detection


class SessionTitleCache:
    """
    Singleton cache of session titles and slugs, keyed by project.

    Stores lightweight title/slug data extracted from JSONL files to avoid
    expensive full-session parsing during search. Data is persisted to disk
    at ~/.claude_karma/cache/titles/{encoded_name}.json and loaded on demand.

    Thread-safe: uses per-project locks so concurrent requests for different
    projects don't block each other.

    Usage:
        from services.session_title_cache import title_cache
        titles = title_cache.get_titles("-Users-me-repo", "abc-123")
        slug = title_cache.get_slug("-Users-me-repo", "abc-123")
    """

    _instance: Optional[SessionTitleCache] = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._project_data: Dict[str, Dict[str, TitleEntry]] = {}
        self._project_locks: Dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()  # Guards _project_locks dict itself

    @classmethod
    def get_instance(cls) -> SessionTitleCache:
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_project_lock(self, encoded_name: str) -> threading.Lock:
        """Get or create a lock for a specific project (thread-safe)."""
        if encoded_name not in self._project_locks:
            with self._meta_lock:
                if encoded_name not in self._project_locks:
                    self._project_locks[encoded_name] = threading.Lock()
        return self._project_locks[encoded_name]

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_project_titles(self, encoded_name: str) -> Dict[str, TitleEntry]:
        """
        Get all title entries for a project, loading/building as needed.

        Args:
            encoded_name: Encoded project directory name (e.g. "-Users-me-repo")

        Returns:
            Dict mapping session UUID to TitleEntry.
        """
        lock = self._get_project_lock(encoded_name)
        with lock:
            if encoded_name not in self._project_data or self._is_stale(encoded_name):
                self._load_or_build(encoded_name)
            return self._project_data.get(encoded_name, {})

    def get_titles(self, encoded_name: str, uuid: str) -> list[str]:
        """
        Get session titles for a specific session.

        Args:
            encoded_name: Encoded project directory name
            uuid: Session UUID

        Returns:
            List of session titles (may be empty).
        """
        entry = self.get_entry(encoded_name, uuid)
        return entry.titles if entry else []

    def get_slug(self, encoded_name: str, uuid: str) -> Optional[str]:
        """
        Get the slug for a specific session.

        Args:
            encoded_name: Encoded project directory name
            uuid: Session UUID

        Returns:
            Session slug or None.
        """
        entry = self.get_entry(encoded_name, uuid)
        return entry.slug if entry else None

    def get_entry(self, encoded_name: str, uuid: str) -> Optional[TitleEntry]:
        """
        Get the full TitleEntry for a specific session.

        Args:
            encoded_name: Encoded project directory name
            uuid: Session UUID

        Returns:
            TitleEntry or None if not found.
        """
        entries = self.get_project_titles(encoded_name)
        return entries.get(uuid)

    def set_title(self, encoded_name: str, uuid: str, title: str) -> None:
        """
        Set or update a session title in the cache.

        If the session already has titles, the new title is prepended to the list.
        If the session doesn't exist in the cache, creates a new entry.

        Args:
            encoded_name: Encoded project directory name
            uuid: Session UUID
            title: New title to set
        """
        lock = self._get_project_lock(encoded_name)
        with lock:
            # Load cache for this project
            cache_path = self._cache_path(encoded_name)

            # Load from disk or create empty cache
            data = self._load_from_disk(cache_path)
            if data is None:
                data = {}

            # Get or create entry for this session
            entry = data.get(uuid)
            if entry:
                # Update existing entry - prepend new title if not already present
                if title not in entry.titles:
                    entry.titles = [title] + entry.titles
            else:
                # Create new entry with current mtime if file exists
                mtime_ms = 0
                project_dir = settings.projects_dir / encoded_name
                jsonl_path = project_dir / f"{uuid}.jsonl"
                if jsonl_path.exists():
                    try:
                        mtime_ns = jsonl_path.stat().st_mtime_ns
                        mtime_ms = mtime_ns // 1_000_000
                    except OSError:
                        pass

                data[uuid] = TitleEntry(titles=[title], slug=None, mtime=mtime_ms)

            # Update in-memory cache
            self._project_data[encoded_name] = data

            # Persist to disk
            self._save_to_disk(cache_path, data)

    # -------------------------------------------------------------------------
    # Staleness detection
    # -------------------------------------------------------------------------

    def _is_stale(self, encoded_name: str) -> bool:
        """
        Check if the in-memory cache is stale for a project.

        Uses SQLite session count when available, falls back to JSONL file count.
        Stale if the difference exceeds 10% (minimum threshold of 1).

        Args:
            encoded_name: Encoded project directory name

        Returns:
            True if cache should be rebuilt.
        """
        cached = self._project_data.get(encoded_name)
        if cached is None:
            return True

        # Try SQLite count first (fast)
        current_count: Optional[int] = None
        if settings.use_sqlite:
            try:
                import sqlite3

                db_path = settings.sqlite_db_path
                if db_path.is_file():
                    conn = sqlite3.connect(str(db_path))
                    row = conn.execute(
                        "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = ?",
                        (encoded_name,),
                    ).fetchone()
                    conn.close()
                    current_count = row[0] if row else 0
            except Exception:
                pass

        # Fallback to JSONL file count
        if current_count is None:
            project_dir = settings.projects_dir / encoded_name
            if not project_dir.is_dir():
                return False
            current_count = get_cached_jsonl_count(project_dir)

        cached_count = len(cached)
        threshold = max(1, int(cached_count * 0.1))

        return abs(current_count - cached_count) > threshold

    # -------------------------------------------------------------------------
    # Load / build / persist
    # -------------------------------------------------------------------------

    def _load_or_build(self, encoded_name: str) -> None:
        """
        Load title data from disk cache, falling back to a full JSONL build.

        Tries the disk cache first. If stale or missing, rebuilds from JSONL
        files and persists the result.

        Args:
            encoded_name: Encoded project directory name
        """
        cache_path = self._cache_path(encoded_name)

        # Try loading from disk first
        disk_data = self._load_from_disk(cache_path)
        if disk_data is not None:
            self._project_data[encoded_name] = disk_data
            # Verify disk cache freshness against current JSONL count
            if not self._is_stale(encoded_name):
                return

        # Disk cache missing or stale -- rebuild from JSONL files
        data = self._build_from_sessions(encoded_name)
        self._project_data[encoded_name] = data
        self._save_to_disk(cache_path, data)

    def _load_from_disk(self, cache_path: Path) -> Optional[Dict[str, TitleEntry]]:
        """
        Load title cache from a JSON file on disk.

        Args:
            cache_path: Path to the cache JSON file

        Returns:
            Dict of UUID -> TitleEntry, or None if file is missing/invalid.
        """
        if not cache_path.is_file():
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            if raw.get("version") != 1:
                logger.debug("Title cache version mismatch at %s, rebuilding", cache_path)
                return None

            entries: Dict[str, TitleEntry] = {}
            for uuid, entry_data in raw.get("entries", {}).items():
                entries[uuid] = TitleEntry(
                    titles=entry_data.get("titles", []),
                    slug=entry_data.get("slug"),
                    mtime=entry_data.get("mtime", 0),
                )
            return entries

        except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
            logger.warning("Failed to load title cache from %s: %s", cache_path, exc)
            return None

    def _save_to_disk(self, cache_path: Path, data: Dict[str, TitleEntry]) -> None:
        """
        Persist title cache to a JSON file on disk.

        Creates parent directories as needed. Writes atomically (to a temp
        name then renames) to avoid partial reads by concurrent processes.

        Args:
            cache_path: Destination path for the cache JSON file
            data: Dict of UUID -> TitleEntry to persist
        """
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            payload = {
                "version": 1,
                "built_at": datetime.now(timezone.utc).isoformat(),
                "session_count": len(data),
                "entries": {
                    uuid: {
                        "titles": entry.titles,
                        "slug": entry.slug,
                        "mtime": entry.mtime,
                    }
                    for uuid, entry in data.items()
                },
            }

            # Write to temp file then rename for atomicity
            tmp_path = cache_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp_path.replace(cache_path)

        except OSError as exc:
            logger.warning("Failed to save title cache to %s: %s", cache_path, exc)

    def _build_from_sessions(self, encoded_name: str) -> Dict[str, TitleEntry]:
        """
        Build title cache from SQLite (fast) or JSONL scanning (slow fallback).

        When SQLite is enabled, reads titles/slugs directly from the indexed
        database — no JSONL file scanning needed. Falls back to JSONL scanning
        only when SQLite is unavailable or not ready.

        Args:
            encoded_name: Encoded project directory name

        Returns:
            Dict of UUID -> TitleEntry for every session in the project.
        """
        # Try SQLite first — fast path
        if settings.use_sqlite:
            data = self._build_from_sqlite(encoded_name)
            if data is not None:
                logger.info(
                    "Built title cache for %s from SQLite: %d sessions",
                    encoded_name,
                    len(data),
                )
                return data

        # Fallback: scan JSONL files (slow)
        data = self._build_from_jsonl(encoded_name)
        logger.info(
            "Built title cache for %s from JSONL scan: %d sessions",
            encoded_name,
            len(data),
        )
        return data

    def _build_from_sqlite(self, encoded_name: str) -> Optional[Dict[str, TitleEntry]]:
        """
        Build title cache from SQLite metadata index, merging any titles
        from the disk cache that may have been set before SQLite indexed
        the session.

        Returns None if SQLite DB file doesn't exist, allowing caller to fall back.
        """
        try:
            import sqlite3

            db_path = settings.sqlite_db_path
            if not db_path.is_file():
                return None

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT uuid, slug, session_titles FROM sessions WHERE project_encoded_name = ?",
                (encoded_name,),
            ).fetchall()
            conn.close()

            data: Dict[str, TitleEntry] = {}
            for row in rows:
                uid = row["uuid"]
                slug = row["slug"]
                titles: list[str] = []

                raw_titles = row["session_titles"]
                if raw_titles:
                    try:
                        parsed = json.loads(raw_titles)
                        if isinstance(parsed, list):
                            titles = parsed
                    except (json.JSONDecodeError, TypeError):
                        pass

                data[uid] = TitleEntry(titles=titles, slug=slug, mtime=0)

            # Merge titles from disk cache (covers titles set before SQLite
            # indexed the session, e.g. hook fired before indexer synced)
            disk_data = self._load_from_disk(self._cache_path(encoded_name))
            if disk_data:
                for uid, disk_entry in disk_data.items():
                    if not disk_entry.titles:
                        continue
                    if uid in data:
                        if not data[uid].titles:
                            # SQLite has no title but disk cache does
                            data[uid] = TitleEntry(
                                titles=disk_entry.titles,
                                slug=data[uid].slug or disk_entry.slug,
                                mtime=0,
                            )
                        else:
                            # Merge: add any disk-only titles
                            merged = list(data[uid].titles)
                            for t in disk_entry.titles:
                                if t not in merged:
                                    merged.append(t)
                            if len(merged) > len(data[uid].titles):
                                data[uid] = TitleEntry(
                                    titles=merged,
                                    slug=data[uid].slug,
                                    mtime=0,
                                )
                    else:
                        # Session in disk cache but not in SQLite yet
                        data[uid] = disk_entry

            return data

        except Exception as exc:
            logger.warning(
                "Failed to build title cache from SQLite for %s: %s",
                encoded_name,
                exc,
            )
            return None

    def _build_from_jsonl(self, encoded_name: str) -> Dict[str, TitleEntry]:
        """
        Build title cache by scanning all session JSONL files (slow fallback).
        """
        project_dir = settings.projects_dir / encoded_name
        if not project_dir.is_dir():
            return {}

        # Load sessions-index.json for fallback titles
        index_path = project_dir / "sessions-index.json"
        index = SessionIndex.load(index_path)
        index_summaries: Dict[str, str] = {}
        if index:
            for entry in index.entries:
                if entry.summary:
                    index_summaries[entry.session_id] = entry.summary

        data: Dict[str, TitleEntry] = {}

        for jsonl_path in project_dir.glob("*.jsonl"):
            if jsonl_path.name.startswith("agent-"):
                continue

            uuid = jsonl_path.stem

            try:
                mtime_ns = jsonl_path.stat().st_mtime_ns
                mtime_ms = mtime_ns // 1_000_000
            except OSError:
                mtime_ms = 0

            try:
                titles, slug = self._extract_titles_lightweight(jsonl_path)
            except Exception as exc:
                logger.debug("Error scanning %s: %s", jsonl_path.name, exc)
                titles, slug = [], None

            if not titles:
                fallback = index_summaries.get(uuid)
                if fallback:
                    titles = [fallback]

            data[uuid] = TitleEntry(titles=titles, slug=slug, mtime=mtime_ms)

        return data

    # -------------------------------------------------------------------------
    # Lightweight JSONL scanner
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_titles_lightweight(jsonl_path: Path) -> Tuple[list[str], Optional[str]]:
        """
        Extract session titles and slug from a JSONL file without full parsing.

        Reads the file line-by-line, looking for:
        - ``"type": "summary"`` entries (after conversation has started) for titles
        - Any entry with a ``"slug"`` field for the session slug

        This is significantly cheaper than constructing a full Session object
        because it skips content block parsing, usage aggregation, etc.

        Args:
            jsonl_path: Path to the session JSONL file

        Returns:
            Tuple of (titles, slug).
        """
        titles: list[str] = []
        slug: Optional[str] = None
        conversation_started = False

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                if not isinstance(data, dict):
                    continue

                msg_type = data.get("type")

                # Track conversation start
                if msg_type in ("human", "assistant"):
                    conversation_started = True

                # Capture slug from the first entry that has one
                if slug is None and "slug" in data:
                    entry_slug = data["slug"]
                    if isinstance(entry_slug, str) and entry_slug:
                        slug = entry_slug

                # Capture titles from summary entries after conversation starts
                if msg_type == "summary" and conversation_started:
                    summary_text = data.get("summary")
                    if isinstance(summary_text, str) and summary_text:
                        titles.append(summary_text)

        return titles, slug

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _cache_path(encoded_name: str) -> Path:
        """Get the disk cache path for a project's title cache."""
        return settings.karma_base / "cache" / "titles" / f"{encoded_name}.json"


# Module-level singleton
title_cache = SessionTitleCache.get_instance()
