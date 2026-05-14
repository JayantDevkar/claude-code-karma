"""
SQLite schema definitions and migration support.

All tables use CREATE TABLE IF NOT EXISTS for idempotent schema creation.
A schema_version table tracks applied migrations for future upgrades.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 11

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
    cursor_workspace_hash TEXT,
    indexed_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_encoded_name);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_slug ON sessions(slug);
CREATE INDEX IF NOT EXISTS idx_sessions_branch ON sessions(project_encoded_name, git_branch);
CREATE INDEX IF NOT EXISTS idx_sessions_mtime ON sessions(jsonl_mtime);
CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(session_source);

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
-- invocation_source: 'main' (Claude Code session), 'cursor' (Cursor IDE session), or future sources
CREATE TABLE IF NOT EXISTS session_tools (
    session_uuid TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    invocation_source TEXT NOT NULL DEFAULT 'main',
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, tool_name, invocation_source),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tools_name ON session_tools(tool_name);
CREATE INDEX IF NOT EXISTS idx_tools_source ON session_tools(invocation_source);

-- Cursor-specific session metadata (sibling to `sessions` for source='cursor' rows)
CREATE TABLE IF NOT EXISTS cursor_session_meta (
    session_uuid              TEXT PRIMARY KEY,
    unified_mode              TEXT,
    force_mode                TEXT,
    agent_backend             TEXT,
    model_name                TEXT,
    context_usage_percent     REAL,
    context_tokens_used       INTEGER,
    context_token_limit       INTEGER,
    is_agentic                INTEGER DEFAULT 0,
    is_archived               INTEGER DEFAULT 0,
    is_draft                  INTEGER DEFAULT 0,
    parent_composer_id        TEXT,
    created_on_branch         TEXT,
    referenced_plans_json     TEXT,
    todos_json                TEXT,
    sub_composer_ids_json     TEXT,
    name                      TEXT,
    subtitle                  TEXT,
    status                    TEXT,
    total_lines_added         INTEGER DEFAULT 0,
    total_lines_removed       INTEGER DEFAULT 0,
    files_changed_count       INTEGER DEFAULT 0,
    indexed_at                INTEGER NOT NULL,
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cursor_meta_mode   ON cursor_session_meta(unified_mode);
CREATE INDEX IF NOT EXISTS idx_cursor_meta_parent ON cursor_session_meta(parent_composer_id);

-- Cursor bubble store (per-message granularity for timeline reconstruction)
CREATE TABLE IF NOT EXISTS cursor_bubble (
    session_uuid         TEXT NOT NULL,
    bubble_id            TEXT NOT NULL,
    seq                  INTEGER NOT NULL,
    bubble_type          INTEGER NOT NULL,
    capability_type      INTEGER,
    created_at_ms        INTEGER,
    has_thinking         INTEGER DEFAULT 0,
    thinking_duration_ms INTEGER,
    has_tool_call        INTEGER DEFAULT 0,
    text_preview         TEXT,
    text_full            TEXT,
    raw_json             TEXT,
    PRIMARY KEY (session_uuid, bubble_id),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cursor_bubble_seq  ON cursor_bubble(session_uuid, seq);
CREATE INDEX IF NOT EXISTS idx_cursor_bubble_type ON cursor_bubble(session_uuid, bubble_type);

-- Cursor tool call detail (per-call, joined to session_tools count aggregates)
CREATE TABLE IF NOT EXISTS cursor_tool_call (
    session_uuid     TEXT NOT NULL,
    bubble_id        TEXT NOT NULL,
    tool_call_id     TEXT,
    tool_name        TEXT NOT NULL,
    tool_int         INTEGER,
    status           TEXT,
    args_json        TEXT,
    result_text      TEXT,
    file_path        TEXT,
    created_at_ms    INTEGER,
    PRIMARY KEY (session_uuid, bubble_id, tool_name),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cursor_toolcall_name ON cursor_tool_call(tool_name);
CREATE INDEX IF NOT EXISTS idx_cursor_toolcall_file ON cursor_tool_call(file_path) WHERE file_path IS NOT NULL;

-- Cursor plan store (~/.cursor/plans/*.plan.md YAML+md files)
CREATE TABLE IF NOT EXISTS cursor_plan (
    slug           TEXT PRIMARY KEY,
    plan_id        TEXT,
    name           TEXT,
    overview       TEXT,
    todos_json     TEXT,
    body_md        TEXT,
    file_path      TEXT NOT NULL,
    file_mtime_ms  INTEGER NOT NULL,
    indexed_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cursor_plan_id ON cursor_plan(plan_id);

-- Cursor MCP server descriptors (one row per declaration per workspace)
CREATE TABLE IF NOT EXISTS cursor_mcp_server (
    server_identifier TEXT NOT NULL,
    workspace_hash    TEXT NOT NULL,
    server_name       TEXT,
    source            TEXT,
    file_path         TEXT NOT NULL,
    indexed_at        INTEGER NOT NULL,
    PRIMARY KEY (server_identifier, workspace_hash)
);

CREATE TABLE IF NOT EXISTS cursor_mcp_tool (
    server_identifier TEXT NOT NULL,
    workspace_hash    TEXT NOT NULL,
    tool_name         TEXT NOT NULL,
    description       TEXT,
    arguments_json    TEXT,
    file_path         TEXT NOT NULL,
    indexed_at        INTEGER NOT NULL,
    PRIMARY KEY (server_identifier, workspace_hash, tool_name),
    FOREIGN KEY (server_identifier, workspace_hash)
        REFERENCES cursor_mcp_server(server_identifier, workspace_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cursor_mcp_tool_name ON cursor_mcp_tool(tool_name);

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
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug);
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

        if current_version < 11:
            logger.info(
                "Migrating → v11: Cursor session support + session_tools 3-tuple PK"
            )
            # Rebuild session_tools to include invocation_source in PK.
            # SQLite can't ALTER PK, so drop+recreate (same pattern as v9 for skills/commands).
            conn.executescript("""
                DROP TABLE IF EXISTS session_tools;
                CREATE TABLE session_tools (
                    session_uuid TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    invocation_source TEXT NOT NULL DEFAULT 'main',
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (session_uuid, tool_name, invocation_source),
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_tools_name ON session_tools(tool_name);
                CREATE INDEX IF NOT EXISTS idx_tools_source ON session_tools(invocation_source);
            """)

            # Add cursor_workspace_hash to sessions
            existing_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "cursor_workspace_hash" not in existing_cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN cursor_workspace_hash TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_cursor_ws "
                "ON sessions(cursor_workspace_hash) "
                "WHERE cursor_workspace_hash IS NOT NULL"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(session_source)"
            )

            # Backfill session_source = 'claude_code' for cleaner JOINs
            conn.execute(
                "UPDATE sessions SET session_source = 'claude_code' "
                "WHERE session_source IS NULL"
            )

            # New Cursor-specific tables
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cursor_session_meta (
                    session_uuid              TEXT PRIMARY KEY,
                    unified_mode              TEXT,
                    force_mode                TEXT,
                    agent_backend             TEXT,
                    model_name                TEXT,
                    context_usage_percent     REAL,
                    context_tokens_used       INTEGER,
                    context_token_limit       INTEGER,
                    is_agentic                INTEGER DEFAULT 0,
                    is_archived               INTEGER DEFAULT 0,
                    is_draft                  INTEGER DEFAULT 0,
                    parent_composer_id        TEXT,
                    created_on_branch         TEXT,
                    referenced_plans_json     TEXT,
                    todos_json                TEXT,
                    sub_composer_ids_json     TEXT,
                    name                      TEXT,
                    subtitle                  TEXT,
                    status                    TEXT,
                    total_lines_added         INTEGER DEFAULT 0,
                    total_lines_removed       INTEGER DEFAULT 0,
                    files_changed_count       INTEGER DEFAULT 0,
                    indexed_at                INTEGER NOT NULL,
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_cursor_meta_mode
                    ON cursor_session_meta(unified_mode);
                CREATE INDEX IF NOT EXISTS idx_cursor_meta_parent
                    ON cursor_session_meta(parent_composer_id);

                CREATE TABLE IF NOT EXISTS cursor_bubble (
                    session_uuid         TEXT NOT NULL,
                    bubble_id            TEXT NOT NULL,
                    seq                  INTEGER NOT NULL,
                    bubble_type          INTEGER NOT NULL,
                    capability_type      INTEGER,
                    created_at_ms        INTEGER,
                    has_thinking         INTEGER DEFAULT 0,
                    thinking_duration_ms INTEGER,
                    has_tool_call        INTEGER DEFAULT 0,
                    text_preview         TEXT,
                    text_full            TEXT,
                    raw_json             TEXT,
                    PRIMARY KEY (session_uuid, bubble_id),
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_cursor_bubble_seq
                    ON cursor_bubble(session_uuid, seq);
                CREATE INDEX IF NOT EXISTS idx_cursor_bubble_type
                    ON cursor_bubble(session_uuid, bubble_type);

                CREATE TABLE IF NOT EXISTS cursor_tool_call (
                    session_uuid     TEXT NOT NULL,
                    bubble_id        TEXT NOT NULL,
                    tool_call_id     TEXT,
                    tool_name        TEXT NOT NULL,
                    tool_int         INTEGER,
                    status           TEXT,
                    args_json        TEXT,
                    result_text      TEXT,
                    file_path        TEXT,
                    created_at_ms    INTEGER,
                    PRIMARY KEY (session_uuid, bubble_id, tool_name),
                    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_cursor_toolcall_name
                    ON cursor_tool_call(tool_name);
                CREATE INDEX IF NOT EXISTS idx_cursor_toolcall_file
                    ON cursor_tool_call(file_path) WHERE file_path IS NOT NULL;

                CREATE TABLE IF NOT EXISTS cursor_plan (
                    slug           TEXT PRIMARY KEY,
                    plan_id        TEXT,
                    name           TEXT,
                    overview       TEXT,
                    todos_json     TEXT,
                    body_md        TEXT,
                    file_path      TEXT NOT NULL,
                    file_mtime_ms  INTEGER NOT NULL,
                    indexed_at     INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cursor_plan_id ON cursor_plan(plan_id);

                CREATE TABLE IF NOT EXISTS cursor_mcp_server (
                    server_identifier TEXT NOT NULL,
                    workspace_hash    TEXT NOT NULL,
                    server_name       TEXT,
                    source            TEXT,
                    file_path         TEXT NOT NULL,
                    indexed_at        INTEGER NOT NULL,
                    PRIMARY KEY (server_identifier, workspace_hash)
                );

                CREATE TABLE IF NOT EXISTS cursor_mcp_tool (
                    server_identifier TEXT NOT NULL,
                    workspace_hash    TEXT NOT NULL,
                    tool_name         TEXT NOT NULL,
                    description       TEXT,
                    arguments_json    TEXT,
                    file_path         TEXT NOT NULL,
                    indexed_at        INTEGER NOT NULL,
                    PRIMARY KEY (server_identifier, workspace_hash, tool_name),
                    FOREIGN KEY (server_identifier, workspace_hash)
                        REFERENCES cursor_mcp_server(server_identifier, workspace_hash) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_cursor_mcp_tool_name
                    ON cursor_mcp_tool(tool_name);
            """)

            # Force re-index so Claude Code tool counts repopulate under new PK
            conn.execute("UPDATE sessions SET jsonl_mtime = jsonl_mtime - 1")

    # Record version
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()

    logger.info("Schema version %d applied successfully", SCHEMA_VERSION)
