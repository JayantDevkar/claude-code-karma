"""JSONL-fallback analytics totals cover the session plus its subagents, like the SQLite path."""

import json
from pathlib import Path

from models.session import Session
from routers.analytics import _calculate_analytics_from_sessions


def _assistant_line(uuid: str) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "uuid": uuid,
            "timestamp": "2026-10-01T09:00:00Z",
            "message": {
                "id": f"msg_{uuid}",
                "role": "assistant",
                "model": "claude-opus-4-5-20251101",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }
    )


def test_fallback_analytics_totals_include_subagents(tmp_path: Path):
    project = tmp_path / "-p"
    (project / "s1" / "subagents").mkdir(parents=True)
    session_path = project / "s1.jsonl"
    session_path.write_text(_assistant_line("m1") + "\n")
    (project / "s1" / "subagents" / "agent-a1.jsonl").write_text(_assistant_line("x1") + "\n")

    analytics = _calculate_analytics_from_sessions(
        [Session.from_path(session_path, claude_base_dir=tmp_path)], use_index=False
    )

    assert analytics.total_input_tokens == 200
    assert analytics.total_output_tokens == 100
