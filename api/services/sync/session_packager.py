"""Session packager — collects project sessions into a staging directory."""

import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings
from models.sync_manifest import SessionEntry, SkillDefinitionEntry, SyncManifest

logger = logging.getLogger(__name__)

MIN_FREE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GiB
MAX_SKILL_SIZE = 1_000_000  # 1 MB, mirrors api/config.py


STALE_LIVE_SESSION_SECONDS = 30 * 60  # 30 minutes


def _get_live_session_uuids() -> set[str]:
    """Return UUIDs of sessions that are currently live (not yet ended).

    Reads ``~/.claude_karma/live-sessions/*.json`` written by Claude Code hooks.
    If hooks aren't configured (directory missing/empty), returns an empty set
    so all sessions pass through — backward compatible.

    Sessions idle for more than 30 minutes are considered stale (likely crashed
    without a SessionEnd hook) and are NOT excluded — their JSONL is stable
    enough to package.
    """
    live_dir = settings.karma_base / "live-sessions"
    if not live_dir.is_dir():
        return set()

    now = datetime.now(timezone.utc)
    live_uuids: set[str] = set()
    for json_file in live_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            state = data.get("state", "")
            if state == "ENDED":
                continue

            # Skip sessions idle longer than the staleness threshold —
            # likely crashed without SessionEnd, safe to package.
            updated_at_str = data.get("updated_at")
            if updated_at_str:
                updated_at = datetime.fromisoformat(
                    updated_at_str.replace("Z", "+00:00")
                )
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                idle_seconds = (now - updated_at).total_seconds()
                if idle_seconds > STALE_LIVE_SESSION_SECONDS:
                    logger.debug(
                        "Live session %s idle %.0fs > %ds, treating as stale",
                        data.get("session_id", "?"),
                        idle_seconds,
                        STALE_LIVE_SESSION_SECONDS,
                    )
                    continue

            # Current active session UUID
            sid = data.get("session_id")
            if sid:
                live_uuids.add(sid)
            # All historical UUIDs for this slug (resumed sessions)
            for sid in data.get("session_ids", []):
                live_uuids.add(sid)
        except (json.JSONDecodeError, OSError):
            continue
    return live_uuids


def get_session_limit(
    team_session_limit: str,
    dest_path: Path,
    *,
    team_name: Optional[str] = None,
    member_tag: Optional[str] = None,
) -> int | None:
    """Return max sessions to package, or None for unlimited.

    Checks for per-device override in metadata file before using team setting.
    If disk has < 10 GiB free, force recent 100 regardless of setting.
    """
    try:
        free = shutil.disk_usage(dest_path).free
    except OSError:
        return 100  # Can't check disk → be conservative
    if free < MIN_FREE_BYTES:
        return 100  # safety cap

    # Check per-device override from metadata file
    effective_limit = team_session_limit
    if team_name and member_tag:
        try:
            meta_file = settings.karma_base / "metadata-folders" / team_name / "members" / f"{member_tag}.json"
            if meta_file.exists():
                state = json.loads(meta_file.read_text(encoding="utf-8"))
                device_limit = state.get("session_limit")
                if device_limit and device_limit in ("all", "recent_100", "recent_10"):
                    effective_limit = device_limit
        except (json.JSONDecodeError, OSError):
            pass

    limits = {"all": None, "recent_100": 100, "recent_10": 10}
    return limits.get(effective_limit, None)


# Regex to extract plan slugs from JSONL bytes: matches plans/{slug}.md
_PLAN_SLUG_RE = re.compile(rb'plans/([\w][\w.-]*?)\.md')


