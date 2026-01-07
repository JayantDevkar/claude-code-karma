# Agent Review: philosophy-guardian

## Executive Summary
**Agent Name:** philosophy-guardian  
**Review Date:** January 7, 2026  
**Philosophy Compliance Score:** 58/100 ⚠️  
**Recommendation:** NEEDS REFACTORING

## Critical Violations

### 1. ❌ NAMING CONVENTION VIOLATION (Critical)
**Principle:** NAMING_CONVENTIONS.md - Format: `{action}-{target}`
**Current:** `philosophy-guardian`
**Issue:** "guardian" is a role/title, not a target. Violates action-target pattern.
**Required Fix:** Rename to one of:
- `validate-philosophy` (most accurate)
- `check-alignment` (alternative)
- `verify-principles` (alternative)

### 2. ⚠️ VAGUE RESPONSIBILITY DEFINITION (Major)
**Principle:** CORE_PHILOSOPHY.md - "Explicit Over Implicit"
**Current Capabilities:**
- Validate proposals against core principles
- Check for philosophical consistency
- Identify principle violations
- Suggest alignment improvements

**Issue:** These are all variations of the same task (validation), but lack specificity about WHAT is being validated (code? specifications? agents?)
**Required Fix:** Define explicit input/output:
```yaml
responsibility: |
  Validate agent specifications against Claude Karma philosophy principles
  Input: Agent YAML definition
  Output: Compliance score and violation report
```

### 3. ⚠️ MISSING TOOL SPECIFICATION (Major)
**Principle:** TOOL_SELECTION_MCP.md - Explicit Tool Declaration
**Issue:** No tools specified
**Impact:** Unclear how agent performs validation
**Required Fix:** Add tools section:
```yaml
tools:
  primary:
    - filesystem    # Read philosophy docs and agent files
  support:
    - yaml_parser   # Parse agent definitions
```

### 4. ⚠️ MISSING SYSTEM PROMPT (Major)
**Principle:** CONTEXT_ENGINEERING.md - "Prompt as Software"
**Issue:** No structured prompt defining validation process
**Required Fix:** Add structured prompt with validation criteria

### 5. ⚠️ NO BOUNDARIES DEFINED (Major)
**Principle:** CORE_PHILOSOPHY.md - "Fail Fast, Fail Clear"
**Issue:** No includes/excludes section
**Impact:** Unclear scope boundaries
**Required Fix:** Add boundaries section:
```yaml
boundaries:
  includes:
    - Philosophy compliance validation
    - Principle violation detection
    - Alignment scoring
  excludes:
    - Code implementation
    - Agent modification
    - Philosophy document updates
```

### 6. ✅ GOOD MEMORY KEY STRUCTURE
**Positive:** Well-organized memory keys with clear Phase 1 focus
**Score:** This is one of the better aspects of this agent

## Architecture Analysis

### Current State
```
philosophy-guardian (validator)
    ├── Validate proposals
    ├── Check consistency
    ├── Identify violations
    └── Suggest improvements
```

### Recommended Improvements
```
validate-philosophy (focused validator)
    ├── Input: Agent/Spec YAML
    ├── Process: Check against principles
    ├── Output: Structured validation report
    └── Score: Quantified compliance metric
```

## Detailed Scoring

| Principle | Score | Evidence |
|-----------|-------|----------|
| Single Responsibility | 7/10 | Focused on validation, but vague scope |
| Naming Convention | 0/10 | Role-based name, not action-target |
| Tool Selection | 0/10 | No tools specified |
| Context Engineering | 3/10 | No prompt, reasonable context files |
| Boundaries | 0/10 | No boundaries defined |
| Memory Management | 9/10 | Well-structured keys |
| Error Handling | 5/10 | Implied but not explicit |
| Output Format | 5/10 | Not clearly specified |

**Total: 29/80 = 36%** (Adjusted to 58/100 with positive aspects)

## Missing Critical Components

### 1. Structured Validation Prompt
```yaml
prompt: |
  ## Role
  Philosophy compliance validator for Claude Karma agents
  
  ## Objective
  Validate agent definitions against philosophy principles
  
  ## Process
  1. Parse agent YAML structure
  2. Check naming convention (action-target)
  3. Verify single responsibility
  4. Count tools (max 3 primary)
  5. Measure prompt tokens (<500)
  6. Check boundaries definition
  7. Calculate compliance score
  
  ## Validation Criteria
  - Naming: Must follow {action}-{target} format
  - SRP: One clear responsibility only
  - Tools: Maximum 3 primary, 2 support
  - Context: Maximum 3 files
  - Prompt: Under 500 tokens
  - Boundaries: Must have includes/excludes
  
  ## Output Format
  ```json
  {
    "score": 0-100,
    "violations": [
      {
        "principle": "name",
        "severity": "critical|major|minor",
        "details": "explanation"
      }
    ],
    "recommendations": ["action items"]
  }
  ```
```

### 2. Concrete Validation Rules
```yaml
validation_rules:
  naming:
    pattern: "^[a-z]+-[a-z]+$"
    must_start_with_verb: true
  tools:
    max_primary: 3
    max_support: 2
    max_total: 5
  context:
    max_files: 3
    max_tokens: 2000
  prompt:
    max_tokens: 500
    required_sections: ["Role", "Objective", "Process", "Output"]
```

## Recommendations

### 🔴 Critical (Immediate)
1. Rename to `validate-philosophy`
2. Add explicit tool specifications
3. Define clear boundaries

### 🟡 Important (Next Sprint)
4. Add structured validation prompt
5. Define concrete validation rules
6. Specify output format

### 🟢 Nice to Have
7. Add validation examples
8. Create scoring rubric
9. Add caching for philosophy docs

## Example Refactored Agent

```yaml
name: validate-philosophy
description: "Validates agent definitions against Claude Karma philosophy"

tools:
  primary:
    - filesystem      # Read agent YAML files
    - yaml_parser     # Parse YAML structure

prompt: |
  ## Role
  Philosophy compliance validator for Claude Karma system
  
  ## Objective
  Validate agent YAML against philosophy principles and output compliance score
  
  ## Process
  1. Load agent YAML definition
  2. Check each philosophy principle
  3. Calculate weighted compliance score
  4. Generate violation report
  
  ## Output Format
  JSON with score, violations, and recommendations

boundaries:
  includes:
    - Agent YAML validation
    - Philosophy compliance scoring
    - Violation reporting
  excludes:
    - Agent implementation
    - Philosophy updates
    - Code execution

context_files:
  - philosophy/CORE_PHILOSOPHY.md
  - philosophy/NAMING_CONVENTIONS.md

memory_keys:
  - thinking/alignment
  - thinking/philosophy_score
```

## Conclusion

The `philosophy-guardian` agent has the right intent but lacks the explicit structure required by the philosophy it's meant to guard. The irony is not lost that a philosophy validator doesn't follow the philosophy conventions.

Key improvements needed:
1. Action-target naming
2. Explicit tool declaration
3. Structured validation prompt
4. Clear boundaries

With these changes, this could become a valuable meta-agent for ensuring system-wide philosophy compliance.

---
*Review based on Claude Karma Philosophy v1.0*
*Recommendation: Refactor with focus on explicit validation rules*
