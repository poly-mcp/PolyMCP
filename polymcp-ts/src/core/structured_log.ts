/**
 * Structured Logging System
 * 
 * Advanced logging with structured data:
 * - Event-based logging
 * - Trace correlation
 * - Multiple log levels
 * - JSON export
 * - Test trace saving
 * - Query and filtering
 */

import * as fs from 'fs';
import * as path from 'path';

/**
 * Log level enum
 */
export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
  FATAL = 'FATAL',
}

/**
 * Structured log entry
 */
export interface LogEntry {
  /** Timestamp (ISO format) */
  timestamp: string;
  
  /** Log level */
  level: LogLevel;
  
  /** Event name */
  event: string;
  
  /** Structured data */
  data?: Record<string, any>;
  
  /** Trace ID for correlation */
  traceId?: string;
  
  /** Error object (if applicable) */
  error?: {
    message: string;
    stack?: string;
    name?: string;
  };
}

/**
 * Logger configuration
 */
export interface LoggerConfig {
  /** Minimum log level to record */
  minLevel?: LogLevel;
  
  /** Enable console output */
  consoleOutput?: boolean;
  
  /** Maximum number of entries to keep in memory */
  maxEntries?: number;
  
  /** Default trace ID */
  defaultTraceId?: string;
  
  /** Include timestamps in console output */
  consoleTimestamps?: boolean;
}

/**
 * Structured Logger.
 * 
 * Production-grade structured logging system.
 * Enables advanced debugging, tracing, and analysis.
 * 
 * Features:
 * - Event-based logging
 * - Structured data
 * - Trace correlation
 * - Multiple log levels
 * - Console output
 * - JSON export
 * - Test trace saving
 * - Query and filtering
 * 
 * Example:
 * ```typescript
 * const logger = new StructuredLogger({
 *   minLevel: LogLevel.INFO,
 *   consoleOutput: true,
 *   defaultTraceId: 'trace-123'
 * });
 * 
 * // Log events
 * logger.info('agent_started', { llmProvider: 'openai', servers: 3 });
 * logger.debug('tool_discovered', { toolName: 'calculator', server: 'api1' });
 * logger.error('tool_failed', { toolName: 'calculator', error: 'timeout' });
 * 
 * // With custom trace ID
 * logger.info('request_received', { userId: '123' }, 'custom-trace-id');
 * 
 * // Export logs
 * const json = logger.exportJSON();
 * logger.saveTestTrace('./trace.json');
 * 
 * // Query logs
 * const errors = logger.getEntriesByLevel(LogLevel.ERROR);
 * const toolEvents = logger.getEntriesByEvent('tool_*');
 * ```
 */
export class StructuredLogger {
  private config: Required<LoggerConfig>;
  private entries: LogEntry[] = [];

  constructor(config: LoggerConfig = {}) {
    this.config = {
      minLevel: config.minLevel || LogLevel.INFO,
      consoleOutput: config.consoleOutput !== false, // default true
      maxEntries: config.maxEntries || 10000,
      defaultTraceId: config.defaultTraceId || 'default',
      consoleTimestamps: config.consoleTimestamps !== false, // default true
    };
  }

  /**
   * Log debug message
   */
  debug(event: string, data?: Record<string, any>, traceId?: string): void {
    this.log(LogLevel.DEBUG, event, data, traceId);
  }

  /**
   * Log info message
   */
  info(event: string, data?: Record<string, any>, traceId?: string): void {
    this.log(LogLevel.INFO, event, data, traceId);
  }

  /**
   * Log warning message
   */
  warn(event: string, data?: Record<string, any>, traceId?: string): void {
    this.log(LogLevel.WARN, event, data, traceId);
  }

  /**
   * Log error message
   */
  error(event: string, data?: Record<string, any>, traceId?: string, error?: Error): void {
    const errorData = error ? {
      message: error.message,
      stack: error.stack,
      name: error.name,
    } : undefined;

    this.log(LogLevel.ERROR, event, data, traceId, errorData);
  }

