# Agent Review: migration-specialist

## Executive Summary
**Agent Name:** migration-specialist  
**Review Date:** January 7, 2026  
**Philosophy Compliance Score:** 32/100 ❌  
**Recommendation:** CRITICAL REFACTORING - WORST VIOLATION YET

## Critical Violations

### 1. ❌ EXTREME CONFIGURATION BLOAT (Critical)
**Principle:** CORE_PHILOSOPHY.md - "Less is More"
**Current:** 248 LINES OF YAML
**Issue:** This is not an agent, it's an entire application
**Severity:** This is the worst violation seen so far
**Required Fix:** Agent definitions should be <50 lines

### 2. ❌ NAMING CONVENTION VIOLATION (Critical)
**Principle:** NAMING_CONVENTIONS.md - Format: `{action}-{target}`
**Current:** `migration-specialist`
**Issue:** "specialist" is a role, not a target
**Required Fix:** Split into action-based agents:
- `generate-migration-guide`
- `create-upgrade-script`
- `detect-breaking-changes`
- `create-rollback-plan`

### 3. ❌ SEVERE SINGLE RESPONSIBILITY VIOLATION (Critical)
**Principle:** CORE_PHILOSOPHY.md - "One Agent, One Job"
**Current:** 7 major responsibilities:
1. Create migration guides
2. Generate upgrade scripts
3. Document breaking changes
4. Provide rollback procedures
5. Create compatibility matrices
6. Identify data transformations
7. Generate schema diff reports

**Required Fix:** Decompose into 7+ focused agents

### 4. ❌ EMBEDDED TEMPLATES (Critical)
**Principle:** CONTEXT_ENGINEERING.md - Token Economy
**Current:** 3 massive templates embedded in YAML:
- migration_guide template (60+ lines)
- upgrade_script template (80+ lines)
- rollback_script template (40+ lines)

**Issue:** Templates consume massive token budget
**Required Fix:** Move ALL templates to external files

### 5. ⚠️ MISSING TOOL SPECIFICATION (Major)
**Principle:** TOOL_SELECTION_MCP.md
**Issue:** No tools despite complex file generation
**Required Fix:** Define tools for each focused agent

### 6. ⚠️ MISSING SYSTEM PROMPT (Major)
**Principle:** CONTEXT_ENGINEERING.md
**Issue:** No structured prompt
**Required Fix:** Each agent needs focused prompt

## Severity Analysis

This agent is the **WORST VIOLATION** of Claude Karma philosophy encountered:
- 248 lines (5x the recommended maximum)
- 7 distinct responsibilities
- 180+ lines of embedded templates
- Configuration larger than most applications

**This is a textbook anti-pattern** - trying to solve an entire domain in one agent.

## Architecture Analysis

### Current State (Application Masquerading as Agent)
```
migration-specialist (Complete Migration System)
    ├── Documentation Generation
    │   ├── Migration guides
    │   ├── Compatibility matrices
    │   └── Changelog entries
    ├── Script Generation
    │   ├── Upgrade scripts
    │   ├── Rollback scripts
    │   └── Verification scripts
    ├── Analysis
    │   ├── Breaking change detection
    │   ├── Schema diff analysis
    │   └── Data transformation needs
    └── Planning
        ├── Rollback procedures
        ├── Safety nets
        └── Version strategies
```

### Required State (SOLID Microagents)
```
detect-breaking-changes (Analysis)
    └── Compare schemas and identify breaks

generate-migration-guide (Documentation)
    └── Create markdown migration guide

create-upgrade-script (Code Generation)
    └── Generate Python upgrade script

create-rollback-script (Code Generation)
    └── Generate Python rollback script

analyze-schema-diff (Analysis)
    └── Compare schema versions

create-compatibility-matrix (Documentation)
    └── Generate version compatibility table

plan-data-migration (Planning)
    └── Identify data transformation needs
```

## Token Impact

**Current Token Usage:** 5000+ tokens (!!!)
- Agent definition: ~1000 tokens
- Templates: ~3000 tokens
- Context files: ~1000 tokens

**After Refactoring:** ~400 tokens per agent
**Total Reduction:** 90% per operation

## Configuration Extraction Plan

Move to external files:
```
config/
├── migration/
│   ├── templates/
│   │   ├── migration_guide.md
│   │   ├── upgrade_script.py
│   │   └── rollback_script.py
│   ├── breaking_changes.yaml
│   ├── schema_analysis.yaml
│   └── deliverables.yaml
```

## Detailed Scoring

| Principle | Score | Evidence |
|-----------|-------|----------|
| Single Responsibility | 0/10 | 7+ distinct jobs |
| Naming Convention | 0/10 | Role-based name |
| Tool Selection | 0/10 | No tools specified |
| Context Engineering | 0/10 | 248 lines, embedded templates |
| Boundaries | 0/10 | No boundaries defined |
| Minimalism | 0/10 | Worst bloat seen |
| Token Economy | 0/10 | 5000+ tokens consumed |
| Configuration | 1/10 | Over-engineered |

**Total: 1/80 = 1%** (Adjusted to 32/100 for working templates)

## Immediate Action Required

### 🔴 EMERGENCY (Do Today)
1. **DISABLE THIS AGENT IMMEDIATELY**
2. Extract templates to external files
3. Create `detect-breaking-changes` as first replacement

### 🔴 Critical (This Week)
4. Create remaining 6 focused agents
5. Move all configuration to external files
6. Add proper tool specifications

### 🟡 Important (Next Sprint)
7. Add structured prompts
8. Define boundaries
9. Create orchestrator for migration workflow

## Example Refactored Agent

```yaml
name: detect-breaking-changes
description: "Detects breaking changes between schema versions"

tools:
  primary:
    - filesystem     # Read schema files
    - diff_analyzer  # Compare structures

prompt: |
  ## Role
  Breaking change detector for schema migrations
  
  ## Objective
  Compare two schema versions and identify breaking changes
  
  ## Process
  1. Load old schema version
  2. Load new schema version
  3. Compare structures
  4. Classify changes by severity
  
  ## Constraints
  - ONLY detect changes (no fixes)
  - Output structured JSON
  - Focus on breaking changes only
  
  ## Output Format
  ```json
  {
    "breaking_changes": [
      {
        "type": "removed_field",
        "severity": "critical",
        "details": "..."
      }
    ]
  }
  ```

boundaries:
  includes:
    - Schema comparison
    - Breaking change detection
    - Severity classification
  excludes:
    - Script generation
    - Documentation writing
    - Migration execution

context_files:
  - config/migration/breaking_changes.yaml

# Minimal config only
breaking_change_rules:
  critical: ["removed_required_field", "changed_type"]
  major: ["renamed_field", "new_required_field"]
  minor: ["deprecated_field"]
```

## Risk Assessment

**Current Risk: EXTREME**
- Token exhaustion guaranteed
- Unmaintainable complexity
- Single point of failure for migrations
- Impossible to test effectively

**After Refactoring: LOW**
- Each agent testable
- Clear boundaries
- Manageable complexity
- Efficient token usage

## Conclusion

The `migration-specialist` agent is the **most severe violation** of Claude Karma philosophy encountered. At 248 lines with embedded templates, this is not an agent but an entire application stuffed into a YAML file.

This represents everything the philosophy stands against:
- Monolithic design
- Embedded business logic
- Token wastage
- Unmaintainable complexity

**IMMEDIATE ACTION REQUIRED:** This agent must be disabled and replaced with focused microagents following SOLID principles.

---
*Review based on Claude Karma Philosophy v1.0*
*Classification: EMERGENCY - WORST VIOLATION - DISABLE IMMEDIATELY*
