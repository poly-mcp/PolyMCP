/**
 * MCP Auth Manager
 * 
 * Manages authentication for multiple MCP servers with:
 * - URL pattern matching
 * - Server-specific auth providers
 * - Dynamic auth loading
 * - Configuration file support
 */

import * as fs from 'fs';
import { AuthProvider, APIKeyAuthProvider, BasicAuthProvider, NoAuthProvider } from './auth_base';
import { JWTAuthProvider, JWTConfig } from './jwt_auth';
import { OAuth2AuthProvider, OAuth2Config } from './oauth2_auth';

/**
 * Auth configuration for a server pattern
 */
export interface ServerAuthConfig {
  /** URL pattern (string or regex) */
  pattern: string | RegExp;
  /** Auth type */
  type: 'none' | 'api_key' | 'basic' | 'jwt' | 'oauth2';
  /** Auth configuration (type-specific) */
  config: Record<string, any>;
}

/**
 * MCP Auth Manager configuration
 */
export interface MCPAuthManagerConfig {
  /** Server auth configurations */
  servers?: ServerAuthConfig[];
  /** Path to auth config file */
  configPath?: string;
  /** Default auth provider (if no match found) */
  defaultAuth?: AuthProvider;
}

/**
 * MCP Auth Manager.
 * 
 * Central manager for MCP server authentication.
 * Maps server URLs to appropriate auth providers using pattern matching.
 * 
 * Features:
 * - URL pattern matching (string prefix or regex)
 * - Multiple auth types (API key, Basic, JWT, OAuth2)
 * - Config file loading
 * - Dynamic auth provider creation
 * - Fallback to default auth
 * 
 * Example:
 * ```typescript
 * const authManager = new MCPAuthManager({
 *   servers: [
 *     {
 *       pattern: 'https://api.example.com',
 *       type: 'api_key',
 *       config: { apiKey: 'secret-key' }
 *     },
 *     {
 *       pattern: /^https:\/\/secure\..*\.com/,
 *       type: 'oauth2',
 *       config: { ... }
 *     }
 *   ],
 *   defaultAuth: new NoAuthProvider()
 * });
 * 
 * const auth = authManager.getAuthForUrl('https://api.example.com/tools');
 * const headers = await auth.getHeadersAsync();
 * ```
 * 
 * Config file format (JSON):
 * ```json
 * {
 *   "servers": [
 *     {
 *       "pattern": "https://api.example.com",
 *       "type": "api_key",
 *       "config": {
 *         "apiKey": "secret-key",
 *         "headerName": "X-API-Key"
 *       }
 *     }
 *   ]
 * }
 * ```
 */
export class MCPAuthManager {
  private authMap: Map<string | RegExp, AuthProvider> = new Map();
  private defaultAuth: AuthProvider;
  private configs: ServerAuthConfig[] = [];

  constructor(config: MCPAuthManagerConfig = {}) {
    this.defaultAuth = config.defaultAuth || new NoAuthProvider();

    // Load from config file if provided
    if (config.configPath) {
      this.loadConfigFile(config.configPath);
    }

    // Add servers from config
    if (config.servers) {
      for (const serverConfig of config.servers) {
        this.addServerAuth(serverConfig);
      }
    }
  }

  /**
   * Load auth config from JSON file
   */
  private loadConfigFile(path: string): void {
    try {
      const data = fs.readFileSync(path, 'utf-8');
      const config = JSON.parse(data);

      if (config.servers && Array.isArray(config.servers)) {
        this.configs = config.servers;
        for (const serverConfig of config.servers) {
          this.addServerAuth(serverConfig);
        }
      }
    } catch (error: any) {
      throw new Error(`Failed to load MCP auth config: ${error.message}`);
    }
  }

  /**
   * Add server-specific auth
   */
  addServerAuth(config: ServerAuthConfig): void {
    const provider = this.createAuthProvider(config.type, config.config);
    const pattern = typeof config.pattern === 'string' 
      ? config.pattern 
      : new RegExp(config.pattern);
    
    this.authMap.set(pattern, provider);
  }