  /**
   * Log fatal error
   */
  fatal(event: string, data?: Record<string, any>, traceId?: string, error?: Error): void {
    const errorData = error ? {
      message: error.message,
      stack: error.stack,
      name: error.name,
    } : undefined;

    this.log(LogLevel.FATAL, event, data, traceId, errorData);
  }

  /**
   * Core logging method
   */
  private log(
    level: LogLevel,
    event: string,
    data?: Record<string, any>,
    traceId?: string,
    error?: { message: string; stack?: string; name?: string }
  ): void {
    // Check if level should be logged
    if (!this.shouldLog(level)) {
      return;
    }

    // Create entry
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      event,
      data,
      traceId: traceId || this.config.defaultTraceId,
      error,
    };

    // Add to entries
    this.entries.push(entry);

    // Trim if needed
    if (this.entries.length > this.config.maxEntries) {
      this.entries = this.entries.slice(-this.config.maxEntries);
    }

    // Console output
    if (this.config.consoleOutput) {
      this.outputToConsole(entry);
    }
  }

  /**
   * Check if level should be logged
   */
  private shouldLog(level: LogLevel): boolean {
    const levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR, LogLevel.FATAL];
    const minIndex = levels.indexOf(this.config.minLevel);
    const levelIndex = levels.indexOf(level);
    return levelIndex >= minIndex;
  }

  /**
   * Output entry to console
   */
  private outputToConsole(entry: LogEntry): void {
    const timestamp = this.config.consoleTimestamps 
      ? `[${entry.timestamp}] ` 
      : '';
    
    const traceId = entry.traceId ? `[${entry.traceId}] ` : '';
    const level = `[${entry.level}]`;
    const event = entry.event;

    let message = `${timestamp}${traceId}${level} ${event}`;

    if (entry.data && Object.keys(entry.data).length > 0) {
      message += ` ${JSON.stringify(entry.data)}`;
    }

    if (entry.error) {
      message += ` ERROR: ${entry.error.message}`;
    }

    // Use appropriate console method
    switch (entry.level) {
      case LogLevel.DEBUG:
        console.debug(message);
        break;
      case LogLevel.INFO:
        console.info(message);
        break;
      case LogLevel.WARN:
        console.warn(message);
        break;
      case LogLevel.ERROR:
      case LogLevel.FATAL:
        console.error(message);
        if (entry.error?.stack) {
          console.error(entry.error.stack);
        }
        break;
    }
  }

  /**
   * Get all log entries
   */
  getEntries(): LogEntry[] {
    return [...this.entries];
  }

  /**
   * Get entries by level
   */
  getEntriesByLevel(level: LogLevel): LogEntry[] {
    return this.entries.filter(e => e.level === level);
  }

  /**
   * Get entries by event (supports wildcards)
   */
  getEntriesByEvent(eventPattern: string): LogEntry[] {
    if (eventPattern.includes('*')) {
      // Convert wildcard to regex
      const regex = new RegExp('^' + eventPattern.replace(/\*/g, '.*') + '$');
      return this.entries.filter(e => regex.test(e.event));
    } else {
      return this.entries.filter(e => e.event === eventPattern);
    }
  }

  /**
   * Get entries by trace ID
   */
  getEntriesByTraceId(traceId: string): LogEntry[] {
    return this.entries.filter(e => e.traceId === traceId);
  }

  /**
   * Get entries in time range
   */
  getEntriesInTimeRange(startTime: Date, endTime: Date): LogEntry[] {
    const startMs = startTime.getTime();
    const endMs = endTime.getTime();

    return this.entries.filter(e => {
      const entryMs = new Date(e.timestamp).getTime();
      return entryMs >= startMs && entryMs <= endMs;
    });
  }

  /**
   * Export logs as JSON
   */
  exportJSON(): string {
    return JSON.stringify(this.entries, null, 2);
  }

  /**
   * Export logs as text
   */
  exportText(): string {
    return this.entries.map(e => {
      let line = `[${e.timestamp}] [${e.traceId}] [${e.level}] ${e.event}`;
      
      if (e.data) {
        line += ` ${JSON.stringify(e.data)}`;
      }
      
      if (e.error) {
        line += ` ERROR: ${e.error.message}`;
        if (e.error.stack) {
          line += `\n${e.error.stack}`;
        }
      }
      
      return line;
    }).join('\n');
  }

  /**
   * Save test trace to file
   */
  saveTestTrace(filePath: string, format: 'json' | 'text' = 'json'): void {
    const dir = path.dirname(filePath);
    
    // Ensure directory exists
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    // Export content
    const content = format === 'json' 
      ? this.exportJSON()
      : this.exportText();

    // Write to file
    fs.writeFileSync(filePath, content, 'utf-8');
  }

  /**
   * Load trace from file
   */
  static loadTrace(filePath: string): StructuredLogger {
    const content = fs.readFileSync(filePath, 'utf-8');
    const entries = JSON.parse(content) as LogEntry[];
    
    const logger = new StructuredLogger();
    logger.entries = entries;
    
    return logger;
  }

  /**
   * Clear all logs
   */
  clear(): void {
    this.entries = [];
  }

  /**
   * Get log count
   */
  getCount(): number {
    return this.entries.length;
  }

  /**
   * Get count by level
   */
  getCountByLevel(level: LogLevel): number {
    return this.getEntriesByLevel(level).length;
  }

  /**
   * Get statistics
   */
  getStatistics(): {
    total: number;
    byLevel: Record<LogLevel, number>;
    uniqueEvents: number;
    uniqueTraces: number;
    timeRange: { start: string; end: string } | null;
  } {
    const byLevel: Record<LogLevel, number> = {
      [LogLevel.DEBUG]: 0,
      [LogLevel.INFO]: 0,
      [LogLevel.WARN]: 0,
      [LogLevel.ERROR]: 0,
      [LogLevel.FATAL]: 0,
    };

    const events = new Set<string>();
    const traces = new Set<string>();

    for (const entry of this.entries) {
      byLevel[entry.level]++;
      events.add(entry.event);
      if (entry.traceId) {
        traces.add(entry.traceId);
      }
    }

    let timeRange: { start: string; end: string } | null = null;
    if (this.entries.length > 0) {
      timeRange = {
        start: this.entries[0].timestamp,
        end: this.entries[this.entries.length - 1].timestamp,
      };
    }

    return {
      total: this.entries.length,
      byLevel,
      uniqueEvents: events.size,
      uniqueTraces: traces.size,
      timeRange,
    };
  }

  /**
   * Create child logger with same config but new trace ID
   */
  createChild(traceId: string): StructuredLogger {
    return new StructuredLogger({
      ...this.config,
      defaultTraceId: traceId,
    });
  }

  /**
   * Update configuration
   */
  updateConfig(config: Partial<LoggerConfig>): void {
    Object.assign(this.config, config);
  }
}

