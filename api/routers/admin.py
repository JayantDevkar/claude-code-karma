"""
Admin endpoints for database maintenance.

These endpoints allow manual re-indexing and FTS rebuild without
needing to restart the API server or delete the database file.
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reindex")
def trigger_reindex():
    """
    Trigger a full re-index of all JSONL sessions into SQLite.

    Runs synchronously. For large installations, this may take
    several seconds. The incremental indexer only re-processes
    files whose mtime has changed.
    """
    from db.connection import get_writer_db
    from db.indexer import sync_all_projects

    try:
        conn = get_writer_db()
        stats = sync_all_projects(conn)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.error("Reindex failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.post("/rebuild-fts")
def rebuild_fts():
    """
    Rebuild the FTS5 full-text search index.

    Use this if search results seem stale or incorrect.
    Equivalent to: INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')
    """
    from db.connection import get_writer_db

    try:
        conn = get_writer_db()
        conn.execute("INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM sessions_fts").fetchone()[0]
        return {"status": "ok", "fts_rows": count}
    except Exception as e:
        logger.error("FTS rebuild failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.post("/vacuum")
def vacuum_db():
    """
    Run VACUUM on the SQLite database to reclaim space and defragment.
    """
    from db.connection import get_writer_db

    try:
        conn = get_writer_db()
        conn.execute("VACUUM")
        return {"status": "ok"}
    except Exception as e:
        logger.error("VACUUM failed: %s", e)
        return {"status": "error", "detail": str(e)}
