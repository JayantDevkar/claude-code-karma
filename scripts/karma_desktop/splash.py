"""The "starting up" page shown while the servers cold-start.

A first ``npm run dev`` on this repo can take a minute or two. Without
feedback a desktop click looks like it did nothing, so the launcher serves
this page from a throwaway HTTP server that is ready in milliseconds, and
tears it down once the dashboard is up.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from pathlib import Path

_TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<title>Karma</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; height: 100vh; display: grid; place-items: center;
    background: #0f1419; color: #e8e8ea;
    font: 14px/1.5 ui-sans-serif, -apple-system, "Inter", system-ui, sans-serif;
  }
  .card { width: 340px; }
  h1 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: #8b8b93; font-size: 12.5px; margin: 0 0 22px; }
  .bar {
    height: 3px; border-radius: 3px; background: #1e1e22;
    overflow: hidden; margin-bottom: 20px;
  }
  .bar i {
    display: block; height: 100%; width: 40%; border-radius: 3px;
    background: linear-gradient(90deg, transparent, #6c8cff, transparent);
    animation: slide 1.25s ease-in-out infinite;
  }
  @keyframes slide {
    0% { transform: translateX(-110%) } 100% { transform: translateX(310%) }
  }
  ul { list-style: none; margin: 0; padding: 0; }
  li {
    display: flex; align-items: center; gap: 9px; padding: 6px 0; color: #8b8b93;
    font: 12.5px/1.4 ui-monospace, "JetBrains Mono", SFMono-Regular, monospace;
  }
  li .dot {
    width: 7px; height: 7px; border-radius: 50%; background: #34343a; flex: none;
  }
  li.on { color: #e8e8ea; }
  li.on .dot { background: #4ade80; }
  li.busy .dot { background: #6c8cff; animation: pulse 1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .3 } }
  .foot {
    margin-top: 22px; color: #5c5c64; font-size: 11.5px;
    font-family: ui-monospace, SFMono-Regular, monospace;
  }
</style>
<div class="card">
  <h1>Starting Karma</h1>
  <p class="sub">First launch compiles the frontend. This can take a minute or two.</p>
  <div class="bar"><i></i></div>
  <ul>
    <li id="api"><span class="dot"></span><span>API server</span></li>
    <li id="web"><span class="dot"></span><span>Frontend</span></li>
  </ul>
  <div class="foot"><span id="elapsed">0s</span> elapsed</div>
</div>
<script>
  const API = __API_PORT__, WEB = __WEB_PORT__;
  const t0 = Date.now();
  setInterval(function () {
    document.getElementById('elapsed').textContent =
      Math.floor((Date.now() - t0) / 1000) + 's';
  }, 1000);

  // A no-cors fetch resolves (opaque) once the port answers and rejects while
  // nothing is listening -- enough to probe liveness without CORS headers.
  async function up(port) {
    try {
      await fetch('http://localhost:' + port + '/', { mode: 'no-cors', cache: 'no-store' });
      return true;
    } catch (e) { return false; }
  }

  async function tick() {
    const apiOk = await up(API);
    document.getElementById('api').className = apiOk ? 'on' : 'busy';

    const webOk = await up(WEB);
    document.getElementById('web').className = webOk ? 'on' : (apiOk ? 'busy' : '');

    if (webOk) {
      __HANDOFF__
      return;
    }
    setTimeout(tick, 700);
  }
  tick();
</script>
"""


# How the splash gives way to the dashboard, which differs by platform.
#
# macOS hands off: the launcher opens the installed PWA (or an app-mode window)
# and closes this one, because navigating *this* window to the dashboard would
# leave it under the browser's Dock icon rather than Karma's — and on macOS the
# Dock icon is the whole point.
#
# Windows redirects in place: the Desktop shortcut already carries Karma's icon,
# and Chrome exposes no scriptable way to close a specific app window from
# outside, so a redirect is both simpler and more reliable there.
_HANDOFF_CLOSE = """document.querySelector('h1').textContent = 'Ready';
      document.querySelector('.sub').textContent = 'Opening Karma\\u2026';
      document.querySelector('.bar').style.visibility = 'hidden';"""

_HANDOFF_REDIRECT = """location.replace('http://localhost:' + WEB + '/');"""


def render(api_port: int, web_port: int, redirect: bool = False) -> str:
    """Splash HTML with this install's ports and handoff strategy baked in.

    ``redirect=True`` makes the page navigate itself to the dashboard once the
    frontend answers; otherwise it parks on a "Ready" state and waits for the
    launcher to close it.
    """
    handoff = _HANDOFF_REDIRECT if redirect else _HANDOFF_CLOSE
    return (
        _TEMPLATE.replace("__API_PORT__", str(api_port))
        .replace("__WEB_PORT__", str(web_port))
        .replace("__HANDOFF__", handoff)
    )


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the splash directory without logging to stderr."""

    def log_message(self, fmt, *args):  # noqa: A003 - stdlib signature
        pass


def serve(directory: Path, port: int = 0) -> socketserver.TCPServer:
    """Start a background HTTP server for ``directory`` and return it.

    Pass ``port=0`` (the default) to let the OS pick a free port; read the
    chosen one back from ``httpd.server_address[1]``. The caller is responsible
    for calling ``shutdown()``. Binds to loopback only — this page is never
    meant to leave the machine.
    """

    def handler(*args, **kwargs):
        return _QuietHandler(*args, directory=str(directory), **kwargs)

    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
