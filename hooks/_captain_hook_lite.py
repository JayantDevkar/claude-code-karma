# Vendored from captain-hook/ — re-sync when captain-hook schema changes.
# Source: captain-hook/src/captain_hook/
#
# Self-contained subset of captain-hook Pydantic models, covering only the
# hooks consumed by live_session_tracker.py:
#   - SessionStart, SessionEnd
#   - UserPromptSubmit
#   - PostToolUse
#   - Notification, PermissionRequest
#   - Stop
#   - SubagentStart, SubagentStop
#
# Field set intentionally minimal — only what the tracker reads today, plus
# fields recently surfaced as useful (SessionStart.model, SessionStart.agent_type,
# Notification.message, PermissionRequest.message).
#
# Pydantic is required at hook runtime. If unavailable, parse_hook_event()
# returns a lightweight dict-shim with attribute access so callers keep working.

from __future__ import annotations

from typing import Any, Dict, Optional, Union

try:
    from pydantic import BaseModel, ConfigDict, Field

    HAS_PYDANTIC = True
except ImportError:  # pragma: no cover - fallback only when pydantic missing
    HAS_PYDANTIC = False


if HAS_PYDANTIC:

    class _BaseHook(BaseModel):
        """Base for all hook events. extra='allow' for forward compatibility."""

        model_config = ConfigDict(extra="allow")

        session_id: str = Field(..., description="Claude Code session UUID")
        transcript_path: str = Field("", description="Path to session JSONL transcript")
        cwd: str = Field("", description="Working directory when hook fired")
        permission_mode: str = Field("default", description="Current permission mode")
        hook_event_name: str = Field(..., description="Hook event name")

    class SessionStartHook(_BaseHook):
        hook_event_name: str = Field("SessionStart")
        source: Optional[str] = Field(
            None, description="startup, resume, clear, or compact"
        )
        model: Optional[str] = Field(None, description="Claude model identifier")
        agent_type: Optional[str] = Field(
            None, description="Agent type if started with --agent flag"
        )

    class SessionEndHook(_BaseHook):
        hook_event_name: str = Field("SessionEnd")
        reason: Optional[str] = Field(
            None, description="prompt_input_exit, clear, logout, other"
        )

    class UserPromptSubmitHook(_BaseHook):
        hook_event_name: str = Field("UserPromptSubmit")
        prompt: Optional[str] = Field(None, description="The user's submitted text")

    class PostToolUseHook(_BaseHook):
        hook_event_name: str = Field("PostToolUse")
        tool_name: Optional[str] = Field(None)
        tool_use_id: Optional[str] = Field(None)

    class NotificationHook(_BaseHook):
        hook_event_name: str = Field("Notification")
        notification_type: str = Field("", description="permission_prompt, idle_prompt, ...")
        message: Optional[str] = Field(None, description="Notification text")

    class PermissionRequestHook(_BaseHook):
        hook_event_name: str = Field("PermissionRequest")
        notification_type: str = Field("")
        message: Optional[str] = Field(None, description="Permission prompt text")

    class StopHook(_BaseHook):
        hook_event_name: str = Field("Stop")
        stop_hook_active: bool = Field(
            False,
            description="True if already continuing from a previous Stop hook",
        )

    class SubagentStartHook(_BaseHook):
        hook_event_name: str = Field("SubagentStart")
        agent_id: Optional[str] = Field(None)
        agent_type: str = Field("unknown")

    class SubagentStopHook(_BaseHook):
        hook_event_name: str = Field("SubagentStop")
        agent_id: Optional[str] = Field(None)
        agent_transcript_path: Optional[str] = Field(None)
        stop_hook_active: bool = Field(False)

    HookEvent = Union[
        SessionStartHook,
        SessionEndHook,
        UserPromptSubmitHook,
        PostToolUseHook,
        NotificationHook,
        PermissionRequestHook,
        StopHook,
        SubagentStartHook,
        SubagentStopHook,
        _BaseHook,
    ]

    _HOOK_TYPE_MAP: Dict[str, type] = {
        "SessionStart": SessionStartHook,
        "SessionEnd": SessionEndHook,
        "UserPromptSubmit": UserPromptSubmitHook,
        "PostToolUse": PostToolUseHook,
        "Notification": NotificationHook,
        "PermissionRequest": PermissionRequestHook,
        "Stop": StopHook,
        "SubagentStart": SubagentStartHook,
        "SubagentStop": SubagentStopHook,
    }

    def parse_hook_event(data: Dict[str, Any]) -> HookEvent:
        """Parse hook dict into a typed model. Falls back to _BaseHook for unknowns."""
        hook_name = data.get("hook_event_name")
        if not hook_name:
            raise ValueError("Missing 'hook_event_name' in hook data")
        hook_class = _HOOK_TYPE_MAP.get(hook_name, _BaseHook)
        return hook_class.model_validate(data)

else:  # pragma: no cover - fallback path
    # Dict-shim with attribute access so the rest of the tracker can keep
    # using `hook.field` even without pydantic installed.

    class _DictShim:
        """Lightweight attribute-access wrapper around a hook dict."""

        __slots__ = ("_data",)

        def __init__(self, data: Dict[str, Any]) -> None:
            self._data = data

        def __getattr__(self, name: str) -> Any:
            if name.startswith("_"):
                raise AttributeError(name)
            return self._data.get(name)

        def model_dump(self) -> Dict[str, Any]:
            return dict(self._data)

    HookEvent = _DictShim  # type: ignore[assignment,misc]

    def parse_hook_event(data: Dict[str, Any]) -> _DictShim:
        """Fallback parser when pydantic is unavailable — returns dict-shim."""
        if not data.get("hook_event_name"):
            raise ValueError("Missing 'hook_event_name' in hook data")
        return _DictShim(data)


__all__ = ["parse_hook_event", "HookEvent", "HAS_PYDANTIC"]
