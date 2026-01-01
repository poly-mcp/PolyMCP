/**
 * Skills System Complete Example
 * 
 * This example demonstrates the complete Skills workflow:
 * 1. Generating skills from MCP servers
 * 2. Loading skills with caching
 * 3. Matching skills to tasks
 * 4. Using skills with agents
 * 
 * Prerequisites:
 * - One or more MCP servers running
 * - Or use the mock server mode
 * 
 * Usage:
 *   # Generate skills from real servers
 *   tsx examples/skills_workflow_example.ts generate http://localhost:8000/mcp
 * 
 *   # Or use mock mode (no servers needed)
 *   tsx examples/skills_workflow_example.ts mock
 * 
 *   # Load and match skills
 *   tsx examples/skills_workflow_example.ts match "Read file and send email"
 * 
 *   # Full workflow
 *   tsx examples/skills_workflow_example.ts workflow
 */

import {
  MCPSkillGenerator,
  MCPSkillLoader,
  MCPSkillMatcher,
  exposeToolsHttp,
  tool
} from '../src/index';
import { z } from 'zod';
import * as fs from 'fs-extra';
import * as path from 'path';

// ============================================================================
// STEP 1: Setup Mock MCP Server (for demo purposes)
// ============================================================================

function createMockServer() {
  const fileTools = [
    tool({
      name: 'read_file',
      description: 'Read content from a file',
      parameters: z.object({
        path: z.string().describe('File path')
      }),
      execute: async ({ path }) => `Content of ${path}`
    }),
    tool({
      name: 'write_file',
      description: 'Write content to a file',
      parameters: z.object({
        path: z.string(),
        content: z.string()
      }),
      execute: async () => 'File written successfully'
    }),
    tool({
      name: 'list_directory',
      description: 'List contents of a directory',
      parameters: z.object({
        path: z.string()
      }),
      execute: async () => JSON.stringify(['file1.txt', 'file2.txt'])
    })
  ];

  const apiTools = [
    tool({
      name: 'http_get',
      description: 'Make HTTP GET request',
      parameters: z.object({
        url: z.string()
      }),
      execute: async ({ url }) => `Response from ${url}`
    }),
    tool({
      name: 'http_post',
      description: 'Make HTTP POST request',
      parameters: z.object({
        url: z.string(),
        body: z.string()
      }),
      execute: async () => 'POST successful'
    })
  ];

  const emailTools = [
    tool({
      name: 'send_email',
      description: 'Send an email',
      parameters: z.object({
        to: z.string(),
        subject: z.string(),
        body: z.string()
      }),
      execute: async ({ to }) => `Email sent to ${to}`
    })
  ];

  // Start three mock servers
  const servers = [
    { tools: fileTools, port: 8001, name: 'File Server' },
    { tools: apiTools, port: 8002, name: 'API Server' },
    { tools: emailTools, port: 8003, name: 'Email Server' }
  ];

  const apps = servers.map(({ tools, port, name }) => {
    const app = exposeToolsHttp(tools, {
      title: name,
      verbose: false
    });
    
    return app.listen(port, () => {
      console.log(`✅ ${name} running on http://localhost:${port}`);
    });
  });

  return {
    servers: ['http://localhost:8001/mcp', 'http://localhost:8002/mcp', 'http://localhost:8003/mcp'],
    cleanup: () => {
      apps.forEach(app => app.close());
      console.log('🛑 Mock servers stopped');
    }
  };
}

// ============================================================================
// STEP 2: Generate Skills from MCP Servers
// ============================================================================

