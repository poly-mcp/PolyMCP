#!/usr/bin/env node
/**
 * PolyMCP CLI - Command Line Interface
 * Project scaffolding and management tool for MCP servers
 * 
 * Commands:
 * - init: Initialize new PolyMCP project
 * - test: Test MCP server connection
 * - version: Show version information
 */

import { Command } from 'commander';
import chalk from 'chalk';
import { initCommand } from './commands/init';
import { testCommand } from './commands/test';

const program = new Command();

program
  .name('polymcp')
  .description('PolyMCP CLI - MCP server toolkit for TypeScript')
  .version('1.0.0');

// Init command
program
  .command('init')
  .description('Initialize a new PolyMCP project')
  .argument('<project-name>', 'Name of the project to create')
  .option(
    '-t, --type <type>',
    'Project type (basic, http-server, stdio-server, wasm-server, agent)',
    'basic'
  )
  .option('--with-auth', 'Include authentication setup', false)
  .option('--with-examples', 'Include example tools', false)
  .option('--skip-install', 'Skip npm install', false)
  .action(async (projectName: string, options: any) => {
    try {
      await initCommand(projectName, options);
    } catch (error: any) {
      console.error(chalk.red(`\n❌ Error: ${error.message}\n`));
      process.exit(1);
    }
  });

// Test command
program
  .command('test')
  .description('Test connection to an MCP server')
  .argument('<server>', 'Server URL or command (e.g., http://localhost:8000/mcp or npx @playwright/mcp)')
  .option('-v, --verbose', 'Verbose output', false)
  .action(async (server: string, options: any) => {
    try {
      await testCommand(server, options);
    } catch (error: any) {
      console.error(chalk.red(`\n❌ Error: ${error.message}\n`));
      process.exit(1);
    }
  });

// Parse arguments
program.parse();
