"""Tests for non-git project handling (GAP-1 through GAP-7 fixes)."""

import json
import sqlite3

import pytest
from click.testing import CliRunner

from karma.main import cli


@pytest.fixture
def setup(tmp_path, monkeypatch, mock_db):
    """Set up test environment with init + team."""
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)
    monkeypatch.setattr("karma.main.KARMA_BASE", tmp_path)

    runner = CliRunner()
    runner.invoke(cli, ["init", "--user-id", "alice"])
    runner.invoke(cli, ["team", "create", "beta"])

    return {"tmp": tmp_path, "db": mock_db, "runner": runner}


class TestSuffixStoredAtShareTime:
    """Fix A: folder_suffix is stored immediately when project is added."""

    def test_nongit_project_stores_cli_name_as_suffix(self, setup):
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        project_path = tmp / "my-notes"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "my-notes",
            "--path", str(project_path),
            "--team", "beta",
        ])
        assert result.exit_code == 0

        row = db.execute(
            "SELECT folder_suffix FROM sync_team_projects WHERE team_name = 'beta'"
        ).fetchone()
        assert row is not None
        assert row["folder_suffix"] == "my-notes"

    def test_git_project_stores_git_identity_as_suffix(self, setup, monkeypatch):
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        project_path = tmp / "repo"
        project_path.mkdir()

        # Mock git identity detection
        monkeypatch.setattr(
            "karma.main.detect_git_identity",
            lambda p: "acme/my-repo",
        )

        result = runner.invoke(cli, [
            "project", "add", "repo",
            "--path", str(project_path),
            "--team", "beta",
        ])
        assert result.exit_code == 0

        row = db.execute(
            "SELECT folder_suffix FROM sync_team_projects WHERE team_name = 'beta'"
        ).fetchone()
        assert row["folder_suffix"] == "acme-my-repo"

    def test_custom_suffix_override(self, setup):
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        project_path = tmp / "design-docs"
        project_path.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "design-docs",
            "--path", str(project_path),
            "--team", "beta",
            "--suffix", "jay-design-docs",
        ])
        assert result.exit_code == 0

        row = db.execute(
            "SELECT folder_suffix FROM sync_team_projects WHERE team_name = 'beta'"
        ).fetchone()
        assert row["folder_suffix"] == "jay-design-docs"


class TestSuffixCollisionDetection:
    """Fix B: suffix uniqueness check prevents non-git collision (GAP-1)."""

    def test_same_suffix_different_project_rejected(self, setup):
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        # Add first project
        p1 = tmp / "notes-v1"
        p1.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "my-notes",
            "--path", str(p1),
            "--team", "beta",
        ])
        assert result.exit_code == 0

        # Add second project with DIFFERENT path but SAME name -> same suffix
        p2 = tmp / "notes-v2"
        p2.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "my-notes",
            "--path", str(p2),
            "--team", "beta",
        ])
        assert result.exit_code != 0
        assert "suffix" in result.output.lower() or "already" in result.output.lower()

    def test_collision_resolved_with_custom_suffix(self, setup):
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        # Add first project
        p1 = tmp / "notes-v1"
        p1.mkdir()
        runner.invoke(cli, [
            "project", "add", "my-notes",
            "--path", str(p1),
            "--team", "beta",
        ])

        # Add second project with custom suffix to avoid collision
        p2 = tmp / "notes-v2"
        p2.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "my-notes-v2",
            "--path", str(p2),
            "--team", "beta",
            "--suffix", "my-notes-v2",
        ])
        assert result.exit_code == 0

        rows = db.execute(
            "SELECT folder_suffix FROM sync_team_projects WHERE team_name = 'beta' ORDER BY folder_suffix"
        ).fetchall()
        suffixes = [r["folder_suffix"] for r in rows]
        assert "my-notes" in suffixes
        assert "my-notes-v2" in suffixes

    def test_same_project_readd_allowed(self, setup):
        """Re-adding the same project (same encoded name) should not trigger collision."""
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        p1 = tmp / "my-app"
        p1.mkdir()
        result = runner.invoke(cli, [
            "project", "add", "my-app",
            "--path", str(p1),
            "--team", "beta",
        ])
        assert result.exit_code == 0

        # Re-add same project (same path -> same encoded) — should hit UNIQUE constraint
        # on (team_name, project_encoded_name), not suffix collision
        result = runner.invoke(cli, [
            "project", "add", "my-app",
            "--path", str(p1),
            "--team", "beta",
        ])
        assert result.exit_code != 0
        assert "already exists" in result.output.lower()


