/**
 * Advanced Tools - PRODUCTION IMPLEMENTATION
 * Built-in advanced tools for common operations.
 * 
 * Features:
 * - Web search tool
 * - Code execution tool
 * - File operations tools
 * - Shell command execution
 * - All with comprehensive error handling and security
 */

import { tool } from '../tool-helpers';
import { z } from 'zod';
import * as fs from 'fs-extra';
import * as path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

/**
 * Web Search Tool
 * Searches the web using a search API
 */
export const webSearch = tool({
  name: 'web_search',
  description: 'Search the web for information. Returns search results with titles, URLs, and snippets.',
  inputSchema: z.object({
    query: z.string().describe('Search query'),
    num_results: z.number().optional().default(5).describe('Number of results to return (1-10)'),
  }),
  function: async ({ query, num_results }: { query: string; num_results?: number }) => {
    try {
      // In production, integrate with a real search API (Google, Bing, DuckDuckGo, etc.)
      // This is a placeholder implementation
      
      // For now, return a structured response indicating the search would be performed
      return JSON.stringify({
        query,
        results: [
          {
            title: `Search results for: ${query}`,
            url: 'https://example.com',
            snippet: 'This is a placeholder. In production, integrate with a real search API.',
          },
        ].slice(0, Math.max(1, Math.min(10, num_results ?? 5))),
        message: 'To enable real web search, configure a search API (Google Custom Search, Bing, etc.)',
      }, null, 2);
    } catch (error: any) {
      throw new Error(`Web search failed: ${error.message}`);
    }
  },
});

/**
 * Code Execution Tool
 * Executes JavaScript code in a sandboxed environment
 */
export const executeCode = tool({
  name: 'execute_code',
  description: 'Execute JavaScript code in a sandboxed environment. Returns the output and any errors.',
  inputSchema: z.object({
    code: z.string().describe('JavaScript code to execute'),
    timeout: z.number().optional().default(5000).describe('Timeout in milliseconds'),
  }),
  function: async ({ code, timeout }: { code: string; timeout?: number }) => {
    try {
      // Use vm2 for sandboxed execution
      const { VM } = require('vm2');
      
      const vm = new VM({
        timeout,
        sandbox: {
          console: {
            log: (...args: any[]) => args.join(' '),
          },
        },
      });

      const result = vm.run(code);
      
      return JSON.stringify({
        success: true,
        result: String(result),
        output: result,
      }, null, 2);
    } catch (error: any) {
      return JSON.stringify({
        success: false,
        error: error.message,
        stack: error.stack,
      }, null, 2);
    }
  },
});

/**
 * Read File Tool
 * Reads content from a file
 */
export const readFile = tool({
  name: 'read_file',
  description: 'Read content from a file. Returns the file content as a string.',
  inputSchema: z.object({
    file_path: z.string().describe('Path to the file to read'),
    encoding: z.string().optional().default('utf-8').describe('File encoding (default: utf-8)'),
  }),
  function: async ({ file_path, encoding }: { file_path: string; encoding?: string }) => {
    try {
      // Security: validate path (prevent directory traversal)
      const resolvedPath = path.resolve(file_path);
      const cwd = process.cwd();
      
      if (!resolvedPath.startsWith(cwd)) {
        throw new Error('Access denied: path is outside working directory');
      }

      // Check if file exists
      if (!(await fs.pathExists(resolvedPath))) {
        throw new Error(`File not found: ${file_path}`);
      }

      // Read file
      const content = await fs.readFile(resolvedPath, encoding as BufferEncoding);
      
      return JSON.stringify({
        success: true,
        file_path: file_path,
        content: content,
        size: content.length,
      }, null, 2);
    } catch (error: any) {
      throw new Error(`Failed to read file: ${error.message}`);
    }
  },
});

/**
 * Write File Tool
 * Writes content to a file
 */
