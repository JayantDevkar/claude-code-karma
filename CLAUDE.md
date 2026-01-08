# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code agent and skill development repository. It contains custom agents for task orchestration with Plane (project management), along with a comprehensive philosophy framework for building effective Claude Code agents.

## Repository Structure

```
agents/                     # Active agent definitions (YAML/MD format)
  fetch-plane-tasks/       # Fetches work items from Plane MCP
  analyze-work-item/       # Parses work item content for planning
  plane-task-orchestrator/ # Coordinates work item delegation
  _deprecated/             # Deprecated agents (kept for reference)
philosophy/                # Agent development guidelines
skills/                    # Reusable skill definitions
config/                    # Configuration templates (migration, benchmark)
docs/                      # Implementation notes and reviews
plans/                     # Design documents for features
suggestions/               # Task-specific review notes
```

## Agent Development Philosophy

### Core Principles
1. **Single Responsibility**: One agent, one domain. No Swiss Army knives.
2. **Name = Function**: Use `action-target` format (e.g., `analyze-security`, `fetch-plane-tasks`)
3. **Tool Minimalism**: Maximum 3 primary tools per agent
4. **Prompt Brevity**: Target <500 tokens per prompt
5. **Fail Fast**: Agents recognize limits and suggest alternatives

### Agent Definition Format
Agents use YAML or Markdown frontmatter with this structure:
```yaml
name: action-target
description: "Specific action-oriented description"
model: sonnet  # default; use opus only for complex reasoning
tools:
  primary: [tool1, tool2]  # max 3
  support: [tool3]         # used <80% of time
skills: [skill1, skill2]
boundaries:
  includes: [what agent does]
  excludes: [what agent doesn't do]
```

### Model Selection
- **Sonnet (default)**: Pattern matching, well-defined tasks, speed-critical
- **Opus**: Complex reasoning, multi-step planning, novel problems

### Creating New Agents
1. Define single responsibility and boundaries first
2. Write tests before implementation (TDAD)
3. Select minimal tool set (necessity-driven)
4. Keep prompts precise—every word must earn its place
5. Document error states and fallback behavior

## Current Agent Pipeline

The Plane task orchestration flow:
1. `fetch-plane-tasks` → Queries Plane MCP for work items
2. `analyze-work-item` → Parses description, extracts task type/complexity
3. `plane-task-orchestrator` → Coordinates selection and delegation

## Key Conventions

### Naming
- Agents: `action-target` (hyphens) — e.g., `generate-tests`
- Skills: `domain_operation` (underscores) — e.g., `data_extraction`
- Reserved prefixes: `test-`, `legacy-`, `experimental-`, `core-`

### Skill Categories
- **Foundation**: error_handling, validation, output_formatting
- **Domain**: code_analysis, document_processing, api_integration
- **Bridge**: format_adapters, schema_mapping

### Anti-Patterns to Avoid
- Vague names (`helper`, `assistant`)
- Too many tools (>5 total)
- Verbose prompts (>500 tokens)
- Feature creep in single agent
- Mixing concerns (frontend + backend, testing + implementation)

## MCP Integration

This repo uses Plane MCP for project management integration:
- `mcp__plane-project-task-manager__list_projects`
- `mcp__plane-project-task-manager__list_work_items`
- `mcp__plane-project-task-manager__retrieve_work_item`
- `mcp__plane-project-task-manager__update_work_item`

Project context detection: Agents use `git remote get-url origin` to map repository → Plane project.

## Philosophy Reference

Key documents in `philosophy/`:
- `CORE_PHILOSOPHY.md` — Fundamental principles
- `AGENT_ARCHITECTURE.md` — Structural patterns, resumability
- `NAMING_CONVENTIONS.md` — Naming rules for agents/skills
- `CONTEXT_ENGINEERING.md` — Prompt optimization techniques
- `SKILL_COMPOSITION.md` — Combining skills effectively
- `TOOL_SELECTION_MCP.md` — Tool selection criteria
- `QUICK_REFERENCE.md` — Checklists and decision matrices
