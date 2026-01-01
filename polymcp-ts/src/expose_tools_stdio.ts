/**
 * MCP Stdio Server - Production Implementation
 * Expose TypeScript functions as MCP tools via stdio (JSON-RPC 2.0).
 * 
 * This allows creating npm-publishable MCP servers like @playwright/mcp.
 * 
 * Features:
 * - Full JSON-RPC 2.0 protocol implementation
 * - MCP protocol (2024-11-05) compliance
 * - Graceful shutdown on SIGINT/SIGTERM
 * - Comprehensive error handling
 * - Request/response validation
 * - Execution statistics
 */

import { z } from 'zod';
import * as readline from 'readline';
import { MCPTool, MCPToolMetadata, ToolResult } from '../types';

/**
 * JSON-RPC 2.0 Request
 */
interface JsonRpcRequest {
  jsonrpc: '2.0';
  id?: string | number | null;
  method: string;
  params?: any;
}

/**
 * JSON-RPC 2.0 Response
 */
interface JsonRpcResponse {
  jsonrpc: '2.0';
  id: string | number | null;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

/**
 * MCP Server Capabilities
 */
interface ServerCapabilities {
  tools?: {
    listChanged?: boolean;
  };
  prompts?: {
    listChanged?: boolean;
  };
  resources?: {
    subscribe?: boolean;
    listChanged?: boolean;
  };
  logging?: {};
}

/**
 * Server Information
 */
interface ServerInfo {
  name: string;
  version: string;
}

/**
 * Initialize Request Parameters
 */
interface InitializeParams {
  protocolVersion: string;
  capabilities: any;
  clientInfo: {
    name: string;
    version: string;
  };
}

/**
 * Stdio MCP Server Options
 */
export interface StdioServerOptions {
  name?: string;
  version?: string;
  verbose?: boolean;
}

/**
 * Tool Registry Entry
 */
interface ToolRegistryEntry {
  metadata: MCPToolMetadata;
  function: (args: any) => any | Promise<any>;
  inputSchema: z.ZodSchema<any>;
  outputSchema?: z.ZodSchema<any>;
  isAsync: boolean;
}

/**
 * Production MCP server using JSON-RPC 2.0 over stdio.
 * 
 * Implements the full MCP protocol (2024-11-05) for stdio transport:
 * - initialize: Protocol handshake
 * - tools/list: List available tools
 * - tools/call: Execute a tool
 * - Proper error handling with JSON-RPC error codes
 * - Graceful shutdown on SIGINT/SIGTERM
 * 
 * Example:
 * ```typescript
 * import { tool, exposeToolsStdio } from 'polymcp';
 * import { z } from 'zod';
 * 
 * const greet = tool({
 *   name: 'greet',
 *   description: 'Greet someone by name',
 *   parameters: z.object({
 *     name: z.string()
 *   }),
 *   execute: async ({ name }) => `Hello, ${name}!`
 * });
 * 
 * const server = exposeToolsStdio([greet]);
 * server.run();
 * ```
 */
export class StdioMCPServer {
  private toolRegistry: Map<string, ToolRegistryEntry>;
  private serverInfo: ServerInfo;
  private verbose: boolean;
  private initialized: boolean = false;
  private running: boolean = false;
  private requestIdCounter: number = 0;
  private rl: readline.Interface | null = null;
  
  // Statistics
  private stats = {
    requestsReceived: 0,
    requestsSuccessful: 0,
    requestsFailed: 0,
    toolsExecuted: 0,
  };

  constructor(tools: MCPTool[], options: StdioServerOptions = {}) {
    if (!tools || tools.length === 0) {
      throw new Error('At least one tool must be provided');
    }

    this.serverInfo = {
      name: options.name || 'PolyMCP Stdio Server',
      version: options.version || '1.0.0',
    };
    
    this.verbose = options.verbose || false;
    this.toolRegistry = this.buildToolRegistry(tools);

    if (this.verbose) {
      this.log(`Initialized ${this.toolRegistry.size} tools`);
    }
  }

