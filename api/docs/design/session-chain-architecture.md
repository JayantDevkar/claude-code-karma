# Session Chain Architecture Design

**Date:** 2026-01-23
**Status:** Design Proposal v0
**Author:** Architecture Design + Meta-Testing Validation

---

## Executive Summary

This document provides a comprehensive redesign of session chain, compaction, and resume tracking in Claude Karma. The design is validated through real-world meta-testing of actual session data.

### Critical Discovery from Meta-Testing

**The `leafUuid` in summary messages has TWO distinct meanings:**

| Scenario | Summary Position | leafUuid Points To | Meaning |
|----------|-----------------|-------------------|---------|
| **Resume** | START of session (before first user msg) | Message in DIFFERENT session | Cross-session chain link |
| **Compaction** | AFTER conversation starts | Message in SAME session | Context overflow marker |

**Real Example Verified:**
- Parent: `e3fcfcf9...` (slug: `rippling-cooking-reef`) - Line 118: msg `65954b54...` "Bye!"
- Child: `03d63f53...` (slug: `imperative-strolling-torvalds`) - Line 1: Summary with `leafUuid: "65954b54..."`
- **Note:** Slugs are DIFFERENT - slug-based detection would fail!

### Key Changes

1. **Unified chain detection** using only `leaf_uuid` with position-based context
2. **Comprehensive test coverage** for all chain detection and compaction logic
3. **Project-level chain precomputation** to eliminate N+1 queries
4. **Clear conceptual separation** between project context, compaction, and continuation markers
5. **Robust null handling** for edge cases where `leaf_uuid` is missing

---

## 1. Current State Analysis

### What Works Well
- **SessionRelationshipResolver** provides chain detection via `leaf_uuid` matching
- **CompactionDetector** distinguishes compaction from session end summaries
- **Session model** tracks both project context and compaction counts
- **Frontend visualization** (SessionChainView.svelte) displays chains

### Critical Issues

#### Issue 1: Inconsistent Detection Methods
**Problem:** Two approaches exist:
- `SessionRelationshipResolver` uses `leaf_uuid` only
- `/continuation/{uuid}` endpoint uses slug + time proximity matching

**Fix:** Unify on `leaf_uuid` with position-aware detection.

#### Issue 2: Position-Blind Detection
**Problem:** Current code doesn't check WHERE in the session the summary appears:
- Summary at START → Resume from previous session
- Summary MID-conversation → Compaction event

**Fix:** Add position-based detection logic.

#### Issue 3: No Unit Tests
**Problem:** Zero test coverage for:
- `CompactionDetector`
- `SessionRelationshipResolver`
- Chain endpoints

**Fix:** Create comprehensive test suite with real-world fixtures.

#### Issue 4: Null `leafUuid` Handling
**Problem:** Many summary messages have `leafUuid: null`. Current code silently skips.

**Fix:** Explicit handling with clear failure reasons.

#### Issue 5: Performance at Project Level
**Problem:** Frontend makes N+1 calls for chain data.

**Fix:** Add batch endpoint `/projects/{name}/chains`.

---

## 2. Conceptual Model

### Three Distinct Concepts

#### A. Project Context (Resume from Previous Session)
- **What:** Summary at START of session from PREVIOUS session
- **Detection:** First N messages, summary with leafUuid in DIFFERENT session
- **Storage:** `Session.project_context_summaries`, `Session.project_context_leaf_uuids`
- **Chain Link:** Creates `resumed_from` relationship

```
Detection Algorithm:
1. Get first 10 messages of session
2. For each summary message:
   a. Check if leafUuid exists
   b. Check if leafUuid is in THIS session or DIFFERENT session
   c. If DIFFERENT session → This is a RESUME
   d. Record parent session UUID
```

#### B. Session Compaction (Mid-Session Overflow)
- **What:** Summary AFTER conversation started, leafUuid in SAME session
- **Detection:** Summary appears after user/assistant messages, leafUuid points to message in same file
- **Storage:** `Session.was_compacted`, `Session.compaction_summary_count`
- **No Chain Link:** Internal session event

```
Detection Algorithm:
1. Track if conversation_started (seen user/assistant message)
2. When summary encountered:
   a. If NOT conversation_started → Project context (resume)
   b. If conversation_started AND leafUuid in SAME session → Compaction
   c. Count compaction events
```

