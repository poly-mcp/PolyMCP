/**
 * PolyMCP Types - Complete type definitions
 * 
 * This module contains all TypeScript type definitions used throughout the library.
 */

import { z } from 'zod';

// ============================================================================
// Tool Types
// ============================================================================

/**
 * MCP Tool Definition
 */
export interface MCPTool {
  name: string;
  description: string;
  inputSchema: z.ZodSchema<any> | Record<string, any>;
  outputSchema?: z.ZodSchema<any> | Record<string, any>;
}

/**
 * Tool metadata for MCP protocol
 */
export interface MCPToolMetadata {
  name: string;
  description: string;
  input_schema: Record<string, any>;
  output_schema?: Record<string, any>;
}

/**
 * Tool invocation result
 */
export interface ToolResult {
  status: 'success' | 'error';
  result?: any;
  error?: string;
  details?: any;
  executionTime?: number;
}

/**
 * Tool registry entry
 */
export interface ToolRegistryEntry {
  metadata: MCPToolMetadata;
  function: Function;
  inputSchema: z.ZodSchema<any>;
  outputSchema?: z.ZodSchema<any>;
  isAsync: boolean;
}

/**
 * Tool with server metadata
 */
export interface ToolWithServer extends MCPToolMetadata {
  _server_url?: string;
  _server_id?: string;
  _server_type?: 'http' | 'stdio' | 'inprocess';
  _parameters?: Record<string, any>;
  _reasoning?: string;
}

/**
 * Tool selection decision
 */
export interface ToolSelection {
  tool_index: number;
  tool_name: string;
  parameters: Record<string, any>;
  reasoning: string;
}

/**
 * Tool execution context
 */
export interface ToolExecutionContext {
  serverUrl?: string;
  serverId?: string;
  serverType: 'http' | 'stdio' | 'inprocess';
  parameters: Record<string, any>;
  timeout?: number;
}

// ============================================================================
// Server Types
// ============================================================================

/**
 * MCP Server configuration
 */
export interface MCPServerConfig {
  url?: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  timeout?: number;
  retries?: number;
}

/**
 * Stdio server configuration
 */
export interface StdioServerConfig {
  command: string;
  args: string[];
  env?: Record<string, string>;
  cwd?: string;
  timeout?: number;
}

/**
 * HTTP server configuration
 */
export interface HttpServerConfig {
  url: string;
  auth?: AuthConfig;
  timeout?: number;
  retries?: number;
  headers?: Record<string, string>;
}

/**
 * In-process server statistics
 */
export interface ServerStats {
  totalExecutions: number;
  totalErrors: number;
  successRate: number;
  averageExecutionTime: number;
  lastExecutionTime?: number;
}

/**
 * Server registry entry
 */
export interface ServerRegistryEntry {
  id: string;
  type: 'http' | 'stdio' | 'inprocess';
  config: MCPServerConfig | StdioServerConfig | HttpServerConfig;
  tools: Map<string, ToolRegistryEntry>;
  stats: ServerStats;
  connected: boolean;
}

// ============================================================================
// MCP Protocol Types
// ============================================================================

/**
 * MCP list tools response
 */
export interface MCPListToolsResponse {
  tools: MCPToolMetadata[];
}

/**
 * JSON-RPC request
 */
export interface JsonRpcRequest {
  jsonrpc: '2.0';
  id: number | string;
  method: string;
  params?: Record<string, any>;
}

/**
 * JSON-RPC response
 */
