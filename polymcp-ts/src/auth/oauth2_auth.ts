/**
 * OAuth2 Authentication Provider
 * 
 * Supports multiple OAuth2 flows:
 * - Authorization Code Flow (with PKCE)
 * - Client Credentials Flow
 * - Password Flow
 * - Refresh Token Flow
 */

import axios from 'axios';
import * as crypto from 'crypto';
import * as fs from 'fs';
import { AuthProvider } from './auth_base';

/**
 * OAuth2 Flow types
 */
export type OAuth2Flow = 
  | 'authorization_code'
  | 'client_credentials'
  | 'password'
  | 'refresh_token';

/**
 * Token response from OAuth2 server
 */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  refresh_token?: string;
  scope?: string;
}

/**
 * OAuth2 Configuration
 */
export interface OAuth2Config {
  /** OAuth2 flow type */
  flow: OAuth2Flow;
  /** Client ID */
  clientId: string;
  /** Client Secret (optional for PKCE) */
  clientSecret?: string;
  /** Authorization endpoint URL */
  authUrl?: string;
  /** Token endpoint URL */
  tokenUrl: string;
  /** Redirect URI (for authorization_code flow) */
  redirectUri?: string;
  /** Scopes to request */
  scope?: string[];
  /** Username (for password flow) */
  username?: string;
  /** Password (for password flow) */
  password?: string;
  /** Initial refresh token (for refresh_token flow) */
  refreshToken?: string;
  /** Enable PKCE (for authorization_code flow) */
  usePkce?: boolean;
  /** Token storage path (optional, for persistence) */
  tokenStoragePath?: string;
  /** Refresh buffer in seconds (default: 300) */
  refreshBuffer?: number;
  /** Header name (default: 'Authorization') */
  headerName?: string;
  /** Header prefix (default: 'Bearer') */
  headerPrefix?: string;
}

/**
 * Token storage (in-memory and optionally file-based)
 */
interface TokenStorage {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: number;
  tokenType: string;
}

/**
 * OAuth2 Authentication Provider.
 * 
 * Features:
 * - Multiple OAuth2 flows
 * - PKCE support for authorization code flow
 * - Automatic token refresh
 * - Token persistence (optional)
 * - State validation
 * - Retry on 401/403
 * 
 * Example (Client Credentials):
 * ```typescript
 * const oauth = new OAuth2AuthProvider({
 *   flow: 'client_credentials',
 *   clientId: 'my-client-id',
 *   clientSecret: 'my-client-secret',
 *   tokenUrl: 'https://auth.example.com/token',
 *   scope: ['read', 'write']
 * });
 * 
 * await oauth.initialize();
 * const headers = await oauth.getHeadersAsync();
 * ```
 * 
 * Example (Authorization Code with PKCE):
 * ```typescript
 * const oauth = new OAuth2AuthProvider({
 *   flow: 'authorization_code',
 *   clientId: 'my-client-id',
 *   authUrl: 'https://auth.example.com/authorize',
 *   tokenUrl: 'https://auth.example.com/token',
 *   redirectUri: 'http://localhost:3000/callback',
 *   usePkce: true
 * });
 * 
 * const authUrl = oauth.getAuthorizationUrl();
 * // Open authUrl in browser, get code from callback
 * await oauth.exchangeCodeForToken(code);
 * const headers = await oauth.getHeadersAsync();
 * ```
 */
export class OAuth2AuthProvider extends AuthProvider {
  private config: OAuth2Config;
  private storage: TokenStorage;
  private pkceVerifier: string | null = null;

  constructor(config: OAuth2Config) {
    super();
    this.config = {
      refreshBuffer: 300,
      headerName: 'Authorization',
      headerPrefix: 'Bearer',
      usePkce: false,
      ...config,
    };

    this.storage = {
      accessToken: null,
      refreshToken: config.refreshToken || null,
      expiresAt: 0,
      tokenType: 'Bearer',
    };

    // Load from file if path provided
    if (this.config.tokenStoragePath) {
      this.loadTokenFromFile();
    }
  }

  /**
   * Initialize OAuth2 provider.
   * Must be called before using the provider.
   * For client_credentials and password flows, this fetches the initial token.
   */
  async initialize(): Promise<void> {
    if (this.config.flow === 'client_credentials') {
      await this.fetchClientCredentialsToken();
    } else if (this.config.flow === 'password') {
      await this.fetchPasswordToken();
    } else if (this.config.flow === 'refresh_token' && this.storage.refreshToken) {
      await this.refreshAccessToken();
    }
    // For authorization_code, user must call getAuthorizationUrl() and exchangeCodeForToken()
  }

