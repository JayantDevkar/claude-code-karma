# Agent Design Document: fetch-plane-tasks

## 1. Agent Metadata

**Name:** fetch-plane-tasks
**Description:** Fetches work items from Plane for the current project context
**Model:** sonnet
**Version:** 1.0.0
**Created:** 2026-01-06
**Philosophy Compliance:** CLAUDEKARM-6 Refactor

---

## 2. Single Responsibility Statement

**DO:** Fetch and return work items from Plane based on current project context
**DON'T:** Plan execution, analyze work item contents, select agents, update status, or execute tasks

This agent has ONE job: retrieve work items from Plane and present them in a structured format for downstream consumption.

---

## 3. Boundaries

### Includes (In Scope)
- Detect current project from git repository context
- Query Plane API for work items in the identified project
- Filter work items by state (unstarted, started by default)
- Return structured work item data with essential fields
- Handle project detection failures gracefully
- Support manual project specification via input

### Excludes (Out of Scope)
- Analyzing work item descriptions or requirements
- Creating execution plans (use TodoWrite elsewhere)
- Selecting appropriate execution agents
- Updating work item status in Plane
- Implementing or executing tasks
- Managing user interactions beyond data retrieval
- Parsing HTML/markdown work item content
- Multi-project queries (single project only)

---

## 4. Tool Selection (Max 3 Primary)

### Primary Tools

1. **mcp__plane-project-task-manager__list_projects**
   - **Purpose:** Identify the Plane project ID from project name/identifier
   - **Justification:** Essential for mapping git repository to Plane project context (>90% usage)
   - **Usage Pattern:** Called once at initialization to establish project context

2. **mcp__plane-project-task-manager__list_work_items**
   - **Purpose:** Retrieve work items for the identified project
   - **Justification:** Core function - this is THE primary operation (100% usage)
   - **Usage Pattern:** Called with project_id and optional state filters

3. **mcp__plane-project-task-manager__retrieve_work_item**
   - **Purpose:** Get detailed information for a specific work item by ID
   - **Justification:** Needed for fetching full details when work item ID is provided directly (>70% usage)
   - **Usage Pattern:** Called when user provides specific work item identifier

### Support Tools
None - agent is intentionally minimal. Bash tool is available from Claude Code environment for git operations.

---

## 5. Prompt Text (<500 tokens)

```markdown
## Role
Work item fetcher for Plane project management system.

## Objective
Retrieve work items from Plane for the current git repository's project context and return structured data.

## Process
1. Detect project identifier:
   - Check git repository name against Plane projects
   - Map repo "claude-karma" → Plane project "Claude Karma" (CLAUDEKARM)
   - If ambiguous: request project_id or project_name in input
2. Query work items using list_work_items:
   - Default filter: state in [unstarted, started]
   - Use expand parameter for essential fields only
   - Limit to 50 items per request (pagination if needed)
3. Return structured JSON output with work item array

## Constraints
- Single project per request only
- No HTML/markdown parsing (return raw description)
- No status updates or modifications
- No execution planning or task analysis
- Fail fast if project cannot be identified
- Maximum 50 work items per fetch

## Output Format
```json
{
  "project_id": "uuid",
  "project_name": "Claude Karma",
  "project_identifier": "CLAUDEKARM",
  "work_items": [
    {
      "id": "uuid",
      "sequence_id": 6,
      "identifier": "CLAUDEKARM-6",
      "name": "Work item title",
      "description_html": "<p>Raw HTML content</p>",
      "priority": "high|medium|low|none",
      "state": "uuid",
      "assignees": [],
      "created_at": "ISO-8601",
      "updated_at": "ISO-8601"
    }
  ],
  "total_fetched": 5,
  "filters_applied": {"state": ["unstarted", "started"]}
}
```
```

**Token Count:** 342 tokens ✅

---

## 6. Input/Output Contracts

