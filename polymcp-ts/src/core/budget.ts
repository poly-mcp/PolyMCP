/**
 * Budget System
 * 
 * Tracks and enforces resource limits:
 * - Wall time (execution duration)
 * - Token consumption
 * - Tool call count
 * - Payload size
 * 
 * Prevents runaway execution and excessive resource usage.
 */

/**
 * Budget configuration
 */
export interface BudgetConfig {
  /** Maximum wall time in seconds (0 = unlimited) */
  maxWallTime?: number;
  
  /** Maximum tokens to consume (0 = unlimited) */
  maxTokens?: number;
  
  /** Maximum number of tool calls (0 = unlimited) */
  maxToolCalls?: number;
  
  /** Maximum payload size in bytes (0 = unlimited) */
  maxPayloadBytes?: number;
}

/**
 * Budget usage statistics
 */
export interface BudgetUsage {
  /** Wall time used in seconds */
  wallTimeUsed: number;
  
  /** Tokens consumed */
  tokensUsed: number;
  
  /** Number of tool calls made */
  toolCallsMade: number;
  
  /** Total payload size in bytes */
  payloadBytesUsed: number;
  
  /** Timestamp when tracking started */
  startTime: number;
}

/**
 * Budget System.
 * 
 * Tracks resource consumption and enforces limits.
 * Useful for preventing runaway agents and managing costs.
 * 
 * Features:
 * - Wall time tracking
 * - Token consumption tracking
 * - Tool call counting
 * - Payload size monitoring
 * - Automatic limit enforcement
 * - Reset capability
 * 
 * Example:
 * ```typescript
 * const budget = new Budget({
 *   maxWallTime: 300,      // 5 minutes
 *   maxTokens: 100000,     // 100k tokens
 *   maxToolCalls: 50,      // 50 tool calls
 *   maxPayloadBytes: 10 * 1024 * 1024  // 10 MB
 * });
 * 
 * // Track usage
 * budget.trackTokens(1500);
 * budget.trackToolCall();
 * budget.trackPayload(2048);
 * 
 * // Check if exceeded
 * if (budget.isExceeded()) {
 *   const reason = budget.getExceededReason();
 *   console.log(`Budget exceeded: ${reason}`);
 * }
 * 
 * // Reset for new run
 * budget.reset();
 * ```
 */
export class Budget {
  private config: Required<BudgetConfig>;
  private usage: BudgetUsage;

  constructor(config: BudgetConfig = {}) {
    // Set defaults (0 = unlimited)
    this.config = {
      maxWallTime: config.maxWallTime || 0,
      maxTokens: config.maxTokens || 0,
      maxToolCalls: config.maxToolCalls || 0,
      maxPayloadBytes: config.maxPayloadBytes || 0,
    };

    // Initialize usage tracking
    this.usage = {
      wallTimeUsed: 0,
      tokensUsed: 0,
      toolCallsMade: 0,
      payloadBytesUsed: 0,
      startTime: Date.now(),
    };
  }

  /**
   * Track token consumption
   */
  trackTokens(tokens: number): void {
    this.usage.tokensUsed += tokens;
  }

  /**
   * Track a tool call
   */
  trackToolCall(): void {
    this.usage.toolCallsMade += 1;
  }

  /**
   * Track payload size
   */
  trackPayload(bytes: number): void {
    this.usage.payloadBytesUsed += bytes;
  }

  /**
   * Update wall time (called periodically or at end)
   */
  updateWallTime(): void {
    const now = Date.now();
    this.usage.wallTimeUsed = (now - this.usage.startTime) / 1000; // Convert to seconds
  }

  /**
   * Get current wall time used (in seconds)
   */
  getWallTimeUsed(): number {
    this.updateWallTime();
    return this.usage.wallTimeUsed;
  }

  /**
   * Check if budget is exceeded
   */
  isExceeded(): boolean {
    this.updateWallTime();

    // Check wall time
    if (this.config.maxWallTime > 0 && this.usage.wallTimeUsed >= this.config.maxWallTime) {
      return true;
    }

    // Check tokens
    if (this.config.maxTokens > 0 && this.usage.tokensUsed >= this.config.maxTokens) {
      return true;
    }

    // Check tool calls
    if (this.config.maxToolCalls > 0 && this.usage.toolCallsMade >= this.config.maxToolCalls) {
      return true;
    }

    // Check payload size
    if (this.config.maxPayloadBytes > 0 && this.usage.payloadBytesUsed >= this.config.maxPayloadBytes) {
      return true;
    }

    return false;
  }

  /**
   * Get reason why budget was exceeded
   */
  getExceededReason(): string | null {
    this.updateWallTime();

    const reasons: string[] = [];

    if (this.config.maxWallTime > 0 && this.usage.wallTimeUsed >= this.config.maxWallTime) {
      reasons.push(`Wall time exceeded (${this.usage.wallTimeUsed.toFixed(2)}s / ${this.config.maxWallTime}s)`);
    }

    if (this.config.maxTokens > 0 && this.usage.tokensUsed >= this.config.maxTokens) {
      reasons.push(`Tokens exceeded (${this.usage.tokensUsed} / ${this.config.maxTokens})`);
    }

    if (this.config.maxToolCalls > 0 && this.usage.toolCallsMade >= this.config.maxToolCalls) {
      reasons.push(`Tool calls exceeded (${this.usage.toolCallsMade} / ${this.config.maxToolCalls})`);
    }

    if (this.config.maxPayloadBytes > 0 && this.usage.payloadBytesUsed >= this.config.maxPayloadBytes) {
      const mb = (this.usage.payloadBytesUsed / (1024 * 1024)).toFixed(2);
      const maxMb = (this.config.maxPayloadBytes / (1024 * 1024)).toFixed(2);
      reasons.push(`Payload size exceeded (${mb} MB / ${maxMb} MB)`);
    }

    return reasons.length > 0 ? reasons.join(', ') : null;
  }