def _discover_plan_references(
    session_jsonl_paths: list[tuple[str, Path]],
) -> dict[str, dict]:
    """Scan session JONLs for plan file references.

    Returns:
        {slug: {"sessions": {uuid: operation, ...}}} where operation is
        "created" (Write), "edited" (Edit/StrReplace), or "read" (Read).
    """
    # Operation priority: created > edited > read
    op_priority = {"created": 3, "edited": 2, "read": 1}
    plans: dict[str, dict[str, str]] = {}  # slug -> {uuid -> operation}

    for uuid, jsonl_path in session_jsonl_paths:
        if not jsonl_path.is_file():
            continue
        try:
            raw = jsonl_path.read_bytes()
        except (PermissionError, OSError):
            continue

        # Fast check: any plan reference at all?
        if b"plans/" not in raw or b".md" not in raw:
            continue

        # Extract all plan slugs referenced in this JSONL
        slugs_found = set(_PLAN_SLUG_RE.findall(raw))
        if not slugs_found:
            continue

        # Determine operation type per slug by scanning for tool use patterns
        for slug_bytes in slugs_found:
            slug = slug_bytes.decode("utf-8", errors="replace")
            needle = f"plans/{slug}.md".encode()

            # Determine best operation: scan for Write/Edit/StrReplace/Read near the slug
            operation = "read"  # default
            for line in raw.split(b"\n"):
                if needle not in line:
                    continue
                if b'"Write"' in line or b'"name": "Write"' in line:
                    operation = "created"
                    break  # highest priority, stop
                elif b'"Edit"' in line or b'"StrReplace"' in line:
                    if op_priority.get(operation, 0) < op_priority["edited"]:
                        operation = "edited"

            if slug not in plans:
                plans[slug] = {}
            # Keep highest-priority operation per session
            existing = plans[slug].get(uuid, "")
            if op_priority.get(operation, 0) > op_priority.get(existing, 0):
                plans[slug][uuid] = operation

    return plans


def _build_titles_from_db(session_uuids: list[str]) -> dict[str, dict]:
    """Query the metadata DB for session titles of given sessions.

    Returns dict suitable for write_titles_bulk():
        {uuid: {"title": str, "source": str}} for sessions that have titles.
    """
    if not session_uuids:
        return {}

    try:
        from db.connection import create_writer_connection

        conn = create_writer_connection()
    except Exception:
        return {}

    titles: dict[str, dict] = {}
    placeholders = ",".join("?" * len(session_uuids))

    try:
        rows = conn.execute(
            f"SELECT uuid, session_titles FROM sessions WHERE uuid IN ({placeholders}) AND session_titles IS NOT NULL",
            session_uuids,
        ).fetchall()
        for row in rows:
            try:
                parsed = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                if isinstance(parsed, list) and parsed:
                    titles[row[0]] = {"title": parsed[0], "source": "db"}
            except (json.JSONDecodeError, TypeError, IndexError):
                continue
    except Exception as e:
        logger.debug("Failed to query session titles from DB: %s", e)
    finally:
        conn.close()

    return titles


def _resolve_skill_file(skill_name: str, claude_base: Path) -> Optional[Path]:
    """Resolve a skill name to its definition file path on disk.

    Synchronous, no HTTP dependencies. Checks global commands/skills,
    plugin cache (with manifest custom paths), and inherited skills.
    Returns None if no file is found.
    """
    is_plugin = ":" in skill_name

    if not is_plugin:
        # Non-plugin: check global commands and skills directories
        for candidate in (
            claude_base / "commands" / f"{skill_name}.md",
            claude_base / "skills" / skill_name / "SKILL.md",
        ):
            if candidate.is_file():
                return candidate

    # Extract plugin/skill parts for cache walk
    if is_plugin:
        plugin_short_name = skill_name.split(":")[0].split("@")[0]
        actual_skill = skill_name.split(":", 1)[1]
    else:
        plugin_short_name = None
        actual_skill = skill_name

    # Try to import read_plugin_manifest for custom path support
    try:
        from models.plugin import read_plugin_manifest
    except ImportError:
        read_plugin_manifest = None  # type: ignore[assignment]

    plugins_cache = claude_base / "plugins" / "cache"
    if plugins_cache.is_dir():
        for registry_dir in plugins_cache.iterdir():
            if not registry_dir.is_dir():
                continue
            for plugin_dir in registry_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                if plugin_short_name and plugin_dir.name != plugin_short_name:
                    continue
                for version_dir in plugin_dir.iterdir():
                    if not version_dir.is_dir():
                        continue

                    # Check default locations
                    for candidate in (
                        version_dir / "commands" / f"{actual_skill}.md",
                        version_dir / "skills" / actual_skill / "SKILL.md",
                    ):
                        if candidate.is_file():
                            return candidate

                    # Check manifest custom paths
                    if read_plugin_manifest:
                        manifest = read_plugin_manifest(version_dir)
                        if manifest:
                            for key, filename in [
                                ("skills", f"{actual_skill}/SKILL.md"),
                                ("commands", f"{actual_skill}.md"),
                            ]:
                                custom = manifest.get(key)
                                if not custom:
                                    continue
                                for cp in (
                                    [custom] if isinstance(custom, str) else custom
                                ):
                                    d = version_dir / cp.removeprefix("./")
                                    candidate = d / filename
                                    if candidate.is_file():
                                        return candidate

    # Fallback: check inherited skills (colon-form and dash-form)
    if is_plugin:
        for candidate_name in (skill_name, skill_name.replace(":", "-")):
            inherited = claude_base / "skills" / candidate_name / "SKILL.md"
            if inherited.is_file():
                return inherited

    return None