/**
 * Global logger instance
 */
let globalLogger: StructuredLogger | null = null;

/**
 * Get or create global logger
 */
export function getGlobalLogger(): StructuredLogger {
  if (!globalLogger) {
    globalLogger = new StructuredLogger();
  }
  return globalLogger;
}

/**
 * Set global logger
 */
export function setGlobalLogger(logger: StructuredLogger): void {
  globalLogger = logger;
}

/**
 * Create logger factory for common configurations
 */
export class LoggerFactory {
  /**
   * Create development logger (verbose)
   */
  static createDevelopment(): StructuredLogger {
    return new StructuredLogger({
      minLevel: LogLevel.DEBUG,
      consoleOutput: true,
      consoleTimestamps: true,
    });
  }

  /**
   * Create production logger (essential logs only)
   */
  static createProduction(): StructuredLogger {
    return new StructuredLogger({
      minLevel: LogLevel.INFO,
      consoleOutput: true,
      consoleTimestamps: true,
    });
  }

  /**
   * Create test logger (no console output)
   */
  static createTest(): StructuredLogger {
    return new StructuredLogger({
      minLevel: LogLevel.DEBUG,
      consoleOutput: false,
    });
  }

  /**
   * Create silent logger (errors only)
   */
  static createSilent(): StructuredLogger {
    return new StructuredLogger({
      minLevel: LogLevel.ERROR,
      consoleOutput: false,
    });
  }
}
