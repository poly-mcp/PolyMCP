/**
 * MCP Stdio Client - Production Implementation
 * Connect to and interact with MCP servers over stdio (JSON-RPC 2.0).
 * 
 * This allows connecting to npm-published MCP servers like @playwright/mcp,
 * @raycast/mcp, and any other stdio-based MCP server.
 * 
 * Features:
 * - Full JSON-RPC 2.0 client implementation
 * - MCP protocol (2024-11-05) compliance
 * - Automatic process spawning and management
 * - Request timeout handling
 * - Connection pooling support
 * - Comprehensive error handling
 * - Async iterator support
 */

import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';
import * as readline from 'readline';

/**
 * JSON-RPC 2.0 Request
 */
interface JsonRpcRequest {
  jsonrpc: '2.0';
  id: string | number;
  method: string;
  params?: any;
}

/**
 * JSON-RPC 2.0 Response
 */
interface JsonRpcResponse {
  jsonrpc: '2.0';
  id: string | number;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

/**
 * Tool definition from MCP server
 */
export interface MCPToolInfo {
  name: string;
  description: string;
  input_schema: any;
}

/**
 * Tool call result
 */
export interface ToolCallResult {
  content: Array<{ type: string; text?: string; [key: string]: any }>;
  isError: boolean;
}

/**
 * Stdio client options
 */
export interface StdioClientOptions {
  /** Command to spawn (e.g., 'npx @playwright/mcp' or 'node server.js') */
  command: string;
  /** Additional command arguments */
  args?: string[];
  /** Request timeout in milliseconds */
  timeout?: number;
  /** Enable verbose logging to stderr */
  verbose?: boolean;
  /** Working directory for spawned process */
  cwd?: string;
  /** Environment variables for spawned process */
  env?: Record<string, string>;
}

/**
 * Pending request tracker
 */
interface PendingRequest {
  resolve: (value: any) => void;
  reject: (error: Error) => void;
  timeout: NodeJS.Timeout;
}

/**
 * Production MCP client for connecting to stdio-based servers.
 * 
 * Spawns and manages a child process, communicating via JSON-RPC 2.0
 * over stdin/stdout. Automatically handles initialization, cleanup,
 * and error recovery.
 * 
 * Example:
 * ```typescript
 * import { MCPStdioClient } from 'polymcp';
 * 
 * const client = new MCPStdioClient({
 *   command: 'npx @playwright/mcp'
 * });
 * 
 * await client.connect();
 * 
 * const tools = await client.listTools();
 * console.log('Available tools:', tools);
 * 
 * const result = await client.callTool('navigate', {
 *   url: 'https://example.com'
 * });
 * 
 * await client.disconnect();
 * ```
 */
export class MCPStdioClient extends EventEmitter {
  private process: ChildProcess | null = null;
  private rl: readline.Interface | null = null;
  private requestId: number = 0;
  private pendingRequests: Map<number, PendingRequest> = new Map();
  private initialized: boolean = false;
  private connected: boolean = false;
  private options: Required<StdioClientOptions>;
  
  // Server info
  private serverInfo: { name: string; version: string } | null = null;
  private serverCapabilities: any = null;

  constructor(options: StdioClientOptions) {
    super();
    
    if (!options.command) {
      throw new Error('Command is required');
    }

    this.options = {
      command: options.command,
      args: options.args || [],
      timeout: options.timeout || 30000,
      verbose: options.verbose || false,
      cwd: options.cwd || process.cwd(),
      env: options.env || {},
    };
  }

  /**
   * Log to stderr
   */
  private log(message: string): void {
    if (this.options.verbose) {
      const timestamp = new Date().toISOString();
      process.stderr.write(`[MCPClient] [${timestamp}] ${message}\n`);
    }
  }

  /**
   * Parse command string into command and args
   */
  private parseCommand(): { cmd: string; args: string[] } {
    const parts = this.options.command.split(' ').filter(p => p.trim());
    return {
      cmd: parts[0],
      args: [...parts.slice(1), ...this.options.args],
    };
  }

  /**
   * Connect to MCP server
   * Spawns the process and performs initialization handshake
   */
  async connect(): Promise<void> {
    if (this.connected) {
      throw new Error('Client already connected');
    }

    const { cmd, args } = this.parseCommand();
    
    this.log(`Spawning: ${cmd} ${args.join(' ')}`);

    // Spawn process
    this.process = spawn(cmd, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: this.options.cwd,
      env: {
        ...process.env,
        ...this.options.env,
      },
    });

