"""
Normalized workflow schema for workflow.db.

Separate from metadata.db to avoid write contention with the session indexer.
Steps and edges are stored as proper rows instead of JSON blobs.
"""

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

WORKFLOW_SCHEMA_VERSION = 1

WORKFLOW_SCHEMA_SQL = """
-- Schema versioning (separate from metadata.db)
CREATE TABLE IF NOT EXISTS wf_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- Workflow definitions (node_positions = visual layout only)
CREATE TABLE IF NOT EXISTS workflows (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    project_path   TEXT,
    node_positions JSON NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wf_project ON workflows(project_path);

-- Steps promoted from JSON blob to rows
CREATE TABLE IF NOT EXISTS workflow_steps (
    id              TEXT NOT NULL,
    workflow_id     TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    model           TEXT NOT NULL DEFAULT 'sonnet',
    tools           JSON NOT NULL DEFAULT '["Read","Edit"]',
    max_turns       INTEGER NOT NULL DEFAULT 10,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, id),
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

-- Edges normalized from graph JSON, with condition on edge
CREATE TABLE IF NOT EXISTS workflow_edges (
    id          TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    condition   TEXT,
    PRIMARY KEY (workflow_id, id),
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

-- Inputs normalized from JSON
CREATE TABLE IF NOT EXISTS workflow_inputs (
    workflow_id TEXT NOT NULL,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'string',
    required    INTEGER NOT NULL DEFAULT 1,
    default_val TEXT,
    description TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, name),
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

-- Workflow execution runs
CREATE TABLE IF NOT EXISTS workflow_runs (
    id           TEXT PRIMARY KEY,
    workflow_id  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    input_values JSON,
    started_at   TEXT,
    completed_at TEXT,
    error        TEXT,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_wf_runs_workflow ON workflow_runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_wf_runs_status ON workflow_runs(status);

-- Individual step execution within a run
CREATE TABLE IF NOT EXISTS workflow_run_steps (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    step_id      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    session_id   TEXT,
    prompt       TEXT,
    output       TEXT,
    started_at   TEXT,
    completed_at TEXT,
    error        TEXT,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_wf_run_steps_run ON workflow_run_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_wf_run_steps_session ON workflow_run_steps(session_id);

-- Migration tracking flag
CREATE TABLE IF NOT EXISTS wf_migration_log (
    source TEXT PRIMARY KEY,
    migrated_at TEXT DEFAULT (datetime('now'))
);
"""


def ensure_workflow_schema(conn: sqlite3.Connection) -> None:
    """Create workflow tables if they don't exist. Idempotent."""
    try:
        row = conn.execute("SELECT MAX(version) FROM wf_schema_version").fetchone()
        current_version = row[0] if row and row[0] else 0
    except sqlite3.OperationalError:
        current_version = 0

    if current_version >= WORKFLOW_SCHEMA_VERSION:
        logger.debug("Workflow schema is up to date (version %d)", current_version)
        return

    logger.info(
        "Applying workflow schema version %d (current: %d)",
        WORKFLOW_SCHEMA_VERSION,
        current_version,
    )

    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(WORKFLOW_SCHEMA_SQL)

    conn.execute(
        "INSERT OR REPLACE INTO wf_schema_version (version) VALUES (?)",
        (WORKFLOW_SCHEMA_VERSION,),
    )
    conn.commit()
    logger.info("Workflow schema version %d applied", WORKFLOW_SCHEMA_VERSION)


