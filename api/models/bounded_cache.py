"""
Bounded cache implementations for session and agent metadata.

Provides LRU-based caches with configurable maximum size and optional TTL
to prevent unbounded memory growth in long-running server processes.

Usage:
    from models.bounded_cache import create_bounded_cache, BoundedCacheConfig

    # Create a cache with default settings (1000 entries, 1 hour TTL)
    cache = create_bounded_cache()

    # Create a cache with custom settings
    cache = create_bounded_cache(BoundedCacheConfig(max_size=500, ttl_seconds=1800))
"""

import os
import threading
from dataclasses import dataclass
from typing import Dict, Generic, Optional, TypeVar

from cachetools import TTLCache

# Type variable for cache value type
V = TypeVar("V")


@dataclass(frozen=True)
class BoundedCacheConfig:
    """
    Configuration for bounded caches.

    Attributes:
        max_size: Maximum number of entries in the cache.
                  When exceeded, least-recently-used entries are evicted.
                  Default: 1000 entries
        ttl_seconds: Time-to-live in seconds for cache entries.
                     Entries older than TTL are automatically evicted.
                     Default: 3600 seconds (1 hour)
    """

    max_size: int = 1000
    ttl_seconds: int = 3600


# Default configuration - can be overridden via environment variables
def get_default_config() -> BoundedCacheConfig:
    """
    Get default cache configuration, respecting environment variable overrides.

    Environment variables:
        CLAUDE_KARMA_CACHE_MAX_SIZE: Maximum cache entries (default: 1000)
        CLAUDE_KARMA_CACHE_TTL: TTL in seconds (default: 3600)
    """
    return BoundedCacheConfig(
        max_size=int(os.environ.get("CLAUDE_KARMA_CACHE_MAX_SIZE", "1000")),
        ttl_seconds=int(os.environ.get("CLAUDE_KARMA_CACHE_TTL", "3600")),
    )


class BoundedCache(Generic[V]):
    """
    Thread-safe bounded cache with LRU eviction and TTL expiration.

    This cache automatically:
    - Evicts least-recently-used entries when max_size is exceeded
    - Removes entries that have exceeded their TTL
    - Provides thread-safe access via a lock

    Example:
        cache: BoundedCache[SessionCache] = BoundedCache(config)
        cache["key"] = value
        value = cache.get("key")
    """

    def __init__(self, config: Optional[BoundedCacheConfig] = None):
        """
        Initialize a bounded cache.

        Args:
            config: Cache configuration. Uses environment-based defaults if None.
        """
        self._config = config or get_default_config()
        self._cache: TTLCache = TTLCache(
            maxsize=self._config.max_size,
            ttl=self._config.ttl_seconds,
        )
        self._lock = threading.RLock()

    def __getitem__(self, key: str) -> V:
        """Get an item from the cache. Raises KeyError if not found or expired."""
        with self._lock:
            return self._cache[key]

    def __setitem__(self, key: str, value: V) -> None:
        """Set an item in the cache."""
        with self._lock:
            self._cache[key] = value

    def __delitem__(self, key: str) -> None:
        """Delete an item from the cache."""
        with self._lock:
            del self._cache[key]

    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache (and is not expired)."""
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        """Return number of items in cache."""
        with self._lock:
            return len(self._cache)

    def get(self, key: str, default: Optional[V] = None) -> Optional[V]:
        """Get an item from the cache, returning default if not found."""
        with self._lock:
            return self._cache.get(key, default)

    def pop(self, key: str, default: Optional[V] = None) -> Optional[V]:
        """Remove and return an item from the cache."""
        with self._lock:
            return self._cache.pop(key, default)

    def clear(self) -> None:
        """Remove all items from the cache."""
        with self._lock:
            self._cache.clear()

    @property
    def max_size(self) -> int:
        """Maximum number of entries allowed in the cache."""
        return self._config.max_size

    @property
    def ttl_seconds(self) -> int:
        """Time-to-live in seconds for cache entries."""
        return self._config.ttl_seconds

    def stats(self) -> Dict[str, int]:
        """
        Return cache statistics.

        Returns:
            Dict with 'size', 'max_size', and 'ttl_seconds' keys.
        """
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._config.max_size,
                "ttl_seconds": self._config.ttl_seconds,
            }


def create_bounded_cache(config: Optional[BoundedCacheConfig] = None) -> BoundedCache:
    """
    Factory function to create a bounded cache.

    Args:
        config: Optional cache configuration. Uses defaults if None.

    Returns:
        A new BoundedCache instance.
    """
    return BoundedCache(config)