def _build_skill_definitions(
    skill_classifications: dict[str, str],
    claude_base: Path,
) -> dict[str, SkillDefinitionEntry]:
    """Resolve skill definition files and build content entries for the manifest.

    Iterates skill_classifications keys, resolves each to its SKILL.md file,
    reads content (capped at MAX_SKILL_SIZE), and builds SkillDefinitionEntry
    objects. Only includes skills where a file was found and readable.
    Skips bundled/builtin categories (they ship with Claude Code).
    """
    definitions: dict[str, SkillDefinitionEntry] = {}
    skip_categories = {"bundled_skill", "builtin_command"}

    for name, category in skill_classifications.items():
        if category in skip_categories:
            continue
        try:
            skill_file = _resolve_skill_file(name, claude_base)
            if not skill_file:
                continue
            if skill_file.stat().st_size > MAX_SKILL_SIZE:
                continue

            content = skill_file.read_text(encoding="utf-8", errors="replace")

            # Parse description from YAML frontmatter
            description = None
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        import yaml

                        frontmatter = yaml.safe_load(parts[1])
                        if isinstance(frontmatter, dict):
                            description = frontmatter.get("description")
                    except Exception:
                        pass  # Best-effort: skip unparseable frontmatter

            definitions[name] = SkillDefinitionEntry(
                content=content,
                description=description,
                category=category,
                base_directory=str(skill_file.parent),
            )
        except Exception as e:
            logger.debug("Skipping skill definition for %s: %s", name, e)

    return definitions


def _build_skill_classifications_from_db(
    session_uuids: list[str],
) -> dict[str, str]:
    """Query the metadata DB for skill/command classifications of given sessions.

    The DB already has correctly classified invocations (session_skills and
    session_commands tables). We extract all plugin colon-format names and
    their categories so the importing machine can use them as ground truth.

    Returns:
        Dict mapping invocation name → InvocationCategory string.
        E.g. {'feature-dev:feature-dev': 'plugin_command',
              'superpowers:brainstorming': 'plugin_skill'}
    """
    if not session_uuids:
        return {}

    try:
        from db.connection import create_writer_connection

        conn = create_writer_connection()
    except Exception:
        return {}

    classifications: dict[str, str] = {}
    placeholders = ",".join("?" * len(session_uuids))

    try:
        # Import classify_invocation from API (already on sys.path)
        try:
            from command_helpers import classify_invocation
            _classify = classify_invocation
        except ImportError:
            # Fallback: colon-format → plugin, otherwise unknown (will be reclassified on import)
            def _classify(name, source="skill_tool"):  # type: ignore[misc]
                return "plugin_skill" if ":" in name else "custom_skill"

        # Skills from session_skills table (all names, not just colon-format)
        rows = conn.execute(
            f"SELECT DISTINCT skill_name FROM session_skills WHERE session_uuid IN ({placeholders})",
            session_uuids,
        ).fetchall()
        for row in rows:
            classifications[row[0]] = _classify(row[0], source="skill_tool")

        # Commands from session_commands table (all names, not just colon-format)
        rows = conn.execute(
            f"SELECT DISTINCT command_name FROM session_commands WHERE session_uuid IN ({placeholders})",
            session_uuids,
        ).fetchall()
        for row in rows:
            classifications[row[0]] = _classify(row[0], source="slash_command")

        # Subagent skills
        rows = conn.execute(
            f"""SELECT DISTINCT ss.skill_name FROM subagent_skills ss
                JOIN subagent_invocations si ON ss.invocation_id = si.id
                WHERE si.session_uuid IN ({placeholders})""",
            session_uuids,
        ).fetchall()
        for row in rows:
            if row[0] not in classifications:
                classifications[row[0]] = _classify(row[0], source="skill_tool")

        # Subagent commands
        rows = conn.execute(
            f"""SELECT DISTINCT sc.command_name FROM subagent_commands sc
                JOIN subagent_invocations si ON sc.invocation_id = si.id
                WHERE si.session_uuid IN ({placeholders})""",
            session_uuids,
        ).fetchall()
        for row in rows:
            if row[0] not in classifications:
                classifications[row[0]] = _classify(row[0], source="slash_command")

    except Exception as e:
        logger.warning("Failed to extract skill classifications from DB: %s", e)
    finally:
        conn.close()

    return classifications


