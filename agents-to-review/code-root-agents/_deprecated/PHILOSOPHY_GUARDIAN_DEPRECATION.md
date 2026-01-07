# DEPRECATED: philosophy-guardian

**Deprecated:** January 7, 2026
**Reason:** Violated naming convention and lacked structure
**Work Item:** CLAUDEKARM-30

## Why Deprecated

The `philosophy-guardian` violated the very philosophy it was meant to guard:
- Role-based naming ("guardian" instead of action-target)
- Missing tool specifications
- No structured prompt
- No boundaries defined

## Replacement Agent

| Old | New | Improvement |
|-----|-----|-------------|
| philosophy-guardian | `validate-philosophy` | Action-target naming |

## Key Improvements

1. **Proper naming**: `validate-philosophy` follows {action}-{target}
2. **Explicit tools**: Read, Grep defined
3. **Structured prompt**: Clear process and output format
4. **Boundaries**: Explicit includes/excludes

---
*Deprecated as part of Claude Karma Philosophy compliance initiative*