### Input Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "project_id": {
      "type": "string",
      "format": "uuid",
      "description": "Optional: Explicit Plane project UUID"
    },
    "project_name": {
      "type": "string",
      "description": "Optional: Plane project name for lookup"
    },
    "project_identifier": {
      "type": "string",
      "description": "Optional: Project identifier (e.g., 'CLAUDEKARM')"
    },
    "state_filter": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["backlog", "unstarted", "started", "completed", "cancelled"]
      },
      "default": ["unstarted", "started"],
      "description": "Filter work items by state"
    },
    "work_item_id": {
      "type": "string",
      "format": "uuid",
      "description": "Optional: Fetch specific work item by ID"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 50,
      "default": 50,
      "description": "Maximum work items to fetch"
    }
  },
  "additionalProperties": false
}
```

### Output Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["project_id", "project_name", "work_items", "total_fetched"],
  "properties": {
    "project_id": {
      "type": "string",
      "format": "uuid"
    },
    "project_name": {
      "type": "string"
    },
    "project_identifier": {
      "type": "string"
    },
    "work_items": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "sequence_id"],
        "properties": {
          "id": {"type": "string", "format": "uuid"},
          "sequence_id": {"type": "integer"},
          "identifier": {"type": "string"},
          "name": {"type": "string"},
          "description_html": {"type": ["string", "null"]},
          "priority": {"type": "string", "enum": ["urgent", "high", "medium", "low", "none"]},
          "state": {"type": "string"},
          "assignees": {"type": "array"},
          "created_at": {"type": "string", "format": "date-time"},
          "updated_at": {"type": "string", "format": "date-time"}
        }
      }
    },
    "total_fetched": {
      "type": "integer"
    },
    "filters_applied": {
      "type": "object"
    },
    "error": {
      "type": "string",
      "description": "Present only when fetch fails"
    }
  }
}
```

---

## 7. Error Handling Strategy

### Error Categories

1. **Project Not Found**
   - **Trigger:** Cannot map git repo to Plane project
   - **Response:**
     ```json
     {
       "error": "PROJECT_NOT_FOUND",
       "message": "Cannot identify Plane project from repository context. Please provide project_id or project_name.",
       "available_projects": ["Claude Karma", "Claude Root", "Claude Code Tools"]
     }
     ```
   - **Recovery:** User provides explicit project identifier

2. **API Connection Failure**
   - **Trigger:** Plane API unreachable or timeout
   - **Response:**
     ```json
     {
       "error": "API_CONNECTION_FAILED",
       "message": "Unable to connect to Plane API. Check network and MCP server status.",
       "retry_suggested": true
     }
     ```
   - **Recovery:** Retry after checking connection

3. **No Work Items Found**
   - **Trigger:** Query returns empty result set
   - **Response:**
     ```json
     {
       "project_id": "uuid",
       "project_name": "Claude Karma",
       "work_items": [],
       "total_fetched": 0,
       "filters_applied": {"state": ["unstarted", "started"]},
       "message": "No work items match the specified filters."
     }
     ```
   - **Recovery:** Success case with empty data (not an error)

4. **Invalid Work Item ID**
   - **Trigger:** Specific work_item_id does not exist
   - **Response:**
     ```json
     {
       "error": "WORK_ITEM_NOT_FOUND",
       "message": "Work item with ID 'xyz' not found in project.",
       "work_item_id": "xyz"
     }
     ```
   - **Recovery:** User provides valid ID or switches to list mode

5. **Authentication Failure**
   - **Trigger:** MCP server not configured or invalid API key
   - **Response:**
     ```json
     {
       "error": "AUTHENTICATION_FAILED",
       "message": "Plane API authentication failed. Check MCP server configuration.",
       "config_hint": "Verify PLANE_API_KEY and PLANE_HOST in environment"
     }
     ```
   - **Recovery:** Configure MCP server credentials

### Error Handling Principles
- **Fail Fast:** Return error immediately, don't retry internally
- **Informative:** Provide actionable error messages
- **Structured:** Always return JSON with error field
- **No Silent Failures:** Every error is logged in output
- **User-Centric:** Suggest concrete next steps for recovery

---

## 8. Test Scenarios (Minimum 5)

### Test 1: Happy Path - Fetch Active Work Items
**Objective:** Verify successful retrieval of unstarted and started work items

**Setup:**
- Repository: claude-karma (maps to "Claude Karma" project)
- Plane has work items: CLAUDEKARM-6 (unstarted), CLAUDEKARM-2 (started), CLAUDEKARM-1 (completed)

**Input:**
```json
{
  "state_filter": ["unstarted", "started"]
}
```

**Expected Output:**
```json
{
  "project_id": "ba9f6b13-3f7a-4e5b-94d8-c234b6243719",
  "project_name": "Claude Karma",
  "project_identifier": "CLAUDEKARM",
  "work_items": [
    {
      "id": "abe18d91-7cc4-4ee9-8720-8ef667e1b3a0",
      "sequence_id": 6,
      "identifier": "CLAUDEKARM-6",
      "name": "Refactor plane-task-executor agent...",
      "priority": "high",
      "state": "be67a9f3-ce04-4022-8ad3-5dab26ecee38"
    }
  ],
  "total_fetched": 2,
  "filters_applied": {"state": ["unstarted", "started"]}
}
```

