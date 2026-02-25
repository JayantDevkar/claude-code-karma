# Phase 4: Async and Structural Optimizations

**Priority**: Medium
**Complexity**: High
**Impact**: Medium-High
**Risk**: Medium

**Dependency**: Phase 1 and Phase 2 should be completed first

---

## Problem Statement

The backend has structural inefficiencies that limit scalability:
1. Date filtering occurs after loading all sessions
2. Subagent processing is sequential (no parallelism)
3. Synchronous file I/O blocks the event loop
4. No connection pooling for file handles

### Verified Issues

| Finding | Location | Impact |
|---------|----------|--------|
| Filter after load | `analytics.py:147-150` | Loads unnecessary sessions |
| Sequential subagent iteration | `sessions.py:451-462` | N serial file reads |
| Sync file I/O | `session.py:160` | Blocks async event loop |
| Per-project session time | `projects.py:115` | O(n) file stats |

---

## Solution Design

### Strategy 1: Early Date Filtering

Filter sessions by file modification time before loading full content.

### Strategy 2: Parallel Subagent Processing

Use asyncio to process multiple subagents concurrently.

### Strategy 3: Async File I/O

Use `aiofiles` for non-blocking file operations.

### Strategy 4: Batch Operations

Aggregate file operations to reduce syscall overhead.

---

## Implementation

### 1. Early Date Filtering

```python
# models/project.py

from pathlib import Path
from datetime import datetime, timezone
from typing import Iterator, Optional

def list_sessions_filtered(
    self,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = None
) -> Iterator[Session]:
    """
    List sessions with early filtering by file modification time.

    Filters by file mtime before parsing JSONL, avoiding unnecessary I/O.
    """
    jsonl_files = list(self.project_dir.glob("*.jsonl"))

    # Pre-filter by file modification time
    if start_date or end_date:
        filtered_files = []
        for f in jsonl_files:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)

            # File mtime >= session end_time, so use as upper bound proxy
            # A session modified before start_date can't have started after it
            if end_date and mtime < start_date:
                continue

            # For start_date filtering, we need actual start_time
            # But mtime gives us a reasonable approximation for most cases
            filtered_files.append(f)

        jsonl_files = filtered_files

    # Sort by modification time (most recent first)
    jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    # Apply limit
    if limit:
        jsonl_files = jsonl_files[:limit]

    for jsonl_path in jsonl_files:
        try:
            session = Session.from_path(jsonl_path)

            # Precise filtering after loading
            if start_date and session.start_time and session.start_time < start_date:
                continue
            if end_date and session.start_time and session.start_time > end_date:
                continue

            yield session
        except Exception:
            continue
```

### 2. Parallel Subagent Processing

```python
# apps/api/utils/parallel.py

import asyncio
from typing import List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor
import functools

# Shared thread pool for file I/O
_io_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file_io")

async def run_in_thread(func: Callable, *args, **kwargs) -> Any:
    """Run a sync function in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _io_executor,
        functools.partial(func, *args, **kwargs)
    )


async def process_subagents_parallel(
    subagents: List,
    processor: Callable
) -> List[Dict]:
    """
    Process multiple subagents in parallel.

    Args:
        subagents: List of Agent objects
        processor: Function to extract data from each agent

    Returns:
        List of processed results
    """
    tasks = [
        run_in_thread(processor, subagent)
        for subagent in subagents
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions
    return [r for r in results if not isinstance(r, Exception)]


# Usage in endpoint
@router.get("/{session_uuid}/subagents")
async def get_subagents(session_uuid: str):
    session = _get_session(session_uuid)
    subagents = list(session.list_subagents())

    def process_subagent(subagent):
        """Extract data from single subagent (runs in thread)."""
        tool_counts = {}
        initial_prompt = None

        for msg in subagent.iter_messages():
            if initial_prompt is None and isinstance(msg, UserMessage):
                initial_prompt = msg.content[:500]
            if isinstance(msg, AssistantMessage):
                for block in msg.content_blocks:
                    if isinstance(block, ToolUseBlock):
                        tool_counts[block.name] = tool_counts.get(block.name, 0) + 1

        return {
            "agent_id": subagent.agent_id,
            "slug": subagent.slug,
            "tool_counts": tool_counts,
            "initial_prompt": initial_prompt
        }

    # Process all subagents in parallel
    subagent_data = await process_subagents_parallel(subagents, process_subagent)

    return {"subagents": subagent_data}
```

