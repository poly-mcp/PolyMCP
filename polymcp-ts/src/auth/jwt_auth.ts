/**
 * JWT Authentication Provider
 * 
 * Supports JWT token generation, validation, and automatic refresh.
 * Compatible algorithms: RS256, HS256, ES256
 */

import * as jwt from 'jsonwebtoken';
import * as fs from 'fs';
import { AuthProvider } from './auth_base';

/**
 * JWT Algorithm types
 */
export type JWTAlgorithm = 'RS256' | 'HS256' | 'ES256';

/**
 * JWT Configuration
 */
export interface JWTConfig {
  /** Secret key (for HS256) or private key (for RS256/ES256) */
  secret?: string;
  /** Path to secret/private key file (alternative to secret string) */
  secretPath?: string;
  /** JWT algorithm */
  algorithm?: JWTAlgorithm;
  /** Token claims/payload */
  claims?: Record<string, any>;
  /** Token expiration in seconds (default: 3600 = 1 hour) */
  expiresIn?: number;
  /** Issuer claim */
  issuer?: string;
  /** Audience claim */
  audience?: string | string[];
  /** Subject claim */
  subject?: string;
  /** Header name for Authorization header (default: 'Authorization') */
  headerName?: string;
  /** Prefix for Authorization header (default: 'Bearer') */
  headerPrefix?: string;
  /** Auto-refresh buffer time in seconds (default: 300 = 5 minutes) */
  refreshBuffer?: number;
}

/**
 * JWT Authentication Provider.
 * 
 * Features:
 * - Token generation with configurable claims
 * - Multiple algorithm support (RS256, HS256, ES256)
 * - Automatic token refresh before expiry
 * - Retry on 401/403 with fresh token
 * 
 * Example:
 * ```typescript
 * const jwtAuth = new JWTAuthProvider({
 *   secret: 'my-secret-key',
 *   algorithm: 'HS256',
 *   claims: { user_id: '123', role: 'admin' },
 *   expiresIn: 3600
 * });
 * 
 * const headers = await jwtAuth.getHeadersAsync();
 * // { Authorization: 'Bearer eyJhbGc...' }
 * ```
 */
export class JWTAuthProvider extends AuthProvider {
  private secret: string;
  private algorithm: JWTAlgorithm;
  private claims: Record<string, any>;
  private expiresIn: number;
  private issuer?: string;
  private audience?: string | string[];
  private subject?: string;
  private headerName: string;
  private headerPrefix: string;
  private refreshBuffer: number;

  // Token state
  private currentToken: string | null = null;
  private tokenExpiresAt: number = 0;

  constructor(config: JWTConfig) {
    super();

    // Load secret from file if path provided
    if (config.secretPath) {
      this.secret = fs.readFileSync(config.secretPath, 'utf-8').trim();
    } else if (config.secret) {
      this.secret = config.secret;
    } else {
      throw new Error('JWT: Either secret or secretPath must be provided');
    }

    this.algorithm = config.algorithm || 'HS256';
    this.claims = config.claims || {};
    this.expiresIn = config.expiresIn || 3600;
    this.issuer = config.issuer;
    this.audience = config.audience;
    this.subject = config.subject;
    this.headerName = config.headerName || 'Authorization';
    this.headerPrefix = config.headerPrefix || 'Bearer';
    this.refreshBuffer = config.refreshBuffer || 300; // 5 minutes default

    // Generate initial token
    this.generateToken();
  }

  /**
   * Generate a new JWT token
   */
  private generateToken(): void {
    const now = Math.floor(Date.now() / 1000);
    
    // Build payload
    const payload: Record<string, any> = {
      ...this.claims,
      iat: now,
      exp: now + this.expiresIn,
    };

    if (this.issuer) payload.iss = this.issuer;
    if (this.audience) payload.aud = this.audience;
    if (this.subject) payload.sub = this.subject;

    // Sign token
    const signOptions: jwt.SignOptions = {
      algorithm: this.algorithm,
    };

    try {
      this.currentToken = jwt.sign(payload, this.secret, signOptions);
      this.tokenExpiresAt = now + this.expiresIn;
    } catch (error: any) {
      throw new Error(`JWT token generation failed: ${error.message}`);
    }
  }

  /**
   * Check if current token needs refresh
   */
  private shouldRefreshToken(): boolean {
    if (!this.currentToken) return true;
    
    const now = Math.floor(Date.now() / 1000);
    const timeUntilExpiry = this.tokenExpiresAt - now;
    
    // Refresh if token expires within refreshBuffer seconds
    return timeUntilExpiry <= this.refreshBuffer;
  }

  /**
   * Get headers synchronously
   */
  getHeadersSync(): Record<string, string> {
    // Check if refresh needed
    if (this.shouldRefreshToken()) {
      this.generateToken();
    }

    if (!this.currentToken) {
      throw new Error('JWT: No token available');
    }

    return {
      [this.headerName]: `${this.headerPrefix} ${this.currentToken}`,
    };
  }

  /**
   * Get headers asynchronously
   */
  async getHeadersAsync(): Promise<Record<string, string>> {
    return this.getHeadersSync();
  }

  /**
   * Should retry on unauthorized
   */
  shouldRetryOnUnauthorized(): boolean {
    // JWT can be refreshed
    return true;
  }

  /**
   * Handle unauthorized synchronously
   */
  handleUnauthorizedSync(): void {
    // Force token refresh
    this.generateToken();
  }

  /**
   * Handle unauthorized asynchronously
   */
  async handleUnauthorizedAsync(): Promise<void> {
    this.handleUnauthorizedSync();
  }

  /**
   * Manually refresh token (useful for testing)
   */
  refreshToken(): void {
    this.generateToken();
  }

  /**
   * Get current token (for inspection/debugging)
   */
  getCurrentToken(): string | null {
    return this.currentToken;
  }

  /**
   * Get token expiration time (Unix timestamp)
   */
  getTokenExpiry(): number {
    return this.tokenExpiresAt;
  }

  /**
   * Check if token is expired
   */
  isTokenExpired(): boolean {
    const now = Math.floor(Date.now() / 1000);
    return now >= this.tokenExpiresAt;
  }

  /**
   * Decode token payload (without verification)
   */
  decodeToken(): Record<string, any> | null {
    if (!this.currentToken) return null;

    try {
      return jwt.decode(this.currentToken) as Record<string, any>;
    } catch {
      return null;
    }
  }
}

/**
 * JWT Auth Provider Factory
 * Convenience factory for common JWT configurations
 */
export class JWTAuthFactory {
  /**
   * Create JWT provider with HS256 (symmetric key)
   */
  static createHS256(
    secret: string,
    claims: Record<string, any>,
    expiresIn: number = 3600
  ): JWTAuthProvider {
    return new JWTAuthProvider({
      secret,
      algorithm: 'HS256',
      claims,
      expiresIn,
    });
  }

  /**
   * Create JWT provider with RS256 (RSA private key)
   */
  static createRS256(
    privateKeyPath: string,
    claims: Record<string, any>,
    expiresIn: number = 3600
  ): JWTAuthProvider {
    return new JWTAuthProvider({
      secretPath: privateKeyPath,
      algorithm: 'RS256',
      claims,
      expiresIn,
    });
  }

  /**
   * Create JWT provider with ES256 (ECDSA private key)
   */
  static createES256(
    privateKeyPath: string,
    claims: Record<string, any>,
    expiresIn: number = 3600
  ): JWTAuthProvider {
    return new JWTAuthProvider({
      secretPath: privateKeyPath,
      algorithm: 'ES256',
      claims,
      expiresIn,
    });
  }
}
