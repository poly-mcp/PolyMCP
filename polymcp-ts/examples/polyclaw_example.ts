/**
 * PolyClaw Example (TypeScript)
 *
 * Run:
 *   npx tsx examples/polyclaw_example.ts
 *
 * Optional env vars:
 *   OPENAI_API_KEY
 *   OPENAI_MODEL
 *   OLLAMA_BASE_URL
 *   OLLAMA_MODEL
 *   POLYCLAW_QUERY
 *   POLYCLAW_DOCKER_IMAGE
 *   POLYCLAW_MCP_SERVERS (comma-separated list)
 */

import {
  OpenAIProvider,
  OllamaProvider,
  PolyClawAgent,
  type LLMProvider,
} from '../src';

function makeProvider(): LLMProvider {
  if (process.env.OPENAI_API_KEY) {
    return new OpenAIProvider({
      apiKey: process.env.OPENAI_API_KEY,
      model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
    });
  }

  return new OllamaProvider({
    model: process.env.OLLAMA_MODEL || 'llama3.2',
    baseUrl: process.env.OLLAMA_BASE_URL || 'http://localhost:11434',
  });
}

function parseServers(): string[] {
  const raw = (process.env.POLYCLAW_MCP_SERVERS || '').trim();
  if (!raw) {
    return [];
  }
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

async function main(): Promise<void> {
  const provider = makeProvider();

  const agent = new PolyClawAgent({
    llmProvider: provider,
    mcpServers: parseServers(),
    verbose: true,
    liveMode: true,
    useDocker: true,
    dockerImage: process.env.POLYCLAW_DOCKER_IMAGE || 'python:3.11-slim',
    dockerEnableNetwork: true,
    maxIterations: 6,
    intent: 'auto',
  });

  const query =
    process.env.POLYCLAW_QUERY ||
    'Create a folder polyclaw-demo, write a README.md with 3 steps to start a PolyMCP server, then show the file content.';

  console.log('\n=== QUERY ===');
  console.log(query);
  console.log('\n=== RESULT ===');

  const result = await agent.run(query);
  console.log(result);
}

main().catch((error) => {
  console.error('\nError:', error);
  process.exit(1);
});

