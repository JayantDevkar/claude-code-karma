"""
Extra session roots: merge other machines' Claude Code sessions into this dashboard.

Karma reads ``~/.claude/projects`` on this machine. Users who sync the
``~/.claude`` dir of other machines here (Syncthing, OneDrive, rsync, ...)
list those copies as *extra roots*::

    CLAUDE_KARMA_EXTRA_ROOTS='[{"name": "laptop", "path": "D:/Sync/laptop/.claude"}]'

or in ``~/.claude_karma/extra-roots.json`` (same list). Karma does not sync
anything itself; it only reads what the user's sync tool put there.

A remote project dir is shown under a *canonical* encoded name: a local
project when one matches, else its own name (a remote-only project).
Matching, first hit wins:

1. ``project_map`` in the root config: explicit ``{remote_encoded: local_encoded}``.
2. Sidecar identity: ``karma-project.json`` in the project dir, written by the
   ``project_identity`` hook or by Karma's indexer on the remote machine.
   Matched on (git identity, subdir within the repo).
3. ``path_map`` prefix rewrites applied to the remote project path.
4. Same encoded name locally (identical path on both machines).
5. ``match_by_name`` (default off): exactly one local project with the same
   folder name. Flagged as a guess.

Unmatched dirs stay standalone; two roots with the same standalone name merge.

Karma writes sidecars into local project dirs only while at least one root is
configured; machines that only publish use the ``project_identity`` hook.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

SIDECAR_NAME = "karma-project.json"
_SIDECAR_STR_FIELDS = ("git_identity", "subdir", "project_path")
ROOTS_FILE_NAME = "extra-roots.json"

_ROOT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_CACHE_TTL = 30.0


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


@dataclass(frozen=True)
class SessionRoot:
    """A synced copy of another machine's ``~/.claude`` dir."""

    name: str
    claude_base: Path
    path_map: tuple[tuple[str, str], ...] = ()
    project_map: tuple[tuple[str, str], ...] = ()
    match_by_name: bool = False
    # claude_base resolved once at load time; root_for_path runs per session file
    resolved_base: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.resolved_base is None:
            object.__setattr__(self, "resolved_base", _resolve(self.claude_base))

    @property
    def projects_dir(self) -> Path:
        return self.claude_base / "projects"

    @property
    def base(self) -> Path:
        return self.resolved_base or self.claude_base


@dataclass(frozen=True)
class RemoteDir:
    """One project dir inside an extra root, mapped to the project it shows under."""

    root: SessionRoot
    path: Path
    canonical: str
    # project_map, sidecar, path_map, same_name, worktree, folder_name (a guess) or standalone
    matched_by: str
    remote_project_path: Optional[str] = None

    @property
    def merged(self) -> bool:
        return self.matched_by != "standalone"


@dataclass
class _State:
    built_at: float = 0.0
    roots: tuple[SessionRoot, ...] = ()
    remote_dirs: tuple[RemoteDir, ...] = ()
    by_canonical: dict[str, list[RemoteDir]] = field(default_factory=dict)
    # False when the last load failed (``roots`` is then the previous list) or rejected an entry
    config_ok: bool = True


_state = _State()
_lock = threading.Lock()
_generation = 0  # bumped by clear_cache()/invalidate(); an older in-flight build is discarded
_build_lock = threading.Lock()  # one rebuild at a time; others serve the previous mapping


# =============================================================================
# Root configuration
# =============================================================================


def _norm_prefix(path: str) -> str:
    return path.replace("\\", "/").rstrip("/")


