/**
 * Tool Metrics System
 * 
 * Tracks tool execution performance:
 * - Success/failure counts
 * - Latency statistics
 * - Success rates
 * - Consecutive failures
 * - Execution history
 */

/**
 * Single tool execution record
 */
export interface ToolExecution {
  /** Timestamp when tool was executed */
  timestamp: number;
  
  /** Execution duration in milliseconds */
  latencyMs: number;
  
  /** Whether execution was successful */
  success: boolean;
  
  /** Error message if failed */
  error?: string;
}

/**
 * Tool Metrics.
 * 
 * Tracks performance metrics for a single tool.
 * Useful for monitoring, debugging, and optimization.
 * 
 * Features:
 * - Success/failure tracking
 * - Latency statistics (min, max, avg, p50, p95, p99)
 * - Success rate calculation
 * - Consecutive failure detection
 * - Execution history
 * 
 * Example:
 * ```typescript
 * const metrics = new ToolMetrics('my_tool');
 * 
 * // Track successful execution
 * const start = Date.now();
 * // ... execute tool ...
 * const duration = Date.now() - start;
 * metrics.recordSuccess(duration);
 * 
 * // Track failed execution
 * try {
 *   // ... execute tool ...
 * } catch (error) {
 *   metrics.recordFailure(Date.now() - start, error.message);
 * }
 * 
 * // Get metrics
 * console.log(`Success rate: ${metrics.getSuccessRate()}%`);
 * console.log(`Average latency: ${metrics.getAverageLatency()}ms`);
 * console.log(`Consecutive failures: ${metrics.getConsecutiveFailures()}`);
 * ```
 */
export class ToolMetrics {
  private toolName: string;
  private successCount: number = 0;
  private failureCount: number = 0;
  private consecutiveFailures: number = 0;
  private latencies: number[] = [];
  private executions: ToolExecution[] = [];
  private maxHistorySize: number;

  constructor(toolName: string, maxHistorySize: number = 1000) {
    this.toolName = toolName;
    this.maxHistorySize = maxHistorySize;
  }

  /**
   * Record successful execution
   */
  recordSuccess(latencyMs: number): void {
    this.successCount += 1;
    this.consecutiveFailures = 0;
    this.latencies.push(latencyMs);

    this.executions.push({
      timestamp: Date.now(),
      latencyMs,
      success: true,
    });

    this.trimHistory();
  }

  /**
   * Record failed execution
   */
  recordFailure(latencyMs: number, error?: string): void {
    this.failureCount += 1;
    this.consecutiveFailures += 1;
    this.latencies.push(latencyMs);

    this.executions.push({
      timestamp: Date.now(),
      latencyMs,
      success: false,
      error,
    });

    this.trimHistory();
  }

  /**
   * Trim history to max size
   */
  private trimHistory(): void {
    if (this.executions.length > this.maxHistorySize) {
      this.executions = this.executions.slice(-this.maxHistorySize);
    }

    if (this.latencies.length > this.maxHistorySize) {
      this.latencies = this.latencies.slice(-this.maxHistorySize);
    }
  }

  /**
   * Get tool name
   */
  getToolName(): string {
    return this.toolName;
  }

  /**
   * Get success count
   */
  getSuccessCount(): number {
    return this.successCount;
  }

  /**
   * Get failure count
   */
  getFailureCount(): number {
    return this.failureCount;
  }

  /**
   * Get total execution count
   */
  getTotalCount(): number {
    return this.successCount + this.failureCount;
  }

  /**
   * Get success rate (0-100)
   */
  getSuccessRate(): number {
    const total = this.getTotalCount();
    if (total === 0) return 0;
    return (this.successCount / total) * 100;
  }

  /**
   * Get consecutive failures
   */
  getConsecutiveFailures(): number {
    return this.consecutiveFailures;
  }

  /**
   * Get minimum latency
   */
  getMinLatency(): number | null {
    if (this.latencies.length === 0) return null;
    return Math.min(...this.latencies);
  }

  /**
   * Get maximum latency
   */
  getMaxLatency(): number | null {
    if (this.latencies.length === 0) return null;
    return Math.max(...this.latencies);
  }

  /**
   * Get average latency
   */
  getAverageLatency(): number | null {
    if (this.latencies.length === 0) return null;
    const sum = this.latencies.reduce((a, b) => a + b, 0);
    return sum / this.latencies.length;
  }

  /**
   * Get latency percentile
   */
  getLatencyPercentile(percentile: number): number | null {
    if (this.latencies.length === 0) return null;

    const sorted = [...this.latencies].sort((a, b) => a - b);
    const index = Math.ceil((percentile / 100) * sorted.length) - 1;
    return sorted[Math.max(0, index)];
  }

  /**
   * Get P50 (median) latency
   */
  getP50Latency(): number | null {
    return this.getLatencyPercentile(50);
  }

  /**
   * Get P95 latency
   */
  getP95Latency(): number | null {
    return this.getLatencyPercentile(95);
  }

  /**
   * Get P99 latency
   */
  getP99Latency(): number | null {
    return this.getLatencyPercentile(99);
  }

  /**
   * Get recent executions (last N)
   */
  getRecentExecutions(count: number = 10): ToolExecution[] {
    return this.executions.slice(-count);
  }

