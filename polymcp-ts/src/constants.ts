/**
 * Constants for PolyMCP
 * 
 * This module contains all constant values used throughout the library.
 */

/**
 * Default timeout values (in milliseconds)
 */
export const TIMEOUTS = {
  DEFAULT: 30000,
  LLM_GENERATION: 60000,
  TOOL_EXECUTION: 30000,
  STDIO_STARTUP: 5000,
  AGENT_STEP: 120000,
  HTTP_REQUEST: 30000,
} as const;

/**
 * HTTP headers
 */
export const HTTP_HEADERS = {
  CONTENT_TYPE: 'Content-Type',
  AUTHORIZATION: 'Authorization',
  USER_AGENT: 'User-Agent',
  ACCEPT: 'Accept',
  API_KEY: 'X-API-Key',
} as const;

/**
 * Content types
 */
export const CONTENT_TYPES = {
  JSON: 'application/json',
  TEXT: 'text/plain',
  HTML: 'text/html',
  FORM: 'application/x-www-form-urlencoded',
} as const;

/**
 * MCP protocol constants
 */
export const MCP = {
  VERSION: '1.0.0',
  JSONRPC_VERSION: '2.0',
  
  METHODS: {
    LIST_TOOLS: 'tools/list',
    INVOKE_TOOL: 'tools/call',
    LIST_RESOURCES: 'resources/list',
    READ_RESOURCE: 'resources/read',
    LIST_PROMPTS: 'prompts/list',
    GET_PROMPT: 'prompts/get',
  } as const,
  
  ENDPOINTS: {
    LIST_TOOLS: '/mcp/list_tools',
    INVOKE_TOOL: '/mcp/invoke',
    HEALTH: '/health',
    ROOT: '/',
  } as const,
} as const;

/**
 * Agent types
 */
export const AGENT_TYPES = {
  BASIC: 'basic',
  CODE_MODE: 'codemode',
  UNIFIED: 'unified',
} as const;

/**
 * LLM providers
 */
export const LLM_PROVIDERS = {
  OPENAI: 'openai',
  ANTHROPIC: 'anthropic',
  OLLAMA: 'ollama',
  KIMI: 'kimi',
  DEEPSEEK: 'deepseek',
} as const;

/**
 * Default LLM models
 */
export const DEFAULT_MODELS = {
  OPENAI: 'gpt-4-turbo-preview',
  ANTHROPIC: 'claude-3-5-sonnet-20241022',
  OLLAMA: 'llama2',
  KIMI: 'moonshot-v1-8k',
  DEEPSEEK: 'deepseek-chat',
} as const;

/**
 * LLM API endpoints
 */
export const LLM_ENDPOINTS = {
  OPENAI: 'https://api.openai.com/v1',
  ANTHROPIC: 'https://api.anthropic.com/v1',
  OLLAMA: 'http://localhost:11434/api',
  KIMI: 'https://api.moonshot.cn/v1',
  DEEPSEEK: 'https://api.deepseek.com/v1',
} as const;

/**
 * Authentication types
 */
export const AUTH_TYPES = {
  NONE: 'none',
  API_KEY: 'api_key',
  JWT: 'jwt',
  BASIC: 'basic',
  OAUTH: 'oauth',
} as const;

/**
 * JWT Configuration defaults
 */
export const JWT_DEFAULTS = {
  ALGORITHM: 'HS256' as const,
  EXPIRATION: '24h',
  ISSUER: 'polymcp',
} as const;

/**
 * Server registry defaults
 */
export const REGISTRY_DEFAULTS = {
  MAX_SERVERS: 100,
  MAX_TOOLS_PER_SERVER: 1000,
} as const;

/**
 * Validation defaults
 */
export const VALIDATION_DEFAULTS = {
  MAX_STRING_LENGTH: 10000,
  MAX_ARRAY_LENGTH: 1000,
  MAX_OBJECT_DEPTH: 10,
} as const;

/**
 * Logging levels
 */
export const LOG_LEVELS = {
  ERROR: 'error',
  WARN: 'warn',
  INFO: 'info',
  DEBUG: 'debug',
  TRACE: 'trace',
} as const;

/**
 * Default ports
 */
export const DEFAULT_PORTS = {
  HTTP: 3000,
  HTTPS: 3443,
} as const;

/**
 * Environment variables
 */
export const ENV_VARS = {
  NODE_ENV: 'NODE_ENV',
  PORT: 'PORT',
  LOG_LEVEL: 'LOG_LEVEL',
  
  // LLM API Keys
  OPENAI_API_KEY: 'OPENAI_API_KEY',
  ANTHROPIC_API_KEY: 'ANTHROPIC_API_KEY',
  KIMI_API_KEY: 'KIMI_API_KEY',
  DEEPSEEK_API_KEY: 'DEEPSEEK_API_KEY',
  
  // Auth
  JWT_SECRET: 'JWT_SECRET',
  API_KEY: 'API_KEY',
} as const;

/**
 * File extensions
 */
export const FILE_EXTENSIONS = {
  TYPESCRIPT: '.ts',
  JAVASCRIPT: '.js',
  JSON: '.json',
  YAML: '.yaml',
  YML: '.yml',
} as const;

/**
 * Status codes
 */
export const STATUS_CODES = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  TIMEOUT: 408,
  INTERNAL_SERVER_ERROR: 500,
  SERVICE_UNAVAILABLE: 503,
} as const;

/**
 * Retry configuration
 */
export const RETRY_DEFAULTS = {
  MAX_RETRIES: 3,
  INITIAL_DELAY: 1000,
  MAX_DELAY: 10000,
  BACKOFF_FACTOR: 2,
} as const;
