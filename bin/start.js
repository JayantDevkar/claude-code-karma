#!/usr/bin/env node

'use strict';

const { spawn, execSync } = require('child_process');
const { existsSync, writeFileSync } = require('fs');
const path = require('path');
const http = require('http');
const net = require('net');

const ROOT = path.join(__dirname, '..');
const VENV_DIR = path.join(ROOT, '.karma-venv');
const VENV_BIN = path.join(VENV_DIR, process.platform === 'win32' ? 'Scripts' : 'bin');
const STAMP = path.join(VENV_DIR, '.deps-installed');

const args = process.argv.slice(2);
const NO_OPEN = args.includes('--no-open');
const PREFERRED_API_PORT = parseInt(flagValue('--api-port') || '8000', 10);
const PREFERRED_WEB_PORT = parseInt(flagValue('--web-port') || '5173', 10);

function flagValue(name) {
  const i = args.indexOf(name);
  return i !== -1 ? args[i + 1] : null;
}

const dim    = (s) => `\x1b[2m${s}\x1b[0m`;
const green  = (s) => `\x1b[32m${s}\x1b[0m`;
const cyan   = (s) => `\x1b[36m${s}\x1b[0m`;
const red    = (s) => `\x1b[31m${s}\x1b[0m`;
const bold   = (s) => `\x1b[1m${s}\x1b[0m`;

const API_TAG = cyan('[api]');
const WEB_TAG = green('[web]');

async function main() {
  console.log('');
  console.log(bold('  Claude Code Karma'));
  console.log('');

  // 1. Find Python 3
  const python = findPython();
  if (!python) {
    console.error(red('  ✗ Python 3 not found.'));
    console.error('    Install it from https://python.org and try again.');
    process.exit(1);
  }

  // 2. Create virtualenv if missing
  if (!existsSync(VENV_DIR)) {
    step('Creating Python environment');
    runSync(`"${python}" -m venv "${VENV_DIR}"`);
    ok();
  }

  // 3. Install Python deps (stamp file prevents re-running every time)
  if (!existsSync(STAMP)) {
    step('Installing API dependencies');
    const pip = path.join(VENV_BIN, 'pip');
    runSync(`"${pip}" install -r "${path.join(ROOT, 'api', 'requirements.txt')}" -q`);
    runSync(`"${pip}" install -e "${path.join(ROOT, 'api')}" -q`);
    writeFileSync(STAMP, new Date().toISOString());
    ok();
  } else {
    stepCached('API dependencies');
  }

  const frontendDir = path.join(ROOT, 'frontend');

  // 4. Resolve free ports
  const apiPort = await findFreePort(PREFERRED_API_PORT);
  const webPort = await findFreePort(PREFERRED_WEB_PORT);

  if (apiPort !== PREFERRED_API_PORT)
    console.log(`  ${dim(`Port ${PREFERRED_API_PORT} in use → API on ${apiPort}`)}`);
  if (webPort !== PREFERRED_WEB_PORT)
    console.log(`  ${dim(`Port ${PREFERRED_WEB_PORT} in use → Web on ${webPort}`)}`);

  console.log('');

  // 6. Spawn API and frontend
  const venvPython = path.join(VENV_BIN, 'python');

  const apiProc = spawn(
    venvPython,
    ['-m', 'uvicorn', 'main:app', '--port', String(apiPort)],
    { cwd: path.join(ROOT, 'api'), stdio: ['ignore', 'pipe', 'pipe'] }
  );

  const webProc = spawn(
    process.execPath,
    [path.join(frontendDir, 'build', 'index.js')],
    {
      cwd: frontendDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PORT: String(webPort),
        KARMA_API_URL: `http://localhost:${apiPort}`,
      },
    }
  );

  const procs = [apiProc, webProc];

  attachPrefix(apiProc, API_TAG);
  attachPrefix(webProc, WEB_TAG);

  for (const proc of procs) {
    proc.on('exit', (code) => {
      if (code !== 0 && code !== null) {
        console.error(red(`\n  Process exited unexpectedly (code ${code}). Shutting down.`));
        cleanup(procs);
        process.exit(code ?? 1);
      }
    });
  }

  // 7. Wait until both ports respond
  process.stdout.write('  Waiting for services');
  try {
    await Promise.all([waitFor(apiPort), waitFor(webPort)]);
  } catch (e) {
    console.error(red('\n  Timed out waiting for services to start.'));
    cleanup(procs);
    process.exit(1);
  }
  console.log(' ' + green('✓'));
  console.log('');

  // 8. Open browser
  const url = `http://localhost:${webPort}`;
  console.log(`  ${bold('Dashboard')} → ${cyan(url)}`);
  if (!NO_OPEN) openUrl(url);
  console.log(`  ${dim('Ctrl+C to stop both services')}`);
  console.log('');

  process.on('SIGINT', () => { cleanup(procs); process.exit(0); });
  process.on('SIGTERM', () => { cleanup(procs); process.exit(0); });
}