  /**
   * Create auth provider from type and config
   */
  private createAuthProvider(
    type: ServerAuthConfig['type'],
    config: Record<string, any>
  ): AuthProvider {
    switch (type) {
      case 'none':
        return new NoAuthProvider();

      case 'api_key':
        return new APIKeyAuthProvider(
          config.apiKey,
          config.headerName,
          config.headerPrefix
        );

      case 'basic':
        return new BasicAuthProvider(
          config.username,
          config.password
        );

      case 'jwt':
        return new JWTAuthProvider(config as JWTConfig);

      case 'oauth2':
        return new OAuth2AuthProvider(config as OAuth2Config);

      default:
        throw new Error(`Unknown auth type: ${type}`);
    }
  }

  /**
   * Get auth provider for URL using pattern matching
   */
  getAuthForUrl(url: string): AuthProvider {
    // Try each pattern
    for (const [pattern, provider] of this.authMap.entries()) {
      if (this.matchesPattern(url, pattern)) {
        return provider;
      }
    }

    // Return default if no match
    return this.defaultAuth;
  }

  /**
   * Check if URL matches pattern
   */
  private matchesPattern(url: string, pattern: string | RegExp): boolean {
    if (typeof pattern === 'string') {
      // Simple prefix match
      return url.startsWith(pattern);
    } else {
      // Regex match
      return pattern.test(url);
    }
  }

  /**
   * Remove auth for pattern
   */
  removeServerAuth(pattern: string | RegExp): void {
    this.authMap.delete(pattern);
  }

  /**
   * Clear all server-specific auth
   */
  clearServerAuth(): void {
    this.authMap.clear();
  }

  /**
   * Get all configured patterns
   */
  getPatterns(): (string | RegExp)[] {
    return Array.from(this.authMap.keys());
  }

  /**
   * Get count of configured servers
   */
  getServerCount(): number {
    return this.authMap.size;
  }

  /**
   * Set default auth provider
   */
  setDefaultAuth(provider: AuthProvider): void {
    this.defaultAuth = provider;
  }

  /**
   * Get default auth provider
   */
  getDefaultAuth(): AuthProvider {
    return this.defaultAuth;
  }

  /**
   * Check if URL has specific auth configured
   */
  hasAuthForUrl(url: string): boolean {
    for (const pattern of this.authMap.keys()) {
      if (this.matchesPattern(url, pattern)) {
        return true;
      }
    }
    return false;
  }

  /**
   * Export current configuration to JSON
   */
  exportConfig(): string {
    return JSON.stringify({ servers: this.configs }, null, 2);
  }

  /**
   * Save configuration to file
   */
  saveConfig(path: string): void {
    const config = this.exportConfig();
    fs.writeFileSync(path, config, 'utf-8');
  }
}

/**
 * MCP Auth Factory
 * Helper for creating common MCP auth configurations
 */
export class MCPAuthFactory {
  /**
   * Create auth manager with API key for specific server
   */
  static createWithAPIKey(
    serverUrl: string,
    apiKey: string,
    headerName: string = 'Authorization'
  ): MCPAuthManager {
    return new MCPAuthManager({
      servers: [{
        pattern: serverUrl,
        type: 'api_key',
        config: { apiKey, headerName }
      }]
    });
  }

  /**
   * Create auth manager with Basic auth for specific server
   */
  static createWithBasic(
    serverUrl: string,
    username: string,
    password: string
  ): MCPAuthManager {
    return new MCPAuthManager({
      servers: [{
        pattern: serverUrl,
        type: 'basic',
        config: { username, password }
      }]
    });
  }

  /**
   * Create auth manager with JWT for specific server
   */
  static createWithJWT(
    serverUrl: string,
    jwtConfig: JWTConfig
  ): MCPAuthManager {
    return new MCPAuthManager({
      servers: [{
        pattern: serverUrl,
        type: 'jwt',
        config: jwtConfig
      }]
    });
  }

  /**
   * Create auth manager from config file
   */
  static createFromFile(configPath: string): MCPAuthManager {
    return new MCPAuthManager({ configPath });
  }

  /**
   * Create auth manager with no auth (open servers)
   */
  static createNoAuth(): MCPAuthManager {
    return new MCPAuthManager({
      defaultAuth: new NoAuthProvider()
    });
  }
}
