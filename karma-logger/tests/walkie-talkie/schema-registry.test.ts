/**
 * Schema Registry unit tests
 * Phase 5: Metadata schema validation for agent types
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  SchemaRegistry,
  schemaRegistry,
  validateMetadata,
  TASK_AGENT_SCHEMA,
  EXPLORE_AGENT_SCHEMA,
} from '../../src/walkie-talkie/schema-registry.js';
import type { MetadataSchema, ValidationMode } from '../../src/walkie-talkie/types.js';

describe('SchemaRegistry', () => {
  let registry: SchemaRegistry;

  beforeEach(() => {
    registry = new SchemaRegistry();
  });

  // ============================================
  // Built-in Schemas
  // ============================================

  describe('built-in schemas', () => {
    it('has task agent schema registered by default', () => {
      const schema = registry.getSchema('task');
      expect(schema).toBeDefined();
      expect(schema?.agentType).toBe('task');
      expect(schema?.required).toContain('taskId');
    });

    it('has explore agent schema registered by default', () => {
      const schema = registry.getSchema('explore');
      expect(schema).toBeDefined();
      expect(schema?.agentType).toBe('explore');
      expect(schema?.required).toContain('goal');
    });

    it('task schema defines expected properties', () => {
      const schema = registry.getSchema('task');
      expect(schema?.properties).toBeDefined();
      expect(schema?.properties?.taskId?.type).toBe('string');
      expect(schema?.properties?.projectId?.type).toBe('string');
      expect(schema?.properties?.priority?.type).toBe('string');
      expect(schema?.properties?.estimatedMinutes?.type).toBe('number');
      expect(schema?.properties?.labels?.type).toBe('array');
    });

    it('explore schema defines expected properties', () => {
      const schema = registry.getSchema('explore');
      expect(schema?.properties).toBeDefined();
      expect(schema?.properties?.goal?.type).toBe('string');
      expect(schema?.properties?.scope?.type).toBe('string');
      expect(schema?.properties?.depth?.type).toBe('number');
      expect(schema?.properties?.patterns?.type).toBe('array');
      expect(schema?.properties?.findings?.type).toBe('object');
    });
  });

  // ============================================
  // Schema Registration
  // ============================================

  describe('schema registration', () => {
    it('registers custom schema', () => {
      const customSchema: MetadataSchema = {
        agentType: 'custom',
        required: ['customField'],
        properties: {
          customField: { type: 'string', description: 'A custom field' },
        },
      };

      registry.register(customSchema);

      const retrieved = registry.getSchema('custom');
      expect(retrieved).toEqual(customSchema);
    });

    it('overwrites existing schema with same agentType', () => {
      const original: MetadataSchema = {
        agentType: 'test',
        required: ['field1'],
      };
      const updated: MetadataSchema = {
        agentType: 'test',
        required: ['field2'],
      };

      registry.register(original);
      registry.register(updated);

      const schema = registry.getSchema('test');
      expect(schema?.required).toEqual(['field2']);
    });

    it('hasSchema returns true for registered types', () => {
      expect(registry.hasSchema('task')).toBe(true);
      expect(registry.hasSchema('explore')).toBe(true);
    });

    it('hasSchema returns false for unregistered types', () => {
      expect(registry.hasSchema('unknown')).toBe(false);
    });

    it('listAgentTypes returns all registered types', () => {
      const types = registry.listAgentTypes();
      expect(types).toContain('task');
      expect(types).toContain('explore');
    });

    it('clear removes all schemas', () => {
      registry.clear();
      expect(registry.listAgentTypes()).toHaveLength(0);
      expect(registry.getSchema('task')).toBeUndefined();
    });

    it('reset restores built-in schemas only', () => {
      registry.register({ agentType: 'custom', required: [] });
      registry.reset();

      expect(registry.hasSchema('task')).toBe(true);
      expect(registry.hasSchema('explore')).toBe(true);
      expect(registry.hasSchema('custom')).toBe(false);
    });
  });

  // ============================================
  // Validation: Known Agent Types
  // ============================================

  describe('validates known agent type metadata', () => {
    it('validates task metadata with all required fields', () => {
      const metadata = {
        taskId: 'task-123',
        projectId: 'project-456',
        priority: 'high',
      };

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('validates explore metadata with all required fields', () => {
      const metadata = {
        goal: 'Find all API endpoints',
        scope: 'project',
        depth: 3,
      };

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('validates task metadata with only required fields', () => {
      const metadata = { taskId: 'task-123' };

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('validates explore metadata with only required fields', () => {
      const metadata = { goal: 'Explore codebase structure' };

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });
  });

  // ============================================
  // Validation: Unknown Agent Types
  // ============================================

  describe('allows unknown agent types', () => {
    it('returns valid for unknown agent type', () => {
      const result = registry.validate('unknown-agent', { anyField: 'value' });
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('returns valid for unknown agent type with empty metadata', () => {
      const result = registry.validate('unknown-agent', {});
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('returns valid for unknown agent type with null metadata', () => {
      const result = registry.validate('unknown-agent', null);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });
  });

  // ============================================
  // Validation: Missing Required Fields
  // ============================================

  describe('warns on missing required fields', () => {
    it('returns error for task without taskId', () => {
      const metadata = { projectId: 'project-123' };

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required field: taskId');
    });

    it('returns error for explore without goal', () => {
      const metadata = { scope: 'file' };

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required field: goal');
    });

    it('returns multiple errors for multiple missing required fields', () => {
      const customSchema: MetadataSchema = {
        agentType: 'multi-required',
        required: ['field1', 'field2', 'field3'],
      };
      registry.register(customSchema);

      const result = registry.validate('multi-required', { field2: 'value' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required field: field1');
      expect(result.errors).toContain('Missing required field: field3');
      expect(result.errors).not.toContain('Missing required field: field2');
    });

    it('returns error when metadata is null for schema with required fields', () => {
      const result = registry.validate('task', null);
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('Missing required fields');
    });

    it('returns error when metadata is undefined for schema with required fields', () => {
      const result = registry.validate('task', undefined);
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('Missing required fields');
    });
  });

  // ============================================
  // Validation: Type Checking
  // ============================================

  describe('validates property types', () => {
    it('rejects wrong type for string property', () => {
      const metadata = { taskId: 123 }; // Should be string

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        "Field 'taskId' has wrong type: expected string, got number",
      );
    });

    it('rejects wrong type for number property', () => {
      const metadata = { goal: 'test', depth: 'three' }; // depth should be number

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        "Field 'depth' has wrong type: expected number, got string",
      );
    });

    it('rejects wrong type for array property', () => {
      const metadata = { taskId: 'task-1', labels: 'not-an-array' };

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        "Field 'labels' has wrong type: expected array, got string",
      );
    });

    it('rejects wrong type for object property', () => {
      const metadata = { goal: 'test', findings: 'not-an-object' };

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        "Field 'findings' has wrong type: expected object, got string",
      );
    });

    it('accepts correct types', () => {
      const metadata = {
        taskId: 'task-123',
        projectId: 'project-456',
        priority: 'high',
        estimatedMinutes: 30,
        labels: ['bug', 'urgent'],
      };

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('correctly identifies array type', () => {
      const metadata = { goal: 'test', patterns: ['*.ts', '*.js'] };

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(true);
    });

    it('correctly identifies object type', () => {
      const metadata = { goal: 'test', findings: { key: 'value' } };

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(true);
    });
  });

  // ============================================
  // Validation: Extra Fields
  // ============================================

  describe('allows extra fields', () => {
    it('allows extra fields not in schema', () => {
      const metadata = {
        taskId: 'task-123',
        extraField: 'extra-value',
        anotherExtra: 42,
      };

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('allows nested extra fields', () => {
      const metadata = {
        goal: 'test',
        customNested: {
          deeply: {
            nested: 'value',
          },
        },
      };

      const result = registry.validate('explore', metadata);
      expect(result.valid).toBe(true);
    });
  });

  // ============================================
  // Validation: Edge Cases
  // ============================================

  describe('edge cases', () => {
    it('rejects non-object metadata', () => {
      const result = registry.validate('task', 'not-an-object');
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Metadata must be an object');
    });

    it('rejects array as metadata', () => {
      const result = registry.validate('task', ['not', 'valid']);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Metadata must be an object');
    });

    it('handles undefined required field value', () => {
      const metadata = { taskId: undefined };

      const result = registry.validate('task', metadata);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required field: taskId');
    });

    it('schema without required fields validates any object', () => {
      const schema: MetadataSchema = {
        agentType: 'no-required',
        properties: {
          optional: { type: 'string' },
        },
      };
      registry.register(schema);

      const result = registry.validate('no-required', {});
      expect(result.valid).toBe(true);
    });

    it('schema without properties only checks required', () => {
      const schema: MetadataSchema = {
        agentType: 'required-only',
        required: ['name'],
      };
      registry.register(schema);

      const result = registry.validate('required-only', { name: 'test', anyOther: 123 });
      expect(result.valid).toBe(true);
    });
  });
});

// ============================================
// validateMetadata Function
// ============================================

describe('validateMetadata', () => {
  let registry: SchemaRegistry;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    registry = new SchemaRegistry();
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleWarnSpy.mockRestore();
  });

  describe('none mode', () => {
    it('returns valid without checking', () => {
      const result = validateMetadata('task', {}, 'none', registry);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('does not throw even for invalid metadata', () => {
      expect(() => {
        validateMetadata('task', 'invalid', 'none', registry);
      }).not.toThrow();
    });
  });

  describe('warn mode', () => {
    it('logs warning for invalid metadata', () => {
      const metadata = { projectId: 'proj-1' }; // Missing taskId

      const result = validateMetadata('task', metadata, 'warn', registry);

      expect(result.valid).toBe(false);
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        '[SchemaRegistry] Validation warnings for task:',
        expect.arrayContaining(['Missing required field: taskId']),
      );
    });

    it('does not throw for invalid metadata', () => {
      expect(() => {
        validateMetadata('task', {}, 'warn', registry);
      }).not.toThrow();
    });

    it('does not log for valid metadata', () => {
      validateMetadata('task', { taskId: 'task-1' }, 'warn', registry);
      expect(consoleWarnSpy).not.toHaveBeenCalled();
    });
  });

  describe('strict mode', () => {
    it('throws for missing required fields', () => {
      expect(() => {
        validateMetadata('task', {}, 'strict', registry);
      }).toThrow('Metadata validation failed: Missing required field: taskId');
    });

    it('throws for wrong type', () => {
      expect(() => {
        validateMetadata('task', { taskId: 123 }, 'strict', registry);
      }).toThrow("Metadata validation failed: Field 'taskId' has wrong type: expected string, got number");
    });

    it('does not throw for valid metadata', () => {
      expect(() => {
        validateMetadata('task', { taskId: 'task-1' }, 'strict', registry);
      }).not.toThrow();
    });

    it('throws with combined error message for multiple errors', () => {
      const schema: MetadataSchema = {
        agentType: 'multi-error',
        required: ['field1', 'field2'],
      };
      registry.register(schema);

      expect(() => {
        validateMetadata('multi-error', {}, 'strict', registry);
      }).toThrow(/Missing required field: field1.*Missing required field: field2/);
    });
  });

  describe('uses global registry by default', () => {
    it('validates against global schemaRegistry', () => {
      // schemaRegistry is the global singleton
      const result = validateMetadata('task', { taskId: 'test' }, 'warn');
      expect(result.valid).toBe(true);
    });
  });
});

// ============================================
// Built-in Schema Constants
// ============================================

describe('built-in schema constants', () => {
  it('exports TASK_AGENT_SCHEMA', () => {
    expect(TASK_AGENT_SCHEMA).toBeDefined();
    expect(TASK_AGENT_SCHEMA.agentType).toBe('task');
    expect(TASK_AGENT_SCHEMA.required).toContain('taskId');
  });

  it('exports EXPLORE_AGENT_SCHEMA', () => {
    expect(EXPLORE_AGENT_SCHEMA).toBeDefined();
    expect(EXPLORE_AGENT_SCHEMA.agentType).toBe('explore');
    expect(EXPLORE_AGENT_SCHEMA.required).toContain('goal');
  });
});

// ============================================
// Integration with AgentRadioImpl
// ============================================

describe('SchemaRegistry integration', () => {
  it('global schemaRegistry is a SchemaRegistry instance', () => {
    expect(schemaRegistry).toBeInstanceOf(SchemaRegistry);
  });

  it('global schemaRegistry has built-in schemas', () => {
    expect(schemaRegistry.hasSchema('task')).toBe(true);
    expect(schemaRegistry.hasSchema('explore')).toBe(true);
  });
});