#### C. Continuation Markers (Session Stubs)
- **What:** Empty session files created when user resumes
- **Detection:** Only `file-history-snapshot` entries, no user/assistant messages
- **Storage:** `Session.is_continuation_marker`
- **Use Case:** Cleanup old stubs

---

## 3. Corrected Detection Logic

### 3.1 Resume Detection (Position + Session Membership)

```python
def detect_resume_parent(session: Session) -> Optional[str]:
    """
    Detect if session is a resume from a previous session.

    Returns parent session UUID if this is a resume, None otherwise.
    """
    conversation_started = False

    for msg in session.iter_messages():
        # Check if conversation has started
        if isinstance(msg, (UserMessage, AssistantMessage)):
            conversation_started = True
            continue

        # Summary BEFORE conversation = potential resume
        if isinstance(msg, SummaryMessage) and not conversation_started:
            if msg.leaf_uuid:
                # Check if leafUuid is in a DIFFERENT session
                parent_session = find_session_containing_uuid(msg.leaf_uuid)
                if parent_session and parent_session.uuid != session.uuid:
                    return parent_session.uuid

    return None
```

### 3.2 Compaction Detection (Position + Same Session)

```python
def detect_compaction_events(session: Session) -> int:
    """
    Count compaction events (summaries after conversation started).

    Returns count of compaction events.
    """
    conversation_started = False
    compaction_count = 0

    for msg in session.iter_messages():
        if isinstance(msg, (UserMessage, AssistantMessage)):
            conversation_started = True
        elif isinstance(msg, SummaryMessage) and conversation_started:
            # Summary AFTER conversation started = compaction
            # Verify by checking leafUuid is in same session
            if msg.leaf_uuid:
                if message_exists_in_session(session, msg.leaf_uuid):
                    compaction_count += 1

    return compaction_count
```

---

## 4. Data Model Changes

### 4.1 Chain Detection Result

```python
# models/chain_detection.py

@dataclass(frozen=True)
class ChainDetectionResult:
    """Result of attempting to detect a session's parent."""
    detected: bool
    parent_uuid: Optional[str] = None
    parent_slug: Optional[str] = None
    detection_method: str = "leaf_uuid"  # Only method we use
    confidence: float = 0.95
    failure_reason: Optional[str] = None

    # Metadata
    summary_position: Optional[int] = None  # Line number in JSONL
    leaf_uuid_found: Optional[str] = None
```

### 4.2 Session Chain Node (Updated)

```python
# schemas.py - Update SessionChainNodeSchema

class SessionChainNodeSchema(BaseModel):
    uuid: str
    slug: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_current: bool = False
    chain_depth: int = 0
    parent_uuid: Optional[str] = None
    children_uuids: list[str] = []

    # Compaction info (distinct from chain)
    was_compacted: bool = False
    compaction_count: int = 0

    # Resume info
    is_continuation_marker: bool = False
    resume_detected_via: Optional[str] = None  # "leaf_uuid" or None

    message_count: int = 0
    initial_prompt: Optional[str] = None
```

### 4.3 Project Chain Cache (New)

```python
# models/project_chain_cache.py

class ProjectChainCache(BaseModel):
    """Precomputed chain data for all sessions in a project."""

    project_encoded_name: str
    computed_at: datetime

    # Map: session_uuid -> parent_uuid (or None)
    parents: dict[str, Optional[str]]

    # Map: session_uuid -> list of child UUIDs
    children: dict[str, list[str]]

    # Map: session_uuid -> chain depth from root
    depths: dict[str, int]

    # Root sessions (no parent)
    roots: list[str]

    # Sessions with detection failures
    orphans: list[str]
    orphan_reasons: dict[str, str]
```

---

## 5. Service Layer Design

### 5.1 Unified Session Chain Service

**File:** `api/services/session_chain_service.py`

