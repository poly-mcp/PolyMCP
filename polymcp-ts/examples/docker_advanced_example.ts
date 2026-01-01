/**
 * Docker Executor & Advanced Tools Example
 * 
 * This example demonstrates:
 * 1. Secure code execution with Docker sandbox
 * 2. Using built-in advanced tools
 * 3. Running Dual Mode server (HTTP + Stdio)
 * 4. Complete production-ready setup
 * 
 * Prerequisites:
 * - Docker installed and running
 * - Node.js 18+
 * 
 * Usage:
 *   # Test Docker executor
 *   tsx examples/docker_advanced_example.ts docker
 * 
 *   # Test advanced tools
 *   tsx examples/docker_advanced_example.ts tools
 * 
 *   # Run dual mode server
 *   tsx examples/docker_advanced_example.ts server
 * 
 *   # Complete workflow
 *   tsx examples/docker_advanced_example.ts workflow
 */

import {
  DockerSandboxExecutor,
  executeInDocker,
  advancedTools,
  fileTools,
  webTools,
  executionTools,
  utilityTools,
  DualModeMCPServer,
  tool,
  MCPStdioClient
} from '../src/index';
import { z } from 'zod';
import * as fs from 'fs-extra';

// ============================================================================
// STEP 1: Docker Executor Examples
// ============================================================================

