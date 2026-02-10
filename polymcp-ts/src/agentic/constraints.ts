/**
 * Constraint System
 * 
 * Tool constraint and dependency management:
 * - Dependency tracking (tool A requires tool B first)
 * - Mutual exclusion (tool A and B cannot both run)
 * - Sequencing (tool A must run before tool B)
 * - Rate limiting (max executions per time window)
 * - Constraint validation
 * - Execution ordering
 */

/**
 * Constraint type enum
 */
export enum ConstraintType {
  /** Tool requires another tool to have been executed first */
  REQUIRES_PREVIOUS = 'REQUIRES_PREVIOUS',
  
  /** Tool is mutually exclusive with another tool */
  MUTEX = 'MUTEX',
  
  /** Tool must be executed in a specific sequence */
  SEQUENCE = 'SEQUENCE',
  
  /** Tool has rate limiting constraints */
  RATE_LIMITED = 'RATE_LIMITED',
}

/**
 * Tool constraint definition
 */
export interface ToolConstraint {
  /** Constraint type */
  type: ConstraintType;
  
  /** Tool this constraint applies to */
  toolName: string;
  
  /** Related tool(s) for the constraint */
  relatedTools?: string[];
  
  /** Additional constraint data */
  data?: Record<string, any>;
}

/**
 * Execution record for constraint checking
 */
interface ExecutionRecord {
  toolName: string;
  timestamp: number;
  success: boolean;
}

/**
 * Constraint Manager.
 * 
 * Manages tool constraints and dependencies.
 * Ensures tools are executed in valid order with proper dependencies.
 * 
 * Features:
 * - Dependency tracking
 * - Mutual exclusion
 * - Sequence enforcement
 * - Rate limiting
 * - Constraint validation
 * - Execution history tracking
 * - Topological sorting for optimal execution order
 * 
 * Example:
 * ```typescript
 * const manager = new ConstraintManager();
 * 
 * // Add constraints
 * manager.addConstraint({
 *   type: ConstraintType.REQUIRES_PREVIOUS,
 *   toolName: 'send_email',
 *   relatedTools: ['fetch_contacts']
 * });
 * 
 * manager.addConstraint({
 *   type: ConstraintType.MUTEX,
 *   toolName: 'read_file',
 *   relatedTools: ['write_file']
 * });
 * 
 * manager.addConstraint({
 *   type: ConstraintType.RATE_LIMITED,
 *   toolName: 'api_call',
 *   data: { maxExecutions: 10, windowMs: 60000 }
 * });
 * 
 * // Check if tool can execute
 * const canExecute = manager.canExecuteTool('send_email');
 * if (!canExecute.allowed) {
 *   console.log('Cannot execute:', canExecute.reason);
 * }
 * 
 * // Record execution
 * manager.recordExecution('fetch_contacts', true);
 * manager.recordExecution('send_email', true);
 * ```
 */
export class ConstraintManager {
  private constraints: Map<string, ToolConstraint[]> = new Map();
  private executionHistory: ExecutionRecord[] = [];
  private maxHistorySize: number = 1000;

  /**
   * Add a constraint
   */
  addConstraint(constraint: ToolConstraint): void {
    const existing = this.constraints.get(constraint.toolName) || [];
    existing.push(constraint);
    this.constraints.set(constraint.toolName, existing);
  }

  /**
   * Remove constraints for a tool
   */
  removeConstraints(toolName: string): void {
    this.constraints.delete(toolName);
  }

  /**
   * Get constraints for a tool
   */
  getConstraints(toolName: string): ToolConstraint[] {
    return this.constraints.get(toolName) || [];
  }

  /**
   * Check if tool can be executed
   */
  canExecuteTool(toolName: string): { allowed: boolean; reason?: string } {
    const constraints = this.getConstraints(toolName);

    for (const constraint of constraints) {
      const check = this.checkConstraint(constraint);
      if (!check.satisfied) {
        return {
          allowed: false,
          reason: check.reason,
        };
      }
    }

    return { allowed: true };
  }

