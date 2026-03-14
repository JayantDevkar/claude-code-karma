"""Tests for titles_io read/write/merge logic."""

import json
from pathlib import Path

import pytest

from karma.titles_io import read_titles, write_title, write_titles_bulk


class TestReadTitles:
    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        result = read_titles(tmp_path / "titles.json")
        assert result == {}

    def test_returns_empty_dict_when_file_corrupt(self, tmp_path):
        path = tmp_path / "titles.json"
        path.write_text("not json")
        result = read_titles(path)
        assert result == {}

    def test_reads_valid_titles(self, tmp_path):
        path = tmp_path / "titles.json"
        path.write_text(json.dumps({
            "version": 1,
            "titles": {
                "uuid-1": {"title": "Fix bug", "source": "git", "generated_at": "2026-03-08T12:00:00Z"}
            }
        }))
        result = read_titles(path)
        assert "uuid-1" in result
        assert result["uuid-1"]["title"] == "Fix bug"
        assert result["uuid-1"]["source"] == "git"

    def test_ignores_unknown_version(self, tmp_path):
        path = tmp_path / "titles.json"
        path.write_text(json.dumps({"version": 99, "titles": {"a": {"title": "x"}}}))
        result = read_titles(path)
        assert result == {}


class TestWriteTitle:
    def test_creates_file_if_missing(self, tmp_path):
        path = tmp_path / "titles.json"
        write_title(path, "uuid-1", "Fix bug", "git")

        data = json.loads(path.read_text())
        assert data["version"] == 1
        assert data["titles"]["uuid-1"]["title"] == "Fix bug"
        assert data["titles"]["uuid-1"]["source"] == "git"
        assert "generated_at" in data["titles"]["uuid-1"]
        assert "updated_at" in data

    def test_merges_with_existing(self, tmp_path):
        path = tmp_path / "titles.json"
        write_title(path, "uuid-1", "First title", "git")
        write_title(path, "uuid-2", "Second title", "haiku")

        data = json.loads(path.read_text())
        assert len(data["titles"]) == 2
        assert data["titles"]["uuid-1"]["title"] == "First title"
        assert data["titles"]["uuid-2"]["title"] == "Second title"

    def test_overwrites_existing_uuid(self, tmp_path):
        path = tmp_path / "titles.json"
        write_title(path, "uuid-1", "Old title", "fallback")
        write_title(path, "uuid-1", "New title", "haiku")

        data = json.loads(path.read_text())
        assert data["titles"]["uuid-1"]["title"] == "New title"
        assert data["titles"]["uuid-1"]["source"] == "haiku"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "titles.json"
        write_title(path, "uuid-1", "Test", "git")
        assert path.exists()


class TestWriteTitlesBulk:
    def test_writes_multiple_titles(self, tmp_path):
        path = tmp_path / "titles.json"
        entries = {
            "uuid-1": {"title": "First", "source": "git"},
            "uuid-2": {"title": "Second", "source": "haiku"},
        }
        write_titles_bulk(path, entries)

        data = json.loads(path.read_text())
        assert len(data["titles"]) == 2

    def test_merges_with_existing_preserving_newer(self, tmp_path):
        path = tmp_path / "titles.json"
        # Write initial
        write_title(path, "uuid-1", "Original", "haiku")

        # Bulk write that includes uuid-1 with different title
        entries = {
            "uuid-1": {"title": "Bulk override", "source": "git"},
            "uuid-2": {"title": "New entry", "source": "haiku"},
        }
        write_titles_bulk(path, entries)

        data = json.loads(path.read_text())
        assert len(data["titles"]) == 2
        # Bulk should overwrite
        assert data["titles"]["uuid-1"]["title"] == "Bulk override"

    def test_handles_empty_entries(self, tmp_path):
        path = tmp_path / "titles.json"
        write_titles_bulk(path, {})
        # Should create valid empty file
        data = json.loads(path.read_text())
        assert data["titles"] == {}
