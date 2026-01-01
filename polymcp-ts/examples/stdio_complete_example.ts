/**
 * Stdio Complete Example - WORKING VERSION
 * 
 * Uses separate command and args (no quotes needed!)
 */

import { z } from 'zod';
import { resolve } from 'path';
import { StdioMCPServer, MCPStdioClient, withStdioClient, StdioClientPool } from '../src';

// ============================================================================
// Tool Definitions
// ============================================================================

const weatherTool = {
  name: 'get_weather',
  description: 'Get current weather for a city',
  parameters: z.object({
    city: z.string().describe('City name'),
    units: z.enum(['celsius', 'fahrenheit']).optional().default('celsius').describe('Temperature units')
  }),
  execute: async (params: { city: string; units?: 'celsius' | 'fahrenheit' }) => {
    const temp = params.units === 'celsius' ? 22 : 72;
    const conditions = ['Sunny', 'Cloudy', 'Rainy', 'Snowy'];
    const condition = conditions[Math.floor(Math.random() * conditions.length)];
    
    return JSON.stringify({
      city: params.city,
      temperature: temp,
      units: params.units || 'celsius',
      conditions: condition,
      humidity: 65,
      wind_speed: 12
    }, null, 2);
  }
};

const calculateTool = {
  name: 'calculate',
  description: 'Perform mathematical calculations',
  parameters: z.object({
    expression: z.string().describe('Math expression (e.g., "2 + 2")'),
  }),
  execute: async (params: { expression: string }) => {
    try {
      const result = eval(params.expression);
      return JSON.stringify({
        expression: params.expression,
        result,
        success: true
      }, null, 2);
    } catch (error: any) {
      return JSON.stringify({
        expression: params.expression,
        error: error.message,
        success: false
      }, null, 2);
    }
  }
};

const dateTool = {
  name: 'get_date_info',
  description: 'Get current date and time information',
  parameters: z.object({
    format: z.enum(['short', 'long', 'iso']).optional().default('long').describe('Date format')
  }),
  execute: async (params: { format?: 'short' | 'long' | 'iso' }) => {
    const now = new Date();
    let formatted: string;
    
    switch (params.format || 'long') {
      case 'short':
        formatted = now.toLocaleDateString();
        break;
      case 'long':
        formatted = now.toLocaleString();
        break;
      case 'iso':
        formatted = now.toISOString();
        break;
    }
    
    return JSON.stringify({
      formatted,
      timestamp: now.getTime(),
      year: now.getFullYear(),
      month: now.getMonth() + 1,
      day: now.getDate(),
      hour: now.getHours(),
      minute: now.getMinutes()
    }, null, 2);
  }
};

// ============================================================================
// Helper: Get command and args separately (no quotes!)
// ============================================================================

function getServerCommand(): { command: string; args: string[] } {
  const nodePath = process.execPath; // Full path to node.exe
  const tsxPath = resolve(__dirname, '..', 'node_modules', 'tsx', 'dist', 'cli.mjs');
  const scriptPath = resolve(__dirname, 'stdio_complete_example.ts');
  
  // Return command and args SEPARATELY - spawn handles paths with spaces correctly
  return {
    command: nodePath,
    args: [tsxPath, scriptPath, 'server']
  };
}

// ============================================================================
// Server Mode
// ============================================================================

function runServer() {
  console.error('🚀 Starting Stdio MCP Server...\n');
  
  const server = new StdioMCPServer([weatherTool, calculateTool, dateTool], {
    name: 'Example Stdio Server',
    version: '1.0.0',
    verbose: true,
  });

  server.run();
}

// ============================================================================
// Client Mode
// ============================================================================