### 3. Async File I/O

```python
# models/async_session.py

import aiofiles
import json
from typing import AsyncIterator, Optional
from pathlib import Path

class AsyncSession:
    """
    Async version of Session for high-throughput scenarios.

    Use when processing many sessions concurrently.
    """

    def __init__(self, jsonl_path: Path):
        self.jsonl_path = jsonl_path

    async def iter_messages(self) -> AsyncIterator[Message]:
        """Async iteration over messages."""
        if not self.jsonl_path.exists():
            return

        async with aiofiles.open(self.jsonl_path, "r", encoding="utf-8") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    yield parse_message(data)
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

    async def get_metadata(self) -> Dict[str, Any]:
        """Get all metadata in single async pass."""
        first_ts = None
        last_ts = None
        slug = None
        message_count = 0

        async for msg in self.iter_messages():
            message_count += 1
            if first_ts is None:
                first_ts = msg.timestamp
            last_ts = msg.timestamp
            if not slug and hasattr(msg, 'slug') and msg.slug:
                slug = msg.slug

        return {
            "start_time": first_ts,
            "end_time": last_ts,
            "slug": slug,
            "message_count": message_count
        }


# Usage in analytics
async def calculate_analytics_async(sessions: List[Path]) -> Dict:
    """Calculate analytics using async I/O."""
    async def process_session(path: Path):
        session = AsyncSession(path)
        return await session.get_metadata()

    # Process all sessions concurrently
    tasks = [process_session(p) for p in sessions]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate results
    valid_results = [r for r in results if isinstance(r, dict)]
    return aggregate_metadata(valid_results)
```

### 4. Batch File Operations

```python
# models/batch_loader.py

from pathlib import Path
from typing import List, Dict, Optional
import json

class BatchSessionLoader:
    """
    Load multiple sessions efficiently with batched I/O.
    """

    def __init__(self, session_paths: List[Path]):
        self.paths = session_paths
        self._cache: Dict[Path, List[Message]] = {}

    def load_all_metadata(self) -> List[Dict]:
        """
        Load metadata from all sessions using optimized I/O.

        Uses read-ahead and batching for better throughput.
        """
        results = []

        for path in self.paths:
            try:
                # Read file in chunks for better I/O performance
                with open(path, "r", encoding="utf-8", buffering=64*1024) as f:
                    first_line = None
                    last_line = None

                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if first_line is None:
                            first_line = line
                        last_line = line

                    # Parse only first and last for timestamps
                    start_time = None
                    end_time = None
                    slug = None

                    if first_line:
                        try:
                            data = json.loads(first_line)
                            start_time = data.get("timestamp")
                            slug = data.get("slug")
                        except json.JSONDecodeError:
                            pass

                    if last_line and last_line != first_line:
                        try:
                            data = json.loads(last_line)
                            end_time = data.get("timestamp")
                        except json.JSONDecodeError:
                            pass
                    elif first_line:
                        end_time = start_time

                    results.append({
                        "path": path,
                        "start_time": start_time,
                        "end_time": end_time,
                        "slug": slug
                    })

            except Exception:
                continue

        return results

    def load_first_last_lines(self, path: Path) -> tuple:
        """
        Efficiently read only first and last lines of a file.

        Uses seek for large files to avoid reading middle content.
        """
        with open(path, "rb") as f:
            # Read first line
            first_line = f.readline().decode("utf-8").strip()

            # Seek to end and scan backwards for last line
            f.seek(0, 2)  # End of file
            file_size = f.tell()

            if file_size < 4096:
                # Small file, just read normally
                f.seek(0)
                lines = f.read().decode("utf-8").strip().split("\n")
                last_line = lines[-1] if lines else first_line
            else:
                # Large file, read last chunk
                f.seek(max(0, file_size - 4096))
                chunk = f.read().decode("utf-8", errors="ignore")
                lines = chunk.strip().split("\n")
                last_line = lines[-1] if lines else first_line

        return first_line, last_line
```

