"""Tests for multi-file HTTP cache validators."""

import os
from pathlib import Path

from http_caching import get_files_cache_info


def test_etag_changes_when_any_file_changes(tmp_path: Path):
    """A change to a secondary file (e.g. a subagent JSONL) must change the ETag."""
    main = tmp_path / "session.jsonl"
    sub = tmp_path / "agent-a1.jsonl"
    main.write_text("{}\n")
    sub.write_text("{}\n")
    os.utime(main, (1_000, 1_000))
    os.utime(sub, (2_000, 2_000))

    etag_before, last_modified = get_files_cache_info([main, sub])
    os.utime(sub, (3_000, 3_000))
    etag_after, last_modified_after = get_files_cache_info([main, sub])

    assert etag_before != etag_after
    assert last_modified.timestamp() == 2_000
    assert last_modified_after.timestamp() == 3_000


def test_missing_files_are_skipped(tmp_path: Path):
    main = tmp_path / "session.jsonl"
    main.write_text("{}\n")

    etag, last_modified = get_files_cache_info([main, tmp_path / "missing.jsonl"])

    assert etag is not None
    assert last_modified is not None
    assert get_files_cache_info([tmp_path / "missing.jsonl"]) == (None, None)
