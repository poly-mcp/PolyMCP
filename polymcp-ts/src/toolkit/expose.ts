/**
 * MCP Tool Exposure Module
 * Production-ready framework for exposing TypeScript functions as MCP tools.
 * Supports both HTTP (Express) and in-process execution modes.
 */

import express, { Express, Request, Response } from 'express';
import { z } from 'zod';
import {
  MCPTool,
  MCPToolMetadata,
  ToolResult,
  ToolRegistryEntry,
  ServerStats,
  MCPListToolsResponse,
} from '../types';

/**
 * Convert Zod schema to JSON Schema for MCP protocol
 */
function zodToJsonSchema(schema: z.ZodSchema<any>): Record<string, any> {
  try {
    // Basic conversion - in production you'd use a library like zod-to-json-schema
    if (schema instanceof z.ZodObject) {
      const shape = (schema as any)._def.shape();
      const properties: Record<string, any> = {};
      const required: string[] = [];

      for (const [key, value] of Object.entries(shape)) {
        const zodType = value as z.ZodTypeAny;
        properties[key] = { type: getZodType(zodType) };
        
        if (!zodType.isOptional()) {
          required.push(key);
        }
      }

      return {
        type: 'object',
        properties,
        required: required.length > 0 ? required : undefined,
      };
    }

    return { type: 'object' };
  } catch (error) {
    return { type: 'object' };
  }
}

/**
 * Get JSON Schema type from Zod type
 */
function getZodType(zodType: z.ZodTypeAny): string {
  const typeName = (zodType as any)._def.typeName;
  
  switch (typeName) {
    case 'ZodString': return 'string';
    case 'ZodNumber': return 'number';
    case 'ZodBoolean': return 'boolean';
    case 'ZodArray': return 'array';
    case 'ZodObject': return 'object';
    default: return 'any';
  }
}

/**
 * Build tool registry from functions
 */
function buildToolRegistry(tools: MCPTool[]): Map<string, ToolRegistryEntry> {
  const registry = new Map<string, ToolRegistryEntry>();

  for (const tool of tools) {
    const inputSchema = tool.inputSchema instanceof z.ZodSchema 
      ? tool.inputSchema 
      : z.object(tool.inputSchema);

    const metadata: MCPToolMetadata = {
      name: tool.name,
      description: tool.description,
      input_schema: zodToJsonSchema(inputSchema),
    };

    registry.set(tool.name, {
      metadata,
      function: (tool as any).function || (() => {}),
      inputSchema,
      outputSchema: tool.outputSchema instanceof z.ZodSchema ? tool.outputSchema : undefined,
      isAsync: (tool as any).isAsync !== undefined ? (tool as any).isAsync : true,
    });
  }

  return registry;
}

/**
 * In-Process MCP Server for direct tool execution
 */
export class InProcessMCPServer {
  private toolRegistry: Map<string, ToolRegistryEntry>;
  private verbose: boolean;
  private executionCount: number = 0;
  private errorCount: number = 0;

  constructor(toolRegistry: Map<string, ToolRegistryEntry>, verbose: boolean = false) {
    this.toolRegistry = toolRegistry;
    this.verbose = verbose;
  }

  /**
   * List all available MCP tools
   */
  async listTools(): Promise<MCPListToolsResponse> {
    const tools: MCPToolMetadata[] = Array.from(this.toolRegistry.values())
      .map(entry => entry.metadata);

    if (this.verbose) {
      console.log(`[InProcessMCP] Listed ${tools.length} tools`);
    }

    return { tools };
  }

