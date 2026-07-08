#!/usr/bin/env python3
"""Multi-peer sync simulation — N isolated karma+Syncthing stacks on one machine.

Each peer gets a fake HOME (isolating ~/.claude, ~/.claude_karma, and the
Syncthing config dir in one stroke), its own Syncthing instance (unique GUI +
listen ports, relays/global-discovery disabled), and its own karma API process
(unique port, CLAUDE_KARMA_SYNCTHING_URL pointing at its Syncthing).

Usage:
    python scripts/sync_sim.py two    # 2-peer full lifecycle
    python scripts/sync_sim.py four   # 4-peer mesh + permutations
    python scripts/sync_sim.py two --keep   # leave stacks running afterwards

Requires: syncthing on PATH, and the API venv (SYNC_SIM_PYTHON env var or
the current interpreter must have the api/ requirements installed).
"""
from __future__ import annotations

import json
import os
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
BASE = Path(os.environ.get("SYNC_SIM_BASE", "/tmp/karma-sync-sim"))
PYTHON = os.environ.get("SYNC_SIM_PYTHON", sys.executable)

GUI_PORT0 = 8590      # Syncthing GUI/REST per peer: 8590, 8591, ...
SYNC_PORT0 = 22190    # Syncthing data listen per peer
API_PORT0 = 8190      # karma API per peer

_T0 = time.monotonic()


def log(msg: str) -> None:
    print(f"[{time.monotonic() - _T0:7.1f}s] {msg}", flush=True)


