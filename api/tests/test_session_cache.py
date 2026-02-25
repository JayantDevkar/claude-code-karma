"""
Unit tests for Session and Agent caching functionality.

Tests verify that cached properties are computed once and reused,
eliminating redundant file I/O operations.

Also tests the bounded cache behavior (LRU eviction, TTL expiration).
"""

import json
from datetime import datetime
from pathlib import Path

from models import Agent, Session, TokenUsage
from models.agent import AgentCache, _agent_cache
from models.bounded_cache import BoundedCache, BoundedCacheConfig
from models.session import SessionCache, _session_cache

# =============================================================================
# Session Cache Tests
# =============================================================================


class TestSessionCache:
    """Tests for Session caching infrastructure."""

    def test_session_cache_initialization(self):
        """Test SessionCache initializes with all fields None."""
        cache = SessionCache()
        assert cache.start_time is None
        assert cache.end_time is None
        assert cache.slug is None
        assert cache.usage_summary is None
        assert cache.tools_used is None
        assert cache.git_branches is None
        assert cache.working_dirs is None
        assert cache.models_used is None
        assert cache.message_count is None
        assert cache.total_cost is None
        assert cache._metadata_loaded is False

    def test_get_cache_creates_new_cache(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test _get_cache() creates a new cache if none exists."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        cache = session._get_cache()
        assert cache is not None
        assert isinstance(cache, SessionCache)
        assert not cache._metadata_loaded

    def test_get_cache_returns_same_cache(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test _get_cache() returns the same cache for same session."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        cache1 = session._get_cache()
        cache2 = session._get_cache()
        assert cache1 is cache2


class TestSessionMetadataLoading:
    """Tests for Session metadata loading and caching."""

    def test_load_metadata_populates_all_fields(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test _load_metadata() populates all cached fields."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        session._load_metadata()
        cache = session._get_cache()

        assert cache._metadata_loaded is True
        assert cache.start_time is not None
        assert cache.end_time is not None
        assert cache.message_count is not None
        assert cache.message_count > 0

    def test_load_metadata_only_runs_once(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test _load_metadata() only iterates messages once."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # First load
        session._load_metadata()
        cache = session._get_cache()
        assert cache._metadata_loaded is True

        # Capture values after first load
        first_start_time = cache.start_time
        first_end_time = cache.end_time

        # Second load should use cached data (not iterate again)
        session._load_metadata()

        # Cache should have same values (not re-computed)
        assert cache.start_time is first_start_time
        assert cache.end_time is first_end_time
        assert cache._metadata_loaded is True

    def test_properties_trigger_single_load(
        self, temp_claude_dir: Path, sample_session_jsonl: Path
    ):
        """Test accessing multiple properties only loads metadata once."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Initially cache should not be loaded
        cache = session._get_cache()
        assert cache._metadata_loaded is False

        # Access first property - this triggers load
        _ = session.start_time
        assert cache._metadata_loaded is True

        # Capture initial values
        initial_start = cache.start_time
        initial_end = cache.end_time

        # Access all other properties - should use same cached data
        _ = session.end_time
        _ = session.slug
        _ = session.message_count
        _ = session.get_usage_summary()
        _ = session.get_tools_used()
        _ = session.get_git_branches()
        _ = session.get_working_directories()
        _ = session.get_models_used()
        _ = session.get_total_cost()

        # Cache should still reference same objects (not re-computed)
        assert cache.start_time is initial_start
        assert cache.end_time is initial_end


class TestSessionCacheIsolation:
    """Tests for cache isolation between different sessions."""

    def test_different_sessions_have_different_caches(
        self, temp_project_dir: Path, temp_claude_dir: Path
    ):
        """Test that different sessions have independent caches."""
        Session.clear_all_caches()

        # Create two session files
        session1_path = temp_project_dir / "session-1.jsonl"
        session2_path = temp_project_dir / "session-2.jsonl"

        session1_data = {
            "uuid": "msg-1",
            "timestamp": "2024-01-01T10:00:00Z",
            "type": "user",
            "message": {"role": "user", "content": "Session 1"},
        }
        session2_data = {
            "uuid": "msg-2",
            "timestamp": "2024-01-02T10:00:00Z",
            "type": "user",
            "message": {"role": "user", "content": "Session 2"},
        }

        session1_path.write_text(json.dumps(session1_data))
        session2_path.write_text(json.dumps(session2_data))

        session1 = Session.from_path(session1_path, claude_base_dir=temp_claude_dir)
        session2 = Session.from_path(session2_path, claude_base_dir=temp_claude_dir)

        cache1 = session1._get_cache()
        cache2 = session2._get_cache()

        assert cache1 is not cache2


class TestSessionClearCache:
    """Tests for cache clearing functionality."""

    def test_clear_cache_resets_metadata(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test clear_cache() resets the cache."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Load metadata
        _ = session.start_time
        assert session._get_cache()._metadata_loaded

        # Clear cache
        session.clear_cache()

        # Should be reset (new cache created)
        assert not session._get_cache()._metadata_loaded

    def test_clear_all_caches(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test clear_all_caches() clears all session caches."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Load metadata
        _ = session.start_time
        assert len(_session_cache) > 0

        # Clear all
        Session.clear_all_caches()
        assert len(_session_cache) == 0


class TestSessionCachedProperties:
    """Tests verifying cached property values are correct."""

    def test_cached_start_time(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test start_time returns correct cached value."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        start_time = session.start_time
        assert start_time is not None
        assert isinstance(start_time, datetime)

    def test_cached_end_time(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test end_time returns correct cached value."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        end_time = session.end_time
        assert end_time is not None
        assert isinstance(end_time, datetime)

    def test_cached_message_count(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test message_count returns correct cached value."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        count = session.message_count
        assert count > 0
        assert isinstance(count, int)

    def test_cached_usage_summary(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test get_usage_summary returns correct cached value."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        usage = session.get_usage_summary()
        assert usage is not None
        assert isinstance(usage, TokenUsage)

    def test_cached_tools_used(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test get_tools_used returns correct cached value."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        tools = session.get_tools_used()
        assert tools is not None
        # Counter should be dict-like
        assert hasattr(tools, "items")


# =============================================================================
# Agent Cache Tests
# =============================================================================


class TestAgentCache:
    """Tests for Agent caching infrastructure."""

    def test_agent_cache_initialization(self):
        """Test AgentCache initializes with all fields None."""
        cache = AgentCache()
        assert cache.start_time is None
        assert cache.end_time is None
        assert cache.usage_summary is None
        assert cache.message_count is None
        assert cache._metadata_loaded is False


class TestAgentMetadataLoading:
    """Tests for Agent metadata loading and caching."""

    def test_agent_properties_trigger_single_load(
        self, temp_claude_dir: Path, sample_session_with_subagents: Path
    ):
        """Test accessing multiple Agent properties only loads metadata once."""
        Agent.clear_all_caches()

        # Get first subagent
        session = Session.from_path(sample_session_with_subagents, claude_base_dir=temp_claude_dir)
        subagents = session.list_subagents()
        assert len(subagents) > 0

        agent = subagents[0]

        # Initially cache should not be loaded
        cache = agent._get_cache()
        assert cache._metadata_loaded is False

        # Access first property - this triggers load
        _ = agent.start_time
        assert cache._metadata_loaded is True

        # Capture initial values
        initial_start = cache.start_time
        initial_end = cache.end_time

        # Access all other properties - should use same cached data
        _ = agent.end_time
        _ = agent.message_count
        _ = agent.get_usage_summary()

        # Cache should still reference same objects (not re-computed)
        assert cache.start_time is initial_start
        assert cache.end_time is initial_end


class TestAgentClearCache:
    """Tests for Agent cache clearing."""

    def test_agent_clear_all_caches(
        self, temp_claude_dir: Path, sample_session_with_subagents: Path
    ):
        """Test clear_all_caches() clears all agent caches."""
        Agent.clear_all_caches()

        session = Session.from_path(sample_session_with_subagents, claude_base_dir=temp_claude_dir)
        subagents = session.list_subagents()
        assert len(subagents) > 0

        # Load metadata for first agent
        _ = subagents[0].start_time
        assert len(_agent_cache) > 0

        # Clear all
        Agent.clear_all_caches()
        assert len(_agent_cache) == 0


# =============================================================================
# Bounded Cache Tests
# =============================================================================


class TestBoundedCache:
    """Tests for the BoundedCache implementation."""

    def test_bounded_cache_initialization(self):
        """Test BoundedCache initializes with default config."""
        cache: BoundedCache[str] = BoundedCache()
        assert cache.max_size == 1000  # Default
        assert cache.ttl_seconds == 3600  # Default (1 hour)
        assert len(cache) == 0

    def test_bounded_cache_custom_config(self):
        """Test BoundedCache with custom configuration."""
        config = BoundedCacheConfig(max_size=100, ttl_seconds=60)
        cache: BoundedCache[str] = BoundedCache(config)
        assert cache.max_size == 100
        assert cache.ttl_seconds == 60

    def test_bounded_cache_basic_operations(self):
        """Test basic get/set/delete operations."""
        cache: BoundedCache[str] = BoundedCache()

        # Set
        cache["key1"] = "value1"
        assert "key1" in cache
        assert len(cache) == 1

        # Get
        assert cache["key1"] == "value1"
        assert cache.get("key1") == "value1"
        assert cache.get("nonexistent") is None

        # Delete
        del cache["key1"]
        assert "key1" not in cache
        assert len(cache) == 0

    def test_bounded_cache_lru_eviction(self):
        """Test that LRU eviction occurs when max_size is exceeded."""
        config = BoundedCacheConfig(max_size=3, ttl_seconds=3600)
        cache: BoundedCache[str] = BoundedCache(config)

        # Fill cache to max
        cache["key1"] = "value1"
        cache["key2"] = "value2"
        cache["key3"] = "value3"
        assert len(cache) == 3

        # Access key1 to make it recently used
        _ = cache["key1"]

        # Add new entry - should evict least recently used (key2)
        cache["key4"] = "value4"
        assert len(cache) == 3

        # key1 should still be present (was accessed)
        assert "key1" in cache
        # key4 should be present (just added)
        assert "key4" in cache
        # One of the older keys should be evicted
        evicted_count = sum(1 for k in ["key2", "key3"] if k not in cache)
        assert evicted_count >= 1

    def test_bounded_cache_stats(self):
        """Test cache statistics."""
        config = BoundedCacheConfig(max_size=100, ttl_seconds=300)
        cache: BoundedCache[str] = BoundedCache(config)

        cache["key1"] = "value1"
        cache["key2"] = "value2"

        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 300

    def test_bounded_cache_clear(self):
        """Test cache clear operation."""
        cache: BoundedCache[str] = BoundedCache()

        cache["key1"] = "value1"
        cache["key2"] = "value2"
        assert len(cache) == 2

        cache.clear()
        assert len(cache) == 0

    def test_bounded_cache_pop(self):
        """Test cache pop operation."""
        cache: BoundedCache[str] = BoundedCache()

        cache["key1"] = "value1"
        value = cache.pop("key1")
        assert value == "value1"
        assert "key1" not in cache

        # Pop nonexistent key returns default
        assert cache.pop("nonexistent") is None
        assert cache.pop("nonexistent", "default") == "default"


class TestSessionCacheStats:
    """Tests for session cache statistics."""

    def test_session_get_cache_stats(self, temp_claude_dir: Path, sample_session_jsonl: Path):
        """Test Session.get_cache_stats() returns valid statistics."""
        Session.clear_all_caches()
        session = Session.from_path(sample_session_jsonl, claude_base_dir=temp_claude_dir)

        # Before loading any data
        stats = Session.get_cache_stats()
        assert "size" in stats
        assert "max_size" in stats
        assert "ttl_seconds" in stats
        assert stats["size"] == 0

        # Load metadata to populate cache
        _ = session.start_time

        stats = Session.get_cache_stats()
        assert stats["size"] == 1


class TestAgentCacheStats:
    """Tests for agent cache statistics."""

    def test_agent_get_cache_stats(
        self, temp_claude_dir: Path, sample_session_with_subagents: Path
    ):
        """Test Agent.get_cache_stats() returns valid statistics."""
        Agent.clear_all_caches()

        session = Session.from_path(sample_session_with_subagents, claude_base_dir=temp_claude_dir)
        subagents = session.list_subagents()
        assert len(subagents) > 0

        # Before loading any data
        stats = Agent.get_cache_stats()
        assert stats["size"] == 0

        # Load metadata to populate cache
        _ = subagents[0].start_time

        stats = Agent.get_cache_stats()
        assert stats["size"] == 1


# =============================================================================
# BaseCache Tests
# =============================================================================


class TestBaseCache:
    """Tests for the BaseCache base class and utilities."""

    def test_session_cache_inherits_from_base_cache(self):
        """Test SessionCache inherits from BaseCache."""
        from models.base_cache import BaseCache

        cache = SessionCache()
        assert isinstance(cache, BaseCache)

    def test_agent_cache_inherits_from_base_cache(self):
        """Test AgentCache inherits from BaseCache."""
        from models.base_cache import BaseCache

        cache = AgentCache()
        assert isinstance(cache, BaseCache)

    def test_session_cache_has_base_cache_slots(self):
        """Test SessionCache has _metadata_loaded and _file_mtime attributes."""
        cache = SessionCache()
        assert hasattr(cache, "_metadata_loaded")
        assert hasattr(cache, "_file_mtime")
        assert cache._metadata_loaded is False
        assert cache._file_mtime is None

    def test_agent_cache_has_base_cache_slots(self):
        """Test AgentCache has _metadata_loaded and _file_mtime attributes."""
        cache = AgentCache()
        assert hasattr(cache, "_metadata_loaded")
        assert hasattr(cache, "_file_mtime")
        assert cache._metadata_loaded is False
        assert cache._file_mtime is None

    def test_session_cache_reset(self):
        """Test SessionCache.reset() clears all fields."""
        cache = SessionCache()
        # Set some values
        cache.start_time = None  # simulate loaded state
        cache._metadata_loaded = True
        cache._file_mtime = 12345.0
        cache.message_count = 10

        # Reset
        cache.reset()

        # Verify reset
        assert cache._metadata_loaded is False
        assert cache._file_mtime is None
        assert cache.message_count is None

    def test_agent_cache_reset(self):
        """Test AgentCache.reset() clears all fields."""
        cache = AgentCache()
        # Set some values
        cache._metadata_loaded = True
        cache._file_mtime = 12345.0
        cache.message_count = 5

        # Reset
        cache.reset()

        # Verify reset
        assert cache._metadata_loaded is False
        assert cache._file_mtime is None
        assert cache.message_count is None

    def test_base_cache_is_loaded_property(self):
        """Test is_loaded property reflects _metadata_loaded state."""
        cache = SessionCache()
        assert cache.is_loaded is False

        cache._metadata_loaded = True
        assert cache.is_loaded is True

    def test_base_cache_mark_loaded(self):
        """Test mark_loaded() sets _metadata_loaded and _file_mtime."""
        cache = SessionCache()
        assert cache._metadata_loaded is False
        assert cache._file_mtime is None

        cache.mark_loaded(12345.0)
        assert cache._metadata_loaded is True
        assert cache._file_mtime == 12345.0


class TestBaseCacheUtilities:
    """Tests for base_cache utility functions."""

    def test_get_file_mtime_existing_file(self, temp_project_dir: Path):
        """Test get_file_mtime returns mtime for existing file."""
        from models.base_cache import get_file_mtime

        test_file = temp_project_dir / "test.txt"
        test_file.write_text("test content")

        mtime = get_file_mtime(test_file)
        assert mtime is not None
        assert isinstance(mtime, float)

    def test_get_file_mtime_missing_file(self, temp_project_dir: Path):
        """Test get_file_mtime returns None for missing file."""
        from models.base_cache import get_file_mtime

        missing_file = temp_project_dir / "does_not_exist.txt"
        mtime = get_file_mtime(missing_file)
        assert mtime is None

    def test_is_cache_stale_not_loaded(self, temp_project_dir: Path):
        """Test is_cache_stale returns False for unloaded cache."""
        from models.base_cache import is_cache_stale

        cache = SessionCache()
        test_file = temp_project_dir / "test.jsonl"
        test_file.write_text("{}")

        # Not loaded yet, so not stale
        assert is_cache_stale(cache, test_file) is False

    def test_is_cache_stale_file_modified(self, temp_project_dir: Path):
        """Test is_cache_stale returns True when file modified."""
        import time

        from models.base_cache import get_file_mtime, is_cache_stale

        test_file = temp_project_dir / "test.jsonl"
        test_file.write_text("{}")

        cache = SessionCache()
        cache.mark_loaded(get_file_mtime(test_file))

        # Modify the file
        time.sleep(0.1)  # Ensure mtime changes
        test_file.write_text('{"updated": true}')

        # Should be stale now
        assert is_cache_stale(cache, test_file) is True

    def test_is_cache_stale_file_unchanged(self, temp_project_dir: Path):
        """Test is_cache_stale returns False when file unchanged."""
        from models.base_cache import get_file_mtime, is_cache_stale

        test_file = temp_project_dir / "test.jsonl"
        test_file.write_text("{}")

        cache = SessionCache()
        cache.mark_loaded(get_file_mtime(test_file))

        # File not modified, should not be stale
        assert is_cache_stale(cache, test_file) is False

    def test_get_or_create_cache_creates_new(self, temp_project_dir: Path):
        """Test get_or_create_cache creates new cache if not exists."""
        from models.base_cache import get_or_create_cache

        storage: dict = {}
        test_file = temp_project_dir / "test.jsonl"

        cache = get_or_create_cache(storage, test_file, SessionCache)
        assert isinstance(cache, SessionCache)
        assert str(test_file) in storage

    def test_get_or_create_cache_returns_existing(self, temp_project_dir: Path):
        """Test get_or_create_cache returns existing cache."""
        from models.base_cache import get_or_create_cache

        storage: dict = {}
        test_file = temp_project_dir / "test.jsonl"

        cache1 = get_or_create_cache(storage, test_file, SessionCache)
        cache2 = get_or_create_cache(storage, test_file, SessionCache)
        assert cache1 is cache2

    def test_clear_cache_removes_entry(self, temp_project_dir: Path):
        """Test clear_cache removes cache entry."""
        from models.base_cache import clear_cache, get_or_create_cache

        storage: dict = {}
        test_file = temp_project_dir / "test.jsonl"

        get_or_create_cache(storage, test_file, SessionCache)
        assert str(test_file) in storage

        clear_cache(storage, test_file)
        assert str(test_file) not in storage

    def test_clear_all_caches_empties_storage(self, temp_project_dir: Path):
        """Test clear_all_caches removes all entries."""
        from models.base_cache import clear_all_caches, get_or_create_cache

        storage: dict = {}
        file1 = temp_project_dir / "test1.jsonl"
        file2 = temp_project_dir / "test2.jsonl"

        get_or_create_cache(storage, file1, SessionCache)
        get_or_create_cache(storage, file2, SessionCache)
        assert len(storage) == 2

        clear_all_caches(storage)
        assert len(storage) == 0