  /**
   * Invoke a specific MCP tool
   */
  async invoke(toolName: string, payload: Record<string, any> = {}): Promise<ToolResult> {
    this.executionCount++;

    const tool = this.toolRegistry.get(toolName);
    if (!tool) {
      this.errorCount++;
      const available = Array.from(this.toolRegistry.keys());
      const errorMsg = `Tool '${toolName}' not found. Available: ${available.join(', ')}`;
      
      if (this.verbose) {
        console.log(`[InProcessMCP] Error: ${errorMsg}`);
      }

      return {
        status: 'error',
        error: errorMsg,
      };
    }

    // Validate input
    try {
      const validated = tool.inputSchema.parse(payload);
      
      if (this.verbose) {
        console.log(`[InProcessMCP] Executing '${toolName}' with params:`, validated);
      }

      // Execute tool
      const result = tool.isAsync 
        ? await tool.function(validated)
        : tool.function(validated);

      if (this.verbose) {
        console.log(`[InProcessMCP] '${toolName}' executed successfully`);
      }

      // Handle different return types
      if (typeof result === 'string') {
        try {
          const parsed = JSON.parse(result);
          if (typeof parsed === 'object' && parsed.status) {
            return parsed as ToolResult;
          }
          return { status: 'success', result: parsed };
        } catch {
          return { status: 'success', result };
        }
      }

      if (typeof result === 'object' && result !== null) {
        if ('status' in result) {
          return result as ToolResult;
        }
        return { status: 'success', result };
      }

      return { status: 'success', result };

    } catch (error: any) {
      this.errorCount++;
      const errorMsg = `Tool execution failed for '${toolName}': ${error.message}`;
      
      if (this.verbose) {
        console.log(`[InProcessMCP] Execution error: ${errorMsg}`);
        console.error(error);
      }

      return {
        status: 'error',
        error: errorMsg,
        details: error instanceof z.ZodError ? error.errors : undefined,
      };
    }
  }

  /**
   * Get execution statistics
   */
  getStats(): ServerStats {
    return {
      totalExecutions: this.executionCount,
      totalErrors: this.errorCount,
      successRate: this.executionCount > 0 
        ? ((this.executionCount - this.errorCount) / this.executionCount) * 100 
        : 0,
      averageExecutionTime: 0, // TODO: Implement execution time tracking
    };
  }

  toString(): string {
    const toolCount = this.toolRegistry.size;
    const toolNames = Array.from(this.toolRegistry.keys()).slice(0, 3).join(', ');
    const more = toolCount > 3 ? ` ... (+${toolCount - 3} more)` : '';
    return `InProcessMCPServer(${toolCount} tools: ${toolNames}${more})`;
  }
}

/**
 * Expose functions as MCP tools via in-process server
 */
export function exposeToolsInprocess(
  tools: MCPTool[],
  verbose: boolean = false
): InProcessMCPServer {
  if (tools.length === 0) {
    throw new Error('At least one tool must be provided');
  }

  const toolRegistry = buildToolRegistry(tools);
  const server = new InProcessMCPServer(toolRegistry, verbose);

  if (verbose) {
    console.log(`Created in-process MCP server with ${toolRegistry.size} tools`);
  }

  return server;
}

/**
 * Expose functions as MCP tools via HTTP server (Express)
 */
