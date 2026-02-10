/**
 * MCP URL Utilities
 * 
 * Utilities for normalizing and constructing MCP server URLs.
 * Ensures consistent URL handling across the codebase.
 */

/**
 * MCP Base URL class.
 * Handles URL normalization and endpoint construction.
 * 
 * Features:
 * - URL normalization (trailing slashes, protocol)
 * - Endpoint URL construction
 * - URL validation
 * 
 * Example:
 * ```typescript
 * const base = MCPBaseURL.normalize('https://api.example.com/');
 * 
 * base.listToolsUrl();
 * // 'https://api.example.com/list_tools'
 * 
 * base.invokeUrl('my_tool');
 * // 'https://api.example.com/invoke/my_tool'
 * ```
 */
export class MCPBaseURL {
  /** Normalized base URL (no trailing slash) */
  public readonly base: string;

  private constructor(base: string) {
    this.base = base;
  }

  /**
   * Normalize and validate URL.
   * Removes trailing slashes and validates format.
   */
  static normalize(url: string): MCPBaseURL {
    if (!url || typeof url !== 'string') {
      throw new Error('URL must be a non-empty string');
    }

    let normalized = url.trim();

    // Validate URL format
    if (!this.isValidUrl(normalized)) {
      throw new Error(`Invalid URL format: ${url}`);
    }

    // Remove trailing slash
    normalized = normalized.replace(/\/+$/, '');

    return new MCPBaseURL(normalized);
  }

  /**
   * Validate URL format.
   * Basic validation for HTTP/HTTPS URLs.
   */
  private static isValidUrl(url: string): boolean {
    try {
      const parsed = new URL(url);
      return ['http:', 'https:'].includes(parsed.protocol);
    } catch {
      return false;
    }
  }

  /**
   * Get list_tools endpoint URL.
   * Used for discovering available tools.
   */
  listToolsUrl(): string {
    return `${this.base}/list_tools`;
  }

  /**
   * Get invoke endpoint URL for a specific tool.
   * Used for executing a tool.
   */
  invokeUrl(toolName: string): string {
    if (!toolName || typeof toolName !== 'string') {
      throw new Error('Tool name must be a non-empty string');
    }

    // Encode tool name for URL safety
    const encoded = encodeURIComponent(toolName.trim());
    return `${this.base}/invoke/${encoded}`;
  }

  /**
   * Get list_resources endpoint URL.
   * Used for discovering available resources (MCP Apps).
   */
  listResourcesUrl(): string {
    return `${this.base}/list_resources`;
  }

  /**
   * Get read_resource endpoint URL.
   * Used for reading a specific resource.
   */
  readResourceUrl(resourceUri: string): string {
    if (!resourceUri || typeof resourceUri !== 'string') {
      throw new Error('Resource URI must be a non-empty string');
    }

    const encoded = encodeURIComponent(resourceUri.trim());
    return `${this.base}/read_resource?uri=${encoded}`;
  }

  /**
   * Get list_prompts endpoint URL (if supported by server).
   */
  listPromptsUrl(): string {
    return `${this.base}/list_prompts`;
  }

  /**
   * Get custom endpoint URL.
   * For server-specific endpoints.
   */
  customUrl(endpoint: string): string {
    if (!endpoint || typeof endpoint !== 'string') {
      throw new Error('Endpoint must be a non-empty string');
    }

    // Remove leading slash if present
    const clean = endpoint.replace(/^\/+/, '');
    return `${this.base}/${clean}`;
  }

  /**
   * Check if this URL matches another URL.
   * Compares base URLs (ignoring paths).
   */
  matches(other: MCPBaseURL | string): boolean {
    const otherBase = typeof other === 'string' 
      ? MCPBaseURL.normalize(other).base 
      : other.base;

    return this.base === otherBase;
  }

  /**
   * Get URL origin (protocol + host).
   */
  origin(): string {
    try {
      const url = new URL(this.base);
      return url.origin;
    } catch {
      return this.base;
    }
  }

  /**
   * Get URL hostname.
   */
  hostname(): string {
    try {
      const url = new URL(this.base);
      return url.hostname;
    } catch {
      return '';
    }
  }