### 5. Project Listing Optimization

```python
# apps/api/routers/projects.py

from typing import List, Dict
from pathlib import Path
import os

@router.get("/")
async def list_projects() -> List[Dict]:
    """
    List projects with optimized session time detection.

    Uses batch stat() calls and minimal file parsing.
    """
    projects = []

    for project in Project.list_all():
        # Get latest session time using file stats only
        latest_time = await get_latest_session_time_fast(project)

        projects.append({
            "encoded_name": project.encoded_name,
            "path": str(project.path),
            "latest_session_time": latest_time,
            # Don't load full session count here - defer to detail endpoint
        })

    return projects


async def get_latest_session_time_fast(project) -> Optional[str]:
    """
    Get latest session time using only file modification times.

    Avoids parsing JSONL entirely.
    """
    jsonl_files = list(project.project_dir.glob("*.jsonl"))

    if not jsonl_files:
        return None

    # Use file mtime as proxy for session activity time
    # This is fast: single stat() call per file
    latest_file = max(jsonl_files, key=lambda f: f.stat().st_mtime)
    mtime = datetime.fromtimestamp(latest_file.stat().st_mtime, tz=timezone.utc)

    return mtime.isoformat()
```

### 6. Connection Pool for File Handles

```python
# models/file_pool.py

from pathlib import Path
from typing import Dict, Optional
from contextlib import contextmanager
import threading
from collections import OrderedDict

class FileHandlePool:
    """
    Pool of file handles for frequently accessed files.

    Reduces open/close overhead for repeated file access.
    """

    def __init__(self, max_handles: int = 100):
        self.max_handles = max_handles
        self._handles: OrderedDict[Path, 'PooledHandle'] = OrderedDict()
        self._lock = threading.Lock()

    @contextmanager
    def open(self, path: Path, mode: str = "r"):
        """Get a file handle from the pool."""
        with self._lock:
            if path in self._handles:
                # Move to end (LRU)
                self._handles.move_to_end(path)
                handle = self._handles[path]
                handle.seek(0)  # Reset position
            else:
                # Open new handle
                if len(self._handles) >= self.max_handles:
                    # Evict oldest
                    _, old_handle = self._handles.popitem(last=False)
                    old_handle.close()

                handle = PooledHandle(path, mode)
                self._handles[path] = handle

        try:
            yield handle
        finally:
            # Don't close, return to pool
            pass

    def close_all(self):
        """Close all pooled handles."""
        with self._lock:
            for handle in self._handles.values():
                handle.close()
            self._handles.clear()


class PooledHandle:
    """Wrapper around file handle for pooling."""

    def __init__(self, path: Path, mode: str):
        self._path = path
        self._file = open(path, mode, encoding="utf-8")

    def __iter__(self):
        return iter(self._file)

    def seek(self, pos: int):
        self._file.seek(pos)

    def read(self, size: int = -1) -> str:
        return self._file.read(size)

    def readline(self) -> str:
        return self._file.readline()

    def close(self):
        self._file.close()


# Global pool instance
_file_pool = FileHandlePool(max_handles=50)

def get_file_pool() -> FileHandlePool:
    return _file_pool
```

---

## Files to Modify/Create

| File | Changes |
|------|---------|
| `models/project.py` | Add `list_sessions_filtered()` method |
| `apps/api/utils/parallel.py` | NEW - Parallel processing utilities |
| `models/async_session.py` | NEW - Async session reader |
| `models/batch_loader.py` | NEW - Batch session loading |
| `models/file_pool.py` | NEW - File handle pooling |
| `apps/api/routers/projects.py` | Optimize `list_projects()` |
| `apps/api/routers/analytics.py` | Use early date filtering |
| `apps/api/routers/sessions.py` | Use parallel subagent processing |
| `requirements.txt` | Add `aiofiles` dependency |

