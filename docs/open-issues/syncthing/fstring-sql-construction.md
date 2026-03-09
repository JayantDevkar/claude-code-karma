# f-String SQL Construction in query_events

**Severity:** HIGH
**File:** `api/db/sync_queries.py:256`

## Problem

The `query_events()` function builds WHERE clauses via f-string concatenation:

```python
where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
rows = conn.execute(
    f"SELECT * FROM sync_events {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
    params,
).fetchall()
```

While the column names are hardcoded (safe) and values use named parameters (also safe), the pattern is fragile. A future developer could accidentally introduce user input into the column name position, creating a SQL injection vulnerability.

## Current Safety

- All condition strings are hardcoded: `"team_name = :team_name"`, `"event_type = :event_type"`, etc.
- All user values go through named parameters (`:team_name`, `:event_type`)
- A safety comment documents this: `# conditions list is built from hardcoded column names only`

## Proposed Fix

Adopt a query builder pattern or add explicit column allowlisting:

```python
_ALLOWED_FILTER_COLUMNS = {"team_name", "event_type", "member_name"}

def query_events(conn, filters: dict, limit=50, offset=0):
    conditions = []
    params = {"limit": limit, "offset": offset}
    for col, val in filters.items():
        assert col in _ALLOWED_FILTER_COLUMNS, f"Invalid filter column: {col}"
        conditions.append(f"{col} = :{col}")
        params[col] = val
    ...
```

## Why Deferred

The current code is safe as written. The proper fix is adopting a query builder (like SQLAlchemy Core) which is a larger architectural decision affecting all of `sync_queries.py`.