async function generateSkills(serverUrls: string[]) {
  console.log('\n📚 STEP 1: Generating Skills from MCP Servers\n');
  console.log('='.repeat(70) + '\n');
  
  const generator = new MCPSkillGenerator({
    outputDir: './examples/mcp_skills',
    verbose: true,
    includeExamples: true
  });

  console.log(`🔍 Discovering tools from ${serverUrls.length} servers...\n`);

  try {
    const stats = await generator.generateFromServers(serverUrls, 10000);
    
    console.log('\n📊 Generation Statistics:');
    console.log(`  Total Tools: ${stats.totalTools}`);
    console.log(`  Total Servers: ${stats.totalServers}`);
    console.log(`  Categories: ${Object.keys(stats.categories).length}`);
    console.log(`  Generation Time: ${(stats.generationTime / 1000).toFixed(2)}s`);
    
    if (stats.errors.length > 0) {
      console.log(`\n⚠️  Errors encountered: ${stats.errors.length}`);
      stats.errors.forEach(err => console.log(`  - ${err}`));
    }
    
    console.log(`\n✅ Skills generated in: ./examples/mcp_skills/`);
    console.log('\nGenerated files:');
    console.log('  - _index.md (overview)');
    console.log('  - _metadata.json (statistics)');
    Object.keys(stats.categories).forEach(cat => {
      console.log(`  - ${cat}.md (${stats.categories[cat]} tools)`);
    });
    
    return stats;
    
  } catch (error: any) {
    console.error('❌ Generation failed:', error.message);
    throw error;
  }
}

// ============================================================================
// STEP 3: Load Skills
// ============================================================================

async function loadSkills(categories?: string[]) {
  console.log('\n📖 STEP 2: Loading Skills\n');
  console.log('='.repeat(70) + '\n');

  const loader = new MCPSkillLoader({
    skillsDir: './examples/mcp_skills',
    maxTokens: 50000,
    verbose: true,
    autoRefresh: true
  });

  // Get available categories
  const available = await loader.getAvailableCategories();
  console.log(`📦 Available categories: ${available.join(', ')}\n`);

  // Load skills
  const categoriesToLoad = categories || available;
  console.log(`🔄 Loading categories: ${categoriesToLoad.join(', ')}...\n`);

  const skills = await loader.loadSkills(categoriesToLoad);
  
  console.log(`✅ Loaded ${skills.length} skills:\n`);
  
  for (const skill of skills) {
    console.log(`  • ${skill.category}`);
    console.log(`    Tools: ${skill.tools.length} (${skill.tokens} tokens)`);
    console.log(`    Sample tools: ${skill.tools.slice(0, 3).join(', ')}`);
  }

  // Get metadata
  const metadata = await loader.getMetadata();
  if (metadata) {
    console.log(`\n📊 Metadata:`);
    console.log(`  Generated: ${new Date(metadata.generated_at).toLocaleString()}`);
    console.log(`  Total tools: ${metadata.stats.total_tools}`);
    console.log(`  Total servers: ${metadata.stats.total_servers}`);
  }

  // Get stats
  const stats = await loader.getStats();
  console.log(`\n🔍 Loader stats:`);
  console.log(`  Cache size: ${stats.cacheSize} skills`);
  console.log(`  Cache age: ${(stats.cacheAge / 1000).toFixed(0)}s`);
  console.log(`  Total tokens: ${stats.totalTokens}`);

  return { loader, skills };
}

// ============================================================================
// STEP 4: Match Skills to Tasks
// ============================================================================

async function matchSkillsToTask(taskDescription: string, loader: MCPSkillLoader) {
  console.log('\n🎯 STEP 3: Matching Skills to Task\n');
  console.log('='.repeat(70) + '\n');

  console.log(`📝 Task: "${taskDescription}"\n`);

  const matcher = new MCPSkillMatcher(loader, true);

  // Analyze task
  console.log('🔍 Analyzing task complexity...\n');
  const analysis = await matcher.analyzeTask(taskDescription);
  
  console.log(`📊 Analysis Results:`);
  console.log(`  Complexity: ${analysis.complexity}`);
  console.log(`  Suggested categories: ${analysis.suggestedCategories.slice(0, 5).join(', ')}`);
  console.log(`  Estimated tokens: ${analysis.estimatedTokens}`);
  console.log(`  Reasoning: ${analysis.reasoning}\n`);

  // Match skills
  console.log('🎯 Finding best matching skills...\n');
  const matches = await matcher.matchTask(taskDescription, {
    maxResults: 5,
    minRelevance: 0.1,
    tokenBudget: 30000,
    verbose: true
  });

  if (matches.length === 0) {
    console.log('❌ No matching skills found\n');
    return { matches: [], analysis };
  }

  console.log(`\n✅ Found ${matches.length} matching skills:\n`);
  
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i];
    const rank = i + 1;
    
    console.log(`${rank}. ${match.skill.category.toUpperCase()}`);
    console.log(`   Relevance: ${(match.relevance * 100).toFixed(0)}%`);
    console.log(`   Keywords: ${match.matchedKeywords.join(', ')}`);
    console.log(`   Reasoning: ${match.reasoning}`);
    console.log(`   Tools: ${match.skill.tools.length} available`);
    console.log(`   Tokens: ${match.skill.tokens}`);
    console.log();
  }

  return { matches, analysis };
}