export interface JsonRpcResponse {
  jsonrpc: '2.0';
  id: number | string;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

/**
 * JSON-RPC error codes
 */
export enum JsonRpcErrorCode {
  ParseError = -32700,
  InvalidRequest = -32600,
  MethodNotFound = -32601,
  InvalidParams = -32602,
  InternalError = -32603,
}

// ============================================================================
// Agent Types
// ============================================================================

/**
 * Agent action history
 */
export interface AgentAction {
  step: number;
  tool: string;
  parameters: Record<string, any>;
  reasoning: string;
  result: ToolResult;
  timestamp: Date;
}

/**
 * Continuation decision
 */
export interface ContinuationDecision {
  continue: boolean;
  reason: string;
}

/**
 * Agent configuration
 */
export interface AgentConfig {
  maxSteps?: number;
  timeout?: number;
  verbose?: boolean;
  enableHistory?: boolean;
}

/** Backward-compatible alias for agent configuration. */
export type AgentOptions = AgentConfig;

/**
 * Agent response
 */
export interface AgentResponse {
  answer: string;
  actions: AgentAction[];
  success: boolean;
  error?: string;
  metadata?: Record<string, any>;
}

// ============================================================================
// Code Execution Types
// ============================================================================

/**
 * Code execution result
 */
export interface ExecutionResult {
  success: boolean;
  output: string;
  error?: string;
  executionTime: number;
  returnValue?: any;
  exitCode?: number;
}

/**
 * Code execution context
 */
export interface ExecutionContext {
  language: string;
  code: string;
  timeout?: number;
  env?: Record<string, string>;
  cwd?: string;
}

// ============================================================================
// LLM Types
// ============================================================================

/**
 * LLM Provider interface
 */
export interface LLMProvider {
  generate(prompt: string, options?: LLMGenerationOptions): Promise<string>;
  generateStream?(prompt: string, options?: LLMGenerationOptions): AsyncIterable<string>;
}

/**
 * LLM Provider configuration
 */
export interface LLMConfig {
  apiKey?: string;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  baseUrl?: string;
  timeout?: number;
}

/**
 * LLM generation options
 */
export interface LLMGenerationOptions {
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  topK?: number;
  stopSequences?: string[];
  systemPrompt?: string;
  stream?: boolean;
}

/**
 * LLM message
 */
export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

// ============================================================================
// Authentication Types
// ============================================================================

/**
 * Authentication configuration
 */
export interface AuthConfig {
  type: 'none' | 'api_key' | 'jwt' | 'basic' | 'oauth';
  apiKey?: string;
  jwtSecret?: string;
  jwtExpiration?: string;
  username?: string;
  password?: string;
  oauthConfig?: OAuthConfig;
}

/**
 * OAuth configuration
 */
export interface OAuthConfig {
  clientId: string;
  clientSecret: string;
  authUrl: string;
  tokenUrl: string;
  redirectUri: string;
  scopes?: string[];
}

/**
 * JWT payload
 */
export interface JWTPayload {
  sub: string;
  iat: number;
  exp: number;
  iss?: string;
  aud?: string;
  [key: string]: any;
}

/**
 * API key configuration
 */
export interface ApiKeyConfig {
  key: string;
  name?: string;
  permissions?: string[];
  expiresAt?: Date;
}

// ============================================================================
// Validation Types
// ============================================================================

/**
 * Validation result
 */
export interface ValidationResult {
  valid: boolean;
  errors: ValidationErrorDetail[];
}

/**
 * Validation error detail
 */
export interface ValidationErrorDetail {
  path: string;
  message: string;
  code: string;
}

/**
 * Validation options
 */
export interface ValidationOptions {
  strict?: boolean;
  coerce?: boolean;
  stripUnknown?: boolean;
}

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Library configuration
 */
export interface PolyMCPConfig {
  defaultTimeout?: number;
  defaultRetries?: number;
  logLevel?: 'error' | 'warn' | 'info' | 'debug' | 'trace';
  auth?: AuthConfig;
  llm?: LLMConfig;
  agent?: AgentConfig;
}

/**
 * Server options for expose_tools
 */
export interface ServerOptions {
  port?: number;
  host?: string;
  auth?: AuthConfig;
  cors?: boolean;
  corsOrigin?: string | string[];
  rateLimit?: RateLimitConfig;
}

/**
 * Rate limit configuration
 */
export interface RateLimitConfig {
  windowMs: number;
  maxRequests: number;
  message?: string;
}

// ============================================================================
// Utility Types
// ============================================================================

/**
 * Async function type
 */
export type AsyncFunction<T = any> = (...args: any[]) => Promise<T>;

/**
 * Sync or async function type
 */
export type MaybePromise<T> = T | Promise<T>;

/**
 * Partial deep type
 */
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

/**
 * Make some properties required
 */
export type RequireProps<T, K extends keyof T> = T & Required<Pick<T, K>>;

/**
 * Make some properties optional
 */
export type OptionalProps<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;