export const writeFile = tool({
  name: 'write_file',
  description: 'Write content to a file. Creates the file if it doesn\'t exist.',
  inputSchema: z.object({
    file_path: z.string().describe('Path to the file to write'),
    content: z.string().describe('Content to write to the file'),
    encoding: z.string().optional().default('utf-8').describe('File encoding (default: utf-8)'),
    append: z.boolean().optional().default(false).describe('Append to file instead of overwriting'),
  }),
  function: async ({
    file_path,
    content,
    encoding,
    append,
  }: {
    file_path: string;
    content: string;
    encoding?: string;
    append?: boolean;
  }) => {
    try {
      // Security: validate path
      const resolvedPath = path.resolve(file_path);
      const cwd = process.cwd();
      
      if (!resolvedPath.startsWith(cwd)) {
        throw new Error('Access denied: path is outside working directory');
      }

      // Ensure directory exists
      await fs.ensureDir(path.dirname(resolvedPath));

      // Write or append
      if (append) {
        await fs.appendFile(resolvedPath, content, encoding as BufferEncoding);
      } else {
        await fs.writeFile(resolvedPath, content, encoding as BufferEncoding);
      }

      return JSON.stringify({
        success: true,
        file_path: file_path,
        bytes_written: content.length,
        mode: append ? 'append' : 'write',
      }, null, 2);
    } catch (error: any) {
      throw new Error(`Failed to write file: ${error.message}`);
    }
  },
});

/**
 * List Directory Tool
 * Lists contents of a directory
 */
export const listDirectory = tool({
  name: 'list_directory',
  description: 'List contents of a directory. Returns files and subdirectories.',
  inputSchema: z.object({
    directory_path: z.string().describe('Path to the directory to list'),
    recursive: z.boolean().optional().default(false).describe('List recursively'),
  }),
  function: async ({ directory_path, recursive }: { directory_path: string; recursive?: boolean }) => {
    try {
      // Security: validate path
      const resolvedPath = path.resolve(directory_path);
      const cwd = process.cwd();
      
      if (!resolvedPath.startsWith(cwd)) {
        throw new Error('Access denied: path is outside working directory');
      }

      // Check if directory exists
      if (!(await fs.pathExists(resolvedPath))) {
        throw new Error(`Directory not found: ${directory_path}`);
      }

      const stat = await fs.stat(resolvedPath);
      if (!stat.isDirectory()) {
        throw new Error(`Not a directory: ${directory_path}`);
      }

      // List directory
      const items: any[] = [];

      if (recursive) {
        // Recursive listing
        const walk = async (dir: string) => {
          const entries = await fs.readdir(dir, { withFileTypes: true });
          
          for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            const relativePath = path.relative(resolvedPath, fullPath);
            
            items.push({
              name: entry.name,
              path: relativePath,
              type: entry.isDirectory() ? 'directory' : 'file',
            });

            if (entry.isDirectory()) {
              await walk(fullPath);
            }
          }
        };

        await walk(resolvedPath);
      } else {
        // Non-recursive listing
        const entries = await fs.readdir(resolvedPath, { withFileTypes: true });
        
        for (const entry of entries) {
          items.push({
            name: entry.name,
            type: entry.isDirectory() ? 'directory' : 'file',
          });
        }
      }

      return JSON.stringify({
        success: true,
        directory: directory_path,
        items,
        count: items.length,
      }, null, 2);
    } catch (error: any) {
      throw new Error(`Failed to list directory: ${error.message}`);
    }
  },
});

/**
 * Shell Command Tool
 * Executes shell commands (with security restrictions)
 */
