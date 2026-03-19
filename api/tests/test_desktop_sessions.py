"""
Tests for desktop session detection and worktree merging service.

Tests platform-aware path detection, worktree identification,
and desktop metadata lookup.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Platform Detection: _get_desktop_sessions_dir
# =============================================================================


class TestGetDesktopSessionsDir:
    """Tests for _get_desktop_sessions_dir platform detection."""

    def test_macos_path(self):
        with patch("services.desktop_sessions.platform.system", return_value="Darwin"):
            from services.desktop_sessions import _get_desktop_sessions_dir

            result = _get_desktop_sessions_dir()
            assert result == (
                Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
            )

    def test_windows_path_with_appdata(self):
        with (
            patch("services.desktop_sessions.platform.system", return_value="Windows"),
            patch.dict("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}),
        ):
            from services.desktop_sessions import _get_desktop_sessions_dir

            result = _get_desktop_sessions_dir()
            assert (
                result
                == Path("C:\\Users\\test\\AppData\\Roaming") / "Claude" / "claude-code-sessions"
            )

    def test_windows_path_without_appdata(self, tmp_path: Path):
        with (
            patch("services.desktop_sessions.platform.system", return_value="Windows"),
            patch.dict("os.environ", {}, clear=True),
            patch("services.desktop_sessions.os.environ.get", return_value=None),
            patch("services.desktop_sessions.Path.home", return_value=tmp_path),
        ):
            from services.desktop_sessions import _get_desktop_sessions_dir

            result = _get_desktop_sessions_dir()
            assert result == (tmp_path / "AppData" / "Roaming" / "Claude" / "claude-code-sessions")

    def test_linux_path_default(self, tmp_path: Path):
        with (
            patch("services.desktop_sessions.platform.system", return_value="Linux"),
            patch.dict("os.environ", {}, clear=True),
            patch(
                "services.desktop_sessions.os.environ.get",
                side_effect=lambda k, d=None: d,
            ),
            patch("services.desktop_sessions.Path.home", return_value=tmp_path),
        ):
            from services.desktop_sessions import _get_desktop_sessions_dir

            result = _get_desktop_sessions_dir()
            assert result == (tmp_path / ".config" / "Claude" / "claude-code-sessions")

    def test_linux_path_with_xdg(self):
        with (
            patch("services.desktop_sessions.platform.system", return_value="Linux"),
            patch(
                "services.desktop_sessions.os.environ.get",
                side_effect=lambda k, d=None: "/custom/config" if k == "XDG_CONFIG_HOME" else d,
            ),
        ):
            from services.desktop_sessions import _get_desktop_sessions_dir

            result = _get_desktop_sessions_dir()
            assert result == Path("/custom/config/Claude/claude-code-sessions")


# =============================================================================
# Worktree Base: _get_worktree_base
# =============================================================================


class TestGetWorktreeBase:
    """Tests for _get_worktree_base with env var override."""

    def test_default_path(self, tmp_path: Path):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "services.desktop_sessions.os.environ.get",
                side_effect=lambda k, d=None: None if k == "CLAUDE_KARMA_WORKTREE_BASE" else d,
            ),
            patch("services.desktop_sessions.Path.home", return_value=tmp_path),
        ):
            from services.desktop_sessions import _get_worktree_base

            result = _get_worktree_base()
            assert result == tmp_path / ".claude-worktrees"

    def test_custom_path_via_env(self):
        with patch(
            "services.desktop_sessions.os.environ.get",
            side_effect=lambda k, d=None: (
                "/custom/worktrees" if k == "CLAUDE_KARMA_WORKTREE_BASE" else d
            ),
        ):
            from services.desktop_sessions import _get_worktree_base

            result = _get_worktree_base()
            assert result == Path("/custom/worktrees")


# =============================================================================
# is_worktree_project
# =============================================================================


class TestIsWorktreeProject:
    """Tests for is_worktree_project encoded name detection."""

    def test_worktree_with_dot_encoding(self):
        from services.desktop_sessions import is_worktree_project

        # Our encode_path preserves dots: -.claude-worktrees- does NOT
        # contain -claude-worktrees- (dot != dash), so this is False
        assert not is_worktree_project("-Users-test-.claude-worktrees-myproject-focused-jepsen")

    def test_worktree_with_dash_encoding(self):
        from services.desktop_sessions import is_worktree_project

        # Claude Code's encoding replaces dots with dashes
        assert is_worktree_project("-Users-test--claude-worktrees-myproject-focused-jepsen")

    def test_regular_project(self):
        from services.desktop_sessions import is_worktree_project

        assert not is_worktree_project("-Users-test-Documents-myproject")

    def test_empty_string(self):
        from services.desktop_sessions import is_worktree_project

        assert not is_worktree_project("")

    def test_partial_match(self):
        from services.desktop_sessions import is_worktree_project

        # Must contain the full marker
        assert not is_worktree_project("-Users-test-claude-worktrees")
        assert is_worktree_project("-Users-test-claude-worktrees-proj-wt")

    def test_cli_worktree_dot_claude_worktrees(self):
        """CLI worktrees at {project}/.claude/worktrees/{name}."""
        from services.desktop_sessions import is_worktree_project

        # Claude Code encodes .claude as -claude, producing --claude-worktrees-
        assert is_worktree_project(
            "-Users-jayantdevkar-Documents-GitHub-claude-karma--claude-worktrees-fix-command-skill-tracking"
        )

    def test_superpowers_dot_worktrees(self):
        """Superpowers worktrees at {project}/.worktrees/{name}."""
        from services.desktop_sessions import is_worktree_project

        # Claude Code encodes .worktrees as -worktrees, producing --worktrees-
        assert is_worktree_project(
            "-Users-jayantdevkar-Documents-GitHub-claude-karma--worktrees-fix-command-skill-tracking"
        )
        # Our encode_path preserves dots
        assert is_worktree_project(
            "-Users-jayantdevkar-Documents-GitHub-claude-karma-.worktrees-fix-command-skill-tracking"
        )


# =============================================================================
# _extract_project_prefix_from_worktree
# =============================================================================


class TestExtractProjectPrefixFromWorktree:
    """Tests for _extract_project_prefix_from_worktree encoded name parsing."""

    def test_cli_worktree_double_dash(self):
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        result = _extract_project_prefix_from_worktree(
            "-Users-jayantdevkar-Documents-GitHub-claude-karma--claude-worktrees-fix-branch"
        )
        assert result == "-Users-jayantdevkar-Documents-GitHub-claude-karma"

    def test_cli_worktree_dot_preserved(self):
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        result = _extract_project_prefix_from_worktree(
            "-Users-test-myproject-.claude-worktrees-feature-x"
        )
        assert result == "-Users-test-myproject"

    def test_superpowers_worktree_double_dash(self):
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        result = _extract_project_prefix_from_worktree("-Users-test-myproject--worktrees-fix-bug")
        assert result == "-Users-test-myproject"

    def test_superpowers_worktree_dot_preserved(self):
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        result = _extract_project_prefix_from_worktree("-Users-test-myproject-.worktrees-fix-bug")
        assert result == "-Users-test-myproject"

    def test_desktop_worktree_no_project_prefix(self):
        """Desktop worktrees (~/. claude-worktrees/) don't have a project prefix."""
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        # This is a Desktop worktree — the path before the marker is the home dir,
        # not a project. Strategy C will return the prefix, but the caller verifies
        # it exists on disk (which it won't as a project dir).
        result = _extract_project_prefix_from_worktree(
            "-Users-test--claude-worktrees-myproject-focused-jepsen"
        )
        # Returns a prefix (Strategy C doesn't know it's not a project)
        assert result == "-Users-test"

    def test_no_marker_returns_none(self):
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        result = _extract_project_prefix_from_worktree("-Users-test-normal-project")
        assert result is None

    def test_empty_string(self):
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        assert _extract_project_prefix_from_worktree("") is None

    def test_marker_at_start_returns_none(self):
        """If marker is at position 0, no valid prefix exists."""
        from services.desktop_sessions import _extract_project_prefix_from_worktree

        assert _extract_project_prefix_from_worktree("--claude-worktrees-foo") is None


