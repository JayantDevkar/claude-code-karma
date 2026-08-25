"""
Unit tests for the settings router's write-safety hardening.

Covers:
- Atomic write (no leftover .tmp, no partial writes)
- Rolling backup (.karma-bak) before each write
- File permission preservation
- Deep merge of partial nested payloads (no clobbering sibling keys)
- null-deletes-key semantics, including nested keys
- Unknown keys preserved verbatim (schema/pydantic don't know about them)
- Corrupt on-disk JSON is reported, never silently overwritten
- Schema validation rejects a wrong-typed value for a real settings.json key
  that our Pydantic model doesn't itself model (extra="allow" passthrough)
"""

import asyncio
import json
import os
import stat
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent.parent
_root_dir = _api_dir.parent

if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from routers import settings as settings_router  # noqa: E402


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(settings_router.router, prefix="/settings")
    test_app.add_exception_handler(RecursionError, settings_router.handle_recursion_error)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def settings_path(mock_claude_base):
    return mock_claude_base / "settings.json"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class TestAtomicWrite:
    def test_write_leaves_no_tmp_file(self, client, settings_path):
        resp = client.put("/settings/", json={"verbose": True})
        assert resp.status_code == 200
        assert settings_path.exists()
        # Temp files are per-call-unique (settings.json.<random>.tmp), not a
        # fixed name -- glob for the pattern rather than one literal name.
        assert list(settings_path.parent.glob("settings.json.*.tmp")) == []

    def test_write_preserves_file_permissions(self, client, settings_path):
        _write_json(settings_path, {"verbose": False})
        os.chmod(settings_path, 0o600)

        resp = client.put("/settings/", json={"verbose": True})
        assert resp.status_code == 200

        mode = stat.S_IMODE(os.stat(settings_path).st_mode)
        assert mode == 0o600


class TestSymlinkedSettingsFile:
    def test_write_through_symlink_preserves_the_symlink(self, client, settings_path, tmp_path):
        # Regression test: os.replace() on a symlink path swaps the symlink
        # itself out for a plain file. A user who syncs settings.json into a
        # dotfiles repo via a symlink would silently lose that setup on the
        # very first save from karma.
        real_target = tmp_path / "dotfiles-settings.json"
        _write_json(real_target, {"verbose": False, "model": "sonnet"})
        settings_path.symlink_to(real_target)

        resp = client.put("/settings/", json={"verbose": True})
        assert resp.status_code == 200

        assert settings_path.is_symlink()
        assert settings_path.resolve() == real_target.resolve()

        on_disk = json.loads(real_target.read_text())
        assert on_disk == {"verbose": True, "model": "sonnet"}

        # Backup and temp files live alongside the real target, not a
        # same-named file dropped next to the symlink.
        assert (tmp_path / "dotfiles-settings.json.karma-bak").exists()
        assert list(tmp_path.glob("dotfiles-settings.json.*.tmp")) == []


class TestRollingBackup:
    def test_backup_created_with_prior_content(self, client, settings_path):
        _write_json(settings_path, {"verbose": False, "model": "sonnet"})

        resp = client.put("/settings/", json={"verbose": True})
        assert resp.status_code == 200

        backup_path = settings_path.with_name("settings.json.karma-bak")
        assert backup_path.exists()
        backup_data = json.loads(backup_path.read_text())
        assert backup_data == {"verbose": False, "model": "sonnet"}

    def test_backup_is_single_rolling_not_timestamped(self, client, settings_path):
        _write_json(settings_path, {"verbose": False})
        client.put("/settings/", json={"verbose": True})
        client.put("/settings/", json={"verbose": False})

        backup_path = settings_path.with_name("settings.json.karma-bak")
        assert json.loads(backup_path.read_text()) == {"verbose": True}

        siblings = list(settings_path.parent.glob("settings.json.karma-bak*"))
        assert siblings == [backup_path]

    def test_no_backup_written_on_first_ever_write(self, client, settings_path):
        assert not settings_path.exists()
        resp = client.put("/settings/", json={"verbose": True})
        assert resp.status_code == 200
        assert not settings_path.with_name("settings.json.karma-bak").exists()


