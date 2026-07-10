# Syncthing Sync — Open Issues

Deferred issues identified during the sync permissions, security, and activity implementation (2026-03-08). These are architectural or structural improvements that were intentionally left for separate PRs to keep the current changeset focused.

## Issue Index

| # | Severity | File | Summary |
|---|----------|------|---------|
| 1 | HIGH | [folder-id-ambiguity.md](./folder-id-ambiguity.md) | Hyphen delimiter in folder IDs causes parsing ambiguity |
| 2 | HIGH | [duplicated-cli-api-logic.md](./duplicated-cli-api-logic.md) | Shared logic duplicated between CLI and API |
| 3 | HIGH | [sync-status-god-router.md](./sync-status-god-router.md) | `sync_status.py` is 1,900 lines — needs splitting |
| 4 | HIGH | [fstring-sql-construction.md](./fstring-sql-construction.md) | f-string SQL in `query_events` is fragile |
| 5 | MEDIUM | [packager-permission-errors.md](./packager-permission-errors.md) | Packager doesn't handle file permission errors |
| 6 | MEDIUM | [watcher-logging.md](./watcher-logging.md) | Watcher uses `print()` instead of `logger` |
