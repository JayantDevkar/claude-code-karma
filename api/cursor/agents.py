"""
Cursor's built-in agents.

Cursor has no custom-agent manifest on disk — its "agents" are hardcoded
UI modes inside the IDE. We surface them so the /agents endpoint
returns a unified view across Claude Code and Cursor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CursorBuiltinAgent:
    name: str
    description: str
    source: str = "cursor-builtin"


CURSOR_BUILTIN_AGENTS: tuple[CursorBuiltinAgent, ...] = (
    CursorBuiltinAgent(
        name="agent",
        description="Cursor's Composer — agentic coding mode (Cmd+I).",
    ),
    CursorBuiltinAgent(
        name="chat",
        description="Cursor's sidebar chat — read-only Q&A (Cmd+L).",
    ),
    CursorBuiltinAgent(
        name="plan",
        description="Cursor's plan mode — drafts plans before execution.",
    ),
    CursorBuiltinAgent(
        name="debug",
        description="Cursor's debug mode — focused troubleshooting workflow.",
    ),
    CursorBuiltinAgent(
        name="edit",
        description="Cursor's inline edit mode — surgical file edits.",
    ),
)


def list_cursor_builtin_agents() -> list[CursorBuiltinAgent]:
    return list(CURSOR_BUILTIN_AGENTS)