export function exposeToolsHttp(
  tools: MCPTool[],
  options: {
    title?: string;
    description?: string;
    version?: string;
    verbose?: boolean;
  } = {}
): Express {
  if (tools.length === 0) {
    throw new Error('At least one tool must be provided');
  }

  const {
    title = 'MCP Tool Server',
    description = 'Express server exposing TypeScript functions as MCP tools',
    version = '1.0.0',
    verbose = false,
  } = options;

  const app = express();
  app.use(express.json());

  const toolRegistry = buildToolRegistry(tools);
  const stats = {
    totalRequests: 0,
    totalErrors: 0,
  };

  // List tools endpoint
  app.get('/mcp/list_tools', async (_req: Request, res: Response) => {
    stats.totalRequests++;

    try {
      const toolsList = Array.from(toolRegistry.values()).map(entry => entry.metadata);

      if (verbose) {
        console.log(`[HTTP MCP] Listed ${toolsList.length} tools`);
      }

      res.json({ tools: toolsList });
    } catch (error: any) {
      stats.totalErrors++;
      if (verbose) {
        console.log(`[HTTP MCP] Error listing tools: ${error.message}`);
      }
      res.status(500).json({ error: error.message });
    }
  });

  // Invoke tool endpoint - Standard MCP format (tool in body)
  app.post('/mcp/invoke', async (req: Request, res: Response) => {
    stats.totalRequests++;
    const { tool: toolName, parameters } = req.body || {};

    if (!toolName) {
      stats.totalErrors++;
      return res.status(400).json({ 
        error: 'Missing required field: tool',
        example: { tool: 'tool_name', parameters: { /* ... */ } }
      });
    }

    const tool = toolRegistry.get(toolName);
    if (!tool) {
      stats.totalErrors++;
      const available = Array.from(toolRegistry.keys());
      const errorMsg = `Tool '${toolName}' not found. Available: ${available.join(', ')}`;
      
      if (verbose) {
        console.log(`[HTTP MCP] 404: ${errorMsg}`);
      }

      return res.status(404).json({ error: errorMsg });
    }

    try {
      const validated = tool.inputSchema.parse(parameters || {});

      if (verbose) {
        console.log(`[HTTP MCP] Invoking '${toolName}' with:`, validated);
      }

      const result = await tool.function(validated);

      if (verbose) {
        console.log(`[HTTP MCP] Tool '${toolName}' completed successfully`);
      }

      // Handle different result formats
      if (typeof result === 'string') {
        try {
          const parsed = JSON.parse(result);
          return res.json({ status: 'success', result: parsed });
        } catch {
          return res.json({ status: 'success', result });
        }
      }

      if (typeof result === 'object' && result !== null) {
        if ('status' in result) {
          return res.json(result);
        }
        return res.json({ status: 'success', result });
      }

      return res.json({ status: 'success', result });

    } catch (error: any) {
      stats.totalErrors++;
      const errorMsg = error instanceof z.ZodError 
        ? 'Invalid input parameters'
        : `Tool execution failed: ${error.message}`;

      if (verbose) {
        console.log(`[HTTP MCP] Error: ${errorMsg}`);
        console.error(error);
      }

      const statusCode = error instanceof z.ZodError ? 422 : 500;
      return res.status(statusCode).json({
        error: errorMsg,
        details: error instanceof z.ZodError ? error.errors : undefined,
      });
    }
  });

  // Invoke tool endpoint - Alternative format (tool in URL)
  app.post('/mcp/invoke/:toolName', async (req: Request, res: Response) => {
    stats.totalRequests++;
    const { toolName } = req.params;
    const payload = req.body || {};

    const tool = toolRegistry.get(toolName);
    if (!tool) {
      stats.totalErrors++;
      const available = Array.from(toolRegistry.keys());
      const errorMsg = `Tool '${toolName}' not found. Available: ${available.join(', ')}`;
      
      if (verbose) {
        console.log(`[HTTP MCP] 404: ${errorMsg}`);
      }

      return res.status(404).json({ error: errorMsg });
    }

    try {
      const validated = tool.inputSchema.parse(payload);

      if (verbose) {
        console.log(`[HTTP MCP] Executing '${toolName}' with params:`, validated);
      }

      const result = tool.isAsync 
        ? await tool.function(validated)
        : tool.function(validated);

      if (verbose) {
        console.log(`[HTTP MCP] '${toolName}' executed successfully`);
      }

      // Handle different return types
      if (typeof result === 'string') {
        try {
          const parsed = JSON.parse(result);
          if (typeof parsed === 'object' && parsed.status) {
            return res.json(parsed);
          }
          return res.json({ status: 'success', result: parsed });
        } catch {
          return res.json({ status: 'success', result });
        }
      }

      if (typeof result === 'object' && result !== null) {
        if ('status' in result) {
          return res.json(result);
        }
        return res.json({ status: 'success', result });
      }

      return res.json({ status: 'success', result });

    } catch (error: any) {
      stats.totalErrors++;
      const errorMsg = error instanceof z.ZodError 
        ? 'Invalid input parameters'
        : `Tool execution failed: ${error.message}`;

      if (verbose) {
        console.log(`[HTTP MCP] Error: ${errorMsg}`);
        console.error(error);
      }

      const statusCode = error instanceof z.ZodError ? 422 : 500;
      return res.status(statusCode).json({
        error: errorMsg,
        details: error instanceof z.ZodError ? error.errors : undefined,
      });
    }
  });

  // Root endpoint
  app.get('/', (_req: Request, res: Response) => {
    res.json({
      name: title,
      description,
      version,
      endpoints: {
        list_tools: '/mcp/list_tools',
        invoke_tool: '/mcp/invoke/{tool_name}',
      },
      available_tools: Array.from(toolRegistry.keys()),
      stats: {
        total_requests: stats.totalRequests,
        total_errors: stats.totalErrors,
        error_rate: stats.totalRequests > 0 
          ? (stats.totalErrors / stats.totalRequests) * 100 
          : 0,
      },
    });
  });

  // Health check endpoint
  app.get('/health', (_req: Request, res: Response) => {
    res.json({
      status: 'healthy',
      tools_count: toolRegistry.size,
      stats,
    });
  });

  if (verbose) {
    console.log(`Created HTTP MCP server with ${toolRegistry.size} tools`);
  }

  return app;
}

/**
 * Backward compatibility - alias to HTTP version
 */
export function exposeTools(
  tools: MCPTool[],
  options?: {
    title?: string;
    description?: string;
    version?: string;
  }
): Express {
  return exposeToolsHttp(tools, options);
}