// ============================================================================
// STEP 5: Complete Workflow
// ============================================================================

async function runCompleteWorkflow() {
  console.log('\n🚀 COMPLETE SKILLS WORKFLOW\n');
  console.log('='.repeat(70) + '\n');

  let mockServers: any = null;

  try {
    // Step 1: Start mock servers
    console.log('🎬 Starting mock MCP servers...\n');
    mockServers = createMockServer();
    
    // Wait for servers to be ready
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log();

    // Step 2: Generate skills
    await generateSkills(mockServers.servers);

    // Wait a bit
    await new Promise(resolve => setTimeout(resolve, 500));

    // Step 3: Load skills
    const { loader } = await loadSkills();

    // Wait a bit
    await new Promise(resolve => setTimeout(resolve, 500));

    // Step 4: Test multiple tasks
    const testTasks = [
      'Read the configuration file and send an email with the contents',
      'Make an HTTP request to fetch data and write it to a file',
      'List all files in a directory and send them via API',
      'Calculate statistics and email the report'
    ];

    for (const task of testTasks) {
      await matchSkillsToTask(task, loader);
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    // Step 5: Show how to use matched skills
    console.log('\n💡 STEP 4: Using Matched Skills\n');
    console.log('='.repeat(70) + '\n');
    
    const { matches } = await matchSkillsToTask(
      'Read file and send email',
      loader
    );

    if (matches.length > 0) {
      console.log('\n📝 Example: How to use these skills with an agent:\n');
      console.log('```typescript');
      console.log('import { UnifiedAgent, OpenAIProvider } from "polymcp";');
      console.log('import { MCPSkillLoader } from "polymcp";');
      console.log('');
      console.log('const loader = new MCPSkillLoader({ skillsDir: "./mcp_skills" });');
      console.log('const skills = await loader.loadSkills([');
      matches.forEach(m => {
        console.log(`  "${m.skill.category}",`);
      });
      console.log(']);');
      console.log('');
      console.log('const agent = new UnifiedAgent({');
      console.log('  llmProvider: new OpenAIProvider({ apiKey: "sk-..." }),');
      console.log('  mcpServers: mockServers.servers');
      console.log('});');
      console.log('');
      console.log('// Add skills to context');
      console.log('const context = loader.formatForContext(skills);');
      console.log('const response = await agent.run(`${context}\\n\\nTask: Read file and send email`);');
      console.log('```\n');
    }

    console.log('\n✅ Complete workflow finished!\n');

  } finally {
    // Cleanup
    if (mockServers) {
      mockServers.cleanup();
    }
  }
}

// ============================================================================
// STEP 6: Additional Examples
// ============================================================================

async function demonstrateAdvancedFeatures() {
  console.log('\n⚡ ADVANCED FEATURES\n');
  console.log('='.repeat(70) + '\n');

  const loader = new MCPSkillLoader({
    skillsDir: './examples/mcp_skills',
    maxTokens: 100000,
    cacheTimeout: 300000,
    autoRefresh: true,
    verbose: true
  });

  // Feature 1: Optimized loading
  console.log('1️⃣ Optimized skill loading (within token budget):\n');
  const optimized = await loader.loadOptimized(['filesystem', 'api', 'communication']);
  console.log(`   Loaded ${optimized.length} skills optimally`);
  console.log(`   Total tokens: ${optimized.reduce((sum, s) => sum + s.tokens, 0)}\n`);

  // Feature 2: Cache management
  console.log('2️⃣ Cache management:\n');
  const stats1 = await loader.getStats();
  console.log(`   Cache size before: ${stats1.cacheSize}`);
  
  loader.clearCache();
  
  const stats2 = await loader.getStats();
  console.log(`   Cache size after clear: ${stats2.cacheSize}`);
  
  await loader.loadAll();
  const stats3 = await loader.getStats();
  console.log(`   Cache size after reload: ${stats3.cacheSize}\n`);

  // Feature 3: Skill formatting
  console.log('3️⃣ Formatting skills for agent context:\n');
  const skills = await loader.loadSkills(['filesystem']);
  const formatted = loader.formatForContext(skills);
  console.log(`   Context length: ${formatted.length} characters`);
  console.log(`   First 200 chars: ${formatted.substring(0, 200)}...\n`);

  // Feature 4: Token estimation
  console.log('4️⃣ Token estimation:\n');
  const categories = await loader.getAvailableCategories();
  for (const category of categories.slice(0, 3)) {
    const tokens = await loader.getTotalTokens([category]);
    console.log(`   ${category}: ~${tokens} tokens`);
  }
  console.log();

  // Feature 5: Matcher features
  console.log('5️⃣ Advanced matching:\n');
  const matcher = new MCPSkillMatcher(loader);
  
  const suggested = await matcher.suggestCategories(
    'I need to process data from a file and store it in a database'
  );
  console.log(`   Suggested categories: ${suggested.join(', ')}\n`);
}

// ============================================================================
// Main Entry Point
// ============================================================================

async function main() {
  const command = process.argv[2];
  const args = process.argv.slice(3);

  try {
    switch (command) {
      case 'generate':
        if (args.length === 0) {
          console.error('❌ Usage: tsx examples/skills_workflow_example.ts generate <server-url1> [server-url2] ...');
          process.exit(1);
        }
        await generateSkills(args);
        break;

      case 'load':
        await loadSkills(args.length > 0 ? args : undefined);
        break;

      case 'match':
        if (args.length === 0) {
          console.error('❌ Usage: tsx examples/skills_workflow_example.ts match "<task description>"');
          process.exit(1);
        }
        const { loader } = await loadSkills();
        await matchSkillsToTask(args.join(' '), loader);
        break;

      case 'workflow':
        await runCompleteWorkflow();
        break;

      case 'mock':
        const mockServers = createMockServer();
        await new Promise(resolve => setTimeout(resolve, 1000));
        await generateSkills(mockServers.servers);
        mockServers.cleanup();
        break;

      case 'advanced':
        await demonstrateAdvancedFeatures();
        break;

      default:
        console.log(`
📚 Skills System Complete Example

Usage:
  tsx examples/skills_workflow_example.ts <command> [args]

Commands:
  generate <urls...>    Generate skills from MCP servers
  load [categories...]  Load skills (optionally specific categories)
  match "<task>"        Match skills to a task description
  workflow              Run complete workflow with mock servers
  mock                  Generate skills using mock servers
  advanced              Demonstrate advanced features

Examples:
  # Generate from real servers
  tsx examples/skills_workflow_example.ts generate http://localhost:8000/mcp http://localhost:8001/mcp

  # Use mock servers (no real servers needed)
  tsx examples/skills_workflow_example.ts mock

  # Complete workflow
  tsx examples/skills_workflow_example.ts workflow

  # Load specific categories
  tsx examples/skills_workflow_example.ts load filesystem api

  # Match skills to task
  tsx examples/skills_workflow_example.ts match "Read file and send email"

  # Advanced features
  tsx examples/skills_workflow_example.ts advanced

Generated skills will be in: ./examples/mcp_skills/
`);
    }
  } catch (error: any) {
    console.error('\n❌ Error:', error.message);
    if (error.stack) {
      console.error('\nStack trace:');
      console.error(error.stack);
    }
    process.exit(1);
  }
}

main();