def migrate_from_metadata_db(wf_conn: sqlite3.Connection) -> None:
    """
    One-time migration: copy workflow data from metadata.db to workflow.db.

    Uses INSERT OR IGNORE for idempotency. Skips if already migrated or
    if metadata.db has no workflow tables.
    """
    # Check if already migrated
    try:
        row = wf_conn.execute(
            "SELECT 1 FROM wf_migration_log WHERE source = 'metadata_db'"
        ).fetchone()
        if row:
            logger.debug("Workflow migration from metadata.db already done, skipping")
            return
    except sqlite3.OperationalError:
        pass

    from config import settings

    metadata_path = settings.sqlite_db_path
    if not metadata_path.exists():
        logger.debug("No metadata.db found, skipping workflow migration")
        _record_migration(wf_conn)
        return

    # Check if metadata.db has workflows table
    meta_conn = sqlite3.connect(str(metadata_path), timeout=5.0)
    meta_conn.row_factory = sqlite3.Row
    try:
        tables = {
            r[0]
            for r in meta_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "workflows" not in tables:
            logger.debug("No workflows table in metadata.db, skipping migration")
            _record_migration(wf_conn)
            return

        rows = meta_conn.execute("SELECT * FROM workflows").fetchall()
        if not rows:
            logger.debug("No workflows in metadata.db to migrate")
            _record_migration(wf_conn)
            return

        migrated_count = 0
        for row in rows:
            wf_id = row["id"]
            graph = json.loads(row["graph"]) if row["graph"] else {"nodes": [], "edges": []}
            steps_json = json.loads(row["steps"]) if row["steps"] else []
            inputs_json = json.loads(row["inputs"]) if row["inputs"] else []

            # Extract node positions from graph nodes
            node_positions = {}
            for node in graph.get("nodes", []):
                node_positions[node["id"]] = {
                    "position": node.get("position", {"x": 0, "y": 0}),
                    "type": node.get("type", "step"),
                    "data": node.get("data", {}),
                }

            # Insert workflow
            wf_conn.execute(
                """INSERT OR IGNORE INTO workflows
                   (id, name, description, project_path, node_positions, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    wf_id,
                    row["name"],
                    row["description"],
                    row["project_path"],
                    json.dumps(node_positions),
                    row["created_at"] or "",
                    row["updated_at"] or "",
                ),
            )

            # Insert steps
            for i, step in enumerate(steps_json):
                if step.get("condition"):
                    logger.warning(
                        "Dropping step-level condition for step '%s' in workflow '%s' "
                        "(conditions now belong on edges)",
                        step.get("id"),
                        wf_id,
                    )
                wf_conn.execute(
                    """INSERT OR IGNORE INTO workflow_steps
                       (id, workflow_id, prompt_template, model, tools, max_turns, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        step["id"],
                        wf_id,
                        step.get("prompt_template", ""),
                        step.get("model", "sonnet"),
                        json.dumps(step.get("tools", ["Read", "Edit"])),
                        step.get("max_turns", 10),
                        i,
                    ),
                )

            # Insert edges (no condition from old format)
            for edge in graph.get("edges", []):
                edge_id = edge.get("id", f"{edge.get('source', '')}_{edge.get('target', '')}")
                wf_conn.execute(
                    """INSERT OR IGNORE INTO workflow_edges
                       (id, workflow_id, source, target, condition)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        edge_id,
                        wf_id,
                        edge.get("source", ""),
                        edge.get("target", ""),
                        None,
                    ),
                )

            # Insert inputs
            for i, inp in enumerate(inputs_json):
                wf_conn.execute(
                    """INSERT OR IGNORE INTO workflow_inputs
                       (workflow_id, name, type, required, default_val, description, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        wf_id,
                        inp["name"],
                        inp.get("type", "string"),
                        1 if inp.get("required", True) else 0,
                        inp.get("default"),
                        inp.get("description"),
                        i,
                    ),
                )

            migrated_count += 1

        # Migrate runs
        if "workflow_runs" in tables:
            run_rows = meta_conn.execute("SELECT * FROM workflow_runs").fetchall()
            for r in run_rows:
                wf_conn.execute(
                    """INSERT OR IGNORE INTO workflow_runs
                       (id, workflow_id, status, input_values, started_at, completed_at, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["id"],
                        r["workflow_id"],
                        r["status"],
                        r["input_values"],
                        r.get("started_at"),
                        r.get("completed_at"),
                        r.get("error"),
                    ),
                )

        if "workflow_run_steps" in tables:
            step_rows = meta_conn.execute("SELECT * FROM workflow_run_steps").fetchall()
            for s in step_rows:
                wf_conn.execute(
                    """INSERT OR IGNORE INTO workflow_run_steps
                       (id, run_id, step_id, status, session_id, prompt, output, started_at, completed_at, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        s["id"],
                        s["run_id"],
                        s["step_id"],
                        s["status"],
                        s.get("session_id"),
                        s.get("prompt"),
                        s.get("output"),
                        s.get("started_at"),
                        s.get("completed_at"),
                        s.get("error"),
                    ),
                )

        wf_conn.commit()
        logger.info("Migrated %d workflows from metadata.db to workflow.db", migrated_count)

    finally:
        meta_conn.close()

    _record_migration(wf_conn)


def _record_migration(wf_conn: sqlite3.Connection) -> None:
    """Record that migration has been completed."""
    wf_conn.execute(
        "INSERT OR IGNORE INTO wf_migration_log (source) VALUES ('metadata_db')"
    )
    wf_conn.commit()
