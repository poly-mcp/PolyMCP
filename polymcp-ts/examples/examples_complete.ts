/**
 * EXAMPLE: Complete PolyAgent v2.0 Usage
 * 
 * This example demonstrates all the new features of PolyAgent v2.0:
 * - Authentication (API Key, JWT, OAuth2)
 * - Multiple servers
 * - Custom headers
 * - Timeout configuration
 * - Error handling
 * - Dynamic auth updates
 */

import { PolyAgent } from './agent';
import { OpenAIProvider, AnthropicProvider } from './llm_providers';

// Auth imports
import { 
  APIKeyAuthProvider, 
  BasicAuthProvider 
} from './auth/auth_base';
import { JWTAuthProvider } from './auth/jwt_auth';
import { OAuth2AuthProvider } from './auth/oauth2_auth';
import { MCPAuthManager } from './auth/mcp_auth';

// ============================================================================
// EXAMPLE 1: Simple Agent (No Auth) - Backward Compatible
// ============================================================================

async function example1_simpleAgent() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 1: Simple Agent (No Auth)');
  console.log('='.repeat(60));

  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ 
      apiKey: process.env.OPENAI_API_KEY || 'sk-...' 
    }),
    mcpServers: [
      'https://api.example.com',
      'https://tools.example.com'
    ],
    verbose: true
  });

  const result = await agent.run('What tools are available?');
  console.log('\nResult:', result);
}

// ============================================================================
// EXAMPLE 2: Agent with API Key Authentication
// ============================================================================

async function example2_apiKeyAuth() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 2: Agent with API Key Auth');
  console.log('='.repeat(60));

  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ 
      apiKey: process.env.OPENAI_API_KEY || 'sk-...' 
    }),
    mcpServers: ['https://secure-api.example.com'],
    authProvider: new APIKeyAuthProvider(
      'your-api-key-here',
      'X-API-Key',  // Custom header name
      ''            // No prefix (just the key)
    ),
    verbose: true
  });

  const result = await agent.run('Execute secure task');
  console.log('\nResult:', result);
}

// ============================================================================
// EXAMPLE 3: Agent with JWT Authentication
// ============================================================================

async function example3_jwtAuth() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 3: Agent with JWT Auth');
  console.log('='.repeat(60));

  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ 
      apiKey: process.env.OPENAI_API_KEY || 'sk-...' 
    }),
    mcpServers: ['https://jwt-protected.example.com'],
    authProvider: new JWTAuthProvider({
      secret: process.env.JWT_SECRET || 'my-secret-key',
      algorithm: 'HS256',
      claims: {
        user_id: 'user-123',
        role: 'admin',
        permissions: ['read', 'write', 'execute']
      },
      expiresIn: 3600, // 1 hour
      issuer: 'my-app',
      audience: 'mcp-api'
    }),
    timeout: 60000, // 1 minute timeout
    verbose: true
  });

  const result = await agent.run('Execute authenticated task');
  console.log('\nResult:', result);
  
  // JWT will auto-refresh when expired
  console.log('\nWaiting to test auto-refresh...');
  await new Promise(resolve => setTimeout(resolve, 2000));
  
  const result2 = await agent.run('Another task (token refreshed if needed)');
  console.log('\nResult 2:', result2);
}

// ============================================================================
// EXAMPLE 4: Agent with OAuth2 Client Credentials
// ============================================================================

async function example4_oauth2Auth() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 4: Agent with OAuth2 Auth');
  console.log('='.repeat(60));

  // Create OAuth2 provider
  const oauth2Auth = new OAuth2AuthProvider({
    flow: 'client_credentials',
    clientId: process.env.OAUTH_CLIENT_ID || 'your-client-id',
    clientSecret: process.env.OAUTH_CLIENT_SECRET || 'your-client-secret',
    tokenUrl: 'https://auth.example.com/oauth/token',
    scope: ['mcp.read', 'mcp.execute']
  });

  // Initialize to fetch initial token
  console.log('Fetching OAuth2 token...');
  await oauth2Auth.initialize();
  console.log('✓ OAuth2 token obtained');

  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ 
      apiKey: process.env.OPENAI_API_KEY || 'sk-...' 
    }),
    mcpServers: ['https://oauth-api.example.com'],
    authProvider: oauth2Auth,
    verbose: true
  });

  const result = await agent.run('Execute OAuth2 protected task');
  console.log('\nResult:', result);
}

