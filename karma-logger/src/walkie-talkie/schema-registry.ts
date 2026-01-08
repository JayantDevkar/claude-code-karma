/**
 * Schema Registry for Metadata Validation
 * Phase 5: Optional schema validation for metadata per agent-type
 */

import type { MetadataSchema, ValidationResult, ValidationMode } from './types.js';

/**
 * Built-in schema for 'task' agent type
 * Task agents work on specific work items with assignments
 */
const TASK_AGENT_SCHEMA: MetadataSchema = {
  agentType: 'task',
  required: ['taskId'],
  properties: {
    taskId: {
      type: 'string',
      description: 'Unique identifier for the task being worked on',
    },
    projectId: {
      type: 'string',
      description: 'Project the task belongs to',
    },
    priority: {
      type: 'string',
      description: 'Task priority level (urgent, high, medium, low, none)',
    },
    estimatedMinutes: {
      type: 'number',
      description: 'Estimated time to complete in minutes',
    },
    labels: {
      type: 'array',
      description: 'Labels/tags associated with the task',
    },
  },
};

/**
 * Built-in schema for 'explore' agent type
 * Explore agents investigate codebases and gather information
 */
const EXPLORE_AGENT_SCHEMA: MetadataSchema = {
  agentType: 'explore',
  required: ['goal'],
  properties: {
    goal: {
      type: 'string',
      description: 'The exploration goal or question to answer',
    },
    scope: {
      type: 'string',
      description: 'Scope of exploration (file, directory, project)',
    },
    depth: {
      type: 'number',
      description: 'How deep to explore (levels of directories/calls)',
    },
    patterns: {
      type: 'array',
      description: 'File patterns to include in exploration',
    },
    findings: {
      type: 'object',
      description: 'Accumulated findings during exploration',
    },
  },
};

/**
 * Registry for agent metadata schemas
 * Provides validation of metadata against registered schemas
 */
export class SchemaRegistry {
  private schemas: Map<string, MetadataSchema> = new Map();

  constructor() {
    // Register built-in schemas
    this.register(TASK_AGENT_SCHEMA);
    this.register(EXPLORE_AGENT_SCHEMA);
  }

  /**
   * Register a metadata schema for an agent type
   * @param schema The metadata schema to register
   */
  register(schema: MetadataSchema): void {
    this.schemas.set(schema.agentType, schema);
  }

  /**
   * Get a registered schema by agent type
   * @param agentType The agent type to look up
   * @returns The schema or undefined if not registered
   */
  getSchema(agentType: string): MetadataSchema | undefined {
    return this.schemas.get(agentType);
  }

  /**
   * Check if a schema is registered for an agent type
   * @param agentType The agent type to check
   * @returns true if schema exists
   */
  hasSchema(agentType: string): boolean {
    return this.schemas.has(agentType);
  }

  /**
   * List all registered agent types
   * @returns Array of registered agent types
   */
  listAgentTypes(): string[] {
    return Array.from(this.schemas.keys());
  }

  /**
   * Validate metadata against the schema for an agent type
   * @param agentType The agent type to validate against
   * @param metadata The metadata to validate
   * @returns Validation result with valid flag and any errors
   */
  validate(agentType: string, metadata: unknown): ValidationResult {
    const errors: string[] = [];

    // Get schema for agent type
    const schema = this.schemas.get(agentType);
    if (!schema) {
      // Unknown agent types are allowed (no schema = valid)
      return { valid: true, errors: [] };
    }

    // Ensure metadata is an object
    if (metadata === null || metadata === undefined) {
      if (schema.required && schema.required.length > 0) {
        errors.push(`Missing required fields: ${schema.required.join(', ')}`);
      }
      return { valid: errors.length === 0, errors };
    }

    if (typeof metadata !== 'object' || Array.isArray(metadata)) {
      errors.push('Metadata must be an object');
      return { valid: false, errors };
    }

    const metadataObj = metadata as Record<string, unknown>;

    // Check required fields
    if (schema.required) {
      for (const field of schema.required) {
        if (!(field in metadataObj) || metadataObj[field] === undefined) {
          errors.push(`Missing required field: ${field}`);
        }
      }
    }

    // Validate property types for fields that exist
    if (schema.properties) {
      for (const [field, spec] of Object.entries(schema.properties)) {
        if (field in metadataObj && metadataObj[field] !== undefined) {
          const value = metadataObj[field];
          const actualType = this.getValueType(value);

          if (actualType !== spec.type) {
            errors.push(
              `Field '${field}' has wrong type: expected ${spec.type}, got ${actualType}`,
            );
          }
        }
      }
    }

    // Note: Extra fields (not in schema.properties) are allowed

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Get the type of a value for validation
   */
  private getValueType(value: unknown): string {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    return typeof value;
  }

  /**
   * Clear all registered schemas (useful for testing)
   */
  clear(): void {
    this.schemas.clear();
  }

  /**
   * Reset to built-in schemas only
   */
  reset(): void {
    this.clear();
    this.register(TASK_AGENT_SCHEMA);
    this.register(EXPLORE_AGENT_SCHEMA);
  }
}

/**
 * Singleton instance of SchemaRegistry
 * Use this for global schema registration
 */
export const schemaRegistry = new SchemaRegistry();

/**
 * Validate metadata and handle result based on validation mode
 * @param agentType Agent type to validate against
 * @param metadata Metadata to validate
 * @param mode Validation mode (none, warn, strict)
 * @param registry Optional custom registry (defaults to global)
 * @returns Validation result
 * @throws Error in strict mode if validation fails
 */
export function validateMetadata(
  agentType: string,
  metadata: unknown,
  mode: ValidationMode,
  registry: SchemaRegistry = schemaRegistry,
): ValidationResult {
  // No validation in 'none' mode
  if (mode === 'none') {
    return { valid: true, errors: [] };
  }

  const result = registry.validate(agentType, metadata);

  // In strict mode, throw on validation failure
  if (mode === 'strict' && !result.valid) {
    throw new Error(`Metadata validation failed: ${result.errors.join('; ')}`);
  }

  // In warn mode, log warnings but don't throw
  if (mode === 'warn' && !result.valid) {
    console.warn(`[SchemaRegistry] Validation warnings for ${agentType}:`, result.errors);
  }

  return result;
}

// Export built-in schemas for reference
export { TASK_AGENT_SCHEMA, EXPLORE_AGENT_SCHEMA };