    if (!this.process.stdin || !this.process.stdout || !this.process.stderr) {
      throw new Error('Failed to create stdio streams');
    }

    // Setup readline for line-by-line reading
    this.rl = readline.createInterface({
      input: this.process.stdout,
      terminal: false,
    });

    // Handle responses
    this.rl.on('line', (line: string) => {
      if (!line.trim()) return;
      
      try {
        const response = JSON.parse(line) as JsonRpcResponse;
        this.handleResponse(response);
      } catch (error: any) {
        this.log(`Failed to parse response: ${error.message}`);
        this.log(`Raw line: ${line}`);
      }
    });

    // Handle stderr (server logs)
    this.process.stderr.on('data', (data: Buffer) => {
      const text = data.toString().trim();
      if (text) {
        this.log(`Server stderr: ${text}`);
      }
    });

    // Handle process errors
    this.process.on('error', (error: Error) => {
      this.log(`Process error: ${error.message}`);
      this.emit('error', error);
      this.handleProcessExit(1, 'error');
    });

    // Handle process exit
    this.process.on('exit', (code: number | null, signal: string | null) => {
      const reason = signal || `code ${code}`;
      this.log(`Process exited: ${reason}`);
      this.handleProcessExit(code || 0, reason);
    });

    this.connected = true;

    // Perform initialization handshake
    try {
      await this.initialize();
      this.log('Connection established and initialized');
    } catch (error: any) {
      this.connected = false;
      throw new Error(`Initialization failed: ${error.message}`);
    }
  }

  /**
   * Handle process exit
   */
  private handleProcessExit(code: number, reason: string): void {
    this.connected = false;
    this.initialized = false;

    // Reject all pending requests
    for (const [id, pending] of this.pendingRequests.entries()) {
      clearTimeout(pending.timeout);
      pending.reject(new Error(`Server process exited: ${reason}`));
      this.pendingRequests.delete(id);
    }

    this.emit('disconnect', { code, reason });
  }

  /**
   * Initialize MCP protocol
   */
  private async initialize(): Promise<void> {
    if (this.initialized) {
      return;
    }

    const response = await this.sendRequest('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'PolyMCP Client',
        version: '1.0.0',
      },
    });

    this.serverInfo = response.serverInfo || null;
    this.serverCapabilities = response.capabilities || null;
    this.initialized = true;

    this.log(`Initialized with server: ${this.serverInfo?.name || 'unknown'}`);
  }

  /**
   * List available tools from server
   */
  async listTools(): Promise<MCPToolInfo[]> {
    if (!this.initialized) {
      throw new Error('Client not initialized. Call connect() first.');
    }

    const response = await this.sendRequest('tools/list', {});
    return response.tools || [];
  }

  /**
   * Call a tool on the server
   */
  async callTool(name: string, args: Record<string, any> = {}): Promise<ToolCallResult> {
    if (!this.initialized) {
      throw new Error('Client not initialized. Call connect() first.');
    }

    const response = await this.sendRequest('tools/call', {
      name,
      arguments: args,
    });

    return response as ToolCallResult;
  }

  /**
   * Send ping to check server health
   */
  async ping(): Promise<void> {
    if (!this.initialized) {
      throw new Error('Client not initialized. Call connect() first.');
    }

    await this.sendRequest('ping', {});
  }

  /**
   * Send JSON-RPC request to server
   */
  private async sendRequest(method: string, params: any): Promise<any> {
    if (!this.connected) {
      throw new Error('Not connected to server');
    }

    if (!this.process || !this.process.stdin) {
      throw new Error('Process stdin not available');
    }

    const id = ++this.requestId;

    const request: JsonRpcRequest = {
      jsonrpc: '2.0',
      id,
      method,
      params,
    };

    const requestJson = JSON.stringify(request);
    this.log(`Sending request: ${method} (id: ${id})`);

    // Write to stdin
    this.process.stdin.write(requestJson + '\n');

    // Wait for response with timeout
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`Request timeout after ${this.options.timeout}ms: ${method}`));
      }, this.options.timeout);

      this.pendingRequests.set(id, { resolve, reject, timeout });
    });
  }

  /**
   * Handle JSON-RPC response from server
   */
  private handleResponse(response: JsonRpcResponse): void {
    const pending = this.pendingRequests.get(response.id as number);

    if (!pending) {
      this.log(`Received response for unknown request id: ${response.id}`);
      return;
    }

    clearTimeout(pending.timeout);
    this.pendingRequests.delete(response.id as number);

    if (response.error) {
      this.log(`Request ${response.id} failed: ${response.error.message}`);
      pending.reject(
        new Error(`JSON-RPC Error ${response.error.code}: ${response.error.message}`)
      );
    } else {
      this.log(`Request ${response.id} succeeded`);
      pending.resolve(response.result);
    }
  }

  /**
   * Disconnect from server
   * Terminates the child process and cleans up resources
   */
  async disconnect(): Promise<void> {
    if (!this.connected) {
      return;
    }

    this.log('Disconnecting...');

    // Close readline interface
    if (this.rl) {
      this.rl.close();
      this.rl = null;
    }

    // Kill process
    if (this.process) {
      this.process.kill('SIGTERM');
      
      // Wait for graceful exit, force kill after 5s
      await new Promise<void>((resolve) => {
        const forceKillTimeout = setTimeout(() => {
          if (this.process && !this.process.killed) {
            this.log('Force killing process...');
            this.process.kill('SIGKILL');
          }
          resolve();
        }, 5000);

        if (this.process) {
          this.process.on('exit', () => {
            clearTimeout(forceKillTimeout);
            resolve();
          });
        } else {
          clearTimeout(forceKillTimeout);
          resolve();
        }
      });

      this.process = null;
    }

    // Clear pending requests
    for (const [id, pending] of this.pendingRequests.entries()) {
      clearTimeout(pending.timeout);
      pending.reject(new Error('Client disconnected'));
      this.pendingRequests.delete(id);
    }

    this.connected = false;
    this.initialized = false;

    this.log('Disconnected');
  }

  /**
   * Get server information
   */
  getServerInfo(): { name: string; version: string } | null {
    return this.serverInfo;
  }

  /**
   * Get server capabilities
   */
  getServerCapabilities(): any {
    return this.serverCapabilities;
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.connected && this.initialized;
  }

  /**
   * Async iterator support for use with for-await-of
   */
  async *[Symbol.asyncIterator]() {
    await this.connect();
    try {
      yield this;
    } finally {
      await this.disconnect();
    }
  }
}

