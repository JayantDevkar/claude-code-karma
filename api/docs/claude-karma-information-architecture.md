# Claude Karma UI - Information Architecture

## Overview
This document defines the information architecture, data flow, and state management strategy for Claude Karma UI.

---

## Data Model Hierarchy

```
ClaudeData
├── Projects[]
│   ├── Project
│   │   ├── name: string
│   │   ├── path: string
│   │   ├── encodedName: string
│   │   ├── createdAt: Date
│   │   ├── lastActiveAt: Date
│   │   └── metadata: ProjectMetadata
│   │
│   ├── Sessions[]
│   │   ├── Session
│   │   │   ├── uuid: string
│   │   │   ├── startTime: Date
│   │   │   ├── endTime: Date
│   │   │   ├── duration: number
│   │   │   ├── gitBranch: string
│   │   │   ├── workingDirectory: string
│   │   │   └── model: string
│   │   │
│   │   ├── Messages[]
│   │   │   ├── UserMessage
│   │   │   │   ├── content: string
│   │   │   │   ├── timestamp: Date
│   │   │   │   └── metadata: MessageMetadata
│   │   │   │
│   │   │   └── AssistantMessage
│   │   │       ├── content: ContentBlock[]
│   │   │       ├── model: string
│   │   │       ├── usage: TokenUsage
│   │   │       └── toolCalls: ToolCall[]
│   │   │
│   │   ├── Subagents[]
│   │   │   └── Agent
│   │   │       ├── agentId: string
│   │   │       ├── slug: string
│   │   │       └── messages: Message[]
│   │   │
│   │   ├── ToolResults[]
│   │   │   └── ToolResult
│   │   │       ├── toolUseId: string
│   │   │       ├── content: string
│   │   │       └── size: number
│   │   │
│   │   └── Todos[]
│   │       └── TodoItem
│   │           ├── content: string
│   │           ├── status: TodoStatus
│   │           └── activeForm: string
│   │
│   └── Agents[] (standalone)
│       └── Agent
│           ├── agentId: string
│           └── messages: Message[]
│
└── GlobalStats
    ├── totalSessions: number
    ├── totalTokens: number
    ├── totalDuration: number
    ├── karmaScore: number
    └── dailyActivity: DailyActivity[]
```

---

## Application Routes

```
/                                    # Dashboard (Project List)
├── /projects                        # All projects view
├── /project/:encodedName            # Project detail
│   ├── /timeline                    # Session timeline (default)
│   ├── /analytics                   # Project analytics
│   └── /files                       # File operations view
├── /session/:uuid                   # Session detail
│   ├── /messages                    # Message flow (default)
│   ├── /tools                       # Tool usage
│   ├── /metrics                     # Session metrics
│   └── /raw                         # Raw JSONL viewer
├── /analytics                       # Global analytics
│   ├── /tokens                      # Token usage
│   ├── /tools                       # Tool patterns
│   ├── /models                      # Model distribution
│   └── /karma                       # Karma trends
├── /search                          # Global search
└── /settings                        # App settings
    ├── /appearance                  # Theme settings
    ├── /data                        # Data management
    └── /export                      # Export options
```

---

## State Management Architecture

### Global State Structure (Zustand)

```typescript
interface AppState {
  // Data
  projects: Map<string, Project>
  currentProject: Project | null
  currentSession: Session | null
  
  // UI State
  theme: 'dark' | 'light' | 'auto'
  sidebarCollapsed: boolean
  activeView: ViewType
  
  // Filters
  dateRange: [Date, Date] | null
  modelFilters: string[]
  branchFilters: string[]
  searchQuery: string
  
  // Analytics
  globalStats: GlobalStats | null
  karmaHistory: KarmaPoint[]
  
  // Actions
  loadProject: (path: string) => Promise<void>
  loadSession: (uuid: string) => Promise<void>
  setFilters: (filters: Partial<Filters>) => void
  refreshStats: () => Promise<void>
}
```

### Local Component State

```typescript
// Use local state for:
// - Form inputs
// - Temporary UI states (hover, expand)
// - Animation states
// - Scroll positions

// Example:
function SessionCard() {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isHovered, setIsHovered] = useState(false)
  
  // Global state only for data
  const session = useAppState(state => state.currentSession)
}
```

