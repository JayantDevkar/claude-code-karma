# Phase 1: Model-Level Caching Optimizations

**Priority**: Critical
**Complexity**: Low
**Impact**: High
**Risk**: Low

---

## Problem Statement

The Python models (`models/session.py`, `models/agent.py`) perform redundant file I/O operations. Each property access or method call opens and re-parses the JSONL file from disk.

### Verified Issues

| Location | Method | Current Behavior |
|----------|--------|------------------|
| `session.py:150-170` | `iter_messages()` | Opens file on every call |
| `session.py:280-284` | `start_time` | Iterates messages (exits early) |
| `session.py:287-292` | `end_time` | Iterates ALL messages |
| `session.py:386-400` | `slug` | Iterates messages (exits on first match) |
| `session.py:303` | `get_usage_summary()` | Full iteration via `iter_assistant_messages()` |
| `session.py:344` | `get_tools_used()` | Full iteration via `iter_assistant_messages()` |

**Constraint**: Models use `ConfigDict(frozen=True)` which prevents using `@cached_property` directly (frozen models don't allow attribute assignment).

---

## Solution Design

### Strategy A: Lazy-Loaded Internal Cache (Recommended)

Since frozen models prevent attribute mutation, use a mutable container (`dict`) passed at construction time or a module-level weak-reference cache.

#### Implementation: Module-Level Weak Cache

```python
# models/session.py
import weakref
from typing import Optional, Dict, Any

# Module-level cache: maps Session path to computed data
_session_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

class SessionCache:
    """Mutable cache object for a session's computed properties."""
    __slots__ = ('messages', 'start_time', 'end_time', 'slug',
                 'usage_summary', 'tools_used', 'git_branches', 'working_dirs')

    def __init__(self):
        self.messages: Optional[list] = None
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.slug: Optional[str] = None
        self.usage_summary: Optional[TokenUsage] = None
        self.tools_used: Optional[Dict[str, int]] = None
        self.git_branches: Optional[set] = None
        self.working_dirs: Optional[set] = None


class Session(BaseModel):
    # ... existing fields ...

    def _get_cache(self) -> SessionCache:
        """Get or create cache for this session."""
        cache_key = str(self.jsonl_path)
        if cache_key not in _session_cache:
            _session_cache[cache_key] = SessionCache()
        return _session_cache[cache_key]

    def _ensure_messages_loaded(self) -> list:
        """Load messages once and cache them."""
        cache = self._get_cache()
        if cache.messages is None:
            cache.messages = list(self.iter_messages())
        return cache.messages
```

### Strategy B: Single-Pass Metadata Extraction

Extract all metadata (start_time, end_time, slug, usage, tools) in a single pass when first accessed.

#### Implementation: Bulk Metadata Loader

```python
# models/session.py

def _load_metadata(self) -> None:
    """Single-pass extraction of all session metadata."""
    cache = self._get_cache()
    if cache.start_time is not None:  # Already loaded
        return

    first_ts = None
    last_ts = None
    slug = None
    usage = TokenUsage()
    tools: Dict[str, int] = {}
    git_branches: set = set()
    working_dirs: set = set()

    for msg in self.iter_messages():
        # Timestamps
        if first_ts is None:
            first_ts = msg.timestamp
        last_ts = msg.timestamp

        # Slug (from any message)
        if not slug and hasattr(msg, 'slug') and msg.slug:
            slug = msg.slug

        # Usage and tools (assistant messages only)
        if isinstance(msg, AssistantMessage):
            if msg.usage:
                usage = usage + msg.usage
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock):
                    tools[block.name] = tools.get(block.name, 0) + 1

        # Git branches
        if hasattr(msg, 'git_branch') and msg.git_branch:
            git_branches.add(msg.git_branch)

        # Working directories
        if hasattr(msg, 'cwd') and msg.cwd:
            working_dirs.add(msg.cwd)
        elif hasattr(msg, 'workingDirectory') and msg.workingDirectory:
            working_dirs.add(msg.workingDirectory)

    # Store all computed values
    cache.start_time = first_ts
    cache.end_time = last_ts
    cache.slug = slug
    cache.usage_summary = usage
    cache.tools_used = tools
    cache.git_branches = git_branches
    cache.working_dirs = working_dirs
```

### Updated Property Implementations

```python
@property
def start_time(self) -> Optional[datetime]:
    """Get timestamp of first message (cached)."""
    self._load_metadata()
    return self._get_cache().start_time

@property
def end_time(self) -> Optional[datetime]:
    """Get timestamp of last message (cached)."""
    self._load_metadata()
    return self._get_cache().end_time

@property
def slug(self) -> Optional[str]:
    """Get the session's human-readable slug (cached)."""
    self._load_metadata()
    return self._get_cache().slug

def get_usage_summary(self) -> TokenUsage:
    """Get aggregated token usage (cached)."""
    self._load_metadata()
    return self._get_cache().usage_summary or TokenUsage()

def get_tools_used(self) -> Dict[str, int]:
    """Get tool usage counts (cached)."""
    self._load_metadata()
    return self._get_cache().tools_used or {}

def get_git_branches(self) -> set:
    """Get unique git branches (cached)."""
    self._load_metadata()
    return self._get_cache().git_branches or set()

def get_working_directories(self) -> set:
    """Get unique working directories (cached)."""
    self._load_metadata()
    return self._get_cache().working_dirs or set()
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `models/session.py` | Add `SessionCache` class, `_session_cache` dict, `_get_cache()`, `_load_metadata()`, update properties |
| `models/agent.py` | Same pattern for `Agent` class (share `_load_metadata` logic) |

---

## Implementation Steps

### Step 1: Add Cache Infrastructure
1. Create `SessionCache` class with `__slots__` for memory efficiency
2. Add module-level `_session_cache` WeakValueDictionary
3. Implement `_get_cache()` method on Session

### Step 2: Implement Bulk Loader
1. Create `_load_metadata()` that extracts all data in single pass
2. Handle all message types (User, Assistant, FileHistorySnapshot)
3. Aggregate: timestamps, slug, usage, tools, branches, directories

### Step 3: Update Properties
1. Replace `start_time`, `end_time`, `slug` property implementations
2. Replace `get_usage_summary()`, `get_tools_used()` method implementations
3. Replace `get_git_branches()`, `get_working_directories()` method implementations

### Step 4: Apply to Agent Model
1. Create similar `AgentCache` class
2. Implement `_load_metadata()` for Agent
3. Update Agent properties/methods

### Step 5: Add Cache Invalidation Hook
1. Add `clear_cache()` method for testing
2. Add file modification time check for stale cache detection (optional)

---

## Testing Requirements

### Unit Tests

```python
# tests/test_session_cache.py

def test_start_time_cached(session_with_messages):
    """Verify start_time doesn't re-read file."""
    _ = session_with_messages.start_time
    _ = session_with_messages.start_time
    # Assert file opened only once (mock file open)

def test_metadata_single_pass(session_with_messages):
    """Verify all metadata extracted in one iteration."""
    _ = session_with_messages.start_time
    _ = session_with_messages.end_time
    _ = session_with_messages.slug
    _ = session_with_messages.get_usage_summary()
    _ = session_with_messages.get_tools_used()
    # Assert iter_messages called only once

def test_cache_isolation(tmp_path):
    """Verify different sessions have independent caches."""
    session1 = Session.from_path(path1)
    session2 = Session.from_path(path2)
    assert session1.start_time != session2.start_time
```

### Performance Benchmarks

```python
def benchmark_session_properties():
    """Measure improvement in property access time."""
    session = load_large_session()  # 1000+ messages

    # Before: Each call iterates file
    # After: First call caches, subsequent instant

    times = []
    for _ in range(10):
        start = time.perf_counter()
        _ = session.end_time  # Most expensive (full iteration)
        times.append(time.perf_counter() - start)

    # First call should be ~100ms, subsequent ~0.001ms
```

---

## Expected Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| `get_session()` endpoint | ~6 file reads | 1 file read | 6x fewer I/O ops |
| `end_time` repeated access | O(n) per call | O(1) after first | 100x+ for large sessions |
| Memory overhead | None | ~1KB per cached session | Acceptable |

---

## Rollback Plan

1. Remove `SessionCache` class and `_session_cache` dict
2. Revert properties to original implementations
3. No database changes required
4. No API contract changes

---

## Success Criteria

- [ ] All existing tests pass
- [ ] New cache tests pass
- [ ] Benchmark shows >5x improvement for repeated property access
- [ ] Memory usage increase <10% for typical workloads
- [ ] No changes to API response format
