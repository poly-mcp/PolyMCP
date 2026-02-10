/**
 * skills.sh Agent Example (TypeScript)
 *
 * 1) Start a local MCP server in another terminal:
 *    npm run example:test-tool-server
 *
 * 2) Install at least one skills.sh skill:
 *    polymcp skills add vercel-labs/agent-skills
 *
 * 3) Run this example:
 *    npm run example:skills-sh
 */

import { UnifiedPolyAgent, OpenAIProvider, OllamaProvider } from '../src';

function makeProvider() {
  if (process.env.OPENAI_API_KEY) {
    return new OpenAIProvider({
      apiKey: process.env.OPENAI_API_KEY,
      model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
    });
  }
  if (process.env.OLLAMA_MODEL || process.env.OLLAMA_BASE_URL) {
    return new OllamaProvider({
      model: process.env.OLLAMA_MODEL || 'llama2',
      baseURL: process.env.OLLAMA_BASE_URL || 'http://localhost:11434',
    } as any);
  }
  throw new Error('No LLM configured. Set OPENAI_API_KEY or OLLAMA_MODEL/OLLAMA_BASE_URL.');
}

async function main() {
  const provider = makeProvider();

  const agent = new UnifiedPolyAgent({
    llmProvider: provider,
    mcpServers: ['http://localhost:3200/mcp'],
    skillsShEnabled: true,
    verbose: true,
  });

  await agent.start();

  const prompt =
    'Call the test_tool with message "skills.sh check" and summarize the result.';
  const result = await agent.run(prompt);
  console.log('\n--- FINAL ---\n');
  console.log(result);
}

main().catch(err => {
  console.error('\n❌', err.message);
  process.exit(1);
});
