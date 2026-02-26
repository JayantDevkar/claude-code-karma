# Claude Karma Features

> A comprehensive guide to all features available in the Claude Karma dashboard for monitoring and analyzing Claude Code sessions.

---

## Table of Contents

- [Home Dashboard](#home-dashboard)
- [Projects](#projects)
- [Sessions](#sessions)
- [Session Detail View](#session-detail-view)
- [Analytics](#analytics)
- [Agents](#agents)
- [Skills](#skills)
- [Plans](#plans)
- [Settings](#settings)
- [Additional Features](#additional-features)

---

## Home Dashboard

**Route:** `/`

The central hub for quick navigation and live session monitoring.

### Features

- **Navigation Grid** — 9 cards for quick access to all sections:
  - Projects, Sessions, Analytics, Plans, Skills, Agents, Plugins, Settings, Archived
- **Live Sessions Terminal** — Real-time view of active Claude Code sessions
- **Terminal Stats Display** — Quick overview of session statistics
- **Clean, minimalist interface** — Focus on what matters most

---

## Projects

**Route:** `/projects`

Browse and manage all your Claude Code projects.

### Project List Features

- **Search & Filter** — Find projects quickly by name
- **Sort Options** — By name, sessions, last active
- **Project Cards** — Show key metrics at a glance:
  - Session count
  - Agent count
  - Git repository status
  - Last active time
- **Git Integration** — Visual indicators for git-tracked projects

### Project Detail View

**Route:** `/projects/[project_name]`

Comprehensive project overview with tabbed navigation.

#### Overview Tab (Default)

- **Stats Grid** — Real-time metrics:
  - Total sessions
  - Total tokens (with input/output breakdown)
  - Total duration
  - Estimated cost
  - Cache hit rate
- **Live Sessions Section** — Currently active sessions for this project
- **Active Branches** — Git branch filters with session counts
- **Recent Sessions** — Time-grouped session cards:
  - Today, Yesterday, This Week, This Month, Older
  - List view (time-grouped) or Grid view (compact)
  - Search with token-based filtering
  - Advanced filters (status, date range, scope, live sub-statuses)
  - Branch filtering (multi-select)
- **Recently Ended Sessions** — Sessions that ended within 45 minutes
- **Pagination** — Navigate through large session lists
- **Filter Chips** — Visual representation of active filters
- **Session Cards** — Rich session previews with:
  - Title and slug
  - Start time and duration
  - Token usage
  - Live status indicators
  - Git branch badges
  - Model badges (Opus, Sonnet, Haiku)

#### Agents Tab

**Route:** `/projects/[project_name]/agents`

- **Agent usage breakdown** for this project
- **Session count** per agent
- **Cost tracking** by agent
- **Navigation to agent detail** pages

#### Skills Tab

**Route:** `/projects/[project_name]/skills`

- **Skill usage analytics** for this project
- **File browser** for skill files
- **Invocation counts** per skill
- **Category filtering** (hooks, commands, etc.)

#### Analytics Tab

- **Time-filtered insights** (24h, 7d, 30d, all time)
- **Sessions over time** chart
- **Time Investment** — Total duration and cost breakdown
- **Work Mode Distribution** — Exploration vs. Building vs. Testing percentages
- **Token usage trends**
- **Cache efficiency metrics**

#### Archived Tab

- **Archived sessions** cleaned up by retention policy
- **Archived prompt cards** with metadata
- **Session count** and prompt count summaries

---

## Sessions

**Route:** `/sessions`

Global view of all Claude Code sessions across all projects.

### Features

- **Token-based Search** — Multi-token AND search:
  - Search in titles, prompts, slugs
  - Scope selection (titles only, prompts only, or both)
- **Project Filter** — Filter by specific project
- **Branch Filter** — Filter by git branch (multi-select)
- **Status Filter** — All, Live, or Completed
- **Live Sub-status Filter** — Active, Waiting, Idle, Starting, Ended
- **Date Range Filter** — Today, Yesterday, This Week, This Month, Custom range
- **View Modes:**
  - **List View** — Time-grouped with larger cards
  - **Grid View** — Compact 4-column layout
- **Live Sessions Section** — Real-time active sessions
- **Recently Ended Section** — Sessions ended within 45 min
- **Time-based Grouping** — Sessions organized by recency
- **Pagination** — Navigate through session history
- **Live Status Indicators** — Real-time status updates
- **Filter Persistence** — URL-based filter state for sharing
- **Keyboard Shortcuts** — CTRL+K to focus search

### Session Cards Display

Each session card shows:
- Project name and path
- Session title (auto-generated or custom)
- Slug (unique identifier)
- Start time and duration
- Token usage (input/output)
- Estimated cost
- Model used (with color-coded badges)
- Git branches
- Live status (if active)
- Compaction indicator (if session was compacted)

---

## Session Detail View

**Route:** `/projects/[project_name]/[session_slug]`

Deep dive into individual Claude Code sessions with comprehensive analysis.

### Tabs

#### Conversation Tab (Default)

- **Full conversation history** — All messages between user and Claude
- **Message types:**
  - User messages (prompts)
  - Assistant messages (responses)
  - Tool calls and results
  - File history snapshots
  - Summary messages (for compacted sessions)
- **Live tailing** — Auto-scroll for active sessions
- **Markdown rendering** — Proper formatting with syntax highlighting
- **Code blocks** — Syntax-highlighted code snippets
- **Thinking blocks** — Claude's reasoning process (if available)

#### Timeline Tab

- **Event-based timeline** — Chronological view of session activity:
  - Tool calls (Read, Write, Edit, Bash, Grep, etc.)
  - Task updates (created, in progress, completed)
  - Plan events (enter/exit plan mode)
  - Subagent spawns
  - Permission requests
- **Event filtering** — Filter by event type
- **Time gaps** — Visual indicators for idle periods
- **Expandable details** — Click events for full context
- **Tool call parameters** — See exact tool inputs/outputs
- **Bash command execution** — View command results

#### File Activity Tab

- **File operations table** — All file changes:
  - Read operations
  - Write operations (new files)
  - Edit operations (modifications)
- **File path** with syntax highlighting
- **Operation count** per file
- **Timestamp** for each operation
- **Sort options** — By path, operations, or time

#### Tools Tab

- **Tool usage breakdown:**
  - Tool name
  - Invocation count
  - Tool category
- **Pie chart visualization** — Visual distribution
- **Color-coded categories** — Easy identification
- **Search/filter** — Find specific tools

#### Subagents Tab

- **Subagent activity** — All spawned agents:
  - Agent type (explore, executor, planner, etc.)
  - Model used (Opus, Sonnet, Haiku)
  - Start time and duration
  - Status (completed, failed, etc.)
  - Token usage
  - Cost
- **Grouped by session** — Nested subagent hierarchies
- **Click to view** — Navigate to subagent detail
- **Summary stats** — Total subagents, cost, tokens

#### Tasks Tab

- **Task management view:**
  - Task list with status (pending, in progress, completed, deleted)
  - Task dependencies (blocks/blocked by)
  - Task owners (for team mode)
  - Task descriptions and metadata
- **Kanban view** — Visual task board
- **Task flow diagram** — Dependency visualization
- **Progress tracking** — Completion percentages

#### Plan Tab

- **Plan viewer** (if session used plan mode):
  - Full plan content (Markdown)
  - Plan metadata (created, modified)
  - Plan status (approved, rejected, pending)
- **Plan file download** — Export plan as .md

#### Skills Tab

- **Skills used** in this session:
  - Skill name
  - Invocation count
  - Category
- **Skill file paths** — Navigate to source

#### Commands Tab

- **Commands executed:**
  - Command name
  - Invocation count
  - Category

### Session Header

- **Project breadcrumb** — Navigate back to project
- **Session metadata:**
  - Session slug
  - Start time
  - Duration
  - Model used
  - Git branches
- **Live status badge** — If session is active
- **Stats summary:**
  - Total tokens
  - Input/output breakdown
  - Estimated cost
  - Cache hit rate
  - Message count

---

## Analytics

**Route:** `/analytics`

Global analytics dashboard for coding patterns and AI collaboration insights.

### Features

- **Time Filter** — Analyze specific periods:
  - Last 6/12/24 hours
  - Last 7/30/90 days
  - All time
- **Hero Stats:**
  - Total sessions
  - Total cost
  - Cache hit rate
- **Velocity Section:**
  - Sessions over time (bar chart)
  - Average sessions per day/hour
  - 14-day sparkline
  - Token usage context
  - Total duration
- **Efficiency Section:**
  - Cache hit rate with progress bar
  - Active projects count
  - Compute DNA (model distribution):
    - Opus/Sonnet/Haiku usage percentages
    - Visual distribution bar
- **Rhythm Section:**
  - Time distribution (morning, afternoon, evening, night)
  - Peak hours identification
  - Absolute time spent per period
  - Visual progress bars
- **Collapsible groups** — Expand/collapse sections
- **Responsive charts** — Interactive Chart.js visualizations

---

## Agents

**Route:** `/agents`

Comprehensive agent usage analytics and management.

### Features

- **Category Filters:**
  - All
  - Built-in (Claude Code's native agents)
  - Plugins (from MCP plugins)
  - Custom (user-defined agents)
  - Project (project-specific agents)
- **Search** — Find agents by name
- **Stats Grid:**
  - Total agents
  - Total runs
  - Total cost
- **Agent Cards** — Rich detail cards showing:
  - Agent name and type
  - Total runs
  - Average duration
  - Token usage
  - Cost per run
  - Last used timestamp
  - Model distribution
- **Grouped Display:**
  - Built-in Agents group
  - Plugin groups (one per plugin)
  - Custom Agents group
  - Project Agents group
- **Expand/Collapse** — Manage group visibility
- **Pagination** — Navigate large agent lists
- **Agent Detail Pages** — Click through for deeper analysis

### Agent Detail View

**Route:** `/agents/usage/[agent_type]`

- **Usage timeline** — Agent runs over time
- **Session list** — All sessions using this agent
- **Cost breakdown** — Detailed cost analysis
- **Performance metrics** — Average duration, success rate

---

## Skills

**Route:** `/skills`

Global skills usage and file browsing.

### Features

#### Usage Analytics Tab (Default)

- **Skill usage cards:**
  - Skill name and path
  - Invocation count
  - Category (hooks, commands, etc.)
  - Last used timestamp
- **Search** — Find skills by name or path
- **Category filter** — Filter by skill type
- **Sort options** — By usage, name, or recency

#### Browse Files Tab

- **File explorer** — Navigate skill directories
- **Directory tree** — Hierarchical file structure
- **File viewer** — View skill file contents
- **Syntax highlighting** — For code files
- **Path navigation** — Breadcrumb trail

### Skill Detail View

**Route:** `/skills/[skill_name]`

- **File content viewer** — Full skill source code
- **Usage statistics** — Sessions using this skill
- **Invocation history** — Timeline of usage

---

## Plans

**Route:** `/plans`

Browse implementation plans from Claude Code plan mode sessions.

### Features

- **Search** — Token-based search in plan content
- **Project Filter** — Filter by project
- **Branch Filter** — Filter by git branch
- **Plan Cards** — Preview cards showing:
  - Plan title
  - Session context (project, branch)
  - Created/modified timestamps
  - Plan content preview
  - Approval status
- **Time-based Grouping** — Today, Yesterday, This Week, etc.
- **Pagination** — Navigate plan history
- **Click to expand** — View full plan content

### Plan Detail View

**Route:** `/plans/[slug]`

- **Full plan content** — Markdown-rendered implementation plan
- **Metadata:**
  - Associated session
  - Created/modified times
  - Approval status
- **Session link** — Navigate to source session

---

## Settings

**Route:** `/settings`

Configure your Claude Code environment.

### Sections

#### General

- **Session Retention:**
  - 7, 14, 30, 60, 90 days, or Never
  - Automatic cleanup of old sessions
- **Extended Thinking:**
  - Enable "always thinking" mode
  - Toggle for deeper reasoning

#### Permissions

- **Default Permission Mode:**
  - Default (ask for each tool)
  - Accept Edits (auto-approve edits)
  - Bypass Permissions (trust mode)
  - Delegate (defer to subagents)
  - Don't Ask (auto-approve specific tools)
- **Permission List:**
  - Add/remove allowed tools
  - Manage tool permissions

#### Plugins

- **Plugin toggle switches** — Enable/disable plugins
- **Plugin status** — View enabled plugins

#### Advanced

- **Status Line Command** — Custom status line configuration
- **Raw JSON View** — Inspect full settings object

---

## Additional Features

### Global Features

#### Navigation

- **Persistent Header** (on all pages except home):
  - Desktop: Inline links to all sections
  - Mobile: Hamburger menu
  - Settings gear icon (top-right)
  - Brand link back to home
- **Breadcrumbs** — Navigate page hierarchy
- **Keyboard Shortcuts:**
  - CTRL+K — Focus search
  - List navigation — Arrow keys for session lists

#### Command Palette

- **Quick navigation** — Search for pages and entities
- **Keyboard-driven** — Fast access to any section

#### Live Sessions Monitoring

- **Real-time polling** (3-second intervals)
- **Status indicators:**
  - Active (working)
  - Waiting (awaiting user input)
  - Idle (paused)
  - Starting (initializing)
  - Ended (recently completed)
- **Duration tracking** — Active + idle time
- **Stuck session cleanup** — Remove orphaned sessions

#### Filtering & Search

- **Token-based search** — Multi-token AND logic
- **URL state persistence** — Shareable filter URLs
- **Active filter chips** — Visual filter representation
- **Quick clear** — Remove all filters at once

#### View Modes

- **List View** — Time-grouped, larger cards
- **Grid View** — Compact, 4-column layout
- **Persistent preference** — Saved to localStorage

#### Themes

- **Light/Dark mode** — Auto-switching based on system preference
- **Design tokens** — Consistent color palette
- **Custom properties** — CSS variables for theming

### Data Visualization

#### Charts (Chart.js)

- **Sessions over time** — Bar charts
- **Tool usage** — Pie charts
- **Time distribution** — Progress bars
- **Model distribution** — Stacked bars

#### Stats Display

- **Stats Grid** — Reusable stat cards with:
  - Icon
  - Title
  - Value
  - Color coding
  - Token breakdowns
- **Collapsible Groups** — Expandable sections with metadata

### Performance Features

- **Skeleton Loaders** — Loading states for all pages
- **Lazy Loading** — Load data on demand
- **Pagination** — Handle large datasets
- **Client-side Filtering** — Fast filter operations
- **Debounced Search** — Smooth search experience

### Accessibility

- **Keyboard Navigation** — Full keyboard support
- **ARIA Labels** — Screen reader friendly
- **Focus Management** — Proper focus handling
- **Semantic HTML** — Accessible structure

---

## Feature Summary by Page

| Page | Key Features |
|------|--------------|
| **Home** | Navigation grid, live sessions terminal, quick stats |
| **Projects** | List all projects, search, project detail with tabs |
| **Sessions** | Global session search, filters, live monitoring |
| **Session Detail** | Conversation, timeline, files, tools, subagents, tasks, plan |
| **Analytics** | Velocity, efficiency, rhythm analysis with charts |
| **Agents** | Agent usage analytics, categories, detail views |
| **Skills** | Usage analytics, file browser, skill details |
| **Plans** | Plan browser, search, project/branch filters |
| **Hooks** | Hook scripts browser, event tracking, activity logs |
| **Plugins** | MCP plugins browser, status display |
| **Tools** | Tool usage analytics and details |
| **Settings** | Retention, permissions, plugins, advanced config |
| **Archived** | View archived sessions, restore options |
| **About** | Project information and documentation |

---

## Technology Stack

- **Frontend:** SvelteKit 2 + Svelte 5 (with runes)
- **Styling:** Tailwind CSS 4
- **Charts:** Chart.js 4
- **UI Components:** bits-ui (accessible primitives)
- **Icons:** lucide-svelte
- **Date Handling:** date-fns
- **Markdown:** marked + isomorphic-dompurify
- **Backend:** FastAPI (Python) on port 8000
- **Real-time:** Polling (3s for live sessions, 30s for historical)

---

## User Value Proposition

Claude Karma provides **complete visibility** into your Claude Code sessions with:

1. **Real-time Monitoring** — See what Claude is doing right now
2. **Historical Analysis** — Understand your coding patterns over time
3. **Cost Tracking** — Monitor AI usage costs and optimize spending
4. **Performance Insights** — Identify bottlenecks and improve efficiency
5. **Session Management** — Organize and search your work history
6. **Agent Analytics** — Understand which agents you use most
7. **Skill Tracking** — See which skills and tools are most valuable
8. **Plan Management** — Review implementation plans and decisions
9. **Configuration Control** — Customize Claude Code behavior
10. **Shareable State** — URL-based filters for team collaboration

---

**Built with ❤️ for Claude Code power users.**
