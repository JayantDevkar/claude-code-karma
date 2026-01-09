# Phase 5: Metadata Schema Validation

**Status:** ✅ COMPLETED (2026-01-08)
**Priority:** Low
**Complexity:** Medium
**Estimated Files:** 4-5

## Problem Statement

From meta-testing: "Metadata is `Record<string, unknown>`. No validation of shape. Different agents might store conflicting metadata structures."

Risk of runtime errors when agents expect specific metadata shapes.

## Goal

Optional schema validation for metadata per agent-type.

## Implementation

### 1. Schema Registry

New file `src/walkie-talkie/schema-registry.ts`:

```typescript
interface MetadataSchema {
  agentType: string;
  required?: string[];
  properties?: Record<string, {
    type: 'string' | 'number' | 'boolean' | 'object' | 'array';
    description?: string;
  }>;
}

class SchemaRegistry {
  register(schema: MetadataSchema): void;
  validate(agentType: string, metadata: unknown): ValidationResult;
  getSchema(agentType: string): MetadataSchema | undefined;
}
```

### 2. Built-in Schemas

Default schemas for common agent types:

```typescript
const BUILTIN_SCHEMAS: MetadataSchema[] = [
  {
    agentType: 'task',
    properties: {
      tool: { type: 'string' },
      files_modified: { type: 'number' },
      error: { type: 'string' }
    }
  },
  {
    agentType: 'explore',
    properties: {
      search_query: { type: 'string' },
      files_found: { type: 'array' }
    }
  }
];
```

### 3. Validation Mode

Three modes for flexibility:

```typescript
type ValidationMode = 'none' | 'warn' | 'strict';

// In config or CLI
karma radio set-status active --metadata '{}' --validate strict
```

- `none`: No validation (default, backward compatible)
- `warn`: Log warning but allow
- `strict`: Reject invalid metadata

### 4. AgentRadio Integration

```typescript
setStatus(state: AgentState, options?: {
  metadata?: Record<string, unknown>;
  validateMetadata?: ValidationMode;
}): void {
  if (options?.validateMetadata !== 'none') {
    const result = this.schemaRegistry.validate(this.agentType, options.metadata);
    if (!result.valid) {
      if (options.validateMetadata === 'strict') {
        throw new Error(`Invalid metadata: ${result.errors.join(', ')}`);
      }
      console.warn(`Metadata validation warning: ${result.errors.join(', ')}`);
    }
  }
  // ... proceed with set
}
```

## Files to Create/Modify

| File | Change |
|------|--------|
| `src/walkie-talkie/schema-registry.ts` | New file |
| `src/walkie-talkie/types.ts` | Add schema types |
| `src/walkie-talkie/agent-radio.ts` | Integrate validation |
| `src/commands/radio.ts` | Add `--validate` flag |
| `src/walkie-talkie/index.ts` | Export schema registry |

## Test Cases

```typescript
describe('SchemaRegistry', () => {
  it('validates known agent type metadata');
  it('allows unknown agent types');
  it('warns on missing required fields');
  it('rejects in strict mode');
  it('allows extra fields');
});
```

## Acceptance Criteria

- [x] Schema registry can register custom schemas
- [x] Built-in schemas for common agent types
- [x] `--validate warn|strict` flag on CLI
- [x] Backward compatible (no validation by default)
- [x] Clear error messages for validation failures

## Configuration

Allow schema overrides in config:

```json
// ~/.karma/schemas.json
{
  "agentTypes": {
    "my-custom-agent": {
      "required": ["task_id"],
      "properties": {
        "task_id": { "type": "string" }
      }
    }
  }
}
```

## Dependencies

None - can be implemented independently.

## Rollback

Validation is opt-in; disable by not using `--validate`.

## Implementation Notes (2026-01-08)

### Files Created/Modified

| File | Status |
|------|--------|
| `src/walkie-talkie/schema-registry.ts` | Created |
| `src/walkie-talkie/types.ts` | Modified (added ValidationMode, MetadataSchema, etc.) |
| `src/walkie-talkie/agent-radio.ts` | Modified (integrated schema validation) |
| `src/commands/radio.ts` | Modified (added --validate flag) |
| `src/walkie-talkie/index.ts` | Modified (exported SchemaRegistry) |
| `tests/walkie-talkie/schema-registry.test.ts` | Created (51 tests) |

### Test Results

```
✓ tests/walkie-talkie/schema-registry.test.ts (51 tests) 9ms
Test Files  1 passed (1)
Tests       51 passed (51)
```

### Features Implemented

1. **SchemaRegistry class** with register/validate/getSchema methods
2. **Built-in schemas** for 'task' and 'explore' agent types
3. **Three validation modes**: none (default), warn, strict
4. **CLI integration**: `--validate <mode>` flag on set-status
5. **Type safety**: Full TypeScript types for schemas and validation results
