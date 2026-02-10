/**
 * MCP Apps - Complete Examples
 * 
 * Shows how PolyMCP simplifies creating MCP Apps for Claude, GPT, and other LLMs
 */

import { MCPAppBuilder, MCPAppTemplates, MCPAppRegistry } from '../src/mcp_apps/mcp_apps';

// ============================================================================
// EXAMPLE 1: Simple Counter (5 lines!)
// ============================================================================

function example1_SimpleCounter() {
  console.log('\n=== Example 1: Simple Counter (5 lines!) ===\n');

  const counterApp = MCPAppTemplates.counter()
    .addTool('increment', 'Increment counter', async () => ({ count: 1 }))
    .addTool('decrement', 'Decrement counter', async () => ({ count: -1 }))
    .addTool('reset', 'Reset counter', async () => ({ count: 0 }))
    .build();

  console.log('✅ Counter app created!');
  console.log(`   Name: ${counterApp.name}`);
  console.log(`   Tools: ${counterApp.tools?.length}`);
  console.log(`   UI Components: ${counterApp.ui.length}`);
  console.log(`   Works with: ${counterApp.metadata?.llmCompatibility?.join(', ')}`);
}

// ============================================================================
// EXAMPLE 2: Todo List (10 lines!)
// ============================================================================

function example2_TodoList() {
  console.log('\n=== Example 2: Todo List (10 lines!) ===\n');

  const todos: any[] = [];

  const todoApp = MCPAppTemplates.todoList()
    .addTool('addTask', 'Add a new task', async (params) => {
      todos.push({ text: params.task, done: false });
      return { todos, success: true };
    })
    .addTool('completeTask', 'Mark task as done', async (params) => {
      todos[params.index].done = true;
      return { todos, success: true };
    })
    .addTool('deleteTask', 'Delete a task', async (params) => {
      todos.splice(params.index, 1);
      return { todos, success: true };
    })
    .build();

  console.log('✅ Todo app created!');
  console.log(`   Tools: ${todoApp.tools?.length}`);
  console.log('   - addTask: Add new tasks');
  console.log('   - completeTask: Mark as done');
  console.log('   - deleteTask: Remove tasks');
}

// ============================================================================
// EXAMPLE 3: Weather Dashboard
// ============================================================================

function example3_WeatherDashboard() {
  console.log('\n=== Example 3: Weather Dashboard ===\n');

  const weatherApp = new MCPAppBuilder('weather', 'Weather Dashboard')
    .description('Real-time weather information')
    .icon('🌤️')
    .category('utilities')
    .tags(['weather', 'forecast', 'temperature'])
    .llmCompatibility(['claude', 'gpt', 'gemini'])
    
    // UI
    .addHeading('Weather Dashboard')
    .addInput('City name', { id: 'city-input', placeholder: 'Enter city...' })
    .addButton('Get Weather', { id: 'fetch', onClick: 'getWeather' })
    .addCard([
      { type: 'heading' as any, content: 'Current Weather' },
      { type: 'text' as any, content: 'Select a city', id: 'temp' },
      { type: 'text' as any, content: '', id: 'condition' },
    ], { id: 'weather-card' })
    
    // Tools
    .addTool('getWeather', 'Get weather for a city', async (params) => {
      // Simulate API call
      return {
        city: params.city,
        temperature: 72,
        condition: 'Sunny',
        humidity: 65,
        wind: 10
      };
    })
    .build();

  console.log('✅ Weather dashboard created!');
  console.log(`   Icon: ${weatherApp.icon}`);
  console.log(`   Category: ${weatherApp.metadata?.category}`);
  console.log(`   Tags: ${weatherApp.metadata?.tags?.join(', ')}`);
}

// ============================================================================
// EXAMPLE 4: Data Analytics Dashboard
// ============================================================================

function example4_AnalyticsDashboard() {
  console.log('\n=== Example 4: Analytics Dashboard ===\n');

  const analyticsApp = new MCPAppBuilder('analytics', 'Analytics Dashboard')
    .description('Business analytics and insights')
    .icon('📊')
    .category('business')
    
    .addHeading('Business Analytics')
    
    // Metrics cards
    .addCard([
      { type: 'heading' as any, content: 'Revenue' },
      { type: 'text' as any, content: '$125,430', id: 'revenue' },
      { type: 'progress' as any, content: { value: 75, max: 100 } },
    ], { id: 'revenue-card' })
    
    .addCard([
      { type: 'heading' as any, content: 'Users' },
      { type: 'text' as any, content: '12,345', id: 'users' },
      { type: 'progress' as any, content: { value: 60, max: 100 } },
    ], { id: 'users-card' })
    
    // Chart
    .addChart({
      type: 'line',
      data: [10, 20, 30, 40, 50],
      labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May']
    }, { id: 'revenue-chart' })
    
    // Tools
    .addTool('getStats', 'Get current statistics', async () => {
      return {
        revenue: 125430,
        users: 12345,
        growth: 23.5
      };
    })
    .addTool('getChartData', 'Get chart data', async (params) => {
      const range = params?.range ?? 'default';
      return {
        range,
        data: [10, 20, 30, 40, 50],
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May']
      };
    })
    .build();

  console.log('✅ Analytics dashboard created!');
  console.log(`   App: ${analyticsApp.name} v${analyticsApp.version}`);
  console.log(`   Tools: ${analyticsApp.tools?.length ?? 0}`);
  console.log(`   Has charts: yes`);
  console.log(`   Has metrics: yes`);
  console.log(`   Has real-time data: yes`);
}

// ============================================================================
// EXAMPLE 5: Multi-App Registry
// ============================================================================

