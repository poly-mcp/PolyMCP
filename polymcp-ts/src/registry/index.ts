/**
 * Server Registry Module
 * 
 * Manages MCP servers, tools, and their execution.
 * Supports HTTP, stdio, and in-process servers.
 */

import {
  ServerRegistryEntry,
  ToolRegistryEntry,
  MCPServerConfig,
  StdioServerConfig,
  HttpServerConfig,
  ServerStats,
  ToolResult,
} from '../types';
import {
  ToolNotFoundError,
  ServerConnectionError,
  ToolExecutionError,
} from '../errors';
import { REGISTRY_DEFAULTS } from '../constants';

/**
 * Server Registry
 * 
 * Central registry for all MCP servers and their tools.
 */
export class ServerRegistry {
  private servers: Map<string, ServerRegistryEntry>;
  private toolIndex: Map<string, string>; // toolName -> serverId
  
  constructor() {
    this.servers = new Map();
    this.toolIndex = new Map();
  }
  
  /**
   * Register a new server
   */
  registerServer(
    id: string,
    type: 'http' | 'stdio' | 'inprocess',
    config: MCPServerConfig | StdioServerConfig | HttpServerConfig
  ): void {
    if (this.servers.size >= REGISTRY_DEFAULTS.MAX_SERVERS) {
      throw new Error(`Maximum number of servers (${REGISTRY_DEFAULTS.MAX_SERVERS}) reached`);
    }
    
    const entry: ServerRegistryEntry = {
      id,
      type,
      config,
      tools: new Map(),
      stats: {
        totalExecutions: 0,
        totalErrors: 0,
        successRate: 0,
        averageExecutionTime: 0,
      },
      connected: false,
    };
    
    this.servers.set(id, entry);
  }
  
  /**
   * Unregister a server
   */
  unregisterServer(id: string): boolean {
    const server = this.servers.get(id);
    if (!server) {
      return false;
    }
    
    // Remove all tools from index
    for (const toolName of server.tools.keys()) {
      this.toolIndex.delete(toolName);
    }
    
    return this.servers.delete(id);
  }
  
  /**
   * Register a tool for a server
   */
  registerTool(serverId: string, tool: ToolRegistryEntry): void {
    const server = this.servers.get(serverId);
    if (!server) {
      throw new Error(`Server not found: ${serverId}`);
    }
    
    if (server.tools.size >= REGISTRY_DEFAULTS.MAX_TOOLS_PER_SERVER) {
      throw new Error(
        `Maximum number of tools per server (${REGISTRY_DEFAULTS.MAX_TOOLS_PER_SERVER}) reached`
      );
    }
    
    const toolName = tool.metadata.name;
    
    // Check for duplicate tool names
    const existingServerId = this.toolIndex.get(toolName);
    if (existingServerId && existingServerId !== serverId) {
      throw new Error(
        `Tool "${toolName}" already exists in server "${existingServerId}"`
      );
    }
    
    server.tools.set(toolName, tool);
    this.toolIndex.set(toolName, serverId);
  }
  
  /**
   * Get a server by ID
   */
  getServer(id: string): ServerRegistryEntry | undefined {
    return this.servers.get(id);
  }
  
  /**
   * Get a tool by name
   */
  getTool(toolName: string): { tool: ToolRegistryEntry; serverId: string } | undefined {
    const serverId = this.toolIndex.get(toolName);
    if (!serverId) {
      return undefined;
    }
    
    const server = this.servers.get(serverId);
    if (!server) {
      return undefined;
    }
    
    const tool = server.tools.get(toolName);
    if (!tool) {
      return undefined;
    }
    
    return { tool, serverId };
  }
  
  /**
   * List all servers
   */
  listServers(): ServerRegistryEntry[] {
    return Array.from(this.servers.values());
  }
  
  /**
   * List all tools
   */
  listTools(): Array<{ tool: ToolRegistryEntry; serverId: string }> {
    const tools: Array<{ tool: ToolRegistryEntry; serverId: string }> = [];
    
    for (const [serverId, server] of this.servers) {
      for (const tool of server.tools.values()) {
        tools.push({ tool, serverId });
      }
    }
    
    return tools;
  }
  
