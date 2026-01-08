import { Command } from 'commander';
import chalk from 'chalk';
import { startTUI } from './tui/index.js';
import { statusCommand } from './commands/status.js';
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
    // Watch command with --ui flag
    program
        .command('watch')
        .description('Watch sessions in real-time')
        .option('-u, --ui', 'Launch interactive TUI dashboard', false)
        .option('-s, --session <id>', 'Watch specific session')
        .action((options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        if (options.ui) {
            // Launch TUI dashboard
            startTUI({ sessionId: options.session });
            return;
        }
        // Default watch behavior (streaming output)
        console.log(chalk.yellow('karma watch: Streaming mode not implemented'));
        console.log(chalk.gray('Use --ui flag for interactive dashboard'));
    });
    // Report command
    program
        .command('report')
        .description('Generate usage reports')
        .action((_options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        console.log(chalk.yellow('karma report: Not implemented'));
        console.log(chalk.gray('This command will be implemented in Phase 6'));
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