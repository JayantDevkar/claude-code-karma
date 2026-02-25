# Phase 3: HTTP Caching and Response Optimization

**Priority**: Medium
**Complexity**: Low-Medium
**Impact**: Medium-High
**Risk**: Low

**Dependency**: Can run in parallel with Phase 1 and Phase 2

---

## Problem Statement

The FastAPI backend sets no HTTP caching headers. Every browser request triggers full backend processing, even for data that hasn't changed.

### Verified Issues

| Finding | Impact |
|---------|--------|
| No `Cache-Control` headers on any endpoint | Browsers can't cache responses |
| No `ETag` headers | No conditional request support |
| No `Last-Modified` headers | Can't use `If-Modified-Since` |
| Session data is immutable after creation | Perfect candidate for aggressive caching |

---

## Solution Design

### Strategy 1: Static Resource Caching

Session JSONL files are append-only and rarely modified after creation. Use file modification time for cache validation.

### Strategy 2: Response ETags

Generate ETags based on file modification time and content hash for conditional requests.

### Strategy 3: Cache-Control Headers

Apply appropriate caching directives based on data mutability patterns.

---

## Implementation

### 1. Cache Middleware

```python
# apps/api/middleware/caching.py

from fastapi import Request, Response
from fastapi.responses import JSONResponse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable
import functools

def generate_etag(content: bytes) -> str:
    """Generate ETag from response content."""
    return f'"{hashlib.md5(content).hexdigest()}"'

def file_based_etag(file_path: Path) -> str:
    """Generate ETag from file modification time."""
    if file_path.exists():
        mtime = file_path.stat().st_mtime
        return f'"{hashlib.md5(f"{file_path}:{mtime}".encode()).hexdigest()}"'
    return None

def format_http_date(dt: datetime) -> str:
    """Format datetime as HTTP date string."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def parse_http_date(date_str: str) -> Optional[datetime]:
    """Parse HTTP date string to datetime."""
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
```

### 2. Session Endpoint Caching

```python
# apps/api/routers/sessions.py

from fastapi import Request, Response, Header
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime, timezone

def get_session_cache_headers(session) -> dict:
    """Generate cache headers for a session."""
    # Session files are append-only; use file mtime for validation
    jsonl_path = session.jsonl_path

    if not jsonl_path.exists():
        return {}

    stat = jsonl_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    etag = file_based_etag(jsonl_path)

    return {
        "ETag": etag,
        "Last-Modified": format_http_date(mtime),
        "Cache-Control": "private, max-age=60, stale-while-revalidate=300"
    }


@router.get("/{session_uuid}")
async def get_session(
    session_uuid: str,
    request: Request,
    if_none_match: Optional[str] = Header(None),
    if_modified_since: Optional[str] = Header(None)
) -> Response:
    """Get session details with HTTP caching support."""
    session = _get_session(session_uuid)

    # Generate cache validation info
    cache_headers = get_session_cache_headers(session)

    # Check If-None-Match (ETag)
    if if_none_match and cache_headers.get("ETag"):
        if if_none_match == cache_headers["ETag"]:
            return Response(status_code=304, headers=cache_headers)

    # Check If-Modified-Since
    if if_modified_since and cache_headers.get("Last-Modified"):
        client_time = parse_http_date(if_modified_since)
        server_time = parse_http_date(cache_headers["Last-Modified"])
        if client_time and server_time and client_time >= server_time:
            return Response(status_code=304, headers=cache_headers)

    # Build full response
    response_data = build_session_response(session)

    return JSONResponse(
        content=response_data,
        headers=cache_headers
    )
```

### 3. Caching Decorator