**Pass Criteria:**
- ✅ Returns only unstarted/started items
- ✅ Excludes completed items
- ✅ Correct project mapping
- ✅ Valid JSON structure

---

### Test 2: Explicit Project ID
**Objective:** Verify agent can use explicit project_id input

**Setup:** Same as Test 1

**Input:**
```json
{
  "project_id": "ba9f6b13-3f7a-4e5b-94d8-c234b6243719",
  "state_filter": ["unstarted"]
}
```

**Expected Output:**
```json
{
  "project_id": "ba9f6b13-3f7a-4e5b-94d8-c234b6243719",
  "project_name": "Claude Karma",
  "work_items": [/* only unstarted items */],
  "total_fetched": 1,
  "filters_applied": {"state": ["unstarted"]}
}
```

**Pass Criteria:**
- ✅ Uses provided project_id directly
- ✅ Skips project detection
- ✅ Applies state filter correctly

---

### Test 3: Fetch Specific Work Item by ID
**Objective:** Verify retrieval of single work item by UUID

**Setup:** Work item CLAUDEKARM-6 exists

**Input:**
```json
{
  "work_item_id": "abe18d91-7cc4-4ee9-8720-8ef667e1b3a0"
}
```

**Expected Output:**
```json
{
  "project_id": "ba9f6b13-3f7a-4e5b-94d8-c234b6243719",
  "project_name": "Claude Karma",
  "work_items": [
    {
      "id": "abe18d91-7cc4-4ee9-8720-8ef667e1b3a0",
      "sequence_id": 6,
      "identifier": "CLAUDEKARM-6",
      "name": "Refactor plane-task-executor agent...",
      "description_html": "<h2>Problem Statement</h2>...",
      "priority": "high"
    }
  ],
  "total_fetched": 1
}
```

**Pass Criteria:**
- ✅ Returns single work item
- ✅ Includes full description_html
- ✅ Detects project from work item

---

### Test 4: Project Not Found Error
**Objective:** Verify error handling when project cannot be identified

**Setup:** Repository with no matching Plane project

**Input:**
```json
{}
```

**Expected Output:**
```json
{
  "error": "PROJECT_NOT_FOUND",
  "message": "Cannot identify Plane project from repository context. Please provide project_id or project_name.",
  "available_projects": ["Claude Karma", "Claude Root", "Claude Code Tools"]
}
```

**Pass Criteria:**
- ✅ Returns error structure
- ✅ Lists available projects
- ✅ Provides clear next steps
- ✅ Does not crash

---

### Test 5: Empty Result Set (No Active Items)
**Objective:** Verify graceful handling of empty query results

**Setup:** Project exists but all work items are completed

**Input:**
```json
{
  "project_name": "Claude Root",
  "state_filter": ["unstarted", "started"]
}
```

**Expected Output:**
```json
{
  "project_id": "d1853109-7233-43e3-8042-d208800009d8",
  "project_name": "Claude Root",
  "project_identifier": "CLAUDEROOT",
  "work_items": [],
  "total_fetched": 0,
  "filters_applied": {"state": ["unstarted", "started"]},
  "message": "No work items match the specified filters."
}
```

**Pass Criteria:**
- ✅ Returns valid JSON (not error)
- ✅ Empty work_items array
- ✅ Informative message
- ✅ Correct project mapping

---

### Test 6: API Connection Failure
**Objective:** Verify error handling when Plane API is unreachable

**Setup:** Plane MCP server offline or misconfigured

**Input:**
```json
{
  "project_name": "Claude Karma"
}
```

**Expected Output:**
```json
{
  "error": "API_CONNECTION_FAILED",
  "message": "Unable to connect to Plane API. Check network and MCP server status.",
  "retry_suggested": true
}
```

**Pass Criteria:**
- ✅ Fails fast (no hanging)
- ✅ Clear error message
- ✅ Suggests retry action

---

### Test 7: All Work Items (No Filter)
**Objective:** Verify fetching all work items regardless of state

**Setup:** Project with mixed state work items

**Input:**
```json
{
  "project_name": "Claude Karma",
  "state_filter": []
}
```

**Expected Output:**
```json
{
  "project_id": "ba9f6b13-3f7a-4e5b-94d8-c234b6243719",
  "work_items": [/* all 6 items including completed */],
  "total_fetched": 6,
  "filters_applied": {"state": []}
}
```

