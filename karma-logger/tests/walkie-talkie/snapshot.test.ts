/**
 * Snapshot Manager unit tests
 * Phase 6.2: Cache snapshot persistence for faster recovery
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs/promises';
import * as path from 'path';
import { existsSync } from 'fs';
import { SnapshotManager, type SnapshotData, type SnapshotEntry } from '../../src/walkie-talkie/snapshot.js';

// Test directory for snapshot files
const TEST_DIR = path.join(process.cwd(), 'test-snapshots');

describe('SnapshotManager', () => {
  let snapshotPath: string;
  let manager: SnapshotManager;

  beforeEach(async () => {
    // Create unique test directory for each test
    const testId = Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    snapshotPath = path.join(TEST_DIR, testId, 'snapshot.json');
    manager = new SnapshotManager(snapshotPath);
  });

  afterEach(async () => {
    // Clean up test files
    try {
      await fs.rm(TEST_DIR, { recursive: true, force: true });
    } catch {
      // Ignore cleanup errors
    }
  });

  // ============================================
  // Save Tests
  // ============================================

  describe('save', () => {
    it('saves snapshot to file', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key1', { value: 'value1', expiresAt: 1704700800000 });
      entries.set('key2', { value: { nested: true }, expiresAt: null });

      const meta = await manager.save(entries);

      expect(meta.keyCount).toBe(2);
      expect(meta.version).toBe(1);
      expect(meta.createdAt).toBeGreaterThan(0);
      expect(existsSync(snapshotPath)).toBe(true);
    });

    it('creates directory if missing', async () => {
      const deepPath = path.join(TEST_DIR, 'deep', 'nested', 'dir', 'snapshot.json');
      const deepManager = new SnapshotManager(deepPath);

      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key', { value: 'value', expiresAt: null });

      await deepManager.save(entries);

      expect(existsSync(deepPath)).toBe(true);
    });

    it('uses atomic write (temp + rename)', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key', { value: 'value', expiresAt: null });

      await manager.save(entries);

      // Temp file should not exist after successful save
      expect(existsSync(snapshotPath + '.tmp')).toBe(false);
      // Final file should exist
      expect(existsSync(snapshotPath)).toBe(true);
    });

    it('preserves expiresAt for entries', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      const expiry1 = 1704700800000;
      const expiry2 = null;

      entries.set('expires', { value: 'test', expiresAt: expiry1 });
      entries.set('noexpire', { value: 'test2', expiresAt: expiry2 });

      await manager.save(entries);

      const data = await manager.load();
      expect(data).not.toBeNull();

      const expiresEntry = data!.entries.find(e => e.key === 'expires');
      const noexpireEntry = data!.entries.find(e => e.key === 'noexpire');

      expect(expiresEntry?.expiresAt).toBe(expiry1);
      expect(noexpireEntry?.expiresAt).toBeNull();
    });

    it('handles empty map', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();

      const meta = await manager.save(entries);

      expect(meta.keyCount).toBe(0);
      expect(meta.version).toBe(1);

      const data = await manager.load();
      expect(data).not.toBeNull();
      expect(data!.entries).toEqual([]);
    });

    it('overwrites existing snapshot', async () => {
      const entries1 = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries1.set('key1', { value: 'value1', expiresAt: null });
      await manager.save(entries1);

      const entries2 = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries2.set('key2', { value: 'value2', expiresAt: null });
      entries2.set('key3', { value: 'value3', expiresAt: null });
      await manager.save(entries2);

      const data = await manager.load();
      expect(data!.meta.keyCount).toBe(2);
      expect(data!.entries.find(e => e.key === 'key1')).toBeUndefined();
      expect(data!.entries.find(e => e.key === 'key2')).toBeDefined();
    });
  });

  // ============================================
  // Load Tests
  // ============================================

  describe('load', () => {
    it('loads snapshot correctly', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('agent:a1:status', { value: { state: 'active' }, expiresAt: 1704701100000 });
      entries.set('agent:a2:status', { value: { state: 'completed' }, expiresAt: null });
      await manager.save(entries);

      const data = await manager.load();

      expect(data).not.toBeNull();
      expect(data!.meta.keyCount).toBe(2);
      expect(data!.meta.version).toBe(1);
      expect(data!.entries.length).toBe(2);
    });

    it('returns null for missing file', async () => {
      const result = await manager.load();
      expect(result).toBeNull();
    });

    it('returns null for corrupted JSON', async () => {
      // Create directory and write corrupted JSON
      await fs.mkdir(path.dirname(snapshotPath), { recursive: true });
      await fs.writeFile(snapshotPath, '{ invalid json ]', 'utf-8');

      const result = await manager.load();
      expect(result).toBeNull();
    });

    it('returns null for invalid structure', async () => {
      // Create directory and write invalid structure
      await fs.mkdir(path.dirname(snapshotPath), { recursive: true });
      await fs.writeFile(snapshotPath, JSON.stringify({ foo: 'bar' }), 'utf-8');

      const result = await manager.load();
      expect(result).toBeNull();
    });

    it('returns null for missing entries array', async () => {
      await fs.mkdir(path.dirname(snapshotPath), { recursive: true });
      await fs.writeFile(snapshotPath, JSON.stringify({ meta: { createdAt: 1, keyCount: 0, version: 1 } }), 'utf-8');

      const result = await manager.load();
      expect(result).toBeNull();
    });

    it('preserves all entry data', async () => {
      const complexValue = {
        nested: {
          array: [1, 2, 3],
          object: { a: 'b' },
          nullVal: null,
          boolVal: true,
          numVal: 42.5,
        },
      };

      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('complex', { value: complexValue, expiresAt: 1704700800000 });
      await manager.save(entries);

      const data = await manager.load();
      const entry = data!.entries.find(e => e.key === 'complex');

      expect(entry?.value).toEqual(complexValue);
      expect(entry?.expiresAt).toBe(1704700800000);
    });
  });

  // ============================================
  // Exists Tests
  // ============================================

  describe('exists', () => {
    it('returns true when file exists', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key', { value: 'value', expiresAt: null });
      await manager.save(entries);

      expect(manager.exists()).toBe(true);
    });

    it('returns false when file missing', () => {
      expect(manager.exists()).toBe(false);
    });
  });

  // ============================================
  // Delete Tests
  // ============================================

  describe('delete', () => {
    it('removes snapshot file', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key', { value: 'value', expiresAt: null });
      await manager.save(entries);

      expect(manager.exists()).toBe(true);

      await manager.delete();

      expect(manager.exists()).toBe(false);
    });

    it('handles missing file gracefully', async () => {
      // Should not throw
      await expect(manager.delete()).resolves.toBeUndefined();
    });

    it('cleans up temp file if present', async () => {
      // Create directory and temp file
      await fs.mkdir(path.dirname(snapshotPath), { recursive: true });
      await fs.writeFile(snapshotPath + '.tmp', 'temp content', 'utf-8');

      await manager.delete();

      expect(existsSync(snapshotPath + '.tmp')).toBe(false);
    });
  });

  // ============================================
  // getPath Tests
  // ============================================

  describe('getPath', () => {
    it('returns the snapshot path', () => {
      expect(manager.getPath()).toBe(snapshotPath);
    });
  });

  // ============================================
  // Integration Tests
  // ============================================

  describe('integration', () => {
    it('save then load roundtrip preserves data', async () => {
      // Create test entries with various value types
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();

      entries.set('string', { value: 'hello world', expiresAt: null });
      entries.set('number', { value: 42, expiresAt: 1704700800000 });
      entries.set('boolean', { value: true, expiresAt: null });
      entries.set('null', { value: null, expiresAt: 1704700900000 });
      entries.set('array', { value: [1, 'two', { three: 3 }], expiresAt: null });
      entries.set('object', { value: { nested: { deep: true } }, expiresAt: null });

      // Save
      const savedMeta = await manager.save(entries);
      expect(savedMeta.keyCount).toBe(6);

      // Load
      const data = await manager.load();
      expect(data).not.toBeNull();
      expect(data!.meta.keyCount).toBe(6);

      // Verify each entry
      for (const [key, original] of entries) {
        const loaded = data!.entries.find(e => e.key === key);
        expect(loaded).toBeDefined();
        expect(loaded!.value).toEqual(original.value);
        expect(loaded!.expiresAt).toBe(original.expiresAt);
      }
    });

    it('handles large snapshots (1000+ entries)', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();

      // Create 1500 entries
      for (let i = 0; i < 1500; i++) {
        entries.set(`key:${i}`, {
          value: { index: i, data: `value-${i}`, timestamp: Date.now() },
          expiresAt: i % 2 === 0 ? Date.now() + 60000 : null,
        });
      }

      // Save
      const savedMeta = await manager.save(entries);
      expect(savedMeta.keyCount).toBe(1500);

      // Load
      const data = await manager.load();
      expect(data).not.toBeNull();
      expect(data!.entries.length).toBe(1500);

      // Verify random samples
      const sample100 = data!.entries.find(e => e.key === 'key:100');
      expect(sample100?.value).toEqual({ index: 100, data: 'value-100', timestamp: expect.any(Number) });

      const sample999 = data!.entries.find(e => e.key === 'key:999');
      expect(sample999?.value).toEqual({ index: 999, data: 'value-999', timestamp: expect.any(Number) });
    });

    it('multiple save/load cycles work correctly', async () => {
      // First cycle
      const entries1 = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries1.set('v1', { value: 'version1', expiresAt: null });
      await manager.save(entries1);

      const data1 = await manager.load();
      expect(data1!.entries.find(e => e.key === 'v1')?.value).toBe('version1');

      // Second cycle - different data
      const entries2 = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries2.set('v2', { value: 'version2', expiresAt: null });
      await manager.save(entries2);

      const data2 = await manager.load();
      expect(data2!.entries.find(e => e.key === 'v2')?.value).toBe('version2');
      expect(data2!.entries.find(e => e.key === 'v1')).toBeUndefined();
    });
  });

  // ============================================
  // Edge Cases
  // ============================================

  describe('edge cases', () => {
    it('handles special characters in keys', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('key:with:colons', { value: 'v1', expiresAt: null });
      entries.set('key.with.dots', { value: 'v2', expiresAt: null });
      entries.set('key/with/slashes', { value: 'v3', expiresAt: null });
      entries.set('key with spaces', { value: 'v4', expiresAt: null });
      entries.set('key"with"quotes', { value: 'v5', expiresAt: null });

      await manager.save(entries);
      const data = await manager.load();

      expect(data!.entries.length).toBe(5);
      expect(data!.entries.find(e => e.key === 'key:with:colons')?.value).toBe('v1');
      expect(data!.entries.find(e => e.key === 'key"with"quotes')?.value).toBe('v5');
    });

    it('handles unicode in values', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('unicode', { value: { emoji: '🎉', chinese: '中文', arabic: 'العربية' }, expiresAt: null });

      await manager.save(entries);
      const data = await manager.load();

      const entry = data!.entries.find(e => e.key === 'unicode');
      expect(entry?.value).toEqual({ emoji: '🎉', chinese: '中文', arabic: 'العربية' });
    });

    it('handles very long string values', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      const longString = 'x'.repeat(100000);
      entries.set('long', { value: longString, expiresAt: null });

      await manager.save(entries);
      const data = await manager.load();

      const entry = data!.entries.find(e => e.key === 'long');
      expect(entry?.value).toBe(longString);
    });

    it('handles zero expiry timestamp', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('zero', { value: 'test', expiresAt: 0 });

      await manager.save(entries);
      const data = await manager.load();

      const entry = data!.entries.find(e => e.key === 'zero');
      expect(entry?.expiresAt).toBe(0);
    });

    it('handles negative expiry timestamp', async () => {
      const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
      entries.set('negative', { value: 'test', expiresAt: -1 });

      await manager.save(entries);
      const data = await manager.load();

      const entry = data!.entries.find(e => e.key === 'negative');
      expect(entry?.expiresAt).toBe(-1);
    });
  });
});
