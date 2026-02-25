# Sessions Index (Summary Field)

> Claude Code now maintains pre-computed metadata in `sessions-index.json`, including auto-generated session summaries that describe what each session accomplished.

## API Implementation

**Affected Endpoint**: `GET /projects/{encoded_name}` (existing endpoint, enhanced response)

**Files**:

- `api/models/session_index.py` - SessionIndex and SessionIndexEntry models
- `api/schemas.py` - Added `summary` field to SessionSummary

**Storage Location**:

```
~/.claude/projects/{encoded-path}/sessions-index.json
```

This file contains pre-computed metadata for all sessions in a project.

---

## Data Schema

### SessionSummary (Enhanced)

```typescript
interface SessionSummary {
	uuid: string;
	slug: string;
	start_time: string; // ISO datetime
	end_time?: string;
	duration_seconds?: number;
	message_count: number;
	initial_prompt?: string; // First 500 chars of user's first message
	summary: string | null; // NEW: Claude's auto-generated summary
	models_used: string[];
	subagent_count: number;
	has_todos: boolean;
	git_branches: string[];
	status?: 'active' | 'completed' | 'error';
	project_encoded_name?: string;
	// ... other existing fields
}
```

### Key Difference: summary vs initial_prompt

| Field            | Source                         | Content                       |
| ---------------- | ------------------------------ | ----------------------------- |
| `initial_prompt` | First user message (truncated) | What the user asked           |
| `summary`        | Claude-generated               | What the session accomplished |

---

## Example Data

### With Summary

```json
{
	"uuid": "abc123...",
	"slug": "gentle-dancing-fox",
	"summary": "Implemented JWT authentication with refresh tokens and added comprehensive test coverage",
	"initial_prompt": "help me add authentication to my express app...",
	"message_count": 47,
	"duration_seconds": 3420
}
```

### Without Summary (older sessions)

```json
{
	"uuid": "def456...",
	"slug": "quiet-sleeping-bear",
	"summary": null,
	"initial_prompt": "can you help me debug this function that...",
	"message_count": 12,
	"duration_seconds": 840
}
```

---

## Summary Characteristics

Claude Code generates summaries that:

- Describe what was accomplished (outcome-focused)
- Are concise (typically 5-15 words)
- Use active voice
- Focus on deliverables

### Example Summaries

| Summary                                          | Session Type      |
| ------------------------------------------------ | ----------------- |
| "SQLite vs Valkey Database Selection Analysis"   | Research/decision |
| "Agent deployment & backlog orchestration"       | Implementation    |
| "Fixed authentication middleware error handling" | Bug fix           |
| "Refactored API routes for better modularity"    | Refactoring       |
| "Added unit tests for payment processing"        | Testing           |

---

## Existing Frontend Context

### SessionCard.svelte

Current body zone displays `initial_prompt`:

```svelte
<!-- BODY ZONE: Context/prompt -->
<div class="px-4 pb-4 pl-5 flex-grow">
	{#if session.initial_prompt}
		<p
			class="text-sm text-[var(--text-secondary)] leading-relaxed line-clamp-2 bg-[var(--bg-muted)] px-2 py-1.5 rounded-md"
		>
			{session.initial_prompt}
		</p>
	{:else}
		<p class="text-sm text-[var(--text-muted)] italic">No prompt recorded</p>
	{/if}
</div>
```

### Session Interface

Current interface in `SessionCard.svelte`:

```typescript
interface Session {
	uuid: string;
	slug: string;
	message_count: number;
	start_time: string;
	end_time?: string;
	duration_seconds?: number;
	models_used: string[];
	subagent_count: number;
	has_todos: boolean;
	initial_prompt?: string; // Currently displayed
	git_branches: string[];
	status?: 'active' | 'completed' | 'error';
	error_message?: string;
	chain_info?: SessionChainInfoSummary;
}
```

### api-types.ts SessionSummary

Current type (needs `summary` field added):

```typescript
export interface SessionSummary {
	uuid: string;
	slug: string;
	message_count: number;
	start_time: string;
	end_time?: string;
	duration_seconds?: number;
	models_used: string[];
	subagent_count: number;
	has_todos: boolean;
	todo_count?: number;
	initial_prompt?: string;
	git_branches: string[];
	status?: 'active' | 'completed' | 'error';
	// summary: string | null;  // TO BE ADDED
	// ...
}
```

---

## Display Considerations

### Hierarchy

When both fields available:

1. **Primary**: `summary` - describes outcome
2. **Secondary**: `initial_prompt` - provides context

When only `initial_prompt` available:

- Display as current behavior

### Fallback Chain

```
summary ?? initial_prompt ?? "No description"
```

### Visual Treatment Options

| Approach | Description                                  |
| -------- | -------------------------------------------- |
| Replace  | Show `summary` instead of `initial_prompt`   |
| Stack    | Summary as title, initial_prompt as subtitle |
| Tooltip  | Summary displayed, initial_prompt on hover   |
| Toggle   | User preference for which to show            |

---

## Affected Views

| View            | Component               | Current Display          |
| --------------- | ----------------------- | ------------------------ |
| Project detail  | `SessionCard.svelte`    | `initial_prompt` in body |
| Projects list   | `ProjectCard.svelte`    | Session count only       |
| Session detail  | Overview tab            | Session metadata         |
| Command palette | `CommandPalette.svelte` | Search results           |

---

## Performance Note

The sessions-index.json provides ~10x performance improvement for list views because:

- No need to parse individual JSONL files
- Pre-computed message counts, timestamps
- Summary already extracted

---

## Test Commands

```bash
# Fetch project with sessions (includes summary in each session)
curl http://localhost:8000/projects/{encoded_name} | jq '.sessions[0].summary'

# Check multiple sessions
curl http://localhost:8000/projects/{encoded_name} | jq '.sessions | map({slug, summary})'
```

---

## Related API Git Commit

Phase 1 implementation: `8dbb553`
