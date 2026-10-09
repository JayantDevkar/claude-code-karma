"""
HTTP Caching Module for FastAPI.

Consolidated module providing:
- HTTP date formatting and parsing (RFC 7231)
- ETag generation utilities
- Conditional request handling (304 Not Modified)
- Cache decorators for endpoints
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, List, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse

# === HTTP Date Utilities ===


def format_http_date(dt: datetime) -> str:
    """
    Format datetime as HTTP date string (RFC 7231).

    Args:
        dt: Datetime object (should be UTC)

    Returns:
        HTTP date string (e.g., "Sun, 11 Jan 2026 12:00:00 GMT")
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def parse_http_date(date_str: str) -> Optional[datetime]:
    """
    Parse HTTP date string to datetime.

    Args:
        date_str: HTTP date string

    Returns:
        UTC datetime, or None if parsing fails
    """
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# === ETag Utilities ===


def generate_etag(content: bytes) -> str:
    """
    Generate ETag from response content.

    Args:
        content: Response body bytes

    Returns:
        Quoted ETag string (e.g., '"abc123..."')
    """
    return f'"{hashlib.md5(content).hexdigest()}"'


def file_based_etag(file_path: Path) -> Optional[str]:
    """
    Generate ETag from file modification time.

    Uses file path and mtime to create a unique identifier that changes
    when the file is modified.

    Args:
        file_path: Path to the file

    Returns:
        Quoted ETag string, or None if file doesn't exist
    """
    if not file_path.exists():
        return None
    mtime = file_path.stat().st_mtime
    hash_input = f"{file_path}:{mtime}".encode()
    return f'"{hashlib.md5(hash_input).hexdigest()}"'


def get_file_mtime(file_path: Path) -> Optional[datetime]:
    """
    Get file modification time as UTC datetime.

    Args:
        file_path: Path to the file

    Returns:
        UTC datetime of last modification, or None if file doesn't exist
    """
    if not file_path.exists():
        return None
    mtime = file_path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def get_file_cache_info(file_path: Path) -> tuple[Optional[str], Optional[datetime]]:
    """
    Get both ETag and mtime from a file with a single stat() call.

    Combines file_based_etag() and get_file_mtime() to avoid redundant
    filesystem operations when both values are needed.

    Args:
        file_path: Path to the file

    Returns:
        Tuple of (etag, last_modified) where both are None if file doesn't exist
    """
    if not file_path.exists():
        return None, None
    mtime = file_path.stat().st_mtime
    hash_input = f"{file_path}:{mtime}".encode()
    etag = f'"{hashlib.md5(hash_input).hexdigest()}"'
    last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return etag, last_modified


# === Conditional Requests ===


def check_conditional_request(
    request: Request,
    etag: Optional[str] = None,
    last_modified: Optional[datetime] = None,
) -> Optional[Response]:
    """
    Check conditional request headers and return 304 if appropriate.

    Handles both If-None-Match (ETag) and If-Modified-Since headers.

    Args:
        request: FastAPI Request object
        etag: Current ETag value for the resource
        last_modified: Last modification datetime (UTC)

    Returns:
        Response with 304 status if conditions are met, None otherwise

    Example:
        @router.get("/{session_uuid}")
        async def get_session(session_uuid: str, request: Request):
            session = _get_session(session_uuid)
            # Use get_file_cache_info for single stat() call
            etag, mtime = get_file_cache_info(session.jsonl_path)

            conditional_response = check_conditional_request(request, etag, mtime)
            if conditional_response:
                return conditional_response

            # Build full response...
    """
    # Check If-None-Match (ETag validation)
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and etag:
        # Handle multiple ETags in header (comma-separated)
        client_etags = [e.strip() for e in if_none_match.split(",")]
        if etag in client_etags or "*" in client_etags:
            return Response(status_code=304, headers={"ETag": etag})

    # Check If-Modified-Since (date validation)
    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since and last_modified:
        client_time = parse_http_date(if_modified_since)
        if client_time and client_time >= last_modified:
            headers = {}
            if last_modified:
                headers["Last-Modified"] = format_http_date(last_modified)
            if etag:
                headers["ETag"] = etag
            return Response(status_code=304, headers=headers)

    return None


