"""
Unit tests for the plan_approval.py hook script.

Tests the hook script functions for intercepting ExitPlanMode calls
and verifying plan approval status.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent
_scripts_dir = _api_dir / "scripts"

# Add paths for imports
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

# Import the functions we're testing
# We need to import the module dynamically since it's in scripts/
import importlib.util

spec = importlib.util.spec_from_file_location("plan_approval", _scripts_dir / "plan_approval.py")
plan_approval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_approval)


# =============================================================================
# Output Function Tests
# =============================================================================


class TestOutputFunctions:
    """Tests for the output helper functions."""

    def test_output_continue(self, capsys):
        """Test output_continue produces correct JSON."""
        plan_approval.output_continue()
        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result == {"continue": True}

    def test_output_allow(self, capsys):
        """Test output_allow produces correct JSON for allowing ExitPlanMode."""
        plan_approval.output_allow()
        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result == {"hookSpecificOutput": {"decision": {"behavior": "allow"}}}

    def test_output_deny(self, capsys):
        """Test output_deny produces correct JSON with message."""
        message = "Plan needs approval"
        plan_approval.output_deny(message)
        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result == {
            "hookSpecificOutput": {"decision": {"behavior": "deny", "message": message}}
        }

    def test_output_deny_with_multiline_message(self, capsys):
        """Test output_deny handles multiline messages correctly."""
        message = "Line 1\nLine 2\nLine 3"
        plan_approval.output_deny(message)
        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["hookSpecificOutput"]["decision"]["message"] == message


# =============================================================================
# Slug Extraction Tests
# =============================================================================


class TestExtractSlugFromToolInput:
    """Tests for extracting plan slug from tool_input."""

    def test_extract_from_plan_path(self):
        """Test extracting slug from plan_path field."""
        tool_input = {"plan_path": "~/.claude/plans/my-plan-slug.md"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result == "my-plan-slug"

    def test_extract_from_planPath_camelCase(self):
        """Test extracting slug from planPath (camelCase) field."""
        tool_input = {"planPath": "/Users/test/.claude/plans/another-slug.md"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result == "another-slug"

    def test_extract_from_slug_field(self):
        """Test extracting slug from direct slug field."""
        tool_input = {"slug": "direct-slug"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result == "direct-slug"

    def test_extract_from_plan_slug_field(self):
        """Test extracting slug from plan_slug field."""
        tool_input = {"plan_slug": "plan-slug-field"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result == "plan-slug-field"

    def test_extract_from_plan_content_with_pattern(self):
        """Test extracting slug from plan content 'Plan:' pattern."""
        tool_input = {"plan": "Plan: my-extracted-slug\n\n## Steps\n1. Do thing"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result == "my-extracted-slug"

    def test_returns_none_for_empty_input(self):
        """Test returns None when tool_input is empty."""
        result = plan_approval.extract_slug_from_tool_input({})
        assert result is None

    def test_returns_none_for_non_md_path(self):
        """Test returns None for non-.md file paths."""
        tool_input = {"plan_path": "/some/path/file.txt"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result is None

    def test_ignores_long_plan_pattern(self):
        """Test ignores Plan: pattern if potential slug is too long."""
        long_slug = "a" * 60  # > 50 chars
        tool_input = {"plan": f"Plan: {long_slug}\n\nContent"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result is None

    def test_ignores_plan_pattern_without_hyphen(self):
        """Test ignores Plan: pattern if potential slug has no hyphen."""
        tool_input = {"plan": "Plan: nohyphen\n\nContent"}
        result = plan_approval.extract_slug_from_tool_input(tool_input)
        assert result is None


class TestGetActivePlanSlug:
    """Tests for getting the active plan slug from filesystem."""

    def test_returns_none_when_no_plans_dir(self, tmp_path, monkeypatch):
        """Test returns None when plans directory doesn't exist."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = plan_approval.get_active_plan_slug()
        assert result is None

    def test_returns_none_when_no_plans(self, tmp_path, monkeypatch):
        """Test returns None when plans directory is empty."""
        plans_dir = tmp_path / ".claude" / "plans"
        plans_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = plan_approval.get_active_plan_slug()
        assert result is None

    def test_returns_most_recent_plan(self, tmp_path, monkeypatch):
        """Test returns the most recently modified plan."""
        import time

        plans_dir = tmp_path / ".claude" / "plans"
        plans_dir.mkdir(parents=True)

        # Create older plan
        old_plan = plans_dir / "old-plan.md"
        old_plan.write_text("Old plan content")

        # Small delay to ensure different mtime
        time.sleep(0.1)

        # Create newer plan
        new_plan = plans_dir / "new-plan.md"
        new_plan.write_text("New plan content")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = plan_approval.get_active_plan_slug()
        assert result == "new-plan"