  /**
   * Build tool registry from MCPTool array
   */
  private buildToolRegistry(tools: MCPTool[]): Map<string, ToolRegistryEntry> {
    const registry = new Map<string, ToolRegistryEntry>();

    for (const tool of tools) {
      // Validate tool structure
      if (!tool.name) {
        throw new Error('Tool must have a name');
      }
      if (!tool.description) {
        throw new Error(`Tool '${tool.name}' must have a description`);
      }
      if (!('parameters' in tool)) {
        throw new Error(`Tool '${tool.name}' must have parameters`);
      }
      if (!('execute' in tool)) {
        throw new Error(`Tool '${tool.name}' must have execute function`);
      }

      const inputSchema = tool.parameters instanceof z.ZodSchema 
        ? tool.parameters 
        : z.object(tool.parameters as any);

      const metadata: MCPToolMetadata = {
        name: tool.name,
        description: tool.description,
        input_schema: this.zodToJsonSchema(inputSchema),
      };

      registry.set(tool.name, {
        metadata,
        function: tool.execute,
        inputSchema,
        outputSchema: (tool as any).outputSchema,
        isAsync: true, // Assume async by default
      });
    }

    return registry;
  }

  /**
   * Convert Zod schema to JSON Schema
   */
  private zodToJsonSchema(schema: z.ZodSchema<any>): Record<string, any> {
    if (schema instanceof z.ZodObject) {
      const shape = (schema as any)._def.shape();
      const properties: Record<string, any> = {};
      const required: string[] = [];

      for (const [key, value] of Object.entries(shape)) {
        const zodType = value as z.ZodTypeAny;
        const typeInfo = this.getZodTypeInfo(zodType);
        
        properties[key] = typeInfo.schema;
        
        if (!zodType.isOptional()) {
          required.push(key);
        }
      }

      return {
        type: 'object',
        properties,
        ...(required.length > 0 ? { required } : {}),
      };
    }

    return { type: 'object' };
  }

  /**
   * Get JSON Schema type info from Zod type
   */
  private getZodTypeInfo(zodType: z.ZodTypeAny): { schema: any } {
    const typeName = (zodType as any)._def.typeName;
    
    // Extract description if present
    const description = (zodType as any)._def.description;
    
    let schema: any = {};
    
    switch (typeName) {
      case 'ZodString':
        schema = { type: 'string' };
        break;
      case 'ZodNumber':
        schema = { type: 'number' };
        break;
      case 'ZodBoolean':
        schema = { type: 'boolean' };
        break;
      case 'ZodArray':
        const itemType = (zodType as any)._def.type;
        schema = {
          type: 'array',
          items: this.getZodTypeInfo(itemType).schema,
        };
        break;
      case 'ZodObject':
        schema = this.zodToJsonSchema(zodType);
        break;
      case 'ZodOptional':
        const innerType = (zodType as any)._def.innerType;
        schema = this.getZodTypeInfo(innerType).schema;
        break;
      case 'ZodEnum':
        const values = (zodType as any)._def.values;
        schema = {
          type: 'string',
          enum: values,
        };
        break;
      default:
        schema = { type: 'string' };
    }
    
    if (description) {
      schema.description = description;
    }
    
    return { schema };
  }

  /**
   * Log to stderr (stdout is reserved for JSON-RPC)
   */
  private log(message: string): void {
    if (this.verbose) {
      const timestamp = new Date().toISOString();
      process.stderr.write(`[${timestamp}] ${message}\n`);
    }
  }

  /**
   * Send JSON-RPC response to stdout
   */
  private sendResponse(response: JsonRpcResponse): void {
    const json = JSON.stringify(response);
    process.stdout.write(json + '\n');
    
    if (this.verbose) {
      this.log(`Sent: ${json.substring(0, 100)}...`);
    }
  }

  /**
   * Create JSON-RPC success response
   */
  private successResponse(id: string | number | null, result: any): JsonRpcResponse {
    return {
      jsonrpc: '2.0',
      id,
      result,
    };
  }