async function demoDockerExecutor() {
  console.log('\n🐳 DOCKER EXECUTOR DEMO\n');
  console.log('='.repeat(70) + '\n');

  const executor = new DockerSandboxExecutor({
    timeout: 30000,
    docker_image: 'node:20-slim',
    resource_limits: {
      cpu_quota: 50000,      // 50% of one CPU
      mem_limit: '256m',     // 256MB RAM
      memswap_limit: '256m', // No swap
      pids_limit: 50         // Max 50 processes
    },
    enable_network: false,   // Network isolation
    verbose: true
  });

  try {
    // Initialize (pull image if needed)
    console.log('🔧 Initializing Docker executor...\n');
    await executor.initialize();
    console.log('✅ Docker executor ready!\n');

    // ========================================================================
    // Example 1: Simple JavaScript Execution
    // ========================================================================
    console.log('1️⃣ Simple JavaScript Execution\n');
    console.log('Code:');
    console.log('```javascript');
    const simpleCode = `
console.log('Hello from Docker!');
console.log('Current time:', new Date().toISOString());
const sum = [1, 2, 3, 4, 5].reduce((a, b) => a + b, 0);
console.log('Sum of 1-5:', sum);
`;
    console.log(simpleCode);
    console.log('```\n');

    const result1 = await executor.execute(simpleCode, 'javascript');
    console.log('📊 Result:');
    console.log(`  Success: ${result1.success}`);
    console.log(`  Exit code: ${result1.exit_code}`);
    console.log(`  Execution time: ${result1.execution_time}ms`);
    console.log(`  Output:\n${result1.output}`);
    console.log();

    // ========================================================================
    // Example 2: Data Processing
    // ========================================================================
    console.log('2️⃣ Data Processing Example\n');
    const dataCode = `
const data = [
  { name: 'Alice', age: 30, city: 'New York' },
  { name: 'Bob', age: 25, city: 'London' },
  { name: 'Charlie', age: 35, city: 'Tokyo' },
  { name: 'Diana', age: 28, city: 'Paris' }
];

// Calculate average age
const avgAge = data.reduce((sum, p) => sum + p.age, 0) / data.length;
console.log('Average age:', avgAge);

// Group by city
const byCity = data.reduce((acc, p) => {
  if (!acc[p.city]) acc[p.city] = [];
  acc[p.city].push(p.name);
  return acc;
}, {});
console.log('People by city:', JSON.stringify(byCity, null, 2));
`;

    const result2 = await executor.execute(dataCode, 'javascript');
    console.log('Output:\n' + result2.output);
    console.log();

    // ========================================================================
    // Example 3: Error Handling
    // ========================================================================
    console.log('3️⃣ Error Handling Example\n');
    const errorCode = `
try {
  const result = nonExistentFunction();
} catch (error) {
  console.log('Caught error:', error.message);
}

// This will also error
JSON.parse('invalid json');
`;

    const result3 = await executor.execute(errorCode, 'javascript');
    console.log(`Success: ${result3.success}`);
    console.log(`Exit code: ${result3.exit_code}`);
    console.log(`Error: ${result3.error}`);
    console.log();

    // ========================================================================
    // Example 4: Resource Usage Tracking
    // ========================================================================
    console.log('4️⃣ Resource-Intensive Task\n');
    const cpuCode = `
// Simulate CPU-intensive task
let sum = 0;
for (let i = 0; i < 1000000; i++) {
  sum += Math.sqrt(i);
}
console.log('Computation complete. Sum:', sum.toFixed(2));
`;

    const result4 = await executor.execute(cpuCode, 'javascript');
    console.log('📊 Resource usage:');
    console.log(`  CPU: ${result4.resource_usage?.cpu_percent?.toFixed(2)}%`);
    console.log(`  Memory: ${(result4.resource_usage?.memory_bytes || 0 / 1024 / 1024).toFixed(2)}MB`);
    console.log(`  Time: ${result4.execution_time}ms`);
    console.log();

    // ========================================================================
    // Example 5: Timeout Handling
    // ========================================================================
    console.log('5️⃣ Timeout Handling\n');
    const timeoutExecutor = new DockerSandboxExecutor({
      timeout: 2000, // 2 seconds only
      verbose: false
    });
    await timeoutExecutor.initialize();

    const infiniteLoop = `
// This will timeout
while (true) {
  const x = Math.random();
}
`;

    const result5 = await timeoutExecutor.execute(infiniteLoop, 'javascript');
    console.log(`Success: ${result5.success}`);
    console.log(`Error: ${result5.error}`);
    console.log();

    // ========================================================================
    // Statistics
    // ========================================================================
    const stats = executor.getStats();
    console.log('📊 Executor Statistics:');
    console.log(`  Total executions: ${stats.executions}`);
    console.log(`  Successes: ${stats.successes}`);
    console.log(`  Failures: ${stats.failures}`);
    console.log(`  Success rate: ${stats.success_rate.toFixed(1)}%`);
    console.log(`  Avg execution time: ${stats.average_execution_time.toFixed(0)}ms`);
    console.log(`  Containers created: ${stats.containers_created}`);
    console.log(`  Containers cleaned: ${stats.containers_cleaned}`);
    console.log();

  } catch (error: any) {
    console.error('❌ Docker error:', error.message);
    console.error('Make sure Docker is installed and running!');
    console.error('Test with: docker ps');
  }
}

// ============================================================================
// STEP 2: Advanced Tools Demo
// ============================================================================

