/**
 * JSON-RPC Support
 * 
 * Generic JSON-RPC 2.0 protocol implementation:
 * - Request/response handling
 * - Method invocation
 * - Error handling
 * - Batch requests
 * - Notification support
 */

/**
 * JSON-RPC 2.0 error codes
 */
export enum JSONRPCErrorCode {
  PARSE_ERROR = -32700,
  INVALID_REQUEST = -32600,
  METHOD_NOT_FOUND = -32601,
  INVALID_PARAMS = -32602,
  INTERNAL_ERROR = -32603,
}

/**
 * JSON-RPC 2.0 error
 */
export interface JSONRPCError {
  code: number;
  message: string;
  data?: any;
}

/**
 * JSON-RPC 2.0 request
 */
export interface JSONRPCRequest {
  jsonrpc: '2.0';
  method: string;
  params?: any[] | Record<string, any>;
  id?: string | number | null;
}

/**
 * JSON-RPC 2.0 response
 */
export interface JSONRPCResponse {
  jsonrpc: '2.0';
  result?: any;
  error?: JSONRPCError;
  id: string | number | null;
}

/**
 * JSON-RPC method handler
 */
export type JSONRPCMethodHandler = (params?: any) => Promise<any> | any;

/**
 * JSON-RPC Client.
 * 
 * Generic client for JSON-RPC 2.0 protocol.
 * Can be used to communicate with any JSON-RPC server.
 * 
 * Features:
 * - Standard JSON-RPC 2.0 compliance
 * - Request/response handling
 * - Error handling
 * - Batch requests
 * - Notification support (no id)
 * - Automatic request ID generation
 * 
 * Example:
 * ```typescript
 * const client = new JSONRPCClient('https://rpc.example.com');
 * 
 * // Call a method
 * const result = await client.call('get_user', { id: 123 });
 * console.log(result);
 * 
 * // Send notification (no response expected)
 * await client.notify('log_event', { event: 'user_login' });
 * 
 * // Batch requests
 * const results = await client.batch([
 *   { method: 'get_user', params: { id: 1 } },
 *   { method: 'get_user', params: { id: 2 } }
 * ]);
 * ```
 */
export class JSONRPCClient {
  private endpoint: string;
  private requestId: number = 1;
  private headers: Record<string, string>;

  constructor(
    endpoint: string,
    headers: Record<string, string> = {}
  ) {
    this.endpoint = endpoint;
    this.headers = {
      'Content-Type': 'application/json',
      ...headers,
    };
  }

  /**
   * Call a JSON-RPC method
   */
  async call(method: string, params?: any[] | Record<string, any>): Promise<any> {
    const request: JSONRPCRequest = {
      jsonrpc: '2.0',
      method,
      params,
      id: this.getNextId(),
    };

    const response = await this.sendRequest(request);

    if (response.error) {
      throw new JSONRPCClientError(response.error);
    }

    return response.result;
  }

  /**
   * Send notification (no response expected)
   */
  async notify(method: string, params?: any[] | Record<string, any>): Promise<void> {
    const request: JSONRPCRequest = {
      jsonrpc: '2.0',
      method,
      params,
      // No id for notifications
    };

    await this.sendRequest(request);
  }

  /**
   * Batch requests
   */
  async batch(
    requests: Array<{ method: string; params?: any[] | Record<string, any> }>
  ): Promise<any[]> {
    const batchRequests: JSONRPCRequest[] = requests.map(req => ({
      jsonrpc: '2.0',
      method: req.method,
      params: req.params,
      id: this.getNextId(),
    }));

    const responses = await this.sendBatchRequest(batchRequests);

    // Check for errors
    const results: any[] = [];
    for (const response of responses) {
      if (response.error) {
        throw new JSONRPCClientError(response.error);
      }
      results.push(response.result);
    }

    return results;
  }