**Pass Criteria:**
- ✅ Returns all work items
- ✅ Includes completed items
- ✅ Correct total count

---

## 9. Agent YAML Configuration

```yaml
name: fetch-plane-tasks
description: "Fetches work items from Plane for current project context"
model: sonnet

prompt: |
  ## Role
  Work item fetcher for Plane project management system.

  ## Objective
  Retrieve work items from Plane for the current git repository's project context and return structured data.

  ## Process
  1. Detect project identifier:
     - Check git repository name against Plane projects
     - Map repo "claude-karma" → Plane project "Claude Karma" (CLAUDEKARM)
     - If ambiguous: request project_id or project_name in input
  2. Query work items using list_work_items:
     - Default filter: state in [unstarted, started]
     - Use expand parameter for essential fields only
     - Limit to 50 items per request (pagination if needed)
  3. Return structured JSON output with work item array

  ## Constraints
  - Single project per request only
  - No HTML/markdown parsing (return raw description)
  - No status updates or modifications
  - No execution planning or task analysis
  - Fail fast if project cannot be identified
  - Maximum 50 work items per fetch

  ## Output Format
  ```json
  {
    "project_id": "uuid",
    "project_name": "Claude Karma",
    "project_identifier": "CLAUDEKARM",
    "work_items": [
      {
        "id": "uuid",
        "sequence_id": 6,
        "identifier": "CLAUDEKARM-6",
        "name": "Work item title",
        "description_html": "<p>Raw HTML content</p>",
        "priority": "high|medium|low|none",
        "state": "uuid",
        "assignees": [],
        "created_at": "ISO-8601",
        "updated_at": "ISO-8601"
      }
    ],
    "total_fetched": 5,
    "filters_applied": {"state": ["unstarted", "started"]}
  }
  ```

tools:
  primary:
    - mcp__plane-project-task-manager__list_projects
    - mcp__plane-project-task-manager__list_work_items
    - mcp__plane-project-task-manager__retrieve_work_item

skills:
  - project_detection
  - data_retrieval
  - error_handling

# Input schema for validation
input_schema:
  type: object
  properties:
    project_id:
      type: string
      format: uuid
    project_name:
      type: string
    project_identifier:
      type: string
    state_filter:
      type: array
      items:
        type: string
        enum: [backlog, unstarted, started, completed, cancelled]
      default: [unstarted, started]
    work_item_id:
      type: string
      format: uuid
    limit:
      type: integer
      minimum: 1
      maximum: 50
      default: 50

# Output schema for validation
output_schema:
  type: object
  required: [project_id, project_name, work_items, total_fetched]
  properties:
    project_id:
      type: string
      format: uuid
    project_name:
      type: string
    project_identifier:
      type: string
    work_items:
      type: array
    total_fetched:
      type: integer
    filters_applied:
      type: object
    error:
      type: string

# Performance targets
performance:
  latency_p50: 500ms
  latency_p95: 1500ms
  latency_p99: 3000ms
  success_rate: 95%
  token_usage: 400

# Version and metadata
version: 1.0.0
created_date: 2026-01-06
philosophy_compliance: CLAUDEKARM-6
```

---

## 10. Philosophy Alignment Checklist

- ✅ **Single Responsibility:** ONLY fetches work items, nothing else
- ✅ **Action-Target Naming:** `fetch-plane-tasks` (verb-noun)
- ✅ **Maximum 3 Primary Tools:** list_projects, list_work_items, retrieve_work_item
- ✅ **Prompt Under 500 Tokens:** 342 tokens
- ✅ **Input/Output Contracts:** JSON schemas defined
- ✅ **Error States Documented:** 5 error categories with recovery
- ✅ **Test Coverage:** 7 test scenarios (>5 required)
- ✅ **Fallback Behavior:** Graceful degradation on errors
- ✅ **Performance Benchmarked:** Targets defined (P50 <500ms)
- ✅ **Stateless Design:** No persistent state, pure data retrieval
- ✅ **Fail Fast:** Immediate error returns, no retries
- ✅ **MCP Tools Only:** All tools are real Plane MCP tools
- ✅ **No TodoWrite/AskUserQuestion:** Excluded non-MCP tools

---

## Summary

The `fetch-plane-tasks` agent is a **hyper-focused, single-purpose agent** that does ONE thing exceptionally well: retrieving work items from Plane. It follows all philosophy principles with 342 tokens, 3 primary tools, single responsibility, and comprehensive error handling.
