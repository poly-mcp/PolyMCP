/**
 * Error Classification System
 * 
 * Classifies errors into types for intelligent retry logic:
 * - TRANSIENT: Temporary failures (network glitches, timeouts)
 * - PERMANENT: Permanent failures (404, 400, invalid input)
 * - AUTH: Authentication/authorization failures (401, 403)
 * - RATE_LIMIT: Rate limiting (429)
 * - TIMEOUT: Request timeouts
 * - SCHEMA: Schema validation errors
 * - NOT_FOUND: Resource not found (404)
 * - UNKNOWN: Unclassified errors
 */

/**
 * Error type enum
 */
export enum ErrorType {
  /** Transient error - safe to retry */
  TRANSIENT = 'TRANSIENT',
  
  /** Permanent error - do not retry */
  PERMANENT = 'PERMANENT',
  
  /** Authentication/authorization error - refresh auth and retry */
  AUTH = 'AUTH',
  
  /** Rate limit error - backoff and retry */
  RATE_LIMIT = 'RATE_LIMIT',
  
  /** Timeout error - retry with longer timeout */
  TIMEOUT = 'TIMEOUT',
  
  /** Schema validation error - permanent, do not retry */
  SCHEMA = 'SCHEMA',
  
  /** Resource not found - permanent */
  NOT_FOUND = 'NOT_FOUND',
  
  /** Unknown error type */
  UNKNOWN = 'UNKNOWN',
}

/**
 * Classified error with metadata
 */
export interface ClassifiedError {
  /** Error type */
  type: ErrorType;
  
  /** Whether this error is retryable */
  retryable: boolean;
  
  /** Recommended retry delay in ms (if retryable) */
  retryDelayMs: number;
  
  /** Maximum recommended retries */
  maxRetries: number;
  
  /** Original error message */
  message: string;
  
  /** HTTP status code (if applicable) */
  statusCode?: number;
  
  /** Additional context */
  context?: any;
}

/**
 * Error Classification.
 * 
 * Classifies errors into types and provides retry recommendations.
 * Enables intelligent error handling and retry logic.
 * 
 * Features:
 * - Automatic error type detection
 * - HTTP status code classification
 * - Retry recommendations
 * - Backoff strategy
 * - Error pattern matching
 * 
 * Example:
 * ```typescript
 * try {
 *   await makeRequest();
 * } catch (error: any) {
 *   const classified = classifyError(error);
 *   
 *   console.log(`Error type: ${classified.type}`);
 *   console.log(`Retryable: ${classified.retryable}`);
 *   
 *   if (classified.retryable) {
 *     console.log(`Retry after ${classified.retryDelayMs}ms`);
 *     console.log(`Max retries: ${classified.maxRetries}`);
 *     
 *     // Implement retry logic
 *     await sleep(classified.retryDelayMs);
 *     await makeRequest(); // Retry
 *   }
 * }
 * ```
 */

/**
 * Classify error into type with retry recommendations
 */
export function classifyError(error: any): ClassifiedError {
  // Default classification
  const result: ClassifiedError = {
    type: ErrorType.UNKNOWN,
    retryable: false,
    retryDelayMs: 0,
    maxRetries: 0,
    message: error.message || 'Unknown error',
  };

  // Extract status code if available
  const statusCode = error.response?.status || error.statusCode;
  if (statusCode) {
    result.statusCode = statusCode;
  }

  // Classify by status code
  if (statusCode) {
    const classification = classifyByStatusCode(statusCode);
    Object.assign(result, classification);
  } 
  // Classify by error message/type
  else if (error.message) {
    const classification = classifyByMessage(error.message);
    Object.assign(result, classification);
  }
  // Classify by error name
  else if (error.name) {
    const classification = classifyByName(error.name);
    Object.assign(result, classification);
  }

  // Store original error in context
  result.context = {
    originalError: error,
    stack: error.stack,
  };

  return result;
}

/**
 * Classify by HTTP status code
 */
