# Claude Karma Philosophy Review: `doc-maintainer.yaml`

**File:** `claude-flow-agents/doc-maintainer.yaml`
**Review Date:** 2026-01-07
**Status:** FAIL (3/7 criteria passed)

---

## Summary

| Criterion | Status | Severity |
|-----------|--------|----------|
| Single, clear responsibility | **FAIL** | HIGH |
| Name follows `action-target` format | **FAIL** | MEDIUM |
| Maximum 3 primary tools | **PASS** | - |
| Prompt under 500 tokens | **PASS** | LOW |
| Input/output contracts specified | **PARTIAL** | MEDIUM |
| Error states documented | **FAIL** | HIGH |
| Fallback behavior defined | **FAIL** | HIGH |

---

## Detailed Findings

### 1. Single, Clear Responsibility (FAIL - HIGH)

**Lines:** 4-11, 86-93

Agent has 14+ distinct capabilities across 2 phases - classic Swiss Army knife:

**Phase 3 capabilities:**
- Update README.md with new features
- Modify schema documentation
- Update MCP_SERVER_README.md with new operations
- Create migration guides
- Update FILES_INDEX.md
- Maintain CHANGELOG.md
- Ensure documentation consistency with implementation

**Phase 4 capabilities:**
- Generate final documentation package
- Update all cross-references
- Create feature announcement
- Update changelog with release notes
- Ensure all examples work
- Verify all links are valid
- Generate PR description

**Recommended Fix:** Split into focused agents:
- `update-readme` - Updates README files only
- `maintain-changelog` - Maintains CHANGELOG.md only
- `create-migration-guide` - Creates migration documentation
- `generate-pr-description` - Generates PR descriptions
- `validate-docs` - Validates links and examples

### 2. Name Follows `action-target` Format (FAIL - MEDIUM)

**Line:** 1

Name `doc-maintainer` uses `target-role` format. "maintainer" is a role/noun, not an action/verb.

**Recommended Fix:** Rename to `update-documentation` or split into properly named agents.

### 3. Maximum 3 Primary Tools (PASS)

No explicit `tools` section defined. Technically passes but indicates incomplete agent.

### 4. Prompt Under 500 Tokens (PASS - with caveat)

No explicit `prompt` field exists. Role description only 5 words. While passing, absence of structured prompt is a design concern.

### 5. Input/Output Contracts (PARTIAL - MEDIUM)

**Lines:** 67-72, 19-34

**Positive:**
- `work_package_schema` defines expected input structure
- `memory_keys` documents data flow with read/write annotations

**Missing:**
- No explicit output contract
- No data types for outputs
- Templates exist but no validation schema

### 6. Error States Documented (FAIL - HIGH)

No error handling documentation in the entire 201-line file.

**Critical Problem (line 49):**
```yaml
validation:
  - markdownlint docs/*.md || true
```

The `|| true` pattern silently swallows errors, directly violating "Fail Fast & Clear."

**Missing:**
- No `error_handling` section
- No documentation of file missing scenarios
- No schema version mismatch handling
- No markdown linting failure handling

### 7. Fallback Behavior Defined (FAIL - HIGH)

No fallback behavior defined anywhere.

**Missing:**
- No `fallback` section
- No degraded mode specification
- No retry logic documentation
- No escalation path

---

## Additional Issues

### Template Bloat (MEDIUM)
**Lines:** 123-200

Templates section (78 lines) is 39% of the file. Should be externalized.

### Phase Overloading (HIGH)
**Lines:** 36-49, 77-119

Two distinct phases with different dependencies and capabilities - code smell indicating agent should be split.

---

## Recommended Refactored Structure

```yaml
name: update-readme
description: "Updates README.md with feature documentation"
model: sonnet

prompt: |
  ## Role
  README documentation updater.

  ## Objective
  Update README.md with new feature information.

  ## Process
  1. Read feature specification
  2. Locate appropriate section
  3. Add documentation following existing patterns
  4. Validate markdown syntax

  ## Constraints
  - Only update README.md
  - Follow existing documentation style
  - Ensure links are valid

  ## Output
  Updated README.md content

tools:
  primary:
    - Read
    - Edit
  support:
    - Grep

error_handling:
  file_not_found: "Create with template or fail with clear message"
  validation_failed: "Report specific lint errors, do not proceed"

fallback:
  on_validation_fail: report_and_halt
  max_retries: 3
```

---

## Conclusion

The `doc-maintainer.yaml` agent fails philosophy review due to:

1. **Swiss Army Knife Design** - 14+ capabilities across 2 phases
2. **Role-Based Naming** - Uses `target-role` pattern instead of `action-target`
3. **Missing Error Documentation** - No error states, `|| true` pattern hides failures
4. **No Fallback Behavior** - No resilience mechanisms

Requires refactoring into smaller, focused agents with proper naming, explicit error handling, and defined fallback behaviors.

---
*Review based on Claude Karma Philosophy v1.0*
