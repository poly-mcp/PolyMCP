/**
 * MCP Apps - Complete Example
 * 
 * This example shows how PolyMCP simplifies creating MCP Apps
 * for Claude, GPT, and other LLMs.
 * 
 * MCP Apps = Tools + UI
 * - Create interactive tools with visual interfaces
 * - Simple API for building apps
 * - Built-in templates for common patterns
 * - Easy deployment
 */

import { 
  MCPAppsBuilder, 
  MCPAppTemplates,
  createSimpleApp 
} from '../src/mcp_apps/mcp_apps_builder';
import { 
  MCPAppsServer,
  MCPAppsServerFactory 
} from '../src/mcp_apps/mcp_apps_server';

// ============================================================================
// EXAMPLE 1: Using Built-in Templates
// ============================================================================

async function example1_builtInTemplates() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 1: Using Built-in Templates');
  console.log('='.repeat(60));

  const builder = new MCPAppsBuilder();

  // Create calculator app from template
  const calculatorApp = builder.createFromTemplate(
    MCPAppTemplates.calculator()
  ).build();

  // Create todo list app from template
  const todoApp = builder.createFromTemplate(
    MCPAppTemplates.todoList()
  ).build();

  // Create dashboard app from template
  const dashboardApp = builder.createFromTemplate(
    MCPAppTemplates.dashboard()
  ).build();

  // Start server with all apps
  const server = MCPAppsServerFactory.createWithApps([
    calculatorApp,
    todoApp,
    dashboardApp
  ]);

  await server.start();

  console.log('\n✅ Server started with 3 apps:');
  console.log('- Calculator: Interactive calculator with UI');
  console.log('- Todo List: Todo manager with UI');
  console.log('- Dashboard: Data dashboard with charts');
  
  console.log('\n📋 Available endpoints:');
  console.log('GET  /list_tools - List all tools');
  console.log('GET  /list_resources - List all UI resources');
  console.log('POST /tools/{name} - Execute a tool');
  console.log('GET  /resources/{uri} - Get UI resource');
}

// ============================================================================
// EXAMPLE 2: Building Custom App from Scratch
// ============================================================================

async function example2_customApp() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 2: Building Custom App from Scratch');
  console.log('='.repeat(60));

  const builder = new MCPAppsBuilder();

  // Create a weather app
  const weatherApp = builder.createApp({
    id: 'weather',
    name: 'Weather App',
    description: 'Get weather information with interactive UI'
  });

  // Add tool for getting weather
  weatherApp.addTool({
    name: 'get_weather',
    description: 'Get weather for a city',
    inputSchema: {
      type: 'object',
      properties: {
        city: {
          type: 'string',
          description: 'City name'
        }
      },
      required: ['city']
    },
    handler: async (params: any) => {
      // In real app, call weather API
      return {
        city: params.city,
        temperature: 72,
        condition: 'Sunny',
        humidity: 65,
        wind: 10
      };
    }
  });

  // Add HTML UI
  weatherApp.addHTMLResource({
    name: 'Weather Interface',
    html: `
<!DOCTYPE html>
<html>
<head>
  <title>Weather</title>
  <style>
    body { font-family: Arial; padding: 20px; max-width: 500px; margin: 0 auto; }
    .search { display: flex; margin-bottom: 20px; }
    input { flex: 1; padding: 10px; font-size: 16px; }
    button { padding: 10px 20px; font-size: 16px; cursor: pointer; }
    .weather-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                     color: white; padding: 30px; border-radius: 10px; }
    .temp { font-size: 48px; font-weight: bold; }
    .city { font-size: 24px; margin-bottom: 10px; }
    .details { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px; }
  </style>
</head>
<body>
  <h2>🌤️ Weather App</h2>
  <div class="search">
    <input type="text" id="city" placeholder="Enter city name">
    <button onclick="getWeather()">Search</button>
  </div>
  <div id="result"></div>
  <script>
    async function getWeather() {
      const city = document.getElementById('city').value;
      if (!city) return;
      
      const result = await window.mcpCall('get_weather', { city });
      
      document.getElementById('result').innerHTML = 
        '<div class="weather-card">' +
        '<div class="city">' + result.city + '</div>' +
        '<div class="temp">' + result.temperature + '°F</div>' +
        '<div>' + result.condition + '</div>' +
        '<div class="details">' +
        '<div>💧 Humidity: ' + result.humidity + '%</div>' +
        '<div>💨 Wind: ' + result.wind + ' mph</div>' +
        '</div>' +
        '</div>';
    }
  </script>
</body>
</html>
    `,
    tools: ['get_weather']
  });

  // Build the app
  const app = weatherApp.build();

  // Validate
  const validation = builder.validate(app);
  if (!validation.valid) {
    console.log('❌ Validation errors:', validation.errors);
    return;
  }

  console.log('✅ Weather app created successfully!');
  console.log(`   - Tools: ${app.tools.length}`);
  console.log(`   - Resources: ${app.resources.length}`);

  // Start server
  const server = new MCPAppsServer({ port: 3001 });
  server.registerApp(app);
  await server.start();
}

