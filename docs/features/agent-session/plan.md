# Agent Session View - Feature Plan

## Overview

This document outlines the plan to implement a dedicated "Agent Session View" feature for Claude Karma. This view will allow users to explore individual subagent sessions with the same level of detail as the main session view.

**Feature**: Agent Session View
**Route**: `/projects/{encoded_name}/{session_slug}/agents/{agent_id}`
**Status**: Planning Complete
**Architecture**: Clean Architecture with ConversationEntity Protocol

---

## Research Findings

### 1. Subagent Data Availability

Claude Code stores subagent data in JSONL files with the following structure:

```
~/.claude/projects/{encoded-path}/{session-uuid}/subagents/agent-{id}.jsonl
```

Each subagent JSONL file contains the **same message structure** as a session:
- `UserMessage` - Task prompts and tool results
- `AssistantMessage` - Tool calls, thinking blocks, text responses
- `FileHistorySnapshot` - File backup checkpoints

#### Agent Model (`api/models/agent.py`)

The `Agent` model already provides all necessary data access methods:

| Property/Method | Description |
|-----------------|-------------|
| `agent_id` | Short hex identifier (e.g., "a5793c3") |
| `jsonl_path` | Path to the agent's JSONL file |
| `is_subagent` | Boolean flag indicating subagent status |
| `parent_session_uuid` | UUID of parent session (if subagent) |
| `slug` | Session slug inherited from parent |
| `iter_messages()` | Generator for lazy message iteration |
| `list_messages()` | Load all messages into memory |
| `message_count` | Total messages (cached) |
| `start_time` | Timestamp of first message (cached) |
| `end_time` | Timestamp of last message (cached) |
| `get_usage_summary()` | TokenUsage with input/output tokens, cache hit rate |

**Key Insight**: The `Agent` model has the **identical interface** to `Session` for message iteration and metadata access. This enables a unified abstraction.

### 2. Current Subagent API Endpoint

The existing `/sessions/{uuid}/subagents` endpoint returns:

```python
class SubagentSummary(BaseModel):
    agent_id: str                    # "a5793c3"
    slug: Optional[str]              # "eager-puzzling-fairy"
    subagent_type: Optional[str]     # "Explore", "Plan", "Bash", or custom
    tools_used: dict[str, int]       # {"Read": 15, "Grep": 8, ...}
    message_count: int               # Total messages in subagent
    initial_prompt: Optional[str]    # First user message (truncated to 500 chars)
```

This provides a good summary but lacks the detailed timeline, file activity, and analytics views.

### 3. Session View Architecture

The current session view (`frontend/src/routes/projects/[encoded_name]/[session_slug]/+page.svelte`) is a 1000+ line component with:

