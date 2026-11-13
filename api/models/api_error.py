"""Synthetic assistant turns flagged `isApiErrorMessage` (usage limits, refusals, server errors)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

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
