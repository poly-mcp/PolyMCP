/**
 * Test Command - Test connection to MCP servers
 * Supports both HTTP and stdio servers
 */

import chalk from 'chalk';
import ora from 'ora';
import { MCPStdioClient } from '../../mcp_stdio_client';

/**
 * Test command options
 */
interface TestOptions {
  verbose: boolean;
}

/**
 * Test HTTP server connection
 */
async function testHttpServer(url: string, verbose: boolean): Promise<void> {
  const spinner = ora('Connecting to HTTP server...').start();

  try {
    // Test list_tools endpoint
    const listUrl = url.endsWith('/') ? `${url}list_tools` : `${url}/list_tools`;
    
    const response = await fetch(listUrl);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    spinner.succeed('Connected to HTTP server');

    // Show tools
    if (data.tools && Array.isArray(data.tools)) {
      console.log(chalk.cyan(`\n📦 Available tools: ${data.tools.length}\n`));
      
      for (const tool of data.tools) {
        console.log(chalk.white(`   • ${tool.name}`));
        if (verbose) {
          console.log(chalk.gray(`     ${tool.description}`));
          if (tool.input_schema?.properties) {
            const params = Object.keys(tool.input_schema.properties);
            console.log(chalk.gray(`     Parameters: ${params.join(', ')}`));
          }
        }
      }
      console.log();
    }

    // Test invoke endpoint
    if (verbose && data.tools && data.tools.length > 0) {
      const testTool = data.tools[0];
      console.log(chalk.cyan('🧪 Testing tool invocation...\n'));
      
      const invokeUrl = url.endsWith('/') ? `${url}invoke` : `${url}/invoke`;
      
      // Create test parameters
      const testParams: any = {};
      if (testTool.input_schema?.properties) {
        for (const [param, schema] of Object.entries(testTool.input_schema.properties)) {
          const paramSchema = schema as any;
          testParams[param] = getExampleValue(paramSchema.type);
        }
      }

      try {
        const invokeResponse = await fetch(invokeUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tool: testTool.name,
            parameters: testParams,
          }),
        });

        if (invokeResponse.ok) {
          const result = await invokeResponse.json();
          console.log(chalk.green('   ✓ Tool invocation successful'));
          if (verbose) {
            console.log(chalk.gray(`   Result: ${JSON.stringify(result, null, 2)}`));
          }
        } else {
          console.log(chalk.yellow('   ⚠ Tool invocation failed (might need valid params)'));
        }
      } catch (error) {
        console.log(chalk.yellow('   ⚠ Could not test tool invocation'));
      }
      console.log();
    }

    // Summary
    console.log(chalk.green('✅ Server is healthy and responding\n'));

  } catch (error: any) {
    spinner.fail('Failed to connect');
    console.error(chalk.red(`\n❌ Error: ${error.message}\n`));
    throw error;
  }
}

/**
 * Test stdio server connection
 */
async function testStdioServer(command: string, verbose: boolean): Promise<void> {
  const spinner = ora('Connecting to stdio server...').start();

  const client = new MCPStdioClient({
    command,
    verbose,
  });

  try {
    await client.connect();
    spinner.succeed('Connected to stdio server');

    // Get server info
    const serverInfo = client.getServerInfo();
    if (serverInfo) {
      console.log(chalk.cyan(`\n📡 Server: ${serverInfo.name} v${serverInfo.version}\n`));
    }

    // List tools
    const tools = await client.listTools();
    console.log(chalk.cyan(`📦 Available tools: ${tools.length}\n`));

    for (const tool of tools) {
      console.log(chalk.white(`   • ${tool.name}`));
      if (verbose) {
        console.log(chalk.gray(`     ${tool.description}`));
        if (tool.input_schema?.properties) {
          const params = Object.keys(tool.input_schema.properties);
          console.log(chalk.gray(`     Parameters: ${params.join(', ')}`));
        }
      }
    }
    console.log();

    // Test tool invocation
    if (verbose && tools.length > 0) {
      const testTool = tools[0];
      console.log(chalk.cyan('🧪 Testing tool invocation...\n'));

      // Create test parameters
      const testParams: any = {};
      if (testTool.input_schema?.properties) {
        for (const [param, schema] of Object.entries(testTool.input_schema.properties)) {
          const paramSchema = schema as any;
          testParams[param] = getExampleValue(paramSchema.type);
        }
      }

      try {
        const result = await client.callTool(testTool.name, testParams);
        console.log(chalk.green('   ✓ Tool invocation successful'));
        if (verbose) {
          console.log(chalk.gray(`   Result: ${JSON.stringify(result, null, 2)}`));
        }
      } catch (error: any) {
        console.log(chalk.yellow(`   ⚠ Tool invocation failed: ${error.message}`));
      }
      console.log();
    }

    // Ping test
    if (verbose) {
      console.log(chalk.cyan('🏓 Testing ping...\n'));
      try {
        await client.ping();
        console.log(chalk.green('   ✓ Ping successful\n'));
      } catch (error) {
        console.log(chalk.yellow('   ⚠ Ping not supported\n'));
      }
    }

    console.log(chalk.green('✅ Server is healthy and responding\n'));

    await client.disconnect();

  } catch (error: any) {
    spinner.fail('Failed to connect');
    console.error(chalk.red(`\n❌ Error: ${error.message}\n`));
    
    if (client.isConnected()) {
      await client.disconnect();
    }
    
    throw error;
  }
}

/**
 * Get example value for parameter type
 */
function getExampleValue(type: string): any {
  switch (type) {
    case 'string':
      return 'test';
    case 'number':
    case 'integer':
      return 42;
    case 'boolean':
      return true;
    case 'array':
      return ['item1', 'item2'];
    case 'object':
      return { key: 'value' };
    default:
      return 'test';
  }
}

/**
 * Main test command handler
 */
export async function testCommand(server: string, options: TestOptions): Promise<void> {
  console.log(chalk.cyan('\n🔍 Testing MCP server connection...\n'));
  console.log(chalk.gray(`   Server: ${server}`));
  console.log(chalk.gray(`   Verbose: ${options.verbose}\n`));

  // Determine server type
  if (server.startsWith('http://') || server.startsWith('https://')) {
    // HTTP server
    await testHttpServer(server, options.verbose);
  } else {
    // Stdio server (command)
    await testStdioServer(server, options.verbose);
  }
}
