# Feature Definition: Agent Walkie-Talkie

## Section 1: Scope & Sub-Features

### Purpose
Enable two Claude Code sessions on different physical machines to coordinate actions during multi-device testing. A developer sits at one machine (commander) and orchestrates a test scenario; the other machine (responder) runs autonomously, executing requested actions and reporting results — all communicated via a temporary git branch.

### Problem Today
Testing sync v4 requires 2 machines (leader + member). The developer manually:
1. Runs a Claude session on Machine A → does an action
2. Switches to Machine B → runs another session for the next step
3. When B hits a bug → fix, commit, push
4. Switch back to A → pull, continue
5. The git log becomes the informal communication channel

This is slow, error-prone, and loses context between sessions.

### The Gap We Fill

No existing tool combines all 5 properties needed for multi-device testing with AI agents:

| Property | What It Means | Who Gets Close | Why They Fall Short |
|----------|--------------|----------------|-------------------|
| **Cross-physical-machine** | Two independent machines coordinate | AutoGen (gRPC), Walkie (P2P) | AutoGen needs a broker server; Walkie needs live P2P connection |
| **Zero new infrastructure** | Works with what developers already have | Walkie (P2P daemon) | Walkie requires a background daemon; claude-code-by-agents requires open HTTP ports |
| **Async & durable** | Messages survive crashes, full audit trail | mcp_agent_mail (git+MCP) | Requires a running MCP server alongside git |
| **LLM-native** | Natural language instructions, not typed functions | CrewAI, AutoGen | Single-machine only; no physical machine isolation |
| **Claude Code native** | Leverages existing skills, tools, worktrees | Agent Teams (Anthropic) | Local filesystem only — inboxes don't cross machines |

