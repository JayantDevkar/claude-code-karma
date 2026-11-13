"""Synthetic JSONL line builders for API-error turn tests."""

import json
from pathlib import Path
from typing import Any, Dict, List

SESSION_ID = "sess-limit-0001"
CWD = "/home/alice/project"
_USAGE = {"input_tokens": 0, "output_tokens": 0}


def _base(kind: str, uid: str, parent, ts: str) -> Dict[str, Any]:
    return {
        "type": kind,
        "uuid": uid,
        "parentUuid": parent,
        "timestamp": ts,
        "sessionId": SESSION_ID,
        "cwd": CWD,
        "isSidechain": False,
        "version": "2.0.0",
    }


def user_line(uid, parent, ts, text) -> Dict[str, Any]:
    line = _base("user", uid, parent, ts)
    line["message"] = {"role": "user", "content": text}
    return line


def reply_line(uid, parent, ts, text, model="claude-opus-4-5-20251101") -> Dict[str, Any]:
    line = _base("assistant", uid, parent, ts)
    line["message"] = {
        "id": f"msg_{uid}",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    return line


def _synthetic(uid, parent, ts, text, stop_reason="stop_sequence") -> Dict[str, Any]:
    line = _base("assistant", uid, parent, ts)
    line["message"] = {
        "id": f"msg_{uid}",
        "role": "assistant",
        "model": "<synthetic>",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "usage": dict(_USAGE),
    }
    return line


def limit_line(
    uid, parent, ts, resets_at=1768046400, rate_limit_type="five_hour"
) -> Dict[str, Any]:
    line = _synthetic(uid, parent, ts, "You've hit your session limit · resets 12pm (UTC)")
    line.update(
        {
            "isApiErrorMessage": True,
            "error": "rate_limit",
            "apiError": "usage_limit_reached",
            "apiErrorStatus": 429,
            "quotaLimits": {
                "status": "rejected",
                "resetsAt": resets_at,
                "rateLimitType": rate_limit_type,
            },
        }
    )
    return line


def server_error_line(uid, parent, ts) -> Dict[str, Any]:
    line = _synthetic(uid, parent, ts, "API Error: Connection lost mid-response.")
    line.update(
        {"isApiErrorMessage": True, "error": "server_error", "apiError": "connection_failed"}
    )
    return line


def refusal_line(uid, parent, ts) -> Dict[str, Any]:
    line = _synthetic(
        uid, parent, ts, "API Error: the model declined this request.", stop_reason="refusal"
    )
    line.update(
        {
            "isApiErrorMessage": True,
            "error": "invalid_request",
            "refusedMessageId": "msg_refused_0001",
        }
    )
    return line


def no_response_line(uid, parent, ts) -> Dict[str, Any]:
    return _synthetic(uid, parent, ts, "No response requested.")


def bookkeeping_line(kind: str) -> Dict[str, Any]:
    """Non-message line. Only `queue-operation` parses via parse_message; `last-prompt` is unknown."""
    if kind == "queue-operation":
        return {
            "type": kind,
            "operation": "enqueue",
            "timestamp": "2026-01-10T09:59:00.000Z",
            "sessionId": SESSION_ID,
        }
    return {"type": kind, "sessionId": SESSION_ID, "lastPrompt": "hello"}


def write_jsonl(path, lines: List[Dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path
