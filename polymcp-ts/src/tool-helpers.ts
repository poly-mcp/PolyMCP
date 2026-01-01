/**
 * Tool Helpers - Simplified tool creation API
 * 
 * This module provides helper functions to create MCP tools more easily,
 * similar to the Python version's automatic metadata extraction.
 */

import { z } from 'zod';
import { MCPTool, MCPToolMetadata } from './types';

/**
 * Tool function with TypeScript types
 */
export type ToolFunction<TInput = any, TOutput = any> = (input: TInput) => TOutput | Promise<TOutput>;

/**
 * Tool configuration
 */
export interface ToolConfig<TInput = any, TOutput = any> {
  name: string;
  description: string;
  inputSchema: z.ZodSchema<TInput>;
  outputSchema?: z.ZodSchema<TOutput>;
  function: ToolFunction<TInput, TOutput>;
}

/**
 * Create a tool with simplified API
 * 
 * @example
 * ```typescript
 * const addTool = tool({
 *   name: 'add',
 *   description: 'Add two numbers',
 *   inputSchema: z.object({
 *     a: z.number().describe('First number'),
 *     b: z.number().describe('Second number'),
 *   }),
 *   function: async ({ a, b }) => a + b,
 * });
 * ```
 */
export function tool<TInput = any, TOutput = any>(
  config: ToolConfig<TInput, TOutput>
): MCPTool & { function: ToolFunction<TInput, TOutput> } {
  return {
    name: config.name,
    description: config.description,
    inputSchema: config.inputSchema,
    outputSchema: config.outputSchema,
    function: config.function,
  };
}

/**
 * Convert Zod schema to JSON Schema for MCP protocol
 */
export function zodToJsonSchema(schema: z.ZodSchema<any>): Record<string, any> {
  // This is a simplified implementation
  // For production, consider using zod-to-json-schema library
  
  if (schema instanceof z.ZodObject) {
    const shape = schema._def.shape();
    const properties: Record<string, any> = {};
    const required: string[] = [];
    
    for (const [key, value] of Object.entries(shape)) {
      const fieldSchema = value as z.ZodTypeAny;
      properties[key] = zodTypeToJsonSchema(fieldSchema);
      
      // Check if field is required (not optional or nullable)
      if (!(fieldSchema instanceof z.ZodOptional) && 
          !(fieldSchema instanceof z.ZodNullable) &&
          !(fieldSchema instanceof z.ZodDefault)) {
        required.push(key);
      }
    }
    
    return {
      type: 'object',
      properties,
      required: required.length > 0 ? required : undefined,
    };
  }
  
  return zodTypeToJsonSchema(schema);
}

/**
 * Convert a Zod type to JSON Schema type
 */
function zodTypeToJsonSchema(schema: z.ZodTypeAny): Record<string, any> {
  const description = schema.description;
  
  // Handle optional and nullable
  if (schema instanceof z.ZodOptional) {
    return zodTypeToJsonSchema(schema.unwrap());
  }
  
  if (schema instanceof z.ZodNullable) {
    const innerSchema = zodTypeToJsonSchema(schema.unwrap());
    return {
      ...innerSchema,
      nullable: true,
    };
  }
  
  if (schema instanceof z.ZodDefault) {
    const innerSchema = zodTypeToJsonSchema(schema._def.innerType);
    return {
      ...innerSchema,
      default: schema._def.defaultValue(),
    };
  }
  
  // Handle basic types
  if (schema instanceof z.ZodString) {
    return { type: 'string', description };
  }
  
  if (schema instanceof z.ZodNumber) {
    return { type: 'number', description };
  }
  
  if (schema instanceof z.ZodBoolean) {
    return { type: 'boolean', description };
  }
  
  if (schema instanceof z.ZodArray) {
    return {
      type: 'array',
      items: zodTypeToJsonSchema(schema.element),
      description,
    };
  }
  
  if (schema instanceof z.ZodObject) {
    const shape = schema._def.shape();
    const properties: Record<string, any> = {};
    const required: string[] = [];
    
    for (const [key, value] of Object.entries(shape)) {
      const fieldSchema = value as z.ZodTypeAny;
      properties[key] = zodTypeToJsonSchema(fieldSchema);
      
      if (!(fieldSchema instanceof z.ZodOptional) && 
          !(fieldSchema instanceof z.ZodNullable) &&
          !(fieldSchema instanceof z.ZodDefault)) {
        required.push(key);
      }
    }
    
    return {
      type: 'object',
      properties,
      required: required.length > 0 ? required : undefined,
      description,
    };
  }
  
  if (schema instanceof z.ZodEnum) {
    return {
      type: 'string',
      enum: schema._def.values,
      description,
    };
  }
  
  if (schema instanceof z.ZodLiteral) {
    return {
      type: typeof schema._def.value,
      const: schema._def.value,
      description,
    };
  }
  
  if (schema instanceof z.ZodUnion) {
    const options = schema._def.options;
    return {
      oneOf: options.map((opt: z.ZodTypeAny) => zodTypeToJsonSchema(opt)),
      description,
    };
  }
  
  // Default fallback
  return { type: 'object', description };
}

/**
 * Create tool metadata from tool definition
 */
export function createToolMetadata(tool: MCPTool): MCPToolMetadata {
  return {
    name: tool.name,
    description: tool.description,
    input_schema: tool.inputSchema instanceof z.ZodSchema
      ? zodToJsonSchema(tool.inputSchema)
      : tool.inputSchema,
    output_schema: tool.outputSchema
      ? tool.outputSchema instanceof z.ZodSchema
        ? zodToJsonSchema(tool.outputSchema)
        : tool.outputSchema
      : undefined,
  };
}

/**
 * Validate tool input using Zod schema
 */
export async function validateToolInput<T>(
  schema: z.ZodSchema<T>,
  input: unknown
): Promise<{ success: true; data: T } | { success: false; error: string }> {
  try {
    const data = await schema.parseAsync(input);
    return { success: true, data };
  } catch (error) {
    if (error instanceof z.ZodError) {
      const errorMessages = error.errors.map(err => 
        `${err.path.join('.')}: ${err.message}`
      ).join(', ');
      return { success: false, error: errorMessages };
    }
    return { success: false, error: String(error) };
  }
}

/**
 * Batch create multiple tools
 */
export function createTools(configs: ToolConfig[]): MCPTool[] {
  return configs.map(config => tool(config));
}
