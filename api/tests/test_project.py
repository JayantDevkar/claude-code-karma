"""
Comprehensive unit tests for the Project model.

Tests cover:
- Project instantiation
- Path encoding/decoding
- Factory methods (from_path, from_encoded_name)
- Properties (project_dir, exists, claude_base_dir)
- Session listing and retrieval
- Agent listing and retrieval
- Aggregate queries
- Immutability
"""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import Agent, Project, Session
from utils import is_encoded_project_dir


class TestProjectInstantiation:
    """Tests for Project instantiation with all fields."""

    def test_instantiate_with_all_fields(self, temp_claude_dir: Path):
        """Test creating a Project with all required and optional fields."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.path == "/Users/test/myproject"
        assert project.encoded_name == "-Users-test-myproject"
        assert project.claude_projects_dir == temp_claude_dir / "projects"

    def test_instantiate_with_default_claude_projects_dir(self):
        """Test creating a Project with default claude_projects_dir."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
        )

        assert project.path == "/Users/test/myproject"
        assert project.encoded_name == "-Users-test-myproject"
        assert project.claude_projects_dir == Path.home() / ".claude" / "projects"

    def test_instantiate_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            Project(path="/Users/test/myproject")  # Missing encoded_name

        with pytest.raises(ValidationError):
            Project(encoded_name="-Users-test-myproject")  # Missing path


class TestEncodePath:
    """Tests for Project.encode_path() static method."""

    def test_encode_simple_unix_path(self):
        """Test encoding a simple Unix path."""
        result = Project.encode_path("/Users/test/myproject")
        assert result == "-Users-test-myproject"

    def test_encode_root_path(self):
        """Test encoding the root path."""
        result = Project.encode_path("/")
        assert result == "-"

    def test_encode_deeply_nested_path(self):
        """Test encoding a deeply nested path."""
        result = Project.encode_path("/Users/test/Documents/Projects/myapp")
        assert result == "-Users-test-Documents-Projects-myapp"

    def test_encode_path_with_single_component(self):
        """Test encoding a path with single component after root."""
        result = Project.encode_path("/Users")
        assert result == "-Users"

    def test_encode_path_object(self):
        """Test encoding a Path object."""
        result = Project.encode_path(Path("/Users/test/myproject"))
        assert result == "-Users-test-myproject"

    def test_encode_path_without_leading_slash(self):
        """Test encoding a relative path (no leading slash, no drive letter)."""
        # Relative paths go through the else branch: colon+slash replaced with dash
        # No leading dash since there's no leading /
        result = Project.encode_path("Users/test/myproject")
        assert result == "Users-test-myproject"


class TestEncodePathWindows:
    """Tests for Project.encode_path() with Windows paths."""

    def test_encode_windows_absolute_path(self):
        """Test encoding a Windows absolute path (C:\\...)."""
        # Windows: C:\Code\Tools -> normalize -> C:/Code/Tools
        # Then replace : and / with - -> C--Code-Tools
        result = Project.encode_path("C:\\Code\\Tools")
        assert result == "C--Code-Tools"

    def test_encode_windows_user_path(self):
        """Test encoding a Windows user path."""
        result = Project.encode_path("C:\\Users\\test\\myproject")
        assert result == "C--Users-test-myproject"

    def test_encode_mixed_slashes(self):
        """Test encoding path with mixed forward and back slashes."""
        result = Project.encode_path("C:\\Users/test\\myproject")
        assert result == "C--Users-test-myproject"

    def test_encode_windows_different_drive(self):
        """Test encoding a path on D: drive."""
        result = Project.encode_path("D:\\Projects\\myapp")
        assert result == "D--Projects-myapp"

    def test_encode_windows_unc_path(self):
        """Test encoding Windows UNC path."""
        result = Project.encode_path("\\\\server\\share\\folder")
        # Backslashes converted to forward, then to dashes
        assert result == "--server-share-folder"


class TestDecodePath:
    """Tests for Project.decode_path() static method."""

    def test_decode_simple_encoded_name(self):
        """Test decoding a simple encoded name back to path."""
        result = Project.decode_path("-Users-test-myproject")
        assert result == "/Users/test/myproject"

    def test_decode_root_encoded(self):
        """Test decoding encoded root path."""
        result = Project.decode_path("-")
        assert result == "/"

    def test_decode_deeply_nested(self):
        """Test decoding deeply nested encoded path."""
        result = Project.decode_path("-Users-test-Documents-Projects-myapp")
        assert result == "/Users/test/Documents/Projects/myapp"

    def test_decode_roundtrip(self):
        """Test that encode/decode roundtrip works for paths without dashes."""
        original = "/Users/test/myproject"
        encoded = Project.encode_path(original)
        decoded = Project.decode_path(encoded)
        assert decoded == original

    def test_decode_lossy_for_paths_with_dashes(self):
        """Test that decode is lossy for paths containing dashes."""
        # Original path with dash: /Users/my-project
        # Encoded: -Users-my-project
        # Decoded: /Users/my/project (lossy - dash becomes slash)
        original = "/Users/my-project"
        encoded = Project.encode_path(original)
        decoded = Project.decode_path(encoded)
        # This demonstrates the lossy nature
        assert decoded != original
        assert decoded == "/Users/my/project"


