/**
 * Write-Ahead Log (WAL) unit tests
 * Phase 6.1: Cache persistence via append-only log
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { WriteAheadLog, type WALEntry } from '../../src/walkie-talkie/wal.js';

describe('WriteAheadLog', () => {
  let tempDir: string;
  let walPath: string;
  let wal: WriteAheadLog;

  beforeEach(async () => {
    // Create temp directory for test files
    tempDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'wal-test-'));
    walPath = path.join(tempDir, 'test.wal');
    wal = new WriteAheadLog(walPath);
  });

  afterEach(async () => {
    // Close WAL if open
    await wal.close();

    // Clean up temp directory
    try {
      await fs.promises.rm(tempDir, { recursive: true, force: true });
    } catch {
      // Ignore cleanup errors
    }
  });

  // ============================================
  // append tests
  // ============================================

  describe('append', () => {
    it('appends set entry to file', async () => {
      await wal.open();

      const entry: WALEntry = {
        ts: Date.now(),
        op: 'set',
        key: 'agent:a1:status',
        value: { state: 'active' },
        ttl: 300000,
      };

      await wal.append(entry);

      // Read file directly to verify
      const content = await fs.promises.readFile(walPath, 'utf8');
      const lines = content.trim().split('\n');
      expect(lines.length).toBe(1);

      const parsed = JSON.parse(lines[0]);
      expect(parsed.op).toBe('set');
      expect(parsed.key).toBe('agent:a1:status');
      expect(parsed.value).toEqual({ state: 'active' });
      expect(parsed.ttl).toBe(300000);
    });

    it('appends del entry to file', async () => {
      await wal.open();

      const entry: WALEntry = {
        ts: Date.now(),
        op: 'del',
        key: 'agent:a1:progress',
      };

      await wal.append(entry);

      // Read file directly to verify
      const content = await fs.promises.readFile(walPath, 'utf8');
      const lines = content.trim().split('\n');
      expect(lines.length).toBe(1);

      const parsed = JSON.parse(lines[0]);
      expect(parsed.op).toBe('del');
      expect(parsed.key).toBe('agent:a1:progress');
      expect(parsed.value).toBeUndefined();
    });

    it('handles concurrent appends', async () => {
      await wal.open();

      // Create multiple entries
      const entries: WALEntry[] = [];
      for (let i = 0; i < 10; i++) {
        entries.push({
          ts: Date.now() + i,
          op: 'set',
          key: `key:${i}`,
          value: `value:${i}`,
          ttl: -1,
        });
      }

      // Append all concurrently
      await Promise.all(entries.map(entry => wal.append(entry)));

      // Read and verify all entries exist
      const content = await fs.promises.readFile(walPath, 'utf8');
      const lines = content.trim().split('\n');
      expect(lines.length).toBe(10);

      // Each line should parse successfully
      const parsedEntries = lines.map(line => JSON.parse(line) as WALEntry);
      const keys = new Set(parsedEntries.map(e => e.key));
      expect(keys.size).toBe(10);
    });

    it('creates directory if missing', async () => {
      const nestedPath = path.join(tempDir, 'nested', 'dir', 'test.wal');
      const nestedWal = new WriteAheadLog(nestedPath);

      await nestedWal.open();

      const entry: WALEntry = {
        ts: Date.now(),
        op: 'set',
        key: 'test',
        value: 'value',
        ttl: -1,
      };

      await nestedWal.append(entry);
      await nestedWal.close();

      // Verify file exists
      const exists = fs.existsSync(nestedPath);
      expect(exists).toBe(true);
    });

    it('throws error if not opened', async () => {
      const entry: WALEntry = {
        ts: Date.now(),
        op: 'set',
        key: 'test',
        value: 'value',
        ttl: -1,
      };

      await expect(wal.append(entry)).rejects.toThrow('WAL not open');
    });

    it('appends multiple entries in order', async () => {
      await wal.open();

      const ts = Date.now();
      await wal.append({ ts: ts + 1, op: 'set', key: 'key1', value: 'v1', ttl: -1 });
      await wal.append({ ts: ts + 2, op: 'set', key: 'key2', value: 'v2', ttl: -1 });
      await wal.append({ ts: ts + 3, op: 'del', key: 'key1' });

      const content = await fs.promises.readFile(walPath, 'utf8');
      const lines = content.trim().split('\n');
      expect(lines.length).toBe(3);

      const entries = lines.map(l => JSON.parse(l) as WALEntry);
      expect(entries[0].key).toBe('key1');
      expect(entries[0].op).toBe('set');
      expect(entries[1].key).toBe('key2');
      expect(entries[2].key).toBe('key1');
      expect(entries[2].op).toBe('del');
    });
  });

  // ============================================
  // readAll tests
  // ============================================

  describe('readAll', () => {
    it('reads all entries in order', async () => {
      await wal.open();

      const ts = Date.now();
      await wal.append({ ts: ts + 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.append({ ts: ts + 2, op: 'set', key: 'k2', value: 'v2', ttl: 300000 });
      await wal.append({ ts: ts + 3, op: 'del', key: 'k1' });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(3);
      expect(entries[0].key).toBe('k1');
      expect(entries[0].op).toBe('set');
      expect(entries[0].value).toBe('v1');
      expect(entries[1].key).toBe('k2');
      expect(entries[1].ttl).toBe(300000);
      expect(entries[2].key).toBe('k1');
      expect(entries[2].op).toBe('del');
    });

    it('skips corrupted lines', async () => {
      await wal.open();

      // Write valid entry
      await wal.append({ ts: 1, op: 'set', key: 'good1', value: 'v1', ttl: -1 });
      await wal.close();

      // Append corrupted line directly
      await fs.promises.appendFile(walPath, 'this is not valid json\n');

      // Append another valid entry
      await fs.promises.appendFile(walPath, JSON.stringify({ ts: 2, op: 'set', key: 'good2', value: 'v2', ttl: -1 }) + '\n');

      // Re-open and read
      wal = new WriteAheadLog(walPath);

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      // Should have both valid entries, skipping the corrupted one
      expect(entries.length).toBe(2);
      expect(entries[0].key).toBe('good1');
      expect(entries[1].key).toBe('good2');
    });

    it('handles empty file', async () => {
      // Create empty file
      await fs.promises.writeFile(walPath, '');

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(0);
    });

    it('handles non-existent file', async () => {
      // Don't create the file, just try to read
      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(0);
    });

    it('handles file with empty lines', async () => {
      await wal.open();

      await wal.append({ ts: 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.close();

      // Add some empty lines
      await fs.promises.appendFile(walPath, '\n\n');
      await fs.promises.appendFile(walPath, JSON.stringify({ ts: 2, op: 'set', key: 'k2', value: 'v2', ttl: -1 }) + '\n');
      await fs.promises.appendFile(walPath, '   \n'); // Whitespace only

      wal = new WriteAheadLog(walPath);

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(2);
    });

    it('handles complex values', async () => {
      await wal.open();

      const complexValue = {
        nested: {
          array: [1, 2, 3],
          object: { a: 'b' },
        },
        unicode: 'Hello \u4e16\u754c',
        special: 'line\nbreak\ttab',
      };

      await wal.append({ ts: 1, op: 'set', key: 'complex', value: complexValue, ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(1);
      expect(entries[0].value).toEqual(complexValue);
    });
  });

  // ============================================
  // readAfter tests
  // ============================================

  describe('readAfter', () => {
    it('returns only entries after timestamp', async () => {
      await wal.open();

      const baseTs = 1000000;
      await wal.append({ ts: baseTs + 100, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.append({ ts: baseTs + 200, op: 'set', key: 'k2', value: 'v2', ttl: -1 });
      await wal.append({ ts: baseTs + 300, op: 'set', key: 'k3', value: 'v3', ttl: -1 });
      await wal.append({ ts: baseTs + 400, op: 'set', key: 'k4', value: 'v4', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAfter(baseTs + 200)) {
        entries.push(entry);
      }

      expect(entries.length).toBe(2);
      expect(entries[0].key).toBe('k3');
      expect(entries[1].key).toBe('k4');
    });

    it('returns empty for future timestamp', async () => {
      await wal.open();

      const ts = Date.now();
      await wal.append({ ts, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.append({ ts: ts + 100, op: 'set', key: 'k2', value: 'v2', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAfter(ts + 1000000)) {
        entries.push(entry);
      }

      expect(entries.length).toBe(0);
    });

    it('returns all entries when timestamp is 0', async () => {
      await wal.open();

      const ts = Date.now();
      await wal.append({ ts, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.append({ ts: ts + 100, op: 'set', key: 'k2', value: 'v2', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAfter(0)) {
        entries.push(entry);
      }

      expect(entries.length).toBe(2);
    });

    it('excludes entry with exact timestamp', async () => {
      await wal.open();

      const ts = 1000;
      await wal.append({ ts, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.append({ ts: ts + 100, op: 'set', key: 'k2', value: 'v2', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAfter(ts)) {
        entries.push(entry);
      }

      // Should only include entry with ts > 1000 (i.e., k2 at 1100)
      expect(entries.length).toBe(1);
      expect(entries[0].key).toBe('k2');
    });
  });

  // ============================================
  // truncate tests
  // ============================================

  describe('truncate', () => {
    it('clears the WAL file', async () => {
      await wal.open();

      await wal.append({ ts: 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.append({ ts: 2, op: 'set', key: 'k2', value: 'v2', ttl: -1 });
      await wal.append({ ts: 3, op: 'set', key: 'k3', value: 'v3', ttl: -1 });

      // Verify entries exist
      let entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }
      expect(entries.length).toBe(3);

      // Truncate
      await wal.truncate();

      // Verify file is empty
      entries = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }
      expect(entries.length).toBe(0);

      // Verify file still exists but is empty
      const content = await fs.promises.readFile(walPath, 'utf8');
      expect(content).toBe('');
    });

    it('allows new appends after truncate', async () => {
      await wal.open();

      await wal.append({ ts: 1, op: 'set', key: 'old', value: 'v1', ttl: -1 });
      await wal.truncate();
      await wal.append({ ts: 2, op: 'set', key: 'new', value: 'v2', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(1);
      expect(entries[0].key).toBe('new');
    });

    it('handles truncate on empty file', async () => {
      await wal.open();
      await wal.truncate();

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(0);
    });
  });

  // ============================================
  // close tests
  // ============================================

  describe('close', () => {
    it('closes file descriptor', async () => {
      await wal.open();
      await wal.append({ ts: 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });

      await wal.close();

      // Trying to append after close should fail
      await expect(
        wal.append({ ts: 2, op: 'set', key: 'k2', value: 'v2', ttl: -1 })
      ).rejects.toThrow('WAL not open');
    });

    it('is idempotent', async () => {
      await wal.open();

      // Close multiple times should not throw
      await wal.close();
      await wal.close();
      await wal.close();
    });

    it('allows reopen after close', async () => {
      await wal.open();
      await wal.append({ ts: 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.close();

      // Reopen and append
      await wal.open();
      await wal.append({ ts: 2, op: 'set', key: 'k2', value: 'v2', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(2);
    });
  });

  // ============================================
  // exists tests
  // ============================================

  describe('exists', () => {
    it('returns false for non-existent file', () => {
      expect(wal.exists()).toBe(false);
    });

    it('returns true after open creates file', async () => {
      await wal.open();
      expect(wal.exists()).toBe(true);
    });

    it('returns true for existing file', async () => {
      // Create file manually
      await fs.promises.writeFile(walPath, '');
      expect(wal.exists()).toBe(true);
    });

    it('returns true even after truncate', async () => {
      await wal.open();
      await wal.append({ ts: 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });
      await wal.truncate();
      expect(wal.exists()).toBe(true);
    });
  });

  // ============================================
  // Edge cases
  // ============================================

  describe('edge cases', () => {
    it('handles very long keys and values', async () => {
      await wal.open();

      const longKey = 'k'.repeat(10000);
      const longValue = 'v'.repeat(100000);

      await wal.append({ ts: 1, op: 'set', key: longKey, value: longValue, ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(1);
      expect(entries[0].key).toBe(longKey);
      expect(entries[0].value).toBe(longValue);
    });

    it('handles special characters in keys', async () => {
      await wal.open();

      const specialKeys = [
        'key:with:colons',
        'key/with/slashes',
        'key\\with\\backslashes',
        'key with spaces',
        'key\twith\ttabs',
        'key"with"quotes',
        'key\nwith\nnewlines',
      ];

      for (let i = 0; i < specialKeys.length; i++) {
        await wal.append({ ts: i, op: 'set', key: specialKeys[i], value: i, ttl: -1 });
      }

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(specialKeys.length);
      for (let i = 0; i < specialKeys.length; i++) {
        expect(entries[i].key).toBe(specialKeys[i]);
      }
    });

    it('handles null and undefined in values', async () => {
      await wal.open();

      await wal.append({ ts: 1, op: 'set', key: 'null', value: null, ttl: -1 });
      await wal.append({ ts: 2, op: 'set', key: 'undef', value: undefined, ttl: -1 });
      await wal.append({ ts: 3, op: 'set', key: 'nested', value: { a: null, b: undefined }, ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(3);
      expect(entries[0].value).toBeNull();
      expect(entries[1].value).toBeUndefined();
      // Note: JSON doesn't preserve undefined in objects
      expect(entries[2].value).toEqual({ a: null });
    });

    it('handles TTL values correctly', async () => {
      await wal.open();

      await wal.append({ ts: 1, op: 'set', key: 'infinite', value: 'v', ttl: -1 });
      await wal.append({ ts: 2, op: 'set', key: 'short', value: 'v', ttl: 1000 });
      await wal.append({ ts: 3, op: 'set', key: 'long', value: 'v', ttl: 86400000 }); // 1 day
      await wal.append({ ts: 4, op: 'set', key: 'zero', value: 'v', ttl: 0 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries[0].ttl).toBe(-1);
      expect(entries[1].ttl).toBe(1000);
      expect(entries[2].ttl).toBe(86400000);
      expect(entries[3].ttl).toBe(0);
    });

    it('preserves timestamp precision', async () => {
      await wal.open();

      const ts = 1704700800123; // Specific millisecond timestamp
      await wal.append({ ts, op: 'set', key: 'precise', value: 'v', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries[0].ts).toBe(ts);
    });
  });

  // ============================================
  // fsync option tests
  // ============================================

  describe('fsync option', () => {
    it('respects fsync option when true', async () => {
      const fsyncWal = new WriteAheadLog(walPath, { fsync: true });
      await fsyncWal.open();

      // Should not throw
      await fsyncWal.append({ ts: 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of fsyncWal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(1);
      await fsyncWal.close();
    });

    it('works without fsync (default)', async () => {
      await wal.open();

      await wal.append({ ts: 1, op: 'set', key: 'k1', value: 'v1', ttl: -1 });

      const entries: WALEntry[] = [];
      for await (const entry of wal.readAll()) {
        entries.push(entry);
      }

      expect(entries.length).toBe(1);
    });
  });
});
