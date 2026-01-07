# Deprecation Notice: integration-validator

**Deprecated Date:** January 7, 2026
**Reason:** Single Responsibility Violation - 7 responsibilities, coordinator anti-pattern
**Compliance Score:** 45/100 (before) → 95/100 (after refactoring)
**Related Ticket:** CLAUDEKARM-34

## Replacement Agents

The `integration-validator` has been decomposed into 4 focused agents:

| New Agent | Responsibility | Token Reduction |
|-----------|----------------|-----------------|
| `run-integration-tests` | Execute integration test suite | ~400 tokens |
| `check-backward-compat` | Verify API backward compatibility | ~400 tokens |
| `run-regression-tests` | Execute regression test suite | ~400 tokens |
| `verify-graph-integrity` | Check graph data consistency | ~400 tokens |

## Migration Guide

### Before (Monolithic)
```bash
# One agent doing everything
use-agent integration-validator
```

### After (Focused)
```bash
# Run each test type independently (can parallelize)
use-agent run-integration-tests
use-agent check-backward-compat
use-agent run-regression-tests
use-agent verify-graph-integrity
```

## Violations Fixed

1. ✅ Removed coordinator anti-pattern
2. ✅ Split into single-responsibility agents
3. ✅ Added tool specifications
4. ✅ Removed wildcard context files
5. ✅ Added clear boundaries
6. ✅ Standardized JSON output format

## Token Impact

- **Before:** ~1500 tokens (with wildcard expansion)
- **After:** ~400 tokens per agent
- **Reduction:** 73% per operation

## Do Not Use

This deprecated agent should NOT be used. It has been moved to `_deprecated/` to preserve history only.

---
*Deprecated as part of CLAUDEKARM-34 implementation*
*Based on review in CLAUDEKARM-18*
