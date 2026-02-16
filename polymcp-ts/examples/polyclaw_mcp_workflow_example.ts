/**
 * PolyClaw MCP Workflow Example (TypeScript)
 *
 * Goal:
 * - Run PolyClaw in Docker
 * - Execute a realistic MCP workflow request
 * - Produce a final delivery report
 *
 * Run:
 *   npx tsx examples/polyclaw_mcp_workflow_example.ts
 *
 * Recommended env:
 *   OPENAI_API_KEY=...
 * or:
 *   OLLAMA_BASE_URL=http://localhost:11434
 *   OLLAMA_MODEL=llama3.2
 *
 * Optional:
 *   POLYCLAW_QUERY="..."
 *   POLYCLAW_DOCKER_IMAGE=python:3.11-slim
 *   POLYCLAW_NO_NETWORK=1
 *   POLYCLAW_MCP_SERVERS=http://localhost:8000/mcp,http://localhost:8001/mcp
 */

import fs from 'fs';
import path from 'path';
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

function loadServersFromRegistry(): string[] {
  const explicit = (process.env.POLYCLAW_MCP_SERVERS || '').trim();
  if (explicit) {
    return explicit
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  }

  const candidates = [
    path.join(process.cwd(), 'polymcp_registry.json'),
    path.join(process.env.HOME || process.env.USERPROFILE || '', '.polymcp', 'polymcp_registry.json'),
  ];

  for (const candidate of candidates) {
    if (!candidate || !fs.existsSync(candidate)) {
      continue;
    }
    try {
      const raw = fs.readFileSync(candidate, 'utf-8');
      const parsed = JSON.parse(raw);
      const servers = parsed?.servers;
      if (servers && typeof servers === 'object' && !Array.isArray(servers)) {
        return Object.keys(servers);
      }
      if (Array.isArray(servers)) {
        return servers.filter((s) => typeof s === 'string');
      }
    } catch {
      // try next candidate
    }
  }

  return [];
}

async function main(): Promise<void> {
  const provider = makeProvider();
  const mcpServers = loadServersFromRegistry();

  const agent = new PolyClawAgent({
    llmProvider: provider,
    mcpServers,
    useDocker: true,
    dockerImage: process.env.POLYCLAW_DOCKER_IMAGE || 'python:3.11-slim',
    dockerEnableNetwork: process.env.POLYCLAW_NO_NETWORK !== '1',
    maxIterations: 8,
    commandTimeoutMs: 300_000,
    verbose: true,
    liveMode: true,
    intent: 'auto',
  });

  const query =
    process.env.POLYCLAW_QUERY ||
    [
      'Serious task: create a folder `mcp_workflow_demo` containing:',
      '1) `PLAN.md` with a 5-step plan to build an HTTP MCP server.',
      '2) `CHECKLIST.md` with technical validations (API, tool schema, invoke test, error handling).',
      '3) `RUNBOOK.md` with exact setup/run/test commands using `polymcp` CLI.',
      'Then verify created files and finish with a concise final report.',
    ].join('\n');

  console.log('\n=== POLYCLAW WORKFLOW ===');
  console.log(`MCP servers loaded: ${mcpServers.length}`);
  for (const server of mcpServers) {
    console.log(`  - ${server}`);
  }

  console.log('\n=== QUERY ===');
  console.log(query);
  console.log('\n=== EXECUTION ===');

  const result = await agent.run(query);

  console.log('\n=== FINAL RESULT ===');
  console.log(result);
}

main().catch((error) => {
  console.error('\nError:', error);
  process.exit(1);
});