def _detect_git_branch(project_path: str) -> Optional[str]:
    """Detect the current git branch for a project/worktree path.

    Tries ``git rev-parse --abbrev-ref HEAD`` in the given directory.
    Returns None if git is not available, the path doesn't exist, or
    the repo is in detached-HEAD state.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        if not branch or branch == "HEAD":
            return None
        return branch
    except (subprocess.SubprocessError, OSError):
        return None


def _extract_worktree_name(dir_name: str, main_dir_name: str) -> Optional[str]:
    """Extract human-readable worktree name from encoded dir name.

    Given main="-Users-jay-GitHub-karma" and
    dir="-Users-jay-GitHub-karma--claude-worktrees-feat-a",
    returns "feat-a".
    """
    markers = ["--claude-worktrees-", "-.claude-worktrees-", "--worktrees-", "-.worktrees-"]
    for marker in markers:
        idx = dir_name.find(marker)
        if idx > 0:
            return dir_name[idx + len(marker):]
    return None


class SessionPackager:
    """Discovers and packages Claude Code sessions for a project."""

    def __init__(
        self,
        project_dir: Path,
        user_id: str,
        machine_id: str,
        device_id: Optional[str] = None,
        project_path: str = "",
        extra_dirs: Optional[list[Path]] = None,
        team_name: Optional[str] = None,
        proj_suffix: Optional[str] = None,
        member_tag: Optional[str] = None,
    ):
        self.project_dir = Path(project_dir)
        self.user_id = user_id
        self.machine_id = machine_id
        self.member_tag = member_tag
        self.device_id = device_id
        self.project_path = project_path or str(self.project_dir)

        self.extra_dirs = [Path(d) for d in (extra_dirs or [])]
        self.team_name = team_name
        self.proj_suffix = proj_suffix
        # ~/.claude/ base directory (parent of projects/{encoded}/)
        self._claude_base = self.project_dir.parent.parent

    def _discover_from_dir(
        self,
        directory: Path,
        worktree_name: Optional[str] = None,
        git_branch: Optional[str] = None,
    ) -> list[SessionEntry]:
        """Find session JSONL files in a single directory."""
        entries = []
        for jsonl_path in sorted(directory.glob("*.jsonl")):
            if jsonl_path.name.startswith("agent-"):
                continue
            try:
                stat = jsonl_path.stat()
            except (PermissionError, OSError) as e:
                logger.debug("Skipping unreadable file %s: %s", jsonl_path, e)
                continue
            if stat.st_size == 0:
                continue
            entries.append(
                SessionEntry(
                    uuid=jsonl_path.stem,
                    mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    size_bytes=stat.st_size,
                    worktree_name=worktree_name,
                    git_branch=git_branch,
                )
            )
        return entries

    def discover_sessions(self, exclude_live: bool = True) -> list[SessionEntry]:
        """Find all session JSONL files in the project and worktree directories.

        Args:
            exclude_live: If True (default), skip sessions that are currently
                live according to ``~/.claude_karma/live-sessions/``. When hooks
                aren't configured the live-sessions dir won't exist, so no
                sessions are excluded — backward compatible.
        """
        live_uuids = _get_live_session_uuids() if exclude_live else set()

        # Detect git branch for the main project directory
        main_branch = _detect_git_branch(self.project_path)
        entries = self._discover_from_dir(self.project_dir, git_branch=main_branch)

        for extra_dir in self.extra_dirs:
            if not extra_dir.is_dir():
                continue
            wt_name = _extract_worktree_name(extra_dir.name, self.project_dir.name)

            # For worktrees, construct the real worktree path from the project path
            wt_branch: Optional[str] = None
            if wt_name:
                wt_path = Path(self.project_path) / ".claude" / "worktrees" / wt_name
                if wt_path.is_dir():
                    wt_branch = _detect_git_branch(str(wt_path))
                if wt_branch is None:
                    # Fallback: try .worktrees/ (alternate location)
                    wt_path_alt = Path(self.project_path) / ".worktrees" / wt_name
                    if wt_path_alt.is_dir():
                        wt_branch = _detect_git_branch(str(wt_path_alt))

            entries.extend(
                self._discover_from_dir(extra_dir, worktree_name=wt_name, git_branch=wt_branch)
            )

        if live_uuids:
            before = len(entries)
            entries = [e for e in entries if e.uuid not in live_uuids]
            skipped = before - len(entries)
            if skipped:
                logger.info("Excluded %d live session(s) from packaging", skipped)

        return entries

    def _source_dir_for_session(self, entry: SessionEntry) -> Path:
        """Find the directory containing the session's JSONL file."""
        if (self.project_dir / f"{entry.uuid}.jsonl").exists():
            return self.project_dir
        for extra_dir in self.extra_dirs:
            if (extra_dir / f"{entry.uuid}.jsonl").exists():
                return extra_dir
        return self.project_dir  # fallback

    def package(self, staging_dir: Path, session_limit: str = "all") -> SyncManifest:
        """Copy session files into staging directory and create manifest."""
        sessions = self.discover_sessions()

        # Apply session limit (disk space aware, with per-device metadata override)
        limit = get_session_limit(
            session_limit, staging_dir,
            team_name=self.team_name, member_tag=self.member_tag,
        )
        if limit is not None and len(sessions) > limit:
            # Sort by mtime descending (most recent first), take top N
            sessions.sort(key=lambda s: s.mtime, reverse=True)
            sessions = sessions[:limit]

        sessions_dir = staging_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        for entry in sessions:
            source_dir = self._source_dir_for_session(entry)

            # Copy JSONL file (skip if unchanged)
            src_jsonl = source_dir / f"{entry.uuid}.jsonl"
            dst_jsonl = sessions_dir / src_jsonl.name
            if not dst_jsonl.exists() or src_jsonl.stat().st_mtime > dst_jsonl.stat().st_mtime:
                try:
                    shutil.copy2(src_jsonl, dst_jsonl)
                except (PermissionError, OSError) as e:
                    logger.warning("Failed to copy %s: %s", src_jsonl, e)
                    continue

            # Copy associated directories (subagents, tool-results)
            assoc_dir = source_dir / entry.uuid
            if assoc_dir.is_dir():
                try:
                    shutil.copytree(
                        assoc_dir,
                        sessions_dir / entry.uuid,
                        dirs_exist_ok=True,
                    )
                except (PermissionError, OSError) as e:
                    logger.warning("Failed to copy directory %s: %s", assoc_dir, e)

        # Copy todos (glob pattern: {uuid}-*.json)
        todos_base = self._claude_base / "todos"
        if todos_base.is_dir():
            todos_staging = staging_dir / "todos"
            for session_entry in sessions:
                for todo_file in todos_base.glob(f"{session_entry.uuid}-*.json"):
                    todos_staging.mkdir(exist_ok=True)
                    try:
                        shutil.copy2(todo_file, todos_staging / todo_file.name)
                    except (PermissionError, OSError) as e:
                        logger.warning("Failed to copy %s: %s", todo_file, e)

        # Copy per-session directories (tasks, file-history)
        for resource_name in ("tasks", "file-history"):
            resource_base = self._claude_base / resource_name
            if resource_base.is_dir():
                resource_staging = staging_dir / resource_name
                for session_entry in sessions:
                    src_dir = resource_base / session_entry.uuid
                    if src_dir.is_dir():
                        resource_staging.mkdir(exist_ok=True)
                        try:
                            shutil.copytree(
                                src_dir,
                                resource_staging / session_entry.uuid,
                                dirs_exist_ok=True,
                            )
                        except (PermissionError, OSError) as e:
                            logger.warning("Failed to copy directory %s: %s", src_dir, e)

        # Copy debug logs (single file: {uuid}.txt)
        debug_base = self._claude_base / "debug"
        if debug_base.is_dir():
            debug_staging = staging_dir / "debug"
            for session_entry in sessions:
                debug_file = debug_base / f"{session_entry.uuid}.txt"
                if debug_file.is_file():
                    debug_staging.mkdir(exist_ok=True)
                    try:
                        shutil.copy2(debug_file, debug_staging / debug_file.name)
                    except (PermissionError, OSError) as e:
                        logger.warning("Failed to copy %s: %s", debug_file, e)

        # Discover and copy referenced plans (best-effort)
        try:
            session_jsonls = [
                (entry.uuid, self._source_dir_for_session(entry) / f"{entry.uuid}.jsonl")
                for entry in sessions
            ]
            plan_refs = _discover_plan_references(session_jsonls)

            if plan_refs:
                plans_base = self._claude_base / "plans"
                plans_staging = staging_dir / "plans"
                copied_slugs = []

                for slug in plan_refs:
                    src_plan = plans_base / f"{slug}.md"
                    if src_plan.is_file():
                        plans_staging.mkdir(exist_ok=True)
                        dst_plan = plans_staging / f"{slug}.md"
                        if not dst_plan.exists() or src_plan.stat().st_mtime > dst_plan.stat().st_mtime:
                            shutil.copy2(src_plan, dst_plan)
                        copied_slugs.append(slug)

                # Write plans-index.json sidecar
                if copied_slugs:
                    plans_index = {
                        "version": 1,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "plans": {
                            slug: {"sessions": plan_refs[slug]}
                            for slug in copied_slugs
                        },
                    }
                    index_path = staging_dir / "plans-index.json"
                    index_path.write_text(
                        json.dumps(plans_index, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    logger.debug("Packaged %d plans for sync", len(copied_slugs))
        except Exception as e:
            logger.debug("Plan packaging failed (best-effort): %s", e)

        # Detect git identity for cross-machine project matching
        from utils.git import detect_git_identity

        git_id = detect_git_identity(self.project_path)

        # Build skill classifications from the metadata DB.
        # The exporting machine has already indexed sessions with correct
        # classifications — reuse that instead of re-scanning JSONL files.
        skill_classifications = _build_skill_classifications_from_db(
            [entry.uuid for entry in sessions]
        )

        # Build skill definitions from the local filesystem (best-effort).
        # Resolves each skill in skill_classifications to its SKILL.md file
        # and includes the content in the manifest for reliable remote import.
        try:
            skill_definitions = _build_skill_definitions(
                skill_classifications, self._claude_base
            )
        except Exception as e:
            logger.debug("Skill definitions packaging failed (best-effort): %s", e)
            skill_definitions = {}

        # Derive human-readable project name for manifest
        # Prefer: directory name from project path > proj_suffix > encoded name
        _project_name = Path(self.project_path).name if self.project_path else self.proj_suffix

        # Build manifest
        manifest = SyncManifest(
            user_id=self.user_id,
            machine_id=self.machine_id,
            member_tag=self.member_tag,
            device_id=self.device_id,
            project_path=self.project_path,
            project_encoded=self.project_dir.name,
            session_count=len(sessions),
            sessions=sessions,

            git_identity=git_id,
            team_name=self.team_name,
            proj_suffix=self.proj_suffix,
            project_name=_project_name,
            skill_classifications=skill_classifications,
            skill_definitions=skill_definitions,
        )

        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")

        # Backfill titles.json from DB (merges with any existing hook-written titles)
        try:
            from services.titles_io import write_titles_bulk

            titles_path = staging_dir / "titles.json"
            db_titles = _build_titles_from_db([entry.uuid for entry in sessions])
            write_titles_bulk(titles_path, db_titles)
        except Exception as e:
            logger.debug("titles.json backfill failed (best-effort): %s", e)

        return manifest
