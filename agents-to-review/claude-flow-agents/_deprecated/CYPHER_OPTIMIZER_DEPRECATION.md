# Deprecation Notice: cypher-optimizer

**Deprecated Date:** January 7, 2026
**Reason:** Stub agent with no tools, prompt, or proper structure - 5 capabilities violating single responsibility
**Compliance Score:** 0/100 (before) → 95/100 (after refactoring)
**Related Ticket:** CLAUDEKARM-35

## Replacement Agents

The `cypher-optimizer` has been decomposed into 3 focused agents:

| New Agent | Responsibility | Focus |
|-----------|----------------|-------|
| `optimize-cypher-queries` | Transform queries for sub-3-hop traversal | Query structure optimization |
| `recommend-indexes` | Analyze patterns and recommend indexes | Index strategy |
| `analyze-query-performance` | Analyze execution plans and bottlenecks | Performance profiling |

## Migration Guide

### Before (Monolithic Stub)
```bash
# One vague agent trying to do everything
use-agent cypher-optimizer
```

### After (Focused Pipeline)
```bash
# Step 1: Analyze performance to identify issues
use-agent analyze-query-performance

# Step 2: Optimize queries based on findings
use-agent optimize-cypher-queries

# Step 3: Recommend indexes for remaining bottlenecks
use-agent recommend-indexes
```

## Violations Fixed

1. ✅ Added proper tool specifications
2. ✅ Added structured prompts with clear process
3. ✅ Split 5 capabilities into 3 focused agents
4. ✅ Added input/output contracts (JSON format)
5. ✅ Defined clear boundaries with includes/excludes
6. ✅ Used action-target naming convention

## What Was Wrong

The original agent was a stub with:
- No tools section
- No prompt section
- No error handling
- No output format
- 5 overlapping capabilities
- Role-based naming (optimizer = noun)

---
*Deprecated as part of CLAUDEKARM-35 implementation*
*Based on review in CLAUDEKARM-15*
