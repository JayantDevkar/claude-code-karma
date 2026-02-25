"""
Base cache infrastructure for Session and Agent metadata caching.

Design Rationale:
- CacheStorageProtocol allows swapping backends (dict for tests, BoundedCache for production)
- BaseCache provides common mtime tracking for automatic cache invalidation
- This abstraction is justified by reuse across SessionCache and AgentCache

Provides a generic caching pattern with:
- File mtime tracking for automatic cache invalidation
- Integration with BoundedCache for LRU eviction and TTL
- Memory-efficient __slots__ usage

This module eliminates code duplication between SessionCache and AgentCache
by providing a common base class and utility functions.

Usage:
    class MyCache(BaseCache):
        __slots__ = ("field1", "field2")

        def __init__(self):
            super().__init__()
            self.field1 = None
            self.field2 = None

        def reset(self):
            self.field1 = None
            self.field2 = None
            super().reset()

    # Create BoundedCache storage
    from .bounded_cache import BoundedCache
    _my_cache: BoundedCache[MyCache] = BoundedCache()

    class MyModel:
        def _get_cache(self) -> MyCache:
            return get_or_create_cache(_my_cache, self.file_path, MyCache)

        def _is_cache_stale(self, cache: MyCache) -> bool:
            return is_cache_stale(cache, self.file_path)
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Protocol, Type, TypeVar

# Type variable for cache classes
C = TypeVar("C", bound="BaseCache")


class CacheStorageProtocol(Protocol[C]):
    """Protocol for cache storage (supports both dict and BoundedCache)."""

    def __contains__(self, key: str) -> bool: ...
    def __getitem__(self, key: str) -> C: ...
    def __setitem__(self, key: str, value: C) -> None: ...
    def get(self, key: str, default: Optional[C] = None) -> Optional[C]: ...
    def pop(self, key: str, default: Optional[C] = None) -> Optional[C]: ...
    def clear(self) -> None: ...


class BaseCache(ABC):
    """
    Base class for file-backed caches with mtime-based invalidation.

    Subclasses must:
    1. Define additional __slots__ for their specific fields
    2. Initialize those fields in __init__ (calling super().__init__())
    3. Implement reset() to reset all fields (calling super().reset())

    Uses __slots__ for memory efficiency - no __dict__ is created.

    Attributes:
        _metadata_loaded: Whether cache has been populated
        _file_mtime: File modification time when cache was populated
    """

    __slots__ = ("_metadata_loaded", "_file_mtime")

    def __init__(self) -> None:
        """Initialize cache tracking fields."""
        self._metadata_loaded: bool = False
        self._file_mtime: Optional[float] = None

    @abstractmethod
    def reset(self) -> None:
        """
        Reset all cache values to initial state.

        Subclasses must call super().reset() to reset base fields.
        """
        self._metadata_loaded = False
        self._file_mtime = None

    @property
    def is_loaded(self) -> bool:
        """Check if cache has been loaded."""
        return self._metadata_loaded

    def mark_loaded(self, file_mtime: Optional[float]) -> None:
        """Mark cache as loaded with the current file mtime."""
        self._metadata_loaded = True
        self._file_mtime = file_mtime


def get_file_mtime(file_path: Path) -> Optional[float]:
    """
    Get file modification time, or None if file doesn't exist.

    Args:
        file_path: Path to the file to check

    Returns:
        Modification time as float, or None if file doesn't exist
    """
    if file_path.exists():
        return file_path.stat().st_mtime
    return None


def is_cache_stale(cache: BaseCache, file_path: Path) -> bool:
    """
    Check if cache is stale (file has been modified since cache was populated).

    Args:
        cache: The cache object to check
        file_path: Path to the backing file

    Returns:
        True if cache should be invalidated
    """
    if not cache._metadata_loaded:
        return False  # Cache not loaded yet, not stale

    current_mtime = get_file_mtime(file_path)
    if current_mtime is None:
        return False  # File doesn't exist

    # Stale if mtime changed or was never recorded
    if cache._file_mtime is None or current_mtime != cache._file_mtime:
        return True

    return False


def get_or_create_cache(
    storage: CacheStorageProtocol[C],
    file_path: Path,
    cache_class: Type[C],
) -> C:
    """
    Get existing cache or create a new one for the given file path.

    Works with both plain dictionaries and BoundedCache instances.

    Args:
        storage: Cache storage (dict or BoundedCache)
        file_path: Path to the backing file (used as cache key)
        cache_class: The cache class to instantiate if not found

    Returns:
        Cache instance for the file path
    """
    cache_key = str(file_path)
    if cache_key not in storage:
        storage[cache_key] = cache_class()
    return storage[cache_key]


def clear_cache(storage: CacheStorageProtocol[C], file_path: Path) -> None:
    """
    Clear cache for a specific file path.

    Works with both plain dictionaries and BoundedCache instances.

    Args:
        storage: Cache storage (dict or BoundedCache)
        file_path: Path to the backing file (used as cache key)
    """
    cache_key = str(file_path)
    storage.pop(cache_key, None)


def clear_all_caches(storage: CacheStorageProtocol[C]) -> None:
    """
    Clear all caches in the storage.

    Works with both plain dictionaries and BoundedCache instances.

    Args:
        storage: Cache storage (dict or BoundedCache)
    """
    storage.clear()
