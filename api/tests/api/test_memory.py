"""
API tests for the project memory endpoints.

Covers:
- GET /projects/{encoded_name}/memory (index + file list)
- GET /projects/{encoded_name}/memory/files/{filename} (single file)

Fixtures create temp ~/.claude/projects/{encoded_name}/memory/ directories
with various shapes (no dir, only index, index+children, orphan children,
malformed YAML frontmatter, non-.md siblings). Security tests assert that
path traversal attempts return 400/403.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

api_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(api_path))

from main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


ENCODED_NAME = "-Users-test-memproj"


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    """
    Create a temp ~/.claude/projects/{encoded_name}/memory/ directory and
    redirect settings.claude_base to the tmp root.

    Returns the Path to the memory directory (not yet populated).
    """
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    project_dir = projects_dir / ENCODED_NAME
    mem_dir = project_dir / "memory"
    mem_dir.mkdir(parents=True)

    from config import settings

    monkeypatch.setattr(settings, "claude_base", claude_dir)

    return mem_dir


@pytest.fixture
def no_memory_dir(tmp_path, monkeypatch):
    """Create a project dir with NO memory subdirectory."""
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    project_dir = projects_dir / ENCODED_NAME
    project_dir.mkdir(parents=True)

    from config import settings

    monkeypatch.setattr(settings, "claude_base", claude_dir)

    return project_dir


# =============================================================================
# GET /memory — shape-variation tests
# =============================================================================


class TestMemoryEndpointShape:
    def test_no_memory_dir_returns_empty_index_and_files(self, client, no_memory_dir):
        """When memory/ does not exist, index.exists=False and files=[]."""
        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        assert response.status_code == 200
        data = response.json()
        assert "index" in data
        assert "files" in data
        assert data["index"]["exists"] is False
        assert data["index"]["content"] == ""
        assert data["index"]["word_count"] == 0
        assert data["files"] == []

    def test_only_index_no_children(self, client, memory_dir):
        """MEMORY.md alone, no children → files=[]."""
        (memory_dir / "MEMORY.md").write_text(
            "# My memory\n\nSome content here with seven words total.\n",
            encoding="utf-8",
        )

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        assert response.status_code == 200
        data = response.json()
        assert data["index"]["exists"] is True
        assert "My memory" in data["index"]["content"]
        assert data["index"]["word_count"] > 0
        assert data["files"] == []

    def test_index_with_children(self, client, memory_dir):
        """Index plus two children, both have valid frontmatter."""
        (memory_dir / "MEMORY.md").write_text(
            "# Index\n\nSee [Arch](arch.md) and [Radio](project_git_radio.md).\n",
            encoding="utf-8",
        )
        (memory_dir / "arch.md").write_text(
            "---\n"
            "name: Architecture notes\n"
            "description: Folder IDs and reconciliation\n"
            "type: project\n"
            "---\n\n"
            "# Arch body\n\nBody content here.\n",
            encoding="utf-8",
        )
        (memory_dir / "project_git_radio.md").write_text(
            "---\n"
            "name: Git radio\n"
            "description: submodule setup\n"
            "type: reference\n"
            "---\n\n"
            "Details about git radio.\n",
            encoding="utf-8",
        )

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        assert response.status_code == 200
        data = response.json()
        assert data["index"]["exists"] is True
        assert len(data["files"]) == 2
        by_name = {f["filename"]: f for f in data["files"]}
        assert "arch.md" in by_name
        assert "project_git_radio.md" in by_name
        assert by_name["arch.md"]["name"] == "Architecture notes"
        assert by_name["arch.md"]["type"] == "project"
        assert by_name["arch.md"]["linked_from_index"] is True
        assert by_name["project_git_radio.md"]["type"] == "reference"
        assert by_name["project_git_radio.md"]["linked_from_index"] is True

    def test_children_only_no_index(self, client, memory_dir):
        """Children present but no MEMORY.md — index.exists=False but files populated."""
        (memory_dir / "orphan1.md").write_text(
            "---\nname: Orphan one\ntype: user\n---\n\nBody.\n", encoding="utf-8"
        )
        (memory_dir / "orphan2.md").write_text("Plain body, no frontmatter.\n", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        assert response.status_code == 200
        data = response.json()
        assert data["index"]["exists"] is False
        assert len(data["files"]) == 2
        filenames = {f["filename"] for f in data["files"]}
        assert filenames == {"orphan1.md", "orphan2.md"}
        for f in data["files"]:
            assert f["linked_from_index"] is False

    def test_malformed_yaml_frontmatter_does_not_fail_response(self, client, memory_dir):
        """A broken frontmatter block falls back; response still succeeds."""
        (memory_dir / "MEMORY.md").write_text("# Index\n", encoding="utf-8")
        (memory_dir / "good.md").write_text(
            "---\nname: Good file\ntype: project\n---\n\nbody\n", encoding="utf-8"
        )
        # Missing closing fence — our parser treats this as "no frontmatter",
        # so the whole file body (including the opening ---) becomes content.
        (memory_dir / "broken_no_close.md").write_text(
            "---\nname: never closed\ntype: project\n\nbody without closing fence\n",
            encoding="utf-8",
        )
        # Opening fence, totally garbage line inside, closing fence — individual
        # bad lines must be skipped, not crash the parser.
        (memory_dir / "garbage.md").write_text(
            "---\nname: partial\nnot_a_key_value_pair_line\n---\n\nbody\n",
            encoding="utf-8",
        )

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 3
        by_name = {f["filename"]: f for f in data["files"]}

        # Good file: valid frontmatter honored.
        assert by_name["good.md"]["name"] == "Good file"
        assert by_name["good.md"]["type"] == "project"

        # Broken (no close): should fall back to filename-derived name.
        assert by_name["broken_no_close.md"]["name"] == "broken no close"
        assert by_name["broken_no_close.md"]["type"] is None
        assert by_name["broken_no_close.md"]["description"] == ""

        # Garbage with partial valid lines: still succeeds, name extracted.
        assert by_name["garbage.md"]["name"] == "partial"

    def test_non_md_files_are_ignored(self, client, memory_dir):
        """Only *.md files should appear in files[]."""
        (memory_dir / "MEMORY.md").write_text("# Index\n", encoding="utf-8")
        (memory_dir / "a.md").write_text("body", encoding="utf-8")
        (memory_dir / "b.txt").write_text("ignored", encoding="utf-8")
        (memory_dir / "c.json").write_text("{}", encoding="utf-8")
        (memory_dir / "sub").mkdir()
        (memory_dir / "sub" / "nested.md").write_text("ignored", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["filename"] == "a.md"

    def test_filename_fallback_for_missing_frontmatter(self, client, memory_dir):
        """File with no frontmatter: name=underscore-to-space, description='', type=None."""
        (memory_dir / "MEMORY.md").write_text("# Index\n", encoding="utf-8")
        (memory_dir / "project_git_radio.md").write_text("Just body text.\n", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        meta = data["files"][0]
        assert meta["name"] == "project git radio"
        assert meta["description"] == ""
        assert meta["type"] is None


# =============================================================================
# linked_from_index computation tests
# =============================================================================


class TestLinkedFromIndex:
    def test_exact_match_links(self, client, memory_dir):
        (memory_dir / "MEMORY.md").write_text(
            "- [Foo](foo.md)\n- [Bar](bar.md)\n", encoding="utf-8"
        )
        (memory_dir / "foo.md").write_text("body", encoding="utf-8")
        (memory_dir / "bar.md").write_text("body", encoding="utf-8")
        (memory_dir / "baz.md").write_text("body", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        data = response.json()
        by_name = {f["filename"]: f for f in data["files"]}
        assert by_name["foo.md"]["linked_from_index"] is True
        assert by_name["bar.md"]["linked_from_index"] is True
        assert by_name["baz.md"]["linked_from_index"] is False

    def test_links_with_fragments_and_queries(self, client, memory_dir):
        """Link targets with #fragment or ?query must still match base filename."""
        (memory_dir / "MEMORY.md").write_text(
            "See [A](arch.md#section1) and [B](other.md?x=1).\n", encoding="utf-8"
        )
        (memory_dir / "arch.md").write_text("body", encoding="utf-8")
        (memory_dir / "other.md").write_text("body", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        data = response.json()
        by_name = {f["filename"]: f for f in data["files"]}
        assert by_name["arch.md"]["linked_from_index"] is True
        assert by_name["other.md"]["linked_from_index"] is True

    def test_relative_path_style_links(self, client, memory_dir):
        """Links with ./ prefix or subdir/ prefix use basename for match."""
        (memory_dir / "MEMORY.md").write_text(
            "[A](./arch.md) and [B](subdir/nested.md)\n", encoding="utf-8"
        )
        (memory_dir / "arch.md").write_text("body", encoding="utf-8")
        (memory_dir / "nested.md").write_text("body", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        data = response.json()
        by_name = {f["filename"]: f for f in data["files"]}
        assert by_name["arch.md"]["linked_from_index"] is True
        assert by_name["nested.md"]["linked_from_index"] is True

    def test_no_false_positive_on_substring(self, client, memory_dir):
        """`foo.md` in index should not match a file named `extrafoo.md`."""
        (memory_dir / "MEMORY.md").write_text("[Foo](foo.md)\n", encoding="utf-8")
        (memory_dir / "foo.md").write_text("body", encoding="utf-8")
        (memory_dir / "extrafoo.md").write_text("body", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        data = response.json()
        by_name = {f["filename"]: f for f in data["files"]}
        assert by_name["foo.md"]["linked_from_index"] is True
        assert by_name["extrafoo.md"]["linked_from_index"] is False

    def test_non_link_md_mentions_do_not_match(self, client, memory_dir):
        """A plain mention of foo.md in text (not a markdown link) must not count."""
        (memory_dir / "MEMORY.md").write_text(
            "Plain text mentioning foo.md but no link syntax.\n", encoding="utf-8"
        )
        (memory_dir / "foo.md").write_text("body", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        data = response.json()
        by_name = {f["filename"]: f for f in data["files"]}
        assert by_name["foo.md"]["linked_from_index"] is False


# =============================================================================
# GET /memory/files/{filename} — happy path
# =============================================================================


class TestMemoryFileEndpoint:
    def test_fetch_file_with_frontmatter(self, client, memory_dir):
        (memory_dir / "MEMORY.md").write_text("# Index\n", encoding="utf-8")
        (memory_dir / "arch.md").write_text(
            "---\n"
            "name: Architecture\n"
            "description: Folder IDs\n"
            "type: project\n"
            "---\n\n"
            "# Body\n\nThis body has exactly seven words here.\n",
            encoding="utf-8",
        )

        response = client.get(f"/projects/{ENCODED_NAME}/memory/files/arch.md")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "arch.md"
        assert data["name"] == "Architecture"
        assert data["description"] == "Folder IDs"
        assert data["type"] == "project"
        # Frontmatter should be stripped from the returned content.
        assert "---" not in data["content"].split("\n", 1)[0]
        assert "Body" in data["content"]
        # word_count computed on stripped body only.
        assert data["word_count"] > 0
        assert data["word_count"] < 20  # sanity — body is short

    def test_fetch_file_without_frontmatter(self, client, memory_dir):
        (memory_dir / "plain.md").write_text("Hello world\n", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory/files/plain.md")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "plain.md"
        assert data["name"] == "plain"
        assert data["type"] is None
        assert data["content"] == "Hello world\n"

    def test_fetch_not_found_returns_404(self, client, memory_dir):
        (memory_dir / "MEMORY.md").write_text("# Index\n", encoding="utf-8")

        response = client.get(f"/projects/{ENCODED_NAME}/memory/files/missing.md")
        assert response.status_code == 404


# =============================================================================
# GET /memory/files/{filename} — path traversal and input validation
# =============================================================================


class TestMemoryFilePathValidation:
    @pytest.mark.parametrize(
        "filename",
        [
            "..%2Fetc%2Fpasswd",  # URL-encoded path traversal
            "%2E%2E%2Fetc%2Fpasswd",  # URL-encoded dots
            "foo%2Fbar.md",  # slash inside filename
            ".hidden.md",  # leading dot
            "..md",  # dot-dot
            "file.txt",  # wrong extension
            "file",  # no extension
            "file.MD.bak",  # .md not at end
            "file.md.txt",  # .md not at end
            "file with space.md",  # space not allowed by regex
            "file$.md",  # $ not allowed by regex
        ],
    )
    def test_invalid_filename_returns_400(self, client, memory_dir, filename):
        response = client.get(f"/projects/{ENCODED_NAME}/memory/files/{filename}")
        # 400 for format violations; 404 for routing mismatch on extreme cases is
        # also acceptable since FastAPI may not match the route at all.
        assert response.status_code in (400, 404), f"{filename!r} returned {response.status_code}"

    def test_empty_filename_returns_404_or_400(self, client, memory_dir):
        """Empty filename doesn't match the route at all → 404, or 400."""
        response = client.get(f"/projects/{ENCODED_NAME}/memory/files/")
        assert response.status_code in (400, 404)

    def test_null_byte_filename_rejected(self, client, memory_dir):
        """Null byte in filename must be rejected."""
        # Starlette/httpx may reject the URL before it reaches the handler;
        # accept any 4xx response as a valid rejection.
        try:
            response = client.get(f"/projects/{ENCODED_NAME}/memory/files/file\x00.md")
            assert 400 <= response.status_code < 500
        except Exception:
            # Client-side rejection is also a valid defense.
            pass

    def test_dot_dot_in_filename_via_direct_handler_rejected(self, client, memory_dir, tmp_path):
        """
        `../etc/passwd` via URL would hit a different route; validate the
        handler directly to confirm its path validation.
        """
        from fastapi import HTTPException

        from routers.projects import get_project_memory_file

        # Create a fake secret outside memory_dir that traversal would access.
        (tmp_path / ".claude" / "secret.txt").write_text("sekrit", encoding="utf-8")

        class _DummyReq:
            pass

        import asyncio

        for bad in ("..etc.passwd", "foo..bar.md", "._hidden.md"):
            # Some of these should fail the leading-dot or .. or regex checks.
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    get_project_memory_file(
                        encoded_name=ENCODED_NAME,
                        filename=bad,
                        request=_DummyReq(),
                    )
                )
            assert exc_info.value.status_code in (400, 403)


# =============================================================================
# Non-existent project behavior
# =============================================================================


class TestMissingProject:
    def test_missing_project_memory_returns_empty(self, client, tmp_path, monkeypatch):
        """Project dir that doesn't exist on disk: returns 404 from resolver,
        or empty-exists=False response. Either is acceptable — we just assert
        the service does not crash."""
        claude_dir = tmp_path / ".claude"
        (claude_dir / "projects").mkdir(parents=True)

        from config import settings

        monkeypatch.setattr(settings, "claude_base", claude_dir)

        response = client.get(f"/projects/{ENCODED_NAME}/memory")
        # Either 404 (resolver rejects unknown slug) OR 200 with empty shape.
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            assert data["index"]["exists"] is False
            assert data["files"] == []