async function runClient() {
  console.log('\n🔌 Connecting to Stdio Server...\n');
  console.log('💡 Note: The client will spawn the server as a subprocess\n');

  const { command, args } = getServerCommand();
  console.log(`📝 Command: ${command}`);
  console.log(`📝 Args: ${args.join(' ')}\n`);

  const client = new MCPStdioClient({
    command: command,
    args: args
  });
  
  try {
    await client.connect();
    console.log('✅ Connected!\n');

    // List tools
    console.log('📋 Listing tools...');
    const tools = await client.listTools();
    console.log(`Found ${tools.length} tools:\n`);
    
    for (const tool of tools) {
      console.log(`  • ${tool.name}`);
      console.log(`    ${tool.description}\n`);
    }

    // Test tools
    console.log('🧪 Testing tools...\n');

    console.log('1️⃣ Getting weather for London...');
    const weather = await client.callTool('get_weather', { city: 'London', units: 'celsius' });
    console.log('Result:', weather.content[0].text);
    console.log();

    console.log('2️⃣ Calculating 2 + 2...');
    const calc = await client.callTool('calculate', { expression: '2 + 2' });
    console.log('Result:', calc.content[0].text);
    console.log();

    console.log('3️⃣ Getting current date...');
    const date = await client.callTool('get_date_info', { format: 'long' });
    console.log('Result:', date.content[0].text);
    console.log();

    console.log('✅ All tests completed!\n');

    await client.disconnect();
  } catch (error: any) {
    console.error('❌ Error:', error.message);
    console.error('\n📋 Details:');
    console.error('  Command:', command);
    console.error('  Args:', args);
    if (error.stack) {
      console.error('\n📚 Stack:', error.stack);
    }
    await client.disconnect();
    process.exit(1);
  }
}

// ============================================================================
// Advanced Mode - Parallel Execution
// ============================================================================

async function runAdvanced() {
  console.log('\n⚡ Advanced Mode - Parallel Tool Execution\n');

  const { command, args } = getServerCommand();

  await withStdioClient(
    { command, args },
    async (client) => {
      console.log('✅ Connected to server\n');

      console.log('🔄 Executing 3 tools in parallel...\n');

      const [weather, calc, date] = await Promise.all([
        client.callTool('get_weather', { city: 'Paris', units: 'celsius' }),
        client.callTool('calculate', { expression: '10 * 5' }),
        client.callTool('get_date_info', { format: 'iso' })
      ]);

      console.log('Weather:', weather.content[0].text);
      console.log();
      console.log('Calculation:', calc.content[0].text);
      console.log();
      console.log('Date:', date.content[0].text);
      console.log();

      console.log('✅ Parallel execution completed!\n');
    }
  );
}

// ============================================================================
// Connection Pool Mode
// ============================================================================

async function runPool() {
  console.log('\n🔗 Connection Pool Mode\n');
  console.log('Creating pool with 3 clients...\n');

  const { command, args } = getServerCommand();

  const pool = new StdioClientPool(
    { command, args },
    3
  );

  try {
    await pool.initialize();
    console.log('✅ Pool initialized with 3 clients\n');

    console.log('🔄 Executing 6 requests across 3 clients...\n');

    const requests = [
      { city: 'London' },
      { city: 'Paris' },
      { city: 'Tokyo' },
      { city: 'New York' },
      { city: 'Sydney' },
      { city: 'Berlin' }
    ];

    for (let i = 0; i < requests.length; i++) {
      const result = await pool.execute(async (client) => {
        return await client.callTool('get_weather', requests[i]);
      });
      
      console.log(`Request ${i + 1}:`, JSON.parse(result.content[0].text).city);
    }

    console.log();
    console.log('✅ All requests completed!\n');

    await pool.shutdown();
    console.log('✅ Pool shut down\n');
  } catch (error: any) {
    console.error('❌ Error:', error.message);
    await pool.shutdown();
    process.exit(1);
  }
}

// ============================================================================
// Main
// ============================================================================

const mode = process.argv[2] || 'help';

async function main() {
  switch (mode) {
    case 'server':
      runServer();
      break;

    case 'client':
      await runClient();
      break;

    case 'advanced':
      await runAdvanced();
      break;

    case 'pool':
      await runPool();
      break;

    default:
      console.log(`
📚 Stdio Complete Example

Usage:
  tsx examples/stdio_complete_example.ts <mode>

Modes:
  server    - Run stdio server (for manual testing)
  client    - Run client test (spawns server automatically)
  advanced  - Run parallel tool execution
  pool      - Test connection pool (3 clients)

Important:
  With stdio protocol, the CLIENT spawns the SERVER as a subprocess.
  You don't need to run the server separately!

Examples:
  # Just run the client - it spawns the server automatically
  tsx examples/stdio_complete_example.ts client

  # Or test advanced features
  tsx examples/stdio_complete_example.ts advanced
  tsx examples/stdio_complete_example.ts pool

  # Manual server mode (for testing stdin/stdout directly)
  tsx examples/stdio_complete_example.ts server
`);
  }
}

main().catch(console.error);