```python
# apps/api/utils/cache_decorator.py

from functools import wraps
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from typing import Callable, Optional
import hashlib
from datetime import datetime, timezone

def cacheable(
    max_age: int = 60,
    stale_while_revalidate: int = 300,
    private: bool = True,
    vary: Optional[list] = None
):
    """
    Decorator for cacheable endpoints.

    Args:
        max_age: Seconds response is considered fresh
        stale_while_revalidate: Seconds stale response can be used while revalidating
        private: Whether response is user-specific
        vary: Headers that affect caching (e.g., ["Authorization"])
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Execute the endpoint
            result = await func(request, *args, **kwargs)

            # If already a Response, just add headers
            if isinstance(result, Response):
                response = result
            else:
                response = JSONResponse(content=result)

            # Build Cache-Control directive
            directives = []
            if private:
                directives.append("private")
            else:
                directives.append("public")
            directives.append(f"max-age={max_age}")
            if stale_while_revalidate:
                directives.append(f"stale-while-revalidate={stale_while_revalidate}")

            response.headers["Cache-Control"] = ", ".join(directives)

            # Add Vary header if specified
            if vary:
                response.headers["Vary"] = ", ".join(vary)

            # Generate ETag from response body
            body = response.body
            if body:
                etag = f'"{hashlib.md5(body).hexdigest()}"'
                response.headers["ETag"] = etag

            return response

        return wrapper
    return decorator
```

### 4. Endpoint-Specific Cache Policies

```python
# apps/api/routers/sessions.py

# Session detail - moderate caching (data rarely changes)
@router.get("/{session_uuid}")
@cacheable(max_age=60, stale_while_revalidate=300, private=True)
async def get_session(session_uuid: str, request: Request):
    ...

# Timeline - moderate caching
@router.get("/{session_uuid}/timeline")
@cacheable(max_age=60, stale_while_revalidate=300, private=True)
async def get_timeline(session_uuid: str, request: Request):
    ...

# File activity - longer cache (historical data)
@router.get("/{session_uuid}/file-activity")
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
async def get_file_activity(session_uuid: str, request: Request):
    ...

# Tools - longer cache (historical data)
@router.get("/{session_uuid}/tools")
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
async def get_tools(session_uuid: str, request: Request):
    ...


# apps/api/routers/projects.py

# Project list - short cache (new sessions may appear)
@router.get("/")
@cacheable(max_age=30, stale_while_revalidate=60, private=True)
async def list_projects(request: Request):
    ...

# Project detail - moderate cache
@router.get("/{encoded_name}")
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_project(encoded_name: str, request: Request):
    ...


# apps/api/routers/analytics.py

# Analytics - short cache (aggregated from multiple sessions)
@router.get("/projects/{encoded_name}")
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
async def get_project_analytics(encoded_name: str, request: Request):
    ...
```

### 5. Conditional Request Handling

```python
# apps/api/utils/conditional.py

from fastapi import Request, Response, HTTPException
from typing import Optional, Tuple
from datetime import datetime

def check_conditional_request(
    request: Request,
    etag: Optional[str],
    last_modified: Optional[datetime]
) -> Optional[Response]:
    """
    Check conditional request headers and return 304 if appropriate.

    Returns:
        Response with 304 status if conditions met, None otherwise
    """
    # Check If-None-Match
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and etag:
        # Handle multiple ETags in header
        client_etags = [e.strip() for e in if_none_match.split(",")]
        if etag in client_etags or "*" in client_etags:
            return Response(
                status_code=304,
                headers={"ETag": etag}
            )

    # Check If-Modified-Since
    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since and last_modified:
        client_time = parse_http_date(if_modified_since)
        if client_time and client_time >= last_modified:
            return Response(
                status_code=304,
                headers={"Last-Modified": format_http_date(last_modified)}
            )

    return None


# Usage in endpoint
@router.get("/{session_uuid}")
async def get_session(session_uuid: str, request: Request):
    session = _get_session(session_uuid)

    # Get cache validators
    etag = file_based_etag(session.jsonl_path)
    mtime = get_file_mtime(session.jsonl_path)

    # Check conditional request
    conditional_response = check_conditional_request(request, etag, mtime)
    if conditional_response:
        return conditional_response

    # Build full response
    ...
```

---

## Cache Policy Matrix

| Endpoint | max-age | stale-while-revalidate | Rationale |
|----------|---------|------------------------|-----------|
| `GET /projects` | 30s | 60s | New projects/sessions may appear frequently |
| `GET /projects/{id}` | 60s | 120s | Project metadata changes infrequently |
| `GET /sessions/{uuid}` | 60s | 300s | Session data is append-only |
| `GET /sessions/{uuid}/timeline` | 60s | 300s | Historical, rarely changes |
| `GET /sessions/{uuid}/file-activity` | 300s | 600s | Historical, never changes |
| `GET /sessions/{uuid}/tools` | 300s | 600s | Historical, never changes |
| `GET /sessions/{uuid}/subagents` | 300s | 600s | Historical, never changes |
| `GET /analytics/*` | 120s | 300s | Aggregated, computed data |