  /**
   * Get current usage statistics
   */
  getUsage(): BudgetUsage {
    this.updateWallTime();
    return { ...this.usage };
  }

  /**
   * Get budget configuration
   */
  getConfig(): BudgetConfig {
    return { ...this.config };
  }

  /**
   * Get remaining budget
   */
  getRemaining(): {
    wallTime: number | null;
    tokens: number | null;
    toolCalls: number | null;
    payloadBytes: number | null;
  } {
    this.updateWallTime();

    return {
      wallTime: this.config.maxWallTime > 0 
        ? Math.max(0, this.config.maxWallTime - this.usage.wallTimeUsed)
        : null,
      tokens: this.config.maxTokens > 0 
        ? Math.max(0, this.config.maxTokens - this.usage.tokensUsed)
        : null,
      toolCalls: this.config.maxToolCalls > 0 
        ? Math.max(0, this.config.maxToolCalls - this.usage.toolCallsMade)
        : null,
      payloadBytes: this.config.maxPayloadBytes > 0 
        ? Math.max(0, this.config.maxPayloadBytes - this.usage.payloadBytesUsed)
        : null,
    };
  }

  /**
   * Get usage percentage (0-100)
   */
  getUsagePercentage(): {
    wallTime: number | null;
    tokens: number | null;
    toolCalls: number | null;
    payloadBytes: number | null;
  } {
    this.updateWallTime();

    return {
      wallTime: this.config.maxWallTime > 0 
        ? Math.min(100, (this.usage.wallTimeUsed / this.config.maxWallTime) * 100)
        : null,
      tokens: this.config.maxTokens > 0 
        ? Math.min(100, (this.usage.tokensUsed / this.config.maxTokens) * 100)
        : null,
      toolCalls: this.config.maxToolCalls > 0 
        ? Math.min(100, (this.usage.toolCallsMade / this.config.maxToolCalls) * 100)
        : null,
      payloadBytes: this.config.maxPayloadBytes > 0 
        ? Math.min(100, (this.usage.payloadBytesUsed / this.config.maxPayloadBytes) * 100)
        : null,
    };
  }

  /**
   * Check if budget is close to limit (>80%)
   */
  isNearLimit(): boolean {
    const percentages = this.getUsagePercentage();
    
    return Object.values(percentages).some(pct => pct !== null && pct >= 80);
  }

  /**
   * Reset budget tracking
   */
  reset(): void {
    this.usage = {
      wallTimeUsed: 0,
      tokensUsed: 0,
      toolCallsMade: 0,
      payloadBytesUsed: 0,
      startTime: Date.now(),
    };
  }

  /**
   * Update budget limits
   */
  updateLimits(config: BudgetConfig): void {
    if (config.maxWallTime !== undefined) {
      this.config.maxWallTime = config.maxWallTime;
    }
    if (config.maxTokens !== undefined) {
      this.config.maxTokens = config.maxTokens;
    }
    if (config.maxToolCalls !== undefined) {
      this.config.maxToolCalls = config.maxToolCalls;
    }
    if (config.maxPayloadBytes !== undefined) {
      this.config.maxPayloadBytes = config.maxPayloadBytes;
    }
  }

  /**
   * Export budget state to JSON
   */
  toJSON(): any {
    return {
      config: this.config,
      usage: this.getUsage(),
      remaining: this.getRemaining(),
      percentage: this.getUsagePercentage(),
      exceeded: this.isExceeded(),
      nearLimit: this.isNearLimit(),
    };
  }

  /**
   * Create budget from JSON state
   */
  static fromJSON(data: any): Budget {
    const budget = new Budget(data.config);
    
    if (data.usage) {
      budget.usage = {
        ...data.usage,
        startTime: data.usage.startTime || Date.now(),
      };
    }
    
    return budget;
  }

  /**
   * Create a copy of this budget
   */
  clone(): Budget {
    const cloned = new Budget(this.config);
    cloned.usage = { ...this.usage };
    return cloned;
  }
}

/**
 * Budget Factory for common configurations
 */
export class BudgetFactory {
  /**
   * Create budget for development (generous limits)
   */
  static createDevelopment(): Budget {
    return new Budget({
      maxWallTime: 600,          // 10 minutes
      maxTokens: 500000,         // 500k tokens
      maxToolCalls: 100,         // 100 calls
      maxPayloadBytes: 50 * 1024 * 1024  // 50 MB
    });
  }

  /**
   * Create budget for production (strict limits)
   */
  static createProduction(): Budget {
    return new Budget({
      maxWallTime: 300,          // 5 minutes
      maxTokens: 100000,         // 100k tokens
      maxToolCalls: 50,          // 50 calls
      maxPayloadBytes: 10 * 1024 * 1024  // 10 MB
    });
  }

  /**
   * Create budget for testing (very strict)
   */
  static createTest(): Budget {
    return new Budget({
      maxWallTime: 60,           // 1 minute
      maxTokens: 10000,          // 10k tokens
      maxToolCalls: 10,          // 10 calls
      maxPayloadBytes: 1024 * 1024  // 1 MB
    });
  }

  /**
   * Create unlimited budget (for debugging)
   */
  static createUnlimited(): Budget {
    return new Budget({
      maxWallTime: 0,
      maxTokens: 0,
      maxToolCalls: 0,
      maxPayloadBytes: 0,
    });
  }

  /**
   * Create custom budget
   */
  static createCustom(config: BudgetConfig): Budget {
    return new Budget(config);
  }
}
