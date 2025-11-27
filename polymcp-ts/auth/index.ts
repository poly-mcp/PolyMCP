/**
 * Authentication Module
 * 
 * Provides JWT and API key authentication for MCP servers.
 * Production-ready with security best practices.
 */

import * as jwt from 'jsonwebtoken';
import * as crypto from 'crypto';
import { AuthConfig, JWTPayload, ApiKeyConfig } from '../types';
import { AuthenticationError, ConfigurationError } from '../errors';
import { JWT_DEFAULTS } from '../constants';

// ============================================================================
// JWT Authentication
// ============================================================================

/**
 * JWT Auth Manager
 */
export class JWTAuthManager {
  private secret: string;
  private algorithm: jwt.Algorithm;
  private expiration: string | number;
  private issuer: string;
  
  constructor(config: AuthConfig) {
    if (!config.jwtSecret) {
      throw new ConfigurationError('JWT secret is required for JWT authentication');
    }
    
    this.secret = config.jwtSecret;
    this.algorithm = JWT_DEFAULTS.ALGORITHM;
    this.expiration = config.jwtExpiration || JWT_DEFAULTS.EXPIRATION;
    this.issuer = JWT_DEFAULTS.ISSUER;
  }
  
  /**
   * Generate a new JWT token
   */
  generateToken(payload: Omit<JWTPayload, 'iat' | 'exp'>): string {
    const now = Math.floor(Date.now() / 1000);
    
    const fullPayload: JWTPayload = {
      sub: payload.sub,
      ...payload,
      iat: now,
      exp: now + this.parseExpiration(this.expiration),
      iss: this.issuer,
    };
    
    return jwt.sign(fullPayload, this.secret, {
      algorithm: this.algorithm,
    });
  }
  
  /**
   * Verify and decode a JWT token
   */
  verifyToken(token: string): JWTPayload {
    try {
      const decoded = jwt.verify(token, this.secret, {
        algorithms: [this.algorithm],
        issuer: this.issuer,
      }) as JWTPayload;
      
      return decoded;
    } catch (error) {
      if (error instanceof jwt.TokenExpiredError) {
        throw new AuthenticationError('Token has expired');
      } else if (error instanceof jwt.JsonWebTokenError) {
        throw new AuthenticationError('Invalid token');
      } else {
        throw new AuthenticationError('Token verification failed');
      }
    }
  }
  
  /**
   * Refresh a token (generate new one with same payload)
   */
  refreshToken(token: string): string {
    const decoded = this.verifyToken(token);
    
    // Remove timing fields for refresh
    const { iat, exp, ...payload } = decoded;
    
    return this.generateToken(payload);
  }
  
  /**
   * Parse expiration string to seconds
   */
  private parseExpiration(exp: string | number): number {
    if (typeof exp === 'number') {
      return exp;
    }
    
    // Parse strings like '24h', '7d', '30m'
    const match = exp.match(/^(\d+)([smhd])$/);
    if (!match) {
      throw new ConfigurationError(`Invalid expiration format: ${exp}`);
    }
    
    const [, num, unit] = match;
    const value = parseInt(num, 10);
    
    switch (unit) {
      case 's':
        return value;
      case 'm':
        return value * 60;
      case 'h':
        return value * 3600;
      case 'd':
        return value * 86400;
      default:
        throw new ConfigurationError(`Invalid expiration unit: ${unit}`);
    }
  }
}

// ============================================================================
// API Key Authentication
// ============================================================================

/**
 * API Key Manager
 */
export class ApiKeyManager {
  private keys: Map<string, ApiKeyConfig>;
  
  constructor() {
    this.keys = new Map();
  }
  
  /**
   * Generate a new API key
   */
  generateKey(config?: Partial<ApiKeyConfig>): string {
    const key = 'pk_' + crypto.randomBytes(32).toString('hex');
    
    this.keys.set(key, {
      key,
      name: config?.name || 'Default',
      permissions: config?.permissions || [],
      expiresAt: config?.expiresAt,
    });
    
    return key;
  }
  
  /**
   * Add an existing API key
   */
  addKey(key: string, config?: Partial<ApiKeyConfig>): void {
    this.keys.set(key, {
      key,
      name: config?.name || 'Default',
      permissions: config?.permissions || [],
      expiresAt: config?.expiresAt,
    });
  }
  
