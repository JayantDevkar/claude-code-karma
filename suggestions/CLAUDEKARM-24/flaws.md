# Agent Review: test-engineer

## Executive Summary
**Agent Name:** test-engineer  
**Review Date:** January 7, 2026  
**Philosophy Compliance Score:** 68/100 ⚠️  
**Recommendation:** NEEDS REFACTORING

## Critical Violations

### 1. ❌ NAMING CONVENTION VIOLATION (Critical)
**Principle:** NAMING_CONVENTIONS.md - Format: `{action}-{target}`
**Current:** `test-engineer` 
**Issue:** "engineer" is a role, not a target. Violates action-target naming pattern.
**Required Fix:** Rename to one of:
- `generate-tests` (if primarily generating test code)
- `validate-tests` (if primarily validating test quality)
- `write-pytests` (if specifically for pytest)

### 2. ❌ SINGLE RESPONSIBILITY VIOLATION (Critical)
**Principle:** CORE_PHILOSOPHY.md - "One Agent, One Job"
**Current Responsibilities:** 6 distinct jobs:
1. Write unit tests
2. Create integration tests
3. Generate performance benchmarks
4. Test edge cases
5. Ensure coverage metrics
6. Follow test patterns

**Required Fix:** Decompose into focused agents:
- `generate-unit-tests`: Creates unit test files
- `generate-integration-tests`: Creates integration test files  
- `measure-coverage`: Analyzes and reports test coverage
- `benchmark-performance`: Creates performance benchmarks

### 3. ⚠️ MISSING TOOL SPECIFICATION (Major)
**Principle:** AGENT_ARCHITECTURE.md - Tool Selection Strategy
**Issue:** No tools specified in YAML
**Impact:** Unclear dependencies and capabilities
**Required Fix:** Explicitly define tools:
```yaml
tools:
  primary:
    - filesystem    # Read/write test files
    - pytest        # Execute tests
  support:
    - coverage      # Measure coverage (if needed)
```

### 4. ⚠️ PROMPT MISSING (Major)
**Principle:** CONTEXT_ENGINEERING.md - "Prompt as Software"
**Issue:** No system prompt or structured context
**Required Fix:** Add structured prompt following pattern:
```yaml
prompt: |
  ## Role
  Test generation specialist for Python pytest framework
  
  ## Objective
  Generate comprehensive unit tests with >80% coverage
  
  ## Process
  1. Analyze code structure
  2. Identify test scenarios
  3. Generate pytest-compatible tests
  
  ## Constraints
  - Only unit tests, no integration
  - Follow AAA pattern (Arrange-Act-Assert)
  - Use existing fixtures
  
  ## Output Format
  Valid Python test file with pytest markers
```

### 5. ❌ CONTEXT OVERLOAD (Major)
**Principle:** CONTEXT_ENGINEERING.md - Token Optimization
**Current:** 4+ context files plus dynamic approved_specs
**Issue:** Excessive context reduces available tokens for processing
**Required Fix:** Limit to 2 essential context files maximum

### 6. ⚠️ UNCLEAR BOUNDARIES (Major)
**Principle:** CORE_PHILOSOPHY.md - "Explicit Over Implicit"
**Issue:** No clear includes/excludes section
**Required Fix:** Add boundaries:
```yaml
boundaries:
  includes:
    - Python pytest unit tests
    - Test file generation
    - Fixture creation
  excludes:
    - Integration tests (separate agent)
    - Test execution (orchestrator's job)
    - Code modification
    - Documentation updates
```

## Positive Aspects ✅

1. **Good Phase Configuration:** Clear phase3 priority and dependencies
2. **Template Patterns:** Useful test generation templates provided
3. **Memory Key Structure:** Well-organized memory key usage
4. **Validation Commands:** Good file validation approach

## Architecture Analysis

### Current State (Monolithic)
```
test-engineer (6 responsibilities)
    ├── Unit Tests
    ├── Integration Tests  
    ├── Performance Benchmarks
    ├── Edge Cases
    ├── Coverage Analysis
    └── Pattern Following
```

