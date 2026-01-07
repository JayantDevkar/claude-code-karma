# DEPRECATED: migration-specialist

**Deprecated:** January 7, 2026
**Reason:** Violated Claude Karma philosophy principles
**Work Item:** CLAUDEKARM-32

## Why Deprecated

The `migration-specialist` agent was the **worst violation** of Claude Karma philosophy:

- **248 lines** (5x recommended maximum of ~50 lines)
- **7 distinct responsibilities** (violates Single Responsibility)
- **180+ lines of embedded templates** (context bloat)
- **5000+ tokens** consumed per invocation
- Role-based naming (`specialist` instead of `action-target`)

## Replacement Agents

The functionality has been decomposed into focused agents following SOLID principles:

| Old Capability | New Agent | Lines | Tokens |
|----------------|-----------|-------|--------|
| Breaking change detection | `detect-breaking-changes` | ~45 | ~400 |
| Migration guide creation | `generate-migration-guide` | ~40 | ~350 |
| Upgrade script generation | `create-upgrade-script` | ~40 | ~350 |
| Rollback script generation | `create-rollback-script` | ~40 | ~350 |
| Schema diff analysis | `analyze-schema-diff` | ~45 | ~400 |
| Compatibility matrices | `create-compatibility-matrix` | ~35 | ~300 |

## Templates Extracted

Templates moved to external files:
- `config/migration/templates/migration_guide.md`
- `config/migration/templates/upgrade_script.py`
- `config/migration/templates/rollback_script.py`

Configuration moved to:
- `config/migration/rules/breaking_changes.yaml`
- `config/migration/rules/schema_analysis.yaml`

## Migration Path

If you were using `migration-specialist`, use this workflow instead:

```bash
# 1. Analyze schema differences
claude-flow run analyze-schema-diff

# 2. Detect breaking changes
claude-flow run detect-breaking-changes

# 3. Generate migration guide
claude-flow run generate-migration-guide

# 4. Create upgrade script
claude-flow run create-upgrade-script

# 5. Create rollback script
claude-flow run create-rollback-script

# 6. (Optional) Create compatibility matrix
claude-flow run create-compatibility-matrix
```

## Token Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total lines | 248 | ~245 (6 agents) | Same |
| Tokens per op | 5000+ | ~400 | **90% reduction** |
| Responsibilities | 7 | 1 each | **SOLID compliant** |
| Testability | Low | High | **Isolated testing** |

---
*Deprecated as part of Claude Karma Philosophy compliance initiative*
