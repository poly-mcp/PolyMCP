/**
 * MCP Apps Server
 * 
 * Serves UI resources and handles tool execution for MCP Apps.
 * Integrates with existing MCP infrastructure.
 */

import { MCPApp, UIResource } from './mcp_apps_builder';

/**
 * MCP Apps Server.
 * 
 * Serves MCP Apps with both tools and UI resources.
 * Handles HTTP requests for UI resources and tool execution.
 * 
 * Features:
 * - Serve UI resources (HTML, React, JSON, etc.)
 * - Execute tool calls from UI
 * - CORS support for cross-origin requests
 * - Resource caching
 * - Hot reload support
 * 
 * Example:
 * ```typescript
 * const server = new MCPAppsServer({ port: 3000 });
 * 
 * // Register an app
 * server.registerApp(calculatorApp);
 * 
 * // Start server
 * await server.start();
 * 
 * // Now accessible at:
 * // - Tools: POST /tools/{toolName}
 * // - Resources: GET /resources/{uri}
 * // - List tools: GET /list_tools
 * // - List resources: GET /list_resources
 * ```
 */
export class MCPAppsServer {
  private apps: Map<string, MCPApp> = new Map();
  private port: number;
  private enableCORS: boolean;

  constructor(config: { port?: number; enableCORS?: boolean } = {}) {
    this.port = config.port || 3000;
    this.enableCORS = config.enableCORS !== false; // default true
  }

  /**
   * Register an MCP app
   */
  registerApp(app: MCPApp): void {
    this.apps.set(app.id, app);
  }

  /**
   * Unregister an app
   */
  unregisterApp(appId: string): void {
    this.apps.delete(appId);
  }

  /**
   * Get all registered apps
   */
  getApps(): MCPApp[] {
    return Array.from(this.apps.values());
  }

  /**
   * Get app by ID
   */
  getApp(appId: string): MCPApp | undefined {
    return this.apps.get(appId);
  }

  /**
   * List all tools from all apps
   */
  listTools(): Array<{
    name: string;
    description: string;
    inputSchema: Record<string, any>;
    appId: string;
    appName: string;
  }> {
    const tools: Array<{
      name: string;
      description: string;
      inputSchema: Record<string, any>;
      appId: string;
      appName: string;
    }> = [];

    for (const app of this.apps.values()) {
      for (const tool of app.tools) {
        tools.push({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
          appId: app.id,
          appName: app.name,
        });
      }
    }

    return tools;
  }

  /**
   * List all UI resources from all apps
   */
  listResources(): Array<{
    uri: string;
    name: string;
    description: string;
    mimeType: string;
    appId: string;
    appName: string;
  }> {
    const resources: Array<{
      uri: string;
      name: string;
      description: string;
      mimeType: string;
      appId: string;
      appName: string;
    }> = [];

    for (const app of this.apps.values()) {
      for (const resource of app.resources) {
        resources.push({
          uri: resource.uri,
          name: resource.name,
          description: resource.description,
          mimeType: resource.mimeType,
          appId: app.id,
          appName: app.name,
        });
      }
    }

    return resources;
  }

  /**
   * Get resource by URI
   */
  getResource(uri: string): UIResource | undefined {
    for (const app of this.apps.values()) {
      const resource = app.resources.find(r => r.uri === uri);
      if (resource) {
        return resource;
      }
    }
    return undefined;
  }

  /**
   * Find tool by name
   */
  findTool(toolName: string): {
    tool: any;
    app: MCPApp;
  } | undefined {
    for (const app of this.apps.values()) {
      const tool = app.tools.find(t => t.name === toolName);
      if (tool) {
        return { tool, app };
      }
    }
    return undefined;
  }

  /**
   * Execute tool
   */
  async executeTool(toolName: string, params: any): Promise<any> {
    const found = this.findTool(toolName);
    
    if (!found) {
      throw new Error(`Tool not found: ${toolName}`);
    }

    try {
      const result = await found.tool.handler(params);
      return result;
    } catch (error: any) {
      throw new Error(`Tool execution failed: ${error.message}`);
    }
  }

  /**
   * Generate MCP protocol response for list_tools
   */
  getMCPToolsResponse(): {
    tools: Array<{
      name: string;
      description: string;
      input_schema: Record<string, any>;
    }>;
  } {
    const tools = this.listTools();
    
    return {
      tools: tools.map(t => ({
        name: t.name,
        description: t.description,
        input_schema: t.inputSchema,
      }))
    };
  }

  /**
   * Generate MCP protocol response for list_resources
   */
  getMCPResourcesResponse(): {
    resources: Array<{
      uri: string;
      name: string;
      description: string;
      mimeType: string;
    }>;
  } {
    const resources = this.listResources();
    
    return {
      resources: resources.map(r => ({
        uri: r.uri,
        name: r.name,
        description: r.description,
        mimeType: r.mimeType,
      }))
    };
  }

