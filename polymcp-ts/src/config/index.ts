/**
 * Configuration Module
 * 
 * Manages library configuration and environment variables.
 */

import * as dotenv from 'dotenv';
import { PolyMCPConfig, AuthConfig, LLMConfig, AgentConfig } from '../types';
import { ConfigurationError } from '../errors';
import { ENV_VARS, DEFAULT_PORTS, TIMEOUTS } from '../constants';

// Load environment variables from .env file
dotenv.config();

/**
 * Get environment variable
 */
function getEnv(key: string, defaultValue?: string): string | undefined {
  return process.env[key] || defaultValue;
}

/**
 * Get required environment variable
 */
export function getRequiredEnv(key: string): string {
  const value = process.env[key];
  if (!value) {
    throw new ConfigurationError(`Required environment variable not set: ${key}`);
  }
  return value;
}

/**
 * Get environment variable as number
 */
function getEnvNumber(key: string, defaultValue?: number): number | undefined {
  const value = process.env[key];
  if (!value) {
    return defaultValue;
  }
  
  const num = parseInt(value, 10);
  if (isNaN(num)) {
    throw new ConfigurationError(`Invalid number for ${key}: ${value}`);
  }
  
  return num;
}

/**
 * Get environment variable as boolean
 */
function getEnvBoolean(key: string, defaultValue?: boolean): boolean {
  const value = process.env[key];
  if (!value) {
    return defaultValue ?? false;
  }
  
  return value.toLowerCase() === 'true' || value === '1';
}

/**
 * Configuration Manager
 */
export class ConfigManager {
  private config: PolyMCPConfig;
  
  constructor(config?: Partial<PolyMCPConfig>) {
    this.config = this.loadConfig(config);
  }
  
  /**
   * Load configuration from environment and provided config
   */
  private loadConfig(userConfig?: Partial<PolyMCPConfig>): PolyMCPConfig {
    return {
      defaultTimeout: userConfig?.defaultTimeout || TIMEOUTS.DEFAULT,
      defaultRetries: userConfig?.defaultRetries || 3,
      logLevel: userConfig?.logLevel || 'info',
      auth: userConfig?.auth || this.loadAuthConfig(),
      llm: userConfig?.llm || this.loadLLMConfig(),
      agent: userConfig?.agent || this.loadAgentConfig(),
    };
  }
  
  /**
   * Load authentication configuration
   */
  private loadAuthConfig(): AuthConfig {
    const jwtSecret = getEnv(ENV_VARS.JWT_SECRET);
    const apiKey = getEnv(ENV_VARS.API_KEY);
    
    if (jwtSecret) {
      return {
        type: 'jwt',
        jwtSecret,
        jwtExpiration: '24h',
      };
    }
    
    if (apiKey) {
      return {
        type: 'api_key',
        apiKey,
      };
    }
    
    return {
      type: 'none',
    };
  }
  
  /**
   * Load LLM configuration
   */
  private loadLLMConfig(): LLMConfig {
    return {
      apiKey: getEnv(ENV_VARS.OPENAI_API_KEY) || getEnv(ENV_VARS.ANTHROPIC_API_KEY),
      temperature: 0.7,
      maxTokens: 4000,
    };
  }
  
  /**
   * Load agent configuration
   */
  private loadAgentConfig(): AgentConfig {
    return {
      maxSteps: 10,
      timeout: TIMEOUTS.AGENT_STEP,
      verbose: getEnvBoolean('VERBOSE', false),
      enableHistory: true,
    };
  }
  
  /**
   * Get full configuration
   */
  getConfig(): PolyMCPConfig {
    return this.config;
  }
  
  /**
   * Get authentication configuration
   */
  getAuthConfig(): AuthConfig | undefined {
    return this.config.auth;
  }
  
  /**
   * Get LLM configuration
   */
  getLLMConfig(): LLMConfig | undefined {
    return this.config.llm;
  }
  
  /**
   * Get agent configuration
   */
  getAgentConfig(): AgentConfig | undefined {
    return this.config.agent;
  }
  
  /**
   * Update configuration
   */
  updateConfig(updates: Partial<PolyMCPConfig>): void {
    this.config = {
      ...this.config,
      ...updates,
    };
  }
  
  /**
   * Validate configuration
   */
  validate(): void {
    if (this.config.auth?.type === 'jwt' && !this.config.auth.jwtSecret) {
      throw new ConfigurationError('JWT secret is required for JWT authentication');
    }
    
    if (this.config.auth?.type === 'api_key' && !this.config.auth.apiKey) {
      throw new ConfigurationError('API key is required for API key authentication');
    }
    
    if (this.config.auth?.type === 'basic') {
      if (!this.config.auth.username || !this.config.auth.password) {
        throw new ConfigurationError('Username and password are required for basic authentication');
      }
    }
  }
}

// ============================================================================
// Global configuration instance
// ============================================================================

let globalConfig: ConfigManager | null = null;

/**
 * Get the global configuration manager
 */
export function getGlobalConfig(): ConfigManager {
  if (!globalConfig) {
    globalConfig = new ConfigManager();
  }
  return globalConfig;
}

/**
 * Initialize global configuration
 */
export function initConfig(config?: Partial<PolyMCPConfig>): ConfigManager {
  globalConfig = new ConfigManager(config);
  return globalConfig;
}

/**
 * Reset global configuration (useful for testing)
 */
export function resetGlobalConfig(): void {
  globalConfig = null;
}

// ============================================================================
// Helper functions
// ============================================================================

/**
 * Load configuration from environment variables
 */
export function loadFromEnv(): PolyMCPConfig {
  const config = new ConfigManager();
  return config.getConfig();
}

/**
 * Get default server port
 */
export function getDefaultPort(): number {
  return getEnvNumber(ENV_VARS.PORT) || DEFAULT_PORTS.HTTP;
}

/**
 * Check if running in production
 */
export function isProduction(): boolean {
  return getEnv(ENV_VARS.NODE_ENV) === 'production';
}

/**
 * Check if running in development
 */
export function isDevelopment(): boolean {
  return getEnv(ENV_VARS.NODE_ENV) === 'development' || !getEnv(ENV_VARS.NODE_ENV);
}

/**
 * Get log level from environment
 */
export function getLogLevel(): string {
  return getEnv(ENV_VARS.LOG_LEVEL) || 'info';
}