# =============================================================================
# API Request Tests
# =============================================================================


class TestApiGet:
    """Tests for the api_get function."""

    def test_successful_request(self):
        """Test successful API request returns data."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "approved"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            data, error = plan_approval.api_get("/plans/test/status")

        assert data == {"status": "approved"}
        assert error is None

    def test_http_404_error(self):
        """Test 404 error returns appropriate message."""
        from urllib.error import HTTPError

        error = HTTPError(
            url="http://localhost:8000/plans/missing/status",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=error):
            data, err = plan_approval.api_get("/plans/missing/status")

        assert data is None
        assert "Not found" in err

    def test_http_500_error(self):
        """Test 500 error returns HTTP code and reason."""
        from urllib.error import HTTPError

        error = HTTPError(
            url="http://localhost:8000/plans/test/status",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=error):
            data, err = plan_approval.api_get("/plans/test/status")

        assert data is None
        assert "HTTP 500" in err

    def test_connection_error(self):
        """Test connection error returns appropriate message."""
        from urllib.error import URLError

        error = URLError("Connection refused")

        with patch("urllib.request.urlopen", side_effect=error):
            data, err = plan_approval.api_get("/plans/test/status")

        assert data is None
        assert "Connection error" in err

    def test_invalid_json_response(self):
        """Test invalid JSON response returns error."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not valid json"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            data, err = plan_approval.api_get("/plans/test/status")

        assert data is None
        assert "Invalid JSON" in err


# =============================================================================
# Annotation Formatting Tests
# =============================================================================


class TestFormatAnnotation:
    """Tests for formatting annotations in deny messages."""

    def test_format_replacement_annotation(self):
        """Test formatting a REPLACEMENT annotation."""
        annotation = {
            "type": "REPLACEMENT",
            "original_text": "old text",
            "new_text": "new text",
            "comment": None,
        }
        result = plan_approval.format_annotation(annotation)
        assert "[REPLACEMENT]" in result
        assert 'Original: "old text"' in result
        assert 'Replace with: "new text"' in result

    def test_format_deletion_annotation(self):
        """Test formatting a DELETION annotation."""
        annotation = {
            "type": "DELETION",
            "original_text": "text to delete",
            "new_text": None,
            "comment": None,
        }
        result = plan_approval.format_annotation(annotation)
        assert "[DELETION]" in result
        assert "Delete this text" in result

    def test_format_insertion_annotation(self):
        """Test formatting an INSERTION annotation."""
        annotation = {
            "type": "INSERTION",
            "original_text": "",
            "new_text": "inserted text",
            "comment": None,
        }
        result = plan_approval.format_annotation(annotation)
        assert "[INSERTION]" in result
        assert 'Insert: "inserted text"' in result

    def test_format_comment_annotation(self):
        """Test formatting a COMMENT annotation."""
        annotation = {
            "type": "COMMENT",
            "original_text": "some text",
            "new_text": None,
            "comment": "This needs clarification",
        }
        result = plan_approval.format_annotation(annotation)
        assert "[COMMENT]" in result
        assert "Comment: This needs clarification" in result

    def test_truncates_long_original_text(self):
        """Test that long original text is truncated."""
        long_text = "x" * 200
        annotation = {
            "type": "COMMENT",
            "original_text": long_text,
            "new_text": None,
            "comment": "Note",
        }
        result = plan_approval.format_annotation(annotation)
        assert "..." in result
        # Should truncate to 100 chars + "..."
        assert len(long_text) > 100

    def test_truncates_long_new_text(self):
        """Test that long new text is truncated."""
        long_text = "y" * 200
        annotation = {
            "type": "REPLACEMENT",
            "original_text": "short",
            "new_text": long_text,
            "comment": None,
        }
        result = plan_approval.format_annotation(annotation)
        assert "..." in result

    def test_truncates_long_comment(self):
        """Test that long comments are truncated."""
        long_comment = "z" * 200
        annotation = {
            "type": "COMMENT",
            "original_text": "text",
            "new_text": None,
            "comment": long_comment,
        }
        result = plan_approval.format_annotation(annotation)
        assert "..." in result


