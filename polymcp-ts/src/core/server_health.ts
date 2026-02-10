/**
 * Server Health & Circuit Breaker System
 * 
 * Tracks server health and implements circuit breaker pattern:
 * - Health status monitoring (HEALTHY, DEGRADED, UNHEALTHY, CIRCUIT_OPEN)
 * - Automatic circuit breaking on repeated failures
 * - Auto-recovery after timeout
 * - Failure threshold detection
 * - Request blocking when circuit is open
 */

/**
 * Health status enum
 */
export enum HealthStatus {
  /** Server is healthy and operating normally */
  HEALTHY = 'HEALTHY',
  
  /** Server is experiencing some issues but still functional */
  DEGRADED = 'DEGRADED',
  
  /** Server is unhealthy with high failure rate */
  UNHEALTHY = 'UNHEALTHY',
  
  /** Circuit breaker is open, blocking all requests */
  CIRCUIT_OPEN = 'CIRCUIT_OPEN',
}

/**
 * Circuit breaker configuration
 */
export interface CircuitBreakerConfig {
  /** Number of consecutive failures to open circuit (default: 5) */
  failureThreshold?: number;
  
  /** Minimum requests before circuit can open (default: 10) */
  minRequests?: number;
  
  /** Error rate percentage to open circuit (default: 50) */
  errorRateThreshold?: number;
  
  /** Time window for error rate calculation in ms (default: 60000 = 1 min) */
  errorRateWindow?: number;
  
  /** Timeout before attempting recovery in ms (default: 30000 = 30s) */
  recoveryTimeout?: number;
  
  /** Number of successful requests to close circuit (default: 3) */
  recoveryThreshold?: number;
}

/**
 * Request record for tracking
 */
interface RequestRecord {
  timestamp: number;
  success: boolean;
}

/**
 * Server Health Metrics.
 * 
 * Monitors server health and implements circuit breaker pattern.
 * Prevents cascading failures by blocking requests to failing servers.
 * 
 * Features:
 * - Health status tracking (HEALTHY, DEGRADED, UNHEALTHY, CIRCUIT_OPEN)
 * - Consecutive failure detection
 * - Error rate monitoring
 * - Automatic circuit breaking
 * - Auto-recovery with timeout
 * - Half-open state for testing recovery
 * 
 * Example:
 * ```typescript
 * const health = new ServerHealthMetrics('https://api.example.com', {
 *   failureThreshold: 5,
 *   errorRateThreshold: 50,
 *   recoveryTimeout: 30000
 * });
 * 
 * // Before making request
 * if (!health.canExecute()) {
 *   console.log('Circuit is open, blocking request');
 *   return;
 * }
 * 
 * // Record result
 * try {
 *   const result = await makeRequest();
 *   health.recordSuccess();
 * } catch (error) {
 *   health.recordFailure();
 *   if (health.isCircuitOpen()) {
 *     console.log('Circuit breaker opened!');
 *   }
 * }
 * 
 * // Check health
 * console.log(`Status: ${health.getStatus()}`);
 * console.log(`Error rate: ${health.getErrorRate()}%`);
 * ```
 */
export class ServerHealthMetrics {
  private serverUrl: string;
  private config: Required<CircuitBreakerConfig>;
  
  // State
  private status: HealthStatus = HealthStatus.HEALTHY;
  private consecutiveFailures: number = 0;
  private consecutiveSuccesses: number = 0;
  private circuitOpenedAt: number = 0;
  
  // Request history
  private requests: RequestRecord[] = [];
  private maxHistorySize: number = 1000;

  constructor(
    serverUrl: string,
    config: CircuitBreakerConfig = {}
  ) {
    this.serverUrl = serverUrl;
    
    // Set defaults
    this.config = {
      failureThreshold: config.failureThreshold || 5,
      minRequests: config.minRequests || 10,
      errorRateThreshold: config.errorRateThreshold || 50,
      errorRateWindow: config.errorRateWindow || 60000, // 1 minute
      recoveryTimeout: config.recoveryTimeout || 30000, // 30 seconds
      recoveryThreshold: config.recoveryThreshold || 3,
    };
  }

  /**
   * Record successful request
   */
  recordSuccess(): void {
    this.consecutiveFailures = 0;
    this.consecutiveSuccesses += 1;
    
    this.requests.push({
      timestamp: Date.now(),
      success: true,
    });
    
    this.trimHistory();
    this.updateStatus();
  }

  /**
   * Record failed request
   */
  recordFailure(): void {
    this.consecutiveFailures += 1;
    this.consecutiveSuccesses = 0;
    
    this.requests.push({
      timestamp: Date.now(),
      success: false,
    });
    
    this.trimHistory();
    this.updateStatus();
  }

  /**
   * Trim history to max size
   */
  private trimHistory(): void {
    if (this.requests.length > this.maxHistorySize) {
      this.requests = this.requests.slice(-this.maxHistorySize);
    }
  }