  /**
   * Verify an API key
   */
  verifyKey(key: string): ApiKeyConfig {
    const config = this.keys.get(key);
    
    if (!config) {
      throw new AuthenticationError('Invalid API key');
    }
    
    // Check expiration
    if (config.expiresAt && config.expiresAt < new Date()) {
      throw new AuthenticationError('API key has expired');
    }
    
    return config;
  }
  
  /**
   * Revoke an API key
   */
  revokeKey(key: string): boolean {
    return this.keys.delete(key);
  }
  
  /**
   * List all API keys
   */
  listKeys(): ApiKeyConfig[] {
    return Array.from(this.keys.values());
  }
  
  /**
   * Check if key has permission
   */
  hasPermission(key: string, permission: string): boolean {
    const config = this.keys.get(key);
    if (!config) {
      return false;
    }
    
    // If no permissions specified, allow all
    if (!config.permissions || config.permissions.length === 0) {
      return true;
    }
    
    return config.permissions.includes(permission) || config.permissions.includes('*');
  }
}

// ============================================================================
// Unified Auth Manager
// ============================================================================

/**
 * Unified authentication manager supporting multiple auth types
 */
export class AuthManager {
  private config: AuthConfig;
  private jwtManager?: JWTAuthManager;
  private apiKeyManager?: ApiKeyManager;
  
  constructor(config: AuthConfig) {
    this.config = config;
    
    if (config.type === 'jwt') {
      this.jwtManager = new JWTAuthManager(config);
    } else if (config.type === 'api_key') {
      this.apiKeyManager = new ApiKeyManager();
      
      // Add initial API key if provided
      if (config.apiKey) {
        this.apiKeyManager.addKey(config.apiKey);
      }
    }
  }
  
  /**
   * Authenticate a request
   */
  authenticate(authHeader: string | undefined): void {
    if (this.config.type === 'none') {
      return; // No authentication required
    }
    
    if (!authHeader) {
      throw new AuthenticationError('Authorization header is required');
    }
    
    if (this.config.type === 'jwt') {
      this.authenticateJWT(authHeader);
    } else if (this.config.type === 'api_key') {
      this.authenticateApiKey(authHeader);
    } else if (this.config.type === 'basic') {
      this.authenticateBasic(authHeader);
    }
  }
  
  /**
   * Authenticate JWT token
   */
  private authenticateJWT(authHeader: string): JWTPayload {
    if (!this.jwtManager) {
      throw new ConfigurationError('JWT manager not initialized');
    }
    
    // Extract token from "Bearer <token>"
    const match = authHeader.match(/^Bearer\s+(.+)$/i);
    if (!match) {
      throw new AuthenticationError('Invalid authorization header format');
    }
    
    const token = match[1];
    return this.jwtManager.verifyToken(token);
  }
  
  /**
   * Authenticate API key
   */
  private authenticateApiKey(authHeader: string): ApiKeyConfig {
    if (!this.apiKeyManager) {
      throw new ConfigurationError('API key manager not initialized');
    }
    
    // Support both "Bearer <key>" and "ApiKey <key>"
    const match = authHeader.match(/^(?:Bearer|ApiKey)\s+(.+)$/i);
    if (!match) {
      throw new AuthenticationError('Invalid authorization header format');
    }
    
    const key = match[1];
    return this.apiKeyManager.verifyKey(key);
  }
  
  /**
   * Authenticate basic auth
   */
  private authenticateBasic(authHeader: string): void {
    // Extract credentials from "Basic <base64>"
    const match = authHeader.match(/^Basic\s+(.+)$/i);
    if (!match) {
      throw new AuthenticationError('Invalid authorization header format');
    }
    
    const credentials = Buffer.from(match[1], 'base64').toString('utf-8');
    const [username, password] = credentials.split(':');
    
    if (!username || !password) {
      throw new AuthenticationError('Invalid credentials format');
    }
    
    // Verify credentials
    if (username !== this.config.username || password !== this.config.password) {
      throw new AuthenticationError('Invalid credentials');
    }
  }
  
  /**
   * Get JWT manager
   */
  getJWTManager(): JWTAuthManager {
    if (!this.jwtManager) {
      throw new ConfigurationError('JWT manager not initialized');
    }
    return this.jwtManager;
  }
  
  /**
   * Get API key manager
   */
  getApiKeyManager(): ApiKeyManager {
    if (!this.apiKeyManager) {
      throw new ConfigurationError('API key manager not initialized');
    }
    return this.apiKeyManager;
  }
}

/**
 * Create an authentication manager
 */
export function createAuthManager(config: AuthConfig): AuthManager {
  return new AuthManager(config);
}
