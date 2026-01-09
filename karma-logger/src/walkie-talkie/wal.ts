/**
 * Write-Ahead Log (WAL) for Cache Persistence
 * Phase 6.1: Append-only log for cache durability
 */

import * as fs from 'fs';
import * as path from 'path';
import * as readline from 'readline';

/**
 * WAL entry representing a cache operation
 */
export interface WALEntry {
  ts: number;           // Unix timestamp ms
  op: 'set' | 'del';    // Operation type
  key: string;          // Cache key
  value?: unknown;      // Value (for 'set')
  ttl?: number;         // TTL in ms (for 'set', -1 for infinite)
}

/**
 * Options for WriteAheadLog
 */
export interface WALOptions {
  fsync?: boolean;      // Whether to fsync after each write (default: false)
}

/**
 * Write-Ahead Log for cache durability
 * Append-only log file with JSON lines format
 */
export class WriteAheadLog {
  private fd: number | null = null;
  private walPath: string;
  private fsync: boolean;

  constructor(walPath: string, options?: WALOptions) {
    this.walPath = walPath;
    this.fsync = options?.fsync ?? false;
  }

  /**
   * Open the WAL file for appending
   * Creates directory and file if they don't exist
   */
  async open(): Promise<void> {
    // Create directory if it doesn't exist
    const dir = path.dirname(this.walPath);
    await fs.promises.mkdir(dir, { recursive: true });

    // Open file for appending
    this.fd = await fs.promises.open(this.walPath, 'a').then(handle => {
      const fd = handle.fd;
      // We need the raw fd, but also need to keep the handle open
      // Store handle reference to prevent GC
      (this as any)._handle = handle;
      return fd;
    });
  }

  /**
   * Append an entry to the WAL
   * @param entry The WAL entry to append
   */
  async append(entry: WALEntry): Promise<void> {
    if (this.fd === null) {
      throw new Error('WAL not open. Call open() first.');
    }

    const line = JSON.stringify(entry) + '\n';
    const buffer = Buffer.from(line, 'utf8');

    await fs.promises.appendFile(this.walPath, buffer);

    if (this.fsync) {
      await fs.promises.open(this.walPath, 'r').then(async (handle) => {
        await handle.sync();
        await handle.close();
      });
    }
  }

  /**
   * Read all entries from the WAL
   * Yields entries one by one, skips corrupted lines with warning
   */
  async *readAll(): AsyncGenerator<WALEntry> {
    // Check if file exists
    if (!this.exists()) {
      return;
    }

    const fileStream = fs.createReadStream(this.walPath, { encoding: 'utf8' });
    const rl = readline.createInterface({
      input: fileStream,
      crlfDelay: Infinity,
    });

    for await (const line of rl) {
      if (!line.trim()) {
        continue; // Skip empty lines
      }

      try {
        const entry = JSON.parse(line) as WALEntry;
        yield entry;
      } catch (error) {
        console.warn(`WAL: Skipping corrupted line: ${line.substring(0, 100)}...`);
      }
    }
  }

  /**
   * Get entries after a specific timestamp
   * @param afterTs Only return entries with ts > afterTs
   */
  async *readAfter(afterTs: number): AsyncGenerator<WALEntry> {
    for await (const entry of this.readAll()) {
      if (entry.ts > afterTs) {
        yield entry;
      }
    }
  }

  /**
   * Truncate the WAL file (used after snapshot)
   */
  async truncate(): Promise<void> {
    // Close current handle if open
    if ((this as any)._handle) {
      await (this as any)._handle.close();
      this.fd = null;
      (this as any)._handle = null;
    }

    // Truncate the file
    await fs.promises.writeFile(this.walPath, '', { encoding: 'utf8' });

    // Reopen if we were open before
    await this.open();
  }

  /**
   * Close the WAL file
   */
  async close(): Promise<void> {
    if ((this as any)._handle) {
      await (this as any)._handle.close();
      this.fd = null;
      (this as any)._handle = null;
    }
  }

  /**
   * Check if WAL file exists
   */
  exists(): boolean {
    try {
      fs.accessSync(this.walPath, fs.constants.F_OK);
      return true;
    } catch {
      return false;
    }
  }
}
