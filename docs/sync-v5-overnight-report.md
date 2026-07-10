# Sync v5 — Overnight Revival Report

**Date**: 2026-07-08
**Branch**: `sync-v5-ux` (local only, in the `testing-sync` worktree — NOT pushed)
**Base**: `origin/worktree-syncthing-sync-design` (b124fe5, Jayant's v4) + `origin/main` (3eafd06) merged

## What this branch is

Jayant's sync v4 (fine-grained model **kept intact**: leader-gated teams, per-member
per-project subscriptions with directions), revived and merged with 3.5 months of
main, plus an eventing + policy layer that removes the two UX killers — hours-late
invites and approval fatigue — and a multi-peer simulation harness that verified the
whole thing end-to-end over real Syncthing transfer.

## Verified results (live simulation, real P2P transfer)

- **2-peer full lifecycle: 17/17 steps pass** (`scripts/sync_sim.py two`)
- **4-peer mesh + permutations: 28/28 steps pass** (`scripts/sync_sim.py four`)
- API tests: 2283 pass / 2 pre-existing env-dependent failures (fail identically on
  pristine main on this machine — `test_background_shells_router` indexes the real
  `~/.claude`). svelte-check: 0 errors. Production build: passes.

Measured latencies (were 60–120s best case, or **never**, before):

| Step | Time |
|---|---|
| Pairing request seen + accepted | ~6s |
| Joiner discovers team | 6–9s |
| New project offer -> policy auto-accept | 12–18s |
| Session packaged -> on peer's disk + indexed | 12–18s |
| Removal signal -> member auto-leaves | ~15s |
| Dissolution -> member auto-leaves | ~12s |

4-peer scenario also verified: 3-member mesh flows in ALL directions (not
hub-and-spoke), receive-only member receives but never leaks her own sessions,
same device in two overlapping teams, cross-team isolation (team-b member saw
nothing from team-a), and team-a surviving team-b's dissolution.

## Root-cause bugs found and fixed (all latent in v4)

1. **No reconciliation loop on fresh machines** — the worker only started in the
   API lifespan *if a team with projects existed*, and `/sync/init` never started
   it. A newly initialized joiner had NO loop at all → invites literally never
   arrived. (`services/sync_bootstrap.py`, called from lifespan + init.)
2. **Polling-only reconciliation** — nothing consumed Syncthing's event stream.
   Now `SyncthingEventListener` long-polls `/rest/events` and triggers a debounced
   reconcile within seconds; the 60s timer remains as fallback. (This is the
   60–120s → 6–18s change.)
3. **Peer subscriptions without a local row were skipped** during metadata sync
   (e.g. the leader's own accepted sub never propagates via `share_project`), so
   Phase 3 device lists excluded the sender → folders never synced.
4. **Phase 3 "recovery" created sendonly outboxes for OTHER members' tags** on
   every machine, blocking receiveonly inbox creation (folder ID taken) →
   receivers silently never got data.
5. **Receive-only could never receive** — device lists were computed from senders
   only. Now: each outbox syncs to its owner + every receive|both member.
6. **Removal/dissolution signals could never deliver** — `remove_member` unpaired
   the device and `dissolve_team` deleted the metadata folder in the same breath
   as writing the signals, severing the channel that carries them. Both now
   soft-remove (cut project folders immediately) and hard-clean via reconciliation
   sweeps after `sync_removed_unpair_grace_seconds` (default 15 min).

## UX layer added (Jayant's model untouched — policy on top)

- **Per-team new-project policy** (local-only, never synced): *Ask me each time*
  (default, classic v4) / *Accept automatically* (+ default direction) / *Receive
  only, automatically*. Schema v24 `sync_team_prefs`; applied during reconciliation
  through the same `ProjectService.accept` path the UI uses.
- **One-click Accept** on invitation cards using the team default; the 3-way
  direction picker is collapsed behind "Customize". **Accept all (N)** for bursts.
- **Sync inbox badge** in the header — `GET /sync/inbox` aggregates every pending
  decision (pending devices, folder offers, offered subscriptions).
- **Pipeline visibility**: members list shows *relay* chips (with an explanation —
  relays are the usual cause of hours-late syncs) and *last seen Xh ago* for
  offline members; sync overview shows **Live — reacting instantly** vs
  **Polling — every 60s** from real watcher state (`/sync/status.watcher`).
- Collaborate nav group (Teams/Members/Sync) restored in the redesigned header +
  homepage with new hand-drawn icons; `--nav-rose` tokens; `--radius` alias.
- `CLAUDE_KARMA_SYNCTHING_URL` setting (enables multi-instance testing).

## How to run the demo yourself

```bash
cd ~/My-Github/testing-sync
# venv with api deps (any venv with api/requirements.txt + pytest + requests)
python scripts/sync_sim.py two --keep    # leaves both stacks running
# then open http://127.0.0.1:8190 (alice) / 8191 (bob) API,
# Syncthing GUIs at 8590/8591; fake HOMEs under /tmp/karma-sync-sim/peer*
# frontend: cd frontend && npm run dev, point VITE_API_BASE at a peer
```
Syncthing v2.1.1 was installed via `brew install syncthing` (not started as a
service — the sim runs isolated instances with their own homes/ports).

## What is NOT yet verified / follow-ups

- **Real two-machine test over the internet** (relays, NAT) — the sim is
  localhost-only by design. The protocol is identical, but do one real run.
- Offline recovery and reset→rejoin (Jayant's scenarios 5–6) — still untested.
- Grace-period sweeps mean a removed member's device stays paired (inert, no
  folders) for up to 15 min — deliberate trade-off so the removal signal delivers.
- Jayant's 6 filed open-issues (`docs/open-issues/syncthing/`) still stand, plus
  the 6 known issues in his v4 status report (auto-commit transactionality,
  metadata TOCTOU, per-request HTTP connections, folder-suffix collision).
- PR #45 can be reopened from this branch once Ayush reviews.

## Update 2026-07-10: REAL two-machine test — 16/16 PASS

`scripts/sync_real_test.py` ran the full lifecycle between the Mac mini (alice)
and the MacBook Air (bob, Intel, macOS 14.8, driven over SSH + LAN HTTP) with
isolated fake HOMEs on both machines — real user data untouched. Direct TCP
(tcp-client, no relay), mini dialing outbound only (mini firewall enabled and
undisturbed). Latencies matched the localhost sim: pairing 6.6s, team discovery
11s, policy auto-accept 16.7s, session transfer mini→Air 10.2s (+6.4s to index),
Air→mini 12s. Event listeners live on both ends.

Air prep (zero-sudo, create-only): repo cloned to ~/karma-sync-test/repo with
the branch fetched from a git bundle, uv-managed Python 3.12 venv, standalone
Syncthing 2.1.2 binary in ~/karma-sync-test/bin. Remaining untested: cross-
internet relay behavior (both machines were on one LAN) and reset→rejoin.
