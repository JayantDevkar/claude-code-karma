import { Command } from 'commander';
import chalk from 'chalk';
import { startTUI } from './tui/index.js';
import { statusCommand } from './commands/status.js';
import { watchCommand } from './commands/watch.js';
import { reportCommand, syncSessionsToDB } from './commands/report.js';
import { startServer } from './dashboard/index.js';
import { LogWatcher } from './watcher.js';
import { MetricsAggregator, connectWatcherToAggregator } from './aggregator.js';
/**
 * Creates and configures the CLI program
 */
export function createProgram() {
    const program = new Command();
    program
        .name('karma')
        .description('Track Claude Code session metrics and costs')
        .version('0.1.0')
        .option('-v, --verbose', 'Enable verbose output', false)
        .option('-c, --config <path>', 'Path to config file');
    // Status command
    program
        .command('status')
        .description('Show current session metrics')
        .option('-p, --project <name>', 'Show status for specific project')
        .option('-a, --all', 'Show all active sessions')
        .option('-j, --json', 'Output as JSON')
        .action(async (options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        await statusCommand({
            project: options.project,
            all: options.all,
            json: options.json,
        });
    });
    // Watch command with multiple modes
    program
        .command('watch')
        .description('Watch sessions in real-time')
        .option('-u, --ui', 'Launch interactive TUI dashboard', false)
        .option('-p, --project <name>', 'Watch specific project')
        .option('-c, --compact', 'Compact display mode', false)
        .option('-a, --activity-only', 'Show only activity feed', false)
        .action(async (options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        if (options.ui) {
            // Launch TUI dashboard
            startTUI({ sessionId: options.project });
            return;
        }
        // Streaming watch mode
        await watchCommand({
            project: options.project,
            compact: options.compact,
            activityOnly: options.activityOnly,
        });
    });
    // Report command
    program
        .command('report [sessionId]')
        .description('View session history and reports')
        .option('-p, --project <name>', 'Filter by project name')
        .option('-s, --since <date>', 'Show sessions since date (e.g., "7d", "2026-01-01")')
        .option('-l, --limit <number>', 'Number of sessions to show', '10')
        .option('-j, --json', 'Output as JSON')
        .option('--csv', 'Output as CSV')
        .option('--sync', 'Sync current sessions to database first')
        .action(async (sessionId, options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        // Optionally sync before reporting
        if (options.sync) {
            console.log(chalk.dim('Syncing sessions...'));
            await syncSessionsToDB();
        }
        await reportCommand({
            sessionId,
            project: options.project,
            since: options.since,
            limit: parseInt(options.limit, 10),
            json: options.json,
            csv: options.csv,
        });
    });
    // Dashboard command (Phase 5)
    program
        .command('dashboard')
        .description('Launch web dashboard for metrics visualization')
        .option('-p, --port <number>', 'Port to run dashboard on', '3333')
        .option('--no-open', 'Do not open browser automatically')
        .action(async (options, cmd) => {
        const ctx = getContext(cmd);
        const port = parseInt(options.port, 10);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
            console.log(chalk.gray(`Dashboard port: ${port}`));
        }
        // Create watcher and aggregator
        const watcher = new LogWatcher({ processExisting: true });
        const aggregator = new MetricsAggregator();
        connectWatcherToAggregator(watcher, aggregator);
        // Start the watcher
        watcher.watch();
        // Start the dashboard server
        try {
            const server = await startServer({
                port,
                open: options.open,
                watcher,
                aggregator,
            });
            console.log(chalk.green(`\nDashboard running at http://localhost:${port}`));
            console.log(chalk.gray('Press Ctrl+C to stop'));
            // Handle graceful shutdown
            process.on('SIGINT', async () => {
                console.log(chalk.yellow('\nShutting down...'));
                await server.stop();
                watcher.stop();
                process.exit(0);
            });
        }
        catch (error) {
            console.error(chalk.red('Failed to start dashboard:'), error);
            process.exit(1);
        }
    });
    return program;
}
/**
 * Extract command context from parent options
 */
function getContext(cmd) {
    const parent = cmd.parent;
    const opts = parent?.opts() ?? {};
    return {
        verbose: opts.verbose ?? false,
        configPath: opts.config,
    };
}
//# sourceMappingURL=cli.js.map