async function demoAdvancedTools() {
  console.log('\n🔧 ADVANCED TOOLS DEMO\n');
  console.log('='.repeat(70) + '\n');

  // Prepare test environment
  const testDir = './examples/test_data';
  await fs.ensureDir(testDir);
  
  try {
    // ========================================================================
    // Tool 1: File Operations
    // ========================================================================
    console.log('1️⃣ File Operations\n');
    
    // Write file
    console.log('📝 Writing file...');
    const writeResult = await fileTools[1].execute({
      file_path: `${testDir}/test.txt`,
      content: 'Hello from Advanced Tools!\nThis is a test file.\nLine 3',
      append: false
    });
    console.log(writeResult);
    console.log();

    // Read file
    console.log('📖 Reading file...');
    const readResult = await fileTools[0].execute({
      file_path: `${testDir}/test.txt`
    });
    console.log(readResult);
    console.log();

    // List directory
    console.log('📂 Listing directory...');
    const listResult = await fileTools[2].execute({
      directory_path: testDir,
      recursive: false
    });
    console.log(listResult);
    console.log();

    // ========================================================================
    // Tool 2: Code Execution (VM2)
    // ========================================================================
    console.log('2️⃣ Code Execution (VM2 Sandbox)\n');
    
    const codeResult = await executionTools[0].execute({
      code: `
const data = [10, 20, 30, 40, 50];
const sum = data.reduce((a, b) => a + b, 0);
const avg = sum / data.length;
console.log('Average:', avg);
return { sum, avg, count: data.length };
      `,
      timeout: 5000
    });
    console.log(codeResult);
    console.log();

    // ========================================================================
    // Tool 3: HTTP Requests
    // ========================================================================
    console.log('3️⃣ HTTP Request\n');
    
    const httpResult = await webTools[1].execute({
      url: 'https://api.github.com/repos/nodejs/node',
      method: 'GET',
      timeout: 10000
    });
    const parsed = JSON.parse(httpResult);
    if (parsed.success && parsed.data) {
      console.log('Repository info:');
      console.log(`  Name: ${parsed.data.full_name}`);
      console.log(`  Stars: ${parsed.data.stargazers_count}`);
      console.log(`  Language: ${parsed.data.language}`);
      console.log(`  Description: ${parsed.data.description}`);
    }
    console.log();

    // ========================================================================
    // Tool 4: Current Time
    // ========================================================================
    console.log('4️⃣ Current Time\n');
    
    const timeFormats = ['iso', 'unix', 'human'];
    for (const format of timeFormats) {
      const timeResult = await utilityTools[0].execute({
        format: format as any
      });
      console.log(`${format}:`, timeResult);
    }
    console.log();

  } finally {
    // Cleanup
    await fs.remove(testDir);
    console.log('🗑️  Test directory cleaned up\n');
  }
}

// ============================================================================
// STEP 3: Dual Mode Server
// ============================================================================

async function demoDualModeServer() {
  console.log('\n🚀 DUAL MODE SERVER DEMO\n');
  console.log('='.repeat(70) + '\n');

  // Create custom tools that use Docker and Advanced Tools
  const safeExecute = tool({
    name: 'safe_execute',
    description: 'Execute code safely in Docker sandbox',
    parameters: z.object({
      code: z.string().describe('JavaScript code to execute'),
      timeout: z.number().optional().default(30000)
    }),
    execute: async ({ code, timeout }) => {
      const executor = new DockerSandboxExecutor({
        timeout,
        verbose: false
      });
      
      await executor.initialize();
      const result = await executor.execute(code, 'javascript');
      
      return JSON.stringify({
        success: result.success,
        output: result.output,
        error: result.error,
        execution_time: result.execution_time,
        exit_code: result.exit_code
      }, null, 2);
    }
  });

  const dataProcessor = tool({
    name: 'process_data',
    description: 'Process JSON data with transformations',
    parameters: z.object({
      data: z.string().describe('JSON data to process'),
      operation: z.enum(['sort', 'filter', 'map', 'reduce']).describe('Operation to perform')
    }),
    execute: async ({ data, operation }) => {
      const parsed = JSON.parse(data);
      
      let result;
      switch (operation) {
        case 'sort':
          result = Array.isArray(parsed) ? parsed.sort() : parsed;
          break;
        case 'filter':
          result = Array.isArray(parsed) ? parsed.filter((x: any) => x != null) : parsed;
          break;
        case 'map':
          result = Array.isArray(parsed) ? parsed.map((x: any) => typeof x === 'number' ? x * 2 : x) : parsed;
          break;
        case 'reduce':
          result = Array.isArray(parsed) && parsed.every((x: any) => typeof x === 'number')
            ? parsed.reduce((a: number, b: number) => a + b, 0)
            : parsed;
          break;
      }
      
      return JSON.stringify({ operation, result }, null, 2);
    }
  });

  // Combine with advanced tools
  const allTools = [
    safeExecute,
    dataProcessor,
    ...fileTools,
    ...executionTools,
    utilityTools[0]
  ];

  // Create dual mode server
  const server = new DualModeMCPServer(allTools, {
    name: 'Advanced MCP Server',
    version: '1.0.0',
    http: {
      enabled: true,
      port: 8000,
      title: 'Advanced MCP Server',
      description: 'MCP server with Docker sandbox and advanced tools'
    },
    stdio: {
      enabled: true
    },
    verbose: true
  });

  console.log('🚀 Starting Dual Mode Server...\n');
  await server.start();

  console.log('\n📚 Server is ready! You can access it via:\n');
  console.log('1️⃣ HTTP Mode:');
  console.log('   curl http://localhost:8000/mcp/list_tools');
  console.log('   curl -X POST http://localhost:8000/mcp/invoke \\');
  console.log('     -H "Content-Type: application/json" \\');
  console.log('     -d \'{"tool":"get_current_time","parameters":{}}\'\n');
  
  console.log('2️⃣ Stdio Mode:');
  console.log('   echo \'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\' | tsx ...\n');
  
  console.log('3️⃣ Test with Client:');
  console.log('   tsx examples/docker_advanced_example.ts test-client\n');

  console.log('Press Ctrl+C to stop the server.\n');

  // Keep server running
  await new Promise(() => {}); // Never resolves
}

