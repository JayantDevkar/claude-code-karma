/**
 * Error Handling for Karma Logger
 * Phase 7: Polish & Packaging
 */

import chalk from 'chalk';
import { getConfig } from './config.js';

// ============================================
// Error Classes
// ============================================

/**
 * Base error class for Karma Logger
 * Includes user-friendly messages and suggestions
 */
export class KarmaError extends Error {
  constructor(
    message: string,
    public suggestion?: string,
    public debug?: unknown
  ) {
    super(message);
    this.name = 'KarmaError';
  }
}

/**
 * Configuration-related errors
 */
export class ConfigError extends KarmaError {
  constructor(message: string, suggestion?: string, debug?: unknown) {
    super(message, suggestion, debug);
    this.name = 'ConfigError';
  }
}

/**
 * Log discovery/parsing errors
 */
export class LogError extends KarmaError {
  constructor(message: string, suggestion?: string, debug?: unknown) {
    super(message, suggestion, debug);
    this.name = 'LogError';
  }
}

/**
 * Database errors
 */
export class DatabaseError extends KarmaError {
  constructor(message: string, suggestion?: string, debug?: unknown) {
    super(message, suggestion, debug);
    this.name = 'DatabaseError';
  }
}

// ============================================
// Common Error Factories
// ============================================

/**
 * Error when Claude logs directory is not found
 */
export function logsNotFoundError(searchedPath: string): LogError {
  return new LogError(
    'Cannot find Claude logs directory',
    'Make sure Claude Code is installed and has been run at least once',
    { searchedPath }
  );
}

/**
 * Error when no sessions are found
 */
export function noSessionsError(project?: string): LogError {
  const msg = project
    ? `No sessions found for project: ${project}`
    : 'No Claude Code sessions found';

  const suggestion = project
    ? 'Check the project name or run "karma status --all" to see all sessions'
    : 'Start a Claude Code session and try again';

  return new LogError(msg, suggestion);
}

/**
 * Error when session is not found
 */
export function sessionNotFoundError(sessionId: string): LogError {
  return new LogError(
    `Session not found: ${sessionId}`,
    'Run "karma report" to see available sessions'
  );
}

/**
 * Error when config key is invalid
 */
export function invalidConfigKeyError(key: string): ConfigError {
  return new ConfigError(
    `Invalid config key: ${key}`,
    'Run "karma config" to see available options'
  );
}

/**
 * Error when config value is invalid
 */
export function invalidConfigValueError(key: string, value: string): ConfigError {
  return new ConfigError(
    `Invalid value "${value}" for config key "${key}"`,
    `Run "karma config" to see the expected format`
  );
}

/**
 * Error when database operation fails
 */
export function databaseError(operation: string, cause?: unknown): DatabaseError {
  return new DatabaseError(
    `Database error during ${operation}`,
    'Try running "karma report --sync" to rebuild the database',
    cause
  );
}

// ============================================
// Error Handler
// ============================================

/**
 * Format and display an error to the user
 */
export function handleError(error: unknown): never {
  const config = getConfig();

  if (error instanceof KarmaError) {
    console.error(chalk.red(`\nError: ${error.message}`));

    if (error.suggestion) {
      console.error(chalk.yellow(`\nSuggestion: ${error.suggestion}`));
    }

    if (config.debug && error.debug) {
      console.error(chalk.gray('\nDebug info:'));
      console.error(chalk.gray(JSON.stringify(error.debug, null, 2)));
    }
  } else if (error instanceof Error) {
    console.error(chalk.red(`\nError: ${error.message}`));

    if (config.debug) {
      console.error(chalk.gray('\nStack trace:'));
      console.error(chalk.gray(error.stack ?? 'No stack trace available'));
    }
  } else {
    console.error(chalk.red('\nAn unexpected error occurred'));

    if (config.debug) {
      console.error(chalk.gray('\nDebug info:'));
      console.error(chalk.gray(String(error)));
    }
  }

  if (!config.debug) {
    console.error(chalk.dim('\nRun with KARMA_DEBUG=true for more details'));
  }

  process.exit(1);
}

/**
 * Wrap an async command handler with error handling
 */
export function withErrorHandler<T extends unknown[]>(
  fn: (...args: T) => Promise<void>
): (...args: T) => Promise<void> {
  return async (...args: T) => {
    try {
      await fn(...args);
    } catch (error) {
      handleError(error);
    }
  };
}

/**
 * Assert a condition or throw KarmaError
 */
export function assert(
  condition: unknown,
  message: string,
  suggestion?: string
): asserts condition {
  if (!condition) {
    throw new KarmaError(message, suggestion);
  }
}
