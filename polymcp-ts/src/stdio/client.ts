/**
 * MCP Stdio Client - Production Implementation
 * Handles communication with stdio-based MCP servers (like Anthropic's official servers).
 */

import spawn from 'cross-spawn';
import { ChildProcess } from 'child_process';
import { EventEmitter } from 'events';
import { StdioServerConfig, JsonRpcRequest, JsonRpcResponse, MCPToolMetadata } from '../types';

/**
 * MCP Stdio Client
 * Communicates with MCP servers that use JSON-RPC over stdin/stdout
 */
export class MCPStdioClient extends EventEmitter {
  private config: StdioServerConfig;
  private process: ChildProcess | null = null;
  private requestId: number = 0;
  private running: boolean = false;
  private pendingResponses: Map<string | number, { resolve: Function; reject: Function; timeout: NodeJS.Timeout }> = new Map();
  private buffer: string = '';

  constructor(config: StdioServerConfig) {
    super();
    this.config = config;
  }

  /**
   * Start the MCP server process
   */
  async start(): Promise<void> {
    if (this.running) {
      return;
    }

    try {
      const env = { ...process.env, ...this.config.env };

      this.process = spawn(this.config.command, this.config.args, {
        env,
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      if (!this.process.stdout || !this.process.stdin) {
        throw new Error('Failed to create process stdio streams');
      }

      // Handle stdout data
      this.process.stdout.on('data', (data: Buffer) => {
        this.handleStdout(data);
      });

      // Handle stderr
      this.process.stderr?.on('data', (data: Buffer) => {
        console.error(`[MCP Stdio] stderr: ${data.toString()}`);
      });

      // Handle process exit
      this.process.on('exit', (code) => {
        console.log(`[MCP Stdio] Process exited with code ${code}`);
        this.running = false;
        this.cleanup();
      });

      // Handle errors
      this.process.on('error', (error) => {
        console.error(`[MCP Stdio] Process error:`, error);
        this.running = false;
        this.cleanup();
      });

      this.running = true;
      console.log(`[MCP Stdio] Started: ${this.config.command} ${this.config.args.join(' ')}`);

      // Wait for process to stabilize
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Initialize connection
      await this.initialize();

    } catch (error: any) {
      console.error(`[MCP Stdio] Failed to start: ${error.message}`);
      throw new Error(`Failed to start MCP server: ${error.message}`);
    }
  }

  /**
   * Handle stdout data from process
   */
  private handleStdout(data: Buffer): void {
    this.buffer += data.toString();
    
    // Process complete lines
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() || ''; // Keep incomplete line in buffer

    for (const line of lines) {
      if (line.trim()) {
        try {
          const response: JsonRpcResponse = JSON.parse(line);
          this.handleResponse(response);
        } catch (error) {
          console.error('[MCP Stdio] Failed to parse response:', line);
        }
      }
    }
  }

  /**
   * Handle JSON-RPC response
   */
  private handleResponse(response: JsonRpcResponse): void {
    const pending = this.pendingResponses.get(response.id);
    if (pending) {
      clearTimeout(pending.timeout);
      this.pendingResponses.delete(response.id);

      if (response.error) {
        pending.reject(new Error(response.error.message));
      } else {
        pending.resolve(response);
      }
    }
  }

  /**
   * Send JSON-RPC request and wait for response
   */
  private async sendRequest(method: string, params?: Record<string, any>, timeout: number = 60000): Promise<JsonRpcResponse> {
    if (!this.running || !this.process?.stdin) {
      throw new Error('MCP server not running');
    }

    this.requestId++;
    const request: JsonRpcRequest = {
      jsonrpc: '2.0',
      id: this.requestId,
      method,
    };

    if (params !== undefined) {
      request.params = params;
    }

    return new Promise((resolve, reject) => {
      const requestId = this.requestId;
      
      // Set timeout
      const timeoutHandle = setTimeout(() => {
        this.pendingResponses.delete(requestId);
        reject(new Error(`Request timeout after ${timeout}ms`));
      }, timeout);

      // Store pending response
      this.pendingResponses.set(requestId, { resolve, reject, timeout: timeoutHandle });

      // Send request
      const requestJson = JSON.stringify(request) + '\n';
      this.process!.stdin!.write(requestJson);
    });
  }

  /**
   * Initialize the MCP connection
   */
  private async initialize(): Promise<void> {
    try {
      const response = await this.sendRequest('initialize', {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {},
        },
        clientInfo: {
          name: 'polymcp',
          version: '1.0.0',
        },
      });

      if (response.error) {
        throw new Error(`Initialization failed: ${response.error.message}`);
      }

      console.log('[MCP Stdio] Connection initialized successfully');
    } catch (error: any) {
      console.error(`[MCP Stdio] Failed to initialize: ${error.message}`);
      throw error;
    }
  }

  /**
   * List available tools from the MCP server
   */
  async listTools(): Promise<MCPToolMetadata[]> {
    try {
      const response = await this.sendRequest('tools/list');

      if (response.error) {
        throw new Error(`Error listing tools: ${response.error.message}`);
      }

      const tools = response.result?.tools || [];
      console.log(`[MCP Stdio] Listed ${tools.length} tools`);

      return tools;
    } catch (error: any) {
      console.error(`[MCP Stdio] Failed to list tools: ${error.message}`);
      return [];
    }
  }

  /**
   * Call a tool on the MCP server
   */
  async callTool(name: string, arguments_: Record<string, any>): Promise<any> {
    try {
      const response = await this.sendRequest('tools/call', {
        name,
        arguments: arguments_,
      });

      if (response.error) {
        const errorMsg = response.error.message || JSON.stringify(response.error);
        throw new Error(`Tool execution failed: ${errorMsg}`);
      }

      const result = response.result || {};
      console.log(`[MCP Stdio] Tool ${name} executed successfully`);

      return result;
    } catch (error: any) {
      console.error(`[MCP Stdio] Failed to call tool ${name}: ${error.message}`);
      throw error;
    }
  }

  /**
   * Stop the MCP server process
   */
  async stop(): Promise<void> {
    if (!this.running) {
      return;
    }

    this.running = false;

    try {
      // Clear all pending responses
      for (const [, pending] of this.pendingResponses.entries()) {
        clearTimeout(pending.timeout);
        pending.reject(new Error('Server stopping'));
      }
      this.pendingResponses.clear();

      if (this.process) {
        // Try graceful termination
        this.process.kill('SIGTERM');

        // Wait for process to exit
        await new Promise<void>((resolve) => {
          const timeout = setTimeout(() => {
            // Force kill if still running
            if (this.process) {
              this.process.kill('SIGKILL');
            }
            resolve();
          }, 3000);

          if (this.process) {
            this.process.once('exit', () => {
              clearTimeout(timeout);
              resolve();
            });
          } else {
            clearTimeout(timeout);
            resolve();
          }
        });

        this.process = null;
        console.log('[MCP Stdio] Server stopped gracefully');
      }
    } catch (error: any) {
      console.error(`[MCP Stdio] Error stopping server: ${error.message}`);
    } finally {
      this.cleanup();
    }
  }

  /**
   * Cleanup resources
   */
  private cleanup(): void {
    this.buffer = '';
    this.pendingResponses.clear();
  }
}

/**
 * Adapter to expose stdio MCP server as HTTP-compatible interface
 */
export class MCPStdioAdapter {
  private client: MCPStdioClient;
  private toolsCache: MCPToolMetadata[] | null = null;

  constructor(client: MCPStdioClient) {
    this.client = client;
  }

  /**
   * Get tools in HTTP-compatible format
   */
  async getTools(): Promise<MCPToolMetadata[]> {
    if (this.toolsCache !== null) {
      return this.toolsCache;
    }

    const stdioTools = await this.client.listTools();
    this.toolsCache = stdioTools;
    return stdioTools;
  }

  /**
   * Invoke tool in HTTP-compatible format
   */
  async invokeTool(toolName: string, parameters: Record<string, any>): Promise<any> {
    try {
      const result = await this.client.callTool(toolName, parameters);
      
      return {
        result,
        status: 'success',
      };
    } catch (error: any) {
      return {
        error: error.message,
        status: 'error',
      };
    }
  }
}