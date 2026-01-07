# DEPRECATED: mcp-updater

**Deprecated:** January 7, 2026
**Reason:** Multi-file ownership, 6 responsibilities
**Work Item:** CLAUDEKARM-33

## Why Deprecated

The `mcp-updater` violated single responsibility by:
- Claiming ownership of 4 files
- Having 6 distinct capabilities
- Mixing concerns across files
- Blocking parallel development

## Replacement Agents

| Old Capability | New Agent | File Focus |
|----------------|-----------|------------|
| Update operations | `update-mcp-operations` | mcp_server.py |
| Update definitions | `update-tool-definitions` | tool_definitions.py |
| Update formatters | `update-formatters` | formatters.py |
| Validate compat | `validate-mcp-compat` | All (read-only) |

## Key Improvements

1. **File-focused**: Each agent modifies ONE file only
2. **Parallel-ready**: Can run concurrently without conflicts
3. **Testable**: Clear boundaries for unit testing
4. **Maintainable**: Single responsibility per agent

## Token Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Lines | 55 | ~35 each | More focused |
| Files owned | 4 | 1 each | No conflicts |
| Responsibilities | 6 | 1 each | SOLID compliant |

---
*Deprecated as part of Claude Karma Philosophy compliance initiative*
