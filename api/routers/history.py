"""
History router - archived prompts from cleaned-up sessions.

Provides endpoints for viewing prompts from sessions that have been
cleaned up by Claude Code's retention policy. These prompts are preserved
in ~/.claude/history.jsonl even after the session files are deleted.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

# Add paths for imports
api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))

from config import settings
from models.history import get_archived_prompts, get_project_name

router = APIRouter()


# =============================================================================
# Response Schemas
# =============================================================================


class ArchivedPromptSchema(BaseModel):
    """A single archived prompt."""

    timestamp: datetime = Field(..., description="When the prompt was sent")
    display: str = Field(..., description="The user's prompt text")
    session_id: Optional[str] = Field(None, description="Session ID if available")


class DateRange(BaseModel):
    """Date range for prompts."""

    start: datetime
    end: datetime


class ArchivedSessionSchema(BaseModel):
    """An archived session with its prompts."""

    session_id: str = Field(..., description="Session UUID or orphan-{timestamp}")
    first_prompt_preview: str = Field(..., description="Preview of first prompt (150 chars)")
    prompt_count: int = Field(..., description="Number of prompts in this session")
    date_range: DateRange = Field(..., description="Date range of session")
    is_orphan: bool = Field(..., description="True if grouped by time proximity")
    prompts: list[ArchivedPromptSchema] = Field(
        default_factory=list, description="All prompts in this session"
    )


class ArchivedProjectSchema(BaseModel):
    """Archived sessions grouped by project."""

    project_path: str = Field(..., description="Full path to the project")
    project_name: str = Field(..., description="Human-readable project name")
    encoded_name: str = Field(..., description="Encoded project name for URLs")
    session_count: int = Field(..., description="Number of archived sessions")
    prompt_count: int = Field(..., description="Total number of archived prompts")
    date_range: DateRange = Field(..., description="Date range of all sessions")
    sessions: list[ArchivedSessionSchema] = Field(
        default_factory=list, description="List of archived sessions"
    )


class ArchivedPromptsResponse(BaseModel):
    """Response for all archived prompts."""

    projects: list[ArchivedProjectSchema] = Field(
        default_factory=list, description="Archived sessions grouped by project"
    )
    total_archived_sessions: int = Field(0, description="Total sessions across all projects")
    total_archived_prompts: int = Field(0, description="Total prompts across all projects")


class ProjectArchivedResponse(BaseModel):
    """Response for a single project's archived sessions."""

    project_name: str = Field(..., description="Human-readable project name")
    project_path: str = Field(..., description="Full path to the project")
    sessions: list[ArchivedSessionSchema] = Field(
        default_factory=list, description="List of archived sessions"
    )
    total_sessions: int = Field(0, description="Total number of archived sessions")
    total_prompts: int = Field(0, description="Total number of archived prompts")


# =============================================================================
# Endpoints
# =============================================================================


def _convert_session_to_schema(session) -> ArchivedSessionSchema:
    """Convert a model ArchivedSession to schema."""
    return ArchivedSessionSchema(
        session_id=session.session_id,
        first_prompt_preview=session.first_prompt_preview,
        prompt_count=session.prompt_count,
        date_range=DateRange(
            start=session.date_range_start,
            end=session.date_range_end,
        ),
        is_orphan=session.is_orphan,
        prompts=[
            ArchivedPromptSchema(
                timestamp=p.timestamp,
                display=p.display,
                session_id=p.session_id,
            )
            for p in session.prompts
        ],
    )


def _convert_project_to_schema(project) -> ArchivedProjectSchema:
    """Convert a model ArchivedProject to schema."""
    return ArchivedProjectSchema(
        project_path=project.project_path,
        project_name=project.project_name,
        encoded_name=project.encoded_name,
        session_count=project.session_count,
        prompt_count=project.prompt_count,
        date_range=DateRange(
            start=project.date_range_start,
            end=project.date_range_end,
        ),
        sessions=[_convert_session_to_schema(s) for s in project.sessions],
    )


