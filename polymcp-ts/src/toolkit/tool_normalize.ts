/**
 * Tool Normalization
 * 
 * Normalizes and validates MCP tool metadata to ensure consistency.
 * Handles missing fields, type coercion, and schema validation.
 */

import { z } from 'zod';

/**
 * Tool metadata structure
 */
export interface MCPToolMetadata {
  name: string;
  description: string;
  input_schema: Record<string, any>;
  [key: string]: any; // Allow additional fields
}

/**
 * Zod schema for tool validation
 */
const toolSchema = z.object({
  name: z.string().min(1, 'Tool name cannot be empty'),
  description: z.string().default(''),
  input_schema: z.record(z.any()).default({}),
}).passthrough(); // Allow additional fields

/**
 * Input schema validation (JSON Schema format)
 */
const inputSchemaSchema = z.object({
  type: z.enum(['object', 'array', 'string', 'number', 'boolean', 'null']).optional(),
  properties: z.record(z.any()).optional(),
  required: z.array(z.string()).optional(),
  additionalProperties: z.boolean().optional(),
}).passthrough();

/**
 * Normalize tool metadata.
 * 
 * Ensures all required fields are present with proper defaults.
 * Validates and coerces types.
 * Handles malformed or incomplete tool definitions.
 * 
 * @param tool - Raw tool metadata (possibly incomplete/malformed)
 * @returns Normalized tool metadata
 * @throws Error if tool is invalid beyond repair
 * 
 * Example:
 * ```typescript
 * const raw = { name: 'my_tool' }; // Missing fields
 * const normalized = normalizeToolMetadata(raw);
 * // {
 * //   name: 'my_tool',
 * //   description: '',
 * //   input_schema: {}
 * // }
 * ```
 */
export function normalizeToolMetadata(tool: any): MCPToolMetadata {
  if (!tool || typeof tool !== 'object') {
    throw new Error('Tool metadata must be an object');
  }

  // Validate with Zod
  try {
    const validated = toolSchema.parse(tool);

    // Additional normalization
    const normalized: MCPToolMetadata = {
      name: validated.name.trim(),
      description: validated.description || '',
      input_schema: validated.input_schema || {},
    };

    // Preserve additional fields
    for (const [key, value] of Object.entries(validated)) {
      if (!['name', 'description', 'input_schema'].includes(key)) {
        normalized[key] = value;
      }
    }

    // Normalize input_schema
    normalized.input_schema = normalizeInputSchema(normalized.input_schema);

    return normalized;
  } catch (error: any) {
    if (error instanceof z.ZodError) {
      const issues = error.errors.map(e => `${e.path.join('.')}: ${e.message}`).join(', ');
      throw new Error(`Tool validation failed: ${issues}`);
    }
    throw error;
  }
}

/**
 * Normalize input schema (JSON Schema format).
 * Ensures proper structure and defaults.
 */
function normalizeInputSchema(schema: any): Record<string, any> {
  if (!schema || typeof schema !== 'object') {
    return { type: 'object', properties: {} };
  }

  // If it's already a valid schema, validate and return
  try {
    inputSchemaSchema.parse(schema);
    return schema;
  } catch {
    // If validation fails, try to coerce to valid schema
  }

  // Ensure it has at least type: object
  if (!schema.type) {
    schema.type = 'object';
  }

  // Ensure properties exist for object types
  if (schema.type === 'object' && !schema.properties) {
    schema.properties = {};
  }

  return schema;
}

/**
 * Validate tool name.
 * Tool names must be valid identifiers.
 */
export function validateToolName(name: string): boolean {
  if (!name || typeof name !== 'string') return false;
  if (name.trim().length === 0) return false;

  // Allow alphanumeric, underscore, hyphen
  const validNameRegex = /^[a-zA-Z0-9_-]+$/;
  return validNameRegex.test(name);
}

/**
 * Validate input schema structure.
 * Checks if schema is valid JSON Schema (basic check).
 */
