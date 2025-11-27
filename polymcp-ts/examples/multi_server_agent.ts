/**
 * Multi-Server Agent Example
 * 
 * Advanced example showing UnifiedPolyAgent communicating with multiple MCP servers.
 * Demonstrates real-world usage of connecting to different tool servers.
 * 
 * Prerequisites:
 * 1. Start the Playwright server: npm run example:playwright-server
 * 2. Start the simple server: npm run example:simple
 * 3. (Optional) Install Ollama for local LLM
 * 
 * This example shows how an agent can orchestrate tools across multiple servers
 * to accomplish complex tasks.
 */

import { UnifiedPolyAgent } from '../src/agent/unified_agent';
import { OpenAIProvider, OllamaProvider } from '../src/agent/llm_providers';

// ============================================================================
// Example 1: Web Research Automation
// ============================================================================

async function webResearchAutomation() {
  console.log('🌐 Web Research Automation Example\n');
  console.log('This example demonstrates using the agent to:');
  console.log('1. Navigate to a website using Playwright server');
  console.log('2. Extract information from the page');
  console.log('3. Process the data using local tools\n');
  
  // Configure the agent with multiple servers
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
      'http://localhost:3000', // Simple tools server
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    console.log('📊 Starting multi-step research task...\n');
    
    const result = await agent.runAsync(`
      Please help me research a website:
      1. Navigate to https://example.com using the browser
      2. Extract the main heading text
      3. Convert that heading to uppercase
      4. Tell me the final result
    `, 10);
    
    console.log('\n✅ Research completed!');
    console.log('📊 Final result:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Example 2: Data Scraping and Processing
// ============================================================================

async function dataScrapingWorkflow() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('📊 Data Scraping and Processing Workflow');
  console.log('═'.repeat(70) + '\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
      'http://localhost:3000', // Simple tools server
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    const result = await agent.runAsync(`
      I need to scrape data from a website:
      1. Navigate to https://example.com
      2. Wait for the page to load completely
      3. Extract all paragraph text from the page
      4. Count how many paragraphs there are
      5. Give me a summary
    `, 10);
    
    console.log('\n✅ Scraping completed!');
    console.log('📊 Summary:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Example 3: Form Automation
// ============================================================================

async function formAutomation() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('📝 Form Automation Example');
  console.log('═'.repeat(70) + '\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    const result = await agent.runAsync(`
      Please fill out a form on a website:
      1. Navigate to https://httpbin.org/forms/post
      2. Fill in the "custname" field with "John Doe"
      3. Fill in the "custtel" field with "555-1234"
      4. Fill in the "custemail" field with "john@example.com"
      5. Take a screenshot of the filled form
      6. Confirm the form was filled correctly
    `, 10);
    
    console.log('\n✅ Form automation completed!');
    console.log('📊 Result:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Example 4: Visual Testing
// ============================================================================

async function visualTesting() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('📸 Visual Testing Example');
  console.log('═'.repeat(70) + '\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    const result = await agent.runAsync(`
      Perform a visual test:
      1. Navigate to https://example.com
      2. Wait for the page to be fully loaded
      3. Take a full page screenshot
      4. Check if the page title contains "Example"
      5. Report if the test passed or failed
    `, 10);
    
    console.log('\n✅ Visual testing completed!');
    console.log('📊 Test result:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Example 5: Complex Multi-Server Workflow
// ============================================================================

async function complexWorkflow() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('🚀 Complex Multi-Server Workflow');
  console.log('═'.repeat(70) + '\n');
  
  console.log('This workflow combines tools from multiple servers:');
  console.log('- Playwright server (browser automation)');
  console.log('- Simple tools server (text processing, math)');
  console.log('- All orchestrated by a single AI agent\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model: 'llama2',
      baseUrl: 'http://localhost:11434',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
      'http://localhost:3000', // Simple tools server
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    const result = await agent.runAsync(`
      I need you to perform a complex task:
      
      1. Navigate to https://example.com
      2. Extract the main heading text
      3. Convert the heading to uppercase using the uppercase tool
      4. Count the number of words in the uppercase heading
      5. Calculate what 20% of that word count would be
      6. Take a screenshot of the page
      7. Give me a summary of everything you found
    `, 10);
    
    console.log('\n✅ Complex workflow completed!');
    console.log('📊 Summary:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Example 6: Using OpenAI Instead of Ollama
// ============================================================================

async function withOpenAI() {
  console.log('\n\n' + '═'.repeat(70));
  console.log('🤖 Using OpenAI GPT-4 as LLM Provider');
  console.log('═'.repeat(70) + '\n');
  
  if (!process.env.OPENAI_API_KEY) {
    console.log('⚠️  Set OPENAI_API_KEY environment variable to run this example');
    return;
  }
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OpenAIProvider({
      apiKey: process.env.OPENAI_API_KEY,
      model: 'gpt-4',
    }),
    mcpServers: [
      'http://localhost:3100', // Playwright server
      'http://localhost:3000', // Simple tools server
    ],
    verbose: true,
  });
  
  await agent.start();  // Discover tools from servers
  
  try {
    const result = await agent.runAsync(`
      Navigate to https://news.ycombinator.com and:
      1. Extract the titles of the top 5 stories
      2. For each title, count the number of words
      3. Calculate the average title length
      4. Tell me which title is the longest
    `, 10);
    
    console.log('\n✅ Analysis completed with GPT-4!');
    console.log('📊 Result:', result);
    
  } catch (error: any) {
    console.error('❌ Error:', error.message);
  }
}

// ============================================================================
// Server Health Check
// ============================================================================

async function checkServers() {
  console.log('🔍 Checking server availability...\n');
  
  const servers = [
    { name: 'Playwright Server', url: 'http://localhost:3100' },
    { name: 'Simple Tools Server', url: 'http://localhost:3000' },
    { name: 'Ollama', url: 'http://localhost:11434' },
  ];
  
  for (const server of servers) {
    try {
      const response = await fetch(`${server.url}/health`);
      if (response.ok) {
        console.log(`✅ ${server.name} is running`);
      } else {
        console.log(`⚠️  ${server.name} returned status ${response.status}`);
      }
    } catch (error) {
      console.log(`❌ ${server.name} is not reachable at ${server.url}`);
    }
  }
  
  console.log('');
}

// ============================================================================
// Main Entry Point
// ============================================================================

async function main() {
  console.log('🎭 Multi-Server Agent Examples\n');
  console.log('═'.repeat(70));
  console.log('Prerequisites:');
  console.log('1. npm run example:playwright-server (in terminal 1)');
  console.log('2. npm run example:simple (in terminal 2)');
  console.log('3. ollama serve (for local LLM)');
  console.log('═'.repeat(70) + '\n');
  
  // Check server availability
  await checkServers();
  
  const args = process.argv.slice(2);
  
  if (args.includes('--help') || args.includes('-h')) {
    console.log('Usage: npm run example:multi-server [options]\n');
    console.log('Options:');
    console.log('  --research         Run web research automation');
    console.log('  --scraping         Run data scraping workflow');
    console.log('  --form             Run form automation');
    console.log('  --visual           Run visual testing');
    console.log('  --complex          Run complex multi-server workflow');
    console.log('  --openai           Run with OpenAI GPT-4');
    console.log('  --all              Run all examples (default)\n');
    return;
  }
  
  if (args.includes('--research')) {
    await webResearchAutomation();
  } else if (args.includes('--scraping')) {
    await dataScrapingWorkflow();
  } else if (args.includes('--form')) {
    await formAutomation();
  } else if (args.includes('--visual')) {
    await visualTesting();
  } else if (args.includes('--complex')) {
    await complexWorkflow();
  } else if (args.includes('--openai')) {
    await withOpenAI();
  } else {
    // Run all examples by default
    await webResearchAutomation();
    await dataScrapingWorkflow();
    await formAutomation();
    await visualTesting();
    await complexWorkflow();
    
    if (process.env.OPENAI_API_KEY) {
      await withOpenAI();
    }
  }
  
  console.log('\n\n✅ All examples completed!\n');
}

main().catch(console.error);