---

## Data Flow Patterns

### 1. Initial Load Flow

```
User Opens App
    ↓
IndexedDB Check → Has Cache? 
    ↓ No              ↓ Yes
File System Scan   Load Cache
    ↓                 ↓
Parse Projects    Validate
    ↓                 ↓
Build Index      Update if Needed
    ↓                 ↓
Store in State ← ─────┘
    ↓
Render UI
```

### 2. Project Selection Flow

```
User Clicks Project
    ↓
Check Memory Cache
    ↓ Miss
Load from ~/.claude/projects/
    ↓
Parse JSONL Files
    ↓
Calculate Metrics
    ↓
Update State
    ↓
Cache in IndexedDB
    ↓
Navigate to Project View
```

### 3. Search Flow

```
User Types Query
    ↓
Debounce (300ms)
    ↓
Build Search Index (if needed)
    ↓
Execute Search
    ├── Project Names
    ├── Session Descriptions
    ├── Message Content
    └── File Paths
    ↓
Rank Results
    ↓
Update UI (Virtual Scroll)
```

---

## Caching Strategy

### Cache Layers

```
L1: React Component State (Immediate)
    - UI states, form inputs
    - TTL: Component lifecycle

L2: Zustand Store (Session)
    - Current project/session
    - Active filters
    - TTL: Browser session

L3: IndexedDB (Persistent)
    - Parsed project data
    - Calculated metrics
    - Search indices
    - TTL: 7 days or file modification

L4: File System (Source of Truth)
    - ~/.claude/ directory
    - JSONL files
    - TTL: Permanent
```

### Cache Invalidation Rules

```typescript
interface CachePolicy {
  // Invalidate when:
  fileModified: boolean      // Source file changed
  versionMismatch: boolean   // Parser version updated
  ttlExpired: boolean        // Cache age > 7 days
  manualRefresh: boolean     // User forces refresh
  
  // Keep when:
  recentAccess: boolean      // Accessed < 1 hour ago
  currentSession: boolean    // Currently viewing
  pinned: boolean           // User pinned project
}
```

---

## Data Processing Pipeline

### 1. JSONL Parser Pipeline

```
Raw JSONL File
    ↓
Line-by-Line Stream
    ↓
JSON Parse Each Line
    ↓
Type Detection (user/assistant/snapshot)
    ↓
Message Object Creation
    ↓
Content Block Parsing
    ↓
Metadata Extraction
    ↓
Thread Construction
    ↓
Session Object
```

### 2. Metrics Calculation Pipeline

```
Session Object
    ↓
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Token Count  │ Duration     │ Tool Usage   │ Cache Stats  │
│   ↓          │   ↓          │   ↓          │   ↓          │
│ Sum usage    │ End - Start  │ Count tools  │ Calculate    │
│ Group by     │ Handle gaps  │ Group by     │ hit rate     │
│ model        │              │ type         │              │
└──────────────┴──────────────┴──────────────┴──────────────┘
    ↓
Aggregate Metrics Object
```

### 3. Karma Score Pipeline

```
Project Metrics
    ↓
┌─────────────────────────────────────┐
│ Positive Factors      Negative      │
│ - Cache hits     ×2   - Errors  ×0.5│
│ - Completions ×1.5   - Retries ×0.3 │
│ - Efficiency  ×1     - Waste   ×0.4 │
└─────────────────────────────────────┘
    ↓
Weighted Score Calculation
    ↓
Historical Comparison
    ↓
Trend Analysis
    ↓
Karma Score + Trend
```

---

## Search Architecture

### Search Index Structure

```typescript
interface SearchIndex {
  projects: Map<string, ProjectSearchDoc>
  sessions: Map<string, SessionSearchDoc>
  messages: InvertedIndex<MessageSearchDoc>
  files: TrieNode<FileSearchDoc>
}

interface InvertedIndex<T> {
  terms: Map<string, Set<DocumentId>>
  documents: Map<DocumentId, T>
  metadata: IndexMetadata
}
```

### Search Ranking Algorithm