# =============================================================================
# extract_worktree_info
# =============================================================================


class TestExtractWorktreeInfo:
    """Tests for extract_worktree_info filesystem scan."""

    def test_non_worktree_returns_none(self):
        from services.desktop_sessions import extract_worktree_info

        assert extract_worktree_info("-Users-test-myproject") is None

    def test_missing_worktree_base_returns_none(self, tmp_path):
        from services.desktop_sessions import extract_worktree_info

        with patch(
            "services.desktop_sessions.WORKTREE_BASE",
            tmp_path / "nonexistent",
        ):
            result = extract_worktree_info("-Users-test-.claude-worktrees-proj-wt")
            assert result is None

    def test_matching_worktree_found(self, tmp_path):
        # Use a dir name without leading dot so the encoded form
        # contains -claude-worktrees- (passing is_worktree_project check)
        wt_base = tmp_path / "claude-worktrees"
        project_dir = wt_base / "myproject"
        worktree_dir = project_dir / "focused-jepsen"
        worktree_dir.mkdir(parents=True)

        from models.project import Project

        encoded = Project.encode_path(str(worktree_dir))
        # Verify the encoded name passes the worktree check
        assert "-claude-worktrees-" in encoded

        with patch("services.desktop_sessions.WORKTREE_BASE", wt_base):
            from services.desktop_sessions import extract_worktree_info

            result = extract_worktree_info(encoded)
            assert result is not None
            assert result["project_name"] == "myproject"
            assert result["worktree_name"] == "focused-jepsen"

    def test_dot_dash_encoding_variant(self, tmp_path):
        """Test that dots-replaced-by-dashes encoding also matches."""
        wt_base = tmp_path / ".claude-worktrees"
        project_dir = wt_base / "myproject"
        worktree_dir = project_dir / "focused-jepsen"
        worktree_dir.mkdir(parents=True)

        from models.project import Project

        encoded = Project.encode_path(str(worktree_dir))
        # Simulate Claude Code's dot->dash encoding
        encoded_dots = encoded.replace(".", "-")

        with patch("services.desktop_sessions.WORKTREE_BASE", wt_base):
            from services.desktop_sessions import extract_worktree_info

            result = extract_worktree_info(encoded_dots)
            assert result is not None
            assert result["project_name"] == "myproject"
            assert result["worktree_name"] == "focused-jepsen"