// ============================================================================
// STEP 4: Test Client for Dual Mode Server
// ============================================================================

async function testDualModeClient() {
  console.log('\n🧪 TESTING DUAL MODE SERVER\n');
  console.log('='.repeat(70) + '\n');

  // Test HTTP endpoint
  console.log('1️⃣ Testing HTTP endpoint...\n');
  try {
    const listResponse = await fetch('http://localhost:8000/mcp/list_tools');
    const tools = await listResponse.json();
    console.log(`✅ HTTP: Found ${tools.tools.length} tools\n`);
    
    // Test tool invocation
    const invokeResponse = await fetch('http://localhost:8000/mcp/invoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool: 'get_current_time',
        parameters: { format: 'iso' }
      })
    });
    const result = await invokeResponse.json();
    console.log('HTTP tool result:', result);
    console.log();
  } catch (error: any) {
    console.log('❌ HTTP test failed:', error.message);
    console.log('Make sure server is running: tsx examples/docker_advanced_example.ts server\n');
  }

  // Test Stdio endpoint (requires server to support dual mode)
  console.log('2️⃣ Testing Stdio via JSON-RPC...\n');
  console.log('(This requires the server to be running in stdio mode)\n');
}

// ============================================================================
// STEP 5: Complete Workflow
// ============================================================================

async function completeWorkflow() {
  console.log('\n🎯 COMPLETE WORKFLOW\n');
  console.log('='.repeat(70) + '\n');

  // Step 1: Docker Executor
  console.log('STEP 1: Docker Executor\n');
  
  const executor = new DockerSandboxExecutor({
    timeout: 15000,
    verbose: false
  });
  
  console.log('Initializing Docker...');
  await executor.initialize();
  console.log('✅ Docker ready\n');

  // Step 2: Execute some code
  console.log('STEP 2: Execute Code in Sandbox\n');
  
  const analysisCode = `
const transactions = [
  { id: 1, amount: 100, type: 'credit' },
  { id: 2, amount: 50, type: 'debit' },
  { id: 3, amount: 200, type: 'credit' },
  { id: 4, amount: 75, type: 'debit' }
];

const credits = transactions.filter(t => t.type === 'credit').reduce((sum, t) => sum + t.amount, 0);
const debits = transactions.filter(t => t.type === 'debit').reduce((sum, t) => sum + t.amount, 0);
const balance = credits - debits;

console.log(JSON.stringify({
  total_credits: credits,
  total_debits: debits,
  balance: balance,
  transaction_count: transactions.length
}, null, 2));
`;

  const result = await executor.execute(analysisCode, 'javascript');
  console.log('Analysis result:');
  console.log(result.output);
  console.log();

  // Step 3: Use Advanced Tools
  console.log('STEP 3: Use Advanced Tools\n');
  
  const testDir = './examples/workflow_output';
  await fs.ensureDir(testDir);

  try {
    // Save result to file
    console.log('💾 Saving result to file...');
    await fileTools[1].execute({
      file_path: `${testDir}/analysis.json`,
      content: result.output
    });
    console.log('✅ Saved to analysis.json\n');

    // Read it back
    console.log('📖 Reading file back...');
    const fileContent = await fileTools[0].execute({
      file_path: `${testDir}/analysis.json`
    });
    console.log('File content:', fileContent);
    console.log();

    // Get timestamp
    console.log('🕐 Getting timestamp...');
    const timestamp = await utilityTools[0].execute({ format: 'iso' });
    console.log('Timestamp:', timestamp);
    console.log();

  } finally {
    await fs.remove(testDir);
    console.log('🗑️  Cleanup complete\n');
  }

  // Step 4: Stats
  const stats = executor.getStats();
  console.log('📊 Final Statistics:');
  console.log(`  Executions: ${stats.executions}`);
  console.log(`  Success rate: ${stats.success_rate.toFixed(1)}%`);
  console.log(`  Avg time: ${stats.average_execution_time.toFixed(0)}ms`);
  console.log();

  console.log('✅ Complete workflow finished!\n');
}

