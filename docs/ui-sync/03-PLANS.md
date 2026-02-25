# Plans Directory

> Claude Code v2.1.9 introduced "plan mode" which saves implementation plans as markdown files. Plans are rendered as formatted markdown using `marked` + `isomorphic-dompurify`.

## API Implementation

**Endpoints**:

| Method | Endpoint        | Description              |
| ------ | --------------- | ------------------------ |
| GET    | `/plans`        | List all plans           |
| GET    | `/plans/stats`  | Aggregate statistics     |
| GET    | `/plans/{slug}` | Single plan with content |

**Files**:

- `api/models/plan.py` - Plan model
- `api/routers/plans.py` - Plans endpoints
- `api/schemas.py` - PlanSummary, PlanDetail

**Storage Location**:

```
~/.claude/plans/{slug}.md
```

Example filenames: `abundant-dancing-newell.md`, `cheeky-foraging-wall.md`

---

## Data Schemas

### PlanSummary

```typescript
interface PlanSummary {
	slug: string; // Plan identifier (filename without .md)
	title: string | null; // Extracted from first h1 header
	preview: string; // First 500 characters
	word_count: number;
	created: string; // ISO datetime
	modified: string; // ISO datetime
	size_bytes: number;
}
```

### PlanDetail

```typescript
interface PlanDetail extends PlanSummary {
	content: string; // Full markdown content
}
```

### PlanStats

```typescript
interface PlanStats {
	total_plans: number;
	total_words: number;
	total_size_bytes: number;
	oldest_plan: string; // slug
	newest_plan: string; // slug
}
```

---

## Example Responses

### GET /plans

```json
[
	{
		"slug": "gentle-dancing-fox",
		"title": "Authentication System Implementation",
		"preview": "## Overview\n\nThis plan outlines the implementation of a JWT-based authentication system with the following components:\n\n1. User registration and login endpoints\n2. Token refresh mechanism\n3. Role-based access control\n...",
		"word_count": 847,
		"created": "2026-01-20T14:32:00Z",
		"modified": "2026-01-20T15:45:00Z",
		"size_bytes": 5234
	},
	{
		"slug": "quiet-sleeping-bear",
		"title": "Database Migration Strategy",
		"preview": "## Background\n\nCurrent system uses PostgreSQL 12. This plan covers migration to PostgreSQL 16 with zero downtime...",
		"word_count": 1203,
		"created": "2026-01-18T09:15:00Z",
		"modified": "2026-01-19T11:20:00Z",
		"size_bytes": 7891
	}
]
```

### GET /plans/stats

```json
{
	"total_plans": 12,
	"total_words": 15420,
	"total_size_bytes": 98304,
	"oldest_plan": "ancient-creeping-vine",
	"newest_plan": "gentle-dancing-fox"
}
```

### GET /plans/{slug}

````json
{
	"slug": "gentle-dancing-fox",
	"title": "Authentication System Implementation",
	"preview": "## Overview\n\nThis plan outlines...",
	"word_count": 847,
	"created": "2026-01-20T14:32:00Z",
	"modified": "2026-01-20T15:45:00Z",
	"size_bytes": 5234,
	"content": "## Overview\n\nThis plan outlines the implementation of a JWT-based authentication system...\n\n## Phase 1: User Registration\n\n### Endpoints\n\n```typescript\nPOST /api/auth/register\nPOST /api/auth/login\n```\n\n### Database Schema\n\n..."
}
````

---

## Plan Content Characteristics

Plans are markdown files typically containing:

- H1 title (extracted to `title` field)
- Structured sections (H2, H3)
- Code blocks with language hints
- Bulleted/numbered lists
- Tables (implementation steps, API endpoints)
- Task checkboxes (markdown `- [ ]` syntax)

### Common Sections

| Section              | Purpose                |
| -------------------- | ---------------------- |
| Overview             | High-level description |
| Background           | Context and motivation |
| Requirements         | Acceptance criteria    |
| Architecture         | System design          |
| Implementation Steps | Phased approach        |
| Testing Strategy     | Validation approach    |
| Risks/Concerns       | Potential issues       |

---

## Placement Context

Plans are related to sessions in these ways:

- Created during "plan mode" within a session
- Slug often matches session slug
- Represent work planned for a project

**User preference**: Plans should be accessible under project/sessions context rather than global navigation.

### Possible URL Structures

```
/projects/{encoded_name}/plans                    # Project plans list
/projects/{encoded_name}/plans/{slug}             # Plan detail
/projects/{encoded_name}/{session}/plan           # Session's plan (if linked)
```

---

## Existing Frontend Context

### Related Components

| Component            | Location               | Potential Reuse         |
| -------------------- | ---------------------- | ----------------------- |
| `Card.svelte`        | `components/ui/`       | Plan card container     |
| `Badge.svelte`       | `components/ui/`       | Word count, date badges |
| `PageHeader.svelte`  | `components/layout/`   | Plans page header       |
| `SkeletonBox.svelte` | `components/skeleton/` | Loading state           |

### Markdown Rendering

Plans use the existing in-house markdown setup:

- `marked` - Markdown parser
- `isomorphic-dompurify` - HTML sanitization

The `PlanViewer` component renders plan content using the same pattern as `AgentViewer` and `SkillViewer`.

### Design Tokens

Relevant CSS variables:

- `--bg-muted` - Code block backgrounds
- `--text-secondary` - Preview text
- `--border` - Card borders
- `--font-mono` - Code font

---

## Navigation Considerations

### Project Scope

Plans should be discoverable from:

- Project detail page
- Session detail (if plan exists for that session slug)

### Sidebar/Navigation

Plans may warrant:

- Tab in project detail view
- Link in session overview (when plan exists)
- Breadcrumb: Project > Plans > {slug}

---

## Empty State

Projects/sessions may have no plans:

- `/plans` returns `[]`
- Display appropriate empty state messaging

---

## Test Commands

```bash
# List all plans
curl http://localhost:8000/plans | jq

# Get plan statistics
curl http://localhost:8000/plans/stats | jq

# Get specific plan content
curl http://localhost:8000/plans/gentle-dancing-fox | jq
```

---

## Related API Git Commit

Phase 3 implementation: `d95d673`
