"""
Hooks router - discover and inspect Claude Code hook registrations.

Provides endpoints for listing hook registrations from settings files and plugins,
inspecting event schemas via captain-hook introspection, and viewing source details.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from http_caching import cacheable
from models.hook import (
    HOOK_EVENT_METADATA,
    LIFECYCLE_ORDER,
    HookEventDetail,
    HookEventSummary,
    HookSourceDetail,
    HooksOverview,
    RelatedEvent,
    build_hooks_overview,
    discover_hooks_cached,
    get_event_schema,
)
from parallel import run_in_thread
from schemas import HookScriptDetail

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=HooksOverview)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def list_hooks(
    request: Request,
    project: Optional[str] = Query(None, description="Project path for project-level hooks"),
    source: Optional[str] = Query(None, description="Filter by source name"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
) -> HooksOverview:
    """
    Get all hook registrations with aggregated stats.

    Discovers hooks from global settings, project settings, and enabled plugins.
    Optionally filter by source name or event type.
    """
    registrations = await run_in_thread(discover_hooks_cached, project)

    # Apply filters
    if source:
        registrations = [
            r for r in registrations if r.source_name == source or r.source_id == source
        ]
    if event_type:
        registrations = [r for r in registrations if r.event_type == event_type]

    return build_hooks_overview(registrations)


@router.get("/sources/{source_id}", response_model=HookSourceDetail)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_hook_source(
    source_id: str,
    request: Request,
    project: Optional[str] = Query(None, description="Project path for project-level hooks"),
) -> HookSourceDetail:
    """
    Get details for a specific hook source.

    Returns all scripts and a coverage matrix showing which event types are covered.
    """
    registrations = await run_in_thread(discover_hooks_cached, project)

    # Filter to source
    source_regs = [r for r in registrations if r.source_id == source_id]
    if not source_regs:
        raise HTTPException(status_code=404, detail=f"Hook source '{source_id}' not found")

    overview = build_hooks_overview(source_regs)
    if not overview.sources:
        raise HTTPException(status_code=404, detail=f"Hook source '{source_id}' not found")

    source = overview.sources[0]

    # Build coverage matrix
    coverage_matrix = {
        event_type: any(r.event_type == event_type for r in source_regs)
        for event_type in HOOK_EVENT_METADATA
    }

    return HookSourceDetail(
        source=source,
        scripts=source.scripts,
        coverage_matrix=coverage_matrix,
    )


@router.get("/scripts/{filename}", response_model=HookScriptDetail)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_hook_script(
    filename: str,
    request: Request,
    project: Optional[str] = Query(None, description="Project path for project-level hooks"),
) -> HookScriptDetail:
    """
    Get details for a specific hook script including source code.

    Returns script metadata and file content with syntax highlighting support.
    """
    registrations = await run_in_thread(discover_hooks_cached, project)
    overview = build_hooks_overview(registrations)

    # Find script across all sources
    found_script = None
    found_source_type = None
    for source in overview.sources:
        for script in source.scripts:
            if script.filename == filename:
                found_script = script
                found_source_type = source.source_type
                break
        if found_script:
            break

    if not found_script:
        raise HTTPException(status_code=404, detail=f"Hook script '{filename}' not found")

    # Read file content
    content = None
    size_bytes = None
    modified_at = None
    line_count = None
    error = None

    if found_script.full_path:
        from pathlib import Path

        script_path = Path(found_script.full_path)
        if not script_path.exists():
            error = "file_not_found"
        else:
            try:
                stat = script_path.stat()
                size_bytes = stat.st_size
                modified_at = datetime.fromtimestamp(stat.st_mtime)

                if size_bytes > 500_000:  # 500KB limit
                    error = "file_too_large"
                else:
                    try:
                        content = script_path.read_text(encoding="utf-8")
                        line_count = content.count("\n") + 1 if content else 0
                    except UnicodeDecodeError:
                        error = "binary_file"
            except OSError:
                error = "file_not_found"
    else:
        error = "file_not_found"

    return HookScriptDetail(
        script=found_script,
        source_type=found_source_type,
        content=content,
        size_bytes=size_bytes,
        modified_at=modified_at,
        line_count=line_count,
        error=error,
    )


# IMPORTANT: This catch-all path param route MUST be registered after
# /sources/{source_id} AND /scripts/{filename} to avoid swallowing those requests.
@router.get("/{event_type}", response_model=HookEventDetail)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_hook_event(
    event_type: str,
    request: Request,
    project: Optional[str] = Query(None, description="Project path for project-level hooks"),
) -> HookEventDetail:
    """
    Get details for a specific hook event type.

    Returns registrations for this event, schema info from captain-hook introspection,
    and related events in the lifecycle.
    """
    # Validate event_type
    if event_type not in HOOK_EVENT_METADATA:
        valid = ", ".join(sorted(HOOK_EVENT_METADATA.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"Unknown event type '{event_type}'. Valid types: {valid}",
        )

    registrations = await run_in_thread(discover_hooks_cached, project)
    event_regs = [r for r in registrations if r.event_type == event_type]

    meta = HOOK_EVENT_METADATA[event_type]
    event_summary = HookEventSummary(
        event_type=event_type,
        phase=meta[0],
        can_block=meta[1],
        description=meta[2],
        total_registrations=len(event_regs),
        sources=sorted(set(r.source_name for r in event_regs)),
        registrations=event_regs,
    )

    # Schema introspection
    schema_info = await run_in_thread(get_event_schema, event_type)

    # Related events (prev/next in lifecycle)
    related_events = []
    if event_type in LIFECYCLE_ORDER:
        idx = LIFECYCLE_ORDER.index(event_type)
        for i in (idx - 1, idx + 1):
            if 0 <= i < len(LIFECYCLE_ORDER):
                rel_type = LIFECYCLE_ORDER[i]
                rel_meta = HOOK_EVENT_METADATA.get(rel_type, ("Unknown", False, ""))
                related_events.append(
                    RelatedEvent(
                        event_type=rel_type,
                        phase=rel_meta[0],
                        can_block=rel_meta[1],
                        description=rel_meta[2],
                        position="previous" if i < idx else "next",
                    )
                )

    return HookEventDetail(
        event=event_summary,
        schema_info=schema_info,
        related_events=related_events,
    )
