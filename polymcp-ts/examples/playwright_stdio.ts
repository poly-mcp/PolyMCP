import { UnifiedPolyAgent } from '../src/agent/unified_agent';
import { OllamaProvider } from '../src/agent/llm_providers';

async function main() {
  console.log('Playwright Client - Stdio Mode\n');
  
  const agent = new UnifiedPolyAgent({
    llmProvider: new OllamaProvider({
      model:'gpt-oss:120b-cloud',
      baseUrl: 'http://localhost:11434',
    }),
    stdioServers: [{
      command: 'npx',
      args: ['@playwright/mcp@latest'],
    }],
    memoryEnabled: true,
    verbose: true,
  });
  
  console.log('Starting Playwright via stdio...');
  await agent.start();
  console.log('Playwright ready!\n');
  
  const response = await agent.runAsync(`
    Go to github.com/llm-use/polymcp,
    take a screenshot,
    analyze the README,
    and summarize the key features
  `, 15);
  
  console.log('\nResult:', response);
}

main().catch(console.error);