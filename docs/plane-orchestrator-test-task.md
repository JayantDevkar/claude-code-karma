# Test Work Item: Plane Task Orchestrator Agent System

## Title
Test Plane Task Orchestrator Agent System

## Type
Task

## Priority
High

## Description

Test the complete orchestration flow of Plane task agents by having the system fetch, analyze, and delegate this work item through the agent pipeline.

### What to Test

**Orchestration Flow:**
1. Fetch this work item from Plane using the `fetch-plane-tasks` agent
2. Parse and extract structured information from this work item using `analyze-work-item` agent
3. Match task requirements to available agents using `select-agent`
4. Delegate the work item context to the selected agent
5. Execute the implementation task described below
6. Report back completion status

**Implementation Task (for the selected agent to execute):**

Create a new REST API endpoint `/api/v1/user/preferences` with the following requirements:

- **Method**: GET and PUT
- **Authentication**: Required (use existing auth middleware)
- **GET Response**: Return user preferences as JSON
  ```json
  {
    "theme": "dark",
    "notifications": true,
    "language": "en"
  }
  ```
- **PUT Request**: Accept preferences object and update user settings
- **Validation**: Validate theme (light/dark), notifications (boolean), language (2-letter ISO code)
- **Database**: Store in a new `user_preferences` table or JSON column
- **Tests**: Add unit tests for GET and PUT endpoints
- **Error Handling**: Return appropriate HTTP status codes (400, 401, 404, 500)

### Acceptance Criteria

**Orchestrator System:**
- [ ] `plane-task-orchestrator` successfully fetches this work item from Plane
- [ ] `analyze-work-item` correctly extracts the implementation task details
- [ ] `select-agent` identifies this as a code implementation task
- [ ] Selected agent receives properly formatted work item context
- [ ] Agent completes the implementation task
- [ ] All agent transitions complete without errors
- [ ] Task status updates properly throughout workflow

**Implementation:**
- [ ] `/api/v1/user/preferences` GET endpoint returns user preferences
- [ ] `/api/v1/user/preferences` PUT endpoint updates preferences
- [ ] Authentication middleware is applied
- [ ] Input validation works correctly
- [ ] Preferences are persisted to database
- [ ] Unit tests pass
- [ ] Error responses use correct HTTP status codes

### Labels
- `testing`
- `agent-orchestration`
- `automation`

### Estimated Time
2-3 hours (including orchestration testing)

---

**Instructions for Manual Creation:**
1. Go to your Plane workspace
2. Navigate to the Claude Karma project
3. Create new issue with the above details
4. Copy the work item ID
5. Run the orchestrator to fetch and process this task