class TestDecodePathWindows:
    """Tests for Project.decode_path() with Windows-encoded names."""

    def test_decode_windows_c_drive(self):
        """Test decoding a Windows C: drive encoded path."""
        result = Project.decode_path("C--Code-Tools")
        assert result == "C:/Code/Tools"

    def test_decode_windows_d_drive(self):
        """Test decoding a Windows D: drive encoded path."""
        result = Project.decode_path("D--Projects-myapp")
        assert result == "D:/Projects/myapp"

    def test_decode_windows_user_path(self):
        """Test decoding a Windows user directory encoded path."""
        result = Project.decode_path("C--Users-test-myproject")
        assert result == "C:/Users/test/myproject"

    def test_decode_windows_lowercase_drive(self):
        """Test decoding with lowercase drive letter normalizes to uppercase."""
        result = Project.decode_path("c--Code-Tools")
        assert result == "C:/Code/Tools"

    def test_decode_windows_roundtrip(self):
        """Test encode/decode roundtrip for Windows paths (lossy for dashes)."""
        original = "C:\\Code\\Tools"
        encoded = Project.encode_path(original)
        assert encoded == "C--Code-Tools"
        decoded = Project.decode_path(encoded)
        assert decoded == "C:/Code/Tools"  # Forward slashes in decoded output


class TestIsEncodedProjectDir:
    """Tests for is_encoded_project_dir() utility function."""

    def test_unix_encoded_path(self):
        """Unix-encoded dirs start with dash."""
        assert is_encoded_project_dir("-Users-me-repo") is True

    def test_unix_root_rejected(self):
        """A bare dash (filesystem root '/') is rejected — Claude Code never creates it."""
        assert is_encoded_project_dir("-") is False

    def test_windows_c_drive(self):
        """Windows C: drive encoded path."""
        assert is_encoded_project_dir("C--Code-Tools") is True

    def test_windows_d_drive(self):
        """Windows D: drive encoded path."""
        assert is_encoded_project_dir("D--Projects-myapp") is True

    def test_windows_lowercase_drive(self):
        """Windows lowercase drive letter."""
        assert is_encoded_project_dir("c--Users-test") is True

    def test_rejects_plain_directory(self):
        """Non-project dirs like 'memory' should be rejected."""
        assert is_encoded_project_dir("memory") is False

    def test_rejects_pycache(self):
        """__pycache__ should be rejected."""
        assert is_encoded_project_dir("__pycache__") is False

    def test_rejects_dotdir(self):
        """Hidden directories should be rejected."""
        assert is_encoded_project_dir(".git") is False

    def test_rejects_empty_string(self):
        """Empty string should be rejected."""
        assert is_encoded_project_dir("") is False

    def test_rejects_single_letter(self):
        """Single letter without -- should be rejected."""
        assert is_encoded_project_dir("C") is False

    def test_rejects_letter_single_dash(self):
        """Letter with single dash is not a Windows pattern."""
        assert is_encoded_project_dir("C-something") is False


