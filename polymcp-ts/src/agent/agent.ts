/**
 * PolyAgent - Enhanced Core Agent Implementation
 * 
 * Production-ready intelligent agent for MCP tool discovery and execution.
 * 
 * NEW FEATURES (v2.0):
 * - Authentication support (JWT, OAuth2, API Key, Basic)
 * - URL normalization with MCPBaseURL
 * - Tool metadata normalization and validation
 * - HTTP connection pooling
 * - Automatic retry on 401/403 errors
 * - Configurable timeout
 * - Custom HTTP headers
 */

import axios, { AxiosInstance } from 'axios';
import * as fs from 'fs';
import { LLMProvider, MCPToolMetadata, ToolResult, ToolWithServer } from '../types';

// Import auth system
import { AuthProvider } from '../auth/auth_base';

// Import utilities
import { MCPBaseURL } from '../toolkit/mcp_url';
import { normalizeToolMetadata } from '../toolkit/tool_normalize';
import { buildSkillsShContext, loadSkillsSh, SkillsShEntry } from '../skills_sh';

/**
 * Enhanced PolyAgent Configuration
 */
export interface PolyAgentConfig {
  /** LLM provider for tool selection and response generation */
  llmProvider: LLMProvider;
  
  /** List of MCP server URLs */
  mcpServers?: string[];
  
  /** Path to server registry JSON file */
  registryPath?: string;
  
  /** Authentication provider (optional) */
  authProvider?: AuthProvider;
  
  /** Custom HTTP headers (optional) */
  httpHeaders?: Record<string, string>;
  
  /** HTTP request timeout in milliseconds (default: 30000) */
  timeout?: number;
  
  /** Enable verbose logging */
  verbose?: boolean;

  /** Enable skills.sh context in prompts (default: true) */
  skillsShEnabled?: boolean;

  /** Extra skills.sh directories to load */
  skillsShDirs?: string[];

  /** Max skills to inject */
  skillsShMaxSkills?: number;

  /** Max total chars for skills context */
  skillsShMaxChars?: number;
}

/**
 * Enhanced Intelligent Agent
 * 
 * Discovers and executes MCP tools with enterprise-grade features:
 * - Multi-server support
 * - Authentication (JWT, OAuth2, API Key, Basic)
 * - Automatic retry on auth failures
 * - Connection pooling
 * - Tool validation
 * - URL normalization
 * 
 * Example:
 * ```typescript
 * import { PolyAgent } from './agent';
 * import { OpenAIProvider } from './llm_providers';
 * import { JWTAuthProvider } from './auth/jwt_auth';
 * 
 * const agent = new PolyAgent({
 *   llmProvider: new OpenAIProvider({ apiKey: 'sk-...' }),
 *   mcpServers: ['https://api.example.com'],
 *   authProvider: new JWTAuthProvider({
 *     secret: 'my-secret',
 *     algorithm: 'HS256',
 *     claims: { user_id: '123' }
 *   }),
 *   timeout: 30000,
 *   verbose: true
 * });
 * 
 * const result = await agent.run('Execute my task');
 * ```
 */
export class PolyAgent {
  private llmProvider: LLMProvider;
  private mcpServers: string[];
  private verbose: boolean;
  private toolsCache: Map<string, MCPToolMetadata[]>;
  private authProvider?: AuthProvider;
  private httpClient: AxiosInstance;
  private skillsShEnabled: boolean;
  private skillsShEntries: SkillsShEntry[];
  private skillsShMaxSkills: number;
  private skillsShMaxChars: number;

  constructor(config: PolyAgentConfig) {
    this.llmProvider = config.llmProvider;
    this.mcpServers = config.mcpServers || [];
    this.verbose = config.verbose || false;
    this.toolsCache = new Map();
    this.authProvider = config.authProvider;
    this.skillsShEnabled = config.skillsShEnabled !== false;
    this.skillsShEntries = this.skillsShEnabled ? loadSkillsSh(config.skillsShDirs) : [];
    this.skillsShMaxSkills = config.skillsShMaxSkills ?? 4;
    this.skillsShMaxChars = config.skillsShMaxChars ?? 5000;

    // Create HTTP client with connection pooling
    this.httpClient = axios.create({
      timeout: config.timeout || 30000,
      headers: config.httpHeaders || {},
    });

    // Apply auth headers if provider exists
    if (this.authProvider) {
      this.applyAuthSync();
    }

    // Load registry if provided
    if (config.registryPath) {
      this.loadRegistry(config.registryPath);
    }

    // Initial tool discovery
    this.discoverTools();
  }

