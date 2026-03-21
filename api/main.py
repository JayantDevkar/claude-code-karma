"""
Claude Code Karma API - FastAPI backend for Claude Code session monitoring.

Run with:
  uvicorn main:app --reload --port 8000
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add project root to path for models import
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings  # noqa: E402
from parallel import shutdown_executor  # noqa: E402
from routers import (  # noqa: E402
    admin,
    agents,
    analytics,
    commands,
    docs,
    history,
    hooks,
    live_sessions,
    plans,
    plugins,
    projects,
    remote_sessions,
    sessions,
    skills,
    subagent_sessions,
    sync_members,
    sync_pairing,
    sync_pending,
    sync_projects,
    sync_system,
    sync_teams,
    tools,
)
from routers import settings as settings_router  # noqa: E402

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Startup: Builds SQLite index + pre-warms agent usage cache
    Shutdown: Cleans up parallel executor and SQLite connection
    """
    # Startup
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Claude base directory: {settings.claude_base}")

    # Start SQLite background indexing (non-blocking)
    periodic_task = None
    if settings.use_sqlite:
        try:
            import threading

            from db.connection import get_writer_db

            # Ensure DB file + schema exist before readers can connect
            get_writer_db()
            from db.indexer import run_background_sync, run_periodic_sync

            index_thread = threading.Thread(
                target=run_background_sync,
                name="sqlite-indexer",
                daemon=True,
            )
            index_thread.start()
            logger.info("SQLite background indexing started")

            # Start periodic reindex task
            if settings.reindex_interval_seconds > 0:
                periodic_task = asyncio.create_task(
                    run_periodic_sync(settings.reindex_interval_seconds)
                )
                logger.info(
                    "Periodic reindex scheduled every %ds",
                    settings.reindex_interval_seconds,
                )
        except Exception as e:
            logger.warning(f"SQLite indexing failed to start (non-critical): {e}")

    # Start remote session watcher (monitors incoming Syncthing files).
    # Watches the karma base dir to catch files in both legacy remote-sessions/
    # and v4 karma-out--* inbox folders.
    remote_watcher = None
    if settings.use_sqlite:
        try:
            from services.watcher_manager import RemoteSessionWatcher

            remote_watcher = RemoteSessionWatcher(
                watch_dir=settings.karma_base,
            )
            remote_watcher.start()
            logger.info(
                "Remote session watcher started: %s", settings.karma_base
            )
        except Exception as e:
            logger.warning(
                "Remote session watcher failed to start (non-critical): %s", e
            )

    # Start session packager (packages local sessions into Syncthing outbox)
    session_watcher_mgr = None
    if settings.use_sqlite:
        try:
            from models.sync_config import SyncConfig
            config = SyncConfig.load()
            if config and config.member_tag:
                from db.connection import get_writer_db
                from services.watcher_manager import WatcherManager

                db = get_writer_db()

                # Build local git_identity → encoded_name mapping
                # so we can resolve cross-machine encoded paths
                local_projects = db.execute(
                    "SELECT encoded_name, git_identity FROM projects "
                    "WHERE git_identity IS NOT NULL"
                ).fetchall()

                def _resolve_local_encoded(git_url: str, fallback: str) -> str:
                    """Match a sync git URL to a local project encoded_name."""
                    # Normalise for comparison: strip .git, lowercase
                    norm = git_url.rstrip("/")
                    if norm.endswith(".git"):
                        norm = norm[:-4]
                    norm = norm.lower()
                    for (enc, local_git) in local_projects:
                        lg = (local_git or "").rstrip("/").lower()
                        if lg.endswith(".git"):
                            lg = lg[:-4]
                        # Match if one contains the other (handles
                        # "user/repo" vs "https://github.com/user/repo")
                        if lg and (lg in norm or norm in lg
                                   or lg.endswith(norm) or norm.endswith(lg)):
                            return enc
                    return fallback

                # Build config_data from sync DB tables
                teams_rows = db.execute(
                    "SELECT name FROM sync_teams WHERE status = 'active'"
                ).fetchall()
                teams_dict = {}
                for (tname,) in teams_rows:
                    proj_rows = db.execute(
                        "SELECT git_identity, encoded_name, folder_suffix "
                        "FROM sync_projects WHERE team_name = ? AND status = 'shared'",
                        (tname,),
                    ).fetchall()
                    projects_dict = {}
                    for git_id, enc_name, _fsuffix in proj_rows:
                        local_enc = _resolve_local_encoded(
                            git_id, enc_name or git_id
                        )
                        projects_dict[git_id] = {
                            "encoded_name": local_enc,
                            "path": "",
                        }
                    if projects_dict:
                        teams_dict[tname] = {"projects": projects_dict}

                if teams_dict:
                    config_data = {
                        "teams": teams_dict,
                        "user_id": config.user_id,
                        "machine_id": config.machine_id,
                        "device_id": (
                            config.syncthing.device_id if config.syncthing else ""
                        ),
                        "member_tag": config.member_tag,
                    }
                    session_watcher_mgr = WatcherManager()
                    session_watcher_mgr.start_all(config_data)
                    logger.info(
                        "Session packager started for %d team(s)",
                        len(teams_dict),
                    )
        except Exception as e:
            logger.warning(
                "Session packager failed to start (non-critical): %s", e
            )

    # Start live session reconciler
    reconciler_task = None
    if settings.reconciler_enabled:
        from services.session_reconciler import run_session_reconciler

        reconciler_task = asyncio.create_task(
            run_session_reconciler(
                check_interval=settings.reconciler_check_interval,
                idle_threshold=settings.reconciler_idle_threshold,
            )
        )
        logger.info(
            "Live session reconciler started (interval=%ds, threshold=%ds)",
            settings.reconciler_check_interval,
            settings.reconciler_idle_threshold,
        )

    yield

    # Shutdown
    if remote_watcher is not None:
        remote_watcher.stop()
        logger.info("Remote session watcher stopped")

    if session_watcher_mgr is not None:
        session_watcher_mgr.stop()
        logger.info("Session packager stopped")

    if reconciler_task is not None:
        reconciler_task.cancel()
        logger.info("Session reconciler cancelled")

    if periodic_task is not None:
        periodic_task.cancel()
        logger.info("Periodic reindex task cancelled")

    if settings.use_sqlite:
        try:
            from db.connection import close_db

            close_db()
            logger.info("SQLite connection closed")
        except Exception as e:
            logger.warning(f"SQLite shutdown error: {e}")

    logger.info("Shutting down executor pool...")
    shutdown_executor()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Include routers
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(agents.router, tags=["agents"])
app.include_router(skills.router, tags=["skills"])
app.include_router(commands.router, tags=["commands"])
app.include_router(settings_router.router, prefix="/settings", tags=["settings"])
app.include_router(history.router, prefix="/history", tags=["history"])
app.include_router(live_sessions.router, prefix="/live-sessions", tags=["live-sessions"])
app.include_router(plans.router, prefix="/plans", tags=["plans"])
app.include_router(plugins.router, prefix="/plugins", tags=["plugins"])
app.include_router(tools.router, prefix="/tools", tags=["tools"])
app.include_router(hooks.router, prefix="/hooks", tags=["hooks"])
app.include_router(docs.router, prefix="/docs", tags=["docs"])
app.include_router(
    subagent_sessions.router,
    prefix="/agents",
    tags=["subagent-sessions"],
)
app.include_router(remote_sessions.router, prefix="/remote", tags=["remote"])
app.include_router(sync_system.router)
app.include_router(sync_members.router)
app.include_router(sync_teams.router)
app.include_router(sync_projects.router)
app.include_router(sync_pairing.router)
app.include_router(sync_pending.router)
app.include_router(admin.router)


@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "claude-code-karma-api"}


@app.get("/health")
def health_check():
    """Health check endpoint with optional SQLite status."""
    result = {"status": "healthy"}

    if settings.use_sqlite:
        try:
            from db.indexer import get_last_health, get_last_sync_time, is_db_ready

            health = get_last_health()
            last_sync = get_last_sync_time()
            result["sqlite"] = {
                "ready": is_db_ready(),
                "db_size_kb": health.get("db_size_kb"),
                "session_count": health.get("session_count"),
                "invocation_count": health.get("invocation_count"),
                "fragmentation_pct": health.get("fragmentation_pct"),
                "last_sync": last_sync if last_sync > 0 else None,
                "reindex_interval": settings.reindex_interval_seconds,
            }
        except Exception:
            result["sqlite"] = {"ready": False}

    return result