// ── Helpers ────────────────────────────────────────────────────────────────

function findPython() {
  for (const cmd of ['python3', 'python']) {
    try {
      const v = execSync(`${cmd} -c "import sys; print(sys.version_info.major)"`, {
        stdio: 'pipe',
      }).toString().trim();
      if (v === '3') return cmd;
    } catch {}
  }
  return null;
}

function runSync(cmd, opts = {}) {
  execSync(cmd, { stdio: 'pipe', ...opts });
}

function step(label) {
  process.stdout.write(`  ${label}...`);
}
function ok() {
  console.log(' ' + green('done'));
}
function stepCached(label) {
  console.log(`  ${label}... ${dim('cached')}`);
}

function attachPrefix(proc, tag) {
  let stdoutBuf = '';
  let stderrBuf = '';

  const flush = (buf, incoming, stream) => {
    buf += incoming.toString();
    const lines = buf.split('\n');
    const remainder = lines.pop();
    for (const line of lines) {
      if (line.trim()) stream.write(`${tag} ${line}\n`);
    }
    return remainder;
  };

  proc.stdout.on('data', (d) => { stdoutBuf = flush(stdoutBuf, d, process.stdout); });
  proc.stderr.on('data', (d) => { stderrBuf = flush(stderrBuf, d, process.stderr); });
}

function findFreePort(preferred) {
  return new Promise((resolve) => {
    // Use connect (not listen) to detect in-use ports — on macOS, listen(0.0.0.0)
    // succeeds even when 127.0.0.1 is already bound (dual IPv4/IPv6 stack quirk).
    const client = net.createConnection({ port: preferred, host: '127.0.0.1' });
    client.on('connect', () => {
      client.destroy();
      const fallback = net.createServer();
      fallback.listen(0, () => {
        const { port } = fallback.address();
        fallback.close(() => resolve(port));
      });
    });
    client.on('error', () => resolve(preferred));
  });
}

function waitFor(port, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      if (Date.now() > deadline) { reject(new Error(`port ${port} timeout`)); return; }
      const req = http.get(`http://localhost:${port}`, () => {
        process.stdout.write('.');
        resolve();
      });
      req.on('error', () => setTimeout(attempt, 600));
      req.setTimeout(400, () => { req.destroy(); setTimeout(attempt, 600); });
    };
    attempt();
  });
}

function openUrl(url) {
  try {
    if (process.platform === 'darwin') execSync(`open "${url}"`);
    else if (process.platform === 'win32') execSync(`start "" "${url}"`);
    else execSync(`xdg-open "${url}"`);
  } catch {}
}

function cleanup(procs) {
  for (const p of procs) {
    try { p.kill('SIGTERM'); } catch {}
  }
}

main().catch((e) => {
  console.error(red('\n  Fatal: ') + e.message);
  process.exit(1);
});
