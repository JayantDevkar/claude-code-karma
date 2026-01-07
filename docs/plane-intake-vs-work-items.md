# Plane: Intake vs Work Items - Understanding the Difference

**Date**: 2026-01-06
**Source**: Plane MCP Server Tool Descriptions

---

## Quick Summary

| Aspect | Work Items | Intake Work Items |
|--------|-----------|-------------------|
| **Purpose** | Main project tasks/issues | Pre-qualification/triage items |
| **Location** | Main project backlog/cycles | Intake view (separate area) |
| **Workflow** | Direct assignment → execution | Review → convert to work item |
| **State Management** | Full state lifecycle | Limited intake states |
| **Features** | All project features | Subset of features |
| **Use Case** | Planned/approved work | Ideas, requests, bug reports needing review |

---

## Work Items (Standard Issues)

### Tool Functions Available
```
- list_work_items
- create_work_item
- retrieve_work_item
- update_work_item
- delete_work_item
- search_work_items
```

### Description from MCP Tools

**`list_work_items`**:
> List all work items in a project.

**`create_work_item`**:
> Create a new work item.
>
> Args include: name, assignees, labels, type_id, point, description_html,
> priority, start_date, target_date, is_draft, parent, state, estimate_point, etc.

**`retrieve_work_item`**:
> Retrieve a work item by ID.
>
> Returns: WorkItemDetail object with expanded relationships

### Key Characteristics

1. **Full Project Integration**
   - Can be assigned to users
   - Can be added to cycles and modules
   - Full state management (backlog, in-progress, completed, etc.)
   - Support for parent-child relationships
   - Time tracking capabilities
   - Estimate points

2. **Rich Metadata**
   - Priority levels (urgent, high, medium, low, none)
   - Labels and custom properties
   - Assignees and watchers
   - Start/target dates
   - External source tracking

3. **Workflow States**
   - Full state lifecycle management
   - Can be moved between states
   - State-based filtering

4. **Features Access**
   - Part of main project views
   - Included in cycles/sprints
   - Included in modules
   - Searchable across workspace
   - Full comment/attachment support

---

## Intake Work Items

### Tool Functions Available
```
- list_intake_work_items
- create_intake_work_item
- retrieve_intake_work_item
- update_intake_work_item
- delete_intake_work_item
```

### Description from MCP Tools

**`list_intake_work_items`**:
> List all intake work items in a project.

**`create_intake_work_item`**:
> Create a new intake work item in a project.
>
> Args: data (as dictionary)

**`retrieve_intake_work_item`**:
> Retrieve an intake work item by work item ID.
>
> Args: work_item_id (use the **issue field** from IntakeWorkItem response,
> not the intake work item ID)

**`update_intake_work_item`**:
> Update an intake work item by work item ID.

### Key Characteristics

1. **Pre-Qualification Zone**
   - Items waiting for review/approval
   - Not yet part of main project workflow
   - Separate "intake view" in Plane UI
   - Triage and prioritization area

2. **Limited Feature Set**
   - Simplified metadata
   - May have different state options
   - Focused on initial assessment

3. **Conversion Workflow**
   - Intake items are reviewed
   - Approved items → converted to regular work items
   - Rejected items → archived or deleted
   - Acts as a filter/gate for the main backlog

4. **Important Note from Tools**
   > **work_item_id**: Use the **issue field** from IntakeWorkItem response,
   > not the intake work item ID

   This suggests intake items have:
   - An intake-specific ID
   - An underlying work item ID (the "issue" field)

---

## Workflow Comparison

### Standard Work Item Workflow
```
Idea/Request
    ↓
Create Work Item (directly in backlog)
    ↓
Assign → Plan (add to cycle/module)
    ↓
Execute (move through states)
    ↓
Complete
```

### Intake Work Item Workflow
```
Idea/Request/Bug Report
    ↓
Create Intake Work Item (in intake view)
    ↓
Review & Triage
    ↓
Decision:
    ├─ Approve → Convert to Work Item → Main Workflow
    ├─ Request More Info → Update Intake Item
    └─ Reject → Archive/Delete
```

---

## When to Use Each

### Use Work Items When:
- ✅ Work is already approved/planned
- ✅ You know the requirements clearly
- ✅ Item should be in active backlog
- ✅ Ready to assign to team members
- ✅ Part of planned cycles/sprints

### Use Intake Work Items When:
- ✅ Collecting ideas from stakeholders
- ✅ Bug reports that need triage
- ✅ Feature requests needing evaluation
- ✅ Items requiring review before commitment
- ✅ Need to filter/qualify before adding to backlog
- ✅ Want to separate "ideas" from "committed work"

---

## Project Configuration

Based on tool descriptions, intake functionality is controlled by:

**`get_project_features`** / **`update_project_features`**:
> Get/Update features of a project.
>
> Args include: epics, modules, cycles, views, pages, **intakes**, work_item_types

The `intakes` feature must be enabled for a project to use intake work items.

---

## Technical Details

### Data Structure Relationship

From the tool descriptions, we can infer:

```python
# IntakeWorkItem has a reference to a WorkItem
{
  "id": "intake-specific-id",
  "issue": "work-item-id",  # The underlying work item ID
  # ... other intake-specific fields
}
```

When you:
1. **Create** an intake item → Creates both an IntakeWorkItem and an underlying WorkItem
2. **Retrieve** an intake item → Use the `issue` field (work item ID), not the intake ID
3. **Convert** to regular work item → The underlying work item moves to main backlog

### Why This Design?

This dual-ID system allows:
- Intake items to leverage the core work item infrastructure
- Additional intake-specific metadata/workflow
- Smooth conversion (just change visibility/state)
- Unified search/query across both types

---

## Common Use Cases

### 1. Customer Support Triage
```
Customer Bug Report
    ↓
Create Intake Work Item
    ↓
Support Team Reviews
    ↓
If Valid → Convert to Work Item (Engineering backlog)
If Duplicate → Link and close
If Not a Bug → Respond and close
```

### 2. Feature Request Evaluation
```
Stakeholder Feature Request
    ↓
Create Intake Work Item
    ↓
Product Team Reviews
    ↓
If Approved → Convert to Work Item (Roadmap)
If Needs Research → Keep in intake, add notes
If Rejected → Archive with explanation
```

### 3. Internal Idea Collection
```
Team Member Idea
    ↓
Create Intake Work Item
    ↓
Weekly Review Meeting
    ↓
Prioritize and convert top ideas
Archive or keep rest for future consideration
```

---

## Summary

**Work Items** = Your main project tasks/issues that are approved and ready for execution.

**Intake Work Items** = A staging area for ideas, requests, and reports that need review before becoming committed work.

The intake system provides:
- **Separation of concerns**: Ideas vs. committed work
- **Triage workflow**: Review before cluttering backlog
- **Quality gate**: Filter out invalid/duplicate/low-priority items
- **Stakeholder management**: Place to collect input without committing to execution

Think of it as:
- **Intake** = "Inbox" for potential work
- **Work Items** = "Tasks" for actual work

---

**References**:
- Plane MCP Server Tool Descriptions
- Tool: `mcp__plane-project-task-manager__*`