def _parse_root(entry: object) -> Optional[SessionRoot]:
    if isinstance(entry, str):
        entry = {"path": entry}
    if not isinstance(entry, dict) or not entry.get("path"):
        logger.warning("Ignoring extra root without a path: %r", entry)
        return None

    path = Path(os.path.expanduser(str(entry["path"])))
    # Accept the .claude dir itself or its projects/ subdir
    base = path.parent if path.name == "projects" and not (path / "projects").is_dir() else path

    name = str(entry.get("name") or base.parent.name or base.name)
    if not _ROOT_NAME_RE.match(name) or name.lower() == "local":
        logger.warning("Ignoring extra root with invalid name %r (use letters, digits, ._-)", name)
        return None

    raw_path_map = entry.get("path_map") or {}
    raw_project_map = entry.get("project_map") or {}
    if not isinstance(raw_path_map, dict) or not isinstance(raw_project_map, dict):
        logger.warning("Ignoring extra root %r: path_map/project_map must be objects", name)
        return None
    path_map = []
    for src, dst in raw_path_map.items():
        src_prefix = _norm_prefix(str(src)) if src else ""
        if not src_prefix or not dst:
            # "/" would normalise to "" and match every remote path
            logger.warning("Ignoring path_map entry %r in extra root %r", src, name)
            continue
        path_map.append((src_prefix, _norm_prefix(str(dst))))
    # Longest prefix first so nested mappings win
    path_map.sort(key=lambda kv: len(kv[0]), reverse=True)
    project_map = tuple((str(k), str(v)) for k, v in raw_project_map.items() if k and v)

    return SessionRoot(
        name=name,
        claude_base=base,
        path_map=tuple(path_map),
        project_map=project_map,
        match_by_name=bool(entry.get("match_by_name", False)),
    )


def roots_file() -> Path:
    """User-editable roots list, alongside the settings/env ``extra_roots``."""
    return settings.karma_base / ROOTS_FILE_NAME


def _load_root_entries() -> list:
    """Configured root entries. Raises when the env value or roots file is malformed.

    A mid-edit or corrupt file must not look like "no roots": the indexer would
    then drop every synced session as belonging to a removed root.
    """
    entries = settings.extra_roots or []
    if isinstance(entries, str):  # raw CLAUDE_KARMA_EXTRA_ROOTS value
        entries = json.loads(entries)
    if not isinstance(entries, list):
        raise ValueError("CLAUDE_KARMA_EXTRA_ROOTS must hold a JSON list")
    entries = list(entries)
    path = roots_file()
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{path} must hold a JSON list")
        entries.extend(data)
    return entries


