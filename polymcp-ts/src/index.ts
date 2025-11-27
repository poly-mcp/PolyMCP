/**
 * PolyMCP - Model Context Protocol Library for TypeScript
 * 
 * Production-ready TypeScript library for building MCP servers and agents.
 * 
 * @packageDocumentation
 */

// Version
export { VERSION, getVersion, isCompatible } from './version';
import { VERSION } from './version';

// Types
export * from './types';

// Errors (export specific to avoid conflicts)
export {
  PolyMCPError,
  ToolNotFoundError,
  ToolExecutionError,
  ToolValidationError,
  ServerConnectionError,
  AuthenticationError,
  AuthorizationError,
  ConfigurationError,
  ValidationError,
  TimeoutError,
  LLMError,
  AgentExecutionError,
} from './errors';

// Constants
export * from './constants';

// Agent Module
export * from './agent';

// Toolkit Module
export * from './toolkit';

// Stdio Module
export * from './stdio';

// Auth Module
export * from './auth';

// Registry Module
export * from './registry';

// Validation Module
export * from './validation';

// Config Module
export * from './config';

// ============================================================================
// Re-export commonly used items for convenience
// ============================================================================

import { tool, createToolMetadata } from './toolkit/tool-helpers';
import { ServerRegistry, getGlobalRegistry } from './registry';
import { ConfigManager, getGlobalConfig } from './config';
import { AuthManager, createAuthManager } from './auth';

export {
  // Tool helpers
  tool,
  createToolMetadata,
  
  // Registry
  ServerRegistry,
  getGlobalRegistry,
  
  // Config
  ConfigManager,
  getGlobalConfig,
  
  // Auth
  AuthManager,
  createAuthManager,
};

// Default export
const polymcp = {
  VERSION,
  tool,
  createToolMetadata,
  ServerRegistry,
  getGlobalRegistry,
  ConfigManager,
  getGlobalConfig,
  AuthManager,
  createAuthManager,
};

export default polymcp;
