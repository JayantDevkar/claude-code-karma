/**
 * Cache Store unit tests
 * Phase 1: Core cache with TTL, pattern matching, and pub/sub
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MemoryCacheStore } from '../../src/walkie-talkie/cache-store.js';
import type { CacheStore } from '../../src/walkie-talkie/types.js';

describe('MemoryCacheStore', () => {
  let cache: MemoryCacheStore;

  beforeEach(() => {
    vi.useFakeTimers();
    cache = new MemoryCacheStore();
  });

  afterEach(() => {
    cache.destroy();
    vi.useRealTimers();
  });

  // ============================================
  // Basic CRUD Operations
  // ============================================

  describe('set/get', () => {
    it('stores and retrieves a value', () => {
      cache.set('key1', 'value1');
      expect(cache.get('key1')).toBe('value1');
    });

    it('stores and retrieves complex objects', () => {
      const obj = { name: 'test', nested: { a: 1, b: [1, 2, 3] } };
      cache.set('obj', obj);
      expect(cache.get('obj')).toEqual(obj);
    });

    it('returns null for non-existent key', () => {
      expect(cache.get('nonexistent')).toBeNull();
    });

    it('overwrites existing key with new value', () => {
      cache.set('key', 'value1');
      cache.set('key', 'value2');
      expect(cache.get('key')).toBe('value2');
    });

    it('overwrites and resets TTL when setting same key', () => {
      cache.set('key', 'value1', 1000);
      vi.advanceTimersByTime(500);
      cache.set('key', 'value2', 1000);
      vi.advanceTimersByTime(800);
      // Should still be valid (800ms into second 1000ms TTL)
      expect(cache.get('key')).toBe('value2');
    });

    it('handles null and undefined values', () => {
      cache.set('null', null);
      cache.set('undefined', undefined);
      expect(cache.get('null')).toBeNull();
      expect(cache.get('undefined')).toBeUndefined(); // undefined is stored as-is
    });
  });

  describe('delete', () => {
    it('removes existing key and returns true', () => {
      cache.set('key', 'value');
      expect(cache.delete('key')).toBe(true);
      expect(cache.get('key')).toBeNull();
    });

    it('returns false for non-existent key', () => {
      expect(cache.delete('nonexistent')).toBe(false);
    });
  });

  describe('clear', () => {
    it('removes all keys from cache', () => {
      cache.set('key1', 'value1');
      cache.set('key2', 'value2');
      cache.set('key3', 'value3');

      cache.clear();

      expect(cache.get('key1')).toBeNull();
      expect(cache.get('key2')).toBeNull();
      expect(cache.get('key3')).toBeNull();
      expect(cache.stats().keys).toBe(0);
    });
  });

  // ============================================
  // TTL and Expiration
  // ============================================

  describe('TTL expiration', () => {
    it('uses default TTL of 5 minutes', () => {
      cache.set('key', 'value');

      // Should exist before 5 minutes
      vi.advanceTimersByTime(299999);
      expect(cache.get('key')).toBe('value');

      // Should be expired after 5 minutes
      vi.advanceTimersByTime(2);
      expect(cache.get('key')).toBeNull();
    });

    it('respects custom TTL', () => {
      cache.set('key', 'value', 1000);

      vi.advanceTimersByTime(999);
      expect(cache.get('key')).toBe('value');

      vi.advanceTimersByTime(2);
      expect(cache.get('key')).toBeNull();
    });

    it('supports infinite TTL with -1', () => {
      cache.set('key', 'value', -1);

      // Advance time far into the future
      vi.advanceTimersByTime(1000 * 60 * 60 * 24 * 365); // 1 year
      expect(cache.get('key')).toBe('value');
    });

    it('lazy-deletes expired keys on get', () => {
      cache.set('key', 'value', 1000);
      vi.advanceTimersByTime(1001);

      // Key should be deleted on access
      expect(cache.get('key')).toBeNull();
      // Verify it's actually deleted from store
      expect(cache.stats().keys).toBe(0);
    });

    it('sweeps expired keys periodically', () => {
      cache.set('key1', 'value1', 1000);
      cache.set('key2', 'value2', 2000);
      cache.set('key3', 'value3', -1); // infinite

      // Advance past first key expiration
      vi.advanceTimersByTime(1500);

      // Advance to trigger cleanup (5 second interval)
      vi.advanceTimersByTime(5000);

      // key1 should be swept, key2 should also be swept, key3 remains
      expect(cache.get('key3')).toBe('value3');
      expect(cache.stats().keys).toBe(1);
    });
  });

  // ============================================
  // Pattern Matching
  // ============================================

  describe('keys() pattern matching', () => {
    beforeEach(() => {
      cache.set('agent:abc:status', 'active', -1);
      cache.set('agent:def:status', 'idle', -1);
      cache.set('agent:abc:config', { timeout: 100 }, -1);
      cache.set('session:123', 'data', -1);
      cache.set('global', 'value', -1);
    });

    it('matches exact keys', () => {
      const keys = cache.keys('agent:abc:status');
      expect(keys).toEqual(['agent:abc:status']);
    });

    it('matches wildcard at end', () => {
      const keys = cache.keys('agent:abc:*');
      expect(keys.sort()).toEqual(['agent:abc:config', 'agent:abc:status']);
    });

    it('matches wildcard in middle', () => {
      const keys = cache.keys('agent:*:status');
      expect(keys.sort()).toEqual(['agent:abc:status', 'agent:def:status']);
    });

    it('wildcard does not match colon (segment boundary)', () => {
      // * should match characters except :
      // agent:*:status should NOT match agent:abc:def:status
      cache.set('agent:abc:def:status', 'nested', -1);

      const keys = cache.keys('agent:*:status');
      expect(keys).not.toContain('agent:abc:def:status');
    });

    it('empty pattern matches all keys', () => {
      const keys = cache.keys('');
      expect(keys.length).toBe(5);
    });

    it('excludes expired keys from results', () => {
      cache.set('expired:key', 'value', 1000);
      vi.advanceTimersByTime(1001);

      const keys = cache.keys('expired:*');
      expect(keys).toEqual([]);
    });

    it('handles special regex characters in pattern', () => {
      cache.set('key.with.dots', 'value', -1);
      cache.set('key+plus', 'value', -1);

      expect(cache.keys('key.with.dots')).toEqual(['key.with.dots']);
      expect(cache.keys('key+plus')).toEqual(['key+plus']);
    });
  });

  describe('getMany() pattern matching', () => {
    beforeEach(() => {
      cache.set('agent:a:status', 'active', -1);
      cache.set('agent:b:status', 'idle', -1);
      cache.set('agent:a:metrics', { cpu: 50 }, -1);
    });

    it('returns map of matching key-value pairs', () => {
      const result = cache.getMany('agent:*:status');

      expect(result.size).toBe(2);
      expect(result.get('agent:a:status')).toBe('active');
      expect(result.get('agent:b:status')).toBe('idle');
    });

    it('returns empty map for no matches', () => {
      const result = cache.getMany('nonexistent:*');
      expect(result.size).toBe(0);
    });

    it('excludes expired keys from results', () => {
      cache.set('temp:1', 'val1', 1000);
      cache.set('temp:2', 'val2', -1);

      vi.advanceTimersByTime(1001);

      const result = cache.getMany('temp:*');
      expect(result.size).toBe(1);
      expect(result.get('temp:2')).toBe('val2');
    });
  });

  // ============================================
  // Pub/Sub
  // ============================================

  describe('subscribe/publish', () => {
    it('notifies subscriber when key is set', () => {
      const callback = vi.fn();
      cache.subscribe('agent:*:status', callback);

      cache.set('agent:abc:status', 'active');

      expect(callback).toHaveBeenCalledWith('agent:abc:status', 'active');
    });

    it('notifies multiple subscribers', () => {
      const cb1 = vi.fn();
      const cb2 = vi.fn();

      cache.subscribe('key', cb1);
      cache.subscribe('key', cb2);

      cache.set('key', 'value');

      expect(cb1).toHaveBeenCalledWith('key', 'value');
      expect(cb2).toHaveBeenCalledWith('key', 'value');
    });

    it('supports pattern subscriptions', () => {
      const callback = vi.fn();
      cache.subscribe('agent:*:status', callback);

      cache.set('agent:1:status', 'active');
      cache.set('agent:2:status', 'idle');
      cache.set('agent:1:config', { x: 1 }); // Should not trigger

      expect(callback).toHaveBeenCalledTimes(2);
      expect(callback).toHaveBeenCalledWith('agent:1:status', 'active');
      expect(callback).toHaveBeenCalledWith('agent:2:status', 'idle');
    });

    it('unsubscribe stops notifications', () => {
      const callback = vi.fn();
      const unsubscribe = cache.subscribe('key', callback);

      cache.set('key', 'value1');
      expect(callback).toHaveBeenCalledTimes(1);

      unsubscribe();
      cache.set('key', 'value2');
      expect(callback).toHaveBeenCalledTimes(1);
    });

    it('empty pattern matches all keys', () => {
      const callback = vi.fn();
      cache.subscribe('', callback);

      cache.set('any:key', 'value1');
      cache.set('another:key', 'value2');

      expect(callback).toHaveBeenCalledTimes(2);
    });

    it('direct publish notifies subscribers', () => {
      const callback = vi.fn();
      cache.subscribe('event:*', callback);

      cache.publish('event:custom', { type: 'test' });

      expect(callback).toHaveBeenCalledWith('event:custom', { type: 'test' });
    });
  });

  describe('subscriber error handling', () => {
    it('continues calling other subscribers when one throws', () => {
      const errorCallback = vi.fn(() => {
        throw new Error('Subscriber error');
      });
      const successCallback = vi.fn();

      cache.subscribe('key', errorCallback);
      cache.subscribe('key', successCallback);

      // Should not throw
      expect(() => cache.set('key', 'value')).not.toThrow();

      expect(errorCallback).toHaveBeenCalled();
      expect(successCallback).toHaveBeenCalled();
    });

    it('logs error when subscriber throws', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const errorCallback = vi.fn(() => {
        throw new Error('Test error');
      });

      cache.subscribe('key', errorCallback);
      cache.set('key', 'value');

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });
  });

  // ============================================
  // Stats
  // ============================================

  describe('stats()', () => {
    it('returns correct key count', () => {
      cache.set('key1', 'value1', -1);
      cache.set('key2', 'value2', -1);
      cache.set('key3', 'value3', -1);

      expect(cache.stats().keys).toBe(3);
    });

    it('excludes expired keys from count', () => {
      cache.set('active', 'value', -1);
      cache.set('expired', 'value', 1000);

      vi.advanceTimersByTime(1001);

      expect(cache.stats().keys).toBe(1);
    });

    it('returns correct subscriber count', () => {
      cache.subscribe('pattern1', () => {});
      cache.subscribe('pattern1', () => {});
      cache.subscribe('pattern2', () => {});

      expect(cache.stats().subscribers).toBe(3);
    });

    it('updates subscriber count after unsubscribe', () => {
      const unsub1 = cache.subscribe('pattern', () => {});
      cache.subscribe('pattern', () => {});

      expect(cache.stats().subscribers).toBe(2);

      unsub1();

      expect(cache.stats().subscribers).toBe(1);
    });

    it('returns memory estimate greater than 0', () => {
      cache.set('key', { data: 'test value with some content' }, -1);

      expect(cache.stats().memoryBytes).toBeGreaterThan(0);
    });
  });

  // ============================================
  // Cleanup and Destroy
  // ============================================

  describe('destroy()', () => {
    it('clears cleanup interval', () => {
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');

      cache.destroy();

      expect(clearIntervalSpy).toHaveBeenCalled();
    });

    it('clears all subscribers', () => {
      cache.subscribe('pattern1', () => {});
      cache.subscribe('pattern2', () => {});

      cache.destroy();

      expect(cache.stats().subscribers).toBe(0);
    });

    it('clears all cached data', () => {
      cache.set('key1', 'value1', -1);
      cache.set('key2', 'value2', -1);

      cache.destroy();

      expect(cache.stats().keys).toBe(0);
    });

    it('prevents further subscriber notifications after destroy', () => {
      const callback = vi.fn();
      cache.subscribe('key', callback);

      cache.destroy();

      // After destroy, subscribers are cleared
      // Direct publish should not notify (no subscribers)
      cache.publish('key', 'value');
      expect(callback).not.toHaveBeenCalled();
    });
  });

  // ============================================
  // Edge Cases
  // ============================================

  describe('edge cases', () => {
    it('handles empty string key', () => {
      cache.set('', 'empty key value', -1);
      expect(cache.get('')).toBe('empty key value');
    });

    it('handles very long keys', () => {
      const longKey = 'a'.repeat(10000);
      cache.set(longKey, 'value', -1);
      expect(cache.get(longKey)).toBe('value');
    });

    it('handles special characters in keys', () => {
      const specialKey = 'key:with:colons:and.dots+plus[brackets]';
      cache.set(specialKey, 'value', -1);
      expect(cache.get(specialKey)).toBe('value');
    });

    it('handles TTL of 0 (immediate expiration)', () => {
      cache.set('key', 'value', 0);
      // Should be expired immediately
      expect(cache.get('key')).toBeNull();
    });

    it('handles concurrent operations', () => {
      // Set multiple keys rapidly
      for (let i = 0; i < 100; i++) {
        cache.set(`key:${i}`, i, -1);
      }

      // Verify all keys exist
      const keys = cache.keys('key:*');
      expect(keys.length).toBe(100);
    });

    it('handles delete during iteration (via getMany)', () => {
      cache.set('key:1', 'v1', -1);
      cache.set('key:2', 'v2', -1);
      cache.set('key:3', 'v3', -1);

      // Delete while getting
      const result = cache.getMany('key:*');
      cache.delete('key:2');

      // Result should have all 3 (captured before delete)
      expect(result.size).toBe(3);

      // Fresh getMany should have only 2
      expect(cache.getMany('key:*').size).toBe(2);
    });
  });

  // ============================================
  // Type Safety
  // ============================================

  describe('type safety', () => {
    it('preserves types through get<T>', () => {
      interface TestData {
        name: string;
        count: number;
      }

      const data: TestData = { name: 'test', count: 42 };
      cache.set('typed', data, -1);

      const retrieved = cache.get<TestData>('typed');
      expect(retrieved?.name).toBe('test');
      expect(retrieved?.count).toBe(42);
    });

    it('returns null with correct typing for missing keys', () => {
      const result = cache.get<{ id: number }>('missing');
      expect(result).toBeNull();
    });
  });
});

describe('CacheStore interface compliance', () => {
  it('MemoryCacheStore implements CacheStore interface', () => {
    const cache: CacheStore = new MemoryCacheStore();

    // Verify all interface methods exist
    expect(typeof cache.set).toBe('function');
    expect(typeof cache.get).toBe('function');
    expect(typeof cache.delete).toBe('function');
    expect(typeof cache.keys).toBe('function');
    expect(typeof cache.getMany).toBe('function');
    expect(typeof cache.subscribe).toBe('function');
    expect(typeof cache.publish).toBe('function');
    expect(typeof cache.clear).toBe('function');
    expect(typeof cache.stats).toBe('function');
    expect(typeof cache.destroy).toBe('function');

    cache.destroy();
  });
});
