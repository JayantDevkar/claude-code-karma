#!/usr/bin/env python3
"""
Plan approval hook for Claude Code's PermissionRequest hook.

Intercepts ExitPlanMode calls and checks plan approval status
in claude-karma before allowing Claude to proceed.

Decision Logic:
- If tool is not ExitPlanMode: continue (allow Claude to proceed)
- If plan status is "approved": allow
- If plan status is "changes_requested" or has annotations: deny with feedback
- If plan is pending or API error: deny, prompt user to review in claude-karma UI

Usage:
    This script is called by Claude Code's PermissionRequest hook when
    ExitPlanMode is invoked. Configure in hooks.json:

    {
      "hooks": {
        "PermissionRequest": [
          {
            "matcher": "ExitPlanMode",
            "hooks": [
              {
                "type": "command",
                "command": "python /path/to/plan_approval.py",
                "timeout": 30
              }
            ]
          }
        ]
      }
    }
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# Claude Karma API base URL
API_BASE_URL = "http://localhost:8000"


def output_continue() -> None:
    """Output continue response (don't intercept this permission request)."""
    print(json.dumps({"continue": True}))


def output_allow() -> None:
    """Output allow response (let Claude proceed with ExitPlanMode)."""
    print(json.dumps({"hookSpecificOutput": {"decision": {"behavior": "allow"}}}))


def output_deny(message: str) -> None:
    """Output deny response with feedback message."""
    print(
        json.dumps({"hookSpecificOutput": {"decision": {"behavior": "deny", "message": message}}})
    )


def extract_slug_from_tool_input(tool_input: dict) -> Optional[str]:
    """
    Extract the plan slug from tool_input.

    The plan content in tool_input may contain a reference to the plan file,
    or we can derive the slug from the plan file path if available.

    Args:
        tool_input: The tool_input dictionary from the hook event

    Returns:
        Plan slug if found, None otherwise
    """
    # Check if there's a plan_path field
    plan_path = tool_input.get("plan_path") or tool_input.get("planPath")
    if plan_path:
        # Extract slug from path like ~/.claude/plans/{slug}.md
        path = Path(plan_path)
        if path.suffix == ".md":
            return path.stem

    # Check if there's a slug field directly
    slug = tool_input.get("slug") or tool_input.get("plan_slug")
    if slug:
        return slug

    # Try to extract from plan content (look for a slug pattern in first line)
    plan_content = tool_input.get("plan", "")
    if plan_content:
        # Plans often have a slug in their metadata or filename reference
        # Look for common patterns like "Plan: {slug}" or "# {slug}"
        first_lines = plan_content.split("\n")[:5]
        for line in first_lines:
            # Skip empty lines and markdown headers
            line = line.strip()
            if line.startswith("Plan:"):
                potential_slug = line.replace("Plan:", "").strip()
                if "-" in potential_slug and len(potential_slug) < 50:
                    return potential_slug

    return None


def get_active_plan_slug() -> Optional[str]:
    """
    Get the currently active plan slug from the plans directory.

    Falls back to finding the most recently modified plan.

    Returns:
        Plan slug if found, None otherwise
    """
    plans_dir = Path.home() / ".claude" / "plans"
    if not plans_dir.exists():
        return None

    # Find most recently modified plan
    plan_files = list(plans_dir.glob("*.md"))
    if not plan_files:
        return None

    # Sort by modification time, most recent first
    plan_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return plan_files[0].stem


def api_get(endpoint: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Make a GET request to the claude-karma API.

    Args:
        endpoint: API endpoint (e.g., "/plans/{slug}/status")

    Returns:
        Tuple of (response_data, error_message)
    """
    url = f"{API_BASE_URL}{endpoint}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data, None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, f"Not found: {endpoint}"
        return None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, f"Connection error: {e.reason}"
    except json.JSONDecodeError:
        return None, "Invalid JSON response from API"
    except Exception as e:
        return None, f"Error: {str(e)}"


def format_annotation(annotation: dict) -> str:
    """
    Format a single annotation for display in the deny message.

    Args:
        annotation: Annotation dictionary from the API

    Returns:
        Formatted annotation string
    """
    ann_type = annotation.get("type", "UNKNOWN")
    original_text = annotation.get("original_text", "")
    new_text = annotation.get("new_text")
    comment = annotation.get("comment")

    # Truncate long text
    if len(original_text) > 100:
        original_text = original_text[:100] + "..."

    lines = [f"- [{ann_type}]"]

    if original_text:
        lines.append(f'  Original: "{original_text}"')

    if ann_type == "REPLACEMENT" and new_text:
        if len(new_text) > 100:
            new_text = new_text[:100] + "..."
        lines.append(f'  Replace with: "{new_text}"')
    elif ann_type == "INSERTION" and new_text:
        if len(new_text) > 100:
            new_text = new_text[:100] + "..."
        lines.append(f'  Insert: "{new_text}"')
    elif ann_type == "DELETION":
        lines.append("  Action: Delete this text")

    if comment:
        if len(comment) > 150:
            comment = comment[:150] + "..."
        lines.append(f"  Comment: {comment}")

    return "\n".join(lines)


def format_deny_message(status: str, status_data: dict, annotations: list) -> str:
    """
    Format the deny message based on plan status and annotations.

    Args:
        status: Plan status ("pending", "approved", "changes_requested")
        status_data: Full status response from API
        annotations: List of annotation dictionaries

    Returns:
        Formatted deny message
    """
    lines = []

    if status == "changes_requested":
        lines.append("Plan changes have been requested in claude-karma.")

        # Include feedback from latest decision if available
        latest_decision = status_data.get("latest_decision")
        if latest_decision and latest_decision.get("feedback"):
            feedback = latest_decision["feedback"]
            if len(feedback) > 500:
                feedback = feedback[:500] + "..."
            lines.append(f"\nFeedback: {feedback}")
    elif status == "pending":
        lines.append("Plan is pending review in claude-karma.")
        lines.append("Please review and approve the plan before proceeding.")

    # Add annotations if any
    if annotations:
        lines.append(f"\n--- Annotations ({len(annotations)}) ---")
        for ann in annotations[:10]:  # Limit to first 10
            lines.append(format_annotation(ann))

        if len(annotations) > 10:
            lines.append(f"\n... and {len(annotations) - 10} more annotations")

    lines.append("\nReview the plan at: http://localhost:5173/plans")

    return "\n".join(lines)


def main() -> None:
    """Main entry point - reads hook data from stdin and decides on action."""
    # Read hook event from stdin
    try:
        event_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        # Invalid JSON - let Claude proceed (don't block on malformed input)
        output_continue()
        return

    # Check if this is an ExitPlanMode tool call
    tool_name = event_data.get("tool_name", "")
    if tool_name != "ExitPlanMode":
        # Not ExitPlanMode - let other hooks handle it
        output_continue()
        return

    # Extract the plan slug from the event
    tool_input = event_data.get("tool_input", {})
    slug = extract_slug_from_tool_input(tool_input)

    # If we couldn't extract a slug, try to find the active plan
    if not slug:
        slug = get_active_plan_slug()

    if not slug:
        # No plan found - let Claude proceed (maybe plan mode wasn't used)
        output_continue()
        return

    # Query the plan status from claude-karma API
    status_data, status_error = api_get(f"/plans/{slug}/status")

    if status_error:
        # API error - deny and ask user to check claude-karma
        if "Connection error" in status_error or "timed out" in status_error:
            output_deny(
                f"Cannot verify plan approval - claude-karma API is not reachable.\n"
                f"Please ensure the API is running (uvicorn main:app --port 8000)\n"
                f"and review the plan at: http://localhost:5173/plans/{slug}"
            )
        elif "Not found" in status_error:
            # Plan not found in API - it might not have been synced yet
            output_deny(
                f"Plan '{slug}' not found in claude-karma.\n"
                f"Please review the plan at: http://localhost:5173/plans/{slug}"
            )
        else:
            output_deny(f"Error checking plan status: {status_error}")
        return

    # Get current status
    status = status_data.get("status", "pending")

    # If approved, allow Claude to proceed
    if status == "approved":
        output_allow()
        return

    # Get annotations for the plan
    annotations_data, _ = api_get(f"/plans/{slug}/annotations")
    annotations = []
    if annotations_data:
        annotations = annotations_data.get("annotations", [])

    # If status is changes_requested OR there are annotations, deny
    if status == "changes_requested" or annotations:
        message = format_deny_message(status, status_data, annotations)
        output_deny(message)
        return

    # Status is pending with no annotations - ask user to review
    output_deny(
        f"Plan '{slug}' is pending review.\n"
        f"Please review and approve the plan in claude-karma before proceeding.\n"
        f"Review at: http://localhost:5173/plans/{slug}"
    )


if __name__ == "__main__":
    main()