  /**
   * Apply authentication headers synchronously.
   * Called during initialization.
   */
  private applyAuthSync(): void {
    if (!this.authProvider) return;

    try {
      const headers = this.authProvider.getHeadersSync();
      Object.assign(this.httpClient.defaults.headers, headers);
      
      if (this.verbose) {
        console.log('✓ Auth headers applied');
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`✗ Auth initialization failed: ${error.message}`);
      }
    }
  }

  /**
   * Apply authentication headers asynchronously.
   * Called before making requests.
   */
  private async applyAuth(): Promise<void> {
    if (!this.authProvider) return;

    try {
      const headers = await this.authProvider.getHeadersAsync();
      Object.assign(this.httpClient.defaults.headers, headers);
      
      if (this.verbose) {
        console.log('✓ Auth headers refreshed');
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`✗ Auth refresh failed: ${error.message}`);
      }
    }
  }

  /**
   * Refresh authentication after 401/403 error.
   * Attempts to get fresh credentials and retry.
   */
  private async refreshAuth(): Promise<void> {
    if (!this.authProvider) return;

    if (!this.authProvider.shouldRetryOnUnauthorized()) {
      if (this.verbose) {
        console.log('✗ Auth provider does not support retry');
      }
      return;
    }

    try {
      await this.authProvider.handleUnauthorizedAsync();
      await this.applyAuth();
      
      if (this.verbose) {
        console.log('✓ Auth refreshed after 401/403');
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`✗ Auth refresh failed: ${error.message}`);
      }
      throw error;
    }
  }

  /**
   * Check if error is an auth error (401/403)
   */
  private isAuthError(error: any): boolean {
    return (
      error.response?.status === 401 ||
      error.response?.status === 403
    );
  }

  /**
   * Load MCP servers from registry JSON file
   */
  private loadRegistry(registryPath: string): void {
    try {
      const data = fs.readFileSync(registryPath, 'utf-8');
      const registry = JSON.parse(data);
      const servers = registry.servers || [];
      this.mcpServers.push(...servers);
      
      if (this.verbose) {
        console.log(`✓ Loaded ${servers.length} servers from registry`);
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`✗ Failed to load registry: ${error.message}`);
      }
    }
  }

  /**
   * Discover tools from all configured MCP servers
   */
  private discoverTools(): void {
    for (const serverUrl of this.mcpServers) {
      this.discoverServerTools(serverUrl);
    }
  }

  /**
   * Discover tools from a single server (with auth and retry)
   */
  private async discoverServerTools(serverUrl: string): Promise<void> {
    try {
      // Normalize URL
      const base = MCPBaseURL.normalize(serverUrl);
      const listUrl = base.listToolsUrl();

      // Apply latest auth
      await this.applyAuth();

      // First attempt
      let response;
      try {
        response = await this.httpClient.get(listUrl, { timeout: 5000 });
      } catch (error: any) {
        // Retry once on auth error
        if (this.isAuthError(error)) {
          if (this.verbose) {
            console.log(`⚠ 401/403 on ${base.base}, refreshing auth...`);
          }
          await this.refreshAuth();
          response = await this.httpClient.get(listUrl, { timeout: 5000 });
        } else {
          throw error;
        }
      }

      // Normalize and validate tools
      const rawTools = response.data.tools || [];
      const tools = rawTools.map((tool: any) => {
        try {
          return normalizeToolMetadata(tool);
        } catch (error: any) {
          if (this.verbose) {
            console.log(`⚠ Skipping invalid tool from ${base.base}: ${error.message}`);
          }
          return null;
        }
      }).filter(Boolean) as MCPToolMetadata[];

      this.toolsCache.set(base.base, tools);
      
      if (this.verbose) {
        console.log(`✓ Discovered ${tools.length} tools from ${base.base}`);
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`✗ Failed to discover tools from ${serverUrl}: ${error.message}`);
      }
    }
  }

  /**
   * Get all discovered tools with server information
   */
  private getAllTools(): ToolWithServer[] {
    const allTools: ToolWithServer[] = [];
    
    for (const [serverUrl, tools] of this.toolsCache.entries()) {
      for (const tool of tools) {
        allTools.push({
          ...tool,
          _server_url: serverUrl,
          _server_type: 'http',
        });
      }
    }
    
    return allTools;
  }

  /**
   * Use LLM to select the most appropriate tool
   */
  private async selectTool(userMessage: string): Promise<ToolWithServer | null> {
    const allTools = this.getAllTools();
    
    if (allTools.length === 0) {
      return null;
    }

    const toolsDescription = allTools
      .map((tool, i) => 
        `${i + 1}. ${tool.name}: ${tool.description}\n   Input: ${JSON.stringify(tool.input_schema, null, 2)}`
      )
      .join('\n\n');

    const skillsCtx = this.skillsShEnabled
      ? buildSkillsShContext(
          userMessage,
          this.skillsShEntries,
          this.skillsShMaxSkills,
          this.skillsShMaxChars
        )
      : '';

    const prompt = `You are a tool selection assistant. Analyze the user request and select the most appropriate tool.

User request: ${userMessage}

Available tools:
${toolsDescription}

${skillsCtx}

Respond with valid JSON only:
{
    "tool_index": <index of selected tool (0-based)>,
    "tool_name": "<name of the tool>",
    "parameters": {<input parameters for the tool>},
    "reasoning": "<brief explanation>"
}

If no tool is suitable, respond with: {"tool_index": -1, "reasoning": "No suitable tool found"}

Respond ONLY with JSON, no additional text.`;

    try {
      let llmResponse = await this.llmProvider.generate(prompt);
      llmResponse = llmResponse.trim();
      
      // Extract JSON from markdown code blocks if present
      if (llmResponse.includes('```json')) {
        llmResponse = llmResponse.split('```json')[1].split('```')[0].trim();
      } else if (llmResponse.includes('```')) {
        llmResponse = llmResponse.split('```')[1].split('```')[0].trim();
      }
      
      const selection = JSON.parse(llmResponse);
      
      if (selection.tool_index < 0) {
        return null;
      }
      
      const toolIndex = selection.tool_index;
      if (toolIndex >= allTools.length) {
        return null;
      }
      
      const selectedTool = { ...allTools[toolIndex] };
      selectedTool._parameters = selection.parameters || {};
      selectedTool._reasoning = selection.reasoning || '';
      
      if (this.verbose) {
        console.log(`✓ Selected tool: ${selectedTool.name}`);
        console.log(`  Reasoning: ${selectedTool._reasoning}`);
      }
      
      return selectedTool;
    } catch (error: any) {
      if (this.verbose) {
        console.log(`✗ Tool selection failed: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Execute a tool by calling the MCP server (with auth and retry)
   */
  private async executeTool(tool: ToolWithServer): Promise<ToolResult> {
    const serverUrl = tool._server_url;
    const toolName = tool.name;
    const parameters = tool._parameters || {};

    if (!serverUrl) {
      return { status: 'error', error: 'Server URL not specified' };
    }

    try {
      // Normalize URL and construct invoke endpoint
      const base = MCPBaseURL.normalize(serverUrl);
      const invokeUrl = base.invokeUrl(toolName);

      // Apply latest auth
      await this.applyAuth();

      // First attempt
      let response;
      try {
        response = await this.httpClient.post(invokeUrl, parameters);
      } catch (error: any) {
        // Retry once on auth error
        if (this.isAuthError(error)) {
          if (this.verbose) {
            console.log(`⚠ 401/403 on tool execution, refreshing auth...`);
          }
          await this.refreshAuth();
          response = await this.httpClient.post(invokeUrl, parameters);
        } else {
          throw error;
        }
      }
      
      if (this.verbose) {
        console.log(`✓ Tool executed successfully`);
      }
      
      return response.data;
    } catch (error: any) {
      const errorMsg = `Tool execution failed: ${error.message}`;
      if (this.verbose) {
        console.log(`✗ ${errorMsg}`);
      }
      return { status: 'error', error: errorMsg };
    }
  }

  /**
   * Generate natural language response based on tool result
   */
  private async generateResponse(userMessage: string, toolResult: ToolResult): Promise<string> {
    const prompt = `You are a helpful assistant. The user asked: "${userMessage}"

A tool was executed and returned:
${JSON.stringify(toolResult, null, 2)}

Provide a clear, natural language response to the user based on this result.
Answer the user's question naturally without mentioning technical details.`;

    try {
      const response = await this.llmProvider.generate(prompt);
      return response;
    } catch (error: any) {
      if (this.verbose) {
        console.log(`✗ Failed to generate response: ${error.message}`);
      }
      return `Tool executed. Result: ${JSON.stringify(toolResult)}`;
    }
  }

  /**
   * Process user request and return response
   */
  async run(userMessage: string): Promise<string> {
    if (this.verbose) {
      console.log(`\n${'='.repeat(60)}`);
      console.log(`User: ${userMessage}`);
      console.log('='.repeat(60));
    }
    
    // Re-discover tools to ensure we have latest
    await Promise.all(
      this.mcpServers.map(server => this.discoverServerTools(server))
    );
    
    const selectedTool = await this.selectTool(userMessage);
    
    if (!selectedTool) {
      return "I couldn't find a suitable tool for your request. Please try rephrasing or ask something else.";
    }
    
    const toolResult = await this.executeTool(selectedTool);
    const response = await this.generateResponse(userMessage, toolResult);
    
    if (this.verbose) {
      console.log(`\nAgent: ${response}`);
      console.log('='.repeat(60) + '\n');
    }
    
    return response;
  }

  /**
   * Add a new MCP server and discover its tools
   */
  async addServer(serverUrl: string): Promise<void> {
    // Normalize URL before adding
    const base = MCPBaseURL.normalize(serverUrl);
    
    if (!this.mcpServers.includes(base.base)) {
      this.mcpServers.push(base.base);
      await this.discoverServerTools(base.base);
      
      if (this.verbose) {
        console.log(`✓ Added server: ${base.base}`);
      }
    }
  }

  /**
   * Remove a server from the agent
   */
  removeServer(serverUrl: string): void {
    const base = MCPBaseURL.normalize(serverUrl);
    const index = this.mcpServers.indexOf(base.base);
    
    if (index > -1) {
      this.mcpServers.splice(index, 1);
      this.toolsCache.delete(base.base);
      
      if (this.verbose) {
        console.log(`✓ Removed server: ${base.base}`);
      }
    }
  }

  /**
   * Get list of configured servers
   */
  getServers(): string[] {
    return [...this.mcpServers];
  }

  /**
   * Get count of discovered tools
   */
  getToolCount(): number {
    let count = 0;
    for (const tools of this.toolsCache.values()) {
      count += tools.length;
    }
    return count;
  }

  /**
   * Get all discovered tool names
   */
  getToolNames(): string[] {
    const allTools = this.getAllTools();
    return allTools.map(tool => tool.name);
  }

  /**
   * Update authentication provider
   */
  setAuthProvider(authProvider: AuthProvider): void {
    this.authProvider = authProvider;
    this.applyAuthSync();
    
    if (this.verbose) {
      console.log('✓ Auth provider updated');
    }
  }

  /**
   * Clear authentication
   */
  clearAuth(): void {
    this.authProvider = undefined;
    
    // Remove auth headers
    if (this.httpClient.defaults.headers) {
      delete this.httpClient.defaults.headers['Authorization'];
    }
    
    if (this.verbose) {
      console.log('✓ Auth cleared');
    }
  }

  /**
   * Close HTTP client (cleanup)
   */
  close(): void {
    // Axios doesn't require explicit cleanup, but we provide this for consistency
    if (this.verbose) {
      console.log('✓ Agent closed');
    }
  }
}