class TestFormatDenyMessage:
    """Tests for formatting the full deny message."""

    def test_format_changes_requested_with_feedback(self):
        """Test formatting deny message for changes_requested status."""
        status_data = {"latest_decision": {"feedback": "Please update the steps"}}
        result = plan_approval.format_deny_message("changes_requested", status_data, [])
        assert "changes have been requested" in result
        assert "Please update the steps" in result

    def test_format_pending_status(self):
        """Test formatting deny message for pending status."""
        result = plan_approval.format_deny_message("pending", {}, [])
        assert "pending review" in result
        assert "Please review and approve" in result

    def test_includes_annotations(self):
        """Test that annotations are included in deny message."""
        annotations = [{"type": "COMMENT", "original_text": "text", "comment": "Fix this"}]
        result = plan_approval.format_deny_message("pending", {}, annotations)
        assert "Annotations (1)" in result
        assert "[COMMENT]" in result

    def test_limits_annotations_to_10(self):
        """Test that only first 10 annotations are shown."""
        annotations = [
            {"type": "COMMENT", "original_text": f"text {i}", "comment": f"Note {i}"}
            for i in range(15)
        ]
        result = plan_approval.format_deny_message("pending", {}, annotations)
        assert "Annotations (15)" in result
        assert "and 5 more annotations" in result

    def test_includes_review_url(self):
        """Test that review URL is included."""
        result = plan_approval.format_deny_message("pending", {}, [])
        assert "http://localhost:5173/plans" in result

    def test_truncates_long_feedback(self):
        """Test that long feedback is truncated."""
        long_feedback = "a" * 600
        status_data = {"latest_decision": {"feedback": long_feedback}}
        result = plan_approval.format_deny_message("changes_requested", status_data, [])
        assert "..." in result


# =============================================================================
# Main Function Tests
# =============================================================================


