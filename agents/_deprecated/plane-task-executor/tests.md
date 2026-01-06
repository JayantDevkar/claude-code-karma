# Plane Task Executor - Test Scenarios

## Test 1: Project Detection
**Objective**: Verify agent correctly identifies project from git context

**Setup**:
```bash
cd /path/to/claude-karma
git remote get-url origin  # Should contain project info
```

**Expected Behavior**:
1. Agent reads git config/README to identify project
2. Falls back to asking user if ambiguous
3. Maps to Plane project "Claude Karma" (ID: ba9f6b13-3f7a-4e5b-94d8-c234b6243719)

**Pass Criteria**: ✅ Correct project ID identified

---

## Test 2: Work Item Fetching
**Objective**: Verify agent fetches active work items

**Setup**: Plane project has work items in various states

**Expected Behavior**:
1. Calls `list_work_items` with correct project_id
2. Filters to show only unstarted/started items
3. Excludes completed items by default
4. Presents readable summary to user

**Pass Criteria**:
✅ Returns CLAUDEKARM-4 (unstarted)
✅ Returns CLAUDEKARM-2 (started)
✅ Excludes CLAUDEKARM-3, CLAUDEKARM-1 (completed)

---

## Test 3: Execution Plan Generation
**Objective**: Verify TodoWrite plan creation from work item

**Input**: Work item CLAUDEKARM-4
```
Title: Create an agent to execute todo work item tickets in plane
Description:
- Fetch work items using Plane MCP
- Look at pages for agent composition
- Create agents in agents/ directory
- Execute in plan mode
- Ask for clarification if needed
```

**Expected Behavior**:
1. Parses work item description (HTML/markdown)
2. Extracts actionable steps
3. Creates TodoWrite items
4. Presents plan to user for approval

**Expected TodoWrite Output**:
```
□ Review Plane pages for agent composition guidance
□ Design plane-task-executor agent architecture
□ Create agent.yaml in agents/plane-task-executor/
□ Create README.md documentation
□ Create test scenarios
□ Test agent with current work items
```

**Pass Criteria**: ✅ All subtasks extracted and properly formatted

---

## Test 4: User Interaction Flow
**Objective**: Verify agent asks for clarification appropriately

**Scenarios**:

### 4a: Multiple Active Items
**Given**: 3 unstarted work items
**Expected**: Agent lists all and asks user to select

### 4b: Ambiguous Description
**Given**: Work item with vague requirements
**Expected**: Agent uses AskUserQuestion to clarify

### 4c: Complex Multi-Step Task
**Given**: Work item requiring planning
**Expected**: Agent suggests entering plan mode

**Pass Criteria**: ✅ Appropriate question asked in each scenario

---

## Test 5: Status Update Flow
**Objective**: Verify safe Plane status updates

**Setup**: Work item CLAUDEKARM-2 in "started" state

**Expected Behavior**:
1. Agent tracks progress via TodoWrite
2. When all todos complete, agent asks user confirmation
3. Only updates Plane status after explicit approval
4. Provides feedback on successful update

**User Interaction**:
```
Agent: "All tasks completed! Update CLAUDEKARM-2 to 'Done' in Plane?"
User: "yes"
Agent: [Calls update_work_item with state="completed"]
Agent: "✓ CLAUDEKARM-2 marked as complete in Plane"
```

**Pass Criteria**:
✅ No auto-update without confirmation
✅ Successful update with user approval
✅ Clear feedback provided

---

## Test 6: Error Handling
**Objective**: Verify graceful error handling

### 6a: Network Failure
**Trigger**: Plane API unavailable
**Expected**: "Unable to connect to Plane. Please check connection and retry."

### 6b: Invalid Project
**Trigger**: Repository not linked to Plane project
**Expected**: "No Plane project found. Please specify project manually."

### 6c: No Active Items
**Trigger**: All work items completed
**Expected**: "No active work items found. Great job! 🎉"

**Pass Criteria**: ✅ Clear error messages, no crashes

---

## Test 7: Integration Test (End-to-End)
**Objective**: Complete workflow from fetch to completion

**Steps**:
1. Start agent in claude-karma repo
2. Agent detects project
3. Agent lists work items
4. User selects CLAUDEKARM-4
5. Agent creates execution plan
6. Agent guides through implementation
7. Agent asks to mark complete
8. User confirms
9. Plane status updated

**Duration**: ~5-10 minutes
**Pass Criteria**: ✅ Smooth flow, no manual intervention needed

---

## Performance Benchmarks

| Metric | Target | Measurement |
|--------|--------|-------------|
| Project detection | <500ms | TBD |
| Work item fetch | <2s | TBD |
| Plan generation | <1s | TBD |
| Total session | <800 tokens | TBD |
| Success rate | >95% | TBD |

---

## Manual Testing Checklist

Before considering agent production-ready:

- [ ] Run Test 1: Project Detection
- [ ] Run Test 2: Work Item Fetching
- [ ] Run Test 3: Execution Plan Generation
- [ ] Run Test 4a-c: User Interactions
- [ ] Run Test 5: Status Update Flow
- [ ] Run Test 6a-c: Error Handling
- [ ] Run Test 7: End-to-End Integration
- [ ] Benchmark performance metrics
- [ ] Document any issues found
- [ ] Verify philosophy alignment

---

## Known Limitations (v1.0)

1. Single project context only (no multi-repo support)
2. Linear task execution (no parallel task handling)
3. English-only work item parsing
4. No rollback mechanism for Plane updates
5. Requires manual MCP server configuration

---

## Future Test Scenarios (v2.0+)

- Dependency management between work items
- Sub-task creation and tracking
- Time estimation and tracking
- Team member assignment
- Label/priority handling
- Cycle/module integration
