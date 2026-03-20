"""
Cross-platform path tests for Windows/Mac/Linux support.

These tests validate the full path lifecycle:
  encode → directory creation → session cwd recovery → decode → display

They use mock Windows project directories and session data to verify
correct behavior on any host OS. When run on the Windows CI runner,
they also validate real pathlib behavior with Windows paths.
"""

import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from models.project import Project, _is_absolute_path
from utils import is_encoded_project_dir

# =============================================================================
# Encoding Roundtrip Tests (all platforms)
# =============================================================================


class TestEncodingRoundtrip:
    """Verify encode/decode roundtrip for common path patterns on each platform."""

    @pytest.mark.parametrize(
        "original,encoded",
        [
            # Unix paths
            ("/Users/me/repo", "-Users-me-repo"),
            ("/home/user/projects/app", "-home-user-projects-app"),
            ("/Users/me/Documents/GitHub/claude-karma", "-Users-me-Documents-GitHub-claude-karma"),
            # Windows paths
            ("C:\\Users\\test\\repo", "C--Users-test-repo"),
            ("C:\\Code\\Tools", "C--Code-Tools"),
            ("D:\\Projects\\myapp", "D--Projects-myapp"),
            ("C:/Users/test/repo", "C--Users-test-repo"),
            # Mixed separators (Windows)
            ("C:\\Users/test\\myproject", "C--Users-test-myproject"),
        ],
    )
    def test_encode_produces_expected(self, original, encoded):
        assert Project.encode_path(original) == encoded

    @pytest.mark.parametrize(
        "encoded,decoded",
        [
            # Unix
            ("-Users-me-repo", "/Users/me/repo"),
            ("-home-user-projects-app", "/home/user/projects/app"),
            # Windows
            ("C--Users-test-repo", "C:/Users/test/repo"),
            ("C--Code-Tools", "C:/Code/Tools"),
            ("D--Projects-myapp", "D:/Projects/myapp"),
            # Lowercase drive normalizes to uppercase
            ("c--Code-Tools", "C:/Code/Tools"),
        ],
    )
    def test_decode_produces_expected(self, encoded, decoded):
        assert Project.decode_path(encoded) == decoded

    @pytest.mark.parametrize(
        "path",
        [
            "/Users/me/repo",
            "/home/user/projects/app",
            "C:\\Code\\Tools",
            "D:\\Projects\\myapp",
        ],
    )
    def test_encode_then_decode_preserves_structure(self, path):
        """Encode then decode should produce a valid path (forward slashes)."""
        encoded = Project.encode_path(path)
        decoded = Project.decode_path(encoded)
        # Normalize original for comparison (backslash → forward slash)
        normalized = path.replace("\\", "/")
        assert decoded == normalized


# =============================================================================
# Directory Filter Tests (all platforms)
# =============================================================================