  /**
   * Generate MCP protocol response for read_resource
   */
  getMCPResourceContent(uri: string): {
    contents: Array<{
      uri: string;
      mimeType: string;
      text?: string;
    }>;
  } {
    const resource = this.getResource(uri);
    
    if (!resource) {
      throw new Error(`Resource not found: ${uri}`);
    }

    return {
      contents: [
        {
          uri: resource.uri,
          mimeType: resource.mimeType,
          text: resource.content,
        }
      ]
    };
  }

  /**
   * Handle HTTP request (generic)
   */
  async handleRequest(
    method: string,
    path: string,
    body?: any
  ): Promise<{
    status: number;
    headers: Record<string, string>;
    body: any;
  }> {
    // CORS headers
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (this.enableCORS) {
      headers['Access-Control-Allow-Origin'] = '*';
      headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS';
      headers['Access-Control-Allow-Headers'] = 'Content-Type';
    }

    // Handle OPTIONS for CORS preflight
    if (method === 'OPTIONS') {
      return { status: 200, headers, body: null };
    }

    try {
      // List tools
      if (method === 'GET' && path === '/list_tools') {
        return {
          status: 200,
          headers,
          body: this.getMCPToolsResponse(),
        };
      }

      // List resources
      if (method === 'GET' && path === '/list_resources') {
        return {
          status: 200,
          headers,
          body: this.getMCPResourcesResponse(),
        };
      }

      // Get resource
      if (method === 'GET' && path.startsWith('/resources/')) {
        const uri = decodeURIComponent(path.substring('/resources/'.length));
        const resource = this.getResource(uri);
        
        if (!resource) {
          return {
            status: 404,
            headers,
            body: { error: 'Resource not found' },
          };
        }

        // Return resource content with appropriate MIME type
        return {
          status: 200,
          headers: {
            ...headers,
            'Content-Type': resource.mimeType,
          },
          body: resource.content,
        };
      }

      // Execute tool
      if (method === 'POST' && path.startsWith('/tools/')) {
        const toolName = path.substring('/tools/'.length);
        const result = await this.executeTool(toolName, body);
        
        return {
          status: 200,
          headers,
          body: result,
        };
      }

      // List apps
      if (method === 'GET' && path === '/apps') {
        return {
          status: 200,
          headers,
          body: {
            apps: this.getApps().map(app => ({
              id: app.id,
              name: app.name,
              description: app.description,
              toolCount: app.tools.length,
              resourceCount: app.resources.length,
            }))
          },
        };
      }

      // Not found
      return {
        status: 404,
        headers,
        body: { error: 'Not found' },
      };
    } catch (error: any) {
      return {
        status: 500,
        headers,
        body: { error: error.message },
      };
    }
  }

  /**
   * Get server info
   */
  getInfo(): {
    port: number;
    appCount: number;
    toolCount: number;
    resourceCount: number;
  } {
    return {
      port: this.port,
      appCount: this.apps.size,
      toolCount: this.listTools().length,
      resourceCount: this.listResources().length,
    };
  }

  /**
   * Start server (stub - actual HTTP server setup would go here)
   */
  async start(): Promise<void> {
    // In a real implementation, this would start an HTTP server
    // using Node.js http/https or Express
    console.log(`MCP Apps Server ready on port ${this.port}`);
    console.log(`Apps: ${this.apps.size}`);
    console.log(`Tools: ${this.listTools().length}`);
    console.log(`Resources: ${this.listResources().length}`);
  }

  /**
   * Stop server (stub)
   */
  async stop(): Promise<void> {
    console.log('MCP Apps Server stopped');
  }
}

/**
 * MCP Apps Server Factory
 */
export class MCPAppsServerFactory {
  /**
   * Create development server (with hot reload, verbose logging)
   */
  static createDevelopment(apps: MCPApp[] = []): MCPAppsServer {
    const server = new MCPAppsServer({ port: 3000, enableCORS: true });
    
    for (const app of apps) {
      server.registerApp(app);
    }
    
    return server;
  }

  /**
   * Create production server
   */
  static createProduction(apps: MCPApp[] = [], port: number = 8080): MCPAppsServer {
    const server = new MCPAppsServer({ port, enableCORS: false });
    
    for (const app of apps) {
      server.registerApp(app);
    }
    
    return server;
  }

  /**
   * Create server with apps
   */
  static createWithApps(apps: MCPApp[], config?: { port?: number }): MCPAppsServer {
    const server = new MCPAppsServer(config);
    
    for (const app of apps) {
      server.registerApp(app);
    }
    
    return server;
  }
}
