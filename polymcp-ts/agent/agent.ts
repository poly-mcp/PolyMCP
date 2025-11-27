/**
 * PolyAgent - Core Agent Implementation
 * Production-ready intelligent agent for MCP tool discovery and execution.
 */

import axios from 'axios';
import * as fs from 'fs';
import { LLMProvider, MCPToolMetadata, ToolResult, ToolWithServer } from '../types';

export interface PolyAgentConfig {
  llmProvider: LLMProvider;
  mcpServers?: string[];
  registryPath?: string;
  verbose?: boolean;
}

/**
 * Intelligent agent that discovers and executes MCP tools
 */
export class PolyAgent {
  private llmProvider: LLMProvider;
  private mcpServers: string[];
  private verbose: boolean;
  private toolsCache: Map<string, MCPToolMetadata[]>;

  constructor(config: PolyAgentConfig) {
    this.llmProvider = config.llmProvider;
    this.mcpServers = config.mcpServers || [];
    this.verbose = config.verbose || false;
    this.toolsCache = new Map();

    if (config.registryPath) {
      this.loadRegistry(config.registryPath);
    }

    this.discoverTools();
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
        console.log(`Loaded ${servers.length} servers from registry`);
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`Failed to load registry: ${error.message}`);
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
   * Discover tools from a single server
   */
  private async discoverServerTools(serverUrl: string): Promise<void> {
    try {
      const listUrl = `${serverUrl}/list_tools`;
      const response = await axios.get(listUrl, { timeout: 5000 });
      
      const tools = response.data.tools || [];
      this.toolsCache.set(serverUrl, tools);
      
      if (this.verbose) {
        console.log(`Discovered ${tools.length} tools from ${serverUrl}`);
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`Failed to discover tools from ${serverUrl}: ${error.message}`);
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

    const prompt = `You are a tool selection assistant. Analyze the user request and select the most appropriate tool.

User request: ${userMessage}

Available tools:
${toolsDescription}

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
        console.log(`Selected tool: ${selectedTool.name}`);
        console.log(`Reasoning: ${selectedTool._reasoning}`);
      }
      
      return selectedTool;
    } catch (error: any) {
      if (this.verbose) {
        console.log(`Tool selection failed: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Execute a tool by calling the MCP server
   */
  private async executeTool(tool: ToolWithServer): Promise<ToolResult> {
    const serverUrl = tool._server_url;
    const toolName = tool.name;
    const parameters = tool._parameters || {};
    
    try {
      const invokeUrl = `${serverUrl}/invoke/${toolName}`;
      const response = await axios.post(invokeUrl, parameters, { timeout: 30000 });
      
      if (this.verbose) {
        console.log('Tool executed successfully');
      }
      
      return response.data;
    } catch (error: any) {
      const errorMsg = `Tool execution failed: ${error.message}`;
      if (this.verbose) {
        console.log(errorMsg);
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
        console.log(`Failed to generate response: ${error.message}`);
      }
      return `Tool executed. Result: ${JSON.stringify(toolResult)}`;
    }
  }

  /**
   * Process user request and return response
   */
  async run(userMessage: string): Promise<string> {
    if (this.verbose) {
      console.log(`\nUser: ${userMessage}\n`);
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
      console.log(`\nAgent: ${response}\n`);
    }
    
    return response;
  }

  /**
   * Add a new MCP server and discover its tools
   */
  async addServer(serverUrl: string): Promise<void> {
    if (!this.mcpServers.includes(serverUrl)) {
      this.mcpServers.push(serverUrl);
      await this.discoverServerTools(serverUrl);
    }
  }
}