# =============================================================================
# get_session_source
# =============================================================================


class TestGetSessionSource:
    """Tests for get_session_source desktop metadata lookup."""

    def test_session_in_desktop_metadata(self):
        mock_meta = {
            "session-uuid-123": {
                "originCwd": "/Users/test/project",
                "worktreeName": "focused-jepsen",
            }
        }
        with patch(
            "services.desktop_sessions.load_desktop_metadata",
            return_value=mock_meta,
        ):
            from services.desktop_sessions import get_session_source

            assert get_session_source("session-uuid-123") == "desktop"

    def test_session_not_in_desktop_metadata(self):
        with patch(
            "services.desktop_sessions.load_desktop_metadata",
            return_value={},
        ):
            from services.desktop_sessions import get_session_source

            assert get_session_source("unknown-uuid") is None


# =============================================================================
# _load_desktop_metadata_impl
# =============================================================================


class TestLoadDesktopMetadataImpl:
    """Tests for _load_desktop_metadata_impl file parsing."""

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        with patch(
            "services.desktop_sessions.DESKTOP_SESSIONS_DIR",
            tmp_path / "nonexistent",
        ):
            from services.desktop_sessions import _load_desktop_metadata_impl

            assert _load_desktop_metadata_impl() == {}

    def test_parses_session_files(self, tmp_path):
        # Create Desktop sessions structure
        account_dir = tmp_path / "account-uuid"
        project_dir = account_dir / "project-uuid"
        project_dir.mkdir(parents=True)

        session_data = {
            "cliSessionId": "cli-session-abc",
            "originCwd": "/Users/test/myproject",
            "worktreeName": "focused-jepsen",
            "title": "Test Session",
            "model": "claude-opus-4-5-20251101",
            "isArchived": False,
            "cwd": "/Users/test/.claude-worktrees/myproject/focused-jepsen",
        }
        session_file = project_dir / "local_session-uuid.json"
        session_file.write_text(json.dumps(session_data))

        with patch("services.desktop_sessions.DESKTOP_SESSIONS_DIR", tmp_path):
            from services.desktop_sessions import _load_desktop_metadata_impl

            result = _load_desktop_metadata_impl()

        assert "cli-session-abc" in result
        meta = result["cli-session-abc"]
        assert meta["originCwd"] == "/Users/test/myproject"
        assert meta["worktreeName"] == "focused-jepsen"
        assert meta["title"] == "Test Session"
        assert meta["model"] == "claude-opus-4-5-20251101"
        assert meta["isArchived"] is False

    def test_skips_invalid_json(self, tmp_path):
        account_dir = tmp_path / "account-uuid"
        project_dir = account_dir / "project-uuid"
        project_dir.mkdir(parents=True)

        # Write invalid JSON
        (project_dir / "local_bad.json").write_text("not json{{{")

        # Write valid JSON without cliSessionId
        (project_dir / "local_nocli.json").write_text(json.dumps({"title": "no cli id"}))

        # Write valid session
        valid_data = {
            "cliSessionId": "valid-session",
            "originCwd": "/Users/test/proj",
        }
        (project_dir / "local_good.json").write_text(json.dumps(valid_data))

        with patch("services.desktop_sessions.DESKTOP_SESSIONS_DIR", tmp_path):
            from services.desktop_sessions import _load_desktop_metadata_impl

            result = _load_desktop_metadata_impl()

        # Only the valid session with cliSessionId should be present
        assert len(result) == 1
        assert "valid-session" in result

    def test_skips_non_local_files(self, tmp_path):
        account_dir = tmp_path / "account-uuid"
        project_dir = account_dir / "project-uuid"
        project_dir.mkdir(parents=True)

        # File that doesn't match local_*.json pattern
        data = {"cliSessionId": "should-not-appear"}
        (project_dir / "remote_session.json").write_text(json.dumps(data))

        with patch("services.desktop_sessions.DESKTOP_SESSIONS_DIR", tmp_path):
            from services.desktop_sessions import _load_desktop_metadata_impl

            result = _load_desktop_metadata_impl()

        assert len(result) == 0


