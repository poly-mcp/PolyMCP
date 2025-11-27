/**
 * CodeMode Agent - LLM Code Generation for Tool Orchestration
 * Production implementation of "Code Mode" paradigm for efficient tool usage.
 */

import axios from 'axios';
import * as fs from 'fs';
import { LLMProvider, MCPToolMetadata, ExecutionResult } from '../types';
import { SandboxExecutor } from '../executor/executor';
import { ToolsAPI, defaultHttpExecutor } from '../executor/tools_api';

export interface CodeModeAgentConfig {
  llmProvider: LLMProvider;
  mcpServers?: string[];
  stdioServers?: any[];
  registryPath?: string;
  sandboxTimeout?: number;
  maxRetries?: number;
  verbose?: boolean;
}

/**
 * Code Mode Agent - Generates code instead of calling tools directly
 */
export class CodeModeAgent {
  private static SYSTEM_PROMPT_TEMPLATE = `You are an AI assistant that writes JavaScript code to accomplish tasks.

You have access to tools through the \`tools\` object. Each tool is a method you can call.

AVAILABLE TOOLS:
{tools_documentation}

RULES:
1. Tools are async, use await: await tools.tool_name({param1: value1})
2. Tools return JSON strings - parse with JSON.parse()
3. Use console.log() for output and results
4. Handle errors with try-catch
5. Use loops, conditions, variables as needed
6. IMPORTANT: All tool calls MUST be awaited

Write ONLY JavaScript code. No explanations.

Example pattern:
\`\`\`javascript
// Call tool (must await!)
const resultJson = await tools.some_tool({param1: "value1", param2: "value2"});
const result = JSON.parse(resultJson);
console.log(\`Result: \${JSON.stringify(result)}\`);
\`\`\``;

  private llmProvider: LLMProvider;
  private mcpServers: string[];
  private sandboxTimeout: number;
  private maxRetries: number;
  private verbose: boolean;
  private httpToolsCache: Map<string, MCPToolMetadata[]>;

  constructor(config: CodeModeAgentConfig) {
    this.llmProvider = config.llmProvider;
    this.mcpServers = config.mcpServers || [];
    this.sandboxTimeout = config.sandboxTimeout || 30000;
    this.maxRetries = config.maxRetries || 2;
    this.verbose = config.verbose || false;
    this.httpToolsCache = new Map();

    if (config.registryPath) {
      this.loadRegistry(config.registryPath);
    }

    this.discoverHttpTools();
  }