  /**
   * Create JSON-RPC error response
   */
  private errorResponse(
    id: string | number | null,
    code: number,
    message: string,
    data?: any
  ): JsonRpcResponse {
    return {
      jsonrpc: '2.0',
      id,
      error: {
        code,
        message,
        ...(data ? { data } : {}),
      },
    };
  }

  /**
   * Handle initialize request
   */
  private async handleInitialize(
    id: string | number | null,
    params: InitializeParams
  ): Promise<JsonRpcResponse> {
    if (this.initialized) {
      return this.errorResponse(
        id,
        -32600,
        'Server already initialized'
      );
    }

    // Validate protocol version
    if (params.protocolVersion !== '2024-11-05') {
      this.log(`Warning: Client using protocol version ${params.protocolVersion}, server supports 2024-11-05`);
    }

    this.initialized = true;
    this.log(`Initialized by client: ${params.clientInfo.name} ${params.clientInfo.version}`);

    const capabilities: ServerCapabilities = {
      tools: {},
    };

    return this.successResponse(id, {
      protocolVersion: '2024-11-05',
      capabilities,
      serverInfo: this.serverInfo,
    });
  }

  /**
   * Handle tools/list request
   */
  private async handleListTools(id: string | number | null): Promise<JsonRpcResponse> {
    if (!this.initialized) {
      return this.errorResponse(
        id,
        -32002,
        'Server not initialized. Call initialize first.'
      );
    }

    const tools = Array.from(this.toolRegistry.values()).map(entry => entry.metadata);
    
    this.log(`Listed ${tools.length} tools`);

    return this.successResponse(id, { tools });
  }

  /**
   * Handle tools/call request
   */
  private async handleCallTool(
    id: string | number | null,
    params: { name: string; arguments?: any }
  ): Promise<JsonRpcResponse> {
    if (!this.initialized) {
      return this.errorResponse(
        id,
        -32002,
        'Server not initialized. Call initialize first.'
      );
    }

    const { name, arguments: args = {} } = params;

    if (!name) {
      return this.errorResponse(
        id,
        -32602,
        'Invalid params: missing tool name'
      );
    }

    const tool = this.toolRegistry.get(name);
    if (!tool) {
      const available = Array.from(this.toolRegistry.keys());
      return this.errorResponse(
        id,
        -32601,
        `Tool '${name}' not found`,
        { available }
      );
    }

    try {
      // Validate input
      const validated = tool.inputSchema.parse(args);
      
      this.log(`Executing tool '${name}' with args: ${JSON.stringify(validated)}`);
      
      // Execute tool
      const result = await tool.function(validated);
      
      this.stats.toolsExecuted++;
      this.log(`Tool '${name}' executed successfully`);

      // Format result for MCP
      let content: any;
      
      if (typeof result === 'string') {
        content = [{ type: 'text', text: result }];
      } else if (typeof result === 'object' && result !== null) {
        if ('content' in result) {
          content = result.content;
        } else if ('text' in result) {
          content = [{ type: 'text', text: result.text }];
        } else {
          content = [{ type: 'text', text: JSON.stringify(result, null, 2) }];
        }
      } else {
        content = [{ type: 'text', text: String(result) }];
      }

      return this.successResponse(id, {
        content,
        isError: false,
      });

    } catch (error: any) {
      this.log(`Tool execution error: ${error.message}`);
      
      if (error instanceof z.ZodError) {
        return this.errorResponse(
          id,
          -32602,
          'Invalid tool arguments',
          { errors: error.errors }
        );
      }

      return this.errorResponse(
        id,
        -32603,
        `Tool execution failed: ${error.message}`,
        { stack: error.stack }
      );
    }
  }