class TestProjectMap:
    """Fix D: manual project mapping CLI for non-git cross-machine resolution."""

    def test_map_updates_project_path(self, setup):
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        # Add a project (simulating what a receiver would have after accepting folders)
        p1 = tmp / "remote-proj"
        p1.mkdir()
        runner.invoke(cli, [
            "project", "add", "design-docs",
            "--path", str(p1),
            "--team", "beta",
        ])

        # Create local directory to map to
        local = tmp / "my-local-design"
        local.mkdir()

        result = runner.invoke(cli, [
            "project", "map", "design-docs",
            "--team", "beta",
            "--path", str(local),
        ])
        assert result.exit_code == 0
        assert "Mapped" in result.output

        # Verify the team project now points to local path
        row = db.execute(
            "SELECT path FROM sync_team_projects WHERE team_name = 'beta' AND folder_suffix = 'design-docs'"
        ).fetchone()
        assert row is not None
        assert row["path"] == str(local)

    def test_map_nonexistent_suffix_fails(self, setup):
        tmp, runner = setup["tmp"], setup["runner"]

        local = tmp / "something"
        local.mkdir()
        result = runner.invoke(cli, [
            "project", "map", "nonexistent-suffix",
            "--team", "beta",
            "--path", str(local),
        ])
        assert result.exit_code != 0
        assert "No project with suffix" in result.output

    def test_map_nonexistent_team_fails(self, setup):
        tmp, runner = setup["tmp"], setup["runner"]

        local = tmp / "something"
        local.mkdir()
        result = runner.invoke(cli, [
            "project", "map", "some-suffix",
            "--team", "no-such-team",
            "--path", str(local),
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_map_nonexistent_path_fails(self, setup):
        tmp, runner = setup["tmp"], setup["runner"]

        # Add a project first
        p1 = tmp / "remote-proj"
        p1.mkdir()
        runner.invoke(cli, [
            "project", "add", "design-docs",
            "--path", str(p1),
            "--team", "beta",
        ])

        result = runner.invoke(cli, [
            "project", "map", "design-docs",
            "--team", "beta",
            "--path", "/nonexistent/path/foo",
        ])
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower()

    def test_map_registers_in_projects_table(self, setup):
        tmp, db, runner = setup["tmp"], setup["db"], setup["runner"]

        p1 = tmp / "remote-proj"
        p1.mkdir()
        runner.invoke(cli, [
            "project", "add", "my-proj",
            "--path", str(p1),
            "--team", "beta",
        ])

        local = tmp / "local-proj"
        local.mkdir()
        runner.invoke(cli, [
            "project", "map", "my-proj",
            "--team", "beta",
            "--path", str(local),
        ])

        # Check projects table has the local path
        row = db.execute(
            "SELECT project_path FROM projects WHERE project_path = ?",
            (str(local),),
        ).fetchone()
        assert row is not None


class TestManifestProjectName:
    """Fix C: SyncManifest includes project_name field."""

    def test_manifest_has_project_name_field(self):
        from karma.manifest import SyncManifest

        m = SyncManifest(
            user_id="alice",
            machine_id="macbook",
            project_path="/Users/alice/notes",
            project_encoded="-Users-alice-notes",
            session_count=0,
            sessions=[],
            project_name="notes",
        )
        data = m.model_dump()
        assert data["project_name"] == "notes"

    def test_manifest_project_name_optional(self):
        from karma.manifest import SyncManifest

        m = SyncManifest(
            user_id="alice",
            machine_id="macbook",
            project_path="/Users/alice/notes",
            project_encoded="-Users-alice-notes",
            session_count=0,
            sessions=[],
        )
        data = m.model_dump()
        assert data["project_name"] is None

    def test_manifest_roundtrip_with_project_name(self):
        from karma.manifest import SyncManifest

        m = SyncManifest(
            user_id="alice",
            machine_id="macbook",
            project_path="/Users/alice/notes",
            project_encoded="-Users-alice-notes",
            session_count=0,
            sessions=[],
            project_name="my-design-notes",
            git_identity=None,
        )
        json_str = json.dumps(m.model_dump())
        data = json.loads(json_str)
        m2 = SyncManifest(**data)
        assert m2.project_name == "my-design-notes"
        assert m2.git_identity is None