// ============================================================================
// EXAMPLE 3: Quick Simple App Creation
// ============================================================================

async function example3_quickApp() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 3: Quick Simple App Creation');
  console.log('='.repeat(60));

  // Create a simple note-taking app in just a few lines
  const notes: string[] = [];

  const notesApp = createSimpleApp(
    'notes',
    'Note Taker',
    'Simple note-taking app',
    async (action: string, params: any) => {
      if (action === 'add') {
        notes.push(params.text);
        return { success: true, total: notes.length };
      } else if (action === 'list') {
        return { notes };
      }
      return { error: 'Unknown action' };
    },
    `
<!DOCTYPE html>
<html>
<head><title>Notes</title><style>
  body { font-family: Arial; padding: 20px; max-width: 600px; margin: 0 auto; }
  textarea { width: 100%; height: 100px; padding: 10px; margin-bottom: 10px; }
  button { padding: 10px 20px; cursor: pointer; }
  .note { background: #fffacd; padding: 10px; margin: 5px 0; border-radius: 5px; }
</style></head>
<body>
  <h2>📓 Notes</h2>
  <textarea id="noteText" placeholder="Write your note..."></textarea>
  <button onclick="addNote()">Add Note</button>
  <div id="notesList"></div>
  <script>
    async function addNote() {
      const text = document.getElementById('noteText').value;
      if (!text) return;
      
      await window.mcpCall('execute', { action: 'add', params: { text } });
      document.getElementById('noteText').value = '';
      await loadNotes();
    }
    
    async function loadNotes() {
      const result = await window.mcpCall('execute', { action: 'list', params: {} });
      document.getElementById('notesList').innerHTML = 
        result.notes.map(note => '<div class="note">' + note + '</div>').join('');
    }
    
    loadNotes();
  </script>
</body>
</html>
    `
  );

  console.log('✅ Note-taking app created with just one function call!');

  // Start server
  const server = new MCPAppsServer({ port: 3002 });
  server.registerApp(notesApp);
  await server.start();
}

// ============================================================================
// EXAMPLE 4: Multi-App Server
// ============================================================================

async function example4_multiAppServer() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 4: Multi-App Server');
  console.log('='.repeat(60));

  const builder = new MCPAppsBuilder();

  // Create multiple apps
  const apps = [
    builder.createFromTemplate(MCPAppTemplates.calculator()).build(),
    builder.createFromTemplate(MCPAppTemplates.todoList()).build(),
    builder.createFromTemplate(MCPAppTemplates.dashboard()).build(),
  ];

  // Create server with all apps
  const server = MCPAppsServerFactory.createDevelopment(apps);
  
  await server.start();

  // Show server info
  const info = server.getInfo();
  console.log('\n📊 Server Info:');
  console.log(`   Apps: ${info.appCount}`);
  console.log(`   Tools: ${info.toolCount}`);
  console.log(`   Resources: ${info.resourceCount}`);

  // List all tools
  console.log('\n🔧 Available Tools:');
  const tools = server.listTools();
  for (const tool of tools) {
    console.log(`   - ${tool.name} (${tool.appName}): ${tool.description}`);
  }

  // List all resources
  console.log('\n🎨 Available Resources:');
  const resources = server.listResources();
  for (const resource of resources) {
    console.log(`   - ${resource.uri} (${resource.appName}): ${resource.name}`);
  }
}

// ============================================================================
// EXAMPLE 5: Using MCP Apps with Claude/GPT
// ============================================================================

