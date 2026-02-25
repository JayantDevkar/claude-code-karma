# Plugins

> Claude Code v2.1.14+ tracks plugin installations. This feature should be extracted from settings and displayed on the dashboard.

## API Implementation

**Endpoints**:

| Method | Endpoint          | Description                   |
| ------ | ----------------- | ----------------------------- |
| GET    | `/plugins`        | List all plugins with summary |
| GET    | `/plugins/stats`  | Aggregate statistics by scope |
| GET    | `/plugins/{name}` | Single plugin details         |

**Files**:

- `api/models/plugin.py` - PluginInstallation, InstalledPlugins models
- `api/routers/plugins.py` - Plugin endpoints
- `api/schemas.py` - Plugin schemas

**Storage Location**:

```
~/.claude/plugins/installed_plugins.json
```

---

## Data Schemas

### PluginsOverview

```typescript
interface PluginsOverview {
	version: number; // Plugin file schema version
	total_plugins: number; // Unique plugin count
	total_installations: number; // Sum of all installations
	plugins: PluginSummary[];
}
```

### PluginSummary

```typescript
interface PluginSummary {
	name: string; // e.g., "github@claude-plugins-official"
	installation_count: number;
	scopes: string[]; // ["user", "project"]
	latest_version: string;
	latest_update: string; // ISO datetime
}
```

### PluginDetail

```typescript
interface PluginDetail {
	name: string;
	installations: PluginInstallation[];
}

interface PluginInstallation {
	plugin_name: string;
	scope: string; // "user" or "project"
	install_path: string;
	version: string;
	installed_at: string; // ISO datetime
	last_updated: string; // ISO datetime
}
```

### PluginStats

```typescript
interface PluginStats {
	total_plugins: number;
	total_installations: number;
	version: number;
	by_scope: {
		user: number;
		project: number;
	};
	oldest_install: string; // ISO datetime
	newest_install: string; // ISO datetime
}
```

---

## Example Responses

### GET /plugins

```json
{
	"version": 2,
	"total_plugins": 3,
	"total_installations": 5,
	"plugins": [
		{
			"name": "github@claude-plugins-official",
			"installation_count": 2,
			"scopes": ["user", "project"],
			"latest_version": "1.2.3",
			"latest_update": "2026-01-21T09:41:35.704Z"
		},
		{
			"name": "playwright@claude-plugins-official",
			"installation_count": 1,
			"scopes": ["user"],
			"latest_version": "1.0.0",
			"latest_update": "2026-01-15T14:22:10.000Z"
		},
		{
			"name": "linear@community-plugins",
			"installation_count": 2,
			"scopes": ["user", "project"],
			"latest_version": "0.9.5",
			"latest_update": "2026-01-10T08:30:00.000Z"
		}
	]
}
```

### GET /plugins/stats

```json
{
	"total_plugins": 3,
	"total_installations": 5,
	"version": 2,
	"by_scope": {
		"user": 3,
		"project": 2
	},
	"oldest_install": "2026-01-03T01:14:29.419Z",
	"newest_install": "2026-01-21T09:41:35.704Z"
}
```

### GET /plugins/{name}

Note: Plugin names contain `@` - use URL encoding.

```bash
curl "http://localhost:8000/plugins/github%40claude-plugins-official" | jq
```

```json
{
	"name": "github@claude-plugins-official",
	"installations": [
		{
			"plugin_name": "github@claude-plugins-official",
			"scope": "user",
			"install_path": "/Users/dev/.claude/plugins/github",
			"version": "1.2.3",
			"installed_at": "2026-01-03T01:14:29.419Z",
			"last_updated": "2026-01-21T09:41:35.704Z"
		},
		{
			"plugin_name": "github@claude-plugins-official",
			"scope": "project",
			"install_path": "/Users/dev/myproject/.claude/plugins/github",
			"version": "1.2.3",
			"installed_at": "2026-01-15T10:00:00.000Z",
			"last_updated": "2026-01-15T10:00:00.000Z"
		}
	]
}
```

---

## Plugin Name Structure

Plugin names follow the pattern: `{plugin-name}@{source}`

| Component   | Description            | Examples                                       |
| ----------- | ---------------------- | ---------------------------------------------- |
| Plugin name | The plugin identifier  | `github`, `playwright`, `linear`               |
| Source      | Plugin registry/author | `claude-plugins-official`, `community-plugins` |

### Common Official Plugins

| Plugin                               | Purpose            |
| ------------------------------------ | ------------------ |
| `github@claude-plugins-official`     | GitHub integration |
| `playwright@claude-plugins-official` | Browser automation |

---

## Scope Semantics

| Scope     | Meaning             | Install Path                 |
| --------- | ------------------- | ---------------------------- |
| `user`    | Global installation | `~/.claude/plugins/`         |
| `project` | Project-specific    | `{project}/.claude/plugins/` |

A plugin can be installed at both scopes simultaneously.

---

## Existing Frontend Context

### Current Settings Integration

`api-types.ts` includes:

```typescript
export interface ClaudeSettings {
	permissions?: PermissionsConfig;
	statusLine?: StatusLineConfig;
	enabledPlugins?: Record<string, boolean>; // Plugin enabled state
	alwaysThinkingEnabled?: boolean;
	cleanupPeriodDays?: number;
}
```

### Settings Page

`/settings` route currently handles permissions and retention. The `enabledPlugins` field suggests some plugin state is already in settings.

**User preference**: Extract plugins display from settings to dashboard.

### Dashboard Context

Home page (`/+page.svelte`) currently shows:

- Navigation cards (Projects, Analytics, Agents, Skills, History, Settings)
- Live Sessions Terminal

### Related Components

| Component                | Location         | Potential Reuse |
| ------------------------ | ---------------- | --------------- |
| `StatsCard.svelte`       | `components/`    | Plugin counts   |
| `Card.svelte`            | `components/ui/` | Plugin card     |
| `Badge.svelte`           | `components/ui/` | Scope badges    |
| `TerminalDisplay.svelte` | `components/`    | Stats display   |

---

## Dashboard Placement Options

### Stats Widget

Small card showing:

- Total plugins installed
- Scope breakdown (user vs project)
- Last updated date

### Navigation Card

Similar to existing nav cards:

- "Plugins" card linking to dedicated view
- Icon + count indicator

### Inline Section

Dedicated section on home page:

- Plugin list with scope badges
- Version information

---

## Visual Considerations

### Scope Badges

| Scope   | Suggested Color | Meaning             |
| ------- | --------------- | ------------------- |
| user    | Blue/Default    | Global installation |
| project | Green/Accent    | Project-specific    |

### Plugin Source

Official plugins (`claude-plugins-official`) may warrant visual distinction from community plugins.

---

## URL Encoding Note

Plugin names contain `@` character. When fetching individual plugins:

```javascript
const pluginName = 'github@claude-plugins-official';
const url = `/plugins/${encodeURIComponent(pluginName)}`;
// Results in: /plugins/github%40claude-plugins-official
```

---

## Empty State

When no plugins are installed:

- `/plugins` returns `{ version: X, total_plugins: 0, plugins: [] }`
- Dashboard widget may show "No plugins installed"

---

## Test Commands

```bash
# List all plugins
curl http://localhost:8000/plugins | jq

# Get plugin statistics
curl http://localhost:8000/plugins/stats | jq

# Get specific plugin (note URL encoding)
curl "http://localhost:8000/plugins/github%40claude-plugins-official" | jq
```

---

## Related API Git Commit

Phase 4 implementation: `55ee419`