function classifyByStatusCode(statusCode: number): Partial<ClassifiedError> {
  // 2xx - Success (shouldn't be here)
  if (statusCode >= 200 && statusCode < 300) {
    return {
      type: ErrorType.UNKNOWN,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // 400 - Bad Request (permanent)
  if (statusCode === 400) {
    return {
      type: ErrorType.PERMANENT,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // 401 - Unauthorized (auth error)
  if (statusCode === 401) {
    return {
      type: ErrorType.AUTH,
      retryable: true,
      retryDelayMs: 1000,
      maxRetries: 2,
    };
  }

  // 403 - Forbidden (auth error)
  if (statusCode === 403) {
    return {
      type: ErrorType.AUTH,
      retryable: true,
      retryDelayMs: 1000,
      maxRetries: 2,
    };
  }

  // 404 - Not Found (permanent)
  if (statusCode === 404) {
    return {
      type: ErrorType.NOT_FOUND,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // 408 - Request Timeout (transient)
  if (statusCode === 408) {
    return {
      type: ErrorType.TIMEOUT,
      retryable: true,
      retryDelayMs: 2000,
      maxRetries: 3,
    };
  }

  // 422 - Unprocessable Entity (schema error)
  if (statusCode === 422) {
    return {
      type: ErrorType.SCHEMA,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // 429 - Too Many Requests (rate limit)
  if (statusCode === 429) {
    return {
      type: ErrorType.RATE_LIMIT,
      retryable: true,
      retryDelayMs: 60000, // 1 minute
      maxRetries: 3,
    };
  }

  // 500 - Internal Server Error (transient)
  if (statusCode === 500) {
    return {
      type: ErrorType.TRANSIENT,
      retryable: true,
      retryDelayMs: 5000,
      maxRetries: 3,
    };
  }

  // 502 - Bad Gateway (transient)
  if (statusCode === 502) {
    return {
      type: ErrorType.TRANSIENT,
      retryable: true,
      retryDelayMs: 3000,
      maxRetries: 3,
    };
  }

  // 503 - Service Unavailable (transient)
  if (statusCode === 503) {
    return {
      type: ErrorType.TRANSIENT,
      retryable: true,
      retryDelayMs: 10000, // 10 seconds
      maxRetries: 5,
    };
  }

  // 504 - Gateway Timeout (timeout)
  if (statusCode === 504) {
    return {
      type: ErrorType.TIMEOUT,
      retryable: true,
      retryDelayMs: 5000,
      maxRetries: 3,
    };
  }

  // 4xx - Client errors (generally permanent)
  if (statusCode >= 400 && statusCode < 500) {
    return {
      type: ErrorType.PERMANENT,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // 5xx - Server errors (generally transient)
  if (statusCode >= 500 && statusCode < 600) {
    return {
      type: ErrorType.TRANSIENT,
      retryable: true,
      retryDelayMs: 5000,
      maxRetries: 3,
    };
  }

  // Unknown status code
  return {
    type: ErrorType.UNKNOWN,
    retryable: false,
    retryDelayMs: 0,
    maxRetries: 0,
  };
}

/**
 * Classify by error message
 */
function classifyByMessage(message: string): Partial<ClassifiedError> {
  const lowerMessage = message.toLowerCase();

  // Timeout patterns
  if (
    lowerMessage.includes('timeout') ||
    lowerMessage.includes('timed out') ||
    lowerMessage.includes('etimedout')
  ) {
    return {
      type: ErrorType.TIMEOUT,
      retryable: true,
      retryDelayMs: 2000,
      maxRetries: 3,
    };
  }

  // Network patterns
  if (
    lowerMessage.includes('network') ||
    lowerMessage.includes('econnrefused') ||
    lowerMessage.includes('econnreset') ||
    lowerMessage.includes('enotfound') ||
    lowerMessage.includes('ehostunreach')
  ) {
    return {
      type: ErrorType.TRANSIENT,
      retryable: true,
      retryDelayMs: 3000,
      maxRetries: 3,
    };
  }

  // Rate limit patterns
  if (
    lowerMessage.includes('rate limit') ||
    lowerMessage.includes('too many requests') ||
    lowerMessage.includes('quota exceeded')
  ) {
    return {
      type: ErrorType.RATE_LIMIT,
      retryable: true,
      retryDelayMs: 60000,
      maxRetries: 3,
    };
  }

  // Auth patterns
  if (
    lowerMessage.includes('unauthorized') ||
    lowerMessage.includes('forbidden') ||
    lowerMessage.includes('authentication') ||
    lowerMessage.includes('invalid token') ||
    lowerMessage.includes('expired token')
  ) {
    return {
      type: ErrorType.AUTH,
      retryable: true,
      retryDelayMs: 1000,
      maxRetries: 2,
    };
  }

  // Schema/validation patterns
  if (
    lowerMessage.includes('validation') ||
    lowerMessage.includes('invalid schema') ||
    lowerMessage.includes('invalid input') ||
    lowerMessage.includes('parse error')
  ) {
    return {
      type: ErrorType.SCHEMA,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // Not found patterns
  if (
    lowerMessage.includes('not found') ||
    lowerMessage.includes('does not exist')
  ) {
    return {
      type: ErrorType.NOT_FOUND,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // Default to unknown
  return {
    type: ErrorType.UNKNOWN,
    retryable: false,
    retryDelayMs: 0,
    maxRetries: 0,
  };
}

/**
 * Classify by error name/type
 */
function classifyByName(name: string): Partial<ClassifiedError> {
  const lowerName = name.toLowerCase();

  // Timeout errors
  if (
    lowerName.includes('timeout') ||
    lowerName === 'timeouterror'
  ) {
    return {
      type: ErrorType.TIMEOUT,
      retryable: true,
      retryDelayMs: 2000,
      maxRetries: 3,
    };
  }

  // Network errors
  if (
    lowerName.includes('network') ||
    lowerName === 'networkerror'
  ) {
    return {
      type: ErrorType.TRANSIENT,
      retryable: true,
      retryDelayMs: 3000,
      maxRetries: 3,
    };
  }

  // Validation errors
  if (
    lowerName.includes('validation') ||
    lowerName === 'validationerror'
  ) {
    return {
      type: ErrorType.SCHEMA,
      retryable: false,
      retryDelayMs: 0,
      maxRetries: 0,
    };
  }

  // Default to unknown
  return {
    type: ErrorType.UNKNOWN,
    retryable: false,
    retryDelayMs: 0,
    maxRetries: 0,
  };
}

/**
 * Check if error is retryable
 */
export function isRetryable(error: any): boolean {
  const classified = classifyError(error);
  return classified.retryable;
}

/**
 * Get recommended retry delay
 */
export function getRetryDelay(error: any): number {
  const classified = classifyError(error);
  return classified.retryDelayMs;
}

/**
 * Get max retries for error
 */
export function getMaxRetries(error: any): number {
  const classified = classifyError(error);
  return classified.maxRetries;
}

/**
 * Calculate exponential backoff delay
 */
export function calculateBackoff(
  baseDelayMs: number,
  attemptNumber: number,
  maxDelayMs: number = 60000
): number {
  const delay = baseDelayMs * Math.pow(2, attemptNumber - 1);
  return Math.min(delay, maxDelayMs);
}

/**
 * Sleep helper for retry delays
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry helper with error classification
 */
export async function retryWithClassification<T>(
  fn: () => Promise<T>,
  onRetry?: (error: ClassifiedError, attempt: number) => void
): Promise<T> {
  let attempt = 0;

  while (true) {
    attempt++;

    try {
      return await fn();
    } catch (error: any) {
      const classified = classifyError(error);

      // Check if retryable
      if (!classified.retryable) {
        throw error;
      }

      // Check if exceeded max retries
      if (attempt >= classified.maxRetries) {
        throw error;
      }

      // Call retry callback
      if (onRetry) {
        onRetry(classified, attempt);
      }

      // Calculate backoff delay
      const delay = calculateBackoff(
        classified.retryDelayMs,
        attempt
      );

      // Wait before retry
      await sleep(delay);
    }
  }
}