// ============================================================================
// EXAMPLE 5: Multiple Servers with Different Auth
// ============================================================================

async function example5_multiServerAuth() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 5: Multiple Servers with Different Auth');
  console.log('='.repeat(60));

  // Setup auth manager with different auth for different servers
  const authManager = new MCPAuthManager({
    servers: [
      {
        pattern: 'https://api1.example.com',
        type: 'api_key',
        config: {
          apiKey: 'key-for-api1',
          headerName: 'X-API-Key'
        }
      },
      {
        pattern: 'https://api2.example.com',
        type: 'jwt',
        config: {
          secret: 'jwt-secret',
          algorithm: 'HS256',
          claims: { service: 'api2' }
        }
      },
      {
        pattern: /^https:\/\/secure\..*\.com$/,
        type: 'oauth2',
        config: {
          flow: 'client_credentials',
          clientId: 'oauth-client',
          clientSecret: 'oauth-secret',
          tokenUrl: 'https://auth.example.com/token'
        }
      }
    ]
  });

  // Create separate agents for each server
  const agent1 = new PolyAgent({
    llmProvider: new OpenAIProvider({ apiKey: 'sk-...' }),
    mcpServers: ['https://api1.example.com'],
    authProvider: authManager.getAuthForUrl('https://api1.example.com'),
    verbose: true
  });

  const agent2 = new PolyAgent({
    llmProvider: new OpenAIProvider({ apiKey: 'sk-...' }),
    mcpServers: ['https://api2.example.com'],
    authProvider: authManager.getAuthForUrl('https://api2.example.com'),
    verbose: true
  });

  console.log('\nExecuting on API 1 (API Key auth)...');
  const result1 = await agent1.run('Task for API 1');
  
  console.log('\nExecuting on API 2 (JWT auth)...');
  const result2 = await agent2.run('Task for API 2');

  console.log('\nResults:');
  console.log('API 1:', result1);
  console.log('API 2:', result2);
}

// ============================================================================
// EXAMPLE 6: Custom Headers and Timeout
// ============================================================================

async function example6_customHeadersTimeout() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 6: Custom Headers and Timeout');
  console.log('='.repeat(60));

  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ apiKey: 'sk-...' }),
    mcpServers: ['https://api.example.com'],
    httpHeaders: {
      'X-Custom-Header': 'custom-value',
      'X-Request-ID': `req-${Date.now()}`,
      'X-Client-Version': '1.3.6'
    },
    timeout: 120000, // 2 minutes for slow APIs
    verbose: true
  });

  const result = await agent.run('Task with custom headers');
  console.log('\nResult:', result);
}

// ============================================================================
// EXAMPLE 7: Dynamic Auth Updates
// ============================================================================

async function example7_dynamicAuth() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 7: Dynamic Auth Updates');
  console.log('='.repeat(60));

  // Start with no auth
  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ apiKey: 'sk-...' }),
    mcpServers: ['https://api.example.com'],
    verbose: true
  });

  console.log('\n1. Running without auth...');
  await agent.run('Public task');

  // Add auth dynamically
  console.log('\n2. Adding API Key auth...');
  agent.setAuthProvider(new APIKeyAuthProvider('new-api-key'));
  await agent.run('Protected task');

  // Switch to JWT auth
  console.log('\n3. Switching to JWT auth...');
  agent.setAuthProvider(new JWTAuthProvider({
    secret: 'jwt-secret',
    algorithm: 'HS256',
    claims: { user: 'admin' }
  }));
  await agent.run('Another protected task');

  // Remove auth
  console.log('\n4. Removing auth...');
  agent.clearAuth();
  await agent.run('Back to public task');
}

// ============================================================================
// EXAMPLE 8: Error Handling and Retry
// ============================================================================

async function example8_errorHandling() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 8: Error Handling and Retry');
  console.log('='.repeat(60));

  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ apiKey: 'sk-...' }),
    mcpServers: [
      'https://flaky-api.example.com',  // Might return 401 first time
      'https://good-api.example.com'
    ],
    authProvider: new JWTAuthProvider({
      secret: 'jwt-secret',
      algorithm: 'HS256',
      claims: { user: 'test' }
    }),
    verbose: true  // Will show retry attempts
  });

  try {
    // This will automatically retry if it gets a 401/403
    const result = await agent.run('Task on flaky API');
    console.log('\nSuccess after retry:', result);
  } catch (error: any) {
    console.error('\nFailed even after retry:', error.message);
  }
}

