/**
 * Persistent Cache Store unit tests
 * Phase 6.3: Recovery logic for cache persistence
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';
import { existsSync } from 'fs';
import { PersistentCacheStore, type PersistentCacheOptions } from '../../src/walkie-talkie/persistent-cache.js';
import { SnapshotManager } from '../../src/walkie-talkie/snapshot.js';
import { WriteAheadLog } from '../../src/walkie-talkie/wal.js';

describe('PersistentCacheStore', () => {
  let tempDir: string;
  let walPath: string;
  let snapshotPath: string;
  let cache: PersistentCacheStore;

  beforeEach(async () => {
    // Create temp directory for test files
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'persistent-cache-test-'));
    walPath = path.join(tempDir, 'cache.wal');
    snapshotPath = path.join(tempDir, 'cache.snapshot');
  });

  afterEach(async () => {
    // Clean up cache if exists
    if (cache) {
      await cache.close();
    }

    // Clean up temp directory
    try {
      await fs.rm(tempDir, { recursive: true, force: true });
    } catch {
      // Ignore cleanup errors
    }
  });

  // Helper to create a cache with default options
  function createCache(options?: Partial<PersistentCacheOptions>): PersistentCacheStore {
    cache = new PersistentCacheStore({
      walPath,
      snapshotPath,
      snapshotInterval: 0, // Disable periodic snapshots for tests
      ...options,
    });
    return cache;
  }

  // ============================================
  // Test 1: Restores from snapshot only
  // ============================================

  describe('restore from snapshot only', () => {
    it('restores keys from snapshot when WAL is empty', async () => {
      // Create a snapshot manually
      const snapshotManager = new SnapshotManager(snapshotPath);
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key1', { value: 'value1', expiresAt: null });
      entries.set('key2', { value: { nested: true }, expiresAt: null });
      entries.set('key3', { value: 42, expiresAt: null });
      await snapshotManager.save(entries);

      // Create cache and restore
      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(3);
      expect(stats.walEntriesReplayed).toBe(0);
      expect(cache.get('key1')).toBe('value1');
      expect(cache.get('key2')).toEqual({ nested: true });
      expect(cache.get('key3')).toBe(42);
    });

    it('restores with correct TTL from snapshot', async () => {
      // Create snapshot with entry that expires in the future
      const snapshotManager = new SnapshotManager(snapshotPath);
      const futureExpiry = Date.now() + 60000; // 1 minute from now
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('expiring', { value: 'will-expire', expiresAt: futureExpiry });
      entries.set('infinite', { value: 'forever', expiresAt: null });
      await snapshotManager.save(entries);

      const cache = createCache();
      await cache.restore();

      expect(cache.get('expiring')).toBe('will-expire');
      expect(cache.get('infinite')).toBe('forever');
    });

    it('skips expired entries from snapshot', async () => {
      const snapshotManager = new SnapshotManager(snapshotPath);
      const pastExpiry = Date.now() - 10000; // 10 seconds ago
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('expired', { value: 'should-not-restore', expiresAt: pastExpiry });
      entries.set('valid', { value: 'should-restore', expiresAt: null });
      await snapshotManager.save(entries);

      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(1);
      expect(cache.get('expired')).toBeNull();
      expect(cache.get('valid')).toBe('should-restore');
    });
  });

  // ============================================
  // Test 2: Restores from WAL only
  // ============================================

  describe('restore from WAL only', () => {
    it('restores keys from WAL when no snapshot exists', async () => {
      // Create WAL with entries
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: Date.now(), op: 'set', key: 'key1', value: 'value1', ttl: -1 });
      await wal.append({ ts: Date.now(), op: 'set', key: 'key2', value: 'value2', ttl: -1 });
      await wal.close();

      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(0);
      expect(stats.walEntriesReplayed).toBe(2);
      expect(cache.get('key1')).toBe('value1');
      expect(cache.get('key2')).toBe('value2');
    });

    it('handles delete operations from WAL', async () => {
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: Date.now(), op: 'set', key: 'key1', value: 'value1', ttl: -1 });
      await wal.append({ ts: Date.now() + 1, op: 'del', key: 'key1' });
      await wal.append({ ts: Date.now() + 2, op: 'set', key: 'key2', value: 'value2', ttl: -1 });
      await wal.close();

      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.walEntriesReplayed).toBe(3);
      expect(cache.get('key1')).toBeNull();
      expect(cache.get('key2')).toBe('value2');
    });

    it('recalculates TTL from WAL entries', async () => {
      const now = Date.now();
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      // Entry with 5 minute TTL written 1 minute ago
      await wal.append({ ts: now - 60000, op: 'set', key: 'key1', value: 'value1', ttl: 300000 });
      await wal.close();

      const cache = createCache();
      await cache.restore();

      // Key should still be valid with ~4 minutes remaining
      expect(cache.get('key1')).toBe('value1');
    });

    it('skips expired WAL entries', async () => {
      const now = Date.now();
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      // Entry with 30 second TTL written 1 minute ago - should be expired
      await wal.append({ ts: now - 60000, op: 'set', key: 'expired', value: 'old', ttl: 30000 });
      // Entry with infinite TTL
      await wal.append({ ts: now - 60000, op: 'set', key: 'valid', value: 'new', ttl: -1 });
      await wal.close();

      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.walEntriesReplayed).toBe(2);
      expect(cache.get('expired')).toBeNull();
      expect(cache.get('valid')).toBe('new');
    });
  });

  // ============================================
  // Test 3: Restores from snapshot + WAL
  // ============================================

  describe('restore from snapshot + WAL', () => {
    it('combines snapshot and WAL correctly', async () => {
      // Create snapshot first
      const snapshotManager = new SnapshotManager(snapshotPath);
      const snapshotTime = Date.now() - 10000; // 10 seconds ago
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('from-snapshot', { value: 'snapshot-value', expiresAt: null });
      await snapshotManager.save(entries);

      // Modify the snapshot's meta to have our controlled timestamp
      const snapshotData = await snapshotManager.load();
      snapshotData!.meta.createdAt = snapshotTime;
      await fs.writeFile(snapshotPath, JSON.stringify(snapshotData, null, 2));

      // Create WAL with entries after snapshot
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: snapshotTime + 1000, op: 'set', key: 'from-wal', value: 'wal-value', ttl: -1 });
      await wal.append({ ts: snapshotTime + 2000, op: 'set', key: 'updated', value: 'new-value', ttl: -1 });
      await wal.close();

      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(1);
      expect(stats.walEntriesReplayed).toBe(2);
      expect(cache.get('from-snapshot')).toBe('snapshot-value');
      expect(cache.get('from-wal')).toBe('wal-value');
      expect(cache.get('updated')).toBe('new-value');
    });

    it('WAL delete overrides snapshot entry', async () => {
      const snapshotTime = Date.now() - 10000;
      const snapshotManager = new SnapshotManager(snapshotPath);
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('to-delete', { value: 'should-be-deleted', expiresAt: null });
      await snapshotManager.save(entries);

      // Update snapshot timestamp
      const snapshotData = await snapshotManager.load();
      snapshotData!.meta.createdAt = snapshotTime;
      await fs.writeFile(snapshotPath, JSON.stringify(snapshotData, null, 2));

      // WAL deletes the key
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: snapshotTime + 1000, op: 'del', key: 'to-delete' });
      await wal.close();

      const cache = createCache();
      await cache.restore();

      expect(cache.get('to-delete')).toBeNull();
    });

    it('WAL update overrides snapshot entry', async () => {
      const snapshotTime = Date.now() - 10000;
      const snapshotManager = new SnapshotManager(snapshotPath);
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('to-update', { value: 'old-value', expiresAt: null });
      await snapshotManager.save(entries);

      // Update snapshot timestamp
      const snapshotData = await snapshotManager.load();
      snapshotData!.meta.createdAt = snapshotTime;
      await fs.writeFile(snapshotPath, JSON.stringify(snapshotData, null, 2));

      // WAL updates the key
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: snapshotTime + 1000, op: 'set', key: 'to-update', value: 'new-value', ttl: -1 });
      await wal.close();

      const cache = createCache();
      await cache.restore();

      expect(cache.get('to-update')).toBe('new-value');
    });

    it('ignores WAL entries before snapshot', async () => {
      const snapshotTime = Date.now();
      const snapshotManager = new SnapshotManager(snapshotPath);
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key', { value: 'snapshot-value', expiresAt: null });
      await snapshotManager.save(entries);

      // Update snapshot timestamp
      const snapshotData = await snapshotManager.load();
      snapshotData!.meta.createdAt = snapshotTime;
      await fs.writeFile(snapshotPath, JSON.stringify(snapshotData, null, 2));

      // WAL has entry before snapshot - should be ignored
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: snapshotTime - 5000, op: 'set', key: 'key', value: 'old-wal-value', ttl: -1 });
      await wal.close();

      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.walEntriesReplayed).toBe(0);
      expect(cache.get('key')).toBe('snapshot-value');
    });
  });

  // ============================================
  // Test 4: Handles TTL expiration on restore
  // ============================================

  describe('TTL expiration on restore', () => {
    it('does not restore expired keys from snapshot', async () => {
      const snapshotManager = new SnapshotManager(snapshotPath);
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('expired', { value: 'old', expiresAt: Date.now() - 1000 });
      entries.set('valid', { value: 'good', expiresAt: Date.now() + 60000 });
      entries.set('infinite', { value: 'forever', expiresAt: null });
      await snapshotManager.save(entries);

      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(2);
      expect(cache.get('expired')).toBeNull();
      expect(cache.get('valid')).toBe('good');
      expect(cache.get('infinite')).toBe('forever');
    });

    it('does not restore expired keys from WAL', async () => {
      const now = Date.now();
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      // 5 second TTL, written 10 seconds ago = expired
      await wal.append({ ts: now - 10000, op: 'set', key: 'expired', value: 'old', ttl: 5000 });
      // 60 second TTL, written 10 seconds ago = still valid (50s left)
      await wal.append({ ts: now - 10000, op: 'set', key: 'valid', value: 'good', ttl: 60000 });
      await wal.close();

      const cache = createCache();
      await cache.restore();

      expect(cache.get('expired')).toBeNull();
      expect(cache.get('valid')).toBe('good');
    });

    it('preserves infinite TTL (-1)', async () => {
      const now = Date.now();
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: now - 100000, op: 'set', key: 'infinite', value: 'forever', ttl: -1 });
      await wal.close();

      const cache = createCache();
      await cache.restore();

      expect(cache.get('infinite')).toBe('forever');
    });
  });

  // ============================================
  // Test 5: Handles corrupted WAL entries gracefully
  // ============================================

  describe('handles corrupted WAL entries', () => {
    it('skips corrupted lines and continues', async () => {
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: Date.now(), op: 'set', key: 'good1', value: 'value1', ttl: -1 });
      await wal.close();

      // Append corrupted line directly
      await fs.appendFile(walPath, 'this is not valid json\n');
      await fs.appendFile(walPath, JSON.stringify({ ts: Date.now() + 1, op: 'set', key: 'good2', value: 'value2', ttl: -1 }) + '\n');

      const cache = createCache();
      const stats = await cache.restore();

      // Should have processed 2 valid entries (corrupted line logged but skipped)
      expect(stats.walEntriesReplayed).toBe(2);
      expect(cache.get('good1')).toBe('value1');
      expect(cache.get('good2')).toBe('value2');
    });

    it('handles truncated JSON in WAL', async () => {
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: Date.now(), op: 'set', key: 'good', value: 'value', ttl: -1 });
      await wal.close();

      // Append truncated JSON
      await fs.appendFile(walPath, '{"ts":123,"op":"set","key":"truncated","val\n');

      const cache = createCache();
      const stats = await cache.restore();

      expect(cache.get('good')).toBe('value');
      expect(cache.get('truncated')).toBeNull();
    });
  });

  // ============================================
  // Test 6: Periodic snapshot timer works
  // ============================================

  describe('periodic snapshot timer', () => {
    it('creates snapshots at intervals', async () => {
      // Use a short interval with real timers
      const localCache = createCache({ snapshotInterval: 100 });
      await localCache.restore();

      localCache.set('key1', 'value1', -1);

      // Wait for snapshot interval + some buffer
      await new Promise(resolve => setTimeout(resolve, 200));

      // Check that snapshot was created
      expect(existsSync(snapshotPath)).toBe(true);

      await localCache.close();
    });

    it('does not start timer when interval is 0', async () => {
      const localCache = createCache({ snapshotInterval: 0 });
      await localCache.restore();

      localCache.set('key1', 'value1', -1);

      // Wait a bit
      await new Promise(resolve => setTimeout(resolve, 100));

      // Snapshot should not exist
      expect(existsSync(snapshotPath)).toBe(false);

      await localCache.close();
    });

    it('stops timer on destroy', async () => {
      const localCache = createCache({ snapshotInterval: 100 });
      await localCache.restore();

      localCache.set('key1', 'value1', -1);
      localCache.destroy();

      // Wait for what would have been the snapshot interval
      await new Promise(resolve => setTimeout(resolve, 200));

      // No snapshot should exist since destroyed
      expect(existsSync(snapshotPath)).toBe(false);
    });
  });

  // ============================================
  // Test 7: set() appends to WAL
  // ============================================

  describe('set appends to WAL', () => {
    it('appends set operations to WAL', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);
      cache.set('key2', { nested: true }, 60000);

      // Wait for async WAL writes
      await new Promise(resolve => setTimeout(resolve, 50));

      // Read WAL directly
      const wal = new WriteAheadLog(walPath);
      const entries: any[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(2);
      expect(entries[0].op).toBe('set');
      expect(entries[0].key).toBe('key1');
      expect(entries[0].value).toBe('value1');
      expect(entries[0].ttl).toBe(-1);
      expect(entries[1].key).toBe('key2');
      expect(entries[1].value).toEqual({ nested: true });
      expect(entries[1].ttl).toBe(60000);
    });

    it('uses default TTL when not specified', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key', 'value'); // No TTL specified

      await new Promise(resolve => setTimeout(resolve, 50));

      const wal = new WriteAheadLog(walPath);
      const entries: any[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries[0].ttl).toBe(300000); // Default 5 minutes
    });
  });

  // ============================================
  // Test 8: delete() appends to WAL
  // ============================================

  describe('delete appends to WAL', () => {
    it('appends delete operations to WAL', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);
      cache.delete('key1');

      await new Promise(resolve => setTimeout(resolve, 50));

      const wal = new WriteAheadLog(walPath);
      const entries: any[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(2);
      expect(entries[1].op).toBe('del');
      expect(entries[1].key).toBe('key1');
      expect(entries[1].value).toBeUndefined();
    });

    it('returns correct boolean from delete', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);

      expect(cache.delete('key1')).toBe(true);
      expect(cache.delete('nonexistent')).toBe(false);
    });
  });

  // ============================================
  // Test 9: snapshot() creates snapshot and truncates WAL
  // ============================================

  describe('snapshot creates snapshot and truncates WAL', () => {
    it('creates snapshot with current cache state', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);
      cache.set('key2', 'value2', -1);

      await cache.snapshot();

      // Verify snapshot exists
      expect(existsSync(snapshotPath)).toBe(true);

      // Load and verify snapshot content
      const snapshotManager = new SnapshotManager(snapshotPath);
      const data = await snapshotManager.load();

      expect(data).not.toBeNull();
      expect(data!.meta.keyCount).toBe(2);
    });

    it('truncates WAL after snapshot', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);
      cache.set('key2', 'value2', -1);

      // Wait for WAL writes
      await new Promise(resolve => setTimeout(resolve, 50));

      // Verify WAL has entries
      const walBefore = new WriteAheadLog(walPath);
      let countBefore = 0;
      for await (const _ of walBefore.readAll()) countBefore++;
      expect(countBefore).toBe(2);

      await cache.snapshot();

      // Verify WAL is empty after snapshot
      const walAfter = new WriteAheadLog(walPath);
      let countAfter = 0;
      for await (const _ of walAfter.readAll()) countAfter++;
      expect(countAfter).toBe(0);
    });

    it('new operations append to truncated WAL', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);
      await cache.snapshot();

      cache.set('key2', 'value2', -1);
      await new Promise(resolve => setTimeout(resolve, 50));

      const wal = new WriteAheadLog(walPath);
      const entries: any[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(1);
      expect(entries[0].key).toBe('key2');
    });
  });

  // ============================================
  // Test 10: destroy() closes WAL properly
  // ============================================

  describe('destroy closes WAL properly', () => {
    it('closes WAL on destroy', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);
      cache.destroy();

      // Should not be able to write after destroy
      // The set should work in memory but WAL append will be skipped
      cache.set('key2', 'value2', -1);

      await new Promise(resolve => setTimeout(resolve, 50));

      // Only key1 should be in WAL (key2 was after destroy)
      const wal = new WriteAheadLog(walPath);
      const entries: any[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(1);
      expect(entries[0].key).toBe('key1');
    });

    it('async close() works correctly', async () => {
      const cache = createCache();
      await cache.restore();

      cache.set('key1', 'value1', -1);
      await cache.close();

      // Verify WAL is closed properly
      expect(existsSync(walPath)).toBe(true);
    });

    it('clears subscribers and intervals on destroy', async () => {
      const cache = createCache({ snapshotInterval: 1000 });
      await cache.restore();

      const callback = vi.fn();
      cache.subscribe('*', callback);

      cache.destroy();

      // Stats should show 0 subscribers
      const stats = cache.stats();
      expect(stats.subscribers).toBe(0);
    });
  });

  // ============================================
  // Integration tests
  // ============================================

  describe('integration', () => {
    it('full cycle: set -> snapshot -> restore -> verify', async () => {
      // First cache instance
      let cache1 = createCache();
      await cache1.restore();

      cache1.set('key1', 'value1', -1);
      cache1.set('key2', { nested: 'object' }, 300000);
      cache1.set('key3', [1, 2, 3], -1);

      await cache1.snapshot();
      await cache1.close();

      // New cache instance - should restore from snapshot
      cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(3);
      expect(stats.walEntriesReplayed).toBe(0);
      expect(cache.get('key1')).toBe('value1');
      expect(cache.get('key2')).toEqual({ nested: 'object' });
      expect(cache.get('key3')).toEqual([1, 2, 3]);
    });

    it('full cycle: set -> crash -> restore from WAL', async () => {
      // First cache instance - no snapshot
      let cache1 = createCache();
      await cache1.restore();

      cache1.set('key1', 'value1', -1);
      cache1.set('key2', 'value2', -1);

      // Wait for WAL writes
      await new Promise(resolve => setTimeout(resolve, 50));

      // Simulate crash - just close without snapshot
      await cache1.close();

      // New cache instance - should restore from WAL
      cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(0);
      expect(stats.walEntriesReplayed).toBe(2);
      expect(cache.get('key1')).toBe('value1');
      expect(cache.get('key2')).toBe('value2');
    });

    it('full cycle: snapshot -> more writes -> restore from both', async () => {
      // First cache instance
      let cache1 = createCache();
      await cache1.restore();

      cache1.set('from-snapshot', 'snapshot-value', -1);
      await cache1.snapshot();

      cache1.set('from-wal', 'wal-value', -1);
      await new Promise(resolve => setTimeout(resolve, 50));

      await cache1.close();

      // New cache instance
      cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(1);
      expect(stats.walEntriesReplayed).toBe(1);
      expect(cache.get('from-snapshot')).toBe('snapshot-value');
      expect(cache.get('from-wal')).toBe('wal-value');
    });

    it('handles many operations correctly', async () => {
      let localCache = createCache();
      await localCache.restore();

      // Perform many operations
      for (let i = 0; i < 100; i++) {
        localCache.set(`key${i}`, `value${i}`, -1);
      }

      // Delete some
      for (let i = 0; i < 50; i += 2) {
        localCache.delete(`key${i}`);
      }

      await localCache.snapshot();

      // Wait for all WAL writes
      await new Promise(resolve => setTimeout(resolve, 100));

      // Create new cache and restore
      await localCache.close();
      localCache = createCache();
      await localCache.restore();

      // Verify state
      expect(localCache.get('key0')).toBeNull(); // Deleted
      expect(localCache.get('key1')).toBe('value1'); // Exists
      expect(localCache.get('key2')).toBeNull(); // Deleted
      expect(localCache.get('key99')).toBe('value99'); // Exists
    });
  });

  // ============================================
  // Edge cases
  // ============================================

  describe('edge cases', () => {
    it('handles empty restore (no snapshot, no WAL)', async () => {
      const cache = createCache();
      const stats = await cache.restore();

      expect(stats.keysRestored).toBe(0);
      expect(stats.walEntriesReplayed).toBe(0);
      expect(cache.keys('')).toEqual([]);
    });

    it('handles special characters in keys and values', async () => {
      let localCache = createCache();
      await localCache.restore();

      localCache.set('key:with:colons', 'value1', -1);
      localCache.set('key/with/slashes', 'value2', -1);
      localCache.set('emoji', '🎉', -1);

      await localCache.snapshot();
      await localCache.close();

      localCache = createCache();
      await localCache.restore();

      expect(localCache.get('key:with:colons')).toBe('value1');
      expect(localCache.get('key/with/slashes')).toBe('value2');
      expect(localCache.get('emoji')).toBe('🎉');
    });

    it('handles very large values', async () => {
      let localCache = createCache();
      await localCache.restore();

      const largeValue = 'x'.repeat(100000);
      localCache.set('large', largeValue, -1);

      await localCache.snapshot();
      await localCache.close();

      localCache = createCache();
      await localCache.restore();

      expect(localCache.get('large')).toBe(largeValue);
    });

    it('handles corrupted snapshot gracefully', async () => {
      // Write corrupted snapshot
      await fs.mkdir(path.dirname(snapshotPath), { recursive: true });
      await fs.writeFile(snapshotPath, 'not valid json', 'utf-8');

      // Create WAL with valid data
      const wal = new WriteAheadLog(walPath);
      await wal.open();
      await wal.append({ ts: Date.now(), op: 'set', key: 'key', value: 'value', ttl: -1 });
      await wal.close();

      const cache = createCache();
      const stats = await cache.restore();

      // Should have 0 from snapshot (corrupted), but replay WAL
      expect(stats.keysRestored).toBe(0);
      expect(stats.walEntriesReplayed).toBe(1);
      expect(cache.get('key')).toBe('value');
    });
  });
});