@router.get("/archived", response_model=ArchivedPromptsResponse)
async def get_all_archived_prompts(
    search: Optional[str] = Query(None, description="Search prompts by text"),
) -> ArchivedPromptsResponse:
    """
    Get all archived sessions grouped by project.

    Returns sessions from which prompts have been cleaned up by Claude Code's
    retention policy. The original session files no longer exist, but the
    prompt history is preserved in history.jsonl.
    """
    archived_projects, total_sessions, total_prompts = get_archived_prompts(settings.claude_base)

    # Apply search filter if provided
    if search:
        search_lower = search.lower()
        filtered_projects = []
        filtered_session_count = 0
        filtered_prompt_count = 0

        for project in archived_projects:
            # Filter sessions that have matching prompts
            matching_sessions = []
            for session in project.sessions:
                matching_prompts = [p for p in session.prompts if search_lower in p.display.lower()]
                if matching_prompts:
                    # Create a filtered session with only matching prompts
                    matching_sessions.append(
                        ArchivedSessionSchema(
                            session_id=session.session_id,
                            first_prompt_preview=matching_prompts[0].display[:150] + "..."
                            if len(matching_prompts[0].display) > 150
                            else matching_prompts[0].display,
                            prompt_count=len(matching_prompts),
                            date_range=DateRange(
                                start=matching_prompts[0].timestamp,
                                end=matching_prompts[-1].timestamp,
                            ),
                            is_orphan=session.is_orphan,
                            prompts=[
                                ArchivedPromptSchema(
                                    timestamp=p.timestamp,
                                    display=p.display,
                                    session_id=p.session_id,
                                )
                                for p in matching_prompts
                            ],
                        )
                    )
                    filtered_prompt_count += len(matching_prompts)

            if matching_sessions:
                # Calculate new date range from filtered sessions
                all_starts = [s.date_range.start for s in matching_sessions]
                all_ends = [s.date_range.end for s in matching_sessions]

                filtered_projects.append(
                    ArchivedProjectSchema(
                        project_path=project.project_path,
                        project_name=project.project_name,
                        encoded_name=project.encoded_name,
                        session_count=len(matching_sessions),
                        prompt_count=sum(s.prompt_count for s in matching_sessions),
                        date_range=DateRange(
                            start=min(all_starts),
                            end=max(all_ends),
                        ),
                        sessions=matching_sessions,
                    )
                )
                filtered_session_count += len(matching_sessions)

        return ArchivedPromptsResponse(
            projects=filtered_projects,
            total_archived_sessions=filtered_session_count,
            total_archived_prompts=filtered_prompt_count,
        )

    # Convert to response schema
    projects_response = [_convert_project_to_schema(p) for p in archived_projects]

    return ArchivedPromptsResponse(
        projects=projects_response,
        total_archived_sessions=total_sessions,
        total_archived_prompts=total_prompts,
    )


@router.get("/archived/{encoded_name}", response_model=ProjectArchivedResponse)
async def get_project_archived_prompts(
    encoded_name: str,
    search: Optional[str] = Query(None, description="Search prompts by text"),
) -> ProjectArchivedResponse:
    """
    Get archived sessions for a specific project.

    This is used by the project detail page's "Archived" tab to show
    archived sessions for just that project.
    """
    from routers.projects import resolve_project_identifier

    encoded_name = resolve_project_identifier(encoded_name)
    archived_projects, _, _ = get_archived_prompts(
        settings.claude_base, project_filter=encoded_name
    )

    if not archived_projects:
        # Return empty response rather than 404 - project may just have no archived prompts
        # Decode the path using Project model (handles both Unix and Windows)
        from models.project import Project

        project_path = Project.decode_path(encoded_name)
        return ProjectArchivedResponse(
            project_name=get_project_name(project_path),
            project_path=project_path,
            sessions=[],
            total_sessions=0,
            total_prompts=0,
        )

    project = archived_projects[0]

    # Apply search filter if provided
    if search:
        search_lower = search.lower()
        matching_sessions = []
        total_prompts = 0

        for session in project.sessions:
            matching_prompts = [p for p in session.prompts if search_lower in p.display.lower()]
            if matching_prompts:
                matching_sessions.append(
                    ArchivedSessionSchema(
                        session_id=session.session_id,
                        first_prompt_preview=matching_prompts[0].display[:150] + "..."
                        if len(matching_prompts[0].display) > 150
                        else matching_prompts[0].display,
                        prompt_count=len(matching_prompts),
                        date_range=DateRange(
                            start=matching_prompts[0].timestamp,
                            end=matching_prompts[-1].timestamp,
                        ),
                        is_orphan=session.is_orphan,
                        prompts=[
                            ArchivedPromptSchema(
                                timestamp=p.timestamp,
                                display=p.display,
                                session_id=p.session_id,
                            )
                            for p in matching_prompts
                        ],
                    )
                )
                total_prompts += len(matching_prompts)

        return ProjectArchivedResponse(
            project_name=project.project_name,
            project_path=project.project_path,
            sessions=matching_sessions,
            total_sessions=len(matching_sessions),
            total_prompts=total_prompts,
        )

    return ProjectArchivedResponse(
        project_name=project.project_name,
        project_path=project.project_path,
        sessions=[_convert_session_to_schema(s) for s in project.sessions],
        total_sessions=project.session_count,
        total_prompts=project.prompt_count,
    )