  /**
   * Get recent success rate (last N executions)
   */
  getRecentSuccessRate(count: number = 10): number {
    const recent = this.getRecentExecutions(count);
    if (recent.length === 0) return 0;

    const successes = recent.filter(e => e.success).length;
    return (successes / recent.length) * 100;
  }

  /**
   * Check if tool is healthy (success rate > threshold)
   */
  isHealthy(threshold: number = 80): boolean {
    return this.getSuccessRate() >= threshold;
  }

  /**
   * Check if tool is degraded (consecutive failures)
   */
  isDegraded(maxConsecutiveFailures: number = 3): boolean {
    return this.consecutiveFailures >= maxConsecutiveFailures;
  }

  /**
   * Reset metrics
   */
  reset(): void {
    this.successCount = 0;
    this.failureCount = 0;
    this.consecutiveFailures = 0;
    this.latencies = [];
    this.executions = [];
  }

  /**
   * Get summary statistics
   */
  getSummary(): {
    toolName: string;
    totalExecutions: number;
    successCount: number;
    failureCount: number;
    successRate: number;
    consecutiveFailures: number;
    latency: {
      min: number | null;
      max: number | null;
      avg: number | null;
      p50: number | null;
      p95: number | null;
      p99: number | null;
    };
    health: {
      isHealthy: boolean;
      isDegraded: boolean;
    };
  } {
    return {
      toolName: this.toolName,
      totalExecutions: this.getTotalCount(),
      successCount: this.successCount,
      failureCount: this.failureCount,
      successRate: this.getSuccessRate(),
      consecutiveFailures: this.consecutiveFailures,
      latency: {
        min: this.getMinLatency(),
        max: this.getMaxLatency(),
        avg: this.getAverageLatency(),
        p50: this.getP50Latency(),
        p95: this.getP95Latency(),
        p99: this.getP99Latency(),
      },
      health: {
        isHealthy: this.isHealthy(),
        isDegraded: this.isDegraded(),
      },
    };
  }

  /**
   * Export to JSON
   */
  toJSON(): any {
    return {
      toolName: this.toolName,
      successCount: this.successCount,
      failureCount: this.failureCount,
      consecutiveFailures: this.consecutiveFailures,
      latencies: this.latencies,
      executions: this.executions,
      summary: this.getSummary(),
    };
  }

  /**
   * Create from JSON
   */
  static fromJSON(data: any): ToolMetrics {
    const metrics = new ToolMetrics(data.toolName);
    metrics.successCount = data.successCount || 0;
    metrics.failureCount = data.failureCount || 0;
    metrics.consecutiveFailures = data.consecutiveFailures || 0;
    metrics.latencies = data.latencies || [];
    metrics.executions = data.executions || [];
    return metrics;
  }
}

/**
 * Collection of metrics for multiple tools
 */
export class ToolMetricsCollection {
  private metrics: Map<string, ToolMetrics> = new Map();

  /**
   * Get or create metrics for a tool
   */
  getMetrics(toolName: string): ToolMetrics {
    if (!this.metrics.has(toolName)) {
      this.metrics.set(toolName, new ToolMetrics(toolName));
    }
    return this.metrics.get(toolName)!;
  }

  /**
   * Record successful execution
   */
  recordSuccess(toolName: string, latencyMs: number): void {
    this.getMetrics(toolName).recordSuccess(latencyMs);
  }

  /**
   * Record failed execution
   */
  recordFailure(toolName: string, latencyMs: number, error?: string): void {
    this.getMetrics(toolName).recordFailure(latencyMs, error);
  }

  /**
   * Get all tool names
   */
  getToolNames(): string[] {
    return Array.from(this.metrics.keys());
  }

  /**
   * Get all metrics
   */
  getAllMetrics(): ToolMetrics[] {
    return Array.from(this.metrics.values());
  }

  /**
   * Get summary for all tools
   */
  getAllSummaries(): any[] {
    return this.getAllMetrics().map(m => m.getSummary());
  }

  /**
   * Get unhealthy tools
   */
  getUnhealthyTools(threshold: number = 80): string[] {
    return this.getAllMetrics()
      .filter(m => !m.isHealthy(threshold))
      .map(m => m.getToolName());
  }

  /**
   * Get degraded tools
   */
  getDegradedTools(maxConsecutiveFailures: number = 3): string[] {
    return this.getAllMetrics()
      .filter(m => m.isDegraded(maxConsecutiveFailures))
      .map(m => m.getToolName());
  }

  /**
   * Reset all metrics
   */
  resetAll(): void {
    this.metrics.clear();
  }

  /**
   * Reset specific tool metrics
   */
  reset(toolName: string): void {
    this.metrics.delete(toolName);
  }

  /**
   * Export to JSON
   */
  toJSON(): any {
    const data: any = {};
    for (const [name, metrics] of this.metrics.entries()) {
      data[name] = metrics.toJSON();
    }
    return data;
  }

  /**
   * Create from JSON
   */
  static fromJSON(data: any): ToolMetricsCollection {
    const collection = new ToolMetricsCollection();
    for (const [name, metricsData] of Object.entries(data)) {
      collection.metrics.set(name, ToolMetrics.fromJSON(metricsData));
    }
    return collection;
  }
}
