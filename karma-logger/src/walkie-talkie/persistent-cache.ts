/**
 * Persistent Cache Store Implementation
 * Phase 6.3: Recovery logic combining WAL and Snapshot for durability
 */

import { MemoryCacheStore } from './cache-store.js';
import { WriteAheadLog, type WALEntry } from './wal.js';
import { SnapshotManager, type SnapshotData } from './snapshot.js';

/**
 * Options for PersistentCacheStore
 */
export interface PersistentCacheOptions {
  /** Path to WAL file */
  walPath: string;
  /** Path to snapshot file */
  snapshotPath: string;
  /** Interval in ms for automatic snapshots (default: 60000, 0 to disable) */
  snapshotInterval?: number;
  /** Whether to fsync WAL writes (default: false) */
  fsync?: boolean;
}

/** Default snapshot interval: 60 seconds */
const DEFAULT_SNAPSHOT_INTERVAL_MS = 60000;

/**
 * Persistent cache store that extends MemoryCacheStore with durability
 * Uses Write-Ahead Log for incremental updates and periodic snapshots for fast recovery
 */
export class PersistentCacheStore extends MemoryCacheStore {
  private wal: WriteAheadLog;
  private snapshotManager: SnapshotManager;
  private snapshotInterval: number;
  private snapshotTimer: ReturnType<typeof setInterval> | null = null;
  private walOpened: boolean = false;

  constructor(options: PersistentCacheOptions) {
    super();
    this.wal = new WriteAheadLog(options.walPath, { fsync: options.fsync ?? false });
    this.snapshotManager = new SnapshotManager(options.snapshotPath);
    this.snapshotInterval = options.snapshotInterval ?? DEFAULT_SNAPSHOT_INTERVAL_MS;
  }

  /**
   * Restore cache state from snapshot and WAL
   * Must be called after construction before using the cache
   *
   * Recovery algorithm:
   * 1. Load snapshot if exists
   * 2. Replay WAL entries after snapshot timestamp
   * 3. Recalculate TTLs based on elapsed time (skip expired entries)
   * 4. Start periodic snapshot timer if interval > 0
   *
   * @returns Statistics about restored data
   */
  async restore(): Promise<{ keysRestored: number; walEntriesReplayed: number }> {
    const now = Date.now();
    let keysRestored = 0;
    let walEntriesReplayed = 0;
    let snapshotTimestamp = 0;

    // Step 1: Load snapshot if exists
    const snapshotData = await this.snapshotManager.load();
    if (snapshotData) {
      snapshotTimestamp = snapshotData.meta.createdAt;
      keysRestored = this.restoreFromSnapshot(snapshotData, now);
    }

    // Step 2: Open WAL and replay entries after snapshot
    await this.wal.open();
    this.walOpened = true;

    walEntriesReplayed = await this.replayWAL(snapshotTimestamp, now);

    // Step 3: Start periodic snapshot timer if configured
    if (this.snapshotInterval > 0) {
      this.snapshotTimer = setInterval(() => {
        this.snapshot().catch(err => {
          console.warn('Periodic snapshot failed:', err);
        });
      }, this.snapshotInterval);
    }

    return { keysRestored, walEntriesReplayed };
  }

  /**
   * Restore entries from a snapshot
   * Recalculates TTLs and skips expired entries
   */
  private restoreFromSnapshot(data: SnapshotData, now: number): number {
    let restored = 0;

    for (const entry of data.entries) {
      // Check if entry has expired
      if (entry.expiresAt !== null && entry.expiresAt !== -1 && entry.expiresAt <= now) {
        // Entry has expired, skip it
        continue;
      }

      // Calculate remaining TTL
      let ttl: number;
      if (entry.expiresAt === null || entry.expiresAt === -1) {
        // Infinite TTL (null from snapshot = -1 internally)
        ttl = -1;
      } else {
        // Calculate remaining time
        ttl = entry.expiresAt - now;
      }

      // Restore to memory (bypass WAL logging)
      super.set(entry.key, entry.value, ttl);
      restored++;
    }

    return restored;
  }

  /**
   * Replay WAL entries after a given timestamp
   * Applies operations in order and handles TTL recalculation
   */
  private async replayWAL(afterTimestamp: number, now: number): Promise<number> {
    let replayed = 0;

    for await (const entry of this.wal.readAfter(afterTimestamp)) {
      try {
        this.applyWALEntry(entry, now);
        replayed++;
      } catch (err) {
        // Log but continue on corrupted entries
        console.warn(`Failed to apply WAL entry for key "${entry.key}":`, err);
      }
    }

    return replayed;
  }