  /**
   * List tools for a specific server
   */
  listServerTools(serverId: string): ToolRegistryEntry[] {
    const server = this.servers.get(serverId);
    if (!server) {
      throw new Error(`Server not found: ${serverId}`);
    }
    
    return Array.from(server.tools.values());
  }
  
  /**
   * Execute a tool
   */
  async executeTool(
    toolName: string,
    parameters: Record<string, any>
  ): Promise<ToolResult> {
    const entry = this.getTool(toolName);
    if (!entry) {
      throw new ToolNotFoundError(toolName);
    }
    
    const { tool, serverId } = entry;
    const server = this.servers.get(serverId);
    if (!server) {
      throw new ServerConnectionError(serverId);
    }
    
    const startTime = Date.now();
    
    try {
      // Validate input
      if (tool.inputSchema) {
        const validation = await tool.inputSchema.parseAsync(parameters);
        parameters = validation;
      }
      
      // Execute the tool
      let result: any;
      if (tool.isAsync) {
        result = await tool.function(parameters);
      } else {
        result = tool.function(parameters);
      }
      
      // Validate output if schema exists
      if (tool.outputSchema) {
        result = await tool.outputSchema.parseAsync(result);
      }
      
      const executionTime = Date.now() - startTime;
      
      // Update stats
      this.updateStats(serverId, true, executionTime);
      
      return {
        status: 'success',
        result,
        executionTime,
      };
    } catch (error) {
      const executionTime = Date.now() - startTime;
      
      // Update stats
      this.updateStats(serverId, false, executionTime);
      
      throw new ToolExecutionError(
        toolName,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }
  
  /**
   * Update server statistics
   */
  private updateStats(serverId: string, success: boolean, executionTime: number): void {
    const server = this.servers.get(serverId);
    if (!server) {
      return;
    }
    
    const stats = server.stats;
    stats.totalExecutions++;
    
    if (!success) {
      stats.totalErrors++;
    }
    
    stats.successRate = (stats.totalExecutions - stats.totalErrors) / stats.totalExecutions;
    
    // Update average execution time using moving average
    if (stats.totalExecutions === 1) {
      stats.averageExecutionTime = executionTime;
    } else {
      stats.averageExecutionTime =
        (stats.averageExecutionTime * (stats.totalExecutions - 1) + executionTime) /
        stats.totalExecutions;
    }
    
    stats.lastExecutionTime = executionTime;
  }
  
  /**
   * Get statistics for a server
   */
  getServerStats(serverId: string): ServerStats | undefined {
    const server = this.servers.get(serverId);
    return server?.stats;
  }
  
  /**
   * Mark server as connected
   */
  markServerConnected(serverId: string, connected: boolean): void {
    const server = this.servers.get(serverId);
    if (server) {
      server.connected = connected;
    }
  }
  
  /**
   * Clear all servers and tools
   */
  clear(): void {
    this.servers.clear();
    this.toolIndex.clear();
  }
  
  /**
   * Get registry statistics
   */
  getStats(): {
    totalServers: number;
    totalTools: number;
    connectedServers: number;
  } {
    const connectedServers = Array.from(this.servers.values()).filter(
      s => s.connected
    ).length;
    
    return {
      totalServers: this.servers.size,
      totalTools: this.toolIndex.size,
      connectedServers,
    };
  }
}

// ============================================================================
// Singleton instance
// ============================================================================

let globalRegistry: ServerRegistry | null = null;

/**
 * Get the global server registry instance
 */
export function getGlobalRegistry(): ServerRegistry {
  if (!globalRegistry) {
    globalRegistry = new ServerRegistry();
  }
  return globalRegistry;
}

/**
 * Reset the global registry (useful for testing)
 */
export function resetGlobalRegistry(): void {
  globalRegistry = new ServerRegistry();
}

/**
 * Backward-compatible aliases.
 */
export class ToolRegistry extends ServerRegistry {}
export class MultiServerRegistry extends ServerRegistry {}
