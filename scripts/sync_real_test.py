#!/usr/bin/env python3
"""REAL two-machine sync test: alice on this Mac mini, bob on the MacBook Air.

Both peers use isolated fake HOMEs (real user data untouched on both machines).
The Air is driven over SSH (process control, file checks) + direct HTTP on the
LAN (karma API :8190, Syncthing GUI :8590). The mini's Syncthing only dials
OUTBOUND to the Air (mini's firewall stays happy; Air's firewall is off).

Usage:  python scripts/sync_real_test.py [--keep]
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
API_DIR = REPO / "api"
PYTHON = os.environ.get("SYNC_SIM_PYTHON", sys.executable)

AIR_SSH = "ayushjhunjhunwala@Ayushs-MacBook-Air.local"
AIR_IP = "192.168.29.117"
AIR_ROOT = "/Users/ayushjhunjhunwala/karma-sync-test"
AIR_HOME = f"{AIR_ROOT}/home"
AIR_REPO = f"{AIR_ROOT}/repo"
AIR_PY = f"{AIR_ROOT}/venv/bin/python"
AIR_ST = f"{AIR_ROOT}/bin/syncthing"

MINI_HOME = Path("/tmp/karma-real-test/mini-home")

GUI_PORT = 8590
SYNC_PORT = 22190
API_PORT = 8190

_T0 = time.monotonic()
RESULTS: list[tuple[str, float, bool]] = []


def log(msg: str) -> None:
    print(f"[{time.monotonic() - _T0:7.1f}s] {msg}", flush=True)


def wait_for(name: str, fn, timeout: float = 120, interval: float = 2.0):
    start = time.monotonic()
    last_exc = None
    while time.monotonic() - start < timeout:
        try:
            value = fn()
            if value:
                elapsed = time.monotonic() - start
                RESULTS.append((name, elapsed, True))
                log(f"PASS  {name}  ({elapsed:.1f}s)")
                return value
        except Exception as e:
            last_exc = e
        time.sleep(interval)
    elapsed = time.monotonic() - start
    RESULTS.append((name, elapsed, False))
    log(f"FAIL  {name}  (timed out after {elapsed:.0f}s; last error: {last_exc})")
    raise AssertionError(f"step failed: {name}")


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, 0.0, bool(ok)))
    log(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        raise AssertionError(f"check failed: {name} {detail}")


def summary() -> bool:
    passed = sum(1 for _, _, ok in RESULTS if ok)
    print("\n=========== REAL 2-MACHINE RESULT SUMMARY ===========")
    for name, elapsed, ok in RESULTS:
        mark = "PASS" if ok else "FAIL"
        t = f"{elapsed:6.1f}s" if elapsed else "      -"
        print(f"  {mark}  {t}  {name}")
    print(f"  {passed}/{len(RESULTS)} steps passed")
    print("=====================================================\n")
    return passed == len(RESULTS)


def ssh(cmd: str, timeout: int = 60) -> str:
    """Run a command on the Air; raises on failure."""
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", AIR_SSH, cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ssh failed ({cmd[:80]}...): {result.stderr[:300]}")
    return result.stdout.strip()


def ssh_ok(cmd: str) -> bool:
    try:
        ssh(cmd)
        return True
    except Exception:
        return False


class PeerAPI:
    """HTTP driver for one peer's karma API + Syncthing REST."""

    def __init__(self, name: str, api_base: str, st_base: str, api_key: str = ""):
        self.name = name
        self.api_base = api_base
        self.st_base = st_base
        self.api_key = api_key
        self.device_id = ""
        self.member_tag = ""

    def api(self, method: str, path: str, body=None, ok=(200, 201)):
        resp = requests.request(method, self.api_base + path, json=body, timeout=30)
        if resp.status_code not in ok:
            raise RuntimeError(f"{self.name} {method} {path} -> {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except Exception:
            return None

    def api_try(self, method: str, path: str, body=None):
        try:
            return self.api(method, path, body)
        except Exception:
            return None

    def st(self, method: str, path: str, body=None):
        resp = requests.request(
            method, self.st_base + path,
            headers={"X-API-Key": self.api_key}, json=body, timeout=15,
        )
        resp.raise_for_status()
        if resp.text and "json" in resp.headers.get("content-type", ""):
            return resp.json()
        return None

    def pin_device_address(self, device_id: str, address: str):
        for dev in self.st("GET", "/rest/config/devices"):
            if dev["deviceID"] == device_id and dev.get("addresses") != [address]:
                dev["addresses"] = [address]
                self.st("PUT", f"/rest/config/devices/{device_id}", dev)

    def accept_pending_device(self, device_id: str) -> bool:
        pend = self.api_try("GET", "/sync/pending-devices")
        for dev in (pend or {}).get("devices", []):
            if dev["device_id"] == device_id:
                self.api("POST", f"/sync/pending-devices/{device_id}/accept", {})
                return True
        devices = self.st("GET", "/rest/config/devices")
        return any(d["deviceID"] == device_id for d in devices)


def session_lines(session_uuid: str, prompt: str, encoded: str) -> str:
    now = "2026-07-10T02:00:00.000Z"
    cwd = "/Users/real/" + encoded.strip("-").replace("-", "/")
    lines = [
        {"parentUuid": None, "isSidechain": False, "userType": "external",
         "cwd": cwd, "sessionId": session_uuid, "version": "2.1.1",
         "gitBranch": "main", "type": "user",
         "message": {"role": "user", "content": prompt},
         "uuid": f"u-{session_uuid[:8]}", "timestamp": now},
        {"parentUuid": f"u-{session_uuid[:8]}", "isSidechain": False, "cwd": cwd,
         "sessionId": session_uuid, "version": "2.1.1", "gitBranch": "main",
         "type": "assistant",
         "message": {"model": "claude-sonnet-5", "id": f"m-{session_uuid[:8]}",
                      "type": "message", "role": "assistant",
                      "content": [{"type": "text", "text": "Done."}],
                      "stop_reason": "end_turn",
                      "usage": {"input_tokens": 10, "output_tokens": 5}},
         "uuid": f"a-{session_uuid[:8]}", "timestamp": now},
    ]
    return "\n".join(json.dumps(line) for line in lines) + "\n"


def main() -> bool:
    keep = "--keep" in sys.argv
    mini_procs: list[subprocess.Popen] = []
    encoded = "-Users-real-demo-app"

    # ---------- boot: mini (alice) ----------
    if MINI_HOME.parent.exists():
        shutil.rmtree(MINI_HOME.parent)
    st_home = MINI_HOME / "Library" / "Application Support" / "Syncthing"
    (MINI_HOME / ".claude" / "projects").mkdir(parents=True)
    (MINI_HOME / ".claude_karma").mkdir(parents=True)
    st_home.mkdir(parents=True)

    env = os.environ.copy()
    env.update({
        "HOME": str(MINI_HOME),
        "CLAUDE_KARMA_SYNCTHING_URL": f"http://127.0.0.1:{GUI_PORT}",
        "CLAUDE_KARMA_RECONCILER_ENABLED": "false",
        "CLAUDE_KARMA_REINDEX_INTERVAL_SECONDS": "0",
        "STNODEFAULTFOLDER": "1", "STNOUPGRADE": "1",
    })
    subprocess.run(["syncthing", "generate", "--home", str(st_home)],
                   check=True, capture_output=True, env=env)
    tree = ET.parse(st_home / "config.xml")
    alice_key = tree.find(".//gui/apikey").text
    alice_device = tree.find(".//device").get("id")
    mini_procs.append(subprocess.Popen(
        ["syncthing", "serve", "--home", str(st_home), "--no-browser",
         "--no-restart", f"--gui-address=127.0.0.1:{GUI_PORT}"],
        stdout=open(MINI_HOME / "syncthing.log", "w"),
        stderr=subprocess.STDOUT, env=env))
    mini_procs.append(subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "main:app", "--port", str(API_PORT),
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=str(API_DIR), stdout=open(MINI_HOME / "api.log", "w"),
        stderr=subprocess.STDOUT, env=env))

    alice = PeerAPI("alice", f"http://127.0.0.1:{API_PORT}",
                    f"http://127.0.0.1:{GUI_PORT}", alice_key)
    alice.device_id = alice_device

    # ---------- boot: air (bob) ----------
    air_env = (
        f"HOME={AIR_HOME} CLAUDE_KARMA_SYNCTHING_URL=http://127.0.0.1:{GUI_PORT} "
        f"CLAUDE_KARMA_RECONCILER_ENABLED=false CLAUDE_KARMA_REINDEX_INTERVAL_SECONDS=0 "
        f"STNODEFAULTFOLDER=1 STNOUPGRADE=1"
    )
    air_st_home = f"{AIR_HOME}/Library/Application Support/Syncthing"
    ssh(f"pkill -f 'syncthing serve' 2>/dev/null; pkill -f 'uvicorn main:app' 2>/dev/null; true")
    ssh(f"mkdir -p '{AIR_HOME}/.claude/projects' '{AIR_HOME}/.claude_karma' '{shlex.quote(air_st_home)}'"
        .replace("''", "'"))
    ssh(f"{air_env} {AIR_ST} generate --home {shlex.quote(air_st_home)} >/dev/null 2>&1 || true")
    bob_key = ssh(
        f"python3 -c \"import xml.etree.ElementTree as ET; "
        f"print(ET.parse('{air_st_home}/config.xml').find('.//gui/apikey').text)\"")
    bob_device = ssh(
        f"python3 -c \"import xml.etree.ElementTree as ET; "
        f"print(ET.parse('{air_st_home}/config.xml').find('.//device').get('id'))\"")
    # GUI on 0.0.0.0 so the mini can drive it; API likewise
    ssh(f"cd {AIR_ROOT} && {air_env} nohup {AIR_ST} serve --home {shlex.quote(air_st_home)} "
        f"--no-browser --no-restart --gui-address=0.0.0.0:{GUI_PORT} "
        f"> {AIR_HOME}/syncthing.log 2>&1 & echo started-st")
    ssh(f"cd {AIR_REPO}/api && {air_env} nohup {AIR_PY} -m uvicorn main:app "
        f"--host 0.0.0.0 --port {API_PORT} --log-level warning "
        f"> {AIR_HOME}/api.log 2>&1 & echo started-api")

    bob = PeerAPI("bob", f"http://{AIR_IP}:{API_PORT}",
                  f"http://{AIR_IP}:{GUI_PORT}", bob_key)
    bob.device_id = bob_device

    try:
        # ---------- readiness ----------
        wait_for("alice syncthing REST up",
                 lambda: alice.st("GET", "/rest/system/status")["myID"] == alice_device, 60)
        wait_for("bob syncthing REST up (over LAN)",
                 lambda: bob.st("GET", "/rest/system/status")["myID"] == bob_device, 60)
        # local-only networking on both: fixed listen ports, no relays/global
        for peer, listen in ((alice, f"tcp://127.0.0.1:0"), (bob, f"tcp://0.0.0.0:{SYNC_PORT}")):
            peer.st("PATCH", "/rest/config/options", {
                "listenAddresses": [listen],
                "globalAnnounceEnabled": False, "relaysEnabled": False,
                "natEnabled": False, "localAnnounceEnabled": True,
                "reconnectionIntervalS": 5,
            })
        wait_for("alice karma API up",
                 lambda: alice.api("GET", "/sync/detect")["syncthing_running"], 90)
        wait_for("bob karma API up (over LAN)",
                 lambda: bob.api("GET", "/sync/detect")["syncthing_running"], 90)

        alice.member_tag = alice.api("POST", "/sync/init", {"user_id": "alice"})["member_tag"]
        bob.member_tag = bob.api("POST", "/sync/init", {"user_id": "bob"})["member_tag"]
        log(f"alice = {alice.member_tag} ({alice.device_id[:7]}) on mini")
        log(f"bob   = {bob.member_tag} ({bob.device_id[:7]}) on air {AIR_IP}")

        # ---------- team + join ----------
        alice.api("POST", "/sync/teams", {"name": "real-crew"})
        check("alice created team real-crew", True)
        code = bob.api("GET", "/sync/pairing/code")["code"]
        alice.api("POST", "/sync/teams/real-crew/members", {"pairing_code": code})
        # mini dials OUT to the air (mini firewall stays quiet)
        alice.pin_device_address(bob.device_id, f"tcp://{AIR_IP}:{SYNC_PORT}")

        def bob_accepts():
            alice.pin_device_address(bob.device_id, f"tcp://{AIR_IP}:{SYNC_PORT}")
            return bob.accept_pending_device(alice.device_id)
        wait_for("bob sees + accepts alice's pairing request", bob_accepts, 120)

        wait_for("bob discovers team 'real-crew'",
                 lambda: any(t["name"] == "real-crew"
                             for t in (bob.api_try("GET", "/sync/status") or {}).get("teams", [])),
                 240, 3)

        bob.api("PUT", "/sync/teams/real-crew/prefs",
                {"new_project_policy": "auto_accept", "default_direction": "both"})
        check("bob set policy auto_accept/both", True)

        # ---------- share + transfer alice -> bob ----------
        s_alice = str(uuid.uuid4())
        proj_dir = MINI_HOME / ".claude" / "projects" / encoded
        proj_dir.mkdir(parents=True, exist_ok=True)
        f = proj_dir / f"{s_alice}.jsonl"
        f.write_text(session_lines(s_alice, "real machine test session", encoded))
        os.utime(f, (time.time() - 3600, time.time() - 3600))

        alice.api("POST", "/sync/teams/real-crew/projects",
                  {"git_identity": "real/demo-app", "encoded_name": encoded})
        check("alice shared real/demo-app", True)

        wait_for("bob auto-accepted the offer (policy)",
                 lambda: any(s["project_git_identity"] == "real/demo-app" and s["status"] == "accepted"
                             for s in (bob.api_try("GET", "/sync/subscriptions") or {}).get("subscriptions", [])),
                 240, 3)

        alice.api("POST", "/sync/package?team_name=real-crew")
        wait_for("alice's session arrived ON THE AIR'S DISK (real P2P over LAN)",
                 lambda: ssh_ok(f"ls {AIR_HOME}/.claude_karma/karma-out--{alice.member_tag}--real-demo-app/sessions/{s_alice}.jsonl"),
                 300, 3)
        wait_for("bob indexed alice's session (remote-sessions API)",
                 lambda: any(s["uuid"] == s_alice
                             for u in (bob.api_try("GET", f"/projects/{encoded}/remote-sessions") or {}).get("users", [])
                             for s in u.get("sessions", [])),
                 240, 3)

        # ---------- reverse: bob -> alice ----------
        s_bob = str(uuid.uuid4())
        air_proj = f"{AIR_HOME}/.claude/projects/{encoded}"
        content = session_lines(s_bob, "air session flows back to mini", encoded)
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", AIR_SSH,
             f"mkdir -p {air_proj} && cat > {air_proj}/{s_bob}.jsonl && touch -t 202607100100 {air_proj}/{s_bob}.jsonl"],
            input=content, text=True, check=True, timeout=30,
        )
        bob.api("POST", "/sync/package?team_name=real-crew")
        wait_for("bob's session arrived on the MINI's disk (reverse direction)",
                 lambda: any((MINI_HOME / ".claude_karma").rglob(f"{s_bob}.jsonl")),
                 300, 3)

        # ---------- health ----------
        for peer in (alice, bob):
            watcher = (peer.api_try("GET", "/sync/status") or {}).get("watcher") or {}
            listener = watcher.get("event_listener") or {}
            check(f"{peer.name} event listener connected", bool(listener.get("connected")),
                  json.dumps(listener))
        conns = alice.st("GET", "/rest/system/connections")["connections"]
        ctype = (conns.get(bob.device_id) or {}).get("type", "?")
        check("alice <-> bob direct LAN connection", "relay" not in ctype.lower(), f"type={ctype}")

        return summary()
    finally:
        if not keep:
            for p in mini_procs:
                try:
                    p.send_signal(signal.SIGTERM)
                except Exception:
                    pass
            # Air: only kill the processes we started; files stay (no deletions)
            try:
                ssh("pkill -f 'syncthing serve' 2>/dev/null; pkill -f 'uvicorn main:app' 2>/dev/null; true")
            except Exception:
                pass
        else:
            log(f"--keep: alice api http://127.0.0.1:{API_PORT}, bob api http://{AIR_IP}:{API_PORT}")


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