  /**
   * Handle incoming JSON-RPC request
   */
  private async handleRequest(request: JsonRpcRequest): Promise<void> {
    this.stats.requestsReceived++;

    // Validate JSON-RPC version
    if (request.jsonrpc !== '2.0') {
      const response = this.errorResponse(
        request.id || null,
        -32600,
        'Invalid Request: jsonrpc must be "2.0"'
      );
      this.sendResponse(response);
      this.stats.requestsFailed++;
      return;
    }

    let response: JsonRpcResponse;

    try {
      switch (request.method) {
        case 'initialize':
          response = await this.handleInitialize(
            request.id || null,
            request.params as InitializeParams
          );
          break;

        case 'tools/list':
          response = await this.handleListTools(request.id || null);
          break;

        case 'tools/call':
          response = await this.handleCallTool(
            request.id || null,
            request.params as any
          );
          break;

        case 'ping':
          // Optional: health check
          response = this.successResponse(request.id || null, {});
          break;

        default:
          response = this.errorResponse(
            request.id || null,
            -32601,
            `Method not found: ${request.method}`
          );
      }

      this.sendResponse(response);
      
      if (!response.error) {
        this.stats.requestsSuccessful++;
      } else {
        this.stats.requestsFailed++;
      }

    } catch (error: any) {
      this.log(`Request handling error: ${error.message}`);
      
      response = this.errorResponse(
        request.id || null,
        -32603,
        'Internal error',
        { message: error.message }
      );
      
      this.sendResponse(response);
      this.stats.requestsFailed++;
    }
  }

  /**
   * Run the stdio server
   * Reads JSON-RPC requests from stdin, sends responses to stdout
   */
  public run(): void {
    if (this.running) {
      throw new Error('Server is already running');
    }

    this.running = true;
    this.log(`${this.serverInfo.name} v${this.serverInfo.version} starting...`);
    this.log(`Tools available: ${this.toolRegistry.size}`);

    // Create readline interface
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: false,
    });

    // Handle each line as a JSON-RPC request
    this.rl.on('line', async (line: string) => {
      if (!line.trim()) {
        return;
      }

      try {
        const request = JSON.parse(line) as JsonRpcRequest;
        this.log(`Received: ${request.method} (id: ${request.id})`);
        await this.handleRequest(request);
      } catch (error: any) {
        this.log(`Failed to parse request: ${error.message}`);
        
        const response = this.errorResponse(
          null,
          -32700,
          'Parse error',
          { message: error.message }
        );
        
        this.sendResponse(response);
        this.stats.requestsFailed++;
      }
    });

    // Handle graceful shutdown
    const shutdown = async () => {
      this.log('Shutting down gracefully...');
      this.running = false;
      
      if (this.rl) {
        this.rl.close();
      }
      
      this.log('Statistics:');
      this.log(`  Requests received: ${this.stats.requestsReceived}`);
      this.log(`  Requests successful: ${this.stats.requestsSuccessful}`);
      this.log(`  Requests failed: ${this.stats.requestsFailed}`);
      this.log(`  Tools executed: ${this.stats.toolsExecuted}`);
      
      process.exit(0);
    };

    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);

    this.log('Server ready, listening on stdin...');
  }

  /**
   * Get server statistics
   */
  public getStats() {
    return { ...this.stats };
  }
}

/**
 * Expose functions as MCP tools via stdio server
 * 
 * @param tools Array of MCP tools to expose
 * @param options Server configuration options
 * @returns StdioMCPServer instance
 * 
 * @example
 * ```typescript
 * import { tool, exposeToolsStdio } from 'polymcp';
 * import { z } from 'zod';
 * 
 * const greet = tool({
 *   name: 'greet',
 *   description: 'Greet someone',
 *   parameters: z.object({
 *     name: z.string()
 *   }),
 *   execute: async ({ name }) => `Hello, ${name}!`
 * });
 * 
 * const server = exposeToolsStdio([greet], {
 *   name: 'My MCP Server',
 *   version: '1.0.0',
 *   verbose: true
 * });
 * 
 * server.run();
 * ```
 */
export function exposeToolsStdio(
  tools: MCPTool[],
  options?: StdioServerOptions
): StdioMCPServer {
  return new StdioMCPServer(tools, options);
}