  /**
   * Check individual constraint
   */
  private checkConstraint(constraint: ToolConstraint): { satisfied: boolean; reason?: string } {
    switch (constraint.type) {
      case ConstraintType.REQUIRES_PREVIOUS:
        return this.checkRequiresPrevious(constraint);
      
      case ConstraintType.MUTEX:
        return this.checkMutex(constraint);
      
      case ConstraintType.SEQUENCE:
        return this.checkSequence(constraint);
      
      case ConstraintType.RATE_LIMITED:
        return this.checkRateLimit(constraint);
      
      default:
        return { satisfied: true };
    }
  }

  /**
   * Check REQUIRES_PREVIOUS constraint
   */
  private checkRequiresPrevious(constraint: ToolConstraint): { satisfied: boolean; reason?: string } {
    if (!constraint.relatedTools || constraint.relatedTools.length === 0) {
      return { satisfied: true };
    }

    for (const requiredTool of constraint.relatedTools) {
      const hasExecuted = this.executionHistory.some(
        record => record.toolName === requiredTool && record.success
      );

      if (!hasExecuted) {
        return {
          satisfied: false,
          reason: `Tool '${constraint.toolName}' requires '${requiredTool}' to be executed first`,
        };
      }
    }

    return { satisfied: true };
  }

  /**
   * Check MUTEX constraint
   */
  private checkMutex(constraint: ToolConstraint): { satisfied: boolean; reason?: string } {
    if (!constraint.relatedTools || constraint.relatedTools.length === 0) {
      return { satisfied: true };
    }

    for (const mutexTool of constraint.relatedTools) {
      const hasExecuted = this.executionHistory.some(
        record => record.toolName === mutexTool
      );

      if (hasExecuted) {
        return {
          satisfied: false,
          reason: `Tool '${constraint.toolName}' is mutually exclusive with '${mutexTool}' which has already executed`,
        };
      }
    }

    return { satisfied: true };
  }

  /**
   * Check SEQUENCE constraint
   */
  private checkSequence(constraint: ToolConstraint): { satisfied: boolean; reason?: string } {
    if (!constraint.relatedTools || constraint.relatedTools.length === 0) {
      return { satisfied: true };
    }

    // Tools must be executed in exact order
    const sequence = [constraint.toolName, ...constraint.relatedTools];
    const executed = this.executionHistory.map(r => r.toolName);

    // Find position of toolName in sequence
    const toolIndex = sequence.indexOf(constraint.toolName);
    
    // Check all previous tools in sequence have been executed
    for (let i = 0; i < toolIndex; i++) {
      if (!executed.includes(sequence[i])) {
        return {
          satisfied: false,
          reason: `Tool '${constraint.toolName}' must be executed after '${sequence[i]}' in sequence`,
        };
      }
    }

    return { satisfied: true };
  }

  /**
   * Check RATE_LIMITED constraint
   */
  private checkRateLimit(constraint: ToolConstraint): { satisfied: boolean; reason?: string } {
    if (!constraint.data) {
      return { satisfied: true };
    }

    const maxExecutions = constraint.data.maxExecutions || 10;
    const windowMs = constraint.data.windowMs || 60000; // 1 minute default

    const now = Date.now();
    const cutoff = now - windowMs;

    // Count executions in time window
    const recentExecutions = this.executionHistory.filter(
      record => record.toolName === constraint.toolName && record.timestamp >= cutoff
    );

    if (recentExecutions.length >= maxExecutions) {
      const oldestExecution = recentExecutions[0];
      const timeUntilReset = oldestExecution.timestamp + windowMs - now;

      return {
        satisfied: false,
        reason: `Rate limit exceeded for '${constraint.toolName}' (${recentExecutions.length}/${maxExecutions} in ${windowMs}ms). Reset in ${timeUntilReset}ms`,
      };
    }

    return { satisfied: true };
  }

  /**
   * Record tool execution
   */
  recordExecution(toolName: string, success: boolean): void {
    this.executionHistory.push({
      toolName,
      timestamp: Date.now(),
      success,
    });

    // Trim history
    if (this.executionHistory.length > this.maxHistorySize) {
      this.executionHistory = this.executionHistory.slice(-this.maxHistorySize);
    }
  }

  /**
   * Get execution history
   */
  getExecutionHistory(): ExecutionRecord[] {
    return [...this.executionHistory];
  }