class TestConcurrentWrites:
    async def test_concurrent_puts_do_not_corrupt_settings_json(self, app, settings_path):
        # Regression test for a fixed-name shared temp file: before the fix,
        # concurrent writers interleaved into the same inode and produced
        # invalid JSON (or a FileNotFoundError racing os.replace()).
        _write_json(settings_path, {"verbose": False})

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
            responses = await asyncio.gather(
                *[async_client.put("/settings/", json={"model": f"sonnet-{i}"}) for i in range(20)]
            )

        assert all(r.status_code == 200 for r in responses)

        # Must still parse as valid JSON at all -- this is exactly what broke
        # before the fix.
        on_disk = json.loads(settings_path.read_text())
        assert on_disk["model"].startswith("sonnet-")

        # The write-sequence lock fully serializes requests, so a sibling key
        # untouched by any of the 20 payloads must survive every request
        # intact -- proving no request's merge was based on a stale read of
        # a concurrently-in-flight write.
        assert on_disk["verbose"] is False

        # No per-request temp file left behind by a "losing" request.
        assert list(settings_path.parent.glob("settings.json.*.tmp")) == []


class TestDeepMerge:
    def test_partial_nested_permissions_does_not_clobber_siblings(self, client, settings_path):
        _write_json(
            settings_path,
            {"permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(rm:*)"]}},
        )

        resp = client.put(
            "/settings/", json={"permissions": {"allow": ["Bash(ls:*)", "Bash(git:*)"]}}
        )
        assert resp.status_code == 200

        on_disk = json.loads(settings_path.read_text())
        assert on_disk["permissions"]["allow"] == ["Bash(ls:*)", "Bash(git:*)"]
        assert on_disk["permissions"]["deny"] == ["Bash(rm:*)"]

    def test_partial_nested_spellcheck_does_not_clobber_siblings(self, client, settings_path):
        _write_json(settings_path, {"spellcheck": {"enabled": True, "language": "en_GB"}})

        resp = client.put("/settings/", json={"spellcheck": {"enabled": False}})
        assert resp.status_code == 200

        on_disk = json.loads(settings_path.read_text())
        assert on_disk["spellcheck"] == {"enabled": False, "language": "en_GB"}


class TestNullDeletesKey:
    def test_top_level_null_deletes_key(self, client, settings_path):
        _write_json(settings_path, {"verbose": True, "model": "sonnet"})

        resp = client.put("/settings/", json={"verbose": None})
        assert resp.status_code == 200

        on_disk = json.loads(settings_path.read_text())
        assert "verbose" not in on_disk
        assert on_disk["model"] == "sonnet"

    def test_nested_null_deletes_only_that_key(self, client, settings_path):
        _write_json(settings_path, {"spellcheck": {"enabled": True, "language": "en_GB"}})

        resp = client.put("/settings/", json={"spellcheck": {"enabled": None}})
        assert resp.status_code == 200

        on_disk = json.loads(settings_path.read_text())
        assert on_disk["spellcheck"] == {"language": "en_GB"}

    def test_nested_null_on_absent_parent_writes_nothing_not_literal_null(
        self, client, settings_path
    ):
        # Regression test: when `spellcheck` was never on disk, _deep_merge
        # used to fall through to a raw assignment and write the nested null
        # verbatim (`{"spellcheck": {"enabled": null}}`) instead of treating
        # it as "nothing to delete, nothing to write".
        assert not settings_path.exists()

        resp = client.put("/settings/", json={"spellcheck": {"enabled": None}})
        assert resp.status_code == 200

        on_disk = json.loads(settings_path.read_text())
        assert "spellcheck" not in on_disk

    def test_nested_null_that_empties_parent_removes_parent_entirely(self, client, settings_path):
        # Resetting the only key left in a nested object shouldn't leave an
        # empty `{}` litter behind -- "reset deletes the key" should mean the
        # whole thing, all the way up.
        _write_json(settings_path, {"spellcheck": {"enabled": True}})

        resp = client.put("/settings/", json={"spellcheck": {"enabled": None}})
        assert resp.status_code == 200

        on_disk = json.loads(settings_path.read_text())
        assert "spellcheck" not in on_disk


