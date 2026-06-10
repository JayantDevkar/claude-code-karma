"""
Unit tests for the global memory index router.

The endpoint is deliberately light — it counts memory files per project and
never parses content — so these tests build a fake projects tree and assert
on the roll-up shape.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


from routers.memory import _project_label, memory_index


def _make_memory(projects_root: Path, encoded: str, notes: list[str], index: bool):
    mem = projects_root / encoded / "memory"
    mem.mkdir(parents=True)
    if index:
        (mem / "MEMORY.md").write_text("- [x](x.md)\n")
    for n in notes:
        (mem / n).write_text(f"# {n}\n")


class TestMemoryIndex:
    def test_counts_and_orders(self, tmp_path, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "claude_base", tmp_path)
        projects = tmp_path / "projects"
        projects.mkdir()

        _make_memory(projects, "-home-me-alpha", ["a.md", "b.md"], index=True)
        _make_memory(projects, "-home-me-beta", ["c.md"], index=False)
        # a project dir with no memory/ must be ignored
        (projects / "-home-me-empty").mkdir()

        out = memory_index()
        assert out["total_projects"] == 2
        assert out["total_notes"] == 3  # a, b, c (MEMORY.md excluded)
        # ordered by note_count desc → alpha (2) before beta (1)
        assert [p["encoded"] for p in out["projects"]] == [
            "-home-me-alpha",
            "-home-me-beta",
        ]
        assert out["projects"][0]["has_index"] is True
        assert out["projects"][1]["has_index"] is False

    def test_index_only_project_counts_zero_notes(self, tmp_path, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "claude_base", tmp_path)
        projects = tmp_path / "projects"
        projects.mkdir()
        _make_memory(projects, "-x", [], index=True)

        out = memory_index()
        assert out["total_projects"] == 1
        assert out["projects"][0]["note_count"] == 0
        assert out["projects"][0]["has_index"] is True

    def test_empty_projects_dir(self, tmp_path, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "claude_base", tmp_path)
        (tmp_path / "projects").mkdir()
        out = memory_index()
        assert out == {"projects": [], "total_projects": 0, "total_notes": 0}


class TestProjectLabel:
    def test_falls_back_when_undecodable(self):
        # A made-up encoded name won't decode to a real path → basename fallback
        label = _project_label("-home-me-myrepo")
        assert label  # non-empty
        assert "/" not in label