---

## Files to Modify

| File | Changes |
|------|---------|
| `apps/api/middleware/caching.py` | NEW - Cache utilities and helpers |
| `apps/api/utils/cache_decorator.py` | NEW - `@cacheable` decorator |
| `apps/api/utils/conditional.py` | NEW - Conditional request handling |
| `apps/api/routers/sessions.py` | Add cache decorators and headers |
| `apps/api/routers/projects.py` | Add cache decorators and headers |
| `apps/api/routers/analytics.py` | Add cache decorators and headers |

---

## Implementation Steps

### Step 1: Create Cache Utilities
1. Implement `generate_etag()` and `file_based_etag()`
2. Implement HTTP date formatting/parsing
3. Create `check_conditional_request()` helper

### Step 2: Create Cacheable Decorator
1. Implement `@cacheable` decorator
2. Support configurable max-age and stale-while-revalidate
3. Auto-generate ETags from response body

### Step 3: Add to Session Endpoints
1. Apply `@cacheable` to all session endpoints
2. Add conditional request handling for `get_session()`
3. Test 304 responses with browser dev tools

### Step 4: Add to Project Endpoints
1. Apply `@cacheable` to project endpoints
2. Use shorter cache times due to dynamic content

### Step 5: Add to Analytics Endpoints
1. Apply `@cacheable` to analytics endpoints
2. Consider query parameter impact on caching

### Step 6: Frontend Integration
1. Verify TanStack Query respects HTTP cache headers
2. Adjust stale times to complement server caching

---

## Testing Requirements

### Unit Tests

```python
# tests/test_caching.py

def test_etag_generation():
    """Verify consistent ETag generation."""
    content = b'{"test": "data"}'
    etag1 = generate_etag(content)
    etag2 = generate_etag(content)
    assert etag1 == etag2
    assert etag1.startswith('"') and etag1.endswith('"')

def test_conditional_request_304():
    """Verify 304 response on matching ETag."""
    request = MockRequest(headers={"if-none-match": '"abc123"'})
    response = check_conditional_request(request, '"abc123"', None)
    assert response.status_code == 304

def test_conditional_request_modified_since():
    """Verify 304 response on If-Modified-Since."""
    old_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    request = MockRequest(headers={
        "if-modified-since": "Wed, 01 Jan 2025 00:00:00 GMT"
    })
    response = check_conditional_request(request, None, old_time)
    assert response.status_code == 304
```

### Integration Tests

```python
def test_session_endpoint_caching(client):
    """Verify cache headers on session endpoint."""
    response = client.get(f"/sessions/{uuid}")
    assert response.status_code == 200
    assert "Cache-Control" in response.headers
    assert "ETag" in response.headers
    assert "max-age=" in response.headers["Cache-Control"]

def test_conditional_get_returns_304(client):
    """Verify conditional GET returns 304."""
    # First request
    response1 = client.get(f"/sessions/{uuid}")
    etag = response1.headers["ETag"]

    # Second request with ETag
    response2 = client.get(
        f"/sessions/{uuid}",
        headers={"If-None-Match": etag}
    )
    assert response2.status_code == 304
```

---

## Expected Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Repeated requests | Full processing | 304 response | 90%+ bandwidth savings |
| Browser cache | Not utilized | Utilized | Faster page loads |
| Server load | All requests processed | Conditional skipped | 30-50% reduction |

---

## Rollback Plan

1. Remove `@cacheable` decorators from endpoints
2. Remove cache middleware and utilities
3. No database changes required
4. No API contract changes (headers are additive)

---

## Success Criteria

- [ ] All endpoints return appropriate `Cache-Control` headers
- [ ] Session endpoints support conditional requests (304)
- [ ] Browser dev tools show cache hits
- [ ] No breaking changes to API responses
- [ ] Frontend still receives fresh data when needed