def build_cache_headers(
    etag: Optional[str] = None,
    last_modified: Optional[datetime] = None,
    max_age: int = 60,
    stale_while_revalidate: int = 300,
    private: bool = True,
) -> dict:
    """
    Build cache headers dictionary for a response.

    Args:
        etag: ETag value for the resource
        last_modified: Last modification datetime (UTC)
        max_age: Seconds response is considered fresh
        stale_while_revalidate: Seconds stale response can be used while revalidating
        private: Whether response is user-specific

    Returns:
        Dictionary of HTTP headers
    """
    headers = {}

    # Cache-Control directive
    directives = []
    if private:
        directives.append("private")
    else:
        directives.append("public")
    directives.append(f"max-age={max_age}")
    if stale_while_revalidate:
        directives.append(f"stale-while-revalidate={stale_while_revalidate}")
    headers["Cache-Control"] = ", ".join(directives)

    # ETag
    if etag:
        headers["ETag"] = etag

    # Last-Modified
    if last_modified:
        headers["Last-Modified"] = format_http_date(last_modified)

    return headers


# === Cache Decorators ===


def cacheable(
    max_age: int = 60,
    stale_while_revalidate: int = 300,
    private: bool = True,
    vary: Optional[List[str]] = None,
    include_etag: bool = True,
):
    """
    Decorator for cacheable endpoints.

    Adds Cache-Control headers and optional ETag generation to responses.
    Works with both sync and async endpoint functions.

    Args:
        max_age: Seconds response is considered fresh (default: 60)
        stale_while_revalidate: Seconds stale response can be used while revalidating (default: 300)
        private: Whether response is user-specific (default: True)
        vary: Headers that affect caching (e.g., ["Authorization"])
        include_etag: Whether to auto-generate ETag from response body (default: True)

    Example:
        @router.get("/data")
        @cacheable(max_age=120, stale_while_revalidate=600)
        async def get_data(request: Request):
            return {"key": "value"}
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Response:
            # Execute the endpoint
            result = await func(*args, **kwargs)

            # Build response with cache headers
            return _add_cache_headers(
                result, max_age, stale_while_revalidate, private, vary, include_etag
            )

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Response:
            # Execute the endpoint
            result = func(*args, **kwargs)

            # Build response with cache headers
            return _add_cache_headers(
                result, max_age, stale_while_revalidate, private, vary, include_etag
            )

        # Check if original function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _add_cache_headers(
    result: Any,
    max_age: int,
    stale_while_revalidate: int,
    private: bool,
    vary: Optional[List[str]],
    include_etag: bool,
) -> Response:
    """Add cache headers to a response."""
    # If already a Response, modify headers
    if isinstance(result, Response):
        response = result
        body = response.body
    else:
        # Convert result to JSON response
        # Handle Pydantic models and dicts - use mode="json" for datetime serialization
        if hasattr(result, "model_dump"):
            content = result.model_dump(mode="json")
        elif hasattr(result, "dict"):
            content = result.dict()
        elif isinstance(result, list):
            content = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in result
            ]
        else:
            content = result

        response = JSONResponse(content=content)
        body = json.dumps(content).encode()

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
    if include_etag and body:
        etag = f'"{hashlib.md5(body).hexdigest()}"'
        response.headers["ETag"] = etag

    return response


def no_cache():
    """
    Decorator for endpoints that should never be cached.

    Adds Cache-Control: no-store, no-cache, must-revalidate
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Response:
            result = await func(*args, **kwargs)
            return _add_no_cache_headers(result)

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Response:
            result = func(*args, **kwargs)
            return _add_no_cache_headers(result)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _add_no_cache_headers(result: Any) -> Response:
    """Add no-cache headers to a response."""
    if isinstance(result, Response):
        response = result
    else:
        if hasattr(result, "model_dump"):
            content = result.model_dump(mode="json")
        elif isinstance(result, list):
            content = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in result
            ]
        else:
            content = result
        response = JSONResponse(content=content)

    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response
