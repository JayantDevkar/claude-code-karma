/**
 * Configuration System for Karma Logger
 * Phase 7: Polish & Packaging
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import type { CostConfig } from './types.js';

// ============================================
// Types
// ============================================

/**
 * Main configuration interface
 */
export interface KarmaConfig {
  /** Directory where Claude Code stores logs. Default: ~/.claude/projects */
  logsDir: string;

  /** Directory for karma data (db, cache). Default: ~/.karma */
  dataDir: string;

  /** Days to retain session history in database. Default: 30 */
  retentionDays: number;

  /** Default project to use when none specified. Default: auto-detect */
  defaultProject: string | null;

  /** Enable debug mode. Default: false */
  debug: boolean;

  /** Custom pricing overrides */
  pricing: Partial<CostConfig>;
}

/**
 * Serializable config (what's stored in file)
 */
export type ConfigFile = Partial<KarmaConfig>;

// ============================================
// Constants
// ============================================

/** Config directory path */
export const CONFIG_DIR = path.join(os.homedir(), '.karma');

/** Config file path */
export const CONFIG_PATH = path.join(CONFIG_DIR, 'config.json');

/** Default configuration values */
export const DEFAULT_CONFIG: KarmaConfig = {
  logsDir: path.join(os.homedir(), '.claude', 'projects'),
  dataDir: CONFIG_DIR,
  retentionDays: 30,
  defaultProject: null,
  debug: false,
  pricing: {},
};

/** Environment variable mappings */
const ENV_MAP: Record<string, keyof KarmaConfig> = {
  KARMA_LOGS_DIR: 'logsDir',
  KARMA_DATA_DIR: 'dataDir',
  KARMA_RETENTION_DAYS: 'retentionDays',
  KARMA_DEFAULT_PROJECT: 'defaultProject',
  KARMA_DEBUG: 'debug',
};

// ============================================
// Config Functions
// ============================================

/**
 * Ensure config directory exists
 */
export function ensureConfigDir(): void {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
}

/**
 * Load configuration from file
 */
export function loadConfigFile(): ConfigFile {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const content = fs.readFileSync(CONFIG_PATH, 'utf-8');
      return JSON.parse(content) as ConfigFile;
    }
  } catch {
    // Invalid JSON, return empty config
  }
  return {};
}

/**
 * Apply environment variable overrides
 */
function applyEnvOverrides(config: KarmaConfig): KarmaConfig {
  const result = { ...config };

  for (const [envVar, configKey] of Object.entries(ENV_MAP)) {
    const value = process.env[envVar];
    if (value !== undefined) {
      switch (configKey) {
        case 'retentionDays':
          result[configKey] = parseInt(value, 10);
          break;
        case 'debug':
          result[configKey] = value === 'true' || value === '1';
          break;
        case 'defaultProject':
          result[configKey] = value || null;
          break;
        default:
          (result as Record<string, unknown>)[configKey] = value;
      }
    }
  }

  return result;
}

/**
 * Load complete configuration with defaults, file, and env overrides
 */
export function loadConfig(): KarmaConfig {
  const fileConfig = loadConfigFile();

  // Merge: defaults <- file <- env
  const merged: KarmaConfig = {
    ...DEFAULT_CONFIG,
    ...fileConfig,
    pricing: {
      ...DEFAULT_CONFIG.pricing,
      ...fileConfig.pricing,
    },
  };

  return applyEnvOverrides(merged);
}

/**
 * Save configuration to file
 */
export function saveConfig(config: ConfigFile): void {
  ensureConfigDir();

  // Load existing config and merge
  const existing = loadConfigFile();
  const merged = {
    ...existing,
    ...config,
    pricing: {
      ...existing.pricing,
      ...config.pricing,
    },
  };

  // Remove default values to keep file minimal
  const toSave: ConfigFile = {};
  for (const [key, value] of Object.entries(merged)) {
    if (key === 'pricing') {
      if (Object.keys(value as object).length > 0) {
        toSave.pricing = value as Partial<CostConfig>;
      }
    } else if (value !== DEFAULT_CONFIG[key as keyof KarmaConfig]) {
      (toSave as Record<string, unknown>)[key] = value;
    }
  }

  fs.writeFileSync(CONFIG_PATH, JSON.stringify(toSave, null, 2) + '\n');
}

/**
 * Reset configuration to defaults
 */
export function resetConfig(): void {
  if (fs.existsSync(CONFIG_PATH)) {
    fs.unlinkSync(CONFIG_PATH);
  }
}

/**
 * Get a single config value
 */
export function getConfigValue<K extends keyof KarmaConfig>(key: K): KarmaConfig[K] {
  const config = loadConfig();
  return config[key];
}

/**
 * Set a single config value
 */
export function setConfigValue<K extends keyof KarmaConfig>(
  key: K,
  value: KarmaConfig[K]
): void {
  saveConfig({ [key]: value } as ConfigFile);
}

/**
 * Validate a config key
 */
export function isValidConfigKey(key: string): key is keyof KarmaConfig {
  return key in DEFAULT_CONFIG;
}

/**
 * Parse config value from string
 */
export function parseConfigValue(key: keyof KarmaConfig, value: string): unknown {
  switch (key) {
    case 'retentionDays':
      const num = parseInt(value, 10);
      if (isNaN(num) || num < 1) {
        throw new Error(`Invalid value for ${key}: must be a positive integer`);
      }
      return num;

    case 'debug':
      if (value === 'true' || value === '1') return true;
      if (value === 'false' || value === '0') return false;
      throw new Error(`Invalid value for ${key}: must be true or false`);

    case 'defaultProject':
      return value || null;

    case 'pricing':
      throw new Error('Use "karma config set pricing.<field> <value>" for pricing');

    default:
      return value;
  }
}

/**
 * Format config value for display
 */
export function formatConfigValue(value: unknown): string {
  if (value === null) return '(not set)';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

// ============================================
// Singleton Config
// ============================================

let _config: KarmaConfig | null = null;

/**
 * Get cached config instance
 */
export function getConfig(): KarmaConfig {
  if (!_config) {
    _config = loadConfig();
  }
  return _config;
}

/**
 * Clear cached config (for testing or after updates)
 */
export function clearConfigCache(): void {
  _config = null;
}