| Tab | Content | Reusable for Agents? |
|-----|---------|---------------------|
| Overview | Initial prompt, stats cards, tools summary, git info | Yes |
| Timeline | Chronological event rail with filtering | Yes |
| Files | File activity table with sorting | Yes |
| Agents | Subagents grouped by type | No (agents don't have subagents) |
| Analytics | Stats grid, tool charts | Yes |

**Key patterns used**:
- Svelte 5 Runes: `$state()`, `$derived()`, `$effect()`, `$props()`
- Tab-based navigation with URL state persistence (`?tab=timeline`)
- Live polling: 2-second intervals when session is live
- HTTP caching: `?fresh=1` param for minimal cache during polling

### 4. Data Collection Optimization

The `api/collectors.py` module provides single-pass data extraction:

```python
@dataclass
class SessionData:
    task_tool_to_type: Dict[str, str]      # tool_use_id → subagent_type
    task_descriptions: Dict[str, str]      # normalized_desc → subagent_type
    session_tool_counts: Counter           # Main session tool usage
    subagent_tool_counts: Counter          # Subagent tool usage
    file_operations: List[FileOperation]   # All file operations
    git_branches: Set[str]                 # Git branches touched
    working_directories: Set[str]          # Working directories
```

**Important**: The `collect_session_data()` function accepts any object with `iter_messages()` method - this means it **already works with Agent objects**!

### 5. Timeline Generation Logic

Timeline events are generated from messages in `api/routers/sessions.py`:

1. **Pass 1**: Collect tool results from `UserMessage` content (tool_result structures)
2. **Pass 2**: Iterate messages and build `TimelineEvent` for each content block

Event types:
- `prompt` - User messages
- `tool_call` - Tool invocations with merged results
- `subagent_spawn` - Task tool creating subagents
- `thinking` - Extended thinking blocks
- `response` - Assistant text responses
- `todo_update` - TodoWrite actions

---

## User Requirements

Based on clarifying questions, the following requirements were confirmed:

1. **Detail Level**: Full session-like view with Timeline, File Activity, Tool Breakdown, and Analytics tabs
2. **Navigation**: Click agent card → dedicated page at `/projects/{project}/{session}/agents/{agent_id}`
3. **Context**: Breadcrumb navigation showing: Project → Session → Agent, with link back to parent
4. **Live Updates**: Poll for updates when parent session is live (same 2s interval as sessions)

---

## Architecture Design: Clean Architecture

### Why Clean Architecture?

| Consideration | Decision |
|---------------|----------|
| Code Reuse | ~80% of session view logic applies to agents |
| Maintainability | Bug fixes automatically apply to both views |
| Type Safety | Protocol ensures compile-time guarantees |
| Extensibility | Easy to add new conversation types in future |

### Core Abstraction: ConversationEntity Protocol

Create a TypeScript-style protocol that both Session and Agent implement:

```python
# api/models/conversation.py

from typing import Protocol, Iterator, Optional, Set
from datetime import datetime
from pathlib import Path

class ConversationEntity(Protocol):
    """Protocol for conversation-like entities (Session, Agent)."""

    @property
    def uuid(self) -> str: ...

    @property
    def slug(self) -> Optional[str]: ...

    @property
    def jsonl_path(self) -> Path: ...

    def iter_messages(self) -> Iterator[Message]: ...

    @property
    def message_count(self) -> int: ...

    @property
    def start_time(self) -> Optional[datetime]: ...

    @property
    def end_time(self) -> Optional[datetime]: ...

    def get_usage_summary(self) -> TokenUsage: ...
```

Both `Session` and `Agent` already satisfy this protocol without modification!

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ConversationView.svelte                  │
│  (Unified component for both sessions and agents)           │
├─────────────────────────────────────────────────────────────┤
│  Props:                                                     │
│  - entity: SessionDetail | AgentDetail                      │
│  - entityType: 'session' | 'agent'                          │
│  - disabledTabs?: ('agents' | 'todos')[]                    │
│  - breadcrumbs: BreadcrumbItem[]                            │
├─────────────────────────────────────────────────────────────┤
│  Tabs (conditional):                                        │
│  ┌─────────┬──────────┬───────┬─────────┬───────────┐      │
│  │Overview │ Timeline │ Files │ Agents* │ Analytics │      │
│  └─────────┴──────────┴───────┴─────────┴───────────┘      │
│  *Hidden for agents (agents don't have subagents)           │
├─────────────────────────────────────────────────────────────┤
│  Shared Components:                                         │
│  - TimelineRail                                             │
│  - FileActivityTable                                        │
│  - ToolUsageTable                                           │
│  - StatsGrid, StatsCard                                     │
│  - ToolsChart                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Backend Foundation

#### 1.1 Create ConversationEntity Protocol
**File**: `api/models/conversation.py` (NEW)

```python
"""
ConversationEntity Protocol - unified interface for Session and Agent.
"""

from typing import Protocol, Iterator, Optional, Set
from datetime import datetime
from pathlib import Path
from .message import Message
from .usage import TokenUsage


class ConversationEntity(Protocol):
    """Protocol for conversation-like entities."""

    @property
    def uuid(self) -> str:
        """Unique identifier for the conversation."""
        ...

    @property
    def slug(self) -> Optional[str]:
        """Human-readable name."""
        ...

    @property
    def jsonl_path(self) -> Path:
        """Path to the JSONL file."""
        ...

    def iter_messages(self) -> Iterator[Message]:
        """Iterate over messages lazily."""
        ...

    @property
    def message_count(self) -> int:
        """Total message count."""
        ...

    @property
    def start_time(self) -> Optional[datetime]:
        """Timestamp of first message."""
        ...

    @property
    def end_time(self) -> Optional[datetime]:
        """Timestamp of last message."""
        ...

    def get_usage_summary(self) -> TokenUsage:
        """Aggregated token usage."""
        ...


def is_session(entity: ConversationEntity) -> bool:
    """Type guard for Session entities."""
    return hasattr(entity, 'list_subagents')


def is_agent(entity: ConversationEntity) -> bool:
    """Type guard for Agent entities."""
    return hasattr(entity, 'is_subagent')
```

#### 1.2 Create Agents Router
**File**: `api/routers/agents_router.py` (NEW)

Endpoints to implement:

| Endpoint | Description |
|----------|-------------|
| `GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}` | Agent detail |
| `GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}/timeline` | Timeline events |
| `GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}/tools` | Tool usage |
| `GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}/file-activity` | File operations |

Key implementation details:
- Use `collect_session_data(agent)` - it works with agents!
- Reuse timeline building logic from sessions.py
- Apply same HTTP caching strategy (`?fresh=1` for live polling)

#### 1.3 Add Schema Definitions
**File**: `api/schemas.py` (MODIFY)

```python
class ConversationContext(BaseModel):
    """Shared context for conversation views."""
    project_encoded_name: str
    parent_session_uuid: Optional[str] = None
    parent_session_slug: Optional[str] = None


class AgentDetail(BaseModel):
    """Agent conversation detail response."""
    agent_id: str
    slug: Optional[str]
    is_subagent: bool
    context: ConversationContext

    # Conversation fields
    message_count: int
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    duration_seconds: Optional[float]

    # Analytics
    total_input_tokens: int
    total_output_tokens: int
    cache_hit_rate: float
    total_cost: float

    # Tool usage
    tools_used: dict[str, int]

    # Context
    git_branches: list[str]
    working_directories: list[str]
```

#### 1.4 Register Router
**File**: `api/main.py` (MODIFY)

```python
from routers import agents_router

app.include_router(
    agents_router.router,
    prefix="/agents",
    tags=["agents"]
)
```

### Phase 2: Frontend Components

#### 2.1 Add TypeScript Types
**File**: `frontend/src/lib/api-types.ts` (MODIFY)

```typescript
export interface ConversationContext {
    project_encoded_name: string;
    parent_session_uuid?: string;
    parent_session_slug?: string;
}

export interface AgentDetail {
    agent_id: string;
    slug?: string;
    is_subagent: boolean;
    context: ConversationContext;

    message_count: number;
    start_time: string;
    end_time?: string;
    duration_seconds?: number;

    total_input_tokens: number;
    total_output_tokens: number;
    cache_hit_rate: number;
    total_cost: number;

    tools_used: Record<string, number>;
    git_branches: string[];
    working_directories: string[];
}
```

#### 2.2 Create ConversationView Component
**File**: `frontend/src/lib/components/conversation/ConversationView.svelte` (NEW)

This component will be ~500 lines, extracted from the session page with polymorphic handling:

```svelte
<script lang="ts">
    import { browser } from '$app/environment';
    import { Tabs } from 'bits-ui';
    import { onMount, onDestroy } from 'svelte';
    import type { SessionDetail, AgentDetail, TimelineEvent, FileActivity } from '$lib/api-types';

    interface Props {
        entity: SessionDetail | AgentDetail;
        entityType: 'session' | 'agent';
        encodedProject: string;
        disabledTabs?: string[];
        breadcrumbs?: { label: string; href: string }[];
        liveSession?: any;
        isStarting?: boolean;
        timeline?: TimelineEvent[];
        fileActivity?: FileActivity[];
        tools?: any[];
        subagents?: any[];
    }

    let {
        entity,
        entityType,
        encodedProject,
        disabledTabs = [],
        breadcrumbs = [],
        liveSession = null,
        timeline = [],
        fileActivity = [],
        tools = [],
        subagents = []
    }: Props = $props();

    // Derive API base path based on entity type
    const apiBase = $derived(
        entityType === 'session'
            ? `http://localhost:8000/sessions/${entity.uuid}`
            : `http://localhost:8000/agents/${encodedProject}/${entity.context?.parent_session_uuid}/agents/${entity.agent_id}`
    );

    // Tab configuration - filter out disabled tabs
    const allTabs = ['overview', 'timeline', 'files', 'agents', 'analytics'];
    const availableTabs = $derived(
        allTabs.filter(tab => !disabledTabs.includes(tab))
    );

    // ... rest of component logic
</script>
```

#### 2.3 Create ConversationOverview Component
**File**: `frontend/src/lib/components/conversation/ConversationOverview.svelte` (NEW)

Extracted overview tab content (~200 lines).

#### 2.4 Create Barrel Export
**File**: `frontend/src/lib/components/conversation/index.ts` (NEW)

```typescript
export { default as ConversationView } from './ConversationView.svelte';
export { default as ConversationOverview } from './ConversationOverview.svelte';
```

### Phase 3: Agent Route Implementation

#### 3.1 Create Server Loader
**File**: `frontend/src/routes/projects/[encoded_name]/[session_slug]/agents/[agent_id]/+page.server.ts` (NEW)

```typescript
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, fetch }) => {
    const { encoded_name, session_slug, agent_id } = params;
    const API_BASE = 'http://localhost:8000';

    // First, get the session UUID from slug
    const projectRes = await fetch(`${API_BASE}/projects/${encoded_name}`);
    const project = await projectRes.json();
    const session = project.sessions.find(s =>
        s.slug === session_slug || s.uuid.startsWith(session_slug)
    );

    if (!session) {
        throw error(404, 'Session not found');
    }

    // Fetch agent data in parallel
    const [agentRes, timelineRes, fileActivityRes, toolsRes] = await Promise.all([
        fetch(`${API_BASE}/agents/${encoded_name}/${session.uuid}/agents/${agent_id}`),
        fetch(`${API_BASE}/agents/${encoded_name}/${session.uuid}/agents/${agent_id}/timeline`),
        fetch(`${API_BASE}/agents/${encoded_name}/${session.uuid}/agents/${agent_id}/file-activity`),
        fetch(`${API_BASE}/agents/${encoded_name}/${session.uuid}/agents/${agent_id}/tools`)
    ]);

    if (!agentRes.ok) {
        throw error(404, 'Agent not found');
    }

    const agent = await agentRes.json();
    const timeline = timelineRes.ok ? await timelineRes.json() : [];
    const fileActivity = fileActivityRes.ok ? await fileActivityRes.json() : [];
    const tools = toolsRes.ok ? await toolsRes.json() : [];

    // Check if parent session is live
    let liveSession = null;
    try {
        const liveRes = await fetch(`${API_BASE}/live-sessions/${session.uuid}`);
        if (liveRes.ok) {
            liveSession = await liveRes.json();
        }
    } catch (e) {
        // Not live, continue
    }

    return {
        agent,
        timeline,
        fileActivity,
        tools,
        parentSession: session,
        encoded_name,
        liveSession
    };
};
```

#### 3.2 Create Agent Page Component
**File**: `frontend/src/routes/projects/[encoded_name]/[session_slug]/agents/[agent_id]/+page.svelte` (NEW)

```svelte
<script lang="ts">
    import { ConversationView } from '$lib/components/conversation';
    import { getProjectName } from '$lib/utils';

    let { data } = $props();

    const breadcrumbs = $derived([
        { label: 'Dashboard', href: '/' },
        { label: 'Projects', href: '/projects' },
        { label: getProjectName(data.encoded_name), href: `/projects/${data.encoded_name}` },
        { label: data.parentSession.slug || data.parentSession.uuid.slice(0, 8), href: `/projects/${data.encoded_name}/${data.parentSession.slug || data.parentSession.uuid}` },
        { label: `Agent ${data.agent.agent_id}`, href: '' }
    ]);
