/**
 * Config Command for Karma Logger
 * Phase 7: Polish & Packaging
 */

import chalk from 'chalk';
import {
  loadConfig,
  saveConfig,
  resetConfig,
  isValidConfigKey,
  parseConfigValue,
  formatConfigValue,
  DEFAULT_CONFIG,
  CONFIG_PATH,
  clearConfigCache,
  type KarmaConfig,
} from '../config.js';
import { invalidConfigKeyError, invalidConfigValueError } from '../errors.js';

/**
 * Config command options
 */
export interface ConfigOptions {
  json?: boolean;
}

/**
 * Show current configuration
 */
export async function configShow(options: ConfigOptions): Promise<void> {
  const config = loadConfig();

  if (options.json) {
    console.log(JSON.stringify(config, null, 2));
    return;
  }

  console.log(chalk.bold('\nKarma Configuration\n'));
  console.log(chalk.dim(`Config file: ${CONFIG_PATH}\n`));

  const maxKeyLength = Math.max(...Object.keys(DEFAULT_CONFIG).map(k => k.length));

  for (const [key, value] of Object.entries(config)) {
    const defaultValue = DEFAULT_CONFIG[key as keyof KarmaConfig];
    const isDefault = JSON.stringify(value) === JSON.stringify(defaultValue);

    const keyStr = chalk.cyan(key.padEnd(maxKeyLength + 2));
    const valueStr = formatConfigValue(value);
    const defaultTag = isDefault ? chalk.dim(' (default)') : '';

    console.log(`  ${keyStr} ${valueStr}${defaultTag}`);
  }

  console.log(chalk.dim('\nEnvironment variables:'));
  console.log(chalk.dim('  KARMA_LOGS_DIR, KARMA_DATA_DIR, KARMA_RETENTION_DAYS'));
  console.log(chalk.dim('  KARMA_DEFAULT_PROJECT, KARMA_DEBUG'));
}

/**
 * Set a config value
 */
export async function configSet(
  key: string,
  value: string,
  _options: ConfigOptions
): Promise<void> {
  // Handle nested keys like "pricing.inputTokenCost"
  if (key.startsWith('pricing.')) {
    const pricingKey = key.slice(8);
    const numValue = parseFloat(value);

    if (isNaN(numValue)) {
      throw invalidConfigValueError(key, value);
    }

    const config = loadConfig();
    const pricing = { ...config.pricing, [pricingKey]: numValue };
    saveConfig({ pricing });
    clearConfigCache();

    console.log(chalk.green(`Set ${key} = ${numValue}`));
    return;
  }

  if (!isValidConfigKey(key)) {
    throw invalidConfigKeyError(key);
  }

  try {
    const parsedValue = parseConfigValue(key, value);
    saveConfig({ [key]: parsedValue } as Partial<KarmaConfig>);
    clearConfigCache();

    console.log(chalk.green(`Set ${key} = ${formatConfigValue(parsedValue)}`));
  } catch (error) {
    if (error instanceof Error) {
      throw invalidConfigValueError(key, value);
    }
    throw error;
  }
}

/**
 * Get a single config value
 */
export async function configGet(key: string, options: ConfigOptions): Promise<void> {
  const config = loadConfig();

  // Handle nested keys
  if (key.startsWith('pricing.')) {
    const pricingKey = key.slice(8);
    const value = (config.pricing as Record<string, unknown>)[pricingKey];

    if (options.json) {
      console.log(JSON.stringify({ [key]: value }));
    } else {
      console.log(formatConfigValue(value));
    }
    return;
  }

  if (!isValidConfigKey(key)) {
    throw invalidConfigKeyError(key);
  }

  const value = config[key];

  if (options.json) {
    console.log(JSON.stringify({ [key]: value }));
  } else {
    console.log(formatConfigValue(value));
  }
}

/**
 * Reset configuration to defaults
 */
export async function configReset(_options: ConfigOptions): Promise<void> {
  resetConfig();
  clearConfigCache();
  console.log(chalk.green('Configuration reset to defaults'));
}

/**
 * List available config keys
 */
export async function configList(_options: ConfigOptions): Promise<void> {
  console.log(chalk.bold('\nAvailable configuration keys:\n'));

  const descriptions: Record<keyof KarmaConfig, string> = {
    logsDir: 'Directory where Claude Code stores logs',
    dataDir: 'Directory for karma data (database, cache)',
    retentionDays: 'Days to retain session history',
    defaultProject: 'Default project when none specified',
    debug: 'Enable debug mode for verbose errors',
    pricing: 'Custom pricing overrides (nested object)',
  };

  for (const [key, desc] of Object.entries(descriptions)) {
    const defaultVal = DEFAULT_CONFIG[key as keyof KarmaConfig];
    console.log(`  ${chalk.cyan(key)}`);
    console.log(`    ${desc}`);
    console.log(`    ${chalk.dim(`Default: ${formatConfigValue(defaultVal)}`)}\n`);
  }

  console.log(chalk.dim('Pricing sub-keys:'));
  console.log(chalk.dim('  pricing.inputTokenCost    - Cost per 1M input tokens'));
  console.log(chalk.dim('  pricing.outputTokenCost   - Cost per 1M output tokens'));
  console.log(chalk.dim('  pricing.cacheReadCost     - Cost per 1M cache read tokens'));
  console.log(chalk.dim('  pricing.cacheCreationCost - Cost per 1M cache creation tokens'));
}