function example5_AppRegistry() {
  console.log('\n=== Example 5: Multi-App Registry ===\n');

  const registry = new MCPAppRegistry();

  // Register multiple apps
  registry.register(MCPAppTemplates.counter().build());
  registry.register(MCPAppTemplates.todoList().build());
  registry.register(MCPAppTemplates.dashboard('My Dashboard').build());

  console.log('✅ Registered 3 apps!');
  
  const stats = registry.getStatistics();
  console.log(`\n📊 Registry Statistics:`);
  console.log(`   Total apps: ${stats.totalApps}`);
  console.log(`   By LLM:`);
  for (const [llm, count] of Object.entries(stats.byLLM)) {
    console.log(`      ${llm}: ${count} apps`);
  }

  // Search apps
  const results = registry.search('counter');
  console.log(`\n🔍 Search results for "counter": ${results.length} apps`);
  
  // Get apps for specific LLM
  const claudeApps = registry.getAppsForLLM('claude');
  console.log(`\n🤖 Apps compatible with Claude: ${claudeApps.length}`);
  
  // Export as tools
  const tools = registry.exportAsTools();
  console.log(`\n🔧 Exported ${tools.length} tools for LLM consumption`);
}

// ============================================================================
// EXAMPLE 6: Custom Form Builder
// ============================================================================

function example6_CustomForm() {
  console.log('\n=== Example 6: Custom Form Builder ===\n');

  const contactForm = MCPAppTemplates.form('Contact Us', [
    { label: 'Name', type: 'text' },
    { label: 'Email', type: 'text' },
    { label: 'Message', type: 'text' },
    { label: 'Subscribe to newsletter', type: 'checkbox' }
  ])
    .addTool('submitForm', 'Submit contact form', async (params) => {
      console.log('Form submitted:', params);
      return { success: true, message: 'Thank you for contacting us!' };
    })
    .build();

  console.log('✅ Contact form created!');
  console.log(`   Fields: ${contactForm.ui.length - 2}`); // -2 for heading and button
}

// ============================================================================
// EXAMPLE 7: Works with Claude
// ============================================================================

function example7_ClaudeIntegration() {
  console.log('\n=== Example 7: Claude Integration ===\n');

  const app = new MCPAppBuilder('my-app', 'My First App')
    .description('A simple app for Claude')
    .icon('🚀')
    .llmCompatibility(['claude'])
    
    .addHeading('Welcome to My App!')
    .addText('This app works with Claude Desktop and Claude API')
    .addButton('Click Me', { onClick: 'handleClick' })
    
    .addTool('handleClick', 'Handle button click', async () => {
      return { message: 'Button clicked!' };
    })
    .build();

  console.log('✅ Claude-compatible app created!');
  console.log(`   App ID: ${app.id}`);
  console.log('\n📖 To use with Claude Desktop:');
  console.log('   1. Add to claude_desktop_config.json:');
  console.log('      {');
  console.log('        "mcpServers": {');
  console.log('          "my-app": { "url": "http://localhost:3000" }');
  console.log('        }');
  console.log('      }');
  console.log('   2. Restart Claude Desktop');
  console.log('   3. Ask Claude: "Show me my app"');
}

// ============================================================================
// EXAMPLE 8: Works with GPT
// ============================================================================

function example8_GPTIntegration() {
  console.log('\n=== Example 8: GPT Integration ===\n');

  const app = new MCPAppBuilder('gpt-app', 'GPT App')
    .description('App for GPT with function calling')
    .icon('🤖')
    .llmCompatibility(['gpt'])
    
    .addHeading('GPT Function Calling Example')
    .addButton('Execute Action', { onClick: 'executeAction' })
    
    .addTool('executeAction', 'Execute an action', async (params) => {
      return {
        result: 'Action executed!',
        input: params ?? {},
        timestamp: Date.now()
      };
    })
    .build();

  // Export for GPT function calling
  const builder = new MCPAppBuilder(app.id, app.name);
  builder['app'] = app;
  const toolMetadata = builder.exportAsToolMetadata();

  console.log('✅ GPT-compatible app created!');
  console.log('\n📖 To use with GPT:');
  console.log('   Use the tool metadata in GPT function calling:');
  console.log('   ' + JSON.stringify(toolMetadata, null, 2).split('\n')[0]);
}

// ============================================================================
// RUN ALL EXAMPLES
// ============================================================================

function runAllExamples() {
  console.log('🚀 PolyMCP - MCP Apps Examples');
  console.log('Simplifying MCP Apps for Claude, GPT, and other LLMs!\n');

  example1_SimpleCounter();
  example2_TodoList();
  example3_WeatherDashboard();
  example4_AnalyticsDashboard();
  example5_AppRegistry();
  example6_CustomForm();
  example7_ClaudeIntegration();
  example8_GPTIntegration();

  console.log('\n' + '='.repeat(60));
  console.log('✅ All examples completed!');
  console.log('\n💡 Key Takeaways:');
  console.log('   - MCP Apps are EASY to create with PolyMCP');
  console.log('   - Works with Claude, GPT, Gemini, and other LLMs');
  console.log('   - Simple fluent API');
  console.log('   - Built-in templates');
  console.log('   - Type-safe and production-ready');
  console.log('\n🎯 Next Steps:');
  console.log('   1. Create your own MCP App');
  console.log('   2. Deploy to your MCP server');
  console.log('   3. Use with your favorite LLM!');
  console.log('='.repeat(60) + '\n');
}

// Run if executed directly
if (require.main === module) {
  runAllExamples();
}

export {
  example1_SimpleCounter,
  example2_TodoList,
  example3_WeatherDashboard,
  example4_AnalyticsDashboard,
  example5_AppRegistry,
  example6_CustomForm,
  example7_ClaudeIntegration,
  example8_GPTIntegration
};
