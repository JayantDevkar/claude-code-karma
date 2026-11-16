"""Synthetic assistant turns flagged `isApiErrorMessage` (usage limits, refusals, server errors)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict

ApiErrorKind = Literal["limit", "refusal", "api_error"]


class ApiError(BaseModel):
    """Classified API-error turn."""

    model_config = ConfigDict(frozen=True)

    kind: ApiErrorKind
    code: Optional[str] = None
    status: Optional[int] = None
    resets_at: Optional[datetime] = None
    text: str = ""


@dataclass(frozen=True)
class ApiErrorSummary:
    """How a transcript ended and how many usage-limit turns it contains."""

    ended_by: Optional[ApiErrorKind] = None
    ended_resets_at: Optional[datetime] = None
    limit_hit_count: int = 0
    ended_turn_uuid: Optional[str] = None

    EMPTY: ClassVar["ApiErrorSummary"]


ApiErrorSummary.EMPTY = ApiErrorSummary()


class ApiErrorTracker:
    """Single-pass fold of assistant turns into an ApiErrorSummary."""

    def __init__(self, skip_sidechain: bool) -> None:
        self._skip_sidechain = skip_sidechain
        self._last: Optional[Any] = None
        self._limit_hits = 0

    def feed(self, msg: Any) -> None:
        # Imported lazily: message.py imports this module.
        from .message import AssistantMessage

        if not isinstance(msg, AssistantMessage):
            return
        if self._skip_sidechain and msg.is_sidechain:
            return
        if msg.api_error is not None and msg.api_error.kind == "limit":
            self._limit_hits += 1
        # Non-error synthetic turns (e.g. "No response requested") neither end nor heal.
        if msg.is_synthetic and msg.api_error is None:
            return
        self._last = msg

    def summary(self) -> ApiErrorSummary:
        last = self._last
        err = last.api_error if last is not None else None
        if err is None:
            return ApiErrorSummary(limit_hit_count=self._limit_hits)
        return ApiErrorSummary(
            ended_by=err.kind,
            ended_resets_at=err.resets_at if err.kind == "limit" else None,
            limit_hit_count=self._limit_hits,
            ended_turn_uuid=last.uuid,
        )


def _str_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _parse_resets_at(data: Dict[str, Any]) -> Optional[datetime]:
    # Malformed quota data must never raise: a parse failure drops the session.
    quota = data.get("quotaLimits")
    if not isinstance(quota, dict):
        return None
    raw = quota.get("resetsAt")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _first_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                return block["text"]
    return ""


def classify_api_error(data: Dict[str, Any]) -> Optional[ApiError]:
    """Classify a raw JSONL dict; None unless it carries `isApiErrorMessage: true`."""
    if not isinstance(data, dict) or data.get("isApiErrorMessage") is not True:
        return None

    message = data.get("message")
    error = _str_or_none(data.get("error"))
    code = _str_or_none(data.get("apiError")) or error
    status = data.get("apiErrorStatus")
    if isinstance(status, bool) or not isinstance(status, int):
        status = None

    stop_reason = message.get("stop_reason") if isinstance(message, dict) else None
    if stop_reason == "refusal":
        kind: ApiErrorKind = "refusal"
    elif error == "rate_limit":
        kind = "limit"
    else:
        kind = "api_error"

    return ApiError(
        kind=kind,
        code=code,
        status=status,
        resets_at=_parse_resets_at(data) if kind == "limit" else None,
        text=_first_text(message),
    )
