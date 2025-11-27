/**
 * Ollama Agent Example
 * 
 * Advanced agent example using Ollama as a local LLM provider.
 * Demonstrates how to use PolyAgent with a local LLM for tool orchestration.
 * 
 * Prerequisites:
 * 1. Install Ollama: https://ollama.ai/download
 * 2. Pull a model: ollama pull llama2
 * 3. Start Ollama server: ollama serve (usually runs by default)
 * 
 * Test Ollama is running:
 * curl http://localhost:11434/api/tags
 */

import { UnifiedPolyAgent } from '../src/agent/unified_agent';
import { OllamaProvider } from '../src/agent/llm_providers';
import { tool, exposeToolsHttp } from '../src';
import { z } from 'zod';
import * as http from 'http';

// ============================================================================
// Define Tools for the Agent
// ============================================================================

const searchWebTool = tool({
  name: 'search_web',
  description: 'Search the web for information (simulated)',
  inputSchema: z.object({
    query: z.string().describe('Search query'),
    maxResults: z.number().default(5).describe('Maximum number of results'),
  }),
  function: async ({ query, maxResults }) => {
    // Simulated web search results
    const results = [
      { title: `Result 1 for "${query}"`, url: 'https://example.com/1', snippet: 'Relevant information about ' + query },
      { title: `Result 2 for "${query}"`, url: 'https://example.com/2', snippet: 'More details about ' + query },
      { title: `Result 3 for "${query}"`, url: 'https://example.com/3', snippet: 'Additional context for ' + query },
    ].slice(0, maxResults);
    
    return {
      query,
      results,
      count: results.length,
    };
  },
});

const calculateTool = tool({
  name: 'calculate',
  description: 'Perform mathematical calculations',
  inputSchema: z.object({
    expression: z.string().describe('Mathematical expression to evaluate'),
  }),
  function: async ({ expression }) => {
    try {
      // Safe eval for math expressions
      const result = Function(`'use strict'; return (${expression})`)();
      return {
        expression,
        result,
        success: true,
      };
    } catch (error: any) {
      return {
        expression,
        error: error.message,
        success: false,
      };
    }
  },
});

const getWeatherTool = tool({
  name: 'get_weather',
  description: 'Get current weather for a location',
  inputSchema: z.object({
    location: z.string().describe('City name or coordinates'),
    units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
  }),
  function: async ({ location, units }) => {
    // Simulated weather data
    const temp = units === 'celsius' ? 22 : 72;
    return {
      location,
      temperature: temp,
      units,
      condition: 'Partly cloudy',
      humidity: 65,
      windSpeed: 15,
    };
  },
});

const fileOperationsTool = tool({
  name: 'file_operations',
  description: 'Simulate file system operations',
  inputSchema: z.object({
    operation: z.enum(['read', 'write', 'list', 'delete']),
    path: z.string().describe('File path'),
    content: z.string().optional().describe('Content for write operation'),
  }),
  function: async ({ operation, path, content }) => {
    // Simulated file operations
    switch (operation) {
      case 'read':
        return { operation, path, content: `Contents of ${path}`, success: true };
      case 'write':
        return { operation, path, content, success: true };
      case 'list':
        return { operation, path, files: ['file1.txt', 'file2.json', 'file3.md'], success: true };
      case 'delete':
        return { operation, path, success: true };
      default:
        return { operation, success: false, error: 'Unknown operation' };
    }
  },
});

const sendEmailTool = tool({
  name: 'send_email',
  description: 'Send an email (simulated)',
  inputSchema: z.object({
    to: z.string().email().describe('Recipient email'),
    subject: z.string().describe('Email subject'),
    body: z.string().describe('Email body'),
  }),
  function: async ({ to, subject, body }) => {
    console.log(`\n📧 Simulated email sent:`);
    console.log(`   To: ${to}`);
    console.log(`   Subject: ${subject}`);
    console.log(`   Body: ${body.substring(0, 100)}...`);
    
    return {
      success: true,
      to,
      subject,
      messageId: `msg_${Date.now()}`,
      timestamp: new Date().toISOString(),
    };
  },
});

// ============================================================================
// Start Tools Server
// ============================================================================

let toolsServer: http.Server | null = null;