  /**
   * Send single request
   */
  private async sendRequest(request: JSONRPCRequest): Promise<JSONRPCResponse> {
    const response = await fetch(this.endpoint, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json() as JSONRPCResponse;
  }

  /**
   * Send batch request
   */
  private async sendBatchRequest(requests: JSONRPCRequest[]): Promise<JSONRPCResponse[]> {
    const response = await fetch(this.endpoint, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(requests),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json() as JSONRPCResponse[];
  }

  /**
   * Get next request ID
   */
  private getNextId(): number {
    return this.requestId++;
  }

  /**
   * Update headers
   */
  setHeaders(headers: Record<string, string>): void {
    this.headers = {
      ...this.headers,
      ...headers,
    };
  }
}

/**
 * JSON-RPC Server.
 * 
 * Generic server for JSON-RPC 2.0 protocol.
 * Can be used to expose methods via JSON-RPC.
 * 
 * Features:
 * - Method registration
 * - Request validation
 * - Error handling
 * - Batch request support
 * - Notification handling
 * 
 * Example:
 * ```typescript
 * const server = new JSONRPCServer();
 * 
 * // Register methods
 * server.registerMethod('add', (params: any) => {
 *   return params.a + params.b;
 * });
 * 
 * server.registerMethod('get_user', async (params: any) => {
 *   return await fetchUser(params.id);
 * });
 * 
 * // Handle request
 * const response = await server.handleRequest({
 *   jsonrpc: '2.0',
 *   method: 'add',
 *   params: { a: 5, b: 3 },
 *   id: 1
 * });
 * 
 * console.log(response.result); // 8
 * ```
 */
export class JSONRPCServer {
  private methods: Map<string, JSONRPCMethodHandler> = new Map();

  /**
   * Register a method
   */
  registerMethod(name: string, handler: JSONRPCMethodHandler): void {
    this.methods.set(name, handler);
  }

  /**
   * Unregister a method
   */
  unregisterMethod(name: string): void {
    this.methods.delete(name);
  }

  /**
   * Check if method exists
   */
  hasMethod(name: string): boolean {
    return this.methods.has(name);
  }

  /**
   * Handle incoming request
   */
  async handleRequest(request: any): Promise<JSONRPCResponse | JSONRPCResponse[]> {
    // Check if batch request
    if (Array.isArray(request)) {
      return await this.handleBatchRequest(request);
    }

    return await this.handleSingleRequest(request);
  }

  /**
   * Handle single request
   */
  private async handleSingleRequest(request: any): Promise<JSONRPCResponse> {
    // Validate request
    const validation = this.validateRequest(request);
    if (!validation.valid) {
      return this.createErrorResponse(
        validation.error!.code,
        validation.error!.message,
        request.id || null
      );
    }

    const rpcRequest = request as JSONRPCRequest;

    // Check if method exists
    if (!this.hasMethod(rpcRequest.method)) {
      return this.createErrorResponse(
        JSONRPCErrorCode.METHOD_NOT_FOUND,
        `Method '${rpcRequest.method}' not found`,
        rpcRequest.id || null
      );
    }

    // Execute method
    try {
      const handler = this.methods.get(rpcRequest.method)!;
      const result = await handler(rpcRequest.params);

      // Don't send response for notifications
      if (rpcRequest.id === undefined) {
        return null as any;
      }

      return this.createSuccessResponse(result, rpcRequest.id || null);
    } catch (error: any) {
      return this.createErrorResponse(
        JSONRPCErrorCode.INTERNAL_ERROR,
        error.message || 'Internal error',
        rpcRequest.id || null,
        { stack: error.stack }
      );
    }
  }

  /**
   * Handle batch request
   */
  private async handleBatchRequest(requests: any[]): Promise<JSONRPCResponse[]> {
    const responses: JSONRPCResponse[] = [];

    for (const request of requests) {
      const response = await this.handleSingleRequest(request);
      // Only add non-null responses (notifications return null)
      if (response !== null) {
        responses.push(response);
      }
    }

    return responses;
  }

  /**
   * Validate request format
   */
  private validateRequest(request: any): { valid: boolean; error?: JSONRPCError } {
    if (typeof request !== 'object' || request === null) {
      return {
        valid: false,
        error: {
          code: JSONRPCErrorCode.INVALID_REQUEST,
          message: 'Request must be an object',
        },
      };
    }

    if (request.jsonrpc !== '2.0') {
      return {
        valid: false,
        error: {
          code: JSONRPCErrorCode.INVALID_REQUEST,
          message: 'jsonrpc must be "2.0"',
        },
      };
    }

    if (typeof request.method !== 'string') {
      return {
        valid: false,
        error: {
          code: JSONRPCErrorCode.INVALID_REQUEST,
          message: 'method must be a string',
        },
      };
    }

    return { valid: true };
  }

  /**
   * Create success response
   */
  private createSuccessResponse(result: any, id: string | number | null): JSONRPCResponse {
    return {
      jsonrpc: '2.0',
      result,
      id,
    };
  }

  /**
   * Create error response
   */
  private createErrorResponse(
    code: number,
    message: string,
    id: string | number | null,
    data?: any
  ): JSONRPCResponse {
    return {
      jsonrpc: '2.0',
      error: {
        code,
        message,
        data,
      },
      id,
    };
  }

  /**
   * Get registered methods
   */
  getMethods(): string[] {
    return Array.from(this.methods.keys());
  }

  /**
   * Clear all methods
   */
  clearMethods(): void {
    this.methods.clear();
  }
}

/**
 * JSON-RPC Client Error
 */
export class JSONRPCClientError extends Error {
  code: number;
  data?: any;

  constructor(error: JSONRPCError) {
    super(error.message);
    this.name = 'JSONRPCClientError';
    this.code = error.code;
    this.data = error.data;
  }
}

/**
 * Utility to check if tool uses JSON-RPC
 */
export function isJSONRPCTool(tool: any): boolean {
  // Check if tool metadata indicates JSON-RPC
  return (
    tool._protocol === 'jsonrpc' ||
    tool._server_type === 'jsonrpc' ||
    tool.protocol === 'jsonrpc'
  );
}

/**
 * Execute JSON-RPC tool
 */
export async function executeJSONRPCTool(
  serverUrl: string,
  toolName: string,
  parameters: Record<string, any>,
  headers?: Record<string, string>
): Promise<any> {
  const client = new JSONRPCClient(serverUrl, headers);
  return await client.call(toolName, parameters);
}

/**
 * JSON-RPC Factory
 */
export class JSONRPCFactory {
  /**
   * Create client for endpoint
   */
  static createClient(endpoint: string, headers?: Record<string, string>): JSONRPCClient {
    return new JSONRPCClient(endpoint, headers);
  }

  /**
   * Create server
   */
  static createServer(): JSONRPCServer {
    return new JSONRPCServer();
  }

  /**
   * Create server with methods
   */
  static createServerWithMethods(
    methods: Record<string, JSONRPCMethodHandler>
  ): JSONRPCServer {
    const server = new JSONRPCServer();
    
    for (const [name, handler] of Object.entries(methods)) {
      server.registerMethod(name, handler);
    }
    
    return server;
  }
}