class TestMain:
    """Tests for the main entry point function."""

    def test_non_exitplanmode_continues(self, capsys):
        """Test that non-ExitPlanMode tools get continue response."""
        event_data = {"tool_name": "Read", "tool_input": {"file_path": "/test"}}

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result == {"continue": True}

    def test_invalid_json_continues(self, capsys):
        """Test that invalid JSON input results in continue response."""
        with patch("sys.stdin.read", return_value="not valid json"):
            plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result == {"continue": True}

    def test_exitplanmode_no_slug_continues(self, capsys, tmp_path, monkeypatch):
        """Test ExitPlanMode with no extractable slug continues."""
        event_data = {"tool_name": "ExitPlanMode", "tool_input": {}}

        # Make sure no plans exist
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result == {"continue": True}

    def test_exitplanmode_approved_allows(self, capsys):
        """Test ExitPlanMode with approved plan allows."""
        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {"slug": "my-plan"},
        }

        mock_status_response = MagicMock()
        mock_status_response.read.return_value = b'{"status": "approved"}'
        mock_status_response.__enter__ = MagicMock(return_value=mock_status_response)
        mock_status_response.__exit__ = MagicMock(return_value=False)

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch("urllib.request.urlopen", return_value=mock_status_response):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result == {"hookSpecificOutput": {"decision": {"behavior": "allow"}}}

    def test_exitplanmode_pending_denies(self, capsys):
        """Test ExitPlanMode with pending plan denies."""
        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {"slug": "my-plan"},
        }

        # Mock both status and annotations responses
        def mock_urlopen(req, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            if "status" in url:
                mock_response.read.return_value = b'{"status": "pending"}'
            else:
                mock_response.read.return_value = b'{"annotations": []}'
            return mock_response

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["hookSpecificOutput"]["decision"]["behavior"] == "deny"
        assert "pending review" in result["hookSpecificOutput"]["decision"]["message"]

    def test_exitplanmode_changes_requested_denies(self, capsys):
        """Test ExitPlanMode with changes_requested status denies with feedback."""
        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {"slug": "my-plan"},
        }

        def mock_urlopen(req, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            if "status" in url:
                mock_response.read.return_value = json.dumps(
                    {
                        "status": "changes_requested",
                        "latest_decision": {"feedback": "Please add error handling"},
                    }
                ).encode()
            else:
                mock_response.read.return_value = b'{"annotations": []}'
            return mock_response

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["hookSpecificOutput"]["decision"]["behavior"] == "deny"
        message = result["hookSpecificOutput"]["decision"]["message"]
        assert "changes have been requested" in message
        assert "Please add error handling" in message

    def test_exitplanmode_with_annotations_denies(self, capsys):
        """Test ExitPlanMode with annotations denies even if approved."""
        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {"slug": "my-plan"},
        }

        def mock_urlopen(req, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            if "status" in url:
                # Status is pending (not approved)
                mock_response.read.return_value = b'{"status": "pending"}'
            else:
                # Has annotations
                mock_response.read.return_value = json.dumps(
                    {
                        "annotations": [
                            {
                                "type": "COMMENT",
                                "original_text": "step 1",
                                "comment": "Clarify this step",
                            }
                        ]
                    }
                ).encode()
            return mock_response

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["hookSpecificOutput"]["decision"]["behavior"] == "deny"
        message = result["hookSpecificOutput"]["decision"]["message"]
        assert "Annotations (1)" in message
        assert "[COMMENT]" in message

    def test_exitplanmode_api_unreachable_denies(self, capsys):
        """Test ExitPlanMode when API is unreachable denies."""
        from urllib.error import URLError

        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {"slug": "my-plan"},
        }

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch(
                "urllib.request.urlopen",
                side_effect=URLError("Connection refused"),
            ):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["hookSpecificOutput"]["decision"]["behavior"] == "deny"
        message = result["hookSpecificOutput"]["decision"]["message"]
        assert "API is not reachable" in message

    def test_exitplanmode_plan_not_found_denies(self, capsys):
        """Test ExitPlanMode when plan not found denies."""
        from urllib.error import HTTPError

        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {"slug": "nonexistent-plan"},
        }

        error = HTTPError(
            url="http://localhost:8000/plans/nonexistent-plan/status",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch("urllib.request.urlopen", side_effect=error):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["hookSpecificOutput"]["decision"]["behavior"] == "deny"
        message = result["hookSpecificOutput"]["decision"]["message"]
        assert "not found" in message


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestFullWorkflow:
    """Tests for complete approval workflow scenarios."""

    def test_extract_slug_from_path_then_check_status(self, capsys):
        """Test full workflow: extract slug from path, check approved status."""
        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {"plan_path": "~/.claude/plans/feature-auth-implementation.md"},
        }

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "approved"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch("urllib.request.urlopen", return_value=mock_response):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["hookSpecificOutput"]["decision"]["behavior"] == "allow"

    def test_fallback_to_active_plan_when_no_slug_in_input(self, capsys, tmp_path, monkeypatch):
        """Test falling back to most recent plan when no slug in tool_input."""
        # Create plans directory with a plan
        plans_dir = tmp_path / ".claude" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "active-plan.md").write_text("# Active Plan\n\nContent")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        event_data = {
            "tool_name": "ExitPlanMode",
            "tool_input": {},  # No slug provided
        }

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "approved"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("sys.stdin.read", return_value=json.dumps(event_data)):
            with patch("urllib.request.urlopen", return_value=mock_response):
                plan_approval.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        # Should have found the active plan and checked its status
        assert result["hookSpecificOutput"]["decision"]["behavior"] == "allow"
