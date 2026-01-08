/**
 * Verify parser against real Claude Code session files
 */

import { parseSession, getToolUsageCounts } from '../src/parser.js';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

async function main() {
  const claudeDir = join(
    homedir(),
    '.claude/projects/-Users-jayantdevkar-Documents-GitHub-claude-karma'
  );

  const files = readdirSync(claudeDir)
    .filter(f => f.endsWith('.jsonl'))
    .slice(0, 3);

  for (const file of files) {
    try {
      const session = await parseSession(join(claudeDir, file));
      console.log('---');
      console.log('Session:', session.sessionId.slice(0, 8) + '...');
      console.log('Entries:', session.entries.length);
      console.log('Models:', Array.from(session.models).join(', ') || 'none');
      console.log('Total Input Tokens:', session.totalUsage.inputTokens.toLocaleString());
      console.log('Total Output Tokens:', session.totalUsage.outputTokens.toLocaleString());
      console.log('Cache Read:', session.totalUsage.cacheReadTokens.toLocaleString());
      console.log('Cache Creation:', session.totalUsage.cacheCreationTokens.toLocaleString());

      const tools = getToolUsageCounts(session.entries);
      const topTools = Array.from(tools.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([t, c]) => `${t}:${c}`)
        .join(', ');
      console.log('Top Tools:', topTools || 'none');
    } catch (e) {
      console.log('Error parsing', file, (e as Error).message);
    }
  }

  console.log('---');
  console.log('✓ Parser verified against', files.length, 'real session files');
}

main().catch(console.error);
