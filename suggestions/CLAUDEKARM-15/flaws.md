# Claude Karma Philosophy Review: `cypher-optimizer.yaml`

**File:** `claude-flow-agents/cypher-optimizer.yaml`
**Review Date:** 2026-01-07
**Status:** FAIL (7/7 criteria failed)

---

## Summary

| Criterion | Status | Severity |
|-----------|--------|----------|
| One Agent, One Job | **FAIL** | HIGH |
| Name = Function (`action-target` format) | **FAIL** | MEDIUM |
| Maximum 3 Primary Tools | **FAIL** | CRITICAL |
| Prompt Under 500 Tokens | **FAIL** | CRITICAL |
| Input/Output Contracts Specified | **FAIL** | HIGH |
| Error States Documented | **FAIL** | MEDIUM |
| Fallback Behavior Defined | **FAIL** | MEDIUM |

---

## Detailed Findings

### 1. One Agent, One Job (FAIL - HIGH)

**Lines:** 5-9

The agent lists 5 distinct capabilities:
```yaml
capabilities:
  - Design efficient Cypher query patterns
  - Optimize for sub-3-hop traversals
  - Create index recommendations
  - Define query templates for common operations
  - Analyze query performance characteristics
```

**Recommended Fix:** Split into focused agents:
- `design-cypher-queries` - Design efficient query patterns
- `recommend-indexes` - Create index recommendations
- `analyze-query-performance` - Analyze performance characteristics

### 2. Name = Function (FAIL - MEDIUM)

**Line:** 1

Name `cypher-optimizer` uses `target-action` format instead of `action-target`.

**Recommended Fix:** Use `optimize-cypher-queries` or `design-cypher-patterns`

### 3. Maximum 3 Primary Tools (FAIL - CRITICAL)

No `tools` section defined in the YAML file.

**Recommended Fix:** Add tools section with max 3 primary tools.

### 4. Prompt Under 500 Tokens (FAIL - CRITICAL)

No `prompt` section exists - only `role` field and `capabilities` list.

**Recommended Fix:** Add proper `prompt` section following the template.

### 5. Input/Output Contracts (FAIL - HIGH)

No input/output contracts defined. Only `memory_keys` present.

**Recommended Fix:** Add explicit input/output contract definitions.

### 6. Error States Documented (FAIL - MEDIUM)

No error handling or error states documented.

**Recommended Fix:** Add `errors` section with defined conditions.

### 7. Fallback Behavior Defined (FAIL - MEDIUM)

No fallback behavior defined.

**Recommended Fix:** Add `fallback` section for degraded operation.

---

## Recommended Refactored Structure

```yaml
name: optimize-cypher-queries
description: "Optimizes Cypher query patterns for sub-3-hop traversal performance"
type: optimizer
model: sonnet

prompt: |
  ## Role
  Cypher query optimization specialist for graph database operations.

  ## Objective
  Transform input Cypher queries into optimized patterns with <3 hops.

  ## Process
  1. Analyze query structure and identify traversal patterns
  2. Apply optimization rules for hop reduction
  3. Output optimized query with performance notes

  ## Constraints
  - Only optimize queries, do not create new ones
  - Maximum 3-hop traversal in output
  - Preserve query semantics exactly

  ## Output
  JSON with: optimized_query, hop_count, optimization_applied

tools:
  primary:
    - mcp__coderoots__coderoots_query
    - Read
  support:
    - Grep

input:
  required:
    - cypher_query: string
    - schema_context: object

output:
  optimized_query: string
  hop_count: integer
  optimizations: array
  warnings: array

errors:
  invalid_syntax: "Return parse error with location"
  cannot_optimize: "Return original with explanation"

fallback:
  default: "Return original query with optimization suggestions"
```

---

## Conclusion

The `cypher-optimizer.yaml` agent appears to be a stub/early draft missing core structural elements. A complete rewrite following the recommended template is necessary.