async function startToolsServer(): Promise<void> {
  return new Promise((resolve, reject) => {
    const tools = [
      searchWebTool,
      calculateTool,
      getWeatherTool,
      fileOperationsTool,
      sendEmailTool,
    ];
    
    console.log('🔧 Starting tools server on port 3200...');
    
    const app = exposeToolsHttp(tools, {
      title: 'Ollama Agent Tools',
      description: 'Tools for Ollama Agent examples',
      verbose: false,
    });
    
    toolsServer = app.listen(3200, () => {
      console.log('✅ Tools server started on http://localhost:3200');
      console.log(`📋 Available tools: ${tools.map(t => t.name).join(', ')}`);
      resolve();
    });
    
    toolsServer.on('error', (error: any) => {
      console.error('❌ Server error:', error.message);
      if (error.code === 'EADDRINUSE') {
        console.error('   Port 3200 is already in use!');
        console.error('   Try: lsof -i :3200 or netstat -ano | findstr :3200');
      }
      reject(error);
    });
  });
}

async function stopToolsServer(): Promise<void> {
  return new Promise((resolve) => {
    if (toolsServer) {
      toolsServer.close(() => {
        if (process.env.VERBOSE) {
          console.log('✅ Tools server stopped');
        }
        resolve();
      });
    } else {
      resolve();
    }
  });
}

// ============================================================================
// Agent Configuration and Execution
// ============================================================================

async function runOllamaAgent() {
  console.log('🦙 Ollama Agent Example\n');
  
  // Check if Ollama is running
  try {
    const response = await fetch('http://localhost:11434/api/tags');
    if (!response.ok) {
      throw new Error('Ollama not responding');
    }
    console.log('✅ Ollama is running\n');
  } catch (error) {
    console.error('❌ Error: Ollama is not running!');
    console.error('   Please install Ollama from https://ollama.ai/download');
    console.error('   Then run: ollama serve\n');
    process.exit(1);
  }
  
  // Start tools server
  await startToolsServer();
  
  // Wait for server to be ready
  console.log('⏳ Waiting for server to be ready...');
  await new Promise(resolve => setTimeout(resolve, 1000));
  
  // Verify server is reachable
  try {
    const testResponse = await fetch('http://localhost:3200/mcp/list_tools');
    if (testResponse.ok) {
      const tools: any = await testResponse.json();
      console.log(`✅ Server verified! Found ${tools.tools?.length || 0} tools\n`);
    } else {
      console.error('⚠️  Server responded but with error status:', testResponse.status);
    }
  } catch (error: any) {
    console.error('❌ Cannot reach tools server:', error.message);
    console.error('   Make sure port 3200 is not blocked\n');
    await stopToolsServer();
    process.exit(1);
  }
  
  // Create Ollama provider
  const llmProvider = new OllamaProvider({
    model: 'gpt-oss:120b-cloud', // or 'mistral', 'codellama', etc.
    baseUrl: 'http://localhost:11434',
    temperature: 0.7,
    maxTokens: 1000,
  });
  
  // Create agent with tools server
  const agent = new UnifiedPolyAgent({
    llmProvider,
    mcpServers: ['http://localhost:3200/mcp'], // Connect to our tools server
    verbose: true,
  });
  
  // CRITICAL: Start agent to discover tools!
  console.log('🔍 Starting agent and discovering tools...');
  await agent.start();
  console.log('✅ Agent started and tools discovered!\n');
  
  console.log('🤖 Agent initialized with tools:');
  console.log('   - search_web: Search for information');
  console.log('   - calculate: Mathematical calculations');
  console.log('   - get_weather: Weather information');
  console.log('   - file_operations: File system operations');
  console.log('   - send_email: Send emails\n');
  
  // ============================================================================
  // Example 1: Simple Query
  // ============================================================================
  
  console.log('═'.repeat(70));
  console.log('Example 1: Simple Information Query');
  console.log('═'.repeat(70) + '\n');
  
  try {
    const result1 = await agent.runAsync(
      'What is the weather like in San Francisco?',
      5  // maxSteps
    );
    console.log('\n📊 Result:', result1);
  } catch (error: any) {
    console.error('Error:', error.message);
  }
  
  // ============================================================================
  // Example 2: Multi-Step Task
  // ============================================================================
  
  console.log('\n\n' + '═'.repeat(70));
  console.log('Example 2: Multi-Step Task with Calculations');
  console.log('═'.repeat(70) + '\n');
  
  try {
    const result2 = await agent.runAsync(
      'Calculate 15% tip on a $85.50 bill, then tell me the total amount',
      5  // maxSteps
    );
    console.log('\n📊 Result:', result2);
  } catch (error: any) {
    console.error('Error:', error.message);
  }
  
  // ============================================================================
  // Example 3: Complex Workflow
  // ============================================================================
  
  console.log('\n\n' + '═'.repeat(70));
  console.log('Example 3: Complex Workflow (Search + Calculate + Email)');
  console.log('═'.repeat(70) + '\n');
  
  try {
    const result3 = await agent.runAsync(
      'Search for "TypeScript tutorial", then calculate how many hours it would take to complete if each tutorial takes 2.5 hours and there are 3 results',
      5  // maxSteps
    );
    console.log('\n📊 Result:', result3);
  } catch (error: any) {
    console.error('Error:', error.message);
  }
  
  // ============================================================================
  // Example 4: File Operations
  // ============================================================================
  
  console.log('\n\n' + '═'.repeat(70));
  console.log('Example 4: File Operations Workflow');
  console.log('═'.repeat(70) + '\n');
  
  try {
    const result4 = await agent.runAsync(
      'List the files in /home/user/documents directory',
      5  // maxSteps
    );
    console.log('\n📊 Result:', result4);
  } catch (error: any) {
    console.error('Error:', error.message);
  }
  
  console.log('\n\n✅ All examples completed!\n');
  
  // Cleanup
  await stopToolsServer();
}

