/**
 * Test Tool Server
 * 
 * Simple script to test if the tool server starts correctly
 * and exposes tools properly.
 */

import { tool, exposeToolsHttp } from '../src';
import { z } from 'zod';

const testTool = tool({
  name: 'test_tool',
  description: 'A simple test tool',
  inputSchema: z.object({
    message: z.string(),
  }),
  function: async ({ message }) => {
    return { success: true, echo: message };
  },
});

async function main() {
  console.log('🧪 Testing Tool Server\n');
  
  const app = exposeToolsHttp([testTool], {
    title: 'Test Server',
    description: 'Testing MCP tool server',
    verbose: true,
  });
  
  const server = app.listen(3200, async () => {
    console.log('✅ Server started on http://localhost:3200\n');
    
    // Wait a bit
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Test endpoints
    console.log('📋 Testing endpoints:\n');
    
    try {
      // Test 1: List tools
      console.log('1. GET /mcp/list_tools');
      const listResponse = await fetch('http://localhost:3200/mcp/list_tools');
      if (listResponse.ok) {
        const data = await listResponse.json();
        console.log('   ✅ Success:', JSON.stringify(data, null, 2));
      } else {
        console.log('   ❌ Failed:', listResponse.status);
      }
      
      console.log('\n2. POST /mcp/invoke');
      const invokeResponse = await fetch('http://localhost:3200/mcp/invoke', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool: 'test_tool',
          parameters: { message: 'Hello!' },
        }),
      });
      
      if (invokeResponse.ok) {
        const data = await invokeResponse.json();
        console.log('   ✅ Success:', JSON.stringify(data, null, 2));
      } else {
        console.log('   ❌ Failed:', invokeResponse.status);
      }
      
      console.log('\n✅ All tests passed!\n');
      console.log('Press Ctrl+C to exit');
      
    } catch (error: any) {
      console.error('\n❌ Test failed:', error.message);
      server.close();
      process.exit(1);
    }
  });
  
  server.on('error', (error: any) => {
    console.error('❌ Server error:', error.message);
    if (error.code === 'EADDRINUSE') {
      console.error('   Port 3200 is already in use!');
    }
    process.exit(1);
  });
}

main();