  /**
   * Update health status based on metrics
   */
  private updateStatus(): void {
    // Check if circuit should open
    if (this.shouldOpenCircuit()) {
      this.openCircuit();
      return;
    }

    // Check if circuit can close (recovery)
    if (this.status === HealthStatus.CIRCUIT_OPEN) {
      if (this.canAttemptRecovery()) {
        this.attemptRecovery();
      }
      return;
    }

    // Update health status based on error rate
    const errorRate = this.getErrorRate();
    const totalRequests = this.getTotalRequests();

    if (totalRequests < this.config.minRequests) {
      // Not enough data yet
      this.status = HealthStatus.HEALTHY;
    } else if (errorRate >= this.config.errorRateThreshold) {
      this.status = HealthStatus.UNHEALTHY;
    } else if (errorRate >= this.config.errorRateThreshold * 0.5) {
      this.status = HealthStatus.DEGRADED;
    } else {
      this.status = HealthStatus.HEALTHY;
    }
  }

  /**
   * Check if circuit should open
   */
  private shouldOpenCircuit(): boolean {
    // Circuit already open
    if (this.status === HealthStatus.CIRCUIT_OPEN) {
      return false;
    }

    // Check consecutive failures
    if (this.consecutiveFailures >= this.config.failureThreshold) {
      return true;
    }

    // Check error rate (only if we have enough requests)
    const totalRequests = this.getTotalRequests();
    if (totalRequests >= this.config.minRequests) {
      const errorRate = this.getErrorRate();
      if (errorRate >= this.config.errorRateThreshold) {
        return true;
      }
    }

    return false;
  }

  /**
   * Open circuit breaker
   */
  private openCircuit(): void {
    this.status = HealthStatus.CIRCUIT_OPEN;
    this.circuitOpenedAt = Date.now();
  }

  /**
   * Check if we can attempt recovery
   */
  private canAttemptRecovery(): boolean {
    if (this.circuitOpenedAt === 0) return false;
    
    const elapsed = Date.now() - this.circuitOpenedAt;
    return elapsed >= this.config.recoveryTimeout;
  }

  /**
   * Attempt recovery (half-open state)
   */
  private attemptRecovery(): void {
    // Reset consecutive counters for recovery attempt
    this.consecutiveFailures = 0;
    this.consecutiveSuccesses = 0;
    
    // Move to DEGRADED state (half-open)
    this.status = HealthStatus.DEGRADED;
    this.circuitOpenedAt = 0;
  }

  /**
   * Check if circuit is recovering (half-open)
   */
  isRecovering(): boolean {
    return this.status === HealthStatus.DEGRADED && 
           this.consecutiveSuccesses > 0 &&
           this.consecutiveSuccesses < this.config.recoveryThreshold;
  }

  /**
   * Get current health status
   */
  getStatus(): HealthStatus {
    return this.status;
  }

  /**
   * Check if circuit is open
   */
  isCircuitOpen(): boolean {
    return this.status === HealthStatus.CIRCUIT_OPEN;
  }

  /**
   * Check if server is healthy
   */
  isHealthy(): boolean {
    return this.status === HealthStatus.HEALTHY;
  }

  /**
   * Check if server is degraded
   */
  isDegraded(): boolean {
    return this.status === HealthStatus.DEGRADED;
  }

  /**
   * Check if server is unhealthy
   */
  isUnhealthy(): boolean {
    return this.status === HealthStatus.UNHEALTHY;
  }

  /**
   * Check if request can be executed
   */
  canExecute(): boolean {
    // Block all requests if circuit is open
    if (this.isCircuitOpen()) {
      // Check if we can attempt recovery
      if (this.canAttemptRecovery()) {
        this.attemptRecovery();
        return true; // Allow one request to test
      }
      return false;
    }
    
    return true;
  }

  /**
   * Get consecutive failures
   */
  getConsecutiveFailures(): number {
    return this.consecutiveFailures;
  }

  /**
   * Get consecutive successes
   */
  getConsecutiveSuccesses(): number {
    return this.consecutiveSuccesses;
  }

  /**
   * Get total requests
   */
  getTotalRequests(): number {
    return this.requests.length;
  }

  /**
   * Get requests in time window
   */
  private getRequestsInWindow(): RequestRecord[] {
    const now = Date.now();
    const cutoff = now - this.config.errorRateWindow;
    return this.requests.filter(r => r.timestamp >= cutoff);
  }

  /**
   * Get error rate (0-100) in time window
   */
  getErrorRate(): number {
    const windowRequests = this.getRequestsInWindow();
    if (windowRequests.length === 0) return 0;
    
    const failures = windowRequests.filter(r => !r.success).length;
    return (failures / windowRequests.length) * 100;
  }

  /**
   * Get time until circuit can recover
   */
  getTimeUntilRecovery(): number {
    if (!this.isCircuitOpen()) return 0;
    if (this.circuitOpenedAt === 0) return 0;
    
    const elapsed = Date.now() - this.circuitOpenedAt;
    const remaining = this.config.recoveryTimeout - elapsed;
    return Math.max(0, remaining);
  }

  /**
   * Force circuit open (for testing/manual intervention)
   */
  forceOpen(): void {
    this.openCircuit();
  }