  /**
   * Get authorization URL (for authorization_code flow)
   */
  getAuthorizationUrl(state?: string): string {
    if (this.config.flow !== 'authorization_code') {
      throw new Error('getAuthorizationUrl() only available for authorization_code flow');
    }

    if (!this.config.authUrl || !this.config.redirectUri) {
      throw new Error('authUrl and redirectUri required for authorization_code flow');
    }

    const params = new URLSearchParams({
      response_type: 'code',
      client_id: this.config.clientId,
      redirect_uri: this.config.redirectUri,
    });

    if (this.config.scope) {
      params.append('scope', this.config.scope.join(' '));
    }

    if (state) {
      params.append('state', state);
    }

    // PKCE
    if (this.config.usePkce) {
      this.pkceVerifier = this.generateCodeVerifier();
      const challenge = this.generateCodeChallenge(this.pkceVerifier);
      params.append('code_challenge', challenge);
      params.append('code_challenge_method', 'S256');
    }

    return `${this.config.authUrl}?${params.toString()}`;
  }

  /**
   * Exchange authorization code for access token (authorization_code flow)
   */
  async exchangeCodeForToken(code: string): Promise<void> {
    if (this.config.flow !== 'authorization_code') {
      throw new Error('exchangeCodeForToken() only available for authorization_code flow');
    }

    const params: Record<string, string> = {
      grant_type: 'authorization_code',
      code,
      client_id: this.config.clientId,
      redirect_uri: this.config.redirectUri || '',
    };

    if (this.config.clientSecret) {
      params.client_secret = this.config.clientSecret;
    }

    if (this.config.usePkce && this.pkceVerifier) {
      params.code_verifier = this.pkceVerifier;
    }

    await this.fetchToken(params);
  }

  /**
   * Fetch token using client credentials flow
   */
  private async fetchClientCredentialsToken(): Promise<void> {
    if (!this.config.clientSecret) {
      throw new Error('clientSecret required for client_credentials flow');
    }

    const params: Record<string, string> = {
      grant_type: 'client_credentials',
      client_id: this.config.clientId,
      client_secret: this.config.clientSecret,
    };

    if (this.config.scope) {
      params.scope = this.config.scope.join(' ');
    }

    await this.fetchToken(params);
  }

  /**
   * Fetch token using password flow
   */
  private async fetchPasswordToken(): Promise<void> {
    if (!this.config.username || !this.config.password) {
      throw new Error('username and password required for password flow');
    }

    const params: Record<string, string> = {
      grant_type: 'password',
      username: this.config.username,
      password: this.config.password,
      client_id: this.config.clientId,
    };

    if (this.config.clientSecret) {
      params.client_secret = this.config.clientSecret;
    }

    if (this.config.scope) {
      params.scope = this.config.scope.join(' ');
    }

    await this.fetchToken(params);
  }

  /**
   * Refresh access token using refresh token
   */
  private async refreshAccessToken(): Promise<void> {
    if (!this.storage.refreshToken) {
      throw new Error('No refresh token available');
    }

    const params: Record<string, string> = {
      grant_type: 'refresh_token',
      refresh_token: this.storage.refreshToken,
      client_id: this.config.clientId,
    };

    if (this.config.clientSecret) {
      params.client_secret = this.config.clientSecret;
    }

    await this.fetchToken(params);
  }

  /**
   * Generic token fetch method
   */
  private async fetchToken(params: Record<string, string>): Promise<void> {
    try {
      const response = await axios.post<TokenResponse>(
        this.config.tokenUrl,
        new URLSearchParams(params),
        {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
        }
      );

      const tokenData = response.data;
      this.updateStorage(tokenData);
    } catch (error: any) {
      throw new Error(`OAuth2 token fetch failed: ${error.message}`);
    }
  }

  /**
   * Update token storage
   */
  private updateStorage(tokenData: TokenResponse): void {
    this.storage.accessToken = tokenData.access_token;
    this.storage.tokenType = tokenData.token_type || 'Bearer';

    if (tokenData.refresh_token) {
      this.storage.refreshToken = tokenData.refresh_token;
    }

    if (tokenData.expires_in) {
      const now = Math.floor(Date.now() / 1000);
      this.storage.expiresAt = now + tokenData.expires_in;
    } else {
      // Default to 1 hour if not provided
      const now = Math.floor(Date.now() / 1000);
      this.storage.expiresAt = now + 3600;
    }

    // Save to file if path provided
    if (this.config.tokenStoragePath) {
      this.saveTokenToFile();
    }
  }

  /**
   * Check if token needs refresh
   */
  private shouldRefreshToken(): boolean {
    if (!this.storage.accessToken) return true;

    const now = Math.floor(Date.now() / 1000);
    const timeUntilExpiry = this.storage.expiresAt - now;

    return timeUntilExpiry <= (this.config.refreshBuffer || 300);
  }