```python
class SessionChainService:
    """Single source of truth for session chain detection."""

    def __init__(self, project: Project):
        self.project = project
        self._uuid_to_session: dict[str, Session] = {}
        self._message_uuid_index: dict[str, str] = {}  # msg_uuid -> session_uuid
        self._cache: Optional[ProjectChainCache] = None

    def detect_parent(self, session: Session) -> ChainDetectionResult:
        """
        Detect if session has a parent (was resumed from another session).

        Uses position-based detection:
        - Summary at START of session with leafUuid in DIFFERENT session = resume
        """
        ...

    def build_message_uuid_index(self) -> None:
        """
        Build index of message UUIDs to session UUIDs.

        This is O(N * M) where N = sessions, M = messages per session.
        Call once per project, cache result.
        """
        ...

    def find_session_by_message_uuid(self, msg_uuid: str) -> Optional[Session]:
        """Find which session contains a message with given UUID."""
        if not self._message_uuid_index:
            self.build_message_uuid_index()
        session_uuid = self._message_uuid_index.get(msg_uuid)
        return self._uuid_to_session.get(session_uuid) if session_uuid else None

    def build_project_cache(self) -> ProjectChainCache:
        """
        Build complete chain cache for all sessions in project.

        This is the N+1 killer - compute once, use everywhere.
        """
        ...

    def get_chain(self, session_uuid: str) -> SessionChain:
        """Get full chain (ancestors + descendants) for a session."""
        if not self._cache:
            self._cache = self.build_project_cache()
        ...
```

---

## 6. API Endpoint Design

### 6.1 Keep & Update

**`GET /sessions/{uuid}/chain`**
- Update to use `SessionChainService`
- Response unchanged

**`GET /sessions/{uuid}/relationships`**
- Update to use `SessionChainService`
- Response unchanged

### 6.2 New Endpoint

**`GET /projects/{encoded_name}/chains`**

```python
@router.get("/projects/{encoded_name}/chains")
async def get_project_chains(encoded_name: str) -> ProjectChainCache:
    """
    Get precomputed chain data for all sessions in a project.

    This eliminates N+1 queries from frontend.
    """
    project = find_project(encoded_name)
    service = SessionChainService(project)
    return service.build_project_cache()
```

### 6.3 Deprecate

**`GET /sessions/continuation/{uuid}`**
- Mark as deprecated
- Redirect to `/sessions/{uuid}/chain`
- Remove slug-based detection logic

---

## 7. Test Plan

### 7.1 Test Fixtures

Create `tests/fixtures/chain_scenarios/`:

```
chain_scenarios/
├── simple_chain/           # A → B (2 sessions)
│   ├── session_a.jsonl
│   └── session_b.jsonl     # Has summary at start with leafUuid → A
├── deep_chain/             # A → B → C → D → E (5 sessions)
├── compaction_only/        # Session with mid-conversation summaries
├── null_leafuuid/          # Summary with leafUuid: null
├── continuation_marker/    # Empty stub session
└── orphan_session/         # No summary, no parent
```

### 7.2 Unit Tests

**CompactionDetector Tests:**
```python
def test_detects_compaction_after_conversation():
    """Summary after user/assistant = compaction."""

def test_ignores_summary_at_start():
    """Summary before conversation = NOT compaction."""

def test_counts_multiple_compactions():
    """Session with 3 summaries mid-conversation."""
```

**SessionChainService Tests:**
```python
def test_detect_parent_from_leafuuid():
    """Parent detected via leafUuid in different session."""

def test_no_parent_for_fresh_session():
    """Session without summary has no parent."""

def test_no_parent_when_leafuuid_same_session():
    """Mid-conversation summary is NOT a parent link."""

def test_build_project_cache_all_sessions():
    """Cache includes all sessions with correct relationships."""
```

### 7.3 Integration Tests

```python
def test_chain_endpoint_returns_ancestors_and_descendants():
    """GET /sessions/{uuid}/chain returns full tree."""

def test_project_chains_endpoint_batch():
    """GET /projects/{name}/chains returns all chains."""
```

---

## 8. Migration Path

### Phase 1: Add New Code (No Breaking Changes)
- [ ] Create `models/chain_detection.py`
- [ ] Create `services/session_chain_service.py`
- [ ] Create test fixtures
- [ ] Write unit tests
- [ ] Run tests until green

### Phase 2: Update Endpoints (Backward Compatible)
- [ ] Update `/sessions/{uuid}/chain` to use new service
- [ ] Update `/sessions/{uuid}/relationships` to use new service
- [ ] Add `/projects/{name}/chains` endpoint
- [ ] Keep old code as fallback