  /**
   * Force circuit close (for testing/manual intervention)
   */
  forceClose(): void {
    this.status = HealthStatus.HEALTHY;
    this.circuitOpenedAt = 0;
    this.consecutiveFailures = 0;
    this.consecutiveSuccesses = 0;
  }

  /**
   * Reset all metrics
   */
  reset(): void {
    this.status = HealthStatus.HEALTHY;
    this.consecutiveFailures = 0;
    this.consecutiveSuccesses = 0;
    this.circuitOpenedAt = 0;
    this.requests = [];
  }

  /**
   * Get summary
   */
  getSummary(): {
    serverUrl: string;
    status: HealthStatus;
    consecutiveFailures: number;
    consecutiveSuccesses: number;
    errorRate: number;
    totalRequests: number;
    canExecute: boolean;
    isRecovering: boolean;
    timeUntilRecovery: number;
  } {
    return {
      serverUrl: this.serverUrl,
      status: this.status,
      consecutiveFailures: this.consecutiveFailures,
      consecutiveSuccesses: this.consecutiveSuccesses,
      errorRate: this.getErrorRate(),
      totalRequests: this.getTotalRequests(),
      canExecute: this.canExecute(),
      isRecovering: this.isRecovering(),
      timeUntilRecovery: this.getTimeUntilRecovery(),
    };
  }

  /**
   * Export to JSON
   */
  toJSON(): any {
    return {
      serverUrl: this.serverUrl,
      config: this.config,
      status: this.status,
      consecutiveFailures: this.consecutiveFailures,
      consecutiveSuccesses: this.consecutiveSuccesses,
      circuitOpenedAt: this.circuitOpenedAt,
      requests: this.requests,
      summary: this.getSummary(),
    };
  }

  /**
   * Create from JSON
   */
  static fromJSON(data: any): ServerHealthMetrics {
    const health = new ServerHealthMetrics(data.serverUrl, data.config);
    health.status = data.status || HealthStatus.HEALTHY;
    health.consecutiveFailures = data.consecutiveFailures || 0;
    health.consecutiveSuccesses = data.consecutiveSuccesses || 0;
    health.circuitOpenedAt = data.circuitOpenedAt || 0;
    health.requests = data.requests || [];
    return health;
  }
}

/**
 * Collection of health metrics for multiple servers
 */
export class ServerHealthCollection {
  private healthMetrics: Map<string, ServerHealthMetrics> = new Map();
  private defaultConfig: CircuitBreakerConfig;

  constructor(defaultConfig: CircuitBreakerConfig = {}) {
    this.defaultConfig = defaultConfig;
  }

  /**
   * Get or create health metrics for a server
   */
  getHealth(serverUrl: string): ServerHealthMetrics {
    if (!this.healthMetrics.has(serverUrl)) {
      this.healthMetrics.set(
        serverUrl,
        new ServerHealthMetrics(serverUrl, this.defaultConfig)
      );
    }
    return this.healthMetrics.get(serverUrl)!;
  }

  /**
   * Record successful request
   */
  recordSuccess(serverUrl: string): void {
    this.getHealth(serverUrl).recordSuccess();
  }

  /**
   * Record failed request
   */
  recordFailure(serverUrl: string): void {
    this.getHealth(serverUrl).recordFailure();
  }

  /**
   * Check if request can be executed
   */
  canExecute(serverUrl: string): boolean {
    return this.getHealth(serverUrl).canExecute();
  }

  /**
   * Get all server URLs
   */
  getServerUrls(): string[] {
    return Array.from(this.healthMetrics.keys());
  }

  /**
   * Get unhealthy servers
   */
  getUnhealthyServers(): string[] {
    return Array.from(this.healthMetrics.entries())
      .filter(([_, health]) => health.isUnhealthy() || health.isCircuitOpen())
      .map(([url, _]) => url);
  }

  /**
   * Get servers with open circuits
   */
  getOpenCircuitServers(): string[] {
    return Array.from(this.healthMetrics.entries())
      .filter(([_, health]) => health.isCircuitOpen())
      .map(([url, _]) => url);
  }

  /**
   * Get all summaries
   */
  getAllSummaries(): any[] {
    return Array.from(this.healthMetrics.values()).map(h => h.getSummary());
  }

  /**
   * Reset all
   */
  resetAll(): void {
    this.healthMetrics.clear();
  }

  /**
   * Reset specific server
   */
  reset(serverUrl: string): void {
    this.healthMetrics.delete(serverUrl);
  }

  /**
   * Export to JSON
   */
  toJSON(): any {
    const data: any = {};
    for (const [url, health] of this.healthMetrics.entries()) {
      data[url] = health.toJSON();
    }
    return data;
  }

  /**
   * Create from JSON
   */
  static fromJSON(data: any): ServerHealthCollection {
    const collection = new ServerHealthCollection();
    for (const [url, healthData] of Object.entries(data)) {
      collection.healthMetrics.set(url, ServerHealthMetrics.fromJSON(healthData));
    }
    return collection;
  }
}
