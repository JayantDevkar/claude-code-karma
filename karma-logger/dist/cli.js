import { Command } from 'commander';
import chalk from 'chalk';
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
    // Status command - placeholder for Phase 4
    program
        .command('status')
        .description('Show current session metrics')
        .action((_options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        console.log(chalk.yellow('karma status: Not implemented'));
        console.log(chalk.gray('This command will be implemented in Phase 4'));
    });
    // Watch command - placeholder for Phase 5
    program
        .command('watch')
        .description('Watch sessions in real-time')
        .action((_options, cmd) => {
        const ctx = getContext(cmd);
        if (ctx.verbose) {
            console.log(chalk.gray('Running in verbose mode'));
        }
        console.log(chalk.yellow('karma watch: Not implemented'));
        console.log(chalk.gray('This command will be implemented in Phase 5'));
    });
    // Report command - placeholder for Phase 6
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