---

## Implementation Steps

### Step 1: Add Dependencies
1. Add `aiofiles>=23.0.0` to requirements
2. Install in development environment

### Step 2: Implement Early Date Filtering
1. Add `list_sessions_filtered()` to Project model
2. Update analytics endpoints to use filtered listing
3. Test with date range queries

### Step 3: Implement Parallel Subagent Processing
1. Create thread pool executor utility
2. Refactor `get_subagents()` to use parallel processing
3. Benchmark improvement with sessions having 10+ subagents

### Step 4: Implement Async File I/O (Optional)
1. Create `AsyncSession` class
2. Use in high-throughput scenarios (analytics)
3. Keep sync version for simpler endpoints

### Step 5: Implement Batch Operations
1. Create `BatchSessionLoader` class
2. Use for project listing and analytics
3. Optimize first/last line reading

### Step 6: Implement File Handle Pool (Optional)
1. Create pooling infrastructure
2. Integrate with Session/Agent iter_messages
3. Monitor memory usage

---

## Testing Requirements

### Unit Tests

```python
# tests/test_parallel.py

@pytest.mark.asyncio
async def test_parallel_subagent_processing():
    """Verify subagents processed in parallel."""
    subagents = [create_mock_subagent() for _ in range(10)]

    start = time.perf_counter()
    results = await process_subagents_parallel(subagents, mock_processor)
    duration = time.perf_counter() - start

    # Parallel should be faster than serial
    assert len(results) == 10
    assert duration < 1.0  # With 100ms processor, serial would be 1s+

@pytest.mark.asyncio
async def test_async_session_iteration():
    """Verify async session reads correctly."""
    session = AsyncSession(test_jsonl_path)

    messages = []
    async for msg in session.iter_messages():
        messages.append(msg)

    assert len(messages) > 0
    assert messages[0].timestamp is not None
```

### Integration Tests

```python
def test_early_date_filtering(client):
    """Verify date filtering reduces loaded sessions."""
    # Create sessions with known timestamps
    # Request with narrow date range
    # Verify only matching sessions loaded

def test_parallel_subagents_endpoint(client):
    """Verify subagents endpoint returns correct data."""
    response = client.get(f"/sessions/{uuid}/subagents")
    assert response.status_code == 200
    assert "subagents" in response.json()
```

### Performance Benchmarks

```python
def benchmark_parallel_vs_serial():
    """Compare parallel vs serial subagent processing."""
    session = load_session_with_many_subagents()  # 20+ subagents

    # Serial
    start = time.perf_counter()
    serial_result = process_subagents_serial(session)
    serial_time = time.perf_counter() - start

    # Parallel
    start = time.perf_counter()
    parallel_result = asyncio.run(process_subagents_parallel(session))
    parallel_time = time.perf_counter() - start

    print(f"Serial: {serial_time:.2f}s, Parallel: {parallel_time:.2f}s")
    print(f"Speedup: {serial_time/parallel_time:.1f}x")
```

---

## Expected Impact

| Optimization | Scenario | Before | After | Improvement |
|--------------|----------|--------|-------|-------------|
| Early filtering | Analytics with date range | Load all sessions | Load matching only | 50-90% reduction |
| Parallel subagents | Session with 20 subagents | ~2s serial | ~0.5s parallel | 4x speedup |
| Async I/O | Bulk analytics | Blocking | Non-blocking | Better concurrency |
| Batch loading | Project listing | N stat+parse | N stat only | 10x speedup |

---

## Rollback Plan

1. Revert to serial subagent processing
2. Remove async file I/O (use sync version)
3. Remove batch loader, use individual loading
4. Remove file pool
5. No database changes required
6. No API contract changes

---

## Success Criteria

- [ ] Date-filtered analytics loads 50%+ fewer sessions
- [ ] Parallel subagent processing shows 3x+ speedup for 10+ subagents
- [ ] Project listing response time reduced by 50%
- [ ] No increase in memory usage under normal load
- [ ] All existing tests pass
- [ ] No changes to API response format