// ============================================================================
// Advanced: Interactive Mode
// ============================================================================

async function interactiveMode() {
  const readline = require('readline');
  
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  
  console.log('🦙 Ollama Agent - Interactive Mode\n');
  console.log('Available commands:');
  console.log('  - Type your query and press Enter');
  console.log('  - Type "exit" to quit');
  console.log('  - Type "tools" to see available tools\n');
  
  // Start tools server
  await startToolsServer();
  
  // Wait for server to be ready
  console.log('⏳ Waiting for server to be ready...');
  await new Promise(resolve => setTimeout(resolve, 1000));
  
  // Verify server is reachable
  try {
    const testResponse = await fetch('http://localhost:3200/mcp/list_tools');
    if (testResponse.ok) {
      const tools: any = await testResponse.json();
      console.log(`✅ Server verified! Found ${tools.tools?.length || 0} tools\n`);
    }
  } catch (error: any) {
    console.error('❌ Cannot reach tools server:', error.message);
    await stopToolsServer();
    process.exit(1);
  }
  
  const llmProvider = new OllamaProvider({
    model: 'gpt-oss:120b-cloud',
    baseUrl: 'http://localhost:11434',
    temperature: 0.7,
  });
  
  const agent = new UnifiedPolyAgent({
    llmProvider,
    mcpServers: ['http://localhost:3200/mcp'],
    verbose: false, // Less verbose for interactive mode
  });
  
  // CRITICAL: Start agent to discover tools!
  console.log('🔍 Starting agent and discovering tools...');
  await agent.start();
  console.log('✅ Agent ready! Type your queries below.\n');
  
  const askQuestion = () => {
    rl.question('\n🤔 You: ', async (query: string) => {
      if (query.toLowerCase() === 'exit') {
        console.log('\n👋 Goodbye!\n');
        await stopToolsServer();
        rl.close();
        return;
      }
      
      if (query.toLowerCase() === 'tools') {
        console.log('\n🔧 Available tools:');
        console.log('  - search_web: Search for information');
        console.log('  - calculate: Mathematical calculations');
        console.log('  - get_weather: Weather information');
        console.log('  - file_operations: File system operations');
        console.log('  - send_email: Send emails');
        askQuestion();
        return;
      }
      
      if (!query.trim()) {
        askQuestion();
        return;
      }
      
      try {
        console.log('\n🤖 Agent: Working on it...\n');
        const result = await agent.runAsync(query, 5);
        console.log('🤖 Agent:', result);
      } catch (error: any) {
        console.error('❌ Error:', error.message);
      }
      
      askQuestion();
    });
  };
  
  askQuestion();
}

// ============================================================================
// Main Entry Point
// ============================================================================

async function main() {
  const args = process.argv.slice(2);
  
  if (args.includes('--interactive') || args.includes('-i')) {
    await interactiveMode();
  } else {
    await runOllamaAgent();
  }
}

main().catch(async (error) => {
  console.error(error);
  await stopToolsServer();
  process.exit(1);
});

