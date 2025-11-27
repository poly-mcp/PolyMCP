/**
 * Custom Error Classes for PolyMCP
 * 
 * This module defines all custom error types used throughout the library.
 */

/**
 * Base error class for all PolyMCP errors
 */
export class PolyMCPError extends Error {
  constructor(message: string, public readonly code?: string) {
    super(message);
    this.name = 'PolyMCPError';
    Object.setPrototypeOf(this, PolyMCPError.prototype);
  }
}

/**
 * Error thrown when a tool is not found
 */
export class ToolNotFoundError extends PolyMCPError {
  constructor(toolName: string) {
    super(`Tool not found: ${toolName}`, 'TOOL_NOT_FOUND');
    this.name = 'ToolNotFoundError';
    Object.setPrototypeOf(this, ToolNotFoundError.prototype);
  }
}

/**
 * Error thrown when tool execution fails
 */
export class ToolExecutionError extends PolyMCPError {
  constructor(
    toolName: string,
    public readonly originalError: Error
  ) {
    super(`Tool execution failed: ${toolName} - ${originalError.message}`, 'TOOL_EXECUTION_ERROR');
    this.name = 'ToolExecutionError';
    Object.setPrototypeOf(this, ToolExecutionError.prototype);
  }
}

/**
 * Error thrown when tool validation fails
 */
export class ToolValidationError extends PolyMCPError {
  constructor(message: string) {
    super(message, 'TOOL_VALIDATION_ERROR');
    this.name = 'ToolValidationError';
    Object.setPrototypeOf(this, ToolValidationError.prototype);
  }
}

/**
 * Error thrown when server connection fails
 */
export class ServerConnectionError extends PolyMCPError {
  constructor(serverName: string, public readonly originalError?: Error) {
    const msg = originalError
      ? `Failed to connect to server: ${serverName} - ${originalError.message}`
      : `Failed to connect to server: ${serverName}`;
    super(msg, 'SERVER_CONNECTION_ERROR');
    this.name = 'ServerConnectionError';
    Object.setPrototypeOf(this, ServerConnectionError.prototype);
  }
}

/**
 * Error thrown when authentication fails
 */
export class AuthenticationError extends PolyMCPError {
  constructor(message: string) {
    super(message, 'AUTHENTICATION_ERROR');
    this.name = 'AuthenticationError';
    Object.setPrototypeOf(this, AuthenticationError.prototype);
  }
}

/**
 * Error thrown when authorization fails
 */
export class AuthorizationError extends PolyMCPError {
  constructor(message: string) {
    super(message, 'AUTHORIZATION_ERROR');
    this.name = 'AuthorizationError';
    Object.setPrototypeOf(this, AuthorizationError.prototype);
  }
}

/**
 * Error thrown when configuration is invalid
 */
export class ConfigurationError extends PolyMCPError {
  constructor(message: string) {
    super(message, 'CONFIGURATION_ERROR');
    this.name = 'ConfigurationError';
    Object.setPrototypeOf(this, ConfigurationError.prototype);
  }
}

/**
 * Error thrown when validation fails
 */
export class ValidationError extends PolyMCPError {
  constructor(message: string, public readonly errors?: unknown[]) {
    super(message, 'VALIDATION_ERROR');
    this.name = 'ValidationError';
    Object.setPrototypeOf(this, ValidationError.prototype);
  }
}

/**
 * Error thrown when a timeout occurs
 */
export class TimeoutError extends PolyMCPError {
  constructor(operation: string, timeoutMs: number) {
    super(`Operation timed out: ${operation} (timeout: ${timeoutMs}ms)`, 'TIMEOUT_ERROR');
    this.name = 'TimeoutError';
    Object.setPrototypeOf(this, TimeoutError.prototype);
  }
}

/**
 * Error thrown when an LLM operation fails
 */
export class LLMError extends PolyMCPError {
  constructor(message: string, public readonly provider?: string) {
    super(provider ? `${provider}: ${message}` : message, 'LLM_ERROR');
    this.name = 'LLMError';
    Object.setPrototypeOf(this, LLMError.prototype);
  }
}

/**
 * Error thrown when agent execution fails
 */
export class AgentExecutionError extends PolyMCPError {
  constructor(message: string) {
    super(message, 'AGENT_EXECUTION_ERROR');
    this.name = 'AgentExecutionError';
    Object.setPrototypeOf(this, AgentExecutionError.prototype);
  }
}