def _is_within(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _load_roots() -> tuple[tuple[SessionRoot, ...], bool]:
    """Valid roots, and False if any entry was rejected (its sessions must not look removed)."""
    local = _resolve(settings.claude_base)
    roots: list[SessionRoot] = []
    seen_names: set[str] = set()
    seen_paths: set[Path] = set()
    entries = _load_root_entries()
    for entry in entries:
        try:
            root = _parse_root(entry)
        except Exception as e:  # one bad entry must not break session loading
            logger.warning("Ignoring invalid extra root %r: %s", entry, e)
            continue
        if root is None:
            continue
        if root.name in seen_names:
            logger.warning("Ignoring duplicate extra root name %r", root.name)
            continue
        if root.base in seen_paths:
            logger.warning("Ignoring extra root %r: same path as an earlier root", root.name)
            continue
        if _is_within(root.base, local) or _is_within(local, root.base):
            logger.warning("Ignoring extra root %r: overlaps this machine's ~/.claude", root.name)
            continue
        if root.claude_base.is_file():
            logger.warning("Ignoring extra root %r: %s is a file", root.name, root.claude_base)
            continue
        seen_names.add(root.name)
        seen_paths.add(root.base)
        roots.append(root)
    return tuple(roots), len(roots) == len(entries)


# =============================================================================
# Sidecar identity files
# =============================================================================


def read_sidecar(project_dir: Path) -> Optional[dict]:
    """Read ``karma-project.json`` from a project dir; None if missing or invalid."""
    try:
        data = json.loads((project_dir / SIDECAR_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    # Synced from other machines: drop fields of the wrong type instead of failing later
    return {k: v for k, v in data.items() if k not in _SIDECAR_STR_FIELDS or isinstance(v, str)}


def compute_subdir(project_path: Optional[str], git_root: Optional[str]) -> Optional[str]:
    """Project path relative to its git root, '/'-separated; '' at the root.

    None when the path is not inside the root: a guessed '' would merge the
    project into its repo root on other machines.
    """
    if not project_path or not git_root:
        return None
    p = _norm_prefix(project_path)
    r = _norm_prefix(git_root)
    if p.lower() == r.lower():
        return ""
    if p.lower().startswith(r.lower() + "/"):
        return p[len(r) + 1 :]
    return None


def write_sidecar(
    project_dir: Path,
    git_identity: Optional[str],
    project_path: Optional[str],
    git_root: Optional[str],
) -> None:
    """Write the sidecar if its content changed. Never raises."""
    if not git_identity or not project_dir.is_dir():
        return
    subdir = compute_subdir(project_path, git_root)
    if subdir is None:
        if git_root:
            # Path is outside its repo: drop a sidecar an older version wrote with subdir ""
            try:
                (project_dir / SIDECAR_NAME).unlink()
            except OSError:
                pass
        return
    data = {
        "git_identity": git_identity,
        "subdir": subdir,
        "project_path": project_path,
    }
    existing = read_sidecar(project_dir)
    if existing and all(existing.get(k) == v for k, v in data.items()):
        return
    data["written_by"] = "karma-api"
    target = project_dir / SIDECAR_NAME
    tmp = project_dir / f".{SIDECAR_NAME}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    except OSError as e:
        logger.debug("Cannot write sidecar in %s: %s", project_dir, e)
        try:
            tmp.unlink()
        except OSError:
            pass


def _identity_key(sidecar: Optional[dict]) -> Optional[tuple[str, str]]:
    if not sidecar or not sidecar.get("git_identity"):
        return None
    subdir = str(sidecar.get("subdir") or "").replace("\\", "/").strip("/").lower()
    return (str(sidecar["git_identity"]).lower(), subdir)


# =============================================================================
# Mapping
# =============================================================================


_WINDOWS_PREFIX_RE = re.compile(r"^(?:[A-Za-z]:(?:/|$)|//)")  # "C:" after _norm_prefix("C:/")


def _apply_path_map(path: str, path_map: tuple[tuple[str, str], ...]) -> Optional[str]:
    p = _norm_prefix(path)
    for src, dst in path_map:
        # Windows paths (drive or UNC) are case-insensitive; POSIX ones are not
        fold = _WINDOWS_PREFIX_RE.match(src) is not None
        haystack, prefix = (p.lower(), src.lower()) if fold else (p, src)
        if haystack == prefix or haystack.startswith(prefix + "/"):
            return dst + p[len(src) :]
    return None


def _folder_name(path: Optional[str]) -> str:
    return PurePosixPath(_norm_prefix(path or "")).name.lower()


def _local_index() -> tuple[
    dict[str, str], dict[tuple[str, str], str], dict[str, list[tuple[str, Optional[str]]]]
]:
    """Index local project dirs: by lowercased name, by sidecar identity, by folder name."""
    from models.project import Project
    from services.desktop_sessions import is_worktree_project
    from utils import is_encoded_project_dir

    by_lower: dict[str, str] = {}
    by_identity: dict[tuple[str, str], str] = {}
    ambiguous: set[tuple[str, str]] = set()  # identity claimed by two local clones
    # folder name -> [(encoded name, git identity or None)]
    by_folder: dict[str, list[tuple[str, Optional[str]]]] = {}

    local_dir = settings.projects_dir
    if not local_dir.is_dir():
        return by_lower, by_identity, by_folder

    for d in local_dir.iterdir():
        if not d.is_dir() or not is_encoded_project_dir(d.name) or is_worktree_project(d.name):
            continue
        by_lower[d.name.lower()] = d.name
        sidecar = read_sidecar(d)
        key = _identity_key(sidecar)
        if key:
            if key in by_identity:
                ambiguous.add(key)
            else:
                by_identity[key] = d.name
        path = (sidecar or {}).get("project_path") or Project._extract_real_path_from_sessions(d)
        if path:
            by_folder.setdefault(_folder_name(path), []).append((d.name, key[0] if key else None))
    for key in ambiguous:
        del by_identity[key]
    return by_lower, by_identity, by_folder


def _build(roots: tuple[SessionRoot, ...]) -> tuple[RemoteDir, ...]:
    from models.project import Project
    from services.desktop_sessions import (
        _extract_project_prefix_from_worktree,
        is_worktree_project,
    )
    from utils import is_encoded_project_dir

    if not roots:
        return ()

    by_lower, by_identity, by_folder = _local_index()
    # Standalone remote projects: first root to claim an identity/name owns it
    standalone_by_identity: dict[tuple[str, str], str] = {}
    standalone_by_lower: dict[str, str] = {}

    result: list[RemoteDir] = []
    for root in roots:
        if not root.projects_dir.is_dir():
            logger.info("Extra root %r has no projects dir at %s", root.name, root.projects_dir)
            continue
        project_map = {k.lower(): v for k, v in root.project_map}

        try:
            dirs = [
                d
                for d in root.projects_dir.iterdir()
                if d.is_dir() and is_encoded_project_dir(d.name)
            ]
        except OSError as e:  # root went offline mid-scan
            logger.info("Cannot scan extra root %r: %s", root.name, e)
            continue
        # Main project dirs first, so worktree dirs can follow their project
        dirs.sort(key=lambda d: (is_worktree_project(d.name), d.name))
        canonical_by_dir: dict[str, str] = {}

        for d in dirs:
            try:
                sidecar = read_sidecar(d)
                key = _identity_key(sidecar)
                remote_path = (sidecar or {}).get("project_path") or (
                    Project._extract_real_path_from_sessions(d)
                )

                canonical: Optional[str] = None
                how = "standalone"

                mapped = project_map.get(d.name.lower())
                if mapped:
                    canonical, how = by_lower.get(mapped.lower(), mapped), "project_map"
                if canonical is None and key and key in by_identity:
                    canonical, how = by_identity[key], "sidecar"
                if canonical is None and remote_path and root.path_map:
                    rewritten = _apply_path_map(remote_path, root.path_map)
                    if rewritten:
                        hit = by_lower.get(Project.encode_path(rewritten).lower())
                        if hit:
                            canonical, how = hit, "path_map"
                if canonical is None and d.name.lower() in by_lower:
                    canonical, how = by_lower[d.name.lower()], "same_name"
                if canonical is None and is_worktree_project(d.name):
                    prefix = (_extract_project_prefix_from_worktree(d.name) or "").lower()
                    if prefix in canonical_by_dir:
                        canonical, how = canonical_by_dir[prefix], "worktree"
                    elif prefix in by_lower:
                        canonical, how = by_lower[prefix], "worktree"
                if canonical is None and root.match_by_name and remote_path:
                    candidates = by_folder.get(_folder_name(remote_path), [])
                    if len(candidates) == 1:
                        local_name, local_identity = candidates[0]
                        # Two known, different git remotes are different projects
                        if not (key and local_identity and key[0] != local_identity):
                            canonical, how = local_name, "folder_name"

                if canonical is None:
                    canonical = (
                        key and standalone_by_identity.get(key)
                    ) or standalone_by_lower.get(d.name.lower(), d.name)
                    standalone_by_lower.setdefault(d.name.lower(), canonical)
                    if key:
                        standalone_by_identity.setdefault(key, canonical)

                canonical_by_dir[d.name.lower()] = canonical
                result.append(
                    RemoteDir(
                        root=root,
                        path=d,
                        canonical=canonical,
                        matched_by=how,
                        remote_project_path=remote_path,
                    )
                )
            except Exception as e:  # one odd dir must not hide the whole root
                logger.warning("Skipping %s in extra root %r: %s", d.name, root.name, e)
    return tuple(result)


def _refresh(force: bool = False) -> _State:
    global _state
    now = time.time()
    state = _state
    if not force and state.built_at and now - state.built_at < _CACHE_TTL:
        return state
    # Someone else is rebuilding: serve the previous mapping, or wait if there is none
    if not _build_lock.acquire(blocking=force or not state.built_at):
        return state
    try:
        state = _state
        if not force and state.built_at and time.time() - state.built_at < _CACHE_TTL:
            return state  # built while we waited
        generation = _generation
        # Disk I/O happens outside _lock. On failure keep the last roots (see _load_root_entries)
        try:
            roots, config_ok = _load_roots()
        except Exception as e:
            logger.warning("Failed to load extra session roots, keeping the previous list: %s", e)
            roots, config_ok = state.roots, False
        try:
            remote_dirs = _build(roots)
        except Exception as e:  # never break local views over a bad remote
            logger.warning("Failed to map extra session roots: %s", e)
            remote_dirs = state.remote_dirs if roots == state.roots else ()
        by_canonical: dict[str, list[RemoteDir]] = {}
        for rd in remote_dirs:
            by_canonical.setdefault(rd.canonical, []).append(rd)
        new_state = _State(
            built_at=time.time(),
            roots=roots,
            remote_dirs=remote_dirs,
            by_canonical=by_canonical,
            config_ok=config_ok,
        )
        with _lock:
            stale = generation != _generation
            if not stale:
                _state = new_state
    finally:
        _build_lock.release()
    if stale:
        # clear_cache() ran mid-build: this result may reflect old config
        return _refresh()
    return new_state


def clear_cache() -> None:
    """Forget roots and mappings entirely (tests)."""
    global _state, _generation
    with _lock:
        _generation += 1
        _state = _State()


def invalidate() -> None:
    """Re-read the config and rescan on the next call, keeping the last roots as a fallback."""
    global _state, _generation
    with _lock:
        _generation += 1
        _state = _State(
            roots=_state.roots,
            remote_dirs=_state.remote_dirs,
            by_canonical=_state.by_canonical,
            config_ok=_state.config_ok,
        )


# =============================================================================
# Public API
# =============================================================================


def get_extra_roots() -> tuple[SessionRoot, ...]:
    return _refresh().roots


def roots_config_ok() -> bool:
    """False while the roots config fails to load or rejects an entry: no removed-root cleanup."""
    return _refresh().config_ok


def get_root(name: Optional[str]) -> Optional[SessionRoot]:
    """Extra root by name; None for the local machine or an unknown name."""
    if not name:
        return None
    return next((r for r in get_extra_roots() if r.name == name), None)


def projects_dir_for_root(name: Optional[str]) -> Optional[Path]:
    """Projects dir for a ``source_root`` value: local for None, None if unknown."""
    if not name:
        return settings.projects_dir
    root = get_root(name)
    return root.projects_dir if root else None


def get_remote_dirs() -> tuple[RemoteDir, ...]:
    return _refresh().remote_dirs


def remote_dirs_for(canonical: str) -> list[RemoteDir]:
    """Remote project dirs shown under this encoded name."""
    return list(_refresh().by_canonical.get(canonical, ()))


def standalone_canonicals() -> list[str]:
    """Encoded names of remote-only projects (no local dir)."""
    local = settings.projects_dir
    return [canonical for canonical in _refresh().by_canonical if not (local / canonical).is_dir()]


def primary_dir_for(canonical: str) -> Optional[RemoteDir]:
    """The remote dir standing in for a remote-only project's own dir."""
    dirs = remote_dirs_for(canonical)
    return dirs[0] if dirs else None


def iter_session_dirs(
    canonical: str, include_local: bool = True
) -> list[tuple[Optional[str], Path]]:
    """All (root name, dir) pairs holding sessions for a project; None = local."""
    out: list[tuple[Optional[str], Path]] = []
    if include_local:
        out.append((None, settings.projects_dir / canonical))
    out.extend((rd.root.name, rd.path) for rd in remote_dirs_for(canonical))
    return out


def find_remote_session_jsonl(canonical: str, uuid: str) -> Optional[Path]:
    """Find a session JSONL in the remote dirs mapped to a project."""
    for rd in remote_dirs_for(canonical):
        p = rd.path / f"{uuid}.jsonl"
        if p.exists():
            return p
    return None


def find_any_remote_session(uuid: str) -> Optional[tuple[RemoteDir, Path]]:
    """Find a session JSONL by UUID in any extra root."""
    for rd in get_remote_dirs():
        p = rd.path / f"{uuid}.jsonl"
        if p.exists():
            return rd, p
    return None


def session_jsonl_path(encoded_name: str, uuid: str) -> Path:
    """Path of a session JSONL shown under a project: local dir, else a synced copy.

    Returns the local path when no copy exists anywhere, so callers keep their
    existing "missing file" handling.
    """
    local = settings.projects_dir / encoded_name / f"{uuid}.jsonl"
    if local.exists():
        return local
    return find_remote_session_jsonl(encoded_name, uuid) or local


def project_dirs_for(encoded_name: str) -> list[Path]:
    """Every dir holding a project's data: local first, then synced copies."""
    return [d for _, d in iter_session_dirs(encoded_name)]


def root_for_path(path: Path) -> Optional[SessionRoot]:
    """The extra root a file lives under, or None for local/unknown paths."""
    roots = get_extra_roots()
    if not roots:
        return None
    try:
        resolved = Path(path).resolve()
    except OSError:
        return None
    for root in roots:
        if _is_within(resolved, root.base):
            return root
    return None


def machine_for_path(path: Optional[Path]) -> Optional[str]:
    """Extra root name a session file was synced from; None for this machine."""
    if path is None:
        return None
    root = root_for_path(path)
    return root.name if root else None


def claude_base_for_path(path: Path) -> Path:
    """The ``.claude`` dir a session file belongs to (todos, debug, tasks live there)."""
    root = root_for_path(path)
    return root.claude_base if root else settings.claude_base
