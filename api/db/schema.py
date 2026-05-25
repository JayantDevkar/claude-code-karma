"""
SQLite schema definitions and migration support.

All tables use CREATE TABLE IF NOT EXISTS for idempotent schema creation.
A schema_version table tracks applied migrations for future upgrades.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 13

SCHEMA_SQL = """
-- Schema versioning
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- Core session metadata (replaces sessions-index.json + in-memory aggregation)
CREATE TABLE IF NOT EXISTS sessions (
    uuid TEXT PRIMARY KEY,
    slug TEXT,
    project_encoded_name TEXT NOT NULL,
    project_path TEXT,
    start_time TEXT,
    end_time TEXT,
    message_count INTEGER DEFAULT 0,
    duration_seconds REAL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0,
    initial_prompt TEXT,
    git_branch TEXT,
    models_used TEXT,
    session_titles TEXT,
    is_continuation_marker INTEGER DEFAULT 0,
    was_compacted INTEGER DEFAULT 0,
    compaction_count INTEGER DEFAULT 0,
    file_snapshot_count INTEGER DEFAULT 0,
    subagent_count INTEGER DEFAULT 0,
    jsonl_mtime REAL NOT NULL,
    jsonl_size INTEGER DEFAULT 0,
    session_source TEXT,
    source_encoded_name TEXT,
    indexed_at TEXT DEFAULT (datetime('now')),
    -- Per-session flag set to 1 when a session needs the bg-shells/cron
    -- extraction pass (v13). Cleared by the indexer after processing.
    -- Avoids touching jsonl_mtime which other consumers depend on.
    needs_shell_cron_reindex INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_encoded_name);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_slug ON sessions(slug);
CREATE INDEX IF NOT EXISTS idx_sessions_branch ON sessions(project_encoded_name, git_branch);
CREATE INDEX IF NOT EXISTS idx_sessions_mtime ON sessions(jsonl_mtime);

-- Full-text search (FTS5)
-- This is an external content FTS5 table (content=sessions) that mirrors the sessions table.
-- Triggers below keep it in sync with INSERT, UPDATE, DELETE operations on sessions.
-- If the FTS index becomes out of sync with the sessions table, rebuild with:
--   INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild');
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    uuid,
    slug,
    initial_prompt,
    session_titles,
    project_path,
    content=sessions,
    content_rowid=rowid
);

-- Triggers to keep FTS in sync with sessions table
CREATE TRIGGER IF NOT EXISTS sessions_fts_insert AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, uuid, slug, initial_prompt, session_titles, project_path)
    VALUES (new.rowid, new.uuid, new.slug, new.initial_prompt, new.session_titles, new.project_path);
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_delete AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, uuid, slug, initial_prompt, session_titles, project_path)
    VALUES ('delete', old.rowid, old.uuid, old.slug, old.initial_prompt, old.session_titles, old.project_path);
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_update AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, uuid, slug, initial_prompt, session_titles, project_path)
    VALUES ('delete', old.rowid, old.uuid, old.slug, old.initial_prompt, old.session_titles, old.project_path);
    INSERT INTO sessions_fts(rowid, uuid, slug, initial_prompt, session_titles, project_path)
    VALUES (new.rowid, new.uuid, new.slug, new.initial_prompt, new.session_titles, new.project_path);
END;

-- Tool usage per session (denormalized for fast aggregation)
CREATE TABLE IF NOT EXISTS session_tools (
    session_uuid TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, tool_name),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tools_name ON session_tools(tool_name);

-- Skill usage per session
-- invocation_source: 'slash_command' (user typed /), 'skill_tool' (Claude auto-invoked), 'text_detection' (regex fallback)
CREATE TABLE IF NOT EXISTS session_skills (
    session_uuid TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, skill_name, invocation_source),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_skills_name ON session_skills(skill_name);
CREATE INDEX IF NOT EXISTS idx_skills_source ON session_skills(invocation_source);

