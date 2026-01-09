/**
 * Memory Cache Store Implementation
 * Phase 1: In-memory cache with TTL, pattern matching, and pub/sub
 */

import type { CacheStore, CacheStats, SubscriberCallback } from './types.js';

/**
 * Internal cache entry with value and expiration
 */
interface CacheEntry {
  value: unknown;
  expiresAt: number; // -1 for infinite
}

/** Default TTL: 5 minutes */
const DEFAULT_TTL_MS = 300000;

/** Cleanup interval: 5 seconds */
const CLEANUP_INTERVAL_MS = 5000;

/**
 * Convert glob pattern to RegExp
 * * matches any characters except :
 * Empty pattern matches all keys
 */
function globToRegex(pattern: string): RegExp {
  if (!pattern) {
    return /^.*$/;
  }

  // Escape special regex chars except *
  const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
  // Replace * with [^:]* (match any chars except colon)
  const regexStr = escaped.replace(/\*/g, '[^:]*');
  return new RegExp(`^${regexStr}$`);
}

/**
 * Estimate memory size of a value in bytes
 * This is a rough approximation for stats purposes
 */
function estimateSize(value: unknown): number {
  if (value === null || value === undefined) {
    return 8;
  }
  if (typeof value === 'boolean') {
    return 4;
  }
  if (typeof value === 'number') {
    return 8;
  }
  if (typeof value === 'string') {
    return value.length * 2; // UTF-16
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value).length * 2;
    } catch {
      return 256; // Default for circular refs etc
    }
  }
  return 64; // Default for functions, symbols, etc
}

/**
 * In-memory cache store implementation
 * Provides key-value storage with TTL, pattern matching, and pub/sub
 */
export class MemoryCacheStore implements CacheStore {
  private store: Map<string, CacheEntry> = new Map();
  private subscribers: Map<string, Set<SubscriberCallback>> = new Map();
  private cleanupInterval: ReturnType<typeof setInterval> | null = null;

  constructor() {
    // Start cleanup interval
    this.cleanupInterval = setInterval(() => {
      this.sweepExpired();
    }, CLEANUP_INTERVAL_MS);
  }

  /**
   * Set a value with optional TTL
   */
  set(key: string, value: unknown, ttlMs: number = DEFAULT_TTL_MS): void {
    const expiresAt = ttlMs === -1 ? -1 : Date.now() + ttlMs;
    this.store.set(key, { value, expiresAt });
    // Notify subscribers
    this.publish(key, value);
  }

  /**
   * Get a value by key (lazy eviction on expired keys)
   */
  get<T>(key: string): T | null {
    const entry = this.store.get(key);
    if (!entry) {
      return null;
    }

    // Check expiration (skip for infinite TTL)
    if (entry.expiresAt !== -1 && Date.now() >= entry.expiresAt) {
      this.store.delete(key);
      return null;
    }

    return entry.value as T;
  }

  /**
   * Delete a key from the cache
   */
  delete(key: string): boolean {
    return this.store.delete(key);
  }

  /**
   * Get all keys matching a pattern
   */
  keys(pattern: string): string[] {
    const regex = globToRegex(pattern);
    const now = Date.now();
    const result: string[] = [];

    for (const [key, entry] of this.store) {
      // Skip expired entries
      if (entry.expiresAt !== -1 && now >= entry.expiresAt) {
        continue;
      }
      if (regex.test(key)) {
        result.push(key);
      }
    }

    return result;
  }

  /**
   * Get multiple values matching a pattern
   */
  getMany(pattern: string): Map<string, unknown> {
    const matchingKeys = this.keys(pattern);
    const result = new Map<string, unknown>();

    for (const key of matchingKeys) {
      const value = this.get(key);
      if (value !== null) {
        result.set(key, value);
      }
    }

    return result;
  }

  /**
   * Subscribe to key changes matching a pattern
   */
  subscribe(pattern: string, cb: SubscriberCallback): () => void {
    if (!this.subscribers.has(pattern)) {
      this.subscribers.set(pattern, new Set());
    }
    this.subscribers.get(pattern)!.add(cb);

    // Return unsubscribe function
    return () => {
      const subs = this.subscribers.get(pattern);
      if (subs) {
        subs.delete(cb);
        if (subs.size === 0) {
          this.subscribers.delete(pattern);
        }
      }
    };
  }

  /**
   * Publish a value change notification to matching subscribers
   */
  publish(key: string, value: unknown): void {
    for (const [pattern, callbacks] of this.subscribers) {
      const regex = globToRegex(pattern);
      if (regex.test(key)) {
        for (const cb of callbacks) {
          try {
            cb(key, value);
          } catch (error) {
            // Log error but continue calling other subscribers
            console.error(`Subscriber error for pattern "${pattern}":`, error);
          }
        }
      }
    }
  }

  /**
   * Clear all keys from the cache
   */
  clear(): void {
    this.store.clear();
  }

  /**
   * Get cache statistics
   */
  stats(): CacheStats {
    const now = Date.now();
    let memoryBytes = 0;
    let validKeys = 0;

    for (const [key, entry] of this.store) {
      // Skip expired entries in count
      if (entry.expiresAt !== -1 && now >= entry.expiresAt) {
        continue;
      }
      validKeys++;
      memoryBytes += key.length * 2; // Key size
      memoryBytes += estimateSize(entry.value);
      memoryBytes += 16; // Overhead for expiresAt and object
    }

    let subscriberCount = 0;
    for (const callbacks of this.subscribers.values()) {
      subscriberCount += callbacks.size;
    }

    return {
      keys: validKeys,
      subscribers: subscriberCount,
      memoryBytes,
    };
  }

  /**
   * Destroy the cache store
   */
  destroy(): void {
    // Clear cleanup interval
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
      this.cleanupInterval = null;
    }

    // Clear all subscribers
    this.subscribers.clear();

    // Clear store
    this.store.clear();
  }

  /**
   * Sweep expired keys (called periodically)
   */
  private sweepExpired(): void {
    const now = Date.now();
    for (const [key, entry] of this.store) {
      if (entry.expiresAt !== -1 && now >= entry.expiresAt) {
        this.store.delete(key);
      }
    }
  }
}