class TestIsAbsolutePath:
    """Tests for _is_absolute_path() cross-platform helper."""

    def test_unix_absolute(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("/Users/test/repo") is True

    def test_unix_root(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("/") is True

    def test_windows_backslash(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("C:\\Users\\test\\repo") is True

    def test_windows_forward_slash(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("C:/Users/test/repo") is True

    def test_windows_lowercase_drive(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("d:/Projects/myapp") is True

    def test_windows_unc_backslash(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("\\\\server\\share\\folder") is True

    def test_windows_unc_forward_slash(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("//server/share/folder") is True

    def test_rejects_relative(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("src/main.py") is False

    def test_rejects_bare_drive_letter(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("C:") is False

    def test_rejects_empty(self):
        from models.project import _is_absolute_path

        assert _is_absolute_path("") is False


class TestHistoryEncodePathDelegation:
    """Tests that history.encode_path delegates to the canonical Project.encode_path."""

    def test_unix_path(self):
        from models.history import encode_path

        assert encode_path("/Users/test/repo") == "-Users-test-repo"

    def test_windows_path(self):
        from models.history import encode_path

        assert encode_path("C:\\Code\\Tools") == "C--Code-Tools"

    def test_windows_forward_slash(self):
        from models.history import encode_path

        assert encode_path("C:/Users/test/repo") == "C--Users-test-repo"


class TestGetProjectName:
    """Tests for history.get_project_name() cross-platform behavior."""

    def test_unix_path_returns_last_two_segments(self):
        from models.history import get_project_name

        assert get_project_name("/Users/me/my-project") == "me/my-project"

    def test_windows_backslash_path_returns_last_two_segments(self):
        from models.history import get_project_name

        # Without the fix, this returns "C:\\Users\\me\\my-project" (the whole raw path)
        assert get_project_name("C:\\Users\\me\\my-project") == "me/my-project"

    def test_windows_forward_slash_path(self):
        from models.history import get_project_name

        assert get_project_name("C:/Users/me/my-project") == "me/my-project"

    def test_single_segment_unix(self):
        from models.history import get_project_name

        # split("/") on "/repo" gives ["", "repo"] — last 2 joined = "/repo"
        assert get_project_name("/repo") == "/repo"

    def test_single_segment_windows(self):
        from models.history import get_project_name

        # normalized "C:\\repo" → "C:/repo", split gives ["C:", "repo"] → "C:/repo"
        assert get_project_name("C:\\repo") == "C:/repo"


class TestFromPath:
    """Tests for Project.from_path() factory method."""

    def test_from_path_absolute(self, temp_claude_dir: Path, tmp_path: Path):
        """Test creating Project from absolute path (OS-appropriate path)."""
        project_path = tmp_path / "myproject"
        project = Project.from_path(
            str(project_path),
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.path == str(project_path)
        assert project.encoded_name == Project.encode_path(str(project_path))
        assert project.claude_projects_dir == temp_claude_dir / "projects"

    def test_from_path_with_path_object(self, temp_claude_dir: Path, tmp_path: Path):
        """Test creating Project from Path object (OS-appropriate path)."""
        project_path = tmp_path / "myproject"
        project = Project.from_path(
            project_path,
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.path == str(project_path)
        assert project.encoded_name == Project.encode_path(str(project_path))

    def test_from_path_default_claude_projects_dir(self, tmp_path: Path):
        """Test creating Project with default claude_projects_dir."""
        project = Project.from_path(tmp_path / "myproject")

        assert project.claude_projects_dir == Path.home() / ".claude" / "projects"


class TestFromPathValueError:
    """Tests for Project.from_path() raising ValueError for relative paths."""

    def test_from_path_relative_raises_valueerror(self):
        """Test that relative path raises ValueError."""
        with pytest.raises(ValueError, match="Project path must be absolute"):
            Project.from_path("relative/path/to/project")

    def test_from_path_dot_relative_raises_valueerror(self):
        """Test that dot-relative path raises ValueError."""
        with pytest.raises(ValueError, match="Project path must be absolute"):
            Project.from_path("./my/project")

    def test_from_path_parent_relative_raises_valueerror(self):
        """Test that parent-relative path raises ValueError."""
        with pytest.raises(ValueError, match="Project path must be absolute"):
            Project.from_path("../my/project")

    def test_from_path_empty_string_raises_valueerror(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Project path must be absolute"):
            Project.from_path("")


class TestFromEncodedName:
    """Tests for Project.from_encoded_name() factory method."""

    def test_from_encoded_name_basic(self, temp_claude_dir: Path):
        """Test creating Project from encoded directory name."""
        project = Project.from_encoded_name(
            "-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.path == "/Users/test/myproject"
        assert project.encoded_name == "-Users-test-myproject"
        assert project.claude_projects_dir == temp_claude_dir / "projects"

    def test_from_encoded_name_deeply_nested(self, temp_claude_dir: Path):
        """Test creating Project from deeply nested encoded name."""
        project = Project.from_encoded_name(
            "-Users-test-Documents-Projects-myapp",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.path == "/Users/test/Documents/Projects/myapp"
        assert project.encoded_name == "-Users-test-Documents-Projects-myapp"

    def test_from_encoded_name_default_claude_projects_dir(self):
        """Test creating Project with default claude_projects_dir."""
        project = Project.from_encoded_name("-Users-test-myproject")

        assert project.claude_projects_dir == Path.home() / ".claude" / "projects"


class TestProjectDirProperty:
    """Tests for Project.project_dir property."""

    def test_project_dir_basic(self, temp_claude_dir: Path):
        """Test project_dir returns correct path."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        expected = temp_claude_dir / "projects" / "-Users-test-myproject"
        assert project.project_dir == expected

    def test_project_dir_is_path(self, temp_claude_dir: Path):
        """Test that project_dir returns a Path object."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert isinstance(project.project_dir, Path)


class TestExistsProperty:
    """Tests for Project.exists property."""

    def test_exists_when_directory_exists(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test exists returns True when project directory exists."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.exists is True

    def test_exists_when_directory_missing(self, temp_claude_dir: Path):
        """Test exists returns False when project directory doesn't exist."""
        project = Project(
            path="/Users/nonexistent/project",
            encoded_name="-Users-nonexistent-project",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.exists is False


class TestClaudeBaseDirProperty:
    """Tests for Project.claude_base_dir property."""

    def test_claude_base_dir(self, temp_claude_dir: Path):
        """Test claude_base_dir returns parent of projects directory."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.claude_base_dir == temp_claude_dir

    def test_claude_base_dir_is_path(self, temp_claude_dir: Path):
        """Test that claude_base_dir returns a Path object."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert isinstance(project.claude_base_dir, Path)


class TestListSessionPaths:
    """Tests for Project.list_session_paths() method."""

    def test_list_session_paths_returns_sorted(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test that session paths are returned sorted."""
        # Create multiple session files with different UUIDs
        session1 = temp_project_dir / "aaaa-uuid.jsonl"
        session2 = temp_project_dir / "cccc-uuid.jsonl"
        session3 = temp_project_dir / "bbbb-uuid.jsonl"

        session1.write_text("{}\n")
        session2.write_text("{}\n")
        session3.write_text("{}\n")

        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_session_paths()

        assert len(paths) == 3
        assert paths[0].name == "aaaa-uuid.jsonl"
        assert paths[1].name == "bbbb-uuid.jsonl"
        assert paths[2].name == "cccc-uuid.jsonl"

    def test_list_session_paths_empty_when_no_sessions(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test empty list when no sessions exist."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_session_paths()
        assert paths == []

    def test_list_session_paths_empty_when_project_dir_missing(self, temp_claude_dir: Path):
        """Test empty list when project directory doesn't exist."""
        project = Project(
            path="/Users/nonexistent/project",
            encoded_name="-Users-nonexistent-project",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_session_paths()
        assert paths == []


class TestListSessionPathsExcludesAgents:
    """Tests for list_session_paths() excluding agent-*.jsonl files."""

    def test_excludes_agent_files(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test that agent-*.jsonl files are excluded from session listing."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_session_paths()

        # Should only include the session, not the agent
        assert len(paths) == 1
        assert paths[0].name == "test-session-uuid.jsonl"
        assert not any("agent-" in p.name for p in paths)

    def test_excludes_multiple_agent_files(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test that multiple agent files are all excluded."""
        # Create session
        session = temp_project_dir / "session-uuid.jsonl"
        session.write_text("{}\n")

        # Create multiple agents
        agent1 = temp_project_dir / "agent-abc123.jsonl"
        agent2 = temp_project_dir / "agent-def456.jsonl"
        agent3 = temp_project_dir / "agent-ghi789.jsonl"
        agent1.write_text("{}\n")
        agent2.write_text("{}\n")
        agent3.write_text("{}\n")

        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_session_paths()

        assert len(paths) == 1
        assert paths[0].name == "session-uuid.jsonl"


class TestListSessions:
    """Tests for Project.list_sessions() method."""

    def test_list_sessions_returns_session_instances(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
    ):
        """Test that list_sessions returns Session instances."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        sessions = project.list_sessions()

        assert len(sessions) == 1
        assert isinstance(sessions[0], Session)
        assert sessions[0].uuid == "test-session-uuid"

    def test_list_sessions_empty_when_no_sessions(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test empty list when no sessions exist."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        sessions = project.list_sessions()
        assert sessions == []

    def test_list_sessions_multiple(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test listing multiple sessions."""
        # Create multiple session files
        for uuid in ["session-aaa", "session-bbb", "session-ccc"]:
            session_path = temp_project_dir / f"{uuid}.jsonl"
            session_path.write_text("{}\n")

        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        sessions = project.list_sessions()

        assert len(sessions) == 3
        uuids = [s.uuid for s in sessions]
        assert "session-aaa" in uuids
        assert "session-bbb" in uuids
        assert "session-ccc" in uuids


class TestGetSession:
    """Tests for Project.get_session() method."""

    def test_get_session_existing(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
    ):
        """Test getting an existing session by UUID."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        session = project.get_session("test-session-uuid")

        assert session is not None
        assert isinstance(session, Session)
        assert session.uuid == "test-session-uuid"

    def test_get_session_nonexistent_returns_none(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test that get_session returns None for nonexistent UUID."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        session = project.get_session("nonexistent-uuid")

        assert session is None

    def test_get_session_with_project_dir_missing(self, temp_claude_dir: Path):
        """Test get_session returns None when project dir doesn't exist."""
        project = Project(
            path="/Users/nonexistent/project",
            encoded_name="-Users-nonexistent-project",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        session = project.get_session("any-uuid")

        assert session is None


class TestListAgentPathsAndListAgents:
    """Tests for list_agent_paths() and list_agents() methods."""

    def test_list_agent_paths_returns_sorted(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test that agent paths are returned sorted."""
        # Create additional agents
        agent2 = temp_project_dir / "agent-aaa111.jsonl"
        agent3 = temp_project_dir / "agent-zzz999.jsonl"
        agent2.write_text("{}\n")
        agent3.write_text("{}\n")

        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_agent_paths()

        assert len(paths) == 3
        assert paths[0].name == "agent-aaa111.jsonl"
        assert paths[1].name == "agent-b1234ef.jsonl"  # From fixture
        assert paths[2].name == "agent-zzz999.jsonl"

    def test_list_agents_returns_agent_instances(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test that list_agents returns Agent instances."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        agents = project.list_agents()

        assert len(agents) == 1
        assert isinstance(agents[0], Agent)
        assert agents[0].agent_id == "b1234ef"

    def test_list_agent_paths_empty_when_no_agents(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test empty list when no agents exist."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_agent_paths()
        assert paths == []

    def test_list_agent_paths_excludes_session_files(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test that session files are not included in agent listing."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        paths = project.list_agent_paths()

        # Should only include agent, not session
        assert len(paths) == 1
        assert "agent-" in paths[0].name
        assert not any("test-session-uuid" in p.name for p in paths)


class TestGetAgent:
    """Tests for Project.get_agent() method."""

    def test_get_agent_existing(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test getting an existing agent by ID."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        agent = project.get_agent("b1234ef")

        assert agent is not None
        assert isinstance(agent, Agent)
        assert agent.agent_id == "b1234ef"

    def test_get_agent_nonexistent_returns_none(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test that get_agent returns None for nonexistent agent."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        agent = project.get_agent("nonexistent")

        assert agent is None

    def test_get_agent_with_project_dir_missing(self, temp_claude_dir: Path):
        """Test get_agent returns None when project dir doesn't exist."""
        project = Project(
            path="/Users/nonexistent/project",
            encoded_name="-Users-nonexistent-project",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        agent = project.get_agent("any-id")

        assert agent is None


class TestSessionCountAndAgentCount:
    """Tests for session_count and agent_count properties."""

    def test_session_count(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
    ):
        """Test session_count returns correct count."""
        # Create additional sessions
        (temp_project_dir / "session-2.jsonl").write_text("{}\n")
        (temp_project_dir / "session-3.jsonl").write_text("{}\n")

        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.session_count == 3

    def test_agent_count(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test agent_count returns correct count."""
        # Create additional agents
        (temp_project_dir / "agent-abc.jsonl").write_text("{}\n")
        (temp_project_dir / "agent-def.jsonl").write_text("{}\n")

        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.agent_count == 3

    def test_counts_zero_when_empty(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test counts are zero when no sessions or agents exist."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.session_count == 0
        assert project.agent_count == 0

    def test_counts_independent(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test that session and agent counts are independent."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.session_count == 1
        assert project.agent_count == 1


class TestGetAllSubagents:
    """Tests for Project.get_all_subagents() method."""

    def test_get_all_subagents_flattens_across_sessions(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_with_subagents: Path,
    ):
        """Test that get_all_subagents flattens subagents across sessions."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        subagents = project.get_all_subagents()

        assert len(subagents) == 1
        assert isinstance(subagents[0], Agent)
        assert subagents[0].agent_id == "a5793c3"
        assert subagents[0].is_subagent is True

    def test_get_all_subagents_multiple_sessions(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_subagent_message_data,
    ):
        """Test flattening subagents from multiple sessions."""
        # Create first session with subagent
        session1_dir = temp_project_dir / "session-1"
        subagents1_dir = session1_dir / "subagents"
        subagents1_dir.mkdir(parents=True)
        (temp_project_dir / "session-1.jsonl").write_text("{}\n")
        agent1 = subagents1_dir / "agent-aaa111.jsonl"
        agent1.write_text(json.dumps(sample_subagent_message_data) + "\n")

        # Create second session with subagent
        session2_dir = temp_project_dir / "session-2"
        subagents2_dir = session2_dir / "subagents"
        subagents2_dir.mkdir(parents=True)
        (temp_project_dir / "session-2.jsonl").write_text("{}\n")
        agent2_data = sample_subagent_message_data.copy()
        agent2_data["agentId"] = "bbb222"
        agent2 = subagents2_dir / "agent-bbb222.jsonl"
        agent2.write_text(json.dumps(agent2_data) + "\n")

        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        subagents = project.get_all_subagents()

        assert len(subagents) == 2
        agent_ids = [a.agent_id for a in subagents]
        assert "aaa111" in agent_ids or "a5793c3" in agent_ids  # Depends on JSONL agentId
        assert "bbb222" in agent_ids

    def test_get_all_subagents_empty_when_no_subagents(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
    ):
        """Test empty list when sessions have no subagents."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        subagents = project.get_all_subagents()

        assert subagents == []

    def test_get_all_subagents_excludes_standalone_agents(
        self,
        temp_project_dir: Path,
        temp_claude_dir: Path,
        sample_session_jsonl: Path,
        standalone_agent_jsonl: Path,
    ):
        """Test that standalone agents are not included in subagents list."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        subagents = project.get_all_subagents()

        # Standalone agent should not appear in subagents
        assert subagents == []


class TestImmutability:
    """Tests for Project immutability (frozen=True)."""

    def test_cannot_modify_path(self, temp_claude_dir: Path):
        """Test that path attribute cannot be modified."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        with pytest.raises(ValidationError):
            project.path = "/Users/different/path"

    def test_cannot_modify_encoded_name(self, temp_claude_dir: Path):
        """Test that encoded_name attribute cannot be modified."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        with pytest.raises(ValidationError):
            project.encoded_name = "-Users-different"

    def test_cannot_modify_claude_projects_dir(self, temp_claude_dir: Path):
        """Test that claude_projects_dir attribute cannot be modified."""
        project = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        with pytest.raises(ValidationError):
            project.claude_projects_dir = Path("/different/path")

    def test_frozen_model_is_hashable(self, temp_claude_dir: Path):
        """Test that frozen Project can be used in sets/dicts."""
        project1 = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )
        project2 = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        # Should be hashable
        project_set = {project1, project2}
        # Both should be equal and collapse to one
        assert len(project_set) == 1

    def test_frozen_model_equality(self, temp_claude_dir: Path):
        """Test that identical frozen Projects are equal."""
        project1 = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )
        project2 = Project(
            path="/Users/test/myproject",
            encoded_name="-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project1 == project2


class TestIsGitRepository:
    """Tests for Project.is_git_repository property."""

    def test_git_repo_with_git_directory_returns_true(self, tmp_path: Path):
        """Test that project with .git directory returns True."""
        # Create a .git directory in the project path
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        project = Project.from_path(tmp_path)

        assert project.is_git_repository is True

    def test_non_git_project_returns_false(self, tmp_path: Path):
        """Test that project without .git returns False."""
        # No .git directory in tmp_path
        project = Project.from_path(tmp_path)

        assert project.is_git_repository is False

    def test_nonexistent_path_returns_false(self):
        """Test that project with nonexistent path returns False."""
        project = Project(
            path="/nonexistent/path/to/project",
            encoded_name="-nonexistent-path-to-project",
        )

        assert project.is_git_repository is False

    def test_git_worktree_with_git_file_returns_true(self, tmp_path: Path):
        """Test that project with .git file (worktree) returns True."""
        # Git worktrees have a .git file instead of directory
        git_file = tmp_path / ".git"
        git_file.write_text("gitdir: /path/to/main/.git/worktrees/foo\n")

        project = Project.from_path(tmp_path)

        assert project.is_git_repository is True

    def test_empty_project_directory_returns_false(self, tmp_path: Path):
        """Test that empty directory returns False."""
        project = Project.from_path(tmp_path)

        assert project.is_git_repository is False

    def test_project_with_other_dot_files_and_directories_returns_false(self, tmp_path: Path):
        """Test that other dot files/directories don't trigger git detection."""
        # Create other dot directories and files but not .git
        (tmp_path / ".vscode").mkdir()
        (tmp_path / ".idea").mkdir()
        (tmp_path / ".env").write_text("SECRET=123")

        project = Project.from_path(tmp_path)

        assert project.is_git_repository is False

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires elevated privileges on Windows",
    )
    def test_git_symlink_returns_true(self, tmp_path: Path):
        """Test that project with symlinked .git returns True."""
        real_git = tmp_path / "real_git_dir"
        real_git.mkdir()
        git_symlink = tmp_path / ".git"
        git_symlink.symlink_to(real_git)

        project = Project.from_path(tmp_path)

        assert project.is_git_repository is True

    def test_permission_error_returns_false(self, tmp_path: Path):
        """Test that PermissionError is handled gracefully."""
        from unittest.mock import patch

        project = Project.from_path(tmp_path)

        with patch.object(Path, "exists", side_effect=PermissionError("Access denied")):
            assert project.is_git_repository is False


class TestExtractRealPathFromSessions:
    """Tests for Project._extract_real_path_from_sessions() static method."""

    def test_extracts_cwd_from_session_file(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test successful path extraction from session with cwd field."""
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "/Users/test/myproject", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "/Users/test/myproject"

    def test_returns_none_for_empty_directory(self, temp_project_dir: Path):
        """Test that empty project directory returns None."""
        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result is None

    def test_returns_none_for_nonexistent_directory(self, tmp_path: Path):
        """Test that non-existent directory returns None."""
        nonexistent = tmp_path / "does_not_exist"

        result = Project._extract_real_path_from_sessions(nonexistent)

        assert result is None

    def test_tries_multiple_session_files(self, temp_project_dir: Path):
        """Test that extraction tries multiple session files when first lacks cwd."""
        # First session file has no cwd
        session1 = temp_project_dir / "aaa-uuid.jsonl"
        session1.write_text('{"type": "user", "message": "hello"}\n')

        # Second session file has cwd
        session2 = temp_project_dir / "bbb-uuid.jsonl"
        session2.write_text('{"cwd": "/Users/test/myproject", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "/Users/test/myproject"

    def test_handles_malformed_json_lines(self, temp_project_dir: Path):
        """Test that malformed JSON lines are skipped."""
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text(
            'not valid json\n{"partial": true\n{"cwd": "/Users/test/myproject", "type": "user"}\n'
        )

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "/Users/test/myproject"

    def test_skips_agent_files(self, temp_project_dir: Path):
        """Test that agent-*.jsonl files are not read for path extraction."""
        # Agent file has cwd but should be skipped
        agent_file = temp_project_dir / "agent-abc123.jsonl"
        agent_file.write_text('{"cwd": "/wrong/path", "type": "user"}\n')

        # Session file has the correct cwd
        session_file = temp_project_dir / "session-uuid.jsonl"
        session_file.write_text('{"cwd": "/Users/test/myproject", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "/Users/test/myproject"

    def test_only_agent_files_returns_none(self, temp_project_dir: Path):
        """Test that having only agent files returns None."""
        agent_file = temp_project_dir / "agent-abc123.jsonl"
        agent_file.write_text('{"cwd": "/some/path", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result is None

    def test_ignores_relative_cwd_paths(self, temp_project_dir: Path):
        """Test that relative cwd paths are ignored (only absolute paths accepted)."""
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text(
            '{"cwd": "relative/path", "type": "user"}\n'
            '{"cwd": "/Users/test/myproject", "type": "user"}\n'
        )

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "/Users/test/myproject"

    def test_stops_at_first_valid_cwd(self, temp_project_dir: Path):
        """Test that extraction stops at first valid cwd found."""
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text(
            '{"cwd": "/first/valid/path", "type": "user"}\n'
            '{"cwd": "/second/valid/path", "type": "user"}\n'
        )

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "/first/valid/path"

    def test_recognizes_windows_cwd_as_absolute(self, temp_project_dir: Path):
        """Test that Windows absolute paths (C:\\...) are recognized on any OS."""
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "C:\\\\Users\\\\test\\\\myproject", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        # Should be recognized as absolute AND normalized to forward slashes
        assert result is not None
        assert result == "C:/Users/test/myproject"

    def test_normalizes_windows_backslashes_to_forward(self, temp_project_dir: Path):
        """Test that backslashes in Windows cwd are normalized to forward slashes."""
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "D:\\\\Projects\\\\my-app", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "D:/Projects/my-app"

    def test_windows_forward_slash_cwd_unchanged(self, temp_project_dir: Path):
        """Test that Windows cwd with forward slashes is returned as-is."""
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "C:/Users/test/myproject", "type": "user"}\n')

        result = Project._extract_real_path_from_sessions(temp_project_dir)

        assert result == "C:/Users/test/myproject"


class TestFromEncodedNameSkipPathRecovery:
    """Tests for Project.from_encoded_name() with skip_path_recovery parameter."""

    def test_skip_path_recovery_uses_lossy_decode(self, temp_claude_dir: Path):
        """Test that skip_path_recovery=True uses lossy decode without reading files."""
        project = Project.from_encoded_name(
            "-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
            skip_path_recovery=True,
        )

        # Should use lossy decode result
        assert project.path == "/Users/test/myproject"
        assert project.encoded_name == "-Users-test-myproject"

    def test_skip_path_recovery_does_not_read_sessions(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test that skip_path_recovery=True does not read session files."""
        # Create session with different cwd
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "/actual/project/path", "type": "user"}\n')

        project = Project.from_encoded_name(
            "-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
            skip_path_recovery=True,
        )

        # Should use lossy decode, NOT the session cwd
        assert project.path == "/Users/test/myproject"

    def test_without_skip_reads_session_cwd(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test that default behavior reads session files for path recovery."""
        # Create session with actual cwd
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "/Users/test/myproject", "type": "user"}\n')

        project = Project.from_encoded_name(
            "-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
            skip_path_recovery=False,
        )

        # Should use session cwd
        assert project.path == "/Users/test/myproject"


class TestEncodedNameValidation:
    """Tests for encoded name validation in from_encoded_name()."""

    def test_mismatched_cwd_falls_back_to_decode(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test that mismatched cwd/encoded_name falls back to lossy decode."""
        # Session has cwd that doesn't match the encoded name
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "/completely/different/path", "type": "user"}\n')

        project = Project.from_encoded_name(
            "-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        # Should fall back to lossy decode since cwd doesn't match encoded name
        assert project.path == "/Users/test/myproject"

    def test_matching_cwd_is_used(self, temp_project_dir: Path, temp_claude_dir: Path):
        """Test that matching cwd is used when it encodes to the same name."""
        # Session has cwd that matches the encoded name
        session_file = temp_project_dir / "test-uuid.jsonl"
        session_file.write_text('{"cwd": "/Users/test/myproject", "type": "user"}\n')

        project = Project.from_encoded_name(
            "-Users-test-myproject",
            claude_projects_dir=temp_claude_dir / "projects",
        )

        assert project.path == "/Users/test/myproject"


# =============================================================================
# git_root_path property tests
# =============================================================================


class TestGitRootPath:
    """Tests for the git_root_path property."""

    def test_git_root_path_at_root(self, temp_claude_dir: Path, temp_git_repo: Path):
        """Project at git root returns its own path."""
        # Create a project at the git repo root
        project = Project.from_path(temp_git_repo, claude_projects_dir=temp_claude_dir / "projects")
        # Compare as Path objects: git outputs forward slashes on Windows,
        # str(Path) gives backslashes — Path normalises both.
        assert Path(project.git_root_path) == temp_git_repo

    def test_git_root_path_nested(self, temp_claude_dir: Path, temp_git_repo: Path):
        """Nested project returns parent git root."""
        # Create a subdirectory in the git repo
        nested_dir = temp_git_repo / "packages" / "api"
        nested_dir.mkdir(parents=True)

        project = Project.from_path(nested_dir, claude_projects_dir=temp_claude_dir / "projects")
        assert Path(project.git_root_path) == temp_git_repo

    def test_git_root_path_non_git(self, temp_claude_dir: Path, tmp_path: Path):
        """Non-git project returns None."""
        non_git_dir = tmp_path / "not-a-repo"
        non_git_dir.mkdir()

        project = Project.from_path(non_git_dir, claude_projects_dir=temp_claude_dir / "projects")
        assert project.git_root_path is None

    def test_git_root_path_nonexistent_path(self, temp_claude_dir: Path, tmp_path: Path):
        """Nonexistent path returns None gracefully."""
        nonexistent = tmp_path / "does-not-exist"
        # Note: do NOT call mkdir — the path must not exist
        project = Project.from_path(
            nonexistent,
            claude_projects_dir=temp_claude_dir / "projects",
        )
        assert project.git_root_path is None


# =============================================================================
# is_nested_project property tests
# =============================================================================


class TestIsNestedProject:
    """Tests for the is_nested_project property."""

    def test_is_nested_project_at_root(self, temp_claude_dir: Path, temp_git_repo: Path):
        """Project at git root is not nested."""
        project = Project.from_path(temp_git_repo, claude_projects_dir=temp_claude_dir / "projects")
        assert project.is_nested_project is False

    def test_is_nested_project_nested(self, temp_claude_dir: Path, temp_git_repo: Path):
        """Project in subdirectory of git repo is nested."""
        nested_dir = temp_git_repo / "apps" / "web"
        nested_dir.mkdir(parents=True)

        project = Project.from_path(nested_dir, claude_projects_dir=temp_claude_dir / "projects")
        assert project.is_nested_project is True

    def test_is_nested_project_non_git(self, temp_claude_dir: Path, tmp_path: Path):
        """Non-git project is not nested."""
        non_git_dir = tmp_path / "standalone"
        non_git_dir.mkdir()

        project = Project.from_path(non_git_dir, claude_projects_dir=temp_claude_dir / "projects")
        assert project.is_nested_project is False
