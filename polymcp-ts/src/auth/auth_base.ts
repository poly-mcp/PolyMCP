/**
 * Auth Base - Abstract Authentication Provider
 * 
 * Base class for all authentication providers.
 * Supports both sync and async operations for maximum flexibility.
 */

/**
 * Abstract base class for authentication providers.
 * All auth implementations must extend this class.
 */
export abstract class AuthProvider {
  /**
   * Get authentication headers synchronously.
   * Use this for simple auth schemes (API keys, static tokens).
   * 
   * @returns Record of HTTP headers to add to requests
   */
  abstract getHeadersSync(): Record<string, string>;

  /**
   * Get authentication headers asynchronously.
   * Use this for auth schemes requiring async operations (OAuth2, JWT refresh).
   * 
   * @returns Promise resolving to Record of HTTP headers
   */
  abstract getHeadersAsync(): Promise<Record<string, string>>;

  /**
   * Determine if auth should be retried after 401/403 error.
   * 
   * @returns true if auth can be refreshed and request retried
   */
  abstract shouldRetryOnUnauthorized(): boolean;

  /**
   * Handle unauthorized error synchronously.
   * Called when a 401/403 is received and shouldRetryOnUnauthorized() is true.
   * Should refresh tokens, credentials, etc.
   */
  abstract handleUnauthorizedSync(): void;

  /**
   * Handle unauthorized error asynchronously.
   * Called when a 401/403 is received and shouldRetryOnUnauthorized() is true.
   * Should refresh tokens, credentials, etc.
   */
  abstract handleUnauthorizedAsync(): Promise<void>;
}

/**
 * Simple API Key authentication provider.
 * Most basic auth scheme - just adds an API key header.
 */
export class APIKeyAuthProvider extends AuthProvider {
  constructor(
    private apiKey: string,
    private headerName: string = 'Authorization',
    private headerPrefix: string = 'Bearer'
  ) {
    super();
  }

  getHeadersSync(): Record<string, string> {
    return {
      [this.headerName]: `${this.headerPrefix} ${this.apiKey}`,
    };
  }

  async getHeadersAsync(): Promise<Record<string, string>> {
    return this.getHeadersSync();
  }

  shouldRetryOnUnauthorized(): boolean {
    // API keys don't refresh
    return false;
  }

  handleUnauthorizedSync(): void {
    // Nothing to do for static API keys
  }

  async handleUnauthorizedAsync(): Promise<void> {
    // Nothing to do for static API keys
  }
}

/**
 * Basic Auth provider (username:password).
 */
export class BasicAuthProvider extends AuthProvider {
  private credentials: string;

  constructor(username: string, password: string) {
    super();
    this.credentials = Buffer.from(`${username}:${password}`).toString('base64');
  }

  getHeadersSync(): Record<string, string> {
    return {
      Authorization: `Basic ${this.credentials}`,
    };
  }

  async getHeadersAsync(): Promise<Record<string, string>> {
    return this.getHeadersSync();
  }

  shouldRetryOnUnauthorized(): boolean {
    return false;
  }

  handleUnauthorizedSync(): void {
    // Nothing to do for Basic auth
  }

  async handleUnauthorizedAsync(): Promise<void> {
    // Nothing to do for Basic auth
  }
}

/**
 * No-op auth provider (no authentication).
 */
export class NoAuthProvider extends AuthProvider {
  getHeadersSync(): Record<string, string> {
    return {};
  }

  async getHeadersAsync(): Promise<Record<string, string>> {
    return {};
  }

  shouldRetryOnUnauthorized(): boolean {
    return false;
  }

  handleUnauthorizedSync(): void {
    // No auth to refresh
  }

  async handleUnauthorizedAsync(): Promise<void> {
    // No auth to refresh
  }
}
