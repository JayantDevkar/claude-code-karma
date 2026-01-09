/**
 * Snapshot Manager for Cache Persistence
 * Phase 6.2: Periodic full dumps of cache state for faster recovery
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import { existsSync } from 'fs';

/**
 * Metadata about a snapshot
 */
export interface SnapshotMeta {
  /** Unix timestamp ms when snapshot was created */
  createdAt: number;
  /** Number of keys in snapshot */
  keyCount: number;
  /** Snapshot format version (for future compatibility) */
  version: number;
}

/**
 * Entry stored in snapshot
 */
export interface SnapshotEntry {
  key: string;
  value: unknown;
  /** Unix timestamp ms, null for no expiry */
  expiresAt: number | null;
}

/**
 * Snapshot data structure
 */
export interface SnapshotData {
  meta: SnapshotMeta;
  entries: SnapshotEntry[];
}

/** Current snapshot format version */
const SNAPSHOT_VERSION = 1;

/**
 * Manages cache snapshots for persistence
 * Uses atomic write (temp file + rename) for safety
 */
export class SnapshotManager {
  private snapshotPath: string;
  private metaPath: string;

  constructor(snapshotPath: string) {
    this.snapshotPath = snapshotPath;
    this.metaPath = snapshotPath + '.meta';
  }

  /**
   * Save a snapshot of the cache state
   * @param entries Map of key to {value, expiresAt}
   * @returns Snapshot metadata
   */
  async save(entries: Map<string, { value: unknown; expiresAt: number | null }>): Promise<SnapshotMeta> {
    // Create parent directory if missing
    const dir = path.dirname(this.snapshotPath);
    await fs.mkdir(dir, { recursive: true });

    // Build snapshot data
    const meta: SnapshotMeta = {
      createdAt: Date.now(),
      keyCount: entries.size,
      version: SNAPSHOT_VERSION,
    };

    const snapshotEntries: SnapshotEntry[] = [];
    for (const [key, entry] of entries) {
      snapshotEntries.push({
        key,
        value: entry.value,
        expiresAt: entry.expiresAt,
      });
    }

    const snapshotData: SnapshotData = {
      meta,
      entries: snapshotEntries,
    };

    // Atomic write: write to temp file first, then rename
    const tempPath = this.snapshotPath + '.tmp';
    const content = JSON.stringify(snapshotData, null, 2);

    await fs.writeFile(tempPath, content, 'utf-8');

    // Rename to final path (atomic on POSIX)
    await fs.rename(tempPath, this.snapshotPath);

    return meta;
  }

  /**
   * Load the snapshot from disk
   * @returns Snapshot data or null if not found/corrupted
   */
  async load(): Promise<SnapshotData | null> {
    // Check if file exists
    if (!this.exists()) {
      return null;
    }

    try {
      const content = await fs.readFile(this.snapshotPath, 'utf-8');
      const data = JSON.parse(content) as SnapshotData;

      // Basic validation
      if (!data.meta || !Array.isArray(data.entries)) {
        console.warn(`Corrupted snapshot: invalid structure at ${this.snapshotPath}`);
        return null;
      }

      return data;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return null;
      }
      console.warn(`Failed to load snapshot from ${this.snapshotPath}:`, error);
      return null;
    }
  }

  /**
   * Check if snapshot file exists
   */
  exists(): boolean {
    return existsSync(this.snapshotPath);
  }

  /**
   * Delete the snapshot file
   */
  async delete(): Promise<void> {
    try {
      await fs.unlink(this.snapshotPath);
    } catch (error) {
      // Ignore ENOENT - file doesn't exist
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw error;
      }
    }

    // Also try to delete temp file if it exists
    try {
      await fs.unlink(this.snapshotPath + '.tmp');
    } catch {
      // Ignore errors for temp file
    }
  }

  /**
   * Get snapshot path
   */
  getPath(): string {
    return this.snapshotPath;
  }
}