/**
 * Helper function to use client with automatic cleanup
 * 
 * @example
 * ```typescript
 * await withStdioClient(
 *   { command: 'npx @playwright/mcp' },
 *   async (client) => {
 *     const tools = await client.listTools();
 *     console.log('Tools:', tools);
 *     
 *     const result = await client.callTool('navigate', {
 *       url: 'https://example.com'
 *     });
 *   }
 * );
 * ```
 */
export async function withStdioClient<T>(
  options: StdioClientOptions,
  fn: (client: MCPStdioClient) => Promise<T>
): Promise<T> {
  const client = new MCPStdioClient(options);
  await client.connect();

  try {
    return await fn(client);
  } finally {
    await client.disconnect();
  }
}

/**
 * Create a connection pool for multiple client connections
 * Useful for load balancing and redundancy
 */
export class StdioClientPool {
  private clients: MCPStdioClient[] = [];
  private currentIndex: number = 0;
  private options: StdioClientOptions;
  private poolSize: number;

  constructor(options: StdioClientOptions, poolSize: number = 3) {
    this.options = options;
    this.poolSize = poolSize;
  }

  /**
   * Initialize all clients in pool
   */
  async initialize(): Promise<void> {
    const promises = [];
    
    for (let i = 0; i < this.poolSize; i++) {
      const client = new MCPStdioClient(this.options);
      this.clients.push(client);
      promises.push(client.connect());
    }

    await Promise.all(promises);
  }

  /**
   * Get next available client (round-robin)
   */
  getClient(): MCPStdioClient {
    if (this.clients.length === 0) {
      throw new Error('Pool not initialized. Call initialize() first.');
    }

    const client = this.clients[this.currentIndex];
    this.currentIndex = (this.currentIndex + 1) % this.clients.length;
    return client;
  }

  /**
   * Execute function with automatic client selection
   */
  async execute<T>(fn: (client: MCPStdioClient) => Promise<T>): Promise<T> {
    const client = this.getClient();
    return await fn(client);
  }

  /**
   * Disconnect all clients
   */
  async shutdown(): Promise<void> {
    await Promise.all(this.clients.map(c => c.disconnect()));
    this.clients = [];
  }
}
