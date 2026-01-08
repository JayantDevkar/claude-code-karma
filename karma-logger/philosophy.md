Karma Logger is a **local-first metrics system** for Claude Code that transforms opaque AI agent activity into actionable insights. By parsing JSONL logs in real-time, it provides developers with visibility into token consumption, agent hierarchies, tool usage patterns, and session costs—enabling informed decisions about AI-assisted development workflows.

**Core Value Proposition:** Turn invisible AI work into visible metrics, making AI development costs and patterns as transparent as traditional CI/CD pipelines.


## The Problem Space

### Current Pain Points

1. **Opacity of Agent Work**

   * Developers spawn agents without understanding cumulative costs

   * No visibility into which agents consume the most resources

   * Difficult to optimize prompts without usage data

2. **Lost Context Across Sessions**

   * Each session starts fresh with no memory of patterns

   * Successful agent strategies aren't captured for reuse

   * No way to track project-level AI usage trends

3. **Hierarchy Blindness**

   * Parent spawns child agents, but the tree is invisible

   * Can't identify wasteful agent cascades

   * No way to detect infinite loops or redundant work

4. **Cost Attribution Vacuum**

   * Total API costs visible, but not per-project or per-feature

   * Can't justify AI tooling costs with concrete metrics

   * No budget tracking or alerts for expensive operations

### Mission

Build a **privacy-first, local metrics system** that:

1. Captures 100% of Claude Code agent activity

2. Provides real-time cost visibility

3. Enables pattern discovery and optimization

4. Respects developer privacy (no cloud dependency)
### Local-First Architecture

**Principle:** All data processing happens on the developer's machine.

**Rationale:**

* Privacy is non-negotiable for code-related metrics

* No latency from network calls

* Works offline, works in secure environments

* Developer owns their data completely

**Trade-offs:**

* No cross-team aggregation without explicit sharing

* Must be resource-efficient to not impact development

* Requires thoughtful data retention policies

### 2. Real-Time Insight

**Principle:** Metrics are available within 100ms of agent action.

**Rationale:**

* Developers need immediate feedback to adjust prompts

* Cost overruns must trigger alerts before damage

* Live visualization creates awareness and learning

**Trade-offs:**

* Requires efficient streaming architecture

* Must handle high-frequency updates gracefully

* Battery impact on laptops must be minimal

### 3. Hierarchical Truth

**Principle:** The agent tree is the primary mental model.

**Rationale:**

* Mirrors how developers think about task delegation

* Enables root-cause analysis of expensive operations

* Natural aggregation boundary for metrics

**Trade-offs:**

* Complex UI requirements for tree visualization

* Must handle incomplete trees (crashed agents)

* Circular dependencies need detection

###

// Core Entities
interface Session {
  id: string;           // Session UUID
  project_path: string; // Encoded project path
  started_at: Date;
  ended_at?: Date;
  total_cost: number;
  agent_count: number;
  model: string;        // Primary model (opus/sonnet)
}

interface Agent {
  id: string;           // 7-char hex
  session_id: string;
  parent_uuid?: string; // For hierarchy
  type: 'main' | 'task' | 'bash' | 'explore' | 'refactor';
  model: string;
  created_at: Date;
  completed_at?: Date;
  status: 'running' | 'completed' | 'failed';
  
  // Metrics
  tokens_in: number;
  tokens_out: number;
  tokens_cached: number;
  cost: number;
  duration_ms: number;
  
  // Context
  task_description?: string;
  tools_used: string[];
  files_touched: string[];
}

interface AgentHierarchy {
  agent_id: string;
  children: AgentHierarchy[];
  depth: number;
  cumulative_cost: number;    // Including all descendants
  cumulative_tokens: number;
}

interface Pattern {
  id: string;
  name: string;             // e.g., "Expensive Exploration"
  description: string;
  detection_rule: string;    // JSONLogic or similar
  occurrences: number;
  total_cost_impact: number;
  suggestions: string[];
}