class StepTimer:
    """Times a named stage and asserts a condition became true within budget."""

    def __init__(self):
        self.results: list[tuple[str, float, bool]] = []

    def wait_for(self, name: str, fn, timeout: float = 90, interval: float = 1.0):
        start = time.monotonic()
        last_exc = None
        while time.monotonic() - start < timeout:
            try:
                value = fn()
                if value:
                    elapsed = time.monotonic() - start
                    self.results.append((name, elapsed, True))
                    log(f"PASS  {name}  ({elapsed:.1f}s)")
                    return value
            except Exception as e:  # endpoint not up yet, etc.
                last_exc = e
            time.sleep(interval)
        elapsed = time.monotonic() - start
        self.results.append((name, elapsed, False))
        log(f"FAIL  {name}  (timed out after {elapsed:.0f}s; last error: {last_exc})")
        raise AssertionError(f"step failed: {name}")

    def check(self, name: str, ok: bool, detail: str = ""):
        self.results.append((name, 0.0, bool(ok)))
        log(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
        if not ok:
            raise AssertionError(f"check failed: {name} {detail}")

    def summary(self) -> bool:
        passed = sum(1 for _, _, ok in self.results if ok)
        print("\n================ RESULT SUMMARY ================")
        for name, elapsed, ok in self.results:
            mark = "PASS" if ok else "FAIL"
            t = f"{elapsed:6.1f}s" if elapsed else "      -"
            print(f"  {mark}  {t}  {name}")
        print(f"  {passed}/{len(self.results)} steps passed")
        print("================================================\n")
        return passed == len(self.results)


class Peer:
    def __init__(self, index: int, user_id: str):
        self.index = index
        self.user_id = user_id
        self.home = BASE / f"peer{index}"
        self.gui_port = GUI_PORT0 + index
        self.sync_port = SYNC_PORT0 + index
        self.api_port = API_PORT0 + index
        self.st_url = f"http://127.0.0.1:{self.gui_port}"
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        self.st_home = self.home / "Library" / "Application Support" / "Syncthing"
        self.api_key: str = ""
        self.device_id: str = ""
        self.member_tag: str = ""
        self.procs: list[subprocess.Popen] = []

    # -- lifecycle -----------------------------------------------------------

    def setup_dirs(self):
        (self.home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
        (self.home / ".claude_karma").mkdir(parents=True, exist_ok=True)
        self.st_home.mkdir(parents=True, exist_ok=True)

    def env(self) -> dict:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["CLAUDE_KARMA_SYNCTHING_URL"] = self.st_url
        env["CLAUDE_KARMA_RECONCILER_ENABLED"] = "false"
        env["CLAUDE_KARMA_REINDEX_INTERVAL_SECONDS"] = "0"
        env["STNODEFAULTFOLDER"] = "1"
        env["STNOUPGRADE"] = "1"
        return env

    def start_syncthing(self):
        subprocess.run(
            ["syncthing", "generate", "--home", str(self.st_home)],
            check=True, capture_output=True, env=self.env(),
        )
        # Read the generated API key + device ID from config.xml
        tree = ET.parse(self.st_home / "config.xml")
        self.api_key = tree.find(".//gui/apikey").text
        self.device_id = tree.find(".//device").get("id")
        logf = open(self.home / "syncthing.log", "w")
        proc = subprocess.Popen(
            [
                "syncthing", "serve",
                "--home", str(self.st_home),
                "--no-browser",
                "--no-restart",
                f"--gui-address=127.0.0.1:{self.gui_port}",
            ],
            stdout=logf, stderr=subprocess.STDOUT, env=self.env(),
        )
        self.procs.append(proc)

    def configure_syncthing(self):
        """Local-only networking: fixed listen port, no relays/global discovery."""
        self.st_request("PATCH", "/rest/config/options", {
            "listenAddresses": [f"tcp://127.0.0.1:{self.sync_port}"],
            "globalAnnounceEnabled": False,
            "relaysEnabled": False,
            "natEnabled": False,
            "localAnnounceEnabled": True,
            "reconnectionIntervalS": 5,
        })

    def start_api(self):
        logf = open(self.home / "api.log", "w")
        proc = subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "main:app", "--port", str(self.api_port),
             "--host", "127.0.0.1", "--log-level", "warning"],
            cwd=str(API_DIR), stdout=logf, stderr=subprocess.STDOUT, env=self.env(),
        )
        self.procs.append(proc)

    def stop(self):
        for proc in self.procs:
            try:
                proc.send_signal(signal.SIGTERM)
            except Exception:
                pass
        for proc in self.procs:
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
        self.procs = []

    # -- HTTP helpers ---------------------------------------------------------

    def st_request(self, method: str, path: str, body=None):
        resp = requests.request(
            method, self.st_url + path,
            headers={"X-API-Key": self.api_key}, json=body, timeout=15,
        )
        resp.raise_for_status()
        if resp.text and "json" in resp.headers.get("content-type", ""):
            return resp.json()
        return None

    def api(self, method: str, path: str, body=None, ok=(200, 201)):
        resp = requests.request(method, self.api_url + path, json=body, timeout=30)
        if resp.status_code not in ok:
            raise RuntimeError(f"peer{self.index} {method} {path} -> {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except Exception:
            return None

    def api_try(self, method: str, path: str, body=None):
        try:
            return self.api(method, path, body)
        except Exception:
            return None

    # -- scenario helpers ------------------------------------------------------

    def seed_session(self, encoded_name: str, prompt: str) -> str:
        """Write a minimal-but-parseable Claude Code session JSONL."""
        proj_dir = self.home / ".claude" / "projects" / encoded_name
        proj_dir.mkdir(parents=True, exist_ok=True)
        session_uuid = str(uuid.uuid4())
        now = "2026-07-08T02:00:00.000Z"
        cwd = "/Users/sim/" + encoded_name.strip("-").replace("-", "/")
        lines = [
            {
                "parentUuid": None, "isSidechain": False, "userType": "external",
                "cwd": cwd, "sessionId": session_uuid, "version": "2.1.1",
                "gitBranch": "main", "type": "user",
                "message": {"role": "user", "content": prompt},
                "uuid": f"u-{session_uuid[:8]}", "timestamp": now,
            },
            {
                "parentUuid": f"u-{session_uuid[:8]}", "isSidechain": False,
                "cwd": cwd, "sessionId": session_uuid, "version": "2.1.1",
                "gitBranch": "main", "type": "assistant",
                "message": {
                    "model": "claude-sonnet-5", "id": f"msg_{session_uuid[:8]}",
                    "type": "message", "role": "assistant",
                    "content": [{"type": "text", "text": "Done."}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
                "uuid": f"a-{session_uuid[:8]}", "timestamp": now,
            },
        ]
        path = proj_dir / f"{session_uuid}.jsonl"
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        # Backdate mtime so live-session exclusion (recent files) can't skip it
        old = time.time() - 3600
        os.utime(path, (old, old))
        return session_uuid

    def accept_pending_device(self, device_id: str) -> bool:
        pend = self.api_try("GET", "/sync/pending-devices")
        for dev in (pend or {}).get("devices", []):
            if dev["device_id"] == device_id:
                self.api("POST", f"/sync/pending-devices/{device_id}/accept", {})
                return True
        return False

    def pin_address(self, other: "Peer"):
        """Pin the other peer's device address (local discovery can be flaky
        across many instances on one host)."""
        try:
            devices = self.st_request("GET", "/rest/config/devices")
        except Exception:
            return
        for dev in devices:
            if dev["deviceID"] == other.device_id:
                addrs = [f"tcp://127.0.0.1:{other.sync_port}"]
                if dev.get("addresses") != addrs:
                    dev["addresses"] = addrs
                    self.st_request("PUT", f"/rest/config/devices/{dev['deviceID']}", dev)


def boot_peers(names: list[str], steps: StepTimer) -> list[Peer]:
    if BASE.exists():
        shutil.rmtree(BASE)
    peers = [Peer(i, name) for i, name in enumerate(names)]
    for p in peers:
        p.setup_dirs()
        p.start_syncthing()
    for p in peers:
        steps.wait_for(
            f"peer{p.index} syncthing REST up",
            lambda p=p: p.st_request("GET", "/rest/system/status")["myID"] == p.device_id,
            timeout=60,
        )
        p.configure_syncthing()
    for p in peers:
        p.start_api()
    for p in peers:
        steps.wait_for(
            f"peer{p.index} karma API up",
            lambda p=p: requests.get(p.api_url + "/sync/detect", timeout=5).json()["syncthing_running"],
            timeout=90,
        )
    for p in peers:
        init = p.api("POST", "/sync/init", {"user_id": p.user_id})
        p.member_tag = init["member_tag"]
        log(f"peer{p.index} = {p.member_tag} ({p.device_id[:7]}...) api:{p.api_port} st:{p.gui_port}")
    return peers


def join_member(leader: Peer, joiner: Peer, team: str, steps: StepTimer):
    """Full join flow: pairing code -> leader adds -> joiner accepts device -> team appears."""
    code = joiner.api("GET", "/sync/pairing/code")["code"]
    leader.api("POST", f"/sync/teams/{team}/members", {"pairing_code": code})
    # Both sides pin explicit localhost addresses (discovery-independent)
    leader.pin_address(joiner)

    def joiner_sees_and_accepts():
        joiner.pin_address(leader)
        if joiner.accept_pending_device(leader.device_id):
            return True
        # Already paired? (auto-accepted by earlier team join)
        devices = joiner.st_request("GET", "/rest/config/devices")
        return any(d["deviceID"] == leader.device_id for d in devices)

    steps.wait_for(
        f"{joiner.user_id} sees + accepts {leader.user_id}'s pairing request",
        joiner_sees_and_accepts, timeout=120, interval=2,
    )
    joiner.pin_address(leader)
    leader.pin_address(joiner)
    steps.wait_for(
        f"{joiner.user_id} discovers team '{team}' (reconciliation)",
        lambda: any(
            t["name"] == team
            for t in (joiner.api_try("GET", "/sync/status") or {}).get("teams", [])
        ),
        timeout=240, interval=3,
    )


def scenario_two() -> bool:
    steps = StepTimer()
    peers = boot_peers(["alice", "bob"], steps)
    alice, bob = peers
    try:
        # 1. Alice creates a team
        alice.api("POST", "/sync/teams", {"name": "mesh-crew"})
        steps.check("alice created team mesh-crew", True)

        # 2. Bob joins (pairing code -> add -> accept -> discover)
        join_member(alice, bob, "mesh-crew", steps)

        # 3. Bob sets auto-accept policy BEFORE any project is shared
        bob.api("PUT", "/sync/teams/mesh-crew/prefs",
                {"new_project_policy": "auto_accept", "default_direction": "both"})
        steps.check("bob set new-project policy = auto_accept", True)

        # 4. Alice seeds a session and shares the project
        encoded = "-Users-sim-demo-app"
        session_uuid = alice.seed_session(encoded, "Build the demo app")
        alice.api("POST", "/sync/teams/mesh-crew/projects",
                  {"git_identity": "sim/demo-app", "encoded_name": encoded})
        steps.check("alice shared project sim/demo-app", True)

        # 5. Bob's subscription should appear AND be auto-accepted (policy)
        def bob_auto_accepted():
            subs = (bob.api_try("GET", "/sync/subscriptions") or {}).get("subscriptions", [])
            return any(
                s["project_git_identity"] == "sim/demo-app" and s["status"] == "accepted"
                for s in subs
            )
        steps.wait_for("bob auto-accepted the offer (policy, no click)", bob_auto_accepted,
                       timeout=240, interval=3)

        # 6. Alice packages sessions; the file must arrive at bob and get indexed
        alice.api("POST", "/sync/package?team_name=mesh-crew")
        steps.check("alice packaged sessions", True)

        def bob_received_file():
            inbox = bob.home / ".claude_karma"
            return any(inbox.rglob(f"{session_uuid}.jsonl"))
        steps.wait_for("session JSONL arrived on bob's disk (P2P transfer)",
                       bob_received_file, timeout=240, interval=3)

        def bob_indexed():
            data = bob.api_try("GET", f"/projects/{encoded}/remote-sessions")
            if not data:
                return False
            return any(
                s["uuid"] == session_uuid
                for u in data.get("users", []) for s in u.get("sessions", [])
            )
        steps.wait_for("bob indexed alice's session (remote-sessions API)",
                       bob_indexed, timeout=180, interval=3)

        # 7. Reverse direction: bob seeds + packages, alice receives
        bob_session = bob.seed_session(encoded, "Fix the demo app tests")
        bob.api("POST", "/sync/package?team_name=mesh-crew")
        steps.wait_for(
            "alice received bob's session (both directions work)",
            lambda: any(alice.home.joinpath(".claude_karma").rglob(f"{bob_session}.jsonl")),
            timeout=240, interval=3,
        )

        # 8. Event-driven health: event listener connected on both peers
        for p in peers:
            watcher = (p.api_try("GET", "/sync/status") or {}).get("watcher") or {}
            listener = watcher.get("event_listener") or {}
            steps.check(f"{p.user_id} event listener connected", bool(listener.get("connected")),
                        json.dumps(listener))

        # 9. Subscription lifecycle sanity: pause -> resume -> decline -> reopen
        bob.api("POST", "/sync/subscriptions/mesh-crew/sim/demo-app/pause")
        bob.api("POST", "/sync/subscriptions/mesh-crew/sim/demo-app/resume")
        bob.api("POST", "/sync/subscriptions/mesh-crew/sim/demo-app/decline")
        bob.api("POST", "/sync/subscriptions/mesh-crew/sim/demo-app/reopen")
        bob.api("POST", "/sync/subscriptions/mesh-crew/sim/demo-app/accept", {"direction": "receive"})
        subs = bob.api("GET", "/sync/subscriptions")["subscriptions"]
        target = next(s for s in subs if s["project_git_identity"] == "sim/demo-app")
        steps.check("bob lifecycle pause/resume/decline/reopen/accept(receive)",
                    target["status"] == "accepted" and target["direction"] == "receive",
                    json.dumps(target))

        return steps.summary()
    finally:
        if "--keep" not in sys.argv:
            for p in peers:
                p.stop()
        else:
            log("--keep: stacks left running")
            for p in peers:
                log(f"  peer{p.index} {p.user_id}: api={p.api_url} st={p.st_url} home={p.home}")


def scenario_four() -> bool:
    steps = StepTimer()
    peers = boot_peers(["alice", "bob", "carol", "dave"], steps)
    alice, bob, carol, dave = peers
    try:
        # Team A: alice(leader) + bob + carol — 3-member mesh
        alice.api("POST", "/sync/teams", {"name": "team-a"})
        join_member(alice, bob, "team-a", steps)
        join_member(alice, carol, "team-a", steps)

        # Everyone pins everyone (mesh addresses)
        for p1 in peers[:3]:
            for p2 in peers[:3]:
                if p1 is not p2:
                    p1.pin_address(p2)

        # Policies: bob auto-accepts BOTH, carol receive-only
        bob.api("PUT", "/sync/teams/team-a/prefs",
                {"new_project_policy": "auto_accept", "default_direction": "both"})
        carol.api("PUT", "/sync/teams/team-a/prefs", {"new_project_policy": "receive_only"})

        encoded = "-Users-sim-mesh-repo"
        s_alice = alice.seed_session(encoded, "alice session on mesh repo")
        alice.api("POST", "/sync/teams/team-a/projects",
                  {"git_identity": "sim/mesh-repo", "encoded_name": encoded})

        def accepted(peer, direction):
            subs = (peer.api_try("GET", "/sync/subscriptions") or {}).get("subscriptions", [])
            return any(
                s["project_git_identity"] == "sim/mesh-repo"
                and s["status"] == "accepted" and s["direction"] == direction
                for s in subs
            )
        steps.wait_for("bob auto-accepted (both)", lambda: accepted(bob, "both"),
                       timeout=240, interval=3)
        steps.wait_for("carol auto-accepted (receive — policy forces it)",
                       lambda: accepted(carol, "receive"), timeout=240, interval=3)

        # Mesh pairing check: bob and carol must pair with EACH OTHER
        # (not just with the leader) via Phase 2 — accept each other's requests
        def cross_paired():
            bob.accept_pending_device(carol.device_id)
            carol.accept_pending_device(bob.device_id)
            bob_devices = {d["deviceID"] for d in bob.st_request("GET", "/rest/config/devices")}
            carol_devices = {d["deviceID"] for d in carol.st_request("GET", "/rest/config/devices")}
            return carol.device_id in bob_devices and bob.device_id in carol_devices
        steps.wait_for("3-member mesh: bob <-> carol paired (Phase 2)", cross_paired,
                       timeout=240, interval=3)

        # Alice's session reaches BOTH members; bob's session reaches alice + carol
        alice.api("POST", "/sync/package?team_name=team-a")
        for peer in (bob, carol):
            steps.wait_for(
                f"{peer.user_id} received alice's session",
                lambda peer=peer: any(peer.home.joinpath(".claude_karma").rglob(f"{s_alice}.jsonl")),
                timeout=300, interval=3,
            )
        s_bob = bob.seed_session(encoded, "bob session on mesh repo")
        bob.api("POST", "/sync/package?team_name=team-a")
        for peer in (alice, carol):
            steps.wait_for(
                f"{peer.user_id} received bob's session (mesh, not hub-and-spoke)",
                lambda peer=peer: any(peer.home.joinpath(".claude_karma").rglob(f"{s_bob}.jsonl")),
                timeout=300, interval=3,
            )
        # carol is receive-only: her sessions must NOT flow out
        s_carol = carol.seed_session(encoded, "carol private session")
        carol.api("POST", "/sync/package?team_name=team-a")
        time.sleep(20)
        leaked = any(alice.home.joinpath(".claude_karma").rglob(f"{s_carol}.jsonl")) or \
                 any(bob.home.joinpath(".claude_karma").rglob(f"{s_carol}.jsonl"))
        steps.check("carol receive-only: her session did NOT leak out", not leaked)

        # Team B: bob(leader) + dave, same device overlapping teams
        bob.api("POST", "/sync/teams", {"name": "team-b"})
        join_member(bob, dave, "team-b", steps)
        encoded_b = "-Users-sim-side-project"
        s_bob_b = bob.seed_session(encoded_b, "bob session for team b")
        bob.api("POST", "/sync/teams/team-b/projects",
                {"git_identity": "sim/side-project", "encoded_name": encoded_b})
        dave.api("PUT", "/sync/teams/team-b/prefs", {"new_project_policy": "auto_accept"})

        def dave_accepted():
            subs = (dave.api_try("GET", "/sync/subscriptions") or {}).get("subscriptions", [])
            return any(s["project_git_identity"] == "sim/side-project" and s["status"] == "accepted"
                       for s in subs)
        steps.wait_for("dave auto-accepted team-b project", dave_accepted, timeout=240, interval=3)
        bob.api("POST", "/sync/package?team_name=team-b")
        steps.wait_for(
            "dave received bob's team-b session",
            lambda: any(dave.home.joinpath(".claude_karma").rglob(f"{s_bob_b}.jsonl")),
            timeout=300, interval=3,
        )
        # Cross-team isolation: dave (team-b only) must never see team-a data
        time.sleep(10)
        crossed = any(dave.home.joinpath(".claude_karma").rglob(f"{s_alice}.jsonl")) or \
                  any(dave.home.joinpath(".claude_karma").rglob(f"{s_bob}.jsonl"))
        steps.check("cross-team isolation: dave saw nothing from team-a", not crossed)

        # Remove member: alice removes carol -> carol auto-leaves
        alice.api("DELETE", f"/sync/teams/team-a/members/{carol.member_tag}")
        steps.wait_for(
            "carol auto-left after removal (removal signal)",
            lambda: not any(
                t["name"] == "team-a"
                for t in (carol.api_try("GET", "/sync/status") or {}).get("teams", [])
            ),
            timeout=300, interval=3,
        )
        # Dissolve team-b: dave auto-leaves
        bob.api("DELETE", "/sync/teams/team-b")
        steps.wait_for(
            "dave auto-left after team-b dissolved",
            lambda: not any(
                t["name"] == "team-b" and t["status"] == "active"
                for t in (dave.api_try("GET", "/sync/status") or {}).get("teams", [])
            ),
            timeout=300, interval=3,
        )
        # team-a must survive team-b's dissolution on bob's machine
        bob_teams = (bob.api_try("GET", "/sync/status") or {}).get("teams", [])
        steps.check("team-a survived team-b dissolution on bob",
                    any(t["name"] == "team-a" and t["status"] == "active" for t in bob_teams))

        return steps.summary()
    finally:
        if "--keep" not in sys.argv:
            for p in peers:
                p.stop()
        else:
            log("--keep: stacks left running")
            for p in peers:
                log(f"  peer{p.index} {p.user_id}: api={p.api_url} st={p.st_url} home={p.home}")


if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "two"
    ok = scenario_two() if scenario == "two" else scenario_four()
    sys.exit(0 if ok else 1)