  /**
   * Apply a single WAL entry to the in-memory cache
   */
  private applyWALEntry(entry: WALEntry, now: number): void {
    if (entry.op === 'del') {
      // Delete operation - just delete from memory
      super.delete(entry.key);
      return;
    }

    // Set operation - check TTL
    if (entry.ttl !== undefined && entry.ttl !== -1) {
      // Calculate expiration time from original operation
      const originalExpiresAt = entry.ts + entry.ttl;

      // Check if already expired
      if (originalExpiresAt <= now) {
        // Entry has expired, don't restore
        return;
      }

      // Calculate remaining TTL
      const remainingTtl = originalExpiresAt - now;
      super.set(entry.key, entry.value, remainingTtl);
    } else {
      // Infinite TTL
      super.set(entry.key, entry.value, -1);
    }
  }

  /**
   * Create a snapshot of current cache state and truncate WAL
   */
  async snapshot(): Promise<void> {
    // Build entries map for snapshot
    const entries = new Map<string, { value: unknown; expiresAt: number | null }>();
    const now = Date.now();

    // Get all keys (this filters out expired entries)
    const allKeys = this.keys('');

    for (const key of allKeys) {
      const value = this.get(key);
      if (value !== null) {
        // Get expiration info by accessing internal store
        // We need to get the expiresAt value for the snapshot
        // Since we can't access private members, we'll estimate based on current state
        // The safest approach is to re-read and just store the value with null expiry
        // However, for accurate restoration, we need the actual expiresAt

        // For now, we'll store with null expiry (infinite) since we can't access internal state
        // A better approach would be to add a method to get entry metadata
        entries.set(key, { value, expiresAt: this.getExpiresAt(key) });
      }
    }

    // Save snapshot
    await this.snapshotManager.save(entries);

    // Truncate WAL after successful snapshot
    await this.wal.truncate();
  }

  /**
   * Get the expiration timestamp for a key
   * Returns null for infinite TTL, the timestamp otherwise
   * This is a helper that accesses the internal store
   */
  private getExpiresAt(key: string): number | null {
    // Access the internal store via parent class
    // Since store is private, we need to use a workaround
    // We'll access it via the any type - this is not ideal but necessary
    const store = (this as any).store as Map<string, { value: unknown; expiresAt: number }>;
    const entry = store.get(key);
    if (!entry) {
      return null;
    }
    // -1 means infinite TTL, convert to null for snapshot format
    return entry.expiresAt === -1 ? null : entry.expiresAt;
  }

  /**
   * Set a value with optional TTL
   * Appends to WAL asynchronously (fire-and-forget)
   */
  override set(key: string, value: unknown, ttlMs?: number): void {
    // Call parent first
    super.set(key, value, ttlMs);

    // Append to WAL asynchronously if WAL is open
    if (this.walOpened) {
      const walEntry: WALEntry = {
        ts: Date.now(),
        op: 'set',
        key,
        value,
        ttl: ttlMs ?? 300000, // Default 5 minutes, same as MemoryCacheStore
      };

      // Fire-and-forget for performance
      this.wal.append(walEntry).catch(err => {
        console.warn(`Failed to append set operation to WAL for key "${key}":`, err);
      });
    }
  }

  /**
   * Delete a key from the cache
   * Appends to WAL asynchronously (fire-and-forget)
   */
  override delete(key: string): boolean {
    // Call parent first
    const result = super.delete(key);

    // Append to WAL asynchronously if WAL is open
    if (this.walOpened) {
      const walEntry: WALEntry = {
        ts: Date.now(),
        op: 'del',
        key,
      };

      // Fire-and-forget for performance
      this.wal.append(walEntry).catch(err => {
        console.warn(`Failed to append delete operation to WAL for key "${key}":`, err);
      });
    }

    return result;
  }

  /**
   * Destroy the cache store and close WAL
   */
  override destroy(): void {
    // Stop snapshot timer
    if (this.snapshotTimer) {
      clearInterval(this.snapshotTimer);
      this.snapshotTimer = null;
    }

    // Close WAL (fire-and-forget since destroy is sync)
    if (this.walOpened) {
      this.wal.close().catch(err => {
        console.warn('Failed to close WAL:', err);
      });
      this.walOpened = false;
    }

    // Call parent destroy
    super.destroy();
  }

  /**
   * Close the WAL gracefully (async version)
   * Call this before process exit for clean shutdown
   */
  async close(): Promise<void> {
    // Stop snapshot timer
    if (this.snapshotTimer) {
      clearInterval(this.snapshotTimer);
      this.snapshotTimer = null;
    }

    // Close WAL
    if (this.walOpened) {
      await this.wal.close();
      this.walOpened = false;
    }
  }
}
