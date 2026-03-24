# Packager Permission Error Handling

**Severity:** MEDIUM
**File:** `cli/karma/packager.py:161-179`

## Problem

`_discover_from_dir()` calls `stat()` on each JSONL file without catching `PermissionError`. On multi-user machines or when files are actively being written by Claude Code, `stat()` or later `shutil.copy2()` could fail.

## Impact

A single unreadable file would crash the entire packaging operation, preventing all other sessions from syncing.

## Proposed Fix

Wrap the stat/add logic in try/except to skip unreadable files:

```python
try:
    file_stat = jsonl_path.stat()
except (PermissionError, OSError) as e:
    logger.debug("Skipping unreadable file %s: %s", jsonl_path, e)
    continue
```

## Why Deferred

Edge case on single-user desktop machines (the primary deployment target). Trivial fix but outside the scope of the current security/permissions changeset.