</script>

<ConversationView
    entity={data.agent}
    entityType="agent"
    encodedProject={data.encoded_name}
    disabledTabs={['agents']}
    {breadcrumbs}
    liveSession={data.liveSession}
    timeline={data.timeline}
    fileActivity={data.fileActivity}
    tools={data.tools}
/>
```

### Phase 4: Integration & Polish

#### 4.1 Refactor Session Page to Use ConversationView
**File**: `frontend/src/routes/projects/[encoded_name]/[session_slug]/+page.svelte` (MODIFY)

Replace the 1000+ lines with:

```svelte
<script lang="ts">
    import { ConversationView } from '$lib/components/conversation';
    import { getProjectName } from '$lib/utils';

    let { data } = $props();

    const breadcrumbs = $derived([
        { label: 'Dashboard', href: '/' },
        { label: 'Projects', href: '/projects' },
        { label: getProjectName(data.encoded_name), href: `/projects/${data.encoded_name}` },
        { label: data.session.slug || data.session.uuid.slice(0, 8), href: '' }
    ]);
</script>

<ConversationView
    entity={data.session}
    entityType="session"
    encodedProject={data.encoded_name}
    {breadcrumbs}
    liveSession={data.liveSession}
    isStarting={data.isStarting}
    timeline={data.timeline}
    fileActivity={data.file_activity}
    tools={data.tools_used}
    subagents={data.subagents}
