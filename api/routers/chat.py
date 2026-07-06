"""
Chat router - WebSocket for live Claude interaction + session rename.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Session rename storage
# ---------------------------------------------------------------------------

def _names_path() -> Path:
    return settings.karma_base / "session-names.json"


def _load_names() -> dict:
    p = _names_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_names(names: dict) -> None:
    p = _names_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(names, indent=2))


class RenameRequest(BaseModel):
    name: str


@router.put("/sessions/{uuid}/name")
async def set_session_name(uuid: str, body: RenameRequest):
    """Store a custom display name for a session."""
    names = _load_names()
    names[uuid] = body.name.strip()
    _save_names(names)
    return {"uuid": uuid, "name": names[uuid]}


@router.delete("/sessions/{uuid}/name")
async def clear_session_name(uuid: str):
    """Remove the custom display name for a session."""
    names = _load_names()
    names.pop(uuid, None)
    _save_names(names)
    return {"uuid": uuid, "name": None}


@router.get("/sessions/{uuid}/name")
async def get_session_name(uuid: str):
    """Get the custom display name for a session, if set."""
    names = _load_names()
    return {"uuid": uuid, "name": names.get(uuid)}


# ---------------------------------------------------------------------------
# WebSocket chat
# ---------------------------------------------------------------------------

@router.websocket("/ws/chat/new")
async def chat_ws_new(websocket: WebSocket, project_path: str = ""):
    """
    Start a brand-new Claude session over WebSocket (no --resume).

    Client sends:  {"type": "message", "text": "..."}
    Server sends:
      {"type": "session_created", "session_uuid": "..."}  — as soon as system.init seen
      {"type": "stream", "event": {...}}   — raw stream-json event from claude
      {"type": "done",   "exit_code": 0}  — turn finished
      {"type": "error",  "message": "..."}— fatal error

    The project_path query param sets cwd for the claude process when it is a
    valid directory.
    """
    await websocket.accept()

    claude_bin = shutil.which("claude")
    if not claude_bin:
        await websocket.send_json({"type": "error", "message": "claude CLI not found in PATH"})
        await websocket.close()
        return

    cwd = project_path if project_path and Path(project_path).is_dir() else None

    active_proc: asyncio.subprocess.Process | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)

            if payload.get("type") == "stop" and active_proc:
                active_proc.terminate()
                continue

            if payload.get("type") != "message":
                continue

            user_text = payload.get("text", "").strip()
            if not user_text:
                continue

            cmd = [
                claude_bin,
                "--print",
                "--verbose",
                "-p", user_text,
                "--output-format", "stream-json",
                "--dangerously-skip-permissions",
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=os.environ.copy(),
            )
            active_proc = proc

            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    # Detect the system.init event which carries the new session UUID
                    if (
                        event.get("type") == "system"
                        and event.get("subtype") == "init"
                        and event.get("session_id")
                    ):
                        await websocket.send_json({
                            "type": "session_created",
                            "session_uuid": event["session_id"],
                        })
                    await websocket.send_json({"type": "stream", "event": event})
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "raw", "text": line})

            await proc.wait()

            stderr_bytes = await proc.stderr.read()
            stderr_out = stderr_bytes.decode("utf-8", errors="replace").strip()

            await websocket.send_json({
                "type": "done",
                "exit_code": proc.returncode,
                "stderr": stderr_out if proc.returncode != 0 else "",
            })
            active_proc = None

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("chat_ws_new error")
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
    finally:
        if active_proc and active_proc.returncode is None:
            active_proc.terminate()


@router.websocket("/ws/chat/{session_uuid}")
async def chat_ws(websocket: WebSocket, session_uuid: str):
    """
    Stream a Claude Code turn over WebSocket.

    Client sends:  {"type": "message", "text": "...", "project_path": "..."}
    Server sends:
      {"type": "stream", "event": {...}}   — raw stream-json event from claude
      {"type": "done",   "exit_code": 0}  — turn finished
      {"type": "error",  "message": "..."}— fatal error
    """
    await websocket.accept()

    claude_bin = shutil.which("claude")
    if not claude_bin:
        await websocket.send_json({"type": "error", "message": "claude CLI not found in PATH"})
        await websocket.close()
        return

    active_proc: asyncio.subprocess.Process | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)

            if payload.get("type") == "stop" and active_proc:
                active_proc.terminate()
                continue

            if payload.get("type") != "message":
                continue

            user_text = payload.get("text", "").strip()
            if not user_text:
                continue

            project_path = payload.get("project_path", "")
            cwd = project_path if project_path and Path(project_path).is_dir() else None

            cmd = [
                claude_bin,
                "--print",
                "--verbose",
                "--resume", session_uuid,
                "-p", user_text,
                "--output-format", "stream-json",
                "--dangerously-skip-permissions",
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=os.environ.copy(),
            )
            active_proc = proc

            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    await websocket.send_json({"type": "stream", "event": event})
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "raw", "text": line})

            await proc.wait()

            stderr_bytes = await proc.stderr.read()
            stderr_out = stderr_bytes.decode("utf-8", errors="replace").strip()

            await websocket.send_json({
                "type": "done",
                "exit_code": proc.returncode,
                "stderr": stderr_out if proc.returncode != 0 else "",
            })
            active_proc = None

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("chat_ws error for session %s", session_uuid)
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
    finally:
        if active_proc and active_proc.returncode is None:
            active_proc.terminate()
