/**
 * Tools API - TypeScript Wrapper for MCP Tools
 * Provides clean interface for LLM-generated code to call MCP tools.
 */

import axios from 'axios';
import { MCPToolMetadata } from '../types';

/**
 * Tools API for code-based tool execution
 */
export class ToolsAPI {
  private httpTools: Map<string, MCPToolMetadata[]>;
  private httpExecutor: (serverUrl: string, toolName: string, parameters: Record<string, any>) => Promise<any>;
  private stdioExecutor: (serverId: string, toolName: string, parameters: Record<string, any>) => Promise<any>;
  private verbose: boolean;
  private toolRegistry: Map<string, { server: string; tool: MCPToolMetadata; type: 'http' | 'stdio' }>;

  constructor(options: {
    httpTools: Map<string, MCPToolMetadata[]>;
    stdioAdapters: Map<string, any>;
    httpExecutor: (serverUrl: string, toolName: string, parameters: Record<string, any>) => Promise<any>;
    stdioExecutor: (serverId: string, toolName: string, parameters: Record<string, any>) => Promise<any>;
    verbose?: boolean;
  }) {
    this.httpTools = options.httpTools;
    // Note: stdioAdapters is passed but not stored since it's not used in current implementation
    this.httpExecutor = options.httpExecutor;
    this.stdioExecutor = options.stdioExecutor;
    this.verbose = options.verbose || false;

    this.toolRegistry = new Map();
    this.buildRegistry();
    this.createToolMethods();
  }

  /**
   * Build internal registry of all available tools
   */
  private buildRegistry(): void {
    // Register HTTP tools
    for (const [serverUrl, tools] of this.httpTools.entries()) {
      for (const tool of tools) {
        this.toolRegistry.set(tool.name, {
          server: serverUrl,
          tool,
          type: 'http',
        });
      }
    }

    if (this.verbose) {
      console.log(`[ToolsAPI] Registered ${this.toolRegistry.size} tools`);
    }
  }

  /**
   * Dynamically create methods for each tool
   */
  private createToolMethods(): void {
    for (const toolName of this.toolRegistry.keys()) {
      // Create method on the instance
      (this as any)[toolName] = async (params: Record<string, any> = {}) => {
        return await this.callTool(toolName, params);
      };
    }
  }

  /**
   * Call a tool by name with parameters
   */
  private async callTool(toolName: string, parameters: Record<string, any>): Promise<string> {
    const entry = this.toolRegistry.get(toolName);
    
    if (!entry) {
      const available = Array.from(this.toolRegistry.keys()).join(', ');
      throw new Error(
        `Tool '${toolName}' not found. Available tools: ${available}`
      );
    }

    if (this.verbose) {
      console.log(`[ToolsAPI] Calling tool: ${toolName}`, parameters);
    }

    try {
      let result: any;

      if (entry.type === 'http') {
        result = await this.httpExecutor(entry.server, toolName, parameters);
      } else {
        result = await this.stdioExecutor(entry.server, toolName, parameters);
      }

      // Always return JSON string for consistency with Python version
      if (typeof result === 'string') {
        // Verify it's valid JSON
        JSON.parse(result);
        return result;
      } else {
        return JSON.stringify(result);
      }
    } catch (error: any) {
      const errorResult = {
        status: 'error',
        error: error.message,
        tool: toolName,
      };
      return JSON.stringify(errorResult);
    }
  }

  /**
   * List all available tool names
   */
  listTools(): string[] {
    return Array.from(this.toolRegistry.keys()).sort();
  }

  /**
   * Get information about a specific tool
   */
  getToolInfo(toolName: string): MCPToolMetadata | null {
    const entry = this.toolRegistry.get(toolName);
    return entry ? entry.tool : null;
  }

  /**
   * String representation
   */
  toString(): string {
    const toolCount = this.toolRegistry.size;
    const toolNames = Array.from(this.toolRegistry.keys()).slice(0, 5).join(', ');
    const more = toolCount > 5 ? ` ... (+${toolCount - 5} more)` : '';
    return `ToolsAPI(${toolCount} tools: ${toolNames}${more})`;
  }
}

/**
 * Default HTTP executor for ToolsAPI
 */
export async function defaultHttpExecutor(
  serverUrl: string,
  toolName: string,
  parameters: Record<string, any>
): Promise<any> {
  try {
    const invokeUrl = `${serverUrl}/invoke/${toolName}`;
    const response = await axios.post(invokeUrl, parameters, {
      timeout: 30000,
    });
    return response.data;
  } catch (error: any) {
    throw new Error(`HTTP tool execution failed: ${error.message}`);
  }
}

/**
 * Default stdio executor for ToolsAPI
 */
export async function defaultStdioExecutor(
  serverId: string,
  toolName: string,
  parameters: Record<string, any>,
  adapters: Map<string, any>
): Promise<any> {
  const adapter = adapters.get(serverId);
  if (!adapter) {
    throw new Error(`Stdio adapter not found for ${serverId}`);
  }

  return await adapter.invokeTool(toolName, parameters);
}