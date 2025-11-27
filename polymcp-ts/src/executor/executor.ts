/**
 * Sandbox Executor - Lightweight Security
 * Optimized for LLM-generated code that calls MCP tools.
 * Security relies on MCP tools being the boundary, not code restrictions.
 */

import { VM } from 'vm2';
import { ExecutionResult } from '../types';

/**
 * Sandbox Executor for safe code execution
 */
export class SandboxExecutor {
  private toolsApi: any;
  private timeout: number;
  private maxOutputSize: number;
  private verbose: boolean;

  // Only block truly dangerous operations
  private static FORBIDDEN_PATTERNS = [
    'require(',
    'import(',
    '__dirname',
    '__filename',
    'process.exit',
    'process.kill',
    'child_process',
    'fs.',
    'require("fs")',
    'require("child_process")',
    'eval(',
    'Function(',
  ];

  constructor(
    toolsApi: any,
    options: {
      timeout?: number;
      maxOutputSize?: number;
      verbose?: boolean;
    } = {}
  ) {
    this.toolsApi = toolsApi;
    this.timeout = options.timeout || 30000; // 30 seconds default
    this.maxOutputSize = options.maxOutputSize || 1000000; // 1MB default
    this.verbose = options.verbose || false;
  }

  /**
   * Lightweight safety check - only block truly dangerous operations
   */
  private checkCodeSafety(code: string): void {
    for (const pattern of SandboxExecutor.FORBIDDEN_PATTERNS) {
      if (code.includes(pattern)) {
        throw new Error(
          `Forbidden operation detected: '${pattern}'. ` +
          `Cannot execute code that accesses filesystem, network, or system processes.`
        );
      }
    }
  }

  /**
   * Execute code in sandbox
   */
  async execute(code: string): Promise<ExecutionResult> {
    const startTime = Date.now();

    if (this.verbose) {
      console.log('\n' + '='.repeat(60));
      console.log('SANDBOX EXECUTION');
      console.log('='.repeat(60));
      console.log(`Code (${code.length} chars):`);
      console.log(code.substring(0, 500) + (code.length > 500 ? '...' : ''));
      console.log('='.repeat(60) + '\n');
    }

    try {
      // Safety check
      this.checkCodeSafety(code);

      // Capture console output
      const outputs: string[] = [];
      const errors: string[] = [];

      const console_log = (...args: any[]) => {
        outputs.push(args.map(a => String(a)).join(' '));
      };

      const console_error = (...args: any[]) => {
        errors.push(args.map(a => String(a)).join(' '));
      };

      // Create VM sandbox
      const vm = new VM({
        timeout: this.timeout,
        sandbox: {
          tools: this.toolsApi,
          console: {
            log: console_log,
            error: console_error,
            warn: console_log,
            info: console_log,
          },
          JSON,
          Date,
          Math,
          setTimeout: undefined, // Disable async operations
          setInterval: undefined,
          setImmediate: undefined,
        },
      });

      // Execute code
      const result = vm.run(code);

      // Collect output
      const output = [
        ...outputs,
        ...(errors.length > 0 ? ['STDERR: ' + errors.join('\n')] : []),
      ].join('\n');

      // Enforce output size limit
      const finalOutput = output.length > this.maxOutputSize
        ? output.substring(0, this.maxOutputSize) + '\n... (output truncated)'
        : output;

      const executionTime = (Date.now() - startTime) / 1000;

      if (this.verbose) {
        console.log(`âœ… Execution successful (${executionTime.toFixed(2)}s)`);
        if (finalOutput) {
          console.log(`Output: ${finalOutput.substring(0, 200)}...`);
        }
      }

      return {
        success: true,
        output: finalOutput,
        executionTime,
        returnValue: result,
      };

    } catch (error: any) {
      const executionTime = (Date.now() - startTime) / 1000;
      const errorMsg = error.message || String(error);

      if (this.verbose) {
        console.log(`âŒ Execution error: ${errorMsg}`);
      }

      return {
        success: false,
        output: '',
        error: errorMsg,
        executionTime,
      };
    }
  }

  /**
   * Validate code without executing it
   */
  validateCode(code: string): { isValid: boolean; error?: string } {
    try {
      this.checkCodeSafety(code);
      // Try to parse as JavaScript
      new Function(code);
      return { isValid: true };
    } catch (error: any) {
      return { isValid: false, error: error.message };
    }
  }
}
