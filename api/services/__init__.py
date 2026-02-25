"""
Services package for Claude Karma API.

Contains business logic and data processing services.

Note: As of Phase 4 reorganization, many utilities have been moved to:
- utils.py: General utilities (tool result parsing, session utils, project listing)
- config.py: Constants (FILE_TOOL_MAPPINGS)

This __init__.py re-exports for backward compatibility.
"""

# Re-export from new locations for backward compatibility
from config import FILE_TOOL_MAPPINGS
from utils import (
    ToolResultData,
    collect_tool_results,
    get_initial_prompt,
    get_tool_summary,
    list_all_projects,
    parse_tool_result_content,
    parse_xml_like_content,
)

# Actual services (stateful classes)
from .session_relationships import SessionRelationshipResolver

__all__ = [
    # Re-exported from utils/config
    "FILE_TOOL_MAPPINGS",
    "get_initial_prompt",
    "get_tool_summary",
    "list_all_projects",
    "ToolResultData",
    "collect_tool_results",
    "parse_tool_result_content",
    "parse_xml_like_content",
    # Actual services
    "SessionRelationshipResolver",
]