# =============================================================================
# get_real_project_encoded_name
# =============================================================================


class TestGetRealProjectEncodedName:
    """Tests for get_real_project_encoded_name resolution strategies."""

    def test_strategy_b_desktop_metadata(self, tmp_path):
        """Strategy B: resolve via Desktop metadata originCwd."""
        projects_dir = tmp_path / "projects"
        real_project = projects_dir / "-Users-test-myproject"
        real_project.mkdir(parents=True)

        mock_meta = {
            "session-uuid-1": {
                "originCwd": "/Users/test/myproject",
            }
        }

        with (
            patch(
                "services.desktop_sessions.load_desktop_metadata",
                return_value=mock_meta,
            ),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.projects_dir = projects_dir

            from services.desktop_sessions import get_real_project_encoded_name

            result = get_real_project_encoded_name(
                "-Users-test--claude-worktrees-myproject-wt",
                ["session-uuid-1"],
            )
            assert result == "-Users-test-myproject"

    def test_strategy_a_filesystem_fallback(self, tmp_path):
        """Strategy A: resolve via worktree filesystem scan."""
        projects_dir = tmp_path / "projects"
        real_project = projects_dir / "-Users-test-myproject"
        real_project.mkdir(parents=True)

        # Use dir name without dot so encoded form passes is_worktree_project
        wt_base = tmp_path / "claude-worktrees"
        wt_dir = wt_base / "myproject" / "focused-jepsen"
        wt_dir.mkdir(parents=True)

        from models.project import Project

        encoded_wt = Project.encode_path(str(wt_dir))

        with (
            patch(
                "services.desktop_sessions.load_desktop_metadata",
                return_value={},
            ),
            patch("services.desktop_sessions.WORKTREE_BASE", wt_base),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.projects_dir = projects_dir

            from services.desktop_sessions import get_real_project_encoded_name

            result = get_real_project_encoded_name(encoded_wt, ["no-match-uuid"])
            assert result == "-Users-test-myproject"

    def test_strategy_c_cli_worktree_prefix(self, tmp_path):
        """Strategy C: resolve CLI worktree by parsing encoded name prefix."""
        projects_dir = tmp_path / "projects"
        real_project = projects_dir / "-Users-jayantdevkar-Documents-GitHub-claude-karma"
        real_project.mkdir(parents=True)

        worktree_encoded = (
            "-Users-jayantdevkar-Documents-GitHub-claude-karma"
            "--claude-worktrees-fix-command-skill-tracking"
        )

        with (
            patch(
                "services.desktop_sessions.load_desktop_metadata",
                return_value={},
            ),
            patch(
                "services.desktop_sessions.WORKTREE_BASE",
                tmp_path / "nonexistent",
            ),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.projects_dir = projects_dir

            from services.desktop_sessions import get_real_project_encoded_name

            result = get_real_project_encoded_name(worktree_encoded, ["no-match-uuid"])
            assert result == "-Users-jayantdevkar-Documents-GitHub-claude-karma"

    def test_strategy_c_superpowers_worktree(self, tmp_path):
        """Strategy C: resolve .worktrees/ (superpowers) by prefix parsing."""
        projects_dir = tmp_path / "projects"
        real_project = projects_dir / "-Users-jayantdevkar-Documents-GitHub-claude-karma"
        real_project.mkdir(parents=True)

        worktree_encoded = (
            "-Users-jayantdevkar-Documents-GitHub-claude-karma"
            "--worktrees-fix-command-skill-tracking"
        )

        with (
            patch(
                "services.desktop_sessions.load_desktop_metadata",
                return_value={},
            ),
            patch(
                "services.desktop_sessions.WORKTREE_BASE",
                tmp_path / "nonexistent",
            ),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.projects_dir = projects_dir

            from services.desktop_sessions import get_real_project_encoded_name

            result = get_real_project_encoded_name(worktree_encoded, ["no-match-uuid"])
            assert result == "-Users-jayantdevkar-Documents-GitHub-claude-karma"

    def test_strategy_c_prefix_not_on_disk(self, tmp_path):
        """Strategy C: if parsed prefix doesn't exist on disk, falls through."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir(parents=True)
        # Don't create the real project dir

        worktree_encoded = "-Users-test-nonexistent-project--claude-worktrees-some-branch"

        with (
            patch(
                "services.desktop_sessions.load_desktop_metadata",
                return_value={},
            ),
            patch(
                "services.desktop_sessions.WORKTREE_BASE",
                tmp_path / "nonexistent",
            ),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.projects_dir = projects_dir

            from services.desktop_sessions import get_real_project_encoded_name

            result = get_real_project_encoded_name(worktree_encoded, ["no-match"])
            assert result is None

    def test_no_match_returns_none(self):
        with (
            patch(
                "services.desktop_sessions.load_desktop_metadata",
                return_value={},
            ),
            patch(
                "services.desktop_sessions.extract_worktree_info",
                return_value=None,
            ),
        ):
            from services.desktop_sessions import get_real_project_encoded_name

            result = get_real_project_encoded_name("-Users-test-unknown", ["no-match"])
            assert result is None