  /**
   * Load servers from registry
   */
  private loadRegistry(registryPath: string): void {
    try {
      const data = fs.readFileSync(registryPath, 'utf-8');
      const registry = JSON.parse(data);
      
      const httpServers = registry.servers || [];
      this.mcpServers.push(...httpServers);
      
      if (this.verbose) {
        console.log(`Loaded ${httpServers.length} HTTP servers`);
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`Failed to load registry: ${error.message}`);
      }
    }
  }

  /**
   * Discover tools from HTTP MCP servers
   */
  private discoverHttpTools(): void {
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
      this.httpToolsCache.set(serverUrl, tools);
      
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
   * Generate clear and simple API documentation for all available tools
   */
  private generateToolsDocumentation(): string {
    const docs: string[] = [];

    for (const [, tools] of this.httpToolsCache.entries()) {
      for (const tool of tools) {
        const properties = tool.input_schema.properties || {};

        // Build parameter signature
        const paramExamples: string[] = [];
        for (const [paramName, paramInfo] of Object.entries(properties)) {
          const info = paramInfo as any;
          const paramType = info.type || 'string';
          
          let exampleValue: string;
          if (paramType === 'string') {
            if (paramName.includes('type')) exampleValue = '"expense"';
            else if (paramName.includes('category')) exampleValue = '"rent"';
            else if (paramName.includes('description')) exampleValue = '"Monthly payment"';
            else if (paramName.includes('name')) exampleValue = '"Client Name"';
            else exampleValue = `"${paramName}_value"`;
          } else if (paramType === 'number' || paramType === 'integer') {
            exampleValue = '1000';
          } else if (paramType === 'boolean') {
            exampleValue = 'true';
          } else {
            exampleValue = 'value';
          }
          
          paramExamples.push(`${paramName}: ${exampleValue}`);
        }

        const signature = `await tools.${tool.name}({${paramExamples.join(', ')}})`;

        const doc = `
tools.${tool.name}():
  Description: ${tool.description}
  Signature: ${signature}
  Returns: JSON string (must parse with JSON.parse())`;
        
        docs.push(doc);
      }
    }

    return docs.length > 0 ? docs.join('\n') : 'No tools available';
  }

  /**
   * Extract JavaScript code from LLM response
   */
  private extractCodeFromResponse(response: string): string | null {
    // Look for code blocks
    const patterns = [
      /```javascript\s*([\s\S]*?)```/,
      /```js\s*([\s\S]*?)```/,
      /```\s*([\s\S]*?)```/,
    ];

    for (const pattern of patterns) {
      const match = response.match(pattern);
      if (match) {
        const code = match[1].trim();
        // Verify it looks like JavaScript code
        if (code.includes('await tools.') || code.includes('tools.')) {
          return code;
        }
      }
    }

    // Last resort: check if response is code
    if (response.includes('await tools.') || response.includes('tools.')) {
      const lines = response.trim().split('\n');
      const codeLines: string[] = [];
      let inCode = false;
      
      for (const line of lines) {
        if (line.includes('tools.') || inCode) {
          inCode = true;
          codeLines.push(line);
        }
      }
      
      if (codeLines.length > 0) {
        return codeLines.join('\n');
      }
    }

    return null;
  }

  /**
   * Create ToolsAPI instance with current tool state
   */
  private createToolsApi(): ToolsAPI {
    const httpExecutor = async (serverUrl: string, toolName: string, parameters: Record<string, any>) => {
      return await defaultHttpExecutor(serverUrl, toolName, parameters);
    };

    const stdioExecutor = async (_serverId: string, _toolName: string, _parameters: Record<string, any>) => {
      throw new Error('Stdio execution not yet implemented in sync mode');
    };

    return new ToolsAPI({
      httpTools: this.httpToolsCache,
      stdioAdapters: new Map(),
      httpExecutor,
      stdioExecutor,
      verbose: this.verbose,
    });
  }

  /**
   * Use LLM to generate code for the task
   */
  private async generateCode(userMessage: string, previousError?: string): Promise<string | null> {
    const toolsDocs = this.generateToolsDocumentation();
    const systemPrompt = CodeModeAgent.SYSTEM_PROMPT_TEMPLATE.replace(
      '{tools_documentation}',
      toolsDocs
    );

    let userPrompt = `USER REQUEST: ${userMessage}`;
    
    if (previousError) {
      userPrompt += `\n\nPREVIOUS ERROR: ${previousError}\nPlease fix the error and generate corrected code.`;
    }
    
    userPrompt += '\n\nWrite JavaScript code:';

    const fullPrompt = `${systemPrompt}\n\n${userPrompt}`;

    try {
      if (this.verbose) {
        console.log('\n' + '='.repeat(60));
        console.log('GENERATING CODE');
        console.log('='.repeat(60));
        console.log(`User request: ${userMessage}`);
        console.log(`Available tools: ${Array.from(this.httpToolsCache.values()).reduce((sum, tools) => sum + tools.length, 0)}`);
      }

      const response = await this.llmProvider.generate(fullPrompt);
      const code = this.extractCodeFromResponse(response);

      if (code) {
        if (this.verbose) {
          console.log(`\nâœ… Code generated (${code.length} chars)`);
          console.log('\nGenerated code:');
          console.log('='.repeat(60));
          console.log(code);
          console.log('='.repeat(60));
        }
        return code;
      } else {
        if (this.verbose) {
          console.log('\nâŒ No valid code found in LLM response');
          console.log(`Response preview: ${response.substring(0, 200)}...`);
        }
        return null;
      }
    } catch (error: any) {
      if (this.verbose) {
        console.log(`\nâŒ Code generation failed: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Execute generated code in sandbox
   */
  private async executeCode(code: string): Promise<ExecutionResult> {
    const toolsApi = this.createToolsApi();
    
    const executor = new SandboxExecutor(toolsApi, {
      timeout: this.sandboxTimeout,
      verbose: this.verbose,
    });

    return await executor.execute(code);
  }

  /**
   * Process user request with code generation approach
   */
  async run(userMessage: string): Promise<string> {
    if (this.verbose) {
      console.log('\n' + '='.repeat(60));
      console.log('CODE MODE AGENT');
      console.log('='.repeat(60));
      console.log(`User: ${userMessage}\n`);
    }

    // Re-discover tools
    await Promise.all(
      this.mcpServers.map(server => this.discoverServerTools(server))
    );

    let previousError: string | undefined;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      if (attempt > 0 && this.verbose) {
        console.log(`\nðŸ”„ Retry ${attempt}/${this.maxRetries}`);
      }

      // Generate code
      const code = await this.generateCode(userMessage, previousError);

      if (!code) {
        if (attempt < this.maxRetries) {
          previousError = 'Failed to generate valid JavaScript code';
          continue;
        }
        return "I couldn't generate appropriate code for your request. Please try rephrasing.";
      }

      // Execute code
      const result = await this.executeCode(code);

      if (result.success) {
        if (this.verbose) {
          console.log(`\nâœ… Execution successful (${result.executionTime.toFixed(2)}s)`);
          if (result.output) {
            console.log(`Output preview: ${result.output.substring(0, 200)}...`);
          }
        }

        return result.output || 'Task completed successfully.';
      } else {
        if (this.verbose) {
          console.log(`\nâŒ Execution failed: ${result.error}`);
        }

        previousError = result.error;

        if (attempt >= this.maxRetries) {
          return `I encountered an error: ${result.error}`;
        }
      }
    }

    return 'Failed to complete the task.';
  }

  /**
   * Add new HTTP MCP server
   */
  async addServer(serverUrl: string): Promise<void> {
    if (!this.mcpServers.includes(serverUrl)) {
      this.mcpServers.push(serverUrl);
      await this.discoverServerTools(serverUrl);
    }
  }
}