export function validateInputSchema(schema: any): boolean {
  if (!schema || typeof schema !== 'object') return false;

  try {
    inputSchemaSchema.parse(schema);
    return true;
  } catch {
    return false;
  }
}

/**
 * Extract parameter names from input schema.
 * Useful for understanding what parameters a tool accepts.
 */
export function extractParameterNames(tool: MCPToolMetadata): string[] {
  const schema = tool.input_schema;
  
  if (!schema || schema.type !== 'object' || !schema.properties) {
    return [];
  }

  return Object.keys(schema.properties);
}

/**
 * Extract required parameters from input schema.
 */
export function extractRequiredParameters(tool: MCPToolMetadata): string[] {
  const schema = tool.input_schema;
  
  if (!schema || schema.type !== 'object' || !schema.required) {
    return [];
  }

  return Array.isArray(schema.required) ? schema.required : [];
}

/**
 * Check if tool accepts any parameters.
 */
export function hasParameters(tool: MCPToolMetadata): boolean {
  return extractParameterNames(tool).length > 0;
}

/**
 * Check if parameter is required.
 */
export function isParameterRequired(tool: MCPToolMetadata, paramName: string): boolean {
  const required = extractRequiredParameters(tool);
  return required.includes(paramName);
}

/**
 * Get parameter schema (type, description, etc.).
 */
export function getParameterSchema(
  tool: MCPToolMetadata,
  paramName: string
): Record<string, any> | null {
  const schema = tool.input_schema;
  
  if (!schema || schema.type !== 'object' || !schema.properties) {
    return null;
  }

  return schema.properties[paramName] || null;
}

/**
 * Normalize tool list.
 * Normalizes all tools in an array, filtering out invalid ones.
 */
export function normalizeToolList(
  tools: any[],
  options: { skipInvalid?: boolean; verbose?: boolean } = {}
): MCPToolMetadata[] {
  const normalized: MCPToolMetadata[] = [];

  for (let i = 0; i < tools.length; i++) {
    try {
      const tool = normalizeToolMetadata(tools[i]);
      normalized.push(tool);
    } catch (error: any) {
      if (options.skipInvalid) {
        if (options.verbose) {
          console.warn(`Skipping invalid tool at index ${i}: ${error.message}`);
        }
        continue;
      } else {
        throw new Error(`Tool at index ${i} is invalid: ${error.message}`);
      }
    }
  }

  return normalized;
}

/**
 * Deep clone tool metadata (to avoid mutation).
 */
export function cloneToolMetadata(tool: MCPToolMetadata): MCPToolMetadata {
  return JSON.parse(JSON.stringify(tool));
}

/**
 * Compare two tools for equality.
 * Compares name, description, and input_schema.
 */
export function toolsEqual(tool1: MCPToolMetadata, tool2: MCPToolMetadata): boolean {
  return (
    tool1.name === tool2.name &&
    tool1.description === tool2.description &&
    JSON.stringify(tool1.input_schema) === JSON.stringify(tool2.input_schema)
  );
}

/**
 * Merge tool metadata (for updates).
 * Updates tool1 with non-empty fields from tool2.
 */
export function mergeToolMetadata(
  base: MCPToolMetadata,
  updates: Partial<MCPToolMetadata>
): MCPToolMetadata {
  const merged = cloneToolMetadata(base);

  if (updates.name && updates.name.trim()) {
    merged.name = updates.name.trim();
  }

  if (updates.description !== undefined) {
    merged.description = updates.description;
  }

  if (updates.input_schema && typeof updates.input_schema === 'object') {
    merged.input_schema = {
      ...merged.input_schema,
      ...updates.input_schema,
    };
  }

  // Merge other fields
  for (const [key, value] of Object.entries(updates)) {
    if (!['name', 'description', 'input_schema'].includes(key)) {
      merged[key] = value;
    }
  }

  return merged;
}