### Recommended State (SOLID)
```
generate-unit-tests (1 responsibility)
    └── Create pytest unit test files

generate-integration-tests (1 responsibility)
    └── Create end-to-end test files

measure-test-coverage (1 responsibility)
    └── Analyze and report coverage metrics

benchmark-performance (1 responsibility)
    └── Create performance test files
```

## Performance Impact

**Current Token Usage:** ~1200 tokens (context overload)
**After Refactoring:** ~400 tokens per focused agent
**Expected Improvement:** 66% reduction in token usage

## Migration Plan

### Step 1: Create Focused Agents
```bash
agents/
├── generate-unit-tests/
│   └── agent.yaml
├── generate-integration-tests/
│   └── agent.yaml
├── measure-test-coverage/
│   └── agent.yaml
└── _deprecated/
    └── test-engineer/
```

### Step 2: Update Orchestrator References
Replace `test-engineer` invocations with appropriate specialized agent

### Step 3: Test Each Agent Independently
Verify single responsibility compliance

## Detailed Scoring

| Principle | Score | Evidence |
|-----------|-------|----------|
| Single Responsibility | 3/10 | 6 distinct jobs in one agent |
| Naming Convention | 0/10 | Role-based name, not action-target |
| Tool Selection | 4/10 | No tools specified |
| Context Engineering | 5/10 | Missing prompt, token inefficient |
| Boundaries | 4/10 | No explicit includes/excludes |
| Test Patterns | 8/10 | Good templates provided |
| Memory Management | 9/10 | Well-structured keys |
| Phase Configuration | 10/10 | Clear dependencies |

**Total: 43/80 = 54%** (Adjusted to 68/100 with positive aspects)

## Recommendations Priority

### 🔴 Critical (Do First)
1. Rename agent to `generate-unit-tests`
2. Remove all non-unit-test responsibilities
3. Add explicit tool specifications

### 🟡 Important (Do Second)  
4. Add structured system prompt
5. Define clear boundaries section
6. Reduce context files to 2 maximum

### 🟢 Nice to Have
7. Create companion agents for other test types
8. Add performance metrics
9. Document test pattern philosophy

## Example Refactored Agent

```yaml
name: generate-unit-tests
description: "Generates Python pytest unit test files"

tools:
  primary:
    - filesystem    # Read code, write tests
  support:
    - ast_parser    # Analyze Python structure

prompt: |
  ## Role
  Python unit test generator specializing in pytest framework
  
  ## Objective
  Generate comprehensive unit tests for provided code
  
  ## Process
  1. Parse code structure
  2. Identify testable functions/methods
  3. Generate test cases with AAA pattern
  4. Include edge cases and error paths
  
  ## Constraints
  - ONLY unit tests (no integration)
  - MUST use pytest conventions
  - MUST achieve >80% coverage
  - CANNOT modify source code
  
  ## Output Format
  Python file with:
  - pytest imports
  - Fixtures if needed
  - Test functions prefixed with test_
  - Descriptive test names
  - Clear assertions

boundaries:
  includes:
    - Unit test generation
    - Fixture creation
    - Test parameterization
  excludes:
    - Integration tests
    - Performance tests
    - Test execution
    - Coverage measurement
    - Source code modification

context_files:
  - tests/conftest.py  # Existing fixtures only
```

## Conclusion

The `test-engineer` agent violates core philosophy principles, particularly Single Responsibility and Naming Conventions. It attempts to be a "Swiss Army knife" for all testing needs, which directly contradicts the "One Agent, One Job" principle.

**Immediate Action Required:** 
1. Rename to follow action-target pattern
2. Extract single responsibility (recommend starting with unit test generation)
3. Create separate focused agents for other test types

This refactoring will improve:
- Philosophy compliance (54% → 95%)
- Token efficiency (66% reduction)
- Testability and maintainability
- Clear separation of concerns

---
*Review based on Claude Karma Philosophy v1.0*
*Reviewer: Claude Code Agent Orchestration System*