// ============================================================================
// EXAMPLE 9: Agent Utility Methods
// ============================================================================

async function example9_utilityMethods() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 9: Agent Utility Methods');
  console.log('='.repeat(60));

  const agent = new PolyAgent({
    llmProvider: new OpenAIProvider({ apiKey: 'sk-...' }),
    mcpServers: [
      'https://api1.example.com',
      'https://api2.example.com',
      'https://api3.example.com'
    ],
    verbose: true
  });

  // Get configured servers
  console.log('\nConfigured servers:');
  console.log(agent.getServers());

  // Get tool count
  console.log('\nTotal tools available:', agent.getToolCount());

  // Get tool names
  console.log('\nAvailable tools:');
  console.log(agent.getToolNames());

  // Add a new server
  console.log('\nAdding new server...');
  await agent.addServer('https://api4.example.com');
  console.log('Updated servers:', agent.getServers());

  // Remove a server
  console.log('\nRemoving server...');
  agent.removeServer('https://api1.example.com');
  console.log('Final servers:', agent.getServers());

  // Cleanup
  agent.close();
}

// ============================================================================
// EXAMPLE 10: Complete Production Setup
// ============================================================================

async function example10_productionSetup() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 10: Complete Production Setup');
  console.log('='.repeat(60));

  // Load configuration from environment
  const config = {
    llmProvider: process.env.LLM_PROVIDER === 'anthropic'
      ? new AnthropicProvider({ apiKey: process.env.ANTHROPIC_API_KEY })
      : new OpenAIProvider({ apiKey: process.env.OPENAI_API_KEY }),
    
    mcpServers: process.env.MCP_SERVERS?.split(',') || [],
    
    registryPath: process.env.MCP_REGISTRY_PATH || './servers.json',
    
    authProvider: process.env.MCP_AUTH_TYPE === 'jwt'
      ? new JWTAuthProvider({
          secret: process.env.JWT_SECRET!,
          algorithm: 'HS256',
          claims: JSON.parse(process.env.JWT_CLAIMS || '{}')
        })
      : process.env.MCP_AUTH_TYPE === 'api_key'
      ? new APIKeyAuthProvider(process.env.API_KEY!)
      : undefined,
    
    httpHeaders: process.env.CUSTOM_HEADERS 
      ? JSON.parse(process.env.CUSTOM_HEADERS)
      : undefined,
    
    timeout: parseInt(process.env.REQUEST_TIMEOUT || '30000'),
    
    verbose: process.env.VERBOSE === 'true'
  };

  const agent = new PolyAgent(config);

  // Execute task
  const result = await agent.run('Production task');
  console.log('\nProduction result:', result);

  // Cleanup
  agent.close();
}

// ============================================================================
// RUN ALL EXAMPLES
// ============================================================================

async function runAllExamples() {
  try {
    await example1_simpleAgent();
    await example2_apiKeyAuth();
    await example3_jwtAuth();
    // await example4_oauth2Auth(); // Uncomment if you have OAuth2 setup
    // await example5_multiServerAuth(); // Uncomment for multi-server demo
    await example6_customHeadersTimeout();
    await example7_dynamicAuth();
    await example8_errorHandling();
    await example9_utilityMethods();
    // await example10_productionSetup(); // Uncomment for production demo
  } catch (error: any) {
    console.error('\nExample failed:', error.message);
    console.error(error.stack);
  }
}

// ============================================================================
// MAIN
// ============================================================================

if (require.main === module) {
  console.log('🚀 PolyAgent v2.0 - Complete Examples\n');
  runAllExamples().then(() => {
    console.log('\n✅ All examples completed!\n');
  }).catch(error => {
    console.error('\n❌ Examples failed:', error);
    process.exit(1);
  });
}

// Export for use in other files
export {
  example1_simpleAgent,
  example2_apiKeyAuth,
  example3_jwtAuth,
  example4_oauth2Auth,
  example5_multiServerAuth,
  example6_customHeadersTimeout,
  example7_dynamicAuth,
  example8_errorHandling,
  example9_utilityMethods,
  example10_productionSetup
};
