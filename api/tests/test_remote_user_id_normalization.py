import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team
from domain.member import Member, MemberStatus
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def seeded_conn(conn):
    TeamRepository().save(conn, Team(name="t1", leader_device_id="D1", leader_member_tag="jay.mac"))
    MemberRepository().save(conn, Member(
        team_name="t1", member_tag="jay.mac", device_id="D1",
        user_id="jay", machine_tag="mac", status=MemberStatus.ACTIVE,
    ))
    return conn


class TestResolveUserIdNormalization:
    def test_priority2_resolves_to_member_tag(self, seeded_conn, tmp_path):
        """When manifest has user_id but no device_id match, resolve to member_tag via DB."""
        from services.remote_sessions import _resolve_user_id, _resolved_user_cache
        _resolved_user_cache.clear()

        user_dir = tmp_path / "jay"
        user_dir.mkdir()
        proj_dir = user_dir / "project1"
        proj_dir.mkdir()
        manifest = {"user_id": "jay"}
        (proj_dir / "manifest.json").write_text(json.dumps(manifest))

        result = _resolve_user_id(user_dir, conn=seeded_conn)
        assert result == "jay.mac"

    def test_priority3_resolves_dir_name_to_member_tag(self, seeded_conn, tmp_path):
        """When no manifest exists and dir_name is a bare user_id, resolve via DB."""
        from services.remote_sessions import _resolve_user_id, _resolved_user_cache
        _resolved_user_cache.clear()

        user_dir = tmp_path / "jay"
        user_dir.mkdir()

        result = _resolve_user_id(user_dir, conn=seeded_conn)
        assert result == "jay.mac"

    def test_unknown_user_id_stays_as_is(self, seeded_conn, tmp_path):
        """When user_id has no DB match, keep as-is."""
        from services.remote_sessions import _resolve_user_id, _resolved_user_cache
        _resolved_user_cache.clear()

        user_dir = tmp_path / "unknown"
        user_dir.mkdir()
        proj_dir = user_dir / "project1"
        proj_dir.mkdir()
        manifest = {"user_id": "unknown"}
        (proj_dir / "manifest.json").write_text(json.dumps(manifest))

        result = _resolve_user_id(user_dir, conn=seeded_conn)
        assert result == "unknown"

    def test_already_member_tag_not_changed(self, seeded_conn, tmp_path):
        """If resolved is already a member_tag (has dot), don't double-resolve."""
        from services.remote_sessions import _resolve_user_id, _resolved_user_cache
        _resolved_user_cache.clear()

        user_dir = tmp_path / "jay.mac"
        user_dir.mkdir()

        result = _resolve_user_id(user_dir, conn=seeded_conn)
        # Should stay as-is or resolve to jay (existing Priority 3 logic)
        # The final normalization block should NOT try to look up "jay.mac"
        # as a user_id since it already contains a dot.
        assert "." in result  # Has dot — either jay.mac or resolved member_tag


class TestV20Migration:
    def test_stale_remote_user_id_fixed(self, seeded_conn):
        """v20 migration SQL normalizes bare user_id to member_tag."""
        seeded_conn.execute(
            "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, source, remote_user_id) "
            "VALUES ('s1', '-Users-me-repo', 1.0, 'remote', 'jay')"
        )
        seeded_conn.commit()

        # Run the migration SQL directly
        seeded_conn.execute("""
            UPDATE sessions SET remote_user_id = (
                SELECT m.member_tag FROM sync_members m
                WHERE m.user_id = sessions.remote_user_id
                LIMIT 1
            ) WHERE source = 'remote'
              AND remote_user_id IS NOT NULL
              AND remote_user_id NOT LIKE '%.%'
              AND EXISTS (
                  SELECT 1 FROM sync_members m
                  WHERE m.user_id = sessions.remote_user_id
              )
        """)
        seeded_conn.commit()

        row = seeded_conn.execute("SELECT remote_user_id FROM sessions WHERE uuid = 's1'").fetchone()
        assert row[0] == "jay.mac"

    def test_already_normalized_not_touched(self, seeded_conn):
        """Sessions with member_tag format are left unchanged."""
        seeded_conn.execute(
            "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, source, remote_user_id) "
            "VALUES ('s2', '-Users-me-repo', 1.0, 'remote', 'jay.mac')"
        )
        seeded_conn.commit()

        seeded_conn.execute("""
            UPDATE sessions SET remote_user_id = (
                SELECT m.member_tag FROM sync_members m
                WHERE m.user_id = sessions.remote_user_id
                LIMIT 1
            ) WHERE source = 'remote'
              AND remote_user_id IS NOT NULL
              AND remote_user_id NOT LIKE '%.%'
              AND EXISTS (
                  SELECT 1 FROM sync_members m
                  WHERE m.user_id = sessions.remote_user_id
              )
        """)

        row = seeded_conn.execute("SELECT remote_user_id FROM sessions WHERE uuid = 's2'").fetchone()
        assert row[0] == "jay.mac"