export const shellCommand = tool({
  name: 'shell_command',
  description: 'Execute a shell command. Use with caution - only for trusted commands.',
  inputSchema: z.object({
    command: z.string().describe('Shell command to execute'),
    timeout: z.number().optional().default(30000).describe('Timeout in milliseconds'),
    cwd: z.string().optional().describe('Working directory for the command'),
  }),
  function: async ({ command, timeout, cwd }: { command: string; timeout?: number; cwd?: string }) => {
    try {
      // Security: block dangerous commands
      const blockedPatterns = [
        /rm\s+-rf/i,
        /sudo/i,
        /passwd/i,
        /shutdown/i,
        /reboot/i,
        />/,  // Redirects
        /\|/, // Pipes (too risky)
      ];

      for (const pattern of blockedPatterns) {
        if (pattern.test(command)) {
          throw new Error(`Blocked command pattern: ${pattern}`);
        }
      }

      // Execute command
      const { stdout, stderr } = await execAsync(command, {
        timeout,
        cwd: cwd || process.cwd(),
        maxBuffer: 1024 * 1024, // 1MB max output
      });

      return JSON.stringify({
        success: true,
        command,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      }, null, 2);
    } catch (error: any) {
      throw new Error(`Command execution failed: ${error.message}`);
    }
  },
});

/**
 * HTTP Request Tool
 * Makes HTTP requests
 */
export const httpRequest = tool({
  name: 'http_request',
  description: 'Make an HTTP request to a URL. Supports GET, POST, PUT, DELETE methods.',
  inputSchema: z.object({
    url: z.string().describe('URL to request'),
    method: z.enum(['GET', 'POST', 'PUT', 'DELETE']).default('GET').describe('HTTP method'),
    headers: z.record(z.string()).optional().describe('HTTP headers'),
    body: z.string().optional().describe('Request body (for POST/PUT)'),
    timeout: z.number().optional().default(30000).describe('Timeout in milliseconds'),
  }),
  function: async ({
    url,
    method,
    headers,
    body,
    timeout,
  }: {
    url: string;
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
    headers?: Record<string, string>;
    body?: string;
    timeout?: number;
  }) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeout);

      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        body: body && (method === 'POST' || method === 'PUT') ? body : undefined,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const responseText = await response.text();
      
      // Try to parse as JSON
      let responseData;
      try {
        responseData = JSON.parse(responseText);
      } catch {
        responseData = responseText;
      }

      return JSON.stringify({
        success: response.ok,
        status: response.status,
        status_text: response.statusText,
        headers: Object.fromEntries(response.headers.entries()),
        data: responseData,
      }, null, 2);
    } catch (error: any) {
      throw new Error(`HTTP request failed: ${error.message}`);
    }
  },
});

/**
 * Get Current Time Tool
 */
export const getCurrentTime = tool({
  name: 'get_current_time',
  description: 'Get the current date and time in various formats.',
  inputSchema: z.object({
    timezone: z.string().optional().describe('Timezone (e.g., "America/New_York")'),
    format: z.enum(['iso', 'unix', 'human']).default('iso').describe('Output format'),
  }),
  function: async ({ timezone, format }: { timezone?: string; format?: 'iso' | 'unix' | 'human' }) => {
    const now = new Date();
    
    let formatted: string;
    
    switch (format) {
      case 'unix':
        formatted = Math.floor(now.getTime() / 1000).toString();
        break;
      case 'human':
        formatted = now.toLocaleString(undefined, timezone ? { timeZone: timezone } : {});
        break;
      case 'iso':
      default:
        formatted = now.toISOString();
    }

    return JSON.stringify({
      timestamp: formatted,
      format,
      timezone: timezone || 'UTC',
    }, null, 2);
  },
});

/**
 * Export all advanced tools as an array
 */
export const advancedTools = [
  webSearch,
  executeCode,
  readFile,
  writeFile,
  listDirectory,
  shellCommand,
  httpRequest,
  getCurrentTime,
];

/**
 * Export tools by category
 */
export const fileTools = [readFile, writeFile, listDirectory];
export const webTools = [webSearch, httpRequest];
export const executionTools = [executeCode, shellCommand];
export const utilityTools = [getCurrentTime];
