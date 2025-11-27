/**
 * Simple Example - Basic Tool Creation and Server
 * 
 * This example demonstrates the simplified API for creating tools and starting a server.
 */

import { z } from 'zod';
import { tool, exposeToolsHttp } from '../src';

// ============================================================================
// Define Tools
// ============================================================================

// Simple addition tool
const addTool = tool({
  name: 'add',
  description: 'Add two numbers together',
  inputSchema: z.object({
    a: z.number().describe('First number'),
    b: z.number().describe('Second number'),
  }),
  function: async ({ a, b }) => {
    return a + b;
  },
});

// String manipulation tool
const uppercaseTool = tool({
  name: 'uppercase',
  description: 'Convert a string to uppercase',
  inputSchema: z.object({
    text: z.string().describe('The text to convert'),
  }),
  function: async ({ text }) => {
    return text.toUpperCase();
  },
});

// Array manipulation tool
const reverseTool = tool({
  name: 'reverse',
  description: 'Reverse an array',
  inputSchema: z.object({
    items: z.array(z.any()).describe('Array to reverse'),
  }),
  function: async ({ items }) => {
    return items.reverse();
  },
});

// Weather tool (simulated)
const weatherTool = tool({
  name: 'get_weather',
  description: 'Get current weather for a location',
  inputSchema: z.object({
    location: z.string().describe('City name or coordinates'),
    units: z.enum(['celsius', 'fahrenheit']).optional().default('celsius'),
  }),
  function: async ({ location, units }) => {
    // Simulated weather data
    return {
      location,
      temperature: units === 'celsius' ? 22 : 72,
      condition: 'Sunny',
      humidity: 45,
      units,
    };
  },
});

// ============================================================================
// Start Server
// ============================================================================

async function main() {
  const tools = [addTool, uppercaseTool, reverseTool, weatherTool];
  
  console.log('Starting MCP server with tools:', tools.map(t => t.name).join(', '));
  
  // Create HTTP server app
  const app = exposeToolsHttp(tools, {
    title: 'Simple MCP Server',
    description: 'Example server with basic tools',
    verbose: true,
  });
  
  // Start the server
  const PORT = 3000;
  const HOST = '0.0.0.0';
  
  app.listen(PORT, HOST, () => {
    console.log('\n✅ Server started successfully!');
    console.log(`📡 Listening on http://localhost:${PORT}`);
    console.log('\n📋 Available endpoints:');
    console.log(`  GET  http://localhost:${PORT}/`);
    console.log(`  GET  http://localhost:${PORT}/health`);
    console.log(`  GET  http://localhost:${PORT}/mcp/list_tools`);
    console.log(`  POST http://localhost:${PORT}/mcp/invoke`);
    console.log('\n🔧 Available tools:');
    tools.forEach(tool => {
      console.log(`  - ${tool.name}: ${tool.description}`);
    });
    
    console.log('\n📝 Example requests:');
    console.log('\n1. List tools:');
    console.log(`   curl http://localhost:${PORT}/mcp/list_tools`);
    
    console.log('\n2. Invoke tool (add):');
    console.log(`   Windows PowerShell:`);
    console.log(`   curl -X POST http://localhost:${PORT}/mcp/invoke -H "Content-Type: application/json" -d "{\\"tool\\": \\"add\\", \\"parameters\\": {\\"a\\": 5, \\"b\\": 3}}"`);
    console.log(`   `);
    console.log(`   Linux/Mac:`);
    console.log(`   curl -X POST http://localhost:${PORT}/mcp/invoke -H "Content-Type: application/json" -d '{"tool": "add", "parameters": {"a": 5, "b": 3}}'`);
    
    console.log('\n3. Get weather:');
    console.log(`   Windows PowerShell:`);
    console.log(`   curl -X POST http://localhost:${PORT}/mcp/invoke -H "Content-Type: application/json" -d "{\\"tool\\": \\"get_weather\\", \\"parameters\\": {\\"location\\": \\"San Francisco\\"}}"`);
    console.log(`   `);
    console.log(`   Linux/Mac:`);
    console.log(`   curl -X POST http://localhost:${PORT}/mcp/invoke -H "Content-Type: application/json" -d '{"tool": "get_weather", "parameters": {"location": "San Francisco"}}'`);
    
    console.log('\n\n⌨️  Press Ctrl+C to stop the server\n');
  });
}

// Error handling
main().catch(error => {
  console.error('❌ Error starting server:', error);
  process.exit(1);
});
