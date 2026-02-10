/**
 * Dual Mode MCP Server - PRODUCTION IMPLEMENTATION
 * Expose tools via both HTTP and stdio simultaneously.
 * 
 * Features:
 * - Single tool registry shared between modes
 * - Independent HTTP and stdio servers
 * - Unified statistics tracking
 * - Graceful shutdown handling
 */

import { Express } from 'express';
import { MCPTool } from './types';
import { exposeToolsHttp } from './toolkit/expose';
import { StdioMCPServer } from './expose_tools_stdio';

/**
 * Dual mode server options
 */
export interface DualModeOptions {
  name?: string;
  version?: string;
  http?: {
    enabled?: boolean;
    port?: number;
    title?: string;
    description?: string;
  };
  stdio?: {
    enabled?: boolean;
  };
  verbose?: boolean;
}

/**
 * Dual mode server statistics
 */
interface DualModeStats {
  http: {
    enabled: boolean;
    requests: number;
    port?: number;
  };
  stdio: {
    enabled: boolean;
    requests: number;
  };
  tools: number;
  uptime: number;
}

/**
 * Production dual-mode MCP server.
 * 
 * Exposes tools via both HTTP (Express) and stdio (JSON-RPC) simultaneously,
 * allowing flexible access patterns for different clients.
 * 
 * Example:
 * ```typescript
 * import { tool, DualModeMCPServer } from 'polymcp';
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
 * const server = new DualModeMCPServer([greet], {
 *   http: { port: 8000 },
 *   stdio: { enabled: true },
 *   verbose: true
 * });
 * 
 * await server.start();
 * ```
 */
export class DualModeMCPServer {
  private tools: MCPTool[];
  private options: {
    name: string;
    version: string;
    http: {
      enabled: boolean;
      port: number;
      title: string;
      description: string;
    };
    stdio: {
      enabled: boolean;
    };
    verbose: boolean;
  };
  
  // Servers
  private httpServer: Express | null = null;
  private stdioServer: StdioMCPServer | null = null;
  private httpHandle: any = null;
  
  // State
  private running: boolean = false;
  private startTime: number = 0;
  
  // Statistics
  private stats: DualModeStats;

  constructor(tools: MCPTool[], options: DualModeOptions = {}) {
    if (!tools || tools.length === 0) {
      throw new Error('At least one tool must be provided');
    }

    this.tools = tools;
    
    // Default options
    this.options = {
      name: options.name || 'PolyMCP Dual Mode Server',
      version: options.version || '1.0.0',
      http: {
        enabled: options.http?.enabled !== false,
        port: options.http?.port || 8000,
        title: options.http?.title || 'PolyMCP Dual Mode Server',
        description: options.http?.description || 'MCP server exposing tools via HTTP and stdio',
      },
      stdio: {
        enabled: options.stdio?.enabled !== false,
      },
      verbose: options.verbose || false,
    };

    // Initialize stats
    this.stats = {
      http: {
        enabled: this.options.http.enabled,
        requests: 0,
        port: this.options.http.enabled ? this.options.http.port : undefined,
      },
      stdio: {
        enabled: this.options.stdio.enabled,
        requests: 0,
      },
      tools: tools.length,
      uptime: 0,
    };
  }

  /**
   * Start dual mode server
   */
  async start(): Promise<void> {
    if (this.running) {
      throw new Error('Server is already running');
    }

    this.log('🚀 Starting Dual Mode MCP Server...\n');
    this.log(`   Name: ${this.options.name}`);
    this.log(`   Tools: ${this.tools.length}`);
    this.log('');

    this.startTime = Date.now();

    // Start HTTP server if enabled
    if (this.options.http.enabled) {
      await this.startHttp();
    }

    // Start stdio server if enabled
    if (this.options.stdio.enabled) {
      this.startStdio();
    }

    this.running = true;

    this.log('');
    this.log('✅ Dual Mode Server is ready!');
    
    if (this.options.http.enabled) {
      this.log(`   HTTP: http://localhost:${this.options.http.port}`);
      this.log(`   Docs: http://localhost:${this.options.http.port}/docs`);
    }
    
    if (this.options.stdio.enabled) {
      this.log('   Stdio: listening on stdin/stdout');
    }
    
    this.log('');

    // Setup graceful shutdown
    this.setupShutdown();
  }