class TestDirectoryFilterCrossPlatform:
    """Verify is_encoded_project_dir works for all platform patterns."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            # Valid Unix
            ("-Users-me-repo", True),
            ("-home-user-app", True),
            ("-", False),  # Bare dash (root "/") rejected — Claude Code never creates it
            # Valid Windows
            ("C--Code-Tools", True),
            ("D--Projects-myapp", True),
            ("c--Users-test", True),
            # Invalid (non-project dirs)
            ("memory", False),
            ("__pycache__", False),
            (".git", False),
            ("", False),
            ("C-something", False),  # Single dash, not double
            ("CC--something", False),  # Two letters before --
        ],
    )
    def test_filter(self, name, expected):
        assert is_encoded_project_dir(name) == expected


# =============================================================================
# Cross-Platform Absolute Path Detection
# =============================================================================


class TestIsAbsolutePathCrossPlatform:
    """Verify _is_absolute_path recognizes all platform formats on any host."""

    @pytest.mark.parametrize(
        "path,expected",
        [
            # Unix
            ("/Users/test/repo", True),
            ("/home/user/app", True),
            ("/", True),
            # Windows drive letter
            ("C:\\Users\\test\\repo", True),
            ("C:/Users/test/repo", True),
            ("d:\\Projects\\myapp", True),
            ("D:/Projects/myapp", True),
            # Windows UNC
            ("\\\\server\\share\\folder", True),
            ("//server/share/folder", True),
            # Relative (should reject)
            ("src/main.py", False),
            ("relative/path", False),
            ("", False),
            ("C:", False),  # Drive letter without separator
        ],
    )
    def test_absolute_detection(self, path, expected):
        assert _is_absolute_path(path) == expected


# =============================================================================
# Windows Session CWD Recovery (mock filesystem)
# =============================================================================


class TestWindowsSessionCwdRecovery:
    """Test that Windows cwd values from JSONL are correctly recovered and normalized."""

    def test_recovers_windows_backslash_cwd(
        self, temp_windows_project_dir, sample_windows_session_jsonl, temp_claude_dir
    ):
        """Windows backslash cwd should be recovered and normalized to forward slashes."""
        result = Project._extract_real_path_from_sessions(temp_windows_project_dir)
        assert result == "C:/Users/test/myproject"

    def test_from_encoded_name_with_windows_session(
        self, temp_windows_project_dir, sample_windows_session_jsonl, temp_claude_dir
    ):
        """from_encoded_name should use cwd from Windows session data."""
        project = Project.from_encoded_name(
            "C--Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )
        assert project.path == "C:/Users/test/myproject"
        assert project.encoded_name == "C--Users-test-myproject"

    def test_from_encoded_name_windows_lossy_decode(self, temp_claude_dir):
        """Without session data, Windows encoded name decodes lossily."""
        # Create empty Windows project dir (no session files)
        win_dir = temp_claude_dir / "projects" / "D--Projects-myapp"
        win_dir.mkdir(parents=True)

        project = Project.from_encoded_name(
            "D--Projects-myapp",
            claude_projects_dir=temp_claude_dir / "projects",
        )
        # Falls back to lossy decode
        assert project.path == "D:/Projects/myapp"

    def test_windows_cwd_forward_slash_passthrough(self, temp_claude_dir):
        """Windows cwd already using forward slashes should pass through unchanged."""
        win_dir = temp_claude_dir / "projects" / "C--Code-Tools"
        win_dir.mkdir(parents=True)
        session = win_dir / "session.jsonl"
        session.write_text('{"cwd": "C:/Code/Tools", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(win_dir)
        assert result == "C:/Code/Tools"


# =============================================================================
# Mixed Project Listing (Unix + Windows dirs coexist)
# =============================================================================


class TestMixedProjectListing:
    """Test that Unix and Windows project dirs are both discovered correctly."""

    def test_both_platforms_detected(self, temp_claude_dir):
        """Both Unix and Windows encoded dirs should pass the filter."""
        projects_dir = temp_claude_dir / "projects"

        # Create dirs for both platforms
        (projects_dir / "-Users-me-repo").mkdir()
        (projects_dir / "C--Users-test-repo").mkdir()
        (projects_dir / "D--Projects-myapp").mkdir()
        # Non-project dirs (should be filtered out)
        (projects_dir / "memory").mkdir()
        (projects_dir / "__pycache__").mkdir()

        project_dirs = [
            d.name for d in projects_dir.iterdir() if d.is_dir() and is_encoded_project_dir(d.name)
        ]

        assert sorted(project_dirs) == sorted(
            ["-Users-me-repo", "C--Users-test-repo", "D--Projects-myapp"]
        )

    def test_windows_project_full_lifecycle(self, temp_claude_dir):
        """Full lifecycle: create Windows dir → write session → recover path → validate."""
        projects_dir = temp_claude_dir / "projects"
        encoded = "C--Users-test-Documents-GitHub-myapp"
        win_dir = projects_dir / encoded
        win_dir.mkdir(parents=True)

        # Write session with Windows cwd
        session = win_dir / "lifecycle-test.jsonl"
        session.write_text(
            json.dumps(
                {
                    "cwd": "C:\\Users\\test\\Documents\\GitHub\\myapp",
                    "type": "user",
                    "sessionId": "lifecycle-test",
                    "message": {"role": "user", "content": "test"},
                    "uuid": "msg-001",
                    "timestamp": "2026-03-18T10:00:00.000Z",
                }
            )
            + "\n"
        )

        # Recover via from_encoded_name
        project = Project.from_encoded_name(encoded, claude_projects_dir=projects_dir)

        assert project.path == "C:/Users/test/Documents/GitHub/myapp"
        assert project.encoded_name == encoded
        # Re-encoding the recovered path should match
        assert Project.encode_path(project.path) == encoded


# =============================================================================
# Platform-Specific Tests (only run on the matching OS)
# =============================================================================


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only pathlib tests")
class TestWindowsNativePathlib:
    """Tests that validate real Windows pathlib behavior. Only run on Windows CI."""

    def test_path_is_absolute_native(self):
        """On real Windows, Path('C:/...').is_absolute() should be True."""
        assert Path("C:/Users/test/repo").is_absolute()
        assert Path("C:\\Users\\test\\repo").is_absolute()

    def test_path_name_extraction(self):
        """Path.name should extract last component on Windows."""
        assert Path("C:/Users/test/repo").name == "repo"
        assert Path("C:\\Users\\test\\repo").name == "repo"

    def test_path_join(self):
        """Path / '.git' should work with Windows paths."""
        git_path = Path("C:/Users/test/repo") / ".git"
        assert str(git_path).endswith(".git")

    def test_git_root_on_windows(self, temp_git_repo):
        """resolve_git_root should work with the native Windows subprocess."""
        from utils import resolve_git_root

        result = resolve_git_root(str(temp_git_repo))
        assert result is not None
        # Git on Windows returns forward-slash paths
        assert "test-repo" in result


@pytest.mark.skipif(platform.system() == "Windows", reason="Non-Windows cross-platform tests")
class TestNonWindowsCrossPlatform:
    """Tests that verify Windows path handling works correctly on Mac/Linux."""

    def test_pathlib_does_not_recognize_windows_absolute(self):
        """On Mac/Linux, pathlib does NOT recognize C:\\ as absolute — our helper does."""
        # This is WHY we need _is_absolute_path()
        assert not Path("C:\\Users\\test").is_absolute()
        assert _is_absolute_path("C:\\Users\\test")

    def test_pathlib_name_with_forward_slash_windows_path(self):
        """On Mac/Linux, Path('C:/Code/Tools').name works with forward slashes."""
        # Forward-slash Windows paths work on all platforms
        assert Path("C:/Code/Tools").name == "Tools"

    def test_pathlib_name_with_backslash_fails_on_posix(self):
        """On Mac/Linux, Path('C:\\Code\\Tools').name returns the whole string."""
        # This is why we normalize backslashes before using pathlib
        assert Path("C:\\Code\\Tools").name == "C:\\Code\\Tools"