```typescript
function rankResults(query: string, results: SearchResult[]): RankedResult[] {
  return results
    .map(result => ({
      ...result,
      score: calculateScore(query, result)
    }))
    .sort((a, b) => b.score - a.score)
}

function calculateScore(query: string, result: SearchResult): number {
  const factors = {
    exactMatch: result.exactMatch ? 10 : 0,
    titleMatch: result.inTitle ? 5 : 0,
    recency: getRecencyScore(result.timestamp),
    frequency: result.termFrequency * 2,
    position: result.position === 0 ? 3 : 1 / result.position
  }
  
  return Object.values(factors).reduce((a, b) => a + b, 0)
}
```

---

## Performance Optimization Strategies

### 1. Lazy Loading Strategy

```typescript
// Load projects on demand
async function loadProjectLazy(encodedName: string) {
  // Check cache first
  const cached = await getCachedProject(encodedName)
  if (cached && !isStale(cached)) return cached
  
  // Load only metadata first
  const metadata = await loadProjectMetadata(encodedName)
  
  // Load sessions in background
  loadSessionsAsync(encodedName).then(sessions => {
    updateProjectSessions(encodedName, sessions)
  })
  
  return { ...metadata, sessions: [] }
}
```

### 2. Virtual Scrolling Implementation

```typescript
// For message lists > 100 items
function MessageList({ messages }) {
  return (
    <VirtualList
      height={window.innerHeight - 200}
      itemCount={messages.length}
      itemSize={estimateMessageHeight}
      overscan={5}
    >
      {({ index, style }) => (
        <MessageCard
          key={messages[index].id}
          message={messages[index]}
          style={style}
        />
      )}
    </VirtualList>
  )
}
```

### 3. Web Worker Processing

```typescript
// Heavy computations in worker
// worker.ts
self.addEventListener('message', async (event) => {
  const { type, data } = event.data
  
  switch (type) {
    case 'PARSE_JSONL':
      const parsed = await parseJSONL(data)
      self.postMessage({ type: 'PARSED', data: parsed })
      break
      
    case 'CALCULATE_METRICS':
      const metrics = await calculateMetrics(data)
      self.postMessage({ type: 'METRICS', data: metrics })
      break
  }
})

// main.ts
const worker = new Worker('worker.js')
worker.postMessage({ type: 'PARSE_JSONL', data: fileContent })
```

---

## Error Handling & Recovery

### Error Types & Handlers

```typescript
enum ErrorType {
  FILE_NOT_FOUND = 'FILE_NOT_FOUND',
  PARSE_ERROR = 'PARSE_ERROR',
  PERMISSION_DENIED = 'PERMISSION_DENIED',
  CORRUPT_DATA = 'CORRUPT_DATA',
  NETWORK_ERROR = 'NETWORK_ERROR'
}

class ErrorHandler {
  static handle(error: AppError): ErrorRecovery {
    switch (error.type) {
      case ErrorType.FILE_NOT_FOUND:
        return {
          message: 'Project data not found',
          action: 'CHECK_PATH',
          recoverable: true
        }
        
      case ErrorType.PARSE_ERROR:
        return {
          message: 'Failed to parse session data',
          action: 'SKIP_SESSION',
          recoverable: true
        }
        
      case ErrorType.CORRUPT_DATA:
        return {
          message: 'Data corruption detected',
          action: 'REBUILD_INDEX',
          recoverable: false
        }
        
      default:
        return {
          message: 'An unexpected error occurred',
          action: 'RETRY',
          recoverable: true
        }
    }
  }
}
```

### Recovery Strategies

```typescript
async function recoverFromError(error: AppError): Promise<boolean> {
  const recovery = ErrorHandler.handle(error)
  
  if (!recovery.recoverable) {
    // Show error UI
    showErrorBoundary(error)
    return false
  }
  
  switch (recovery.action) {
    case 'CHECK_PATH':
      // Verify ~/.claude exists
      const exists = await checkClaudeDirectory()
      if (!exists) {
        showSetupInstructions()
      }
      break
      
    case 'SKIP_SESSION':
      // Continue with partial data
      logError(error)
      return true
      
    case 'REBUILD_INDEX':
      // Clear cache and rebuild
      await clearCache()
      await rebuildIndex()
      return true
  }
  
  return false
}
```

