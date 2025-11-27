/**
 * Authentication Example - Using JWT and API Keys
 * 
 * This example shows how to use authentication with MCP servers.
 */

import { z } from 'zod';
import { tool, exposeToolsHttp, createAuthManager } from '../src';

// ============================================================================
// Define Protected Tools
// ============================================================================

const secretTool = tool({
  name: 'get_secret',
  description: 'Get a secret value (requires authentication)',
  inputSchema: z.object({
    key: z.string().describe('Secret key to retrieve'),
  }),
  function: async ({ key }) => {
    return {
      key,
      value: `Secret value for ${key}`,
      timestamp: new Date().toISOString(),
    };
  },
});

const adminTool = tool({
  name: 'admin_action',
  description: 'Perform an admin action (requires authentication)',
  inputSchema: z.object({
    action: z.string().describe('Action to perform'),
  }),
  function: async ({ action }) => {
    return {
      action,
      result: `Admin action "${action}" completed`,
      timestamp: new Date().toISOString(),
    };
  },
});

// ============================================================================
// Start Server with Authentication
// ============================================================================

async function main() {
  const tools = [secretTool, adminTool];
  
  console.log('Starting authenticated MCP server...\n');
  
  // Create auth manager with JWT
  const authManager = createAuthManager({
    type: 'jwt',
    jwtSecret: 'your-secret-key-change-this-in-production',
    jwtExpiration: '1h',
  });
  
  // Generate a test token
  const testToken = authManager.getJWTManager().generateToken({
    sub: 'user123',
    name: 'Test User',
    role: 'admin',
  });
  
  console.log('🔐 Test JWT Token:');
  console.log(testToken);
  console.log('\n');
  
  // Create server app
  const app = exposeToolsHttp(tools, {
    title: 'Authenticated MCP Server',
    description: 'Server with JWT authentication example',
    verbose: true,
  });
  
  // Add authentication middleware
  app.use('/mcp/invoke', (req, res, next) => {
    const authHeader = req.headers.authorization;
    
    try {
      authManager.authenticate(authHeader);
      next();
    } catch (error: any) {
      res.status(401).json({
        error: 'Authentication required',
        message: error.message,
      });
    }
  });
  
  // Start server
  const PORT = 3001;
  const HOST = '0.0.0.0';
  
  app.listen(PORT, HOST, () => {
    console.log('✅ Authenticated server started!');
    console.log(`📡 Listening on http://localhost:${PORT}`);
    
    console.log('\n📝 Example authenticated request:');
    console.log(`curl -X POST http://localhost:${PORT}/mcp/invoke \\`);
    console.log(`  -H "Content-Type: application/json" \\`);
    console.log(`  -H "Authorization: Bearer ${testToken}" \\`);
    console.log(`  -d '{"tool": "get_secret", "parameters": {"key": "my-key"}}'`);
    
    console.log('\n📝 Without token (will fail):');
    console.log(`curl -X POST http://localhost:${PORT}/mcp/invoke \\`);
    console.log(`  -H "Content-Type: application/json" \\`);
    console.log(`  -d '{"tool": "get_secret", "parameters": {"key": "my-key"}}'`);
    
    console.log('\n\n⌨️  Press Ctrl+C to stop the server\n');
  });
}

// ============================================================================
// Alternative: API Key Authentication
// ============================================================================

async function mainWithApiKey() {
  const tools = [secretTool, adminTool];
  
  console.log('Starting API key authenticated MCP server...\n');
  
  const API_KEY = 'my-secret-api-key';
  
  // Create auth manager with API key
  const authManager = createAuthManager({
    type: 'api_key',
    apiKey: API_KEY,
  });
  
  // Create server app
  const app = exposeToolsHttp(tools, {
    title: 'API Key Authenticated Server',
    description: 'Server with API key authentication',
    verbose: true,
  });
  
  // Add authentication middleware
  app.use('/mcp/invoke', (req, res, next) => {
    const authHeader = req.headers.authorization;
    
    try {
      authManager.authenticate(authHeader);
      next();
    } catch (error: any) {
      res.status(401).json({
        error: 'Authentication required',
        message: error.message,
      });
    }
  });
  
  // Start server
  const PORT = 3002;
  const HOST = '0.0.0.0';
  
  app.listen(PORT, HOST, () => {
    console.log('✅ API Key authenticated server started!');
    console.log(`📡 Listening on http://localhost:${PORT}`);
    
    console.log('\n📝 Example authenticated request:');
    console.log(`curl -X POST http://localhost:${PORT}/mcp/invoke \\`);
    console.log(`  -H "Content-Type: application/json" \\`);
    console.log(`  -H "Authorization: Bearer ${API_KEY}" \\`);
    console.log(`  -d '{"tool": "get_secret", "parameters": {"key": "my-key"}}'`);
    
    console.log('\n\n⌨️  Press Ctrl+C to stop the server\n');
  });
}

// Run the example
if (require.main === module) {
  const useApiKey = process.argv.includes('--api-key');
  
  if (useApiKey) {
    mainWithApiKey().catch(error => {
      console.error('❌ Error:', error);
      process.exit(1);
    });
  } else {
    main().catch(error => {
      console.error('❌ Error:', error);
      process.exit(1);
    });
  }
}

export { main, mainWithApiKey };
