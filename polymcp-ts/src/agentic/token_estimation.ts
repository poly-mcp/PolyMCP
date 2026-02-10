/**
 * Token Estimation System
 * 
 * Estimates token count for text to manage context windows:
 * - Accurate token counting
 * - Fallback estimation
 * - Context window management
 * - Text truncation
 * - Token budgeting
 */

/**
 * Token estimator.
 * 
 * Estimates token count for different LLM providers.
 * Helps manage context window limits.
 * 
 * Features:
 * - Provider-specific estimation
 * - Character-based fallback
 * - Text truncation to fit limits
 * - Token budgeting
 * - Batch estimation
 * 
 * Example:
 * ```typescript
 * const estimator = new TokenEstimator('gpt-4');
 * 
 * const text = 'Your long text here...';
 * const tokenCount = estimator.estimateTokens(text);
 * 
 * console.log(`Estimated tokens: ${tokenCount}`);
 * 
 * // Truncate to fit context window
 * const truncated = estimator.truncateToTokenLimit(text, 1000);
 * 
 * // Check if text fits
 * if (estimator.fitsInContext(text, 4096)) {
 *   console.log('Text fits in context window');
 * }
 * ```
 */
export class TokenEstimator {
  private modelName: string;
  private charsPerToken: number = 4; // Average for most models

  // Token limits for common models
  private static readonly MODEL_LIMITS: Record<string, number> = {
    'gpt-4': 8192,
    'gpt-4-32k': 32768,
    'gpt-3.5-turbo': 4096,
    'gpt-3.5-turbo-16k': 16384,
    'claude-2': 100000,
    'claude-instant': 100000,
    'claude-3-opus': 200000,
    'claude-3-sonnet': 200000,
    'claude-3-haiku': 200000,
    'claude-3-5-sonnet': 200000,
    'claude-4-opus': 200000,
    'claude-4-sonnet': 200000,
    'claude-sonnet-4': 200000,
  };

  constructor(modelName: string = 'gpt-4') {
    this.modelName = modelName;
    
    // Adjust chars per token based on model
    if (modelName.includes('claude')) {
      this.charsPerToken = 3.5; // Claude tends to have slightly more efficient tokenization
    } else if (modelName.includes('gpt')) {
      this.charsPerToken = 4;
    }
  }

  /**
   * Estimate token count for text
   */
  estimateTokens(text: string): number {
    if (!text) return 0;

    // Simple character-based estimation
    // This is a fallback when tiktoken is not available
    const charCount = text.length;
    return Math.ceil(charCount / this.charsPerToken);
  }

  /**
   * Estimate tokens for multiple texts
   */
  estimateBatch(texts: string[]): number {
    return texts.reduce((sum, text) => sum + this.estimateTokens(text), 0);
  }

  /**
   * Get context window limit for model
   */
  getContextLimit(): number {
    const limit = TokenEstimator.MODEL_LIMITS[this.modelName];
    return limit || 4096; // Default fallback
  }

  /**
   * Check if text fits in context window
   */
  fitsInContext(text: string, maxTokens?: number): boolean {
    const limit = maxTokens || this.getContextLimit();
    const tokens = this.estimateTokens(text);
    return tokens <= limit;
  }

  /**
   * Truncate text to fit token limit
   */
  truncateToTokenLimit(text: string, maxTokens: number): string {
    const currentTokens = this.estimateTokens(text);
    
    if (currentTokens <= maxTokens) {
      return text;
    }

    // Calculate ratio to truncate
    const ratio = maxTokens / currentTokens;
    const targetLength = Math.floor(text.length * ratio);

    // Truncate and add ellipsis
    return text.substring(0, targetLength) + '...';
  }

  /**
   * Split text into chunks that fit token limit
   */
  chunkText(text: string, maxTokensPerChunk: number, overlap: number = 0): string[] {
    const chunks: string[] = [];
    const totalTokens = this.estimateTokens(text);

    if (totalTokens <= maxTokensPerChunk) {
      return [text];
    }

    const estimatedCharsPerChunk = Math.floor(maxTokensPerChunk * this.charsPerToken);
    const overlapChars = Math.floor(overlap * this.charsPerToken);

    let start = 0;
    while (start < text.length) {
      const end = Math.min(start + estimatedCharsPerChunk, text.length);
      const chunk = text.substring(start, end);
      chunks.push(chunk);

      start = end - overlapChars;
      if (start >= text.length) break;
    }

    return chunks;
  }

  /**
   * Estimate tokens for messages format (chat completion)
   */
  estimateMessages(messages: Array<{ role: string; content: string }>): number {
    // Each message has some overhead (role, formatting)
    const messageOverhead = 4; // Rough estimate
    
    let totalTokens = 0;
    for (const message of messages) {
      totalTokens += messageOverhead;
      totalTokens += this.estimateTokens(message.content);
    }

    return totalTokens;
  }

  /**
   * Calculate remaining tokens in context
   */
  getRemainingTokens(usedText: string, maxTokens?: number): number {
    const limit = maxTokens || this.getContextLimit();
    const used = this.estimateTokens(usedText);
    return Math.max(0, limit - used);
  }

  /**
   * Estimate cost based on tokens (rough estimate)
   */
  estimateCost(
    tokens: number,
    pricePerMillionTokens: number
  ): number {
    return (tokens / 1000000) * pricePerMillionTokens;
  }

  /**
   * Get recommended chunk size for model
   */
  getRecommendedChunkSize(): number {
    const contextLimit = this.getContextLimit();
    
    // Use 80% of context limit to be safe
    return Math.floor(contextLimit * 0.8);
  }

  /**
   * Estimate tokens for structured data (JSON)
   */
  estimateJSON(data: any): number {
    const jsonString = JSON.stringify(data);
    return this.estimateTokens(jsonString);
  }