  /**
   * Get URL protocol.
   */
  protocol(): string {
    try {
      const url = new URL(this.base);
      return url.protocol;
    } catch {
      return '';
    }
  }

  /**
   * Check if URL uses HTTPS.
   */
  isSecure(): boolean {
    return this.protocol() === 'https:';
  }

  /**
   * Convert to string (returns base URL).
   */
  toString(): string {
    return this.base;
  }

  /**
   * Create URL with query parameters.
   */
  withQueryParams(endpoint: string, params: Record<string, string>): string {
    const baseUrl = endpoint.startsWith('/') 
      ? `${this.base}${endpoint}`
      : `${this.base}/${endpoint}`;

    if (Object.keys(params).length === 0) {
      return baseUrl;
    }

    const searchParams = new URLSearchParams(params);
    return `${baseUrl}?${searchParams.toString()}`;
  }
}

/**
 * URL Builder for MCP endpoints.
 * Fluent API for constructing URLs.
 */
export class MCPURLBuilder {
  private baseUrl: MCPBaseURL;
  private path: string = '';
  private params: Record<string, string> = {};

  constructor(baseUrl: string | MCPBaseURL) {
    this.baseUrl = typeof baseUrl === 'string' 
      ? MCPBaseURL.normalize(baseUrl)
      : baseUrl;
  }

  /**
   * Add path segment.
   */
  addPath(segment: string): this {
    const clean = segment.replace(/^\/+|\/+$/g, '');
    this.path = this.path ? `${this.path}/${clean}` : clean;
    return this;
  }

  /**
   * Add query parameter.
   */
  addParam(key: string, value: string): this {
    this.params[key] = value;
    return this;
  }

  /**
   * Add multiple query parameters.
   */
  addParams(params: Record<string, string>): this {
    Object.assign(this.params, params);
    return this;
  }

  /**
   * Build final URL.
   */
  build(): string {
    let url = this.baseUrl.base;

    if (this.path) {
      url = `${url}/${this.path}`;
    }

    if (Object.keys(this.params).length > 0) {
      const searchParams = new URLSearchParams(this.params);
      url = `${url}?${searchParams.toString()}`;
    }

    return url;
  }

  /**
   * Reset builder.
   */
  reset(): this {
    this.path = '';
    this.params = {};
    return this;
  }
}

/**
 * Parse MCP URL to extract components.
 */
export function parseMCPUrl(url: string): {
  base: string;
  endpoint: string;
  toolName?: string;
  params: Record<string, string>;
} {
  try {
    const parsed = new URL(url);
    const base = `${parsed.protocol}//${parsed.host}`;
    const path = parsed.pathname;
    
    // Extract endpoint and tool name
    const pathParts = path.split('/').filter(Boolean);
    const endpoint = pathParts[0] || '';
    const toolName = endpoint === 'invoke' ? pathParts[1] : undefined;

    // Extract query params
    const params: Record<string, string> = {};
    parsed.searchParams.forEach((value, key) => {
      params[key] = value;
    });

    return {
      base,
      endpoint,
      toolName,
      params,
    };
  } catch (error) {
    throw new Error(`Failed to parse MCP URL: ${url}`);
  }
}

/**
 * Join URL parts safely.
 * Handles trailing/leading slashes automatically.
 */
export function joinUrlParts(...parts: string[]): string {
  return parts
    .map((part, index) => {
      let clean = part.trim();
      
      // Remove trailing slash (except for last part if it ends with /)
      if (index < parts.length - 1) {
        clean = clean.replace(/\/+$/, '');
      }
      
      // Remove leading slash (except for first part)
      if (index > 0) {
        clean = clean.replace(/^\/+/, '');
      }
      
      return clean;
    })
    .filter(Boolean)
    .join('/');
}

/**
 * Check if URL is a valid MCP server URL.
 */
export function isValidMCPUrl(url: string): boolean {
  try {
    MCPBaseURL.normalize(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Compare two URLs for equality (ignoring trailing slashes).
 */
export function urlsEqual(url1: string, url2: string): boolean {
  try {
    const base1 = MCPBaseURL.normalize(url1);
    const base2 = MCPBaseURL.normalize(url2);
    return base1.matches(base2);
  } catch {
    return false;
  }
}
