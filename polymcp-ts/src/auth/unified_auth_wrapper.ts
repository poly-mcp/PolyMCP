/**
 * Unified Auth Wrapper
 * 
 * Combines multiple auth providers with fallback chain and header merging.
 * Useful for scenarios requiring multiple authentication schemes.
 */

import { AuthProvider } from './auth_base';

/**
 * Unified Auth Wrapper Configuration
 */
export interface UnifiedAuthConfig {
  /** List of auth providers in priority order */
  providers: AuthProvider[];
  /** Whether to merge headers from all providers (default: true) */
  mergeHeaders?: boolean;
  /** Whether to stop at first successful provider (default: false) */
  stopAtFirst?: boolean;
}

/**
 * Unified Auth Wrapper.
 * 
 * Combines multiple authentication providers into one.
 * Can either merge headers from all providers or use first successful one.
 * 
 * Features:
 * - Multiple provider support
 * - Header merging or fallback
 * - Priority ordering
 * - Retry with next provider on failure
 * 
 * Example (Merge mode):
 * ```typescript
 * const unified = new UnifiedAuthWrapper({
 *   providers: [
 *     new APIKeyAuthProvider('api-key-123'),
 *     new JWTAuthProvider({ ... }),
 *   ],
 *   mergeHeaders: true
 * });
 * 
 * const headers = await unified.getHeadersAsync();
 * // { 'Authorization': 'Bearer ...', 'X-API-Key': '...' }
 * ```
 * 
 * Example (Fallback mode):
 * ```typescript
 * const unified = new UnifiedAuthWrapper({
 *   providers: [
 *     new OAuth2AuthProvider({ ... }), // Try OAuth2 first
 *     new APIKeyAuthProvider('fallback-key'), // Fallback to API key
 *   ],
 *   mergeHeaders: false,
 *   stopAtFirst: true
 * });
 * ```
 */
export class UnifiedAuthWrapper extends AuthProvider {
  private providers: AuthProvider[];
  private mergeHeaders: boolean;
  private stopAtFirst: boolean;

  constructor(config: UnifiedAuthConfig) {
    super();

    if (!config.providers || config.providers.length === 0) {
      throw new Error('UnifiedAuthWrapper: At least one provider required');
    }

    this.providers = config.providers;
    this.mergeHeaders = config.mergeHeaders !== false; // default true
    this.stopAtFirst = config.stopAtFirst || false;
  }

  /**
   * Get headers synchronously
   */
  getHeadersSync(): Record<string, string> {
    if (this.mergeHeaders) {
      // Merge headers from all providers
      const allHeaders: Record<string, string> = {};

      for (const provider of this.providers) {
        try {
          const headers = provider.getHeadersSync();
          Object.assign(allHeaders, headers);
        } catch (error) {
          // Ignore errors if merging
          continue;
        }
      }

      return allHeaders;
    } else {
      // Use first successful provider
      for (const provider of this.providers) {
        try {
          const headers = provider.getHeadersSync();
          if (this.stopAtFirst && Object.keys(headers).length > 0) {
            return headers;
          }
        } catch (error) {
          continue;
        }
      }

      throw new Error('UnifiedAuthWrapper: All providers failed');
    }
  }

  /**
   * Get headers asynchronously
   */
  async getHeadersAsync(): Promise<Record<string, string>> {
    if (this.mergeHeaders) {
      // Merge headers from all providers
      const allHeaders: Record<string, string> = {};

      for (const provider of this.providers) {
        try {
          const headers = await provider.getHeadersAsync();
          Object.assign(allHeaders, headers);
        } catch (error) {
          // Ignore errors if merging
          continue;
        }
      }

      return allHeaders;
    } else {
      // Use first successful provider
      for (const provider of this.providers) {
        try {
          const headers = await provider.getHeadersAsync();
          if (this.stopAtFirst && Object.keys(headers).length > 0) {
            return headers;
          }
        } catch (error) {
          continue;
        }
      }

      throw new Error('UnifiedAuthWrapper: All providers failed');
    }
  }

  /**
   * Should retry on unauthorized
   * Returns true if ANY provider can retry
   */
  shouldRetryOnUnauthorized(): boolean {
    return this.providers.some(p => p.shouldRetryOnUnauthorized());
  }

  /**
   * Handle unauthorized synchronously
   */
  handleUnauthorizedSync(): void {
    // Attempt to refresh all providers that support it
    for (const provider of this.providers) {
      if (provider.shouldRetryOnUnauthorized()) {
        try {
          provider.handleUnauthorizedSync();
        } catch (error) {
          // Continue to next provider
          continue;
        }
      }
    }
  }

  /**
   * Handle unauthorized asynchronously
   */
  async handleUnauthorizedAsync(): Promise<void> {
    // Attempt to refresh all providers that support it
    const refreshPromises: Promise<void>[] = [];

    for (const provider of this.providers) {
      if (provider.shouldRetryOnUnauthorized()) {
        refreshPromises.push(
          provider.handleUnauthorizedAsync().catch(() => {
            // Ignore individual failures
          })
        );
      }
    }

    await Promise.all(refreshPromises);
  }

  /**
   * Add a provider to the chain
   */
  addProvider(provider: AuthProvider, priority: 'high' | 'low' = 'low'): void {
    if (priority === 'high') {
      this.providers.unshift(provider);
    } else {
      this.providers.push(provider);
    }
  }

  /**
   * Remove a provider from the chain
   */
  removeProvider(provider: AuthProvider): void {
    const index = this.providers.indexOf(provider);
    if (index > -1) {
      this.providers.splice(index, 1);
    }
  }

  /**
   * Get all providers
   */
  getProviders(): AuthProvider[] {
    return [...this.providers];
  }

  /**
   * Get count of providers
   */
  getProviderCount(): number {
    return this.providers.length;
  }

  /**
   * Clear all providers
   */
  clearProviders(): void {
    this.providers = [];
  }
}
