"""
Shared subagent type extraction logic.

Extracts subagent_type mappings from session JSONL files by analyzing
raw JSON lines for Task tool calls and their corresponding tool results.

Used by both the indexer (at index time) and subagent_sessions router
(at request time fallback).

Implementation notes:
- Parses raw JSON (no Pydantic models) for speed and to avoid lossy parsing
- Scans both parent session and all subagent JSONLs (catches nested agents)
- Classifies system agents (acompact-*, aprompt_suggestion-*) by ID prefix
- Classifies remaining agents by first message content (warmup, teammate)
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Pre-compiled regex for agent ID extraction from tool result text
AGENT_ID_PATTERN = re.compile(r"agentId:\s*([a-fA-F0-9]+)")


def get_all_subagent_types(jsonl_path: Path, subagents_dir: Path | None = None) -> dict[str, str]:
    """
    Extract agent_id -> subagent_type mapping from a session and its subagents.

    Four-phase approach:
    1. Scan parent session JSONL for Task tool_use / tool_result pairs
    2. Scan ALL subagent JSONLs (catches nested agent spawns)
    3. Classify remaining agents by ID prefix (system agents)
    4. Classify remaining _unknown agents by first message content

    Args:
        jsonl_path: Path to the parent session's JSONL file
        subagents_dir: Path to the subagents/ directory (may not exist)

    Returns:
        Dict mapping agent_id -> subagent_type
    """
    result: dict[str, str] = {}

    # Phase 1: Scan parent session JSONL
    result.update(_extract_types_from_raw_jsonl(jsonl_path))

    # Collect agent files once if subagents_dir exists
    agent_files = []
    if subagents_dir and subagents_dir.exists():
        agent_files = list(subagents_dir.glob("agent-*.jsonl"))

    # Phase 2: Scan ALL subagent JSONLs (catches nested agents)
    for agent_file in agent_files:
        result.update(_extract_types_from_raw_jsonl(agent_file))

    # Phase 3: Classify remaining by ID prefix
    for agent_file in agent_files:
        agent_id = agent_file.stem.removeprefix("agent-")
        if agent_id not in result:
            result[agent_id] = _classify_by_prefix(agent_id)

    # Phase 4: Classify remaining _unknown agents by first message content
    for agent_file in agent_files:
        agent_id = agent_file.stem.removeprefix("agent-")
        if result.get(agent_id) == "_unknown":
            classified = _classify_by_first_message(agent_file)
            if classified:
                result[agent_id] = classified

    return result


def _extract_types_from_raw_jsonl(path: Path) -> dict[str, str]:
    """
    Parse a JSONL file line-by-line to extract Task tool call -> agent ID mappings.

    For assistant messages: finds Task tool_use blocks -> collects {tool_use_id: subagent_type}
    For user messages: finds tool_result entries whose tool_use_id matches a known Task call
                       -> extracts agentId from the result text content

    Key invariant: Only extracts agentId from tool_result entries whose tool_use_id
    matches a known Task tool call. This prevents double-counting from Bash output
    or other incidental mentions of agent IDs.

    Returns:
        Dict mapping agent_id -> subagent_type
    """
    task_tools: dict[str, str] = {}  # tool_use_id -> subagent_type
    agent_id_to_type: dict[str, str] = {}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")
                if msg_type == "assistant":
                    _collect_task_tools(msg, task_tools)
                elif msg_type == "user":
                    _match_tool_results(msg, task_tools, agent_id_to_type)

    except (OSError, IOError) as e:
        logger.debug("Error reading JSONL %s: %s", path, e)

    return agent_id_to_type


def _collect_task_tools(msg: dict, task_tools: dict[str, str]) -> None:
    """
    Extract Task tool_use blocks from an assistant message.

    Looks for content blocks with type="tool_use" and name="Task",
    then stores tool_use_id -> subagent_type from the input.
    """
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, str):
        return

    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") in ("Task", "Agent"):
            tool_use_id = block.get("id")
            subagent_type = (block.get("input") or {}).get("subagent_type")
            if tool_use_id and subagent_type:
                task_tools[tool_use_id] = subagent_type


def _match_tool_results(
    msg: dict,
    task_tools: dict[str, str],
    agent_id_to_type: dict[str, str],
) -> None:
    """
    Match tool_result entries in a user message to known Task tool calls.

    User messages have a "content" field that is either a string or a list
    of content blocks. Each block may be a tool_result with a tool_use_id.
    If that tool_use_id matches a known Task call, extract agentId from the
    text content of the result.
    """
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, str):
        # Simple string content — check if any task tool_use_id appears
        # (fallback for flattened content)
        for tid, subagent_type in task_tools.items():
            if tid in content:
                match = AGENT_ID_PATTERN.search(content)
                if match:
                    agent_id_to_type[match.group(1)] = subagent_type
        return

    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue

        tool_use_id = block.get("tool_use_id")
        if not tool_use_id or tool_use_id not in task_tools:
            continue

        # Extract agentId from the tool result's content
        result_content = block.get("content", "")
        if isinstance(result_content, str):
            text = result_content
        elif isinstance(result_content, list):
            # Content may be a list of text blocks
            text_parts = []
            for part in result_content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            text = "\n".join(text_parts)
        else:
            continue

        match = AGENT_ID_PATTERN.search(text)
        if match:
            agent_id_to_type[match.group(1)] = task_tools[tool_use_id]


def _classify_by_prefix(agent_id: str) -> str:
    """
    Classify an agent by its ID prefix for known system agent patterns.

    Returns:
        A type string: "_compact", "_prompt_suggestion", or "_unknown"
    """
    if agent_id.startswith("acompact-") or agent_id.startswith("acompact_"):
        return "_compact"
    if agent_id.startswith("aprompt_suggestion-") or agent_id.startswith("aprompt_suggestion_"):
        return "_prompt_suggestion"
    return "_unknown"


def _classify_by_first_message(agent_file: Path) -> str | None:
    """
    Classify an agent by reading its first JSONL line (the initial prompt).

    Detects:
    - Warmup agents: prompt starts with "Warmup"
    - Team/swarm agents: prompt contains "<teammate-message"

    Returns:
        A type string ("_warmup", "_teammate") or None if unclassifiable.
    """
    try:
        with open(agent_file, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
            if not first_line:
                return None
            msg = json.loads(first_line)
            content = msg.get("message", {}).get("content", "")

            # Extract text from content (string or list of blocks)
            if isinstance(content, str):
                prompt = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        prompt = block.get("text", "")
                        break
                else:
                    return None
            else:
                return None

            prompt = prompt.strip()
            if prompt.startswith("Warmup"):
                return "_warmup"
            if "<teammate-message" in prompt:
                return "_teammate"

    except (OSError, json.JSONDecodeError):
        pass

    return None
