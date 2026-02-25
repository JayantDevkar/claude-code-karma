"""
Subagent Sessions Router - detailed views of subagent conversations.

Provides session-like detail endpoints for subagent JSONL files,
enabling the Agent Session View feature with timeline, file activity,
and tool usage breakdowns.

Phase 1: Backend Foundation for Agent Session View
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Add models and api to path
api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))

from collectors import collect_agent_data
from http_caching import (
    build_cache_headers,
    check_conditional_request,
    get_file_cache_info,
)
from models import AssistantMessage, Session
from schemas import (
    ConversationContext,
    SubagentSessionDetail,
    TaskSchema,
)
from services.session_lookup import find_subagent
from utils import normalize_timezone

router = APIRouter()


@router.get("/{encoded_name}/{session_uuid}/agents/{agent_id}")
def get_subagent_detail(
    encoded_name: str, session_uuid: str, agent_id: str, request: Request, fresh: bool = False
):
    """
    Get detailed information about a subagent's conversation.

    Provides session-like detail for subagents, including message count,
    token usage, tool breakdown, and context.

    Args:
        encoded_name: Encoded project directory name
        session_uuid: Parent session UUID
        agent_id: Short hex agent ID
        fresh: If true, use minimal cache for live session polling
    """
    result = find_subagent(encoded_name, session_uuid, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Subagent not found")

    agent = result.agent
    parent_session = result.parent_session

    # Clear cache for fresh requests
    if fresh:
        agent.clear_cache()

    # Check conditional request headers (single stat() call)
    etag, last_modified = get_file_cache_info(agent.jsonl_path)

    conditional_response = check_conditional_request(request, etag, last_modified)
    if conditional_response:
        return conditional_response

    # Single-pass data collection
    agent_data = collect_agent_data(agent)

    # Get usage summary
    usage = agent.get_usage_summary()

    # Calculate duration
    duration_seconds = None
    if agent.start_time and agent.end_time:
        duration_seconds = (agent.end_time - agent.start_time).total_seconds()

    # Calculate cost from usage
    total_cost = 0.0
    for msg in agent.iter_messages():
        if isinstance(msg, AssistantMessage) and msg.usage:
            total_cost += msg.usage.calculate_cost(msg.model)

    # Determine subagent type: SQLite fast-path, then JSONL fallback
    subagent_type = None
    from db.connection import sqlite_read

    with sqlite_read() as conn:
        if conn is not None:
            row = conn.execute(
                "SELECT subagent_type FROM subagent_invocations "
                "WHERE session_uuid = ? AND agent_id = ?",
                (session_uuid, agent_id),
            ).fetchone()
            if row and row[0]:
                subagent_type = row[0]

    if not subagent_type:
        subagent_type = _determine_subagent_type(parent_session, agent_id)

    response_data = SubagentSessionDetail(
        agent_id=agent.agent_id,
        slug=agent.slug,
        is_subagent=True,
        context=ConversationContext(
            project_encoded_name=encoded_name,
            parent_session_uuid=session_uuid,
            parent_session_slug=parent_session.slug,
        ),
        message_count=agent.message_count,
        start_time=agent.start_time,
        end_time=agent.end_time,
        duration_seconds=duration_seconds,
        total_input_tokens=usage.total_input,
        total_output_tokens=usage.output_tokens,
        cache_hit_rate=usage.cache_hit_rate,
        total_cost=total_cost,
        tools_used=dict(agent_data.tool_counts),
        skills_used=dict(agent_data.skills),
        commands_used=dict(agent_data.commands),
        git_branches=list(agent_data.git_branches),
        working_directories=list(agent_data.working_directories),
        subagent_type=subagent_type,
        initial_prompt=agent_data.initial_prompt,
    )

    # Add cache headers
    cache_headers = build_cache_headers(
        etag=etag,
        last_modified=last_modified,
        max_age=1 if fresh else 60,
        stale_while_revalidate=2 if fresh else 300,
        private=True,
    )

    return JSONResponse(
        content=response_data.model_dump(mode="json"),
        headers=cache_headers,
    )


def _determine_subagent_type(parent_session: Session, agent_id: str) -> Optional[str]:
    """
    Determine the subagent type by finding the Task tool call that spawned it.

    Uses raw JSONL scanning for reliable extraction (avoids Pydantic parsing bugs).

    Args:
        parent_session: The parent session containing Task tool calls
        agent_id: The agent ID to find

    Returns:
        The subagent_type if found, None otherwise
    """
    from services.subagent_types import get_all_subagent_types

    jsonl_path = parent_session.jsonl_path
    subagents_dir = jsonl_path.parent / jsonl_path.stem / "subagents"
    types = get_all_subagent_types(jsonl_path, subagents_dir)
    return types.get(agent_id)


@router.get("/{encoded_name}/{session_uuid}/agents/{agent_id}/timeline")
def get_subagent_timeline(
    encoded_name: str, session_uuid: str, agent_id: str, request: Request, fresh: bool = False
):
    """
    Get chronological timeline of events in a subagent conversation.

    Phase 3 DRY: Uses shared conversation_endpoints service.

    Args:
        encoded_name: Encoded project directory name
        session_uuid: Parent session UUID
        agent_id: Short hex agent ID
        fresh: If true, use minimal cache for live session polling
    """
    from services.conversation_endpoints import build_conversation_timeline

    result = find_subagent(encoded_name, session_uuid, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Subagent not found")

    agent = result.agent

    # Collect working directories for path relativization
    agent_data = collect_agent_data(agent)
    working_directories = list(agent_data.working_directories)

    # Use shared service for building timeline
    events = build_conversation_timeline(
        conversation=agent,
        working_dirs=working_directories,
        actor=agent.agent_id,
        actor_type="subagent",
    )

    # Return with cache headers
    response_data = [e.model_dump(mode="json") for e in events]
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 60}, stale-while-revalidate={2 if fresh else 300}"
    }
    return JSONResponse(content=response_data, headers=headers)


@router.get("/{encoded_name}/{session_uuid}/agents/{agent_id}/tools")
def get_subagent_tools(
    encoded_name: str, session_uuid: str, agent_id: str, request: Request, fresh: bool = False
):
    """
    Get tool usage breakdown for a subagent.

    Phase 3 DRY: Uses shared conversation_endpoints service.

    Args:
        encoded_name: Encoded project directory name
        session_uuid: Parent session UUID
        agent_id: Short hex agent ID
        fresh: If true, use minimal cache for live session polling
    """
    from services.conversation_endpoints import build_agent_tool_summaries

    result = find_subagent(encoded_name, session_uuid, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Subagent not found")

    agent = result.agent

    # Collect tool counts
    agent_data = collect_agent_data(agent)

    # Use shared service for building tool summaries
    summaries = build_agent_tool_summaries(agent_data.tool_counts)

    # Return with cache headers
    response_data = [s.model_dump(mode="json") for s in summaries]
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 300}, stale-while-revalidate={2 if fresh else 600}"
    }
    return JSONResponse(content=response_data, headers=headers)


@router.get("/{encoded_name}/{session_uuid}/agents/{agent_id}/file-activity")
def get_subagent_file_activity(
    encoded_name: str, session_uuid: str, agent_id: str, request: Request, fresh: bool = False
):
    """
    Get file operations performed by a subagent.

    Phase 3 DRY: Uses shared conversation_endpoints service.

    Args:
        encoded_name: Encoded project directory name
        session_uuid: Parent session UUID
        agent_id: Short hex agent ID
        fresh: If true, use minimal cache for live session polling
    """
    from services.conversation_endpoints import build_file_activities

    result = find_subagent(encoded_name, session_uuid, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Subagent not found")

    agent = result.agent

    # Collect file operations
    agent_data = collect_agent_data(agent)

    # Use shared service for building file activities (handles sorting)
    activities = build_file_activities(agent_data.file_operations)

    # Return with cache headers
    response_data = [a.model_dump(mode="json") for a in activities]
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 300}, stale-while-revalidate={2 if fresh else 600}"
    }
    return JSONResponse(content=response_data, headers=headers)


@router.get("/{encoded_name}/{session_uuid}/agents/{agent_id}/tasks")
def get_subagent_tasks(
    encoded_name: str,
    session_uuid: str,
    agent_id: str,
    request: Request,
    fresh: bool = False,
    since: Optional[str] = None,
) -> JSONResponse:
    """
    Get tasks created by a subagent.

    Tasks are reconstructed from TaskCreate/TaskUpdate tool_use events
    in the subagent's JSONL file.

    Args:
        encoded_name: Encoded project directory name
        session_uuid: Parent session UUID
        agent_id: Short hex agent ID
        fresh: If true, use minimal cache for live session polling
        since: ISO timestamp string - only return tasks modified after this time.
               Used for incremental fetching during live polling.

    Returns:
        JSONResponse with list of TaskSchema items sorted by ID
    """
    from datetime import datetime

    result = find_subagent(encoded_name, session_uuid, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Subagent not found")

    agent = result.agent
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 60}, stale-while-revalidate={2 if fresh else 300}"
    }

    # Parse the since parameter if provided
    since_dt: Optional[datetime] = None
    if since:
        try:
            # Handle ISO format with Z suffix
            since_str = since.replace("Z", "+00:00")
            since_dt = datetime.fromisoformat(since_str)
        except ValueError:
            logger.warning(f"Invalid 'since' timestamp format: {since}")

    try:
        tasks = agent.list_tasks()
        # For subagent tasks (reconstructed from JSONL), use agent end time or current time
        base_updated_at = agent.end_time or datetime.now()

        response_data = []
        for task in tasks:
            updated_at = base_updated_at

            # Filter by since parameter if provided
            if since_dt and updated_at:
                # Use normalize_timezone for proper timezone comparison
                # This properly converts naive local time to UTC
                normalized_updated = normalize_timezone(updated_at)
                normalized_since = normalize_timezone(since_dt)

                if normalized_updated <= normalized_since:
                    continue  # Skip tasks not modified since the given time

            response_data.append(
                TaskSchema(
                    id=task.id,
                    subject=task.subject,
                    description=task.description,
                    status=task.status,
                    active_form=task.active_form,
                    blocks=task.blocks,
                    blocked_by=task.blocked_by,
                    updated_at=updated_at,
                )
            )

        return JSONResponse(
            content=[t.model_dump(mode="json") for t in response_data],
            headers=headers,
        )
    except Exception as e:
        logger.warning(f"Failed to load tasks for subagent {agent_id}: {e}")
        return JSONResponse(content=[], headers=headers)
