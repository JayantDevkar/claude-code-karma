"""Tests for plan discovery, packaging, and plans-index.json generation."""

import json
from pathlib import Path

import pytest

from karma.packager import _discover_plan_references


class TestDiscoverPlanReferences:
    """Test the JSONL-based plan slug discovery."""

    def _write_jsonl(self, path: Path, lines: list[str]) -> None:
        path.write_text("\n".join(lines) + "\n")

    def test_finds_plan_slug_in_jsonl(self, tmp_path):
        """A JSONL mentioning plans/my-plan.md should be discovered."""
        jsonl = tmp_path / "session-001.jsonl"
        self._write_jsonl(jsonl, [
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/home/user/.claude/plans/cool-plan.md"}}]}}',
        ])

        refs = _discover_plan_references([("session-001", jsonl)])
        assert "cool-plan" in refs
        assert refs["cool-plan"]["session-001"] == "read"

    def test_detects_write_operation(self, tmp_path):
        """Write tool should map to 'created' operation."""
        jsonl = tmp_path / "session-001.jsonl"
        self._write_jsonl(jsonl, [
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/home/user/.claude/plans/new-plan.md"}}]}}',
        ])

        refs = _discover_plan_references([("session-001", jsonl)])
        assert refs["new-plan"]["session-001"] == "created"

    def test_detects_edit_operation(self, tmp_path):
        """Edit/StrReplace tool should map to 'edited' operation."""
        jsonl = tmp_path / "session-001.jsonl"
        self._write_jsonl(jsonl, [
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Edit","input":{"file_path":"/home/user/.claude/plans/my-plan.md"}}]}}',
        ])

        refs = _discover_plan_references([("session-001", jsonl)])
        assert refs["my-plan"]["session-001"] == "edited"

    def test_write_takes_priority_over_read(self, tmp_path):
        """If a session both reads and writes a plan, 'created' wins."""
        jsonl = tmp_path / "session-001.jsonl"
        self._write_jsonl(jsonl, [
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/home/user/.claude/plans/mixed-plan.md"}}]}}',
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/home/user/.claude/plans/mixed-plan.md"}}]}}',
        ])

        refs = _discover_plan_references([("session-001", jsonl)])
        assert refs["mixed-plan"]["session-001"] == "created"

    def test_no_plans_returns_empty(self, tmp_path):
        """JSONL without plan references should return empty dict."""
        jsonl = tmp_path / "session-001.jsonl"
        self._write_jsonl(jsonl, [
            '{"type":"user","message":{"role":"user","content":"hello world"}}',
        ])

        refs = _discover_plan_references([("session-001", jsonl)])
        assert refs == {}

    def test_multiple_sessions_multiple_plans(self, tmp_path):
        """Multiple sessions referencing different plans."""
        j1 = tmp_path / "s1.jsonl"
        j2 = tmp_path / "s2.jsonl"
        self._write_jsonl(j1, [
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/home/.claude/plans/plan-a.md"}}]}}',
        ])
        self._write_jsonl(j2, [
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/home/.claude/plans/plan-a.md"}}]}}',
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/home/.claude/plans/plan-b.md"}}]}}',
        ])

        refs = _discover_plan_references([("s1", j1), ("s2", j2)])
        assert refs["plan-a"]["s1"] == "created"
        assert refs["plan-a"]["s2"] == "read"
        assert refs["plan-b"]["s2"] == "created"

    def test_skips_missing_files(self, tmp_path):
        """Non-existent JSONL paths should be skipped without error."""
        missing = tmp_path / "missing.jsonl"
        refs = _discover_plan_references([("s1", missing)])
        assert refs == {}

    def test_ignores_non_plan_md_files(self, tmp_path):
        """References to non-plan .md files should be ignored."""
        jsonl = tmp_path / "session-001.jsonl"
        self._write_jsonl(jsonl, [
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/home/user/docs/README.md"}}]}}',
        ])

        refs = _discover_plan_references([("session-001", jsonl)])
        assert refs == {}


class TestPackagerPlanCopying:
    """Integration test: packager copies plan files and writes plans-index.json."""

    @pytest.fixture
    def project_with_plans(self, tmp_path):
        """Create a project with sessions that reference plans."""
        project_dir = tmp_path / ".claude" / "projects" / "-My-project"
        project_dir.mkdir(parents=True)

        # Create a session that references a plan
        s1 = project_dir / "session-001.jsonl"
        s1.write_text(
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"'
            + str(tmp_path / ".claude" / "plans" / "test-plan.md")
            + '"}}]}}\n'
        )

        # Create the plan file
        plans_dir = tmp_path / ".claude" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "test-plan.md").write_text("# Test Plan\n\nThis is a test plan.\n")

        return project_dir

    def test_plans_copied_to_staging(self, project_with_plans, tmp_path):
        """Plans referenced by sessions should be copied to staging."""
        from karma.packager import SessionPackager

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_with_plans,
            user_id="alice",
            machine_id="test-mac",
        )
        packager.package(staging_dir=staging)

        plans_dir = staging / "plans"
        assert plans_dir.is_dir()
        assert (plans_dir / "test-plan.md").is_file()
        assert "Test Plan" in (plans_dir / "test-plan.md").read_text()

    def test_plans_index_json_created(self, project_with_plans, tmp_path):
        """plans-index.json should map plan slugs to session UUIDs."""
        from karma.packager import SessionPackager

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_with_plans,
            user_id="alice",
            machine_id="test-mac",
        )
        packager.package(staging_dir=staging)

        index_path = staging / "plans-index.json"
        assert index_path.is_file()

        data = json.loads(index_path.read_text())
        assert data["version"] == 1
        assert "test-plan" in data["plans"]
        assert "session-001" in data["plans"]["test-plan"]["sessions"]

    def test_unreferenced_plans_not_copied(self, project_with_plans, tmp_path):
        """Plans not referenced by any session should NOT be copied."""
        # Add an unreferenced plan
        plans_dir = tmp_path / ".claude" / "plans"
        (plans_dir / "other-plan.md").write_text("# Other\n")

        from karma.packager import SessionPackager

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_with_plans,
            user_id="alice",
            machine_id="test-mac",
        )
        packager.package(staging_dir=staging)

        assert not (staging / "plans" / "other-plan.md").exists()
