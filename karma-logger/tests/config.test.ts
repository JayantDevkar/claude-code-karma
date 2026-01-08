/**
 * Config unit tests
 * Phase 7: Configuration system tests
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import {
  loadConfig,
  saveConfig,
  resetConfig,
  isValidConfigKey,
  parseConfigValue,
  formatConfigValue,
  DEFAULT_CONFIG,
  clearConfigCache,
} from '../src/config.js';

// Use temp directory for tests
const TEST_CONFIG_DIR = path.join(os.tmpdir(), 'karma-test-config');
const TEST_CONFIG_PATH = path.join(TEST_CONFIG_DIR, 'config.json');

// Helper to override config paths for testing
function setupTestEnv() {
  // Clear any cached config
  clearConfigCache();

  // Create test directory
  if (!fs.existsSync(TEST_CONFIG_DIR)) {
    fs.mkdirSync(TEST_CONFIG_DIR, { recursive: true });
  }

  // Remove any existing test config
  if (fs.existsSync(TEST_CONFIG_PATH)) {
    fs.unlinkSync(TEST_CONFIG_PATH);
  }
}

function cleanupTestEnv() {
  clearConfigCache();
  if (fs.existsSync(TEST_CONFIG_PATH)) {
    fs.unlinkSync(TEST_CONFIG_PATH);
  }
}

describe('config', () => {
  beforeEach(setupTestEnv);
  afterEach(cleanupTestEnv);

  describe('loadConfig', () => {
    it('returns default config when no file exists', () => {
      const config = loadConfig();

      expect(config.logsDir).toBe(DEFAULT_CONFIG.logsDir);
      expect(config.dataDir).toBe(DEFAULT_CONFIG.dataDir);
      expect(config.retentionDays).toBe(30);
      expect(config.defaultProject).toBeNull();
      expect(config.debug).toBe(false);
    });

    it('applies environment variable overrides', () => {
      process.env.KARMA_DEBUG = 'true';

      const config = loadConfig();
      expect(config.debug).toBe(true);

      delete process.env.KARMA_DEBUG;
    });

    it('applies KARMA_RETENTION_DAYS env override', () => {
      process.env.KARMA_RETENTION_DAYS = '60';

      const config = loadConfig();
      expect(config.retentionDays).toBe(60);

      delete process.env.KARMA_RETENTION_DAYS;
    });
  });

  describe('isValidConfigKey', () => {
    it('returns true for valid keys', () => {
      expect(isValidConfigKey('logsDir')).toBe(true);
      expect(isValidConfigKey('dataDir')).toBe(true);
      expect(isValidConfigKey('retentionDays')).toBe(true);
      expect(isValidConfigKey('defaultProject')).toBe(true);
      expect(isValidConfigKey('debug')).toBe(true);
      expect(isValidConfigKey('pricing')).toBe(true);
    });

    it('returns false for invalid keys', () => {
      expect(isValidConfigKey('invalid')).toBe(false);
      expect(isValidConfigKey('foo')).toBe(false);
      expect(isValidConfigKey('')).toBe(false);
    });
  });

  describe('parseConfigValue', () => {
    it('parses retentionDays as integer', () => {
      expect(parseConfigValue('retentionDays', '30')).toBe(30);
      expect(parseConfigValue('retentionDays', '60')).toBe(60);
    });

    it('throws for invalid retentionDays', () => {
      expect(() => parseConfigValue('retentionDays', 'abc')).toThrow();
      expect(() => parseConfigValue('retentionDays', '0')).toThrow();
      expect(() => parseConfigValue('retentionDays', '-1')).toThrow();
    });

    it('parses debug as boolean', () => {
      expect(parseConfigValue('debug', 'true')).toBe(true);
      expect(parseConfigValue('debug', '1')).toBe(true);
      expect(parseConfigValue('debug', 'false')).toBe(false);
      expect(parseConfigValue('debug', '0')).toBe(false);
    });

    it('throws for invalid debug value', () => {
      expect(() => parseConfigValue('debug', 'yes')).toThrow();
      expect(() => parseConfigValue('debug', 'no')).toThrow();
    });

    it('parses defaultProject as string or null', () => {
      expect(parseConfigValue('defaultProject', 'myproject')).toBe('myproject');
      expect(parseConfigValue('defaultProject', '')).toBeNull();
    });

    it('throws for pricing key (requires subkey)', () => {
      expect(() => parseConfigValue('pricing', '{}')).toThrow();
    });
  });

  describe('formatConfigValue', () => {
    it('formats null as (not set)', () => {
      expect(formatConfigValue(null)).toBe('(not set)');
    });

    it('formats objects as JSON', () => {
      expect(formatConfigValue({ a: 1 })).toBe('{"a":1}');
    });

    it('formats primitives as strings', () => {
      expect(formatConfigValue(true)).toBe('true');
      expect(formatConfigValue(30)).toBe('30');
      expect(formatConfigValue('/path/to/dir')).toBe('/path/to/dir');
    });
  });

  describe('DEFAULT_CONFIG', () => {
    it('has expected default values', () => {
      expect(DEFAULT_CONFIG.retentionDays).toBe(30);
      expect(DEFAULT_CONFIG.debug).toBe(false);
      expect(DEFAULT_CONFIG.defaultProject).toBeNull();
      expect(DEFAULT_CONFIG.pricing).toEqual({});
    });

    it('uses home directory for paths', () => {
      expect(DEFAULT_CONFIG.logsDir).toContain(os.homedir());
      expect(DEFAULT_CONFIG.dataDir).toContain(os.homedir());
    });
  });
});

describe('errors module', () => {
  it('exports error classes', async () => {
    const { KarmaError, ConfigError, LogError, DatabaseError } = await import('../src/errors.js');

    expect(KarmaError).toBeDefined();
    expect(ConfigError).toBeDefined();
    expect(LogError).toBeDefined();
    expect(DatabaseError).toBeDefined();
  });

  it('KarmaError has suggestion and debug', async () => {
    const { KarmaError } = await import('../src/errors.js');

    const error = new KarmaError('Test error', 'Try this', { debug: 'info' });

    expect(error.message).toBe('Test error');
    expect(error.suggestion).toBe('Try this');
    expect(error.debug).toEqual({ debug: 'info' });
    expect(error.name).toBe('KarmaError');
  });

  it('error factories create proper errors', async () => {
    const {
      logsNotFoundError,
      noSessionsError,
      sessionNotFoundError,
      invalidConfigKeyError,
    } = await import('../src/errors.js');

    const logsError = logsNotFoundError('/path');
    expect(logsError.name).toBe('LogError');
    expect(logsError.suggestion).toBeDefined();

    const noSessions = noSessionsError();
    expect(noSessions.name).toBe('LogError');

    const noSessionsProject = noSessionsError('myproject');
    expect(noSessionsProject.message).toContain('myproject');

    const notFound = sessionNotFoundError('abc-123');
    expect(notFound.message).toContain('abc-123');

    const invalidKey = invalidConfigKeyError('badkey');
    expect(invalidKey.name).toBe('ConfigError');
    expect(invalidKey.message).toContain('badkey');
  });
});