// ============================================================================
// STEP 6: Helper Function - Quick Docker Test
// ============================================================================

async function quickDockerTest() {
  console.log('\n⚡ QUICK DOCKER TEST\n');
  console.log('='.repeat(70) + '\n');

  console.log('Testing Docker with simple code execution...\n');

  const result = await executeInDocker(
    `
console.log('Docker is working!');
console.log('Node version:', process.version);
console.log('Platform:', process.platform);
console.log('2 + 2 =', 2 + 2);
    `,
    'javascript',
    {
      timeout: 10000,
      verbose: true
    }
  );

  console.log('\n📊 Result:');
  console.log(`  Success: ${result.success}`);
  console.log(`  Time: ${result.execution_time}ms`);
  console.log(`  Output:\n${result.output}`);
  console.log();
}

// ============================================================================
// Main Entry Point
// ============================================================================

async function main() {
  const command = process.argv[2] || 'help';

  try {
    switch (command) {
      case 'docker':
        await demoDockerExecutor();
        break;

      case 'tools':
        await demoAdvancedTools();
        break;

      case 'server':
        await demoDualModeServer();
        break;

      case 'test-client':
        await testDualModeClient();
        break;

      case 'workflow':
        await completeWorkflow();
        break;

      case 'quick':
        await quickDockerTest();
        break;

      default:
        console.log(`
🚀 Docker Executor & Advanced Tools Example

Usage:
  tsx examples/docker_advanced_example.ts <command>

Commands:
  docker        Full Docker executor demo
  tools         Advanced tools demo
  server        Run Dual Mode server (HTTP + Stdio)
  test-client   Test client for Dual Mode server
  workflow      Complete workflow demonstration
  quick         Quick Docker test

Examples:
  # Test Docker executor
  tsx examples/docker_advanced_example.ts docker

  # Test advanced tools
  tsx examples/docker_advanced_example.ts tools

  # Run server (Terminal 1)
  tsx examples/docker_advanced_example.ts server

  # Test server (Terminal 2)
  tsx examples/docker_advanced_example.ts test-client

  # Complete workflow
  tsx examples/docker_advanced_example.ts workflow

  # Quick test
  tsx examples/docker_advanced_example.ts quick

Prerequisites:
  - Docker installed and running (docker ps)
  - Node.js 18+
  - All dependencies installed (npm install)

Note:
  If Docker is not available, some features will be skipped.
  You can still test the advanced tools and dual mode server.
`);
    }
  } catch (error: any) {
    console.error('\n❌ Error:', error.message);
    if (error.message.includes('Docker')) {
      console.error('\n💡 Make sure Docker is installed and running:');
      console.error('   docker --version');
      console.error('   docker ps');
    }
    process.exit(1);
  }
}

main();
