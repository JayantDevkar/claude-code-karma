"""
SQLite schema definitions and migration support.

All tables use CREATE TABLE IF NOT EXISTS for idempotent schema creation.
A schema_version table tracks applied migrations for future upgrades.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 21

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
    source TEXT DEFAULT 'local',
    remote_user_id TEXT,
    remote_machine_id TEXT,
    indexed_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);

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
    agent_display_name TEXT,
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
    git_identity TEXT,
    session_count INTEGER DEFAULT 0,
    last_activity TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug);

-- Sync v4 tables (added in schema v19)
CREATE TABLE IF NOT EXISTS sync_teams (
    name              TEXT PRIMARY KEY,
    leader_device_id  TEXT NOT NULL,
    leader_member_tag TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK(status IN ('active', 'dissolved')),
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_members (
    team_name    TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
    member_tag   TEXT NOT NULL,
    device_id    TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    machine_tag  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'added'
                 CHECK(status IN ('added', 'active', 'removed')),
    added_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, member_tag)
);

CREATE TABLE IF NOT EXISTS sync_projects (
    team_name     TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
    git_identity  TEXT NOT NULL,
    encoded_name  TEXT,
    folder_suffix TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'shared'
                  CHECK(status IN ('shared', 'removed')),
    shared_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, git_identity)
);

CREATE TABLE IF NOT EXISTS sync_subscriptions (
    member_tag           TEXT NOT NULL,
    team_name            TEXT NOT NULL,
    project_git_identity TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'offered'
                         CHECK(status IN ('offered', 'accepted', 'paused', 'declined')),
    direction            TEXT NOT NULL DEFAULT 'both'
                         CHECK(direction IN ('receive', 'send', 'both')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (member_tag, team_name, project_git_identity),
    FOREIGN KEY (team_name, member_tag)
        REFERENCES sync_members(team_name, member_tag) ON DELETE CASCADE,
    FOREIGN KEY (team_name, project_git_identity)
        REFERENCES sync_projects(team_name, git_identity) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_events (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type           TEXT NOT NULL,
    team_name            TEXT,
    member_tag           TEXT,
    project_git_identity TEXT,
    session_uuid         TEXT,
    detail               TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_removed_members (
    team_name   TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
    device_id   TEXT NOT NULL,
    member_tag  TEXT,
    removed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, device_id)
);

CREATE INDEX IF NOT EXISTS idx_members_device ON sync_members(device_id);
CREATE INDEX IF NOT EXISTS idx_members_status ON sync_members(team_name, status);
CREATE INDEX IF NOT EXISTS idx_projects_suffix ON sync_projects(folder_suffix);
CREATE INDEX IF NOT EXISTS idx_projects_git ON sync_projects(git_identity);
CREATE INDEX IF NOT EXISTS idx_subs_member ON sync_subscriptions(member_tag);
CREATE INDEX IF NOT EXISTS idx_subs_status ON sync_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subs_project ON sync_subscriptions(project_git_identity);
CREATE INDEX IF NOT EXISTS idx_events_type ON sync_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_team ON sync_events(team_name);
CREATE INDEX IF NOT EXISTS idx_events_time ON sync_events(created_at);

-- Skill definitions (custom skills, user commands, remote plugin skills)
CREATE TABLE IF NOT EXISTS skill_definitions (
    skill_name TEXT NOT NULL,
    source_user_id TEXT NOT NULL DEFAULT '__local__',
    source_machine_id TEXT,
    category TEXT,
    content TEXT,
    base_directory TEXT,
    description TEXT,
    extracted_from_session TEXT,
    updated_at TEXT,
    PRIMARY KEY (skill_name, source_user_id)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create tables and indexes if they don't exist.

    Idempotent — safe to call on every startup.
    """
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

        # v11-v18: no-op placeholders (schema evolution before sync v4)

        if current_version < 19:
            logger.info(
                "Migrating → v19: sync v4 — drop all old sync tables, recreate with clean-slate schema"
            )
            # Drop all sync tables — both v3 names and v4 names (order matters for FKs)
            conn.execute("DROP TABLE IF EXISTS sync_subscriptions")
            conn.execute("DROP TABLE IF EXISTS sync_rejected_folders")
            conn.execute("DROP TABLE IF EXISTS sync_settings")
            conn.execute("DROP TABLE IF EXISTS sync_removed_members")
            conn.execute("DROP TABLE IF EXISTS sync_events")
            conn.execute("DROP TABLE IF EXISTS sync_team_projects")
            conn.execute("DROP TABLE IF EXISTS sync_projects")
            conn.execute("DROP TABLE IF EXISTS sync_members")
            conn.execute("DROP TABLE IF EXISTS sync_teams")

            # Recreate with v4 schema
            conn.execute("""
                CREATE TABLE sync_teams (
                    name              TEXT PRIMARY KEY,
                    leader_device_id  TEXT NOT NULL,
                    leader_member_tag TEXT NOT NULL,
                    status            TEXT NOT NULL DEFAULT 'active'
                                      CHECK(status IN ('active', 'dissolved')),
                    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE sync_members (
                    team_name    TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
                    member_tag   TEXT NOT NULL,
                    device_id    TEXT NOT NULL,
                    user_id      TEXT NOT NULL,
                    machine_tag  TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'added'
                                 CHECK(status IN ('added', 'active', 'removed')),
                    added_at     TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (team_name, member_tag)
                )
            """)
            conn.execute("""
                CREATE TABLE sync_projects (
                    team_name     TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
                    git_identity  TEXT NOT NULL,
                    encoded_name  TEXT,
                    folder_suffix TEXT NOT NULL,
                    status        TEXT NOT NULL DEFAULT 'shared'
                                  CHECK(status IN ('shared', 'removed')),
                    shared_at     TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (team_name, git_identity)
                )
            """)
            conn.execute("""
                CREATE TABLE sync_subscriptions (
                    member_tag           TEXT NOT NULL,
                    team_name            TEXT NOT NULL,
                    project_git_identity TEXT NOT NULL,
                    status               TEXT NOT NULL DEFAULT 'offered'
                                         CHECK(status IN ('offered', 'accepted', 'paused', 'declined')),
                    direction            TEXT NOT NULL DEFAULT 'both'
                                         CHECK(direction IN ('receive', 'send', 'both')),
                    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (member_tag, team_name, project_git_identity),
                    FOREIGN KEY (team_name, member_tag)
                        REFERENCES sync_members(team_name, member_tag) ON DELETE CASCADE,
                    FOREIGN KEY (team_name, project_git_identity)
                        REFERENCES sync_projects(team_name, git_identity) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE sync_events (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type           TEXT NOT NULL,
                    team_name            TEXT,
                    member_tag           TEXT,
                    project_git_identity TEXT,
                    session_uuid         TEXT,
                    detail               TEXT,
                    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE sync_removed_members (
                    team_name   TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
                    device_id   TEXT NOT NULL,
                    member_tag  TEXT,
                    removed_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (team_name, device_id)
                )
            """)
            # Indexes
            conn.execute("CREATE INDEX idx_members_device ON sync_members(device_id)")
            conn.execute("CREATE INDEX idx_members_status ON sync_members(team_name, status)")
            conn.execute("CREATE INDEX idx_projects_suffix ON sync_projects(folder_suffix)")
            conn.execute("CREATE INDEX idx_projects_git ON sync_projects(git_identity)")
            conn.execute("CREATE INDEX idx_subs_member ON sync_subscriptions(member_tag)")
            conn.execute("CREATE INDEX idx_subs_status ON sync_subscriptions(status)")
            conn.execute("CREATE INDEX idx_subs_project ON sync_subscriptions(project_git_identity)")
            conn.execute("CREATE INDEX idx_events_type ON sync_events(event_type)")
            conn.execute("CREATE INDEX idx_events_team ON sync_events(team_name)")
            conn.execute("CREATE INDEX idx_events_time ON sync_events(created_at)")

        if current_version < 20:
            logger.info(
                "Migrating → v20: normalize remote_user_id from bare user_id to member_tag"
            )
            conn.execute("""
                UPDATE sessions SET remote_user_id = (
                    SELECT m.member_tag FROM sync_members m
                    WHERE m.user_id = sessions.remote_user_id
                    LIMIT 1
                ) WHERE source = 'remote'
                  AND remote_user_id IS NOT NULL
                  AND remote_user_id NOT LIKE '%.%'
                  AND EXISTS (
                      SELECT 1 FROM sync_members m
                      WHERE m.user_id = sessions.remote_user_id
                  )
            """)

        if current_version < 21:
            logger.info(
                "Migrating → v21: adding skill_definitions table and projects.git_identity column"
            )
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skill_definitions (
                    skill_name TEXT NOT NULL,
                    source_user_id TEXT NOT NULL DEFAULT '__local__',
                    source_machine_id TEXT,
                    category TEXT,
                    content TEXT,
                    base_directory TEXT,
                    description TEXT,
                    extracted_from_session TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (skill_name, source_user_id)
                );
            """)
            try:
                conn.execute("ALTER TABLE projects ADD COLUMN git_identity TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

    # Record version
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()

    logger.info("Schema version %d applied successfully", SCHEMA_VERSION)