/>
```

#### 4.2 Make SubagentCard Clickable
**File**: `frontend/src/lib/components/subagents/SubagentCard.svelte` (MODIFY)

```svelte
<script lang="ts">
    import { ExternalLink } from 'lucide-svelte';
    import type { SubagentSummary } from '$lib/api-types';

    interface Props {
        subagent: SubagentSummary;
        projectEncoded?: string;
        sessionSlug?: string;
        class?: string;
    }

    let { subagent, projectEncoded, sessionSlug, class: className = '' }: Props = $props();

    const agentUrl = $derived(
        projectEncoded && sessionSlug
            ? `/projects/${projectEncoded}/${sessionSlug}/agents/${subagent.agent_id}`
            : null
    );
</script>

{#if agentUrl}
<a href={agentUrl} class="block group">
{/if}
    <!-- Existing card content -->
    <div class="... {agentUrl ? 'cursor-pointer hover:border-[var(--accent)]' : ''}">
        <!-- ... existing card content ... -->

        {#if agentUrl}
            <div class="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                <ExternalLink size={16} class="text-[var(--text-muted)]" />
            </div>
        {/if}
    </div>
{#if agentUrl}
</a>
{/if}
```

#### 4.3 Update SubagentGroup to Pass Context
**File**: `frontend/src/lib/components/subagents/SubagentGroup.svelte` (MODIFY)

```svelte
<script lang="ts">
    interface Props {
        type: string;
        agents: SubagentSummary[];
        projectEncoded?: string;
        sessionSlug?: string;
        defaultExpanded?: boolean;
    }

    let { type, agents, projectEncoded, sessionSlug, defaultExpanded = false }: Props = $props();
</script>

<!-- Pass context to SubagentCard -->
{#each agents as subagent}
    <SubagentCard {subagent} {projectEncoded} {sessionSlug} />
{/each}
```

---

## File Summary

### Files to CREATE (8)

| File | Lines (est.) | Description |
|------|--------------|-------------|
| `api/models/conversation.py` | ~50 | ConversationEntity Protocol |
| `api/routers/agents_router.py` | ~300 | Agent API endpoints |
| `frontend/src/lib/components/conversation/ConversationView.svelte` | ~500 | Unified view component |
| `frontend/src/lib/components/conversation/ConversationOverview.svelte` | ~200 | Overview tab component |
| `frontend/src/lib/components/conversation/index.ts` | ~5 | Barrel export |
| `frontend/src/routes/.../agents/[agent_id]/+page.server.ts` | ~80 | Server loader |
| `frontend/src/routes/.../agents/[agent_id]/+page.svelte` | ~50 | Agent page |

### Files to MODIFY (6)

| File | Changes | Description |
|------|---------|-------------|
| `api/schemas.py` | +30 lines | Add AgentDetail, ConversationContext |
| `api/collectors.py` | +10 lines | Add collect_conversation_data() wrapper |
| `api/main.py` | +3 lines | Register agents router |
| `frontend/src/lib/api-types.ts` | +25 lines | Add TypeScript types |
| `frontend/src/routes/.../[session_slug]/+page.svelte` | Refactor | Use ConversationView |
| `frontend/src/lib/components/subagents/SubagentCard.svelte` | +20 lines | Add navigation |

---

## Testing Strategy

### Backend Tests

```python
# api/tests/api/test_agents_router.py

def test_get_agent_detail(client, sample_project_with_subagents):
    """Test agent detail endpoint returns correct data."""
    res = client.get("/agents/-test-project/session-uuid/agents/a5793c3")
    assert res.status_code == 200
    data = res.json()
    assert data["agent_id"] == "a5793c3"
    assert "total_cost" in data
    assert "context" in data

def test_get_agent_timeline(client, sample_project_with_subagents):
    """Test agent timeline returns events."""
    res = client.get("/agents/-test-project/session-uuid/agents/a5793c3/timeline")
    assert res.status_code == 200
    events = res.json()
    assert isinstance(events, list)

def test_agent_not_found(client, sample_project):
    """Test 404 for non-existent agent."""
    res = client.get("/agents/-test-project/session-uuid/agents/invalid")
    assert res.status_code == 404
```

### Frontend Tests

```typescript
// ConversationView.test.ts

describe('ConversationView', () => {
    it('renders session entity correctly', () => {
        render(ConversationView, {
            entity: mockSession,
            entityType: 'session',
            encodedProject: '-test-project'
        });
        expect(screen.getByText('Subagents')).toBeInTheDocument();
    });

    it('hides agents tab for agent entity', () => {
        render(ConversationView, {
            entity: mockAgent,
            entityType: 'agent',
            encodedProject: '-test-project',
            disabledTabs: ['agents']
        });
        expect(screen.queryByText('Subagents')).not.toBeInTheDocument();
    });

    it('shows correct breadcrumbs for agent', () => {
        render(ConversationView, {
            entity: mockAgent,
            entityType: 'agent',
            breadcrumbs: mockAgentBreadcrumbs
        });
        expect(screen.getByText('Agent a5793c3')).toBeInTheDocument();
    });
});
```

### Manual Testing Checklist

- [ ] Navigate from session to agent by clicking SubagentCard
- [ ] Verify all tabs work correctly in agent view
- [ ] Verify breadcrumb navigation back to session
- [ ] Test live polling when parent session is active
- [ ] Test with agents that have no messages (edge case)
- [ ] Test URL state persistence for tabs
- [ ] Verify caching works correctly (`?fresh=1` param)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Session page regression | Medium | High | Keep original as backup, thorough testing |
| Performance issues | Low | Medium | Reuse existing optimized collectors |
| Timeline logic differences | Low | Low | Timeline builder works identically |
| Live polling complexity | Low | Medium | Inherit parent session live status |

---

## Success Criteria

1. **Functional**: Click subagent card → see agent detail page with all tabs working
2. **Consistent**: Agent view looks identical to session view (same components)
3. **Navigable**: Breadcrumbs clearly show: Project → Session → Agent
4. **Live**: Agent view updates in real-time when parent session is active
5. **Performance**: Page loads in < 500ms
6. **Maintainable**: Bug fixes in ConversationView apply to both views

---

## Appendix: API Endpoint Details

### GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}

**Response**:
```json
{
    "agent_id": "a5793c3",
    "slug": "eager-puzzling-fairy",
    "is_subagent": true,
    "context": {
        "project_encoded_name": "-Users-me-claude-karma",
        "parent_session_uuid": "abc123...",
        "parent_session_slug": "fix-bug-session"
    },
    "message_count": 45,
    "start_time": "2024-01-15T10:30:00Z",
    "end_time": "2024-01-15T10:35:00Z",
    "duration_seconds": 300,
    "total_input_tokens": 15000,
    "total_output_tokens": 5000,
    "cache_hit_rate": 0.75,
    "total_cost": 0.12,
    "tools_used": {
        "Read": 15,
        "Grep": 8,
        "Write": 3
    },
    "git_branches": ["main"],
    "working_directories": ["/Users/me/project"]
}
```

### GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}/timeline

**Response**: Array of `TimelineEvent` (same schema as session timeline)

### GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}/tools

**Response**: Array of `ToolUsageSummary` (same schema as session tools)

### GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}/file-activity

**Response**: Array of `FileActivity` (same schema as session file-activity)

---

## Next Steps

1. Review and approve this plan
2. Create feature branch: `feature/agent-session-view`
3. Implement Phase 1 (Backend Foundation)
4. Implement Phase 2 (Frontend Components)
5. Implement Phase 3 (Agent Route)
6. Implement Phase 4 (Integration & Polish)
7. Code review and testing
8. Merge to main