---

## Security & Privacy

### Data Access Patterns

```typescript
interface SecurityPolicy {
  // Read-only access to ~/.claude
  fileAccess: 'readonly'
  
  // No network requests except for updates
  networkPolicy: 'offline-first'
  
  // Data stays local
  dataStorage: 'local-only'
  
  // Sensitive data masking
  maskPatterns: RegExp[] // [/api[_-]?key/i, /token/i, /secret/i]
}
```

### Privacy Controls

```typescript
interface PrivacySettings {
  // User-controlled data retention
  retentionDays: number // Default: 90
  
  // Opt-in analytics
  allowTelemetry: boolean // Default: false
  
  // Export filters
  exportFilters: {
    excludeMessages: boolean
    excludeFilePaths: boolean
    anonymizeNames: boolean
  }
}
```

---

## Monitoring & Analytics

### Internal Metrics

```typescript
interface AppMetrics {
  performance: {
    loadTime: number
    renderTime: number
    searchTime: number
    cacheHitRate: number
  }
  
  usage: {
    activeProjects: number
    sessionsViewed: number
    searchQueries: number
    exportsGenerated: number
  }
  
  errors: {
    parseFailures: number
    cacheErrors: number
    uiExceptions: number
  }
}
```

### Performance Budget

```
Initial Load:        < 2s
Search Response:     < 100ms
Navigation:          < 200ms
Memory Usage:        < 200MB
Cache Size:          < 50MB
```

---

## Data Export Formats

### JSON Export

```json
{
  "version": "1.0",
  "exportDate": "2026-01-09T10:00:00Z",
  "project": {
    "name": "aruba-backend",
    "path": "/Users/.../aruba-backend",
    "sessions": [
      {
        "uuid": "abc123...",
        "startTime": "2026-01-09T09:00:00Z",
        "messages": [...],
        "metrics": {...}
      }
    ]
  }
}
```

### CSV Export

```csv
Project,Session,Start Time,Duration,Messages,Tokens,Cache Hit Rate,Model
aruba-backend,abc123,2026-01-09 09:00,45m,87,125000,72%,opus-4-5
aruba-backend,def456,2026-01-08 14:00,30m,45,67000,84%,sonnet-4
```

### Markdown Report

```markdown
# Claude Karma Report - aruba-backend

Generated: 2026-01-09

## Overview
- Total Sessions: 47
- Total Tokens: 1.2M
- Average Cache Hit: 73%

## Recent Sessions

### Session 1 (2026-01-09)
Duration: 45 minutes
Model: opus-4-5
Summary: Implemented WebSocket handler...
```

---

## Migration & Versioning

### Schema Versions

```typescript
interface SchemaVersion {
  version: string
  migrations: Migration[]
}

const SCHEMA_VERSIONS: SchemaVersion[] = [
  {
    version: '1.0.0',
    migrations: []
  },
  {
    version: '1.1.0',
    migrations: [
      {
        name: 'add-karma-score',
        up: (data) => ({ ...data, karmaScore: 0 }),
        down: (data) => omit(data, 'karmaScore')
      }
    ]
  }
]
```

### Backward Compatibility

```typescript
function parseWithCompatibility(jsonl: string, version?: string) {
  const currentVersion = CURRENT_VERSION
  const dataVersion = version || detectVersion(jsonl)
  
  if (dataVersion < currentVersion) {
    return migrateData(parseJSONL(jsonl), dataVersion, currentVersion)
  }
  
  return parseJSONL(jsonl)
}
```

---

## Future Considerations

### Planned Features

1. **Real-time Monitoring**
   - WebSocket connection to active sessions
   - Live token counter
   - Real-time tool usage

2. **Team Features**
   - Shared dashboards
   - Team karma leaderboard
   - Collaborative annotations

3. **AI Insights**
   - Pattern detection
   - Optimization suggestions
   - Anomaly alerts

4. **Plugin System**
   - Custom metrics
   - Third-party integrations
   - Export plugins

---

This information architecture provides the foundation for building a scalable, performant, and maintainable Claude Karma UI application.