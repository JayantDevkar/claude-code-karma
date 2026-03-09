# Folder ID Ambiguity

**Severity:** HIGH
**Files:** `api/routers/sync_status.py:211`, `cli/karma/main.py:171`

## Problem

Syncthing folder IDs use hyphens as delimiters: `karma-out-{member}-{suffix}`. Both member names and project suffixes can contain hyphens, making parsing ambiguous.

Example: `karma-out-alice-bob-my-app` could be:
- member=`alice`, suffix=`bob-my-app`
- member=`alice-bob`, suffix=`my-app`

The current parser picks the shortest prefix (first hyphen split). The CLI has a smarter `_extract_username_from_karma_folder()` that cross-references known member names from the DB, which resolves most real-world cases.

## Impact

- Wrong inbox folder matching during Syncthing cleanup
- Wrong member attribution during auto-accept
- Wrong project detection in `_find_team_for_folder`

## Possible Fixes

1. **Change delimiter** to double-dash `--` (e.g., `karma-out--alice-bob--my-app`). Requires migration of existing Syncthing folder configs on all deployed machines.
2. **Enforce no-hyphens-in-usernames** at registration time. Breaks existing users with hyphenated names.
3. **Always use DB lookup** for disambiguation (current CLI approach). Extend to API side.

## Why Deferred

Options 1-2 require migration strategy affecting deployed machines. Option 3 is partially done (CLI side). Needs a dedicated PR with proper migration plan.
