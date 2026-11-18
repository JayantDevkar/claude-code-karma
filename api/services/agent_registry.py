"""
Who the subagents of a session are: name, type, team, colour and model.

Claude Code writes an `agent-<id>.meta.json` next to each subagent JSONL.
The registry reads those so the timeline can name agents instead of showing ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

_META_SUFFIX = ".meta.json"


@dataclass(frozen=True)
class AgentInfo:
    """Identity of one subagent, from its meta.json."""

    agent_id: str
    name: Optional[str] = None
    agent_type: Optional[str] = None
    team_name: Optional[str] = None
    color: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    tool_use_id: Optional[str] = None
    parent_agent_id: Optional[str] = None

    @property
    def display_name(self) -> Optional[str]:
        """Teammate name, else the agent type."""
        return self.name or self.agent_type


@dataclass
class AgentRegistry:
    """Lookup of a session's subagents by id, name and spawning tool call."""

    _by_id: dict[str, AgentInfo] = field(default_factory=dict)
    _by_name: dict[str, list[AgentInfo]] = field(default_factory=dict)
    _by_tool: dict[str, AgentInfo] = field(default_factory=dict)

    def add(self, info: AgentInfo) -> None:
        if info.agent_id in self._by_id:
            # The same meta.json can be reached from a parent dir and from its own
            return
        self._by_id[info.agent_id] = info
        if info.name:
            self._by_name.setdefault(info.name, []).append(info)
        if info.tool_use_id:
            self._by_tool[info.tool_use_id] = info

    def get(self, agent_id: Optional[str]) -> Optional[AgentInfo]:
        return self._by_id.get(agent_id) if agent_id else None

    def by_name(self, name: Optional[str]) -> Optional[AgentInfo]:
        """The agent with this name; None when no agent or more than one has it."""
        named = self._by_name.get(name, []) if name else []
        return named[0] if len(named) == 1 else None

    def is_ambiguous(self, name: Optional[str]) -> bool:
        return bool(name) and len(self._by_name.get(name, [])) > 1

    def by_tool_use_id(self, tool_use_id: Optional[str]) -> Optional[AgentInfo]:
        return self._by_tool.get(tool_use_id) if tool_use_id else None

    def __len__(self) -> int:
        return len(self._by_id)


def _str(value: object) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _model(value: object) -> Optional[str]:
    """The model an agent was given; "inherit" only says it has none of its own."""
    model = _str(value)
    return None if model == "inherit" else model


def _read_meta(meta_path: Path) -> Optional[AgentInfo]:
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    agent_id = meta_path.name[: -len(_META_SUFFIX)].removeprefix("agent-")
    name = _str(data.get("name"))
    # For teammates agentType only repeats the name; the real type is in the spawned/custom keys.
    agent_type = _str(data.get("spawnedAgentType")) or _str(data.get("customAgentType"))
    if agent_type is None and _str(data.get("agentType")) != name:
        agent_type = _str(data.get("agentType"))
    return AgentInfo(
        agent_id=agent_id,
        name=name,
        agent_type=agent_type,
        team_name=_str(data.get("teamName")),
        color=_str(data.get("color")),
        model=_model(data.get("model")),
        description=_str(data.get("description")),
        tool_use_id=_str(data.get("toolUseId")),
        parent_agent_id=_str(data.get("parentAgentId")),
    )


def build_agent_registry(
    subagent_paths: Iterable[Path], extra_dirs: Iterable[Path] = ()
) -> AgentRegistry:
    """Build the registry from the meta.json files beside these subagent JSONLs (and in extra_dirs)."""
    registry = AgentRegistry()
    seen: set[Path] = set()
    for directory in sorted({p.parent for p in subagent_paths} | set(extra_dirs)):
        try:
            meta_paths = sorted(directory.rglob(f"agent-*{_META_SUFFIX}"))
        except OSError:
            continue
        for meta_path in meta_paths:
            # A nested dir is searched from its parent too; read each file once
            if meta_path in seen:
                continue
            seen.add(meta_path)
            info = _read_meta(meta_path)
            if info is not None:
                registry.add(info)
    return registry