### Phase 3: Frontend Integration
- [ ] Update project detail loader to batch-fetch chains
- [ ] Remove individual chain fetches
- [ ] Add chain badges to session list
- [ ] Measure performance improvement

### Phase 4: Deprecation & Cleanup
- [ ] Mark `/sessions/continuation/{uuid}` as deprecated
- [ ] Remove slug-based detection from codebase
- [ ] Update documentation
- [ ] Remove unused code

---

## 9. Frontend Changes

### 9.1 Batch Chain Fetching

**Before (N+1 problem):**
```typescript
// ConversationOverview.svelte
const chain = await fetch(`/sessions/${uuid}/chain`);
```

**After (1 query at project level):**
```typescript
// +page.ts (project detail)
export async function load({ params }) {
    const [project, chains] = await Promise.all([
        fetch(`/projects/${params.name}`),
        fetch(`/projects/${params.name}/chains`)
    ]);

    // Annotate sessions
    project.sessions.forEach(s => {
        s.chainInfo = chains.parents[s.uuid] ? {
            parentUuid: chains.parents[s.uuid],
            depth: chains.depths[s.uuid],
            isRoot: chains.roots.includes(s.uuid)
        } : null;
    });

    return { project };
}
```

### 9.2 Chain Badges in Session List

Add visual indicators to session cards:
- Chain depth badge (e.g., "D2" for depth 2)
- Root indicator
- Orphan indicator (no parent detected)

---

## 10. Edge Cases & Error Handling

### 10.1 Null `leafUuid`
```python
if not summary.leaf_uuid:
    return ChainDetectionResult(
        detected=False,
        failure_reason="Summary has null leafUuid"
    )
```

### 10.2 Circular References
```python
def build_chain(session_uuid: str, visited: set[str] = None):
    visited = visited or set()
    if session_uuid in visited:
        log.warning(f"Circular reference detected: {session_uuid}")
        return None
    visited.add(session_uuid)
    ...
```

### 10.3 Missing Session Files
```python
def find_session(uuid: str) -> Optional[Session]:
    try:
        return Session.from_uuid(uuid)
    except FileNotFoundError:
        log.warning(f"Session file missing: {uuid}")
        return None
```

---

## 11. Implementation Checklist

- [ ] Create `api/models/chain_detection.py`
- [ ] Create `api/models/project_chain_cache.py`
- [ ] Implement `api/services/session_chain_service.py`
- [ ] Create test fixtures in `tests/fixtures/chain_scenarios/`
- [ ] Write unit tests for `CompactionDetector`
- [ ] Write unit tests for `SessionChainService`
- [ ] Write API integration tests
- [ ] Update existing endpoints to use new service
- [ ] Add new `/projects/{name}/chains` endpoint
- [ ] Update frontend to batch-fetch chains
- [ ] Add chain badges to session list UI
- [ ] Deprecate old `/continuation/{uuid}` endpoint
- [ ] Document migration guide
- [ ] Performance benchmark (100 session project)

---

## Appendix A: Detection Method Comparison

| Method | Confidence | Pros | Cons | Decision |
|--------|-----------|------|------|----------|
| **leaf_uuid + position** | 95% | Direct reference, position-aware | Fails if null | **USE THIS** |
| **slug + time** | 60% | Works when leaf_uuid missing | False positives (slugs not unique!) | **DEPRECATED** |
| **continuation marker** | 70% | Detects stubs | Doesn't identify target | Cleanup only |

**Decision:** Use **only** `leaf_uuid` with position-based context. Document null cases clearly.

## Appendix B: Real-World Examples Verified

### Example 1: Resume Chain
```
Parent: e3fcfcf9-69dd-4e7a-90ec-0c5d981f18bb
  Slug: "rippling-cooking-reef"
  Last msg (line 118): uuid="65954b54..." content="Bye!"

Child: 03d63f53-64fb-4999-bb2c-a48b03834cce
  Slug: "imperative-strolling-torvalds" (DIFFERENT!)
  Line 1: Summary with leafUuid="65954b54..." → Points to parent!
```

### Example 2: Compaction (NOT a chain link)
```
Session: 04c655c7-8884-4c23-843e-bb95ee76ae76
  Line 122: Assistant msg uuid="2d8b6f64..."
  Line 123: Summary with leafUuid="2d8b6f64..." → Same session!

This is compaction, NOT a resume link.
```

---

**End of Design Document**