  /**
   * Start HTTP server
   */
  private async startHttp(): Promise<void> {
    this.log('📡 Starting HTTP server...');

    this.httpServer = exposeToolsHttp(this.tools, {
      title: this.options.http.title,
      description: this.options.http.description,
      version: this.options.version,
      verbose: this.options.verbose,
    });

    // Add custom endpoints
    this.httpServer.get('/stats', (_req, res) => {
      this.stats.uptime = Date.now() - this.startTime;
      res.json(this.stats);
    });

    this.httpServer.get('/health', (_req, res) => {
      res.json({
        status: 'healthy',
        modes: {
          http: this.options.http.enabled,
          stdio: this.options.stdio.enabled,
        },
        uptime: Date.now() - this.startTime,
      });
    });

    // Start listening
    await new Promise<void>((resolve, reject) => {
      this.httpHandle = this.httpServer!.listen(
        this.options.http.port,
        () => {
          this.log(`   ✓ HTTP server listening on port ${this.options.http.port}`);
          resolve();
        }
      ).on('error', reject);
    });
  }

  /**
   * Start stdio server
   */
  private startStdio(): void {
    this.log('🔌 Starting stdio server...');

    this.stdioServer = new StdioMCPServer(this.tools, {
      name: this.options.name,
      version: this.options.version,
      verbose: this.options.verbose,
    });

    // Run in background (non-blocking)
    setImmediate(() => {
      this.stdioServer!.run();
    });

    this.log('   ✓ Stdio server ready');
  }

  /**
   * Setup graceful shutdown handlers
   */
  private setupShutdown(): void {
    const shutdown = async () => {
      this.log('\n🛑 Shutting down gracefully...');
      await this.stop();
      process.exit(0);
    };

    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
  }

  /**
   * Stop dual mode server
   */
  async stop(): Promise<void> {
    if (!this.running) {
      return;
    }

    this.log('Stopping servers...');

    // Stop HTTP server
    if (this.httpHandle) {
      await new Promise<void>((resolve) => {
        this.httpHandle.close(() => {
          this.log('   ✓ HTTP server stopped');
          resolve();
        });
      });
      this.httpHandle = null;
      this.httpServer = null;
    }

    // Stdio server will stop when process exits
    this.stdioServer = null;

    this.running = false;
    this.log('✅ Servers stopped');
  }

  /**
   * Get server statistics
   */
  getStats(): DualModeStats {
    this.stats.uptime = this.running ? Date.now() - this.startTime : 0;
    
    // Update from actual servers
    if (this.httpServer) {
      // HTTP stats would be tracked via middleware
    }
    
    if (this.stdioServer) {
      const stdioStats = this.stdioServer.getStats();
      this.stats.stdio.requests = stdioStats.requestsReceived;
    }

    return { ...this.stats };
  }

  /**
   * Check if server is running
   */
  isRunning(): boolean {
    return this.running;
  }

  /**
   * Log helper
   */
  private log(message: string): void {
    if (this.options.verbose) {
      console.log(message);
    }
  }
}

/**
 * Helper function to create and start dual mode server
 */
export async function exposeDualMode(
  tools: MCPTool[],
  options?: DualModeOptions
): Promise<DualModeMCPServer> {
  const server = new DualModeMCPServer(tools, options);
  await server.start();
  return server;
}

/**
 * Helper function to run dual mode server (blocking)
 */
export async function runDualMode(
  tools: MCPTool[],
  options?: DualModeOptions
): Promise<void> {
  const server = new DualModeMCPServer(tools, options);
  await server.start();

  // Keep process alive
  await new Promise(() => {
    // Never resolves - server runs until SIGINT/SIGTERM
  });
}