  /**
   * Get execution order (topological sort based on dependencies)
   */
  getExecutionOrder(toolNames: string[]): string[] {
    // Build dependency graph
    const graph = new Map<string, string[]>();
    const inDegree = new Map<string, number>();

    // Initialize
    for (const tool of toolNames) {
      graph.set(tool, []);
      inDegree.set(tool, 0);
    }

    // Build edges from constraints
    for (const tool of toolNames) {
      const constraints = this.getConstraints(tool);
      
      for (const constraint of constraints) {
        if (constraint.type === ConstraintType.REQUIRES_PREVIOUS && constraint.relatedTools) {
          for (const requiredTool of constraint.relatedTools) {
            if (toolNames.includes(requiredTool)) {
              graph.get(requiredTool)!.push(tool);
              inDegree.set(tool, (inDegree.get(tool) || 0) + 1);
            }
          }
        }
      }
    }

    // Topological sort (Kahn's algorithm)
    const result: string[] = [];
    const queue: string[] = [];

    // Find nodes with no incoming edges
    for (const [tool, degree] of inDegree.entries()) {
      if (degree === 0) {
        queue.push(tool);
      }
    }

    while (queue.length > 0) {
      const tool = queue.shift()!;
      result.push(tool);

      const neighbors = graph.get(tool) || [];
      for (const neighbor of neighbors) {
        inDegree.set(neighbor, (inDegree.get(neighbor) || 0) - 1);
        if (inDegree.get(neighbor) === 0) {
          queue.push(neighbor);
        }
      }
    }

    // Check for cycles
    if (result.length !== toolNames.length) {
      // Cycle detected, return original order
      return toolNames;
    }

    return result;
  }

  /**
   * Validate all constraints for a set of tools
   */
  validateAllConstraints(toolNames: string[]): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    // Check for circular dependencies
    const order = this.getExecutionOrder(toolNames);
    if (order.length !== toolNames.length) {
      errors.push('Circular dependencies detected');
    }

    // Check mutex conflicts
    for (const tool of toolNames) {
      const constraints = this.getConstraints(tool);
      for (const constraint of constraints) {
        if (constraint.type === ConstraintType.MUTEX && constraint.relatedTools) {
          for (const mutexTool of constraint.relatedTools) {
            if (toolNames.includes(mutexTool)) {
              errors.push(`Mutex conflict: '${tool}' and '${mutexTool}' cannot both be executed`);
            }
          }
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Clear execution history
   */
  clearHistory(): void {
    this.executionHistory = [];
  }

  /**
   * Clear all constraints
   */
  clearAllConstraints(): void {
    this.constraints.clear();
  }

  /**
   * Get statistics
   */
  getStatistics(): {
    totalConstraints: number;
    constraintsByType: Record<ConstraintType, number>;
    totalExecutions: number;
    uniqueToolsExecuted: number;
  } {
    let totalConstraints = 0;
    const constraintsByType: Record<ConstraintType, number> = {
      [ConstraintType.REQUIRES_PREVIOUS]: 0,
      [ConstraintType.MUTEX]: 0,
      [ConstraintType.SEQUENCE]: 0,
      [ConstraintType.RATE_LIMITED]: 0,
    };

    for (const constraints of this.constraints.values()) {
      totalConstraints += constraints.length;
      for (const constraint of constraints) {
        constraintsByType[constraint.type]++;
      }
    }

    const uniqueTools = new Set(this.executionHistory.map(r => r.toolName));

    return {
      totalConstraints,
      constraintsByType,
      totalExecutions: this.executionHistory.length,
      uniqueToolsExecuted: uniqueTools.size,
    };
  }

  /**
   * Export constraints to JSON
   */
  exportConstraints(): string {
    const data: any = {};
    for (const [toolName, constraints] of this.constraints.entries()) {
      data[toolName] = constraints;
    }
    return JSON.stringify(data, null, 2);
  }

  /**
   * Import constraints from JSON
   */
  importConstraints(json: string): void {
    const data = JSON.parse(json);
    this.constraints.clear();
    
    for (const [toolName, constraints] of Object.entries(data)) {
      this.constraints.set(toolName, constraints as ToolConstraint[]);
    }
  }
}
