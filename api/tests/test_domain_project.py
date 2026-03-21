"""Tests for the SharedProject domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
from domain.project import SharedProject, SharedProjectStatus, derive_folder_suffix


def make_project(**kwargs):
    defaults = dict(
        team_name="team-abc",
        git_identity="https://github.com/user/repo.git",
        folder_suffix=derive_folder_suffix("https://github.com/user/repo.git"),
    )
    defaults.update(kwargs)
    return SharedProject(**defaults)


class TestDeriveFolderSuffix:
    def test_simple_path(self):
        assert derive_folder_suffix("my-repo") == "my-repo"

    def test_strips_dot_git(self):
        assert derive_folder_suffix("my-repo.git") == "my-repo"

    def test_replaces_slashes_with_dashes(self):
        assert derive_folder_suffix("user/repo") == "user-repo"

    def test_replaces_slashes_and_strips_git(self):
        assert derive_folder_suffix("user/repo.git") == "user-repo"

    def test_full_https_url(self):
        result = derive_folder_suffix("https://github.com/user/repo.git")
        assert "/" not in result
        assert "repo" in result

    def test_multiple_path_segments(self):
        result = derive_folder_suffix("org/team/repo")
        assert result == "org-team-repo"


class TestSharedProjectModel:
    def test_create_project_defaults(self):
        p = make_project()
        assert p.team_name == "team-abc"
        assert p.git_identity == "https://github.com/user/repo.git"
        assert p.status == SharedProjectStatus.SHARED
        assert p.encoded_name is None
        assert isinstance(p.shared_at, datetime)
        assert p.shared_at.tzinfo is not None

    def test_project_is_frozen(self):
        p = make_project()
        with pytest.raises(Exception):
            p.git_identity = "changed"

    def test_encoded_name_optional(self):
        p = make_project(encoded_name="-Users-alice-repo")
        assert p.encoded_name == "-Users-alice-repo"

    def test_encoded_name_none_by_default(self):
        p = make_project()
        assert p.encoded_name is None

    def test_folder_suffix_field(self):
        p = make_project(git_identity="user/myrepo.git", folder_suffix="user-myrepo")
        assert p.folder_suffix == "user-myrepo"
        assert "/" not in p.folder_suffix

    def test_folder_suffix_derived_helper(self):
        p = make_project(
            git_identity="https://github.com/user/myrepo.git",
            folder_suffix=derive_folder_suffix("https://github.com/user/myrepo.git"),
        )
        assert p.folder_suffix is not None
        assert "myrepo" in p.folder_suffix
        assert "/" not in p.folder_suffix

    def test_remove_project(self):
        p = make_project()
        removed = p.remove()
        assert removed.status == SharedProjectStatus.REMOVED

    def test_remove_already_removed_raises(self):
        p = make_project()
        removed = p.remove()
        with pytest.raises(Exception):
            removed.remove()

    def test_shared_project_status_enum_values(self):
        assert SharedProjectStatus.SHARED.value == "shared"
        assert SharedProjectStatus.REMOVED.value == "removed"
