# Workflow Feature Design

**Date**: 2026-03-01
**Status**: Approved

## Overview

Add a "Workflow" feature to Claude Karma that lets users define multi-step automated pipelines of Claude Code sessions. Users build workflows visually in the dashboard using a Svelte Flow node editor, then execute them with a single click. Each step spawns a `claude -p` subprocess, and the dashboard tracks execution progress with links to the spawned sessions.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Definition format | Visual node editor (Svelte Flow + Dagre) | Most accessible, fits dashboard-first UX |
| Storage | SQLite (`~/.claude_karma/metadata.db`) | Already our central DB |
| Triggers | Manual only (MVP) | Keeps scope tight; add commit/hook triggers later |
| Autonomy | Fully autonomous | No approval gates for MVP |
| Session tracking | Step status + session link | Leverages existing session detail pages |
| Execution | `claude -p` subprocesses | Works with Claude subscription (no API key needed) |
| Architecture | API-driven orchestrator | FastAPI backend manages everything |

## Constraints

- **No API key** — users have Claude subscriptions, not API access. All execution via `claude` CLI.
- **No Agent SDK** — subprocess-based execution only.
- The `claude -p` command supports `--output-format json`, `--model`, `--allowedTools`, `--max-turns`, `--resume`.

## Data Model

### Tables (added to existing SQLite DB)

```sql
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    project_path TEXT,
    graph JSON NOT NULL,       -- Svelte Flow nodes[] + edges[]
    steps JSON NOT NULL,       -- [{id, prompt_template, model, tools, max_turns, condition}]
    inputs JSON,               -- [{name, type, required, default, description}]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL,       -- pending | running | completed | failed
    input_values JSON,         -- {"feature_desc": "auth module", "branch": "main"}
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    FOREIGN KEY(workflow_id) REFERENCES workflows(id)
);

CREATE TABLE workflow_run_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    status TEXT NOT NULL,       -- pending | running | completed | failed | skipped
    session_id TEXT,            -- links to claude session (existing session views)
    prompt TEXT,                -- resolved prompt after template substitution
    output TEXT,                -- claude's JSON output
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    FOREIGN KEY(run_id) REFERENCES workflow_runs(id)
);
```

### Step Definition (inside `steps` JSON)

```json
{
  "id": "test_agent",
  "prompt_template": "Write tests for these changes:\n{{ steps.extract.output }}",
  "model": "sonnet",
  "tools": ["Read", "Edit", "Bash"],
  "max_turns": 10,
  "condition": null
}
```

### Template Variables

| Variable | Source |
|----------|--------|
| `{{ steps.<id>.output }}` | Output from a previous step |
| `{{ steps.<id>.session_id }}` | Session UUID from a previous step |
| `{{ inputs.<name> }}` | User-provided input at run time |
| `{{ workflow.name }}` | Workflow name |
| `{{ workflow.project_path }}` | Project path |
| `{{ run.id }}` | Current run UUID |

## Execution Engine

The FastAPI backend orchestrates workflow execution as a background task:

```
POST /workflows/{id}/run  (body: {input_values: {...}})
  → Creates workflow_run record (status: "pending")
  → Spawns asyncio.create_task(execute_workflow(...))
  → Returns {run_id} immediately

execute_workflow(run_id):
  → Topologically sort steps using edges from the Svelte Flow graph
  → For each step (in dependency order):
      1. Check condition (if any) — skip if false
      2. Resolve prompt template (substitute {{ steps.x.output }}, {{ inputs.y }})
      3. Run: subprocess(["claude", "-p", resolved_prompt, "--output-format", "json",
                          "--model", model, "--allowedTools", tools_csv])
      4. Parse JSON output → extract result + session_id
      5. Update workflow_run_steps record
      6. If step failed → mark run as failed, stop
  → Mark run as completed
```

Key details:
- Steps with multiple dependencies wait for all upstream steps
- `--allowedTools` prevents permission prompts in headless mode
- `--output-format json` gives structured output with session_id
- Runs in the project's directory (`cwd=project_path`)
- Dashboard polls for status updates every 2-3 seconds

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/workflows` | List all workflows |
| `POST` | `/workflows` | Create workflow |
| `GET` | `/workflows/{id}` | Get workflow definition |
| `PUT` | `/workflows/{id}` | Update workflow |
| `DELETE` | `/workflows/{id}` | Delete workflow |
| `POST` | `/workflows/{id}/run` | Trigger execution |
| `GET` | `/workflows/{id}/runs` | List runs for a workflow |
| `GET` | `/workflows/{id}/runs/{run_id}` | Get run status + step statuses |

## Frontend

### Routes

| Route | View |
|-------|------|
| `/workflows` | List all workflows |
| `/workflows/new` | Visual node editor (create) |
| `/workflows/[id]` | Visual node editor (edit) |
| `/workflows/[id]/runs` | Run history |
| `/workflows/[id]/runs/[run_id]` | Live execution view |

### Visual Editor

- **Canvas**: Svelte Flow with Dagre auto-layout
- **Nodes**: Each node = one workflow step, shows name + model badge
- **Edges**: Drag between ports to create dependencies
- **Config panel** (right side): Step name, model dropdown, prompt textarea, tools checkboxes, max turns, condition
- **Workflow config**: Name, description, input parameters
- **Actions**: Save, Run (opens input dialog if inputs defined)

### Execution View

Same Svelte Flow graph but read-only, with live status:

| Status | Node Color |
|--------|-----------|
| pending | gray |
| running | blue (pulsing) |
| completed | green |
| failed | red |
| skipped | dimmed |

Each completed node shows duration. Clicking a node navigates to `/sessions/{session_id}` (existing session detail page).

## Example Workflow

**"Feature Review Pipeline"**

Inputs: `feature_desc` (string, required)

```
[extract] → [test] → [review] → [fix] → [docs]
```

1. **extract**: "Analyze the codebase and find all files related to: {{ inputs.feature_desc }}"
2. **test**: "Write tests for: {{ steps.extract.output }}"
3. **review**: "Review the code for: {{ inputs.feature_desc }}. Context: {{ steps.extract.output }}"
4. **fix** (condition: `{{ steps.review.has_issues }}`): "Fix these issues: {{ steps.review.output }}"
5. **docs**: "Update documentation for: {{ inputs.feature_desc }}"

## Future Enhancements (post-MVP)

- Commit detection triggers (git hooks or polling)
- SessionEnd hook triggers
- Approval gates between steps
- Parallel step execution (asyncio.gather for independent steps)
- Workflow templates/presets
- Real-time streaming output (SSE/WebSocket)
- Step retry with configurable policy
- Workflow versioning