async function example5_withLLM() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 5: Using MCP Apps with Claude/GPT');
  console.log('='.repeat(60));

  const builder = new MCPAppsBuilder();

  // Create calculator app
  const calcApp = builder.createFromTemplate(
    MCPAppTemplates.calculator()
  ).build();

  // Start server
  const server = new MCPAppsServer({ port: 3000 });
  server.registerApp(calcApp);
  await server.start();

  console.log('\n✅ Server running on http://localhost:3000');
  console.log('\n📖 How to use with Claude/GPT:');
  console.log('\n1. Claude Desktop / API:');
  console.log('   Configure MCP server in claude_desktop_config.json:');
  console.log('   {');
  console.log('     "mcpServers": {');
  console.log('       "calculator": {');
  console.log('         "url": "http://localhost:3000"');
  console.log('       }');
  console.log('     }');
  console.log('   }');
  
  console.log('\n2. GPT with Function Calling:');
  console.log('   - Expose tools via /list_tools endpoint');
  console.log('   - GPT calls tools via /tools/{name} endpoint');
  console.log('   - Show UI resources to users');

  console.log('\n3. Try it:');
  console.log('   - Ask Claude: "Can you calculate 15 * 23?"');
  console.log('   - Claude will use the calculate tool');
  console.log('   - Users can also use the interactive UI');
}

// ============================================================================
// EXAMPLE 6: Testing MCP Apps
// ============================================================================

async function example6_testing() {
  console.log('\n' + '='.repeat(60));
  console.log('EXAMPLE 6: Testing MCP Apps');
  console.log('='.repeat(60));

  const builder = new MCPAppsBuilder();
  const calcApp = builder.createFromTemplate(MCPAppTemplates.calculator()).build();

  const server = new MCPAppsServer();
  server.registerApp(calcApp);

  // Test 1: List tools
  console.log('\n🧪 Test 1: List Tools');
  const toolsResponse = server.getMCPToolsResponse();
  console.log(`   ✓ Found ${toolsResponse.tools.length} tool(s)`);
  console.log(`   - ${toolsResponse.tools[0].name}`);

  // Test 2: Execute tool
  console.log('\n🧪 Test 2: Execute Tool');
  try {
    const result = await server.executeTool('calculate', { expression: '10 + 5' });
    console.log(`   ✓ Result: ${result.result}`);
  } catch (error: any) {
    console.log(`   ✗ Error: ${error.message}`);
  }

  // Test 3: Get resource
  console.log('\n🧪 Test 3: Get UI Resource');
  const resources = server.listResources();
  if (resources.length > 0) {
    const resource = server.getResource(resources[0].uri);
    console.log(`   ✓ Resource found: ${resource?.name}`);
    console.log(`   ✓ MIME type: ${resource?.mimeType}`);
    console.log(`   ✓ Content length: ${resource?.content.length} chars`);
  }

  // Test 4: Handle HTTP requests
  console.log('\n🧪 Test 4: HTTP Request Handling');
  
  const listToolsReq = await server.handleRequest('GET', '/list_tools');
  console.log(`   ✓ GET /list_tools: ${listToolsReq.status}`);
  
  const listResourcesReq = await server.handleRequest('GET', '/list_resources');
  console.log(`   ✓ GET /list_resources: ${listResourcesReq.status}`);
  
  const executeToolReq = await server.handleRequest('POST', '/tools/calculate', { expression: '2 * 3' });
  console.log(`   ✓ POST /tools/calculate: ${executeToolReq.status}`);
  console.log(`   ✓ Result: ${JSON.stringify(executeToolReq.body)}`);
}

// ============================================================================
// RUN ALL EXAMPLES
// ============================================================================

async function runAllExamples() {
  try {
    await example1_builtInTemplates();
    await example2_customApp();
    await example3_quickApp();
    await example4_multiAppServer();
    await example5_withLLM();
    await example6_testing();
  } catch (error: any) {
    console.error('\n❌ Example failed:', error.message);
    console.error(error.stack);
  }
}

// ============================================================================
// MAIN
// ============================================================================

if (require.main === module) {
  console.log('🚀 MCP Apps - Complete Examples\n');
  console.log('PolyMCP simplifies creating MCP Apps for Claude, GPT, and other LLMs!\n');
  
  runAllExamples().then(() => {
    console.log('\n✅ All examples completed!');
    console.log('\n📚 Next steps:');
    console.log('   1. Customize the templates for your use case');
    console.log('   2. Build your own custom apps');
    console.log('   3. Deploy and share with Claude/GPT users');
    console.log('   4. Check the documentation for more info\n');
  }).catch(error => {
    console.error('\n❌ Examples failed:', error);
    process.exit(1);
  });
}

// Export for use in other files
export {
  example1_builtInTemplates,
  example2_customApp,
  example3_quickApp,
  example4_multiAppServer,
  example5_withLLM,
  example6_testing
};