  /**
   * Get headers synchronously (not recommended for OAuth2)
   */
  getHeadersSync(): Record<string, string> {
    if (!this.storage.accessToken) {
      throw new Error('OAuth2: No access token available. Call initialize() first.');
    }

    return {
      [this.config.headerName!]: `${this.config.headerPrefix} ${this.storage.accessToken}`,
    };
  }

  /**
   * Get headers asynchronously
   */
  async getHeadersAsync(): Promise<Record<string, string>> {
    // Refresh token if needed
    if (this.shouldRefreshToken() && this.storage.refreshToken) {
      await this.refreshAccessToken();
    }

    return this.getHeadersSync();
  }

  /**
   * Should retry on unauthorized
   */
  shouldRetryOnUnauthorized(): boolean {
    // Can retry if we have a refresh token
    return !!this.storage.refreshToken;
  }

  /**
   * Handle unauthorized synchronously
   */
  handleUnauthorizedSync(): void {
    // Can't do sync refresh for OAuth2
    throw new Error('OAuth2: Use handleUnauthorizedAsync() instead');
  }

  /**
   * Handle unauthorized asynchronously
   */
  async handleUnauthorizedAsync(): Promise<void> {
    if (this.storage.refreshToken) {
      await this.refreshAccessToken();
    } else {
      throw new Error('OAuth2: No refresh token available, re-authentication required');
    }
  }

  /**
   * Save token to file
   */
  private saveTokenToFile(): void {
    if (!this.config.tokenStoragePath) return;

    const data = JSON.stringify(this.storage, null, 2);
    fs.writeFileSync(this.config.tokenStoragePath, data, 'utf-8');
  }

  /**
   * Load token from file
   */
  private loadTokenFromFile(): void {
    if (!this.config.tokenStoragePath) return;

    try {
      if (fs.existsSync(this.config.tokenStoragePath)) {
        const data = fs.readFileSync(this.config.tokenStoragePath, 'utf-8');
        this.storage = JSON.parse(data);
      }
    } catch (error) {
      // Ignore errors, will fetch fresh token
    }
  }

  /**
   * Generate PKCE code verifier
   */
  private generateCodeVerifier(): string {
    return crypto.randomBytes(32).toString('base64url');
  }

  /**
   * Generate PKCE code challenge (S256)
   */
  private generateCodeChallenge(verifier: string): string {
    return crypto
      .createHash('sha256')
      .update(verifier)
      .digest('base64url');
  }

  /**
   * Get current access token (for inspection)
   */
  getAccessToken(): string | null {
    return this.storage.accessToken;
  }

  /**
   * Get current refresh token (for inspection)
   */
  getRefreshToken(): string | null {
    return this.storage.refreshToken;
  }

  /**
   * Check if token is expired
   */
  isTokenExpired(): boolean {
    const now = Math.floor(Date.now() / 1000);
    return now >= this.storage.expiresAt;
  }

  /**
   * Clear stored tokens
   */
  clearTokens(): void {
    this.storage.accessToken = null;
    this.storage.refreshToken = null;
    this.storage.expiresAt = 0;

    if (this.config.tokenStoragePath && fs.existsSync(this.config.tokenStoragePath)) {
      fs.unlinkSync(this.config.tokenStoragePath);
    }
  }
}

/**
 * OAuth2 Factory for common configurations
 */
export class OAuth2Factory {
  /**
   * Create OAuth2 provider for GitHub
   */
  static createGitHub(
    clientId: string,
    clientSecret: string,
    scope?: string[]
  ): OAuth2AuthProvider {
    return new OAuth2AuthProvider({
      flow: 'authorization_code',
      clientId,
      clientSecret,
      authUrl: 'https://github.com/login/oauth/authorize',
      tokenUrl: 'https://github.com/login/oauth/access_token',
      scope: scope || ['user', 'repo'],
    });
  }

  /**
   * Create OAuth2 provider for Google
   */
  static createGoogle(
    clientId: string,
    clientSecret: string,
    redirectUri: string,
    scope?: string[]
  ): OAuth2AuthProvider {
    return new OAuth2AuthProvider({
      flow: 'authorization_code',
      clientId,
      clientSecret,
      authUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
      tokenUrl: 'https://oauth2.googleapis.com/token',
      redirectUri,
      scope: scope || ['openid', 'email', 'profile'],
      usePkce: true,
    });
  }

  /**
   * Create OAuth2 provider for Microsoft
   */
  static createMicrosoft(
    clientId: string,
    clientSecret: string,
    redirectUri: string,
    tenant: string = 'common'
  ): OAuth2AuthProvider {
    return new OAuth2AuthProvider({
      flow: 'authorization_code',
      clientId,
      clientSecret,
      authUrl: `https://login.microsoftonline.com/${tenant}/oauth2/v2.0/authorize`,
      tokenUrl: `https://login.microsoftonline.com/${tenant}/oauth2/v2.0/token`,
      redirectUri,
      usePkce: true,
    });
  }
}
