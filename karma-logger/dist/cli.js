import { Command } from 'commander';
import chalk from 'chalk';
import { startTUI } from './tui/index.js';
import { statusCommand } from './commands/status.js';
import { watchCommand } from './commands/watch.js';
import { reportCommand, syncSessionsToDB } from './commands/report.js';
import { configShow, configSet, configGet, configReset, configList } from './commands/config.js';
import { startServer } from './dashboard/index.js';
import { LogWatcher } from './watcher.js';
import { MetricsAggregator, connectWatcherToAggregator } from './aggregator.js';
import { withErrorHandler } from './errors.js';
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
        .option('-c, --config <path>', 'Path to config file')
        .addHelpText('after', `
Examples:
  $ karma status              Show current session metrics
  $ karma watch               Watch sessions in real-time
  $ karma report --since 7d   View last 7 days of history
  $ karma config              Show configuration

Documentation: https://github.com/anthropics/karma-logger
`);
    // Status command
    program
        .command('status')
        .description('Show current session metrics')
        .option('-p, --project <name>', 'Show status for specific project')
        .option('-a, --all', 'Show all active sessions')
        .option('-j, --json', 'Output as JSON')
        .option('-t, --tree', 'Display agent hierarchy tree')
        .addHelpText('after', `
Examples:
  $ karma status                  Show current project session
  $ karma status --all            Show all active sessions
  $ karma status -p myproject     Show specific project
  $ karma status --json           Output as JSON
  $ karma status --tree           Show agent hierarchy tree
`)
        .action(async (options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        await statusCommand({
            project: options.project,
            all: options.all,
            json: options.json,
            tree: options.tree,
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
        .option('--no-persist', 'Disable automatic persistence to SQLite')
        .addHelpText('after', `
Examples:
  $ karma watch                   Stream mode with live metrics
  $ karma watch --ui              Interactive TUI dashboard
  $ karma watch --compact         Compact streaming view
  $ karma watch --activity-only   Show only tool activity feed
  $ karma watch --no-persist      Disable auto-save to database
`)
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
            persist: options.persist,
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
        .addHelpText('after', `
Examples:
  $ karma report                  List recent sessions
  $ karma report <session-id>     Show details for a session
  $ karma report --since 7d       Sessions from last 7 days
  $ karma report --sync --csv     Sync and export to CSV
`)
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
        // Pre-populate aggregator with recent sessions (for immediate display)
        const { discoverSessions, getSessionAgents } = await import('./discovery.js');
        const { parseSessionFile } = await import('./parser.js');
        const sessions = await discoverSessions();
        const recentSessions = sessions.filter(s => !s.isAgent).slice(0, 10);
        let agentCount = 0;
        for (const session of recentSessions) {
            try {
                // Load main session entries
                const entries = await parseSessionFile(session.filePath);
                for (const entry of entries) {
                    aggregator.processEntry(entry, session);
                }
                // Load agents for this session (with types for better display)
                const agents = await getSessionAgents(session.projectPath, session.sessionId, { includeAgentTypes: true });
                for (const agent of agents) {
                    try {
                        // Register the agent
                        aggregator.registerAgent(agent, session);
                        // Load agent entries
                        const agentEntries = await parseSessionFile(agent.filePath);
                        for (const entry of agentEntries) {
                            aggregator.processEntry(entry, agent);
                        }
                        agentCount++;
                    }
                    catch {
                        // Skip agents that can't be parsed
                    }
                }
            }
            catch (err) {
                // Skip sessions that can't be parsed
            }
        }
        if (ctx.verbose) {
            console.log(chalk.gray(`Pre-loaded ${recentSessions.length} sessions, ${agentCount} agents`));
        }
        // Start the watcher for real-time updates
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
    // Config command (Phase 7)
    const configCmd = program
        .command('config')
        .description('Manage karma configuration')
        .option('-j, --json', 'Output as JSON')
        .action(withErrorHandler(async (options) => {
        await configShow(options);
    }));
    configCmd
        .command('get <key>')
        .description('Get a configuration value')
        .action(withErrorHandler(async (key, options, cmd) => {
        const parentOpts = cmd.parent?.opts() ?? {};
        await configGet(key, parentOpts);
    }));
    configCmd
        .command('set <key> <value>')
        .description('Set a configuration value')
        .action(withErrorHandler(async (key, value, options, cmd) => {
        const parentOpts = cmd.parent?.opts() ?? {};
        await configSet(key, value, parentOpts);
    }));
    configCmd
        .command('reset')
        .description('Reset configuration to defaults')
        .action(withErrorHandler(async (options, cmd) => {
        const parentOpts = cmd.parent?.opts() ?? {};
        await configReset(parentOpts);
    }));
    configCmd
        .command('list')
        .description('List available configuration keys')
        .action(withErrorHandler(async (options, cmd) => {
        const parentOpts = cmd.parent?.opts() ?? {};
        await configList(parentOpts);
    }));
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