# Watcher Uses print() Instead of logger

**Severity:** MEDIUM
**File:** `cli/karma/watcher.py:56-59`

## Problem

Packaging errors in `SessionWatcher._do_package()` are printed to stderr via `print()`:

```python
except Exception as e:
    print(f"[karma watch] Packaging error: {e}", file=sys.stderr)
```

This makes errors invisible in log aggregation systems and doesn't include stack traces.

## Proposed Fix

```python
except Exception:
    logger.exception("Packaging error during watch")
```

Using `logger.exception()` captures the full traceback and routes through the standard logging module.

## Why Deferred

Minor robustness improvement with no functional impact for the current CLI-only usage. The watcher is run interactively where stderr is visible.