**Closest competitor**: [Walkie](https://github.com/vikasprogrammer/walkie) (vikasprogrammer) — P2P encrypted agent chat with a Claude Code skill. But it's real-time/ephemeral (no persistence, no offline support, no audit trail, no structured test scenarios). We are async/durable/structured.

**Structural analog**: Claude Code's own Agent Teams (Feb 2026) uses JSON inbox files on disk (`~/.claude/<team>/inboxes/<agent>.json`). Our product is architecturally identical — except the inboxes are git-committed, making them cross-machine.

### Product Layer Model

We build a thin protocol layer on top of two powerful platforms that already exist:

```
┌─────────────────────────────────────────────────────────────┐
│                    SCENARIO LAYER (we build)                │
│  YAML test definitions, step sequencing, variable           │
│  resolution, step tracking, pass/fail evaluation            │
│  → walkie/scenario.py                                       │
├─────────────────────────────────────────────────────────────┤
│                    PROTOCOL LAYER (we build)                │
│  Channel lifecycle (create/join/stop/cleanup),              │
│  JSON message format, sequential IDs, message tracking,     │
│  intervention/guidance flow                                 │
│  → walkie/channel.py, walkie/messages.py                    │
├─────────────────────────────────────────────────────────────┤
│                    SKILL LAYER (we build)                   │
│  Claude Code skills that teach the LLM the protocol:       │
│  /walkie start, /walkie join, /walkie run, /walkie stop     │
│  Skills are prompts, not code — they instruct the LLM      │
├─────────────────────────────────────────────────────────────┤
│               CLAUDE CODE (we leverage — not ours)          │
│  LLM interpretation, Bash/Read/Write/Edit tools,            │
│  API calls via curl, DB queries via sqlite3,                │
│  error handling, improvisation, natural language             │
├─────────────────────────────────────────────────────────────┤
│               GIT (we leverage — not ours)                  │
│  Branch isolation (walkie/{name}), push/pull transport,     │
│  commit history as audit log, SSH/HTTPS auth,               │
│  NAT traversal, offline message queuing                     │
└─────────────────────────────────────────────────────────────┘
```

**What we build**: 3 thin Python modules + 6 Claude Code skills
**What we leverage**: Claude Code (executor) + Git (transport + auth + persistence)
**What we don't build**: execution engine, transport layer, auth system, message broker

### Sub-Features

1. **Channel Setup** — Create a temporary `walkie/{test-name}` branch for communication
   - Triggered by: Commander runs `/walkie start --name sync-test-001`
   - Depends on: Git repo with remote, both machines can push/pull

2. **Scenario Definition** — Define a multi-step test scenario in YAML with actors, actions, and expected outcomes
   - Triggered by: Commander creates or references a scenario file
   - Depends on: Channel setup

3. **Message Exchange** — Write/read JSON message files via git push/pull
   - Triggered by: Commander sends action, responder detects via git pull loop
   - Depends on: Channel setup

4. **Action Execution** — Responder parses messages and executes API calls, CLI commands, DB queries, Syncthing checks
   - Triggered by: New message detected in `.walkie/messages/`
   - Depends on: Message exchange, local API server running

5. **State Capture** — Snapshot relevant DB tables and system state on request
   - Triggered by: Commander requests state, or scenario step requires it
   - Depends on: Action execution

6. **Intervention Handling** — Responder reports back when it hits an error or needs clarification
   - Triggered by: Action fails, unexpected state, or ambiguous instruction
   - Depends on: Message exchange

7. **Channel Cleanup** — Delete the temporary branch and `.walkie/` directory after test completes
   - Triggered by: Commander runs `/walkie stop` or scenario completes
   - Depends on: Channel setup

### Not In Scope
- Real-time communication (sub-second latency)
- More than 2 machines (v1 is pair-only)
- Syncthing as transport (can't test Syncthing with Syncthing)
- Automatic responder startup (manual for MVP)
- Persistent message history across tests (branch is deleted)
- UI/frontend for walkie-talkie (CLI only)

---

## Section 2: Actors & Roles

| Actor | Type | Capabilities | Restrictions |
|-------|------|-------------|-------------|
| **Developer** | human | Starts walkie session on commander, writes scenario, monitors progress, intervenes when responder is stuck | Must be present on commander machine |
| **Commander Session** | Claude Code session (Machine A) | Send action messages, receive responses, run local actions, orchestrate scenario flow, display results to developer | Cannot directly execute on Machine B |
| **Responder Session** | Claude Code session (Machine B) — **LLM-driven** | Poll for messages, interpret action specs, execute locally using judgement, capture state, report results, request intervention. May improvise when action specs are ambiguous or when encountering unexpected state. | Cannot initiate — only reacts to messages. Cannot modify the scenario. Must not invent steps or skip steps. |
| **Git Remote** | system (GitHub) | Store and relay messages between machines via push/pull | 5-10s latency per round trip |
| **Local API Server** | system (per machine) | Execute sync endpoints, serve DB state | Must be running on both machines |
| **Syncthing** | external (per machine) | Sync files between machines (the system under test) | Not used as walkie transport |

**Critical rules:**
- Commander is the **orchestrator** — it drives the test flow
- Responder is **autonomous but obedient** — executes what it's told, reports back, asks for help when stuck
- Both sessions are **LLM-driven Claude Code sessions** — they interpret natural language instructions, use Claude Code's native tools (Bash, Read, Write, etc.) to execute, and can improvise when things go wrong
- Communication is **async** — 5-10s git push/pull latency between each message
- The developer reads results on the commander side — they don't switch machines
- **We don't build an executor** — Claude Code already knows how to make API calls, run CLI commands, query databases, and read files. Our product is the *protocol* (message format, channel lifecycle, scenario definition), not the execution engine.

---

## Section 3: Vocabulary

| Term | Definition | NOT the same as |
|------|-----------|-----------------|
| **channel** | A temporary git branch (`walkie/{name}`) containing `.walkie/` directory for message exchange | chat room, IRC channel — this is git-based, async |
| **commander** | The Claude Code session the developer is sitting at. Drives the scenario. | leader (sync concept) — commander is about the test session, not sync role |
| **responder** | The autonomous Claude Code session on the remote machine. Executes actions. | member (sync concept) — responder is about the test session |
| **message** | A JSON file in `.walkie/messages/` representing one action or response | git commit — a commit may contain multiple messages |
| **scenario** | A YAML file defining a sequence of steps with actors, actions, and expected outcomes | test case — a scenario is a coordinated multi-machine test |
| **step** | One action in a scenario, assigned to an actor (commander or responder) | message — a step may generate multiple messages (action + response) |
| **intervention** | Responder reports back that it needs human/commander guidance | error — not all interventions are errors (could be ambiguous instructions) |
| **action** | A natural language instruction with a structured category hint. The LLM interprets and executes using Claude Code's native tools. | message — action is what to DO, message is how it's communicated |
| **category** | A hint classifying what kind of action to perform (api, cli, db_query, etc.). Guides the LLM, not a rigid execution spec. | action type — category is metadata, not a dispatch key |
| **state snapshot** | A capture of relevant DB tables, Syncthing config, or filesystem state at a point in time | log — snapshot is structured data, not narrative |
| **round trip** | Commander sends action → responder executes → responder sends response → commander receives. ~10-20s including 2 git push/pull cycles. | message — a round trip is 2 messages |

---

## Section 4: State Models

### State Model: Channel

| State | Meaning |
|-------|---------|
| CREATED | Branch created, `.walkie/channel.json` initialized, not yet started |
| ACTIVE | Both commander and responder are connected, scenario running |
| WAITING | Responder requested intervention, commander hasn't responded yet |
| COMPLETED | Scenario finished (all steps done or explicitly stopped) |
| CLEANED | Branch deleted, `.walkie/` removed |

| From | To | Triggered By | Side Effects | Idempotent? |
|------|-----|-------------|-------------|-------------|
| — | CREATED | Commander `/walkie start` | Create branch, `.walkie/` dir, `channel.json`, push | Yes |
| CREATED | ACTIVE | Responder detects channel and confirms | Update `channel.json` with responder info | Yes |
| ACTIVE | WAITING | Responder sends intervention message | Commander notified | Yes |
| WAITING | ACTIVE | Commander responds to intervention | Responder continues | Yes |
| ACTIVE | COMPLETED | Last scenario step finished or `/walkie stop` | Write completion summary | No |
| COMPLETED | CLEANED | Commander `/walkie cleanup` | Delete branch locally + remote | No |

### State Model: Scenario Step

| State | Meaning |
|-------|---------|
| PENDING | Step defined but not yet started |
| EXECUTING | Actor is executing the action |
| PASSED | Action completed, outcome matches expected |
| FAILED | Action completed, outcome doesn't match expected |
| BLOCKED | Action cannot proceed (waiting for intervention) |
| SKIPPED | Step was skipped (dependency failed or manually skipped) |

| From | To | Triggered By | Side Effects | Idempotent? |
|------|-----|-------------|-------------|-------------|
| PENDING | EXECUTING | Previous step completed, actor picks up next step | Write action message | Yes |
| EXECUTING | PASSED | Action result matches `expect` | Write response message with result | Yes |
| EXECUTING | FAILED | Action result doesn't match `expect` | Write response with actual vs expected | Yes |
| EXECUTING | BLOCKED | Action hits error or ambiguity | Write intervention request | Yes |
| BLOCKED | EXECUTING | Commander responds with guidance | Retry action | Yes |
| PENDING | SKIPPED | Dependency step failed and `on_fail: skip_rest` | Log skip reason | Yes |

### State Model: Message

| State | Meaning |
|-------|---------|
| WRITTEN | JSON file created in `.walkie/messages/` |
| COMMITTED | File committed to git |
| PUSHED | Commit pushed to remote |
| RECEIVED | Other party pulled and read the message |
| ACKNOWLEDGED | Other party sent a response referencing this message |

Messages are immutable once written. No state transitions on the message itself — the lifecycle is implicit from the git log.

**Critical questions answered:**
1. **Initiator state**: Commander stays ACTIVE. Sending a message doesn't change channel state.
2. **Late joiner**: Responder must join before scenario starts. No mid-scenario joining.
3. **Idempotency**: Messages have sequential IDs. Duplicate pulls don't re-process already-seen messages.
4. **Cross-system sync**: Messages propagate via `git push` → `git pull`. ~5-10s per hop.
5. **Cascade**: Channel COMPLETED → all remaining PENDING steps become SKIPPED.

---

## Section 5: Workflows

### Workflow 5.1: Start Walkie Session

**Trigger**: Developer runs `/walkie start --name sync-test-001 --scenario scenarios/full-sync-lifecycle.yaml`
**Preconditions**: Git repo with remote, current branch is the branch to test

| # | Actor | Action | Data | Can Fail? | Failure Handling |
|---|-------|--------|------|-----------|-----------------|
| 1 | Commander | Create branch `walkie/sync-test-001` off current branch | branch name | Branch exists | Append timestamp suffix |
| 2 | Commander | Create `.walkie/` directory structure | — | — | — |
| 3 | Commander | Write `channel.json` with commander info | member_tag, machine, timestamp | — | — |
| 4 | Commander | Copy scenario YAML to `.walkie/scenario.yaml` | scenario content | File not found | Error: specify valid scenario |
| 5 | Commander | Commit + push branch | — | Remote down | Fatal — can't proceed without remote |
| 6 | Commander | Display: "Channel ready. Start responder on Machine B with: `/walkie join walkie/sync-test-001`" | — | — | — |

### Workflow 5.2: Responder Joins Channel

**Trigger**: Developer manually runs `/walkie join walkie/sync-test-001` on Machine B
**Preconditions**: Branch exists on remote, Machine B has the repo

| # | Actor | Action | Data | Can Fail? | Failure Handling |
|---|-------|--------|------|-----------|-----------------|
| 1 | Responder | `git fetch && git checkout walkie/sync-test-001` | branch name | Branch not found | Error: check branch name |
| 2 | Responder | Read `channel.json`, validate | commander info | Invalid format | Error: corrupted channel |
| 3 | Responder | Read `scenario.yaml`, parse all steps | scenario content | Parse error | Report to developer |
| 4 | Responder | Update `channel.json` with responder info AND local variables | member_tag, machine, pairing_code, device_id, timestamp | — | — |
| 5 | Responder | Commit + push confirmation (commit message: "walkie: responder joined with variables") | — | — | — |
| 6 | Responder | Start git pull loop (every 5s) | — | — | — |
| 7 | Responder | Enter autonomous mode: wait for first message | — | — | — |

### Workflow 5.3: Scenario Execution (Choreography)

**Trigger**: Both commander and responder connected, scenario loaded
**Preconditions**: Channel ACTIVE, commander has pulled responder's join commit (with published variables)

**Synchronization**: No formal checkpoints needed. The message exchange pattern enforces ordering — the responder cannot execute step N until the commander sends it, and the commander won't send step N+1 until it receives the response for step N. Consecutive same-actor steps (e.g., commander steps 1→2→3) execute locally in sequence without message exchange.

**Step timeout**: Each step has a default timeout of 60s (configurable per-step via `step_timeout` in YAML). If the commander receives no response within `step_timeout + 20s` (accounting for 2 git round trips), the step is marked BLOCKED and the developer is notified.

```
For each step in scenario:
  1. Resolve any ${{variables}} in the step definition
     - If resolution fails → BLOCK, request intervention
  2. Determine actor (commander or responder)
  3. If actor is local → execute action locally
  4. If actor is remote → write action message, push, wait for response (with timeout)
  5. Read response → compare result with expected outcome
  6. Mark step PASSED/FAILED/BLOCKED
  7. If BLOCKED → wait for intervention
  8. If FAILED and on_fail=stop → stop scenario
  9. Continue to next step
```

| # | Actor | Action | Data | Can Fail? | Failure Handling |
|---|-------|--------|------|-----------|-----------------|
| 1 | Commander | Read next step from scenario | step definition | No more steps | Scenario complete |
| 2 | Commander | If step.actor == "commander": execute locally | action, expect | Action fails | Mark FAILED, check on_fail |
| 3 | Commander | If step.actor == "responder": write action message | action JSON | — | — |
| 4 | Commander | Commit + push | — | Push fails | Retry once |
| 5 | Responder | Pull, detect new message | message JSON | — | — |
| 6 | Responder | Parse action, execute locally | API/CLI/DB/Syncthing | Action fails | Write intervention message |
| 7 | Responder | Compare result with expected | result vs expect | Mismatch | Mark FAILED in response |
| 8 | Responder | Write response message + commit + push | result JSON | — | — |
| 9 | Commander | Pull, read response | response JSON | — | — |
| 10 | Commander | Display result to developer, mark step PASSED/FAILED | — | — | — |

### Workflow 5.4: Intervention Handling

**Trigger**: Responder encounters error, unexpected state, or ambiguous instruction

| # | Actor | Action | Data | Can Fail? | Failure Handling |
|---|-------|--------|------|-----------|-----------------|
| 1 | Responder | Write intervention message (type=intervention) | error details, context, what it tried | — | — |
| 2 | Responder | Commit + push | — | — | — |
| 3 | Responder | Enter WAITING state (stop processing new steps) | — | — | — |
| 4 | Commander | Pull, detect intervention | intervention JSON | — | — |
| 5 | Commander | Display to developer: "Responder needs help: {details}" | — | — | — |
| 6 | Developer | Provides guidance to commander | free text | — | — |
| 7 | Commander | Write guidance message (type=guidance) | instructions | — | — |
| 8 | Commander | Commit + push | — | — | — |
| 9 | Responder | Pull, read guidance, resume execution | — | — | — |

### Workflow 5.5: Commander UX (Developer View)

**What the developer sees**: A step-by-step log in the terminal, similar to a test runner. Each step prints as it completes.

```
🟢 Step 1/12: Create team ........................... PASSED (342ms)
🟢 Step 2/12: Share project ......................... PASSED (215ms)
⏳ Step 3/12: Add responder as member ............... WAITING (sent to responder)
🟢 Step 3/12: Add responder as member ............... PASSED (1.2s + 12s transport)
   → responder: {"member_tag": "jayant.mac-mini", "status": "added"}
⏳ Step 4/12: Run reconciliation .................... WAITING (sent to responder)
🔴 Step 6/12: Accept subscription ................... FAILED
   → expected: status 200   actual: status 404
   → responder note: "Subscription not found. Metadata may not have synced yet."
🟡 Step 6/12: INTERVENTION REQUESTED
   → "Should I run reconciliation again, or is there a bug?"
   Developer: "Run reconciliation first, then retry"
⏳ Step 6/12: Retrying with guidance ...
🟢 Step 6/12: Accept subscription ................... PASSED (after retry)
```

The developer watches passively. They only type when:
- An intervention is requested (responder needs help)
- They want to stop (`/walkie stop`)

No interactive confirmation per step — the scenario runs automatically.

### Workflow 5.6: Recovery from Crash

**Trigger**: Responder session crashes mid-step and is restarted via `/walkie join`

| # | Actor | Action | Data | Can Fail? | Failure Handling |
|---|-------|--------|------|-----------|-----------------|
| 1 | Responder | Re-checkout walkie branch, pull latest | — | Branch gone | Channel was cleaned up, nothing to recover |
| 2 | Responder | Read `channel.json` state | channel state | COMPLETED | Session is over, exit |
| 3 | Responder | Scan `.walkie/messages/` for last message | sequence IDs | — | — |
| 4 | Responder | Determine: was the last action responded to? | action vs response messages | — | — |
| 5 | Responder | Write intervention message: "Responder restarted. Last known state: step {N}, {responded/not responded}. How should I proceed?" | crash context | — | — |
| 6 | Responder | Commit + push intervention | — | — | — |
| 7 | Commander | Display intervention to developer | — | — | — |
| 8 | Developer | Provides guidance: "retry step N" or "skip to step N+1" | free text | — | — |
| 9 | Commander | Write guidance, push | — | — | — |
| 10 | Responder | Resume based on guidance | — | — | — |

**Why intervention over auto-retry**: Some steps are not idempotent (e.g., creating a team that already exists). The LLM responder doesn't know if the previous attempt partially succeeded. Asking the commander (who has the developer) is safer.

---

## Section 6: Data Contracts

### Channel File (`.walkie/channel.json`)
```json
{
  "name": "sync-test-001",
  "created_at": "2026-03-19T10:00:00Z",
  "base_branch": "worktree-syncthing-sync-design",
  "state": "active",
  "commander": {
    "member_tag": "jayant.macbook-pro",
    "machine": "Jayants-MacBook-Pro",
    "joined_at": "2026-03-19T10:00:00Z"
  },
  "responder": {
    "member_tag": "jayant.mac-mini",
    "machine": "Jayants-Mac-mini",
    "pairing_code": "amF5YW50...",
    "device_id": "DEV-MINI-ABC",
    "joined_at": "2026-03-19T10:00:15Z"
  },
  "scenario": "scenarios/full-sync-lifecycle.yaml",
  "current_step": 3,
  "steps_total": 12,
  "steps_passed": 2,
  "steps_failed": 0
}
```

### Scenario File (`.walkie/scenario.yaml`)
```yaml
name: "Full Sync Lifecycle"
description: "Test complete flow: team creation → project sharing → subscription → session sync"
timeout: 600  # seconds for entire scenario
step_timeout: 60  # default per-step timeout in seconds (overridable per step)

setup:
  commander:
    require: ["API server running on port 8000", "Syncthing running", "sync initialized"]
  responder:
    require: ["API server running on port 8000", "Syncthing running", "sync initialized"]

steps:
  - id: 1
    actor: commander
    name: "Create team"
    action:
      type: api
      method: POST
      path: /sync/teams
      body: { "name": "walkie-test" }
    expect:
      status: 201
      body_contains: { "name": "walkie-test" }

  - id: 2
    actor: commander
    name: "Share project"
    action:
      type: api
      method: POST
      path: /sync/teams/walkie-test/projects
      body: { "git_identity": "jayantdevkar/claude-code-karma", "encoded_name": "-Users-jayantdevkar-Documents-GitHub-claude-karma" }
    expect:
      status: 201

  - id: 3
    actor: commander
    name: "Add responder as member"
    action:
      type: api
      method: POST
      path: /sync/teams/walkie-test/members
      body: { "pairing_code": "${{responder.pairing_code}}" }
    expect:
      status: 201

  - id: 4
    actor: responder
    name: "Run reconciliation to discover team"
    action:
      type: api
      method: POST
      path: /sync/reconcile
    expect:
      status: 200

  - id: 5
    actor: responder
    name: "Verify team discovered"
    action:
      type: api
      method: GET
      path: /sync/status
    expect:
      body_contains: { "teams": [{ "name": "walkie-test" }] }

  - id: 6
    actor: responder
    name: "Accept subscription with direction BOTH"
    action:
      type: api
      method: POST
      path: /sync/subscriptions/walkie-test/jayantdevkar%2Fclaude-code-karma/accept
      body: { "direction": "both" }
    expect:
      status: 200
      body_contains: { "status": "accepted", "direction": "both" }

  - id: 7
    actor: commander
    name: "Run reconciliation to sync subscription status"
    action:
      type: api
      method: POST
      path: /sync/reconcile
    expect:
      status: 200

  - id: 8
    actor: commander
    name: "Verify responder's subscription synced"
    action:
      type: state_snapshot
      tables: ["sync_subscriptions"]
      filter: { "member_tag": "${{responder.member_tag}}" }
    expect:
      rows_contain: { "status": "accepted" }

  - id: 9
    actor: commander
    name: "Package sessions"
    action:
      type: api
      method: POST
      path: /sync/package
    expect:
      status: 200

  - id: 10
    actor: responder
    name: "Wait for sessions to arrive"
    action:
      type: wait
      condition: "inbox folder has manifest.json"
      timeout: 120
      poll_interval: 10
    expect:
      condition_met: true

  - id: 11
    actor: responder
    name: "Verify received sessions"
    action:
      type: state_snapshot
      tables: ["sessions"]
      filter: { "source": "remote" }
    expect:
      row_count_gte: 1

  - id: 12
    actor: commander
    name: "Cleanup: dissolve team"
    action:
      type: api
      method: DELETE
      path: /sync/teams/walkie-test
    expect:
      status: 200

on_fail: stop
```

### Variable Resolution

Variables use `${{namespace.key}}` syntax. They are resolved at **scenario load time** (after both parties have joined), not at step execution time.

**Namespace:**

| Namespace | Source | Available After |
|-----------|--------|----------------|
| `commander.*` | `channel.json → commander` object | Channel created |
| `responder.*` | `channel.json → responder` object | Responder joins |

**Available variables:**

| Variable | Example Value |
|----------|--------------|
| `${{commander.member_tag}}` | `jayant.macbook-pro` |
| `${{commander.machine}}` | `Jayants-MacBook-Pro` |
| `${{commander.device_id}}` | `DEV-MBP-XYZ` |
| `${{responder.member_tag}}` | `jayant.mac-mini` |
| `${{responder.pairing_code}}` | `amF5YW50...` |
| `${{responder.device_id}}` | `DEV-MINI-ABC` |

**Resolution flow:**
1. Commander starts scenario → pulls latest `channel.json` (which now has responder's published variables)
2. Walk all steps, replace `${{...}}` tokens with values from `channel.json`
3. If any variable cannot be resolved → step is **BLOCKED**, intervention requested: `"Unresolved variable: {name}. Check channel.json — was it published during join?"`

**Not supported in v1:** Step output references (e.g., `${{step.1.response.body.id}}`). Scenario values that depend on runtime results should be hardcoded or use natural language instructions ("use the team ID from the previous step").

### Message File (`.walkie/messages/{sequence}-{actor}.json`)

Messages carry **natural language instructions** with **structured metadata** for categorization. The responder (an LLM-driven Claude Code session) interprets the instruction and uses its native tools to execute. The structure helps organize, not constrain.

**Action Message:**
```json
{
  "id": "005",
  "from": "commander",
  "timestamp": "2026-03-19T10:01:30Z",
  "type": "action",
  "step_id": 3,
  "step_name": "Add responder as member",
  "category": "api",
  "instruction": "Call POST /sync/teams/walkie-test/members with body {\"pairing_code\": \"amF5YW50...\"}. This adds Machine B as a team member.",
  "context": {
    "method": "POST",
    "path": "/sync/teams/walkie-test/members",
    "body": { "pairing_code": "amF5YW50..." }
  },
  "expect": {
    "description": "Member should be added successfully with status 201",
    "status": 201
  },
  "step_timeout": 60
}
```

**Key design**: `instruction` is what the LLM reads. `context` is structured data that helps if the LLM needs precise values. `expect` defines what success looks like — the LLM evaluates whether the result matches.

**Response Message:**
```json
{
  "id": "006",
  "from": "responder",
  "timestamp": "2026-03-19T10:01:45Z",
  "type": "response",
  "in_reply_to": "005",
  "step_id": 3,
  "result": {
    "status": 201,
    "body": { "member_tag": "jayant.mac-mini", "device_id": "DEV-MINI", "status": "added" }
  },
  "passed": true,
  "notes": "API responded as expected. Member added to team.",
  "duration_ms": 342
}
```

**Intervention Message:**
```json
{
  "id": "007",
  "from": "responder",
  "timestamp": "2026-03-19T10:02:15Z",
  "type": "intervention",
  "step_id": 6,
  "reason": "API returned 404: Subscription not found",
  "context": "Reconciliation ran but no subscription exists. Possible timing issue — metadata may not have synced yet.",
  "tried": ["Waited 30s and retried — same result", "Checked sync_subscriptions table — 0 rows"],
  "question": "Should I run reconciliation again, or is there a bug?"
}
```

**Guidance Message (from commander after intervention):**
```json
{
  "id": "008",
  "from": "commander",
  "timestamp": "2026-03-19T10:03:00Z",
  "type": "guidance",
  "in_reply_to": "007",
  "step_id": 6,
  "instruction": "Run reconciliation first (POST /sync/reconcile), wait 10s, then retry the subscription accept."
}
```

### Action Categories

Categories are **hints**, not dispatch keys. The LLM responder reads the `instruction` field and uses Claude Code's native tools to execute. The category helps organize messages and tells the LLM what *kind* of thing to do.

| Category | What It Means | Typical LLM Approach |
|----------|--------------|---------------------|
| `api` | Make an HTTP request to local API server | Use `curl` via Bash, or `httpx` in a Python snippet |
| `cli` | Run a karma CLI command | Execute via Bash tool |
| `db_query` | Query the local SQLite database | Use `sqlite3` via Bash or read with Python |
| `syncthing_check` | Check Syncthing state via its REST API | `curl` to Syncthing API (localhost:8384) |
| `file_check` | Verify file/directory existence or contents | Use Read tool or `ls`/`cat` via Bash |
| `state_snapshot` | Capture DB tables or system state | Combine `sqlite3` queries + file reads |
| `wait` | Poll a condition until met or timeout | Loop with sleep in Bash, checking condition each iteration |
| `shell` | Run an arbitrary shell command | Execute via Bash tool |
| `observe` | Look at something and report what you see (no mutation) | Read files, query APIs, describe state |

---

## Section 7: Cross-Cutting Concerns

### Trust Model
- **Both machines are developer-owned**. The walkie channel is created by the developer, the responder is started by the developer on their own machine. There is no untrusted input.
- **The git remote is the developer's repo**. Messages flow through a private GitHub repo. No third-party access.
- **The branch is ephemeral**. Created for one test, deleted after. No persistent attack surface.
- **All action types are allowed**, including `shell` and `cli`. The responder is a Claude Code session — it already has full shell access on Machine B. Walkie messages don't grant any capability the responder doesn't already have.
- **No allowlisting or sandboxing** in v1. If the developer writes a scenario with `shell: rm -rf /`, that's on them — same as typing it directly into Claude Code.

### Identity
- **Within a session**: Commander and responder identify themselves by `member_tag` from SyncConfig
- **Across machines**: Messages use `member_tag` as the author identity (same as sync system)
- **Channel identity**: The branch name `walkie/{test-name}` is the unique channel identifier
- **Message identity**: Sequential integer IDs (001, 002, ...) — no UUIDs needed within a single test

### Cleanup & Teardown
- `/walkie stop` → write COMPLETED to `channel.json`, push
- `/walkie cleanup` → delete branch locally + `git push origin --delete walkie/{name}`
- If test crashes mid-scenario → branch persists, can be manually deleted
- No DB rows created by walkie itself — cleanup is purely git
- Responder exits autonomous mode when channel state = COMPLETED

### Migration
- N/A — this is a new product, no prior version

### Timing & Ordering
| Scenario | Max Delay | Acceptable? |
|----------|-----------|-------------|
| Commander sends action → responder receives | 5-10s (git push + pull cycle) | Yes |
| Responder sends response → commander receives | 5-10s | Yes |
| Full round trip (action → response) | 10-20s + execution time | Yes |
| Responder git pull loop interval | 5s | Yes — configurable |
| Syncthing sync (the thing being tested) | Variable (seconds to minutes) | Test must account for this with `wait` actions |

**Race condition**: Commander pushes 2 messages before responder pulls → responder processes both in order (sorted by filename/sequence ID). No conflict.

**Git conflict**: Only one party writes at a time (request-response pattern). Commander waits for response before sending next action. No concurrent writes to same file. No formal checkpoint mechanism needed — the message exchange pattern inherently enforces ordering. The responder cannot execute step N until the commander sends it, and the commander won't send step N+1 until it receives the response for step N.

### Recovery

**Responder crash mid-step**: On restart, the responder re-joins the channel (`/walkie join`), reads `channel.json` and `.walkie/messages/` to determine last known state, then sends an **intervention** asking the commander how to proceed. It does NOT auto-retry — some steps are not idempotent, and the LLM can't know if the previous attempt partially succeeded.

**Commander crash**: The developer restarts the commander session and runs `/walkie status` to see current progress. The commander reads the latest messages from git, determines where the scenario left off, and resumes. If the responder is in WAITING state (sent an intervention), the commander sees it and can respond.

**Git push fails**: Retry once after 5s. If still fails, report to the developer. Do not silently drop messages.

**Stale channel**: If a walkie branch exists from a previous crashed run, `/walkie start` with the same name will detect it and ask: "Channel walkie/{name} already exists. Resume or clean up and restart?"

### Multi-Tenancy / Shared Resources
- Each walkie session is on its own branch — complete isolation
- Multiple walkie sessions can run simultaneously (different branch names)
- The repo itself is shared — walkie branches coexist with feature branches
- `.walkie/` directory is only on walkie branches, never merged to main

---

## Section 8: Verification Matrix

### 8.1 Channel Lifecycle
| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1 | `/walkie start` creates branch with `.walkie/` directory | `git branch -a`, `ls .walkie/` | [ ] |
| 2 | `channel.json` contains commander info | Read file | [ ] |
| 3 | Responder `/walkie join` updates `channel.json` with responder info | Read file after join | [ ] |
| 4 | `/walkie stop` sets channel state to COMPLETED | Read `channel.json` | [ ] |
| 5 | `/walkie cleanup` deletes branch locally and remotely | `git branch -a` | [ ] |

### 8.2 Message Exchange
| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1 | Commander writes message → push → responder detects within 10s | Timestamp diff | [ ] |
| 2 | Responder writes response → push → commander detects within 10s | Timestamp diff | [ ] |
| 3 | Messages are sequential (no gaps in IDs) | List `.walkie/messages/` | [ ] |
| 4 | Duplicate pull doesn't re-process already-seen messages | Check message tracking state | [ ] |

### 8.3 Scenario Execution
| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1 | All steps executed in order | Message sequence in `.walkie/messages/` | [ ] |
| 2 | Commander steps executed locally (not sent to responder) | No message for commander-actor steps | [ ] |
| 3 | Responder steps sent as messages and executed remotely | Message exists for responder-actor steps | [ ] |
| 4 | PASSED steps have matching actual vs expected | Response message `passed: true` | [ ] |
| 5 | FAILED steps show actual vs expected diff | Response message with both values | [ ] |
| 6 | Scenario stops on first failure (when `on_fail: stop`) | No messages after failed step | [ ] |
| 7 | `wait` action polls until condition met or timeout | Response shows `waited_seconds` | [ ] |

### 8.4 Intervention Flow
| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1 | Responder sends intervention with context and question | Message type=intervention | [ ] |
| 2 | Commander displays intervention to developer | Terminal output | [ ] |
| 3 | Developer guidance sent back to responder | Message type=guidance | [ ] |
| 4 | Responder resumes after receiving guidance | Next response message after guidance | [ ] |

### 8.5 Variable Resolution
| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1 | Responder publishes pairing_code, device_id to `channel.json` during join | Read `channel.json` after join commit | [ ] |
| 2 | `${{responder.pairing_code}}` resolves correctly in scenario steps | Check resolved action message body | [ ] |
| 3 | Unresolvable variable `${{responder.nonexistent}}` triggers BLOCKED + intervention | Message type=intervention with variable name | [ ] |
| 4 | Commander pulls responder's join commit before resolving variables | Git log shows pull before scenario start | [ ] |

### 8.6 Commander UX
| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1 | Each step prints status line as it completes | Terminal output | [ ] |
| 2 | Remote steps show WAITING while waiting for responder | Terminal output during execution | [ ] |
| 3 | Intervention displays responder's question to developer | Terminal output | [ ] |
| 4 | Developer can type `/walkie stop` to halt scenario | Channel state = COMPLETED, remaining steps SKIPPED | [ ] |

### 8.7 Recovery
| # | Assertion | Verify By | Pass? |
|---|-----------|-----------|-------|
| 1 | Responder crash → rejoin → sends intervention with last known state | Message type=intervention after rejoin | [ ] |
| 2 | Commander crash → restart → reads latest messages and resumes | Scenario continues from correct step | [ ] |
| 3 | Stale channel detected on `/walkie start` with existing name | Prompt: "Resume or clean up?" | [ ] |

### 8.8 Edge Cases
| # | Scenario | Expected Behavior | Pass? |
|---|----------|-------------------|-------|
| E1 | Responder is offline when commander sends action | Message queues in git. Responder processes on next pull | [ ] |
| E2 | Git push fails (network down) | Retry once after 5s. If still fails, report to developer | [ ] |
| E3 | Responder's API server is not running | Intervention: "API server not responding on port 8000" | [ ] |
| E4 | Scenario references `${{responder.pairing_code}}` | Resolved from `channel.json` (published during join) | [ ] |
| E5 | Two walkie sessions on same branch name | Append timestamp suffix to prevent collision | [ ] |
| E6 | Scenario step timeout exceeded | Mark step BLOCKED, notify developer (timeout + 20s for transport) | [ ] |
| E7 | Commander sends `/walkie stop` mid-scenario | All remaining steps SKIPPED, channel COMPLETED | [ ] |
| E8 | Responder crashes mid-execution | On rejoin, sends intervention asking commander how to proceed | [ ] |
| E9 | Responder LLM misinterprets instruction | Result doesn't match expect → FAILED, developer sees actual vs expected | [ ] |
| E10 | Responder improvises successfully (e.g., retries on transient error) | Response notes field explains what it did differently | [ ] |
| E11 | Consecutive commander steps (1→2→3) with no actor switch | All execute locally, no messages sent, no wait | [ ] |

---

## Implementation Components Needed

### Design Philosophy

**Claude Code IS the executor. Git IS the transport. Our product is the protocol.**

We don't build an execution engine — Claude Code already knows how to make API calls, run CLI commands, query databases, read files, and handle errors. We don't build a transport layer — Git already provides branch isolation, push/pull, and commit history. Our product is a *thin protocol layer* that gives two Claude Code sessions a structured way to coordinate.

| Concern | Provided By | We Build |
|---------|-------------|----------|
| Action execution | Claude Code (LLM + native tools) | Nothing — the LLM reads instructions and uses Bash, Read, Write, etc. |
| Message transport | Git (push/pull to shared remote) | Nothing — standard git commands |
| Branch isolation | Git branches | Just the naming convention (`walkie/{name}`) |
| Natural language interpretation | Claude Code (LLM) | Nothing — the LLM interprets `instruction` field |
| Error handling / improvisation | Claude Code (LLM) | Nothing — the LLM decides when to retry, when to ask for help |
| **Channel lifecycle** | — | **Yes** — create/join/stop/cleanup channel state |
| **Message protocol** | — | **Yes** — JSON message format, sequential IDs, message tracking |
| **Scenario definition** | — | **Yes** — YAML schema, variable resolution, step tracking |
| **Polling loop** | — | **Yes** — git pull every 5s, detect new messages |

### Claude Code Skills (Entry Points)

These are Claude Code skills (YAML + system prompt) that instruct the LLM how to follow the walkie protocol. They don't contain execution logic — they teach the LLM the protocol.

| Skill | Role | What It Teaches the LLM |
|-------|------|------------------------|
| `/walkie start` | Commander | Create walkie branch, init `.walkie/` dir, write `channel.json`, push, display join instructions |
| `/walkie join` | Responder | Checkout branch, read channel, publish local variables to `channel.json`, push, start poll loop, enter autonomous mode |
| `/walkie run` | Commander | Load scenario, resolve variables, execute steps in order, send messages to responder, display step-by-step log |
| `/walkie stop` | Either | Write COMPLETED to `channel.json`, push, exit |
| `/walkie cleanup` | Commander | Delete branch locally + remotely |
| `/walkie status` | Either | Read `channel.json` + latest messages, display current state |

### Thin Protocol Layer (Python Helpers)

Minimal Python utilities that the Claude Code skills call. These handle the mechanical parts that are tedious for an LLM to do manually every time (sequential ID generation, JSON schema validation).

| Module | Purpose | Why Not Just LLM? |
|--------|---------|-------------------|
| `walkie/channel.py` | Read/write `channel.json`, state transitions | Schema consistency across sessions |
| `walkie/messages.py` | Sequential ID generation, message file I/O, "last seen" tracking | IDs must be gap-free; tracking must be reliable |
| `walkie/scenario.py` | Parse YAML scenarios, resolve `${{variables}}`, track step state | Variable resolution needs to be deterministic |

**Not needed** (Claude Code handles these natively):
- ~~`executor.py`~~ — The LLM reads the instruction and executes using its own tools
- ~~`git_transport.py`~~ — The LLM runs `git push`/`git pull` directly
- ~~`responder.py`~~ — The `/walkie join` skill teaches the LLM the autonomous loop
- ~~`commander.py`~~ — The `/walkie run` skill teaches the LLM the orchestration flow

### Dependencies
- `pyyaml` — scenario YAML parsing (used by `walkie/scenario.py`)
- `git` — CLI git commands, already available on both machines
- No new infrastructure — uses existing git remote
- No `httpx` — Claude Code makes HTTP calls via `curl` in Bash