class TestUnknownKeysPreserved:
    def test_unmodeled_key_survives_an_unrelated_write(self, client, settings_path):
        _write_json(
            settings_path,
            {"someFutureFeatureFlag": {"nested": "value"}, "verbose": False},
        )

        resp = client.put("/settings/", json={"verbose": True})
        assert resp.status_code == 200

        on_disk = json.loads(settings_path.read_text())
        assert on_disk["someFutureFeatureFlag"] == {"nested": "value"}
        assert on_disk["verbose"] is True


class TestCorruptFile:
    def test_get_reports_corrupt_file_without_raising(self, client, settings_path):
        settings_path.write_text("{not valid json", encoding="utf-8")

        resp = client.get("/settings/")
        assert resp.status_code == 500
        assert settings_path.read_text() == "{not valid json"

    def test_put_leaves_corrupt_file_untouched(self, client, settings_path):
        settings_path.write_text("{not valid json", encoding="utf-8")

        resp = client.put("/settings/", json={"verbose": True})
        assert resp.status_code == 500
        assert settings_path.read_text() == "{not valid json"
        assert list(settings_path.parent.glob("settings.json.*.tmp")) == []
        assert not settings_path.with_name("settings.json.karma-bak").exists()


class TestSchemaValidation:
    def test_wrong_typed_value_for_unmodeled_schema_key_is_rejected(self, client, settings_path):
        # autoCompactEnabled is a real settings.json boolean our Pydantic model
        # doesn't type explicitly (extra="allow" lets it through raw) — the
        # vendored jsonschema is the only thing that catches the bad type here.
        resp = client.put("/settings/", json={"autoCompactEnabled": "yes"})
        assert resp.status_code == 422
        assert not settings_path.exists()

    def test_valid_value_for_unmodeled_schema_key_is_accepted(self, client, settings_path):
        resp = client.put("/settings/", json={"autoCompactEnabled": True})
        assert resp.status_code == 200
        on_disk = json.loads(settings_path.read_text())
        assert on_disk["autoCompactEnabled"] is True

    def test_typo_in_nested_strict_object_is_rejected(self, client, settings_path):
        # `mathcer` (typo of `matcher`) inside a hook entry -- `hooks.*.hooks[]`'s
        # schema fragment declares additionalProperties: false several levels
        # down. Regression test: the additionalProperties filter used to be
        # applied tree-wide, so this typo -- which would make the hook
        # silently never fire, with zero feedback -- was written verbatim.
        resp = client.put(
            "/settings/",
            json={
                "hooks": {
                    "PostToolUse": [
                        {
                            "mathcer": "Edit",
                            "hooks": [{"type": "command", "command": "echo hi"}],
                        }
                    ]
                }
            },
        )
        assert resp.status_code == 422
        assert not settings_path.exists()

    def test_correctly_spelled_nested_strict_object_is_accepted(self, client, settings_path):
        payload = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [{"type": "command", "command": "echo hi"}],
                    }
                ]
            }
        }
        resp = client.put("/settings/", json=payload)
        assert resp.status_code == 200
        on_disk = json.loads(settings_path.read_text())
        assert on_disk["hooks"] == payload["hooks"]


class TestDeeplyNestedPayload:
    def test_deeply_nested_body_returns_clean_400_not_a_raw_500(self, client, settings_path):
        # A JSON body nested thousands of levels deep blows Python's
        # recursion limit while Starlette parses it, before router code (or
        # even Pydantic validation) ever runs. Regression test: this used to
        # surface as an unhandled 500. Built as a raw string, not a nested
        # Python dict/json.dumps -- constructing the payload that way would
        # hit the same recursion limit on the test's own client side.
        depth = 3000
        raw_body = ('{"a":' * depth) + "{}" + ("}" * depth)
        raw_body = '{"reallyDeepKey":' + raw_body + "}"

        resp = client.put(
            "/settings/", content=raw_body, headers={"Content-Type": "application/json"}
        )

        assert resp.status_code == 400
        assert not settings_path.exists()