  /**
   * Check if adding text would exceed limit
   */
  wouldExceedLimit(
    currentText: string,
    additionalText: string,
    maxTokens?: number
  ): boolean {
    const limit = maxTokens || this.getContextLimit();
    const currentTokens = this.estimateTokens(currentText);
    const additionalTokens = this.estimateTokens(additionalText);
    
    return (currentTokens + additionalTokens) > limit;
  }

  /**
   * Get statistics for text
   */
  getStatistics(text: string): {
    characters: number;
    tokens: number;
    tokensPercentage: number;
    remainingTokens: number;
    fitsInContext: boolean;
  } {
    const characters = text.length;
    const tokens = this.estimateTokens(text);
    const limit = this.getContextLimit();
    const tokensPercentage = (tokens / limit) * 100;
    const remainingTokens = limit - tokens;
    const fitsInContext = tokens <= limit;

    return {
      characters,
      tokens,
      tokensPercentage,
      remainingTokens,
      fitsInContext,
    };
  }

  /**
   * Smart truncation with sentence boundaries
   */
  truncateAtSentence(text: string, maxTokens: number): string {
    const currentTokens = this.estimateTokens(text);
    
    if (currentTokens <= maxTokens) {
      return text;
    }

    // Split into sentences
    const sentences = text.split(/[.!?]+/).filter(s => s.trim());
    
    let result = '';
    let totalTokens = 0;

    for (const sentence of sentences) {
      const sentenceTokens = this.estimateTokens(sentence);
      
      if (totalTokens + sentenceTokens <= maxTokens) {
        result += sentence + '. ';
        totalTokens += sentenceTokens;
      } else {
        break;
      }
    }

    return result.trim() || this.truncateToTokenLimit(text, maxTokens);
  }

  /**
   * Estimate tokens with caching
   */
  private cache: Map<string, number> = new Map();

  estimateWithCache(text: string): number {
    // Use first 100 chars as cache key
    const cacheKey = text.substring(0, 100);
    
    if (this.cache.has(cacheKey)) {
      return this.cache.get(cacheKey)!;
    }

    const tokens = this.estimateTokens(text);
    this.cache.set(cacheKey, tokens);

    // Limit cache size
    if (this.cache.size > 1000) {
      const firstKey = this.cache.keys().next().value;
      if (typeof firstKey === 'string') {
        this.cache.delete(firstKey);
      }
    }

    return tokens;
  }

  /**
   * Clear estimation cache
   */
  clearCache(): void {
    this.cache.clear();
  }
}

/**
 * Token Budget Manager.
 * 
 * Manages token allocation across multiple parts of a prompt.
 * Useful for complex multi-part prompts.
 * 
 * Example:
 * ```typescript
 * const budget = new TokenBudgetManager(4096);
 * 
 * budget.allocate('system', 100);
 * budget.allocate('context', 2000);
 * budget.allocate('history', 1000);
 * budget.allocate('user_query', 500);
 * 
 * console.log(budget.getRemainingBudget()); // 496
 * console.log(budget.isOverBudget()); // false
 * ```
 */
export class TokenBudgetManager {
  private totalBudget: number;
  private allocations: Map<string, number> = new Map();

  constructor(totalBudget: number) {
    this.totalBudget = totalBudget;
  }

  /**
   * Allocate tokens to a category
   */
  allocate(category: string, tokens: number): void {
    this.allocations.set(category, tokens);
  }

  /**
   * Get allocated tokens for category
   */
  getAllocation(category: string): number {
    return this.allocations.get(category) || 0;
  }

  /**
   * Get total allocated tokens
   */
  getTotalAllocated(): number {
    let total = 0;
    for (const tokens of this.allocations.values()) {
      total += tokens;
    }
    return total;
  }

  /**
   * Get remaining budget
   */
  getRemainingBudget(): number {
    return Math.max(0, this.totalBudget - this.getTotalAllocated());
  }

  /**
   * Check if over budget
   */
  isOverBudget(): boolean {
    return this.getTotalAllocated() > this.totalBudget;
  }

  /**
   * Get budget utilization percentage
   */
  getUtilization(): number {
    return (this.getTotalAllocated() / this.totalBudget) * 100;
  }

  /**
   * Reset all allocations
   */
  reset(): void {
    this.allocations.clear();
  }

  /**
   * Get allocation breakdown
   */
  getBreakdown(): Array<{ category: string; tokens: number; percentage: number }> {
    const total = this.getTotalAllocated();
    const breakdown: Array<{ category: string; tokens: number; percentage: number }> = [];

    for (const [category, tokens] of this.allocations.entries()) {
      breakdown.push({
        category,
        tokens,
        percentage: total > 0 ? (tokens / total) * 100 : 0,
      });
    }

    return breakdown.sort((a, b) => b.tokens - a.tokens);
  }
}

/**
 * Factory for creating estimators
 */
export class TokenEstimatorFactory {
  /**
   * Create estimator for GPT models
   */
  static createForGPT(version: '3.5' | '4' = '4', variant?: '16k' | '32k'): TokenEstimator {
    let model = `gpt-${version}-turbo`;
    if (variant) {
      model = `gpt-${version}-turbo-${variant}`;
    } else if (version === '4') {
      model = 'gpt-4';
    }
    return new TokenEstimator(model);
  }

  /**
   * Create estimator for Claude models
   */
  static createForClaude(version: '2' | '3' | '4' = '3', variant?: string): TokenEstimator {
    let model = `claude-${version}`;
    if (variant) {
      model = `claude-${version}-${variant}`;
    }
    return new TokenEstimator(model);
  }

  /**
   * Create estimator with custom model
   */
  static createCustom(modelName: string): TokenEstimator {
    return new TokenEstimator(modelName);
  }
}