-- Command usage per session
-- invocation_source: 'slash_command' (user typed /), 'skill_tool' (Claude invoked), 'text_detection' (regex fallback)
CREATE TABLE IF NOT EXISTS session_commands (
    session_uuid TEXT NOT NULL,
    command_name TEXT NOT NULL,
    invocation_source TEXT NOT NULL DEFAULT 'slash_command',
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, command_name, invocation_source),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_commands_name ON session_commands(command_name);
CREATE INDEX IF NOT EXISTS idx_commands_source ON session_commands(invocation_source);

-- Subagent invocations (replaces AgentUsageIndex)
CREATE TABLE IF NOT EXISTS subagent_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    subagent_type TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    started_at TEXT,
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subagent_session ON subagent_invocations(session_uuid);
CREATE INDEX IF NOT EXISTS idx_subagent_type ON subagent_invocations(subagent_type);
CREATE INDEX IF NOT EXISTS idx_subagent_type_time ON subagent_invocations(subagent_type, started_at DESC);

-- Tool usage per subagent invocation
CREATE TABLE IF NOT EXISTS subagent_tools (
    invocation_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    count INTEGER DEFAULT 1,
    PRIMARY KEY (invocation_id, tool_name),
    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subagent_tools_invocation ON subagent_tools(invocation_id);

-- Skill usage per subagent invocation
CREATE TABLE IF NOT EXISTS subagent_skills (
    invocation_id INTEGER NOT NULL,
    skill_name TEXT NOT NULL,
    invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
    count INTEGER DEFAULT 1,
    PRIMARY KEY (invocation_id, skill_name, invocation_source),
    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subagent_skills_invocation ON subagent_skills(invocation_id);
CREATE INDEX IF NOT EXISTS idx_subagent_skills_name ON subagent_skills(skill_name);

-- Command usage per subagent invocation
CREATE TABLE IF NOT EXISTS subagent_commands (
    invocation_id INTEGER NOT NULL,
    command_name TEXT NOT NULL,
    invocation_source TEXT NOT NULL DEFAULT 'slash_command',
    count INTEGER DEFAULT 1,
    PRIMARY KEY (invocation_id, command_name, invocation_source),
    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subagent_commands_invocation ON subagent_commands(invocation_id);
CREATE INDEX IF NOT EXISTS idx_subagent_commands_name ON subagent_commands(command_name);

-- Message UUID to session mapping (for fast continuation lookup)
CREATE TABLE IF NOT EXISTS message_uuids (
    message_uuid TEXT PRIMARY KEY,
    session_uuid TEXT NOT NULL,
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_message_session ON message_uuids(session_uuid);

-- Session leaf_uuid references (for chain detection via leaf_uuid)
CREATE TABLE IF NOT EXISTS session_leaf_refs (
    session_uuid TEXT NOT NULL,
    leaf_uuid TEXT NOT NULL,
    PRIMARY KEY (session_uuid, leaf_uuid),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leaf_refs_leaf ON session_leaf_refs(leaf_uuid);

-- Project summary (derived, for fast project listing)
CREATE TABLE IF NOT EXISTS projects (
    encoded_name TEXT PRIMARY KEY,
    project_path TEXT,
    slug TEXT,
    display_name TEXT,
    session_count INTEGER DEFAULT 0,
    last_activity TEXT,
    -- git_identity: canonical `owner/repo` lowercase, derived from
    -- `git -C project_path config --get remote.origin.url`. NULL when
    -- the project has no local git remote (sync-imported, never inited).
    -- Used by ticket queries to aggregate across encoded_names that
    -- represent the same logical repo (worktrees, subdir projects, etc.).
    git_identity TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_git_identity ON projects(git_identity);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug);
"""

# Ticket tables — extracted into a separate constant so they can be applied
# UNCONDITIONALLY at ensure_schema() time, regardless of the recorded
# SCHEMA_VERSION. This protects against cross-branch DB drift: if a karma
# DB has been used on a parallel branch whose linear SCHEMA_VERSION ran
# ahead of ours, the early-return version gate would otherwise skip our
# v11 migration block and leave us with no ticket tables. CREATE TABLE IF
# NOT EXISTS makes the unconditional run safe on every install path.
_TICKETS_SCHEMA_SQL = """
-- Ticket registry: de-duped per (provider, external_key).
-- Populated by the agent (via MCP) at slash-command link time, or empty
-- (URL-only) when the link comes from the branch-detect hook or dashboard.
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL CHECK (provider IN ('linear','jira','github')),
    external_key TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    status TEXT,
    metadata_json TEXT CHECK (metadata_json IS NULL OR length(metadata_json) <= 65536),
    metadata_updated_at TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(provider, external_key)
);

CREATE INDEX IF NOT EXISTS idx_tickets_provider ON tickets(provider);

-- Many-to-many: a session can link to many tickets; a ticket can be linked
-- from many sessions. No FK on session_uuid because the branch-detect hook
-- writes at SessionStart, possibly before the JSONL indexer has created the
-- sessions row. Orphans are reaped periodically (see api/main.py lifespan).
CREATE TABLE IF NOT EXISTS session_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT NOT NULL,
    session_slug TEXT,
    ticket_id INTEGER NOT NULL,
    link_source TEXT NOT NULL CHECK (link_source IN ('branch','slash_command','dashboard')),
    linked_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
    UNIQUE(session_uuid, ticket_id)
);

CREATE INDEX IF NOT EXISTS idx_session_tickets_session ON session_tickets(session_uuid);
CREATE INDEX IF NOT EXISTS idx_session_tickets_slug    ON session_tickets(session_slug);
CREATE INDEX IF NOT EXISTS idx_session_tickets_ticket  ON session_tickets(ticket_id);

-- Partial unique index dedupes links across resumed sessions (resumes share
-- a slug but get fresh UUIDs). Skipped when slug isn't known at write time;
-- per-UUID UNIQUE above is the fallback.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_session_tickets_slug_ticket
    ON session_tickets(session_slug, ticket_id)
    WHERE session_slug IS NOT NULL;
"""

# Keep ticket tables in the canonical fresh-install schema too, so a
# brand-new DB still gets everything in one shot through SCHEMA_SQL.
SCHEMA_SQL = SCHEMA_SQL + _TICKETS_SCHEMA_SQL

# Background shells + cron tables (v13) — extracted into a separate constant
# so they can be applied UNCONDITIONALLY at ensure_schema() time, same
# cross-branch safety story as _TICKETS_SCHEMA_SQL above. All statements
# are CREATE … IF NOT EXISTS and therefore safe to re-run.
#
# Design notes:
#   - One row per logical entity (shell / cron job), keyed by tool_use_id
#     which is globally unique in Claude's JSONL.
#   - UPSERT (ON CONFLICT … DO UPDATE) is used in indexer writes — never
#     INSERT OR REPLACE — so the parent row's `id` is preserved and child
#     CASCADE deletes don't churn on re-index.
#   - cron_fires is intentionally absent: fire times are derived on read by
#     joining cron_jobs to message_uuids and assistant turn timestamps.
#     Avoids baking croniter's matching window into the DB.
_SHELLS_CRON_SCHEMA_SQL = """
-- Background shells: one row per spawned background Bash or Monitor process.
-- Reconstructed from JSONL by the indexer; represents immutable history.
CREATE TABLE IF NOT EXISTS background_shells (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid             TEXT    NOT NULL,
    tool_use_id              TEXT    NOT NULL,
    shell_id                 TEXT,
    tool_name                TEXT    NOT NULL CHECK (tool_name IN ('Bash','Monitor')),
    command                  TEXT    NOT NULL,
    command_truncated        INTEGER NOT NULL DEFAULT 0 CHECK (command_truncated IN (0,1)),
    description              TEXT,
    is_persistent            INTEGER NOT NULL DEFAULT 0 CHECK (is_persistent IN (0,1)),
    timeout_ms               INTEGER,
    spawned_at               TEXT    NOT NULL,
    terminated_at            TEXT,
    terminated_by            TEXT    CHECK (terminated_by IN ('kill','natural','timeout','session_end')),
    exit_code                INTEGER,
    poll_count               INTEGER NOT NULL DEFAULT 0,
    total_output_bytes       INTEGER NOT NULL DEFAULT 0,
    last_output_at           TEXT,
    spawn_message_uuid       TEXT,
    CHECK ((terminated_at IS NULL) = (terminated_by IS NULL)),
    FOREIGN KEY (session_uuid)       REFERENCES sessions(uuid)            ON DELETE CASCADE,
    FOREIGN KEY (spawn_message_uuid) REFERENCES message_uuids(message_uuid) ON DELETE SET NULL,
    UNIQUE(tool_use_id)
);

CREATE INDEX IF NOT EXISTS idx_bg_shells_session
    ON background_shells(session_uuid, spawned_at DESC);
CREATE INDEX IF NOT EXISTS idx_bg_shells_shell_id
    ON background_shells(shell_id) WHERE shell_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bg_shells_spawned
    ON background_shells(spawned_at DESC);

-- One row per BashOutput poll. Output excerpt stored inline (4KB); full
-- content remains in JSONL and is re-read on demand by router endpoints.
CREATE TABLE IF NOT EXISTS shell_polls (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    shell_row_id      INTEGER NOT NULL,
    polled_at         TEXT    NOT NULL,
    filter_pattern    TEXT,
    output_bytes      INTEGER NOT NULL DEFAULT 0,
    output_excerpt    TEXT,
    output_truncated  INTEGER NOT NULL DEFAULT 0 CHECK (output_truncated IN (0,1)),
    tool_use_id       TEXT    NOT NULL,
    FOREIGN KEY (shell_row_id) REFERENCES background_shells(id) ON DELETE CASCADE,
    UNIQUE(shell_row_id, tool_use_id)
);

CREATE INDEX IF NOT EXISTS idx_shell_polls_shell
    ON shell_polls(shell_row_id, polled_at DESC);

-- Cron jobs: one row per CronCreate tool_use. Reconstructed from JSONL.
-- deleted_at / deleted_via fold in CronDelete events; coherence CHECK
-- ensures the two NULL/non-NULL together.
CREATE TABLE IF NOT EXISTS cron_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid        TEXT    NOT NULL,
    tool_use_id         TEXT    NOT NULL,
    cron_id             TEXT,
    cron_expression     TEXT    NOT NULL,
    prompt              TEXT    NOT NULL,
    recurring           INTEGER NOT NULL DEFAULT 0 CHECK (recurring IN (0,1)),
    created_at          TEXT    NOT NULL,
    deleted_at          TEXT,
    deleted_via         TEXT    CHECK (deleted_via IN ('CronDelete','session_end','expiry','unknown')),
    ttl_expires_at      TEXT    NOT NULL,
    create_message_uuid TEXT,
    CHECK ((deleted_at IS NULL) = (deleted_via IS NULL)),
    FOREIGN KEY (session_uuid)        REFERENCES sessions(uuid)            ON DELETE CASCADE,
    FOREIGN KEY (create_message_uuid) REFERENCES message_uuids(message_uuid) ON DELETE SET NULL,
    UNIQUE(tool_use_id)
);

CREATE INDEX IF NOT EXISTS idx_cron_jobs_session
    ON cron_jobs(session_uuid, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_cron_id
    ON cron_jobs(cron_id) WHERE cron_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cron_jobs_active
    ON cron_jobs(ttl_expires_at) WHERE deleted_at IS NULL;

-- Cron live-state snapshots: optional, populated by cron_state_capture.py
-- hook on every CronCreate/CronDelete/CronList tool call. payload_json
-- holds the raw CronList result so the schema doesn't need to track
-- Claude's internal cron representation.
CREATE TABLE IF NOT EXISTS cron_state_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid    TEXT    NOT NULL,
    captured_at     TEXT    NOT NULL,
    trigger_event   TEXT    NOT NULL CHECK (trigger_event IN ('CronCreate','CronDelete','CronList','session_start')),
    payload_json    TEXT    NOT NULL,
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE,
    UNIQUE(session_uuid, trigger_event, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_cron_state_session
    ON cron_state_snapshots(session_uuid, captured_at DESC);
"""

# Append to canonical fresh-install schema.
SCHEMA_SQL = SCHEMA_SQL + _SHELLS_CRON_SCHEMA_SQL


def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create tables and indexes if they don't exist.

    Idempotent — safe to call on every startup.
    """
    # Cross-branch safety: always run the ticket-tables block. If a karma
    # DB has a recorded SCHEMA_VERSION higher than ours (e.g., from a
    # parallel branch with more migrations), the early-return below would
    # otherwise skip our v11 work and leave ticket endpoints broken. The
    # CREATE TABLE IF NOT EXISTS statements make this a no-op when the
    # tables already exist.
    conn.executescript(_TICKETS_SCHEMA_SQL)

    # Same cross-branch guard for v13 bg-shells/cron tables. All statements
    # inside are CREATE … IF NOT EXISTS so re-running is a no-op. The
    # sessions.needs_shell_cron_reindex ALTER is handled separately in the
    # v13 incremental block below (ALTER is not idempotent).
    conn.executescript(_SHELLS_CRON_SCHEMA_SQL)

    # Check current version
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current_version = row[0] if row and row[0] else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        current_version = 0

    if current_version >= SCHEMA_VERSION:
        logger.debug("Schema is up to date (version %d)", current_version)
        return

    logger.info(
        "Applying schema version %d (current: %d)",
        SCHEMA_VERSION,
        current_version,
    )

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")

    if current_version == 0:
        # Fresh install: apply full schema
        conn.executescript(SCHEMA_SQL)
    else:
        # Incremental migrations
        if current_version < 2:
            logger.info("Migrating v1 → v2: adding subagent_tools table")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS subagent_tools (
                    invocation_id INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (invocation_id, tool_name),
                    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_subagent_tools_invocation ON subagent_tools(invocation_id);
            """)

        if current_version < 3:
            logger.info("Migrating v2 → v3: adding message_uuids table")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS message_uuids (
                    message_uuid TEXT PRIMARY KEY,
                    session_uuid TEXT NOT NULL,
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_message_session ON message_uuids(session_uuid);
            """)

        if current_version < 4:
            logger.info("Migrating v3 → v4: adding session_leaf_refs table")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS session_leaf_refs (
                    session_uuid TEXT NOT NULL,
                    leaf_uuid TEXT NOT NULL,
                    PRIMARY KEY (session_uuid, leaf_uuid),
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_leaf_refs_leaf ON session_leaf_refs(leaf_uuid);
            """)

        if current_version < 5:
            logger.info("Migrating v4 → v5: adding message_uuid index for chain BFS joins")
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_message_uuid ON message_uuids(message_uuid);
            """)

        if current_version < 6:
            logger.info("Migrating v5 → v6: adding slug/display_name to projects")
            existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
            if "slug" not in existing_cols:
                conn.execute("ALTER TABLE projects ADD COLUMN slug TEXT")
            if "display_name" not in existing_cols:
                conn.execute("ALTER TABLE projects ADD COLUMN display_name TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug)")

        if current_version < 7:
            logger.info("Migrating v6 → v7: worktree consolidation + session_source")
            existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
            if "session_source" not in existing_cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN session_source TEXT")
            if "source_encoded_name" not in existing_cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN source_encoded_name TEXT")

            # Delete worktree sessions and projects (forces re-index under real project)
            conn.execute(
                "DELETE FROM sessions WHERE project_encoded_name LIKE '%claude-worktrees%'"
            )
            conn.execute("DELETE FROM projects WHERE encoded_name LIKE '%claude-worktrees%'")

        if current_version < 8:
            logger.info("Migrating v7 → v8: adding subagent_skills and subagent_commands tables")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS subagent_skills (
                    invocation_id INTEGER NOT NULL,
                    skill_name TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (invocation_id, skill_name),
                    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_subagent_skills_invocation ON subagent_skills(invocation_id);
                CREATE INDEX IF NOT EXISTS idx_subagent_skills_name ON subagent_skills(skill_name);

                CREATE TABLE IF NOT EXISTS subagent_commands (
                    invocation_id INTEGER NOT NULL,
                    command_name TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (invocation_id, command_name),
                    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_subagent_commands_invocation ON subagent_commands(invocation_id);
                CREATE INDEX IF NOT EXISTS idx_subagent_commands_name ON subagent_commands(command_name);
            """)
            # Force re-index of subagent data so skills/commands get populated
            conn.execute("DELETE FROM subagent_tools")
            conn.execute("DELETE FROM subagent_invocations")
            # Nudge mtime so the indexer picks up sessions with subagents
            conn.execute(
                "UPDATE sessions SET jsonl_mtime = jsonl_mtime - 1 WHERE subagent_count > 0"
            )

        if current_version < 9:
            logger.info(
                "Migrating → v9: invocation source tracking, plugin name normalization, "
                "worktree session resolution"
            )
            # Recreate skill/command tables with new PK that includes invocation_source.
            # SQLite doesn't support ALTER TABLE to change PK, so drop & recreate.
            conn.executescript("""
                DROP TABLE IF EXISTS session_skills;
                CREATE TABLE session_skills (
                    session_uuid TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (session_uuid, skill_name, invocation_source),
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_skills_name ON session_skills(skill_name);
                CREATE INDEX IF NOT EXISTS idx_skills_source ON session_skills(invocation_source);

                DROP TABLE IF EXISTS session_commands;
                CREATE TABLE session_commands (
                    session_uuid TEXT NOT NULL,
                    command_name TEXT NOT NULL,
                    invocation_source TEXT NOT NULL DEFAULT 'slash_command',
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (session_uuid, command_name, invocation_source),
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_commands_name ON session_commands(command_name);
                CREATE INDEX IF NOT EXISTS idx_commands_source ON session_commands(invocation_source);

                DROP TABLE IF EXISTS subagent_skills;
                CREATE TABLE subagent_skills (
                    invocation_id INTEGER NOT NULL,
                    skill_name TEXT NOT NULL,
                    invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (invocation_id, skill_name, invocation_source),
                    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_subagent_skills_invocation ON subagent_skills(invocation_id);
                CREATE INDEX IF NOT EXISTS idx_subagent_skills_name ON subagent_skills(skill_name);

                DROP TABLE IF EXISTS subagent_commands;
                CREATE TABLE subagent_commands (
                    invocation_id INTEGER NOT NULL,
                    command_name TEXT NOT NULL,
                    invocation_source TEXT NOT NULL DEFAULT 'slash_command',
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (invocation_id, command_name, invocation_source),
                    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_subagent_commands_invocation ON subagent_commands(invocation_id);
                CREATE INDEX IF NOT EXISTS idx_subagent_commands_name ON subagent_commands(command_name);
            """)

            # Delete worktree phantom sessions/projects so the indexer
            # re-resolves them under the correct real project.
            conn.execute("DELETE FROM sessions WHERE project_encoded_name LIKE '%--worktrees-%'")
            conn.execute("DELETE FROM projects WHERE encoded_name LIKE '%--worktrees-%'")
            conn.execute("DELETE FROM sessions WHERE project_encoded_name LIKE '%-.worktrees-%'")
            conn.execute("DELETE FROM projects WHERE encoded_name LIKE '%-.worktrees-%'")

            # Force full re-index of all sessions and subagent data
            conn.execute("DELETE FROM subagent_tools")
            conn.execute("DELETE FROM subagent_invocations")
            conn.execute("UPDATE sessions SET jsonl_mtime = jsonl_mtime - 1")

        if current_version < 10:
            logger.info(
                "Migrating → v10: re-index skills for command_triggered invocation source"
            )
            # Clear skill/command tables so they get repopulated with new linkage logic
            conn.execute("DELETE FROM session_skills")
            conn.execute("DELETE FROM session_commands")
            conn.execute("DELETE FROM subagent_skills")
            conn.execute("DELETE FROM subagent_commands")
            # Nudge mtime to force re-index of all sessions
            conn.execute("UPDATE sessions SET jsonl_mtime = jsonl_mtime - 1")

        if current_version < 11:
            logger.info("Migrating → v11: adding tickets + session_tickets tables")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL CHECK (provider IN ('linear','jira','github')),
                    external_key TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    status TEXT,
                    metadata_json TEXT CHECK (metadata_json IS NULL OR length(metadata_json) <= 65536),
                    metadata_updated_at TEXT,
                    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(provider, external_key)
                );

                CREATE INDEX IF NOT EXISTS idx_tickets_provider ON tickets(provider);

                CREATE TABLE IF NOT EXISTS session_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_uuid TEXT NOT NULL,
                    session_slug TEXT,
                    ticket_id INTEGER NOT NULL,
                    link_source TEXT NOT NULL CHECK (link_source IN ('branch','slash_command','dashboard')),
                    linked_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                    UNIQUE(session_uuid, ticket_id)
                );

                CREATE INDEX IF NOT EXISTS idx_session_tickets_session ON session_tickets(session_uuid);
                CREATE INDEX IF NOT EXISTS idx_session_tickets_slug    ON session_tickets(session_slug);
                CREATE INDEX IF NOT EXISTS idx_session_tickets_ticket  ON session_tickets(ticket_id);

                CREATE UNIQUE INDEX IF NOT EXISTS uniq_session_tickets_slug_ticket
                    ON session_tickets(session_slug, ticket_id)
                    WHERE session_slug IS NOT NULL;
            """)

        if current_version < 12:
            logger.info(
                "Migrating → v12: adding projects.git_identity for cross-encoded "
                "ticket aggregation"
            )
            # The minimum-fixture schema test (test_migration_from_v10) seeds
            # only schema_version and skips SCHEMA_SQL, so projects/sessions
            # may not exist. PRAGMA table_info returns 0 rows in that case
            # and we'd ALTER a missing table. Production always has both
            # tables — they're in SCHEMA_SQL since v1.
            projects_cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
            if projects_cols:
                # Idempotent: some DBs already have the column from an
                # out-of-band ALTER on a parallel branch (e.g. the sync-v4
                # prototype worktree).
                if "git_identity" not in projects_cols:
                    conn.execute("ALTER TABLE projects ADD COLUMN git_identity TEXT")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_projects_git_identity "
                    "ON projects(git_identity)"
                )
                # Nudge mtimes so the next periodic indexer pass re-runs
                # _update_project_summaries for every project and populates
                # the new column. Matches the v8/v9/v10 backfill pattern.
                # Gated by the same projects-table guard because if projects
                # doesn't exist, sessions doesn't either in the minimal fixture.
                conn.execute("UPDATE sessions SET jsonl_mtime = jsonl_mtime - 1")

        if current_version < 13:
            logger.info(
                "Migrating → v13: bg-shells/cron tables + "
                "sessions.needs_shell_cron_reindex flag"
            )
            # The CREATE TABLE block for the new tables already ran in the
            # unconditional executescript() above, so we only need the ALTER
            # here. Guarded against the minimum-fixture case where sessions
            # may not exist (same pattern as v12).
            sessions_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if sessions_cols and "needs_shell_cron_reindex" not in sessions_cols:
                # NOT NULL DEFAULT 1 flags every existing row for the bg-shells/
                # cron extraction pass. The indexer clears the flag after
                # processing each session, converging on idle without
                # blocking startup.
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN needs_shell_cron_reindex "
                    "INTEGER NOT NULL DEFAULT 1"
                )

    # Record version
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()

    logger.info("Schema version %d applied successfully", SCHEMA_VERSION)
