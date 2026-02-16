<p align="center">
  <img src="poly-mcp-ts.png" alt="PolymCP-TS Logo" width="700"/>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://github.com/llm-use/polymcp/stargazers"><img src="https://img.shields.io/github/stars/llm-use/polymcp?style=social" alt="GitHub stars"></a>
  <img src="https://img.shields.io/badge/node-%3E%3D18-green.svg" alt="Node 18+">
  <img src="https://img.shields.io/badge/typescript-production-informational" alt="TypeScript">
</p>

> TypeScript implementation of PolyMCP for MCP servers, clients, and agents.

Version: 1.3.6

## What This Package Is For

Use `polymcp-ts` when you want to build MCP-native systems in a Node.js stack.

It includes:
- MCP server exposure (HTTP, stdio, in-process)
- stdio MCP client with connection pooling
- multi-step agent orchestration
- 🦞 PolyClaw autonomous OpenClaw-style shell execution agent (Docker-first)
- skills via skills.sh (external CLI)
- sandbox executor modules

## Install

Requirements: Node.js 18+

```bash
npm install
```

## Build and Test

```bash
npm run build
npm test
npm run lint
```

## One-Command MCP App Scaffold

```bash
npx ts-node src/cli/index.ts init my-mcp-app --type mcp-app
cd my-mcp-app
npm run dev
```

## Minimal Examples

Define a tool:

```ts
import { tool } from 'polymcp-ts';
import { z } from 'zod';

export const add = tool({
  name: 'add',
  description: 'Add two numbers',
  parameters: z.object({ a: z.number(), b: z.number() }),
  execute: async ({ a, b }) => a + b,
});
```

Expose HTTP MCP server:

```ts
import { exposeToolsHttp } from 'polymcp-ts';
import { add } from './tools';

const app = await exposeToolsHttp([add], {
  title: 'Math MCP Server',
  description: 'Example server',
  version: '1.0.0',
});

app.listen(3000);
```

Expose stdio MCP server:

```ts
import { StdioMCPServer } from 'polymcp-ts';
import { add } from './tools';

new StdioMCPServer([add], {
  name: 'Math Stdio',
  version: '1.0.0',
}).run();
```

Use stdio client and pool:

```ts
import { MCPStdioClient, StdioClientPool } from 'polymcp-ts';

const client = new MCPStdioClient({
  command: 'npx',
  args: ['@playwright/mcp@latest'],
});
await client.connect();
await client.disconnect();

const pool = new StdioClientPool({ command: 'node', args: ['dist/server.js'] }, 3);
await pool.initialize();
await pool.shutdown();
```

## Agent Orchestration Examples

Single MCP server:

```ts
import { UnifiedPolyAgent, OpenAIProvider } from 'polymcp-ts';

const agent = new UnifiedPolyAgent({
  llmProvider: new OpenAIProvider({
    apiKey: process.env.OPENAI_API_KEY!,
    model: 'gpt-4o-mini',
  }),
  mcpServers: ['http://localhost:3000/mcp'],
  verbose: true,
});

await agent.start();
const answer = await agent.run('Summarize tasks and compute totals.');
console.log(answer);
```

Multiple MCP servers (HTTP + stdio):

```ts
import { UnifiedPolyAgent, OpenAIProvider } from 'polymcp-ts';

const agent = new UnifiedPolyAgent({
  llmProvider: new OpenAIProvider({
    apiKey: process.env.OPENAI_API_KEY!,
    model: 'gpt-4o-mini',
  }),
  mcpServers: ['http://localhost:3000/mcp', 'http://localhost:3001/mcp'],
  stdioServers: [{ command: 'npx', args: ['@playwright/mcp@latest'] }],
  verbose: true,
});

await agent.start();
const answer = await agent.run('Collect data and summarize.');
console.log(answer);
```

## 🦞 PolyClaw (Autonomous OpenClaw-Style Agent)

PolyClaw is an autonomous agent inspired by OpenClaw for end-to-end execution in TypeScript PolyMCP workflows.

What it does:
- Understands a goal and executes the workflow autonomously
- Runs real shell actions inside Docker with the project mounted at `/workspace`
- Can create, configure, register, and test MCP servers via `polymcp` CLI when useful
- Adapts strategy from command output and continues until completion
- Produces a final report with completed actions, failures, and next concrete step

Safety defaults:
- Delete/remove commands require confirmation by default (`confirmDeleteCommands: true`)
- If destructive commands are denied, PolyClaw reports that no removal was executed
- Recommended usage: isolated Docker environments for autonomous runs

Programmatic usage:

```ts
import { PolyClawAgent, OllamaProvider } from 'polymcp-ts';

const agent = new PolyClawAgent({
  llmProvider: new OllamaProvider({
    model: process.env.OLLAMA_MODEL || 'llama3.2',
    baseUrl: process.env.OLLAMA_BASE_URL || 'http://localhost:11434',
  }),
  useDocker: true,
  intent: 'auto',
  verbose: true,
  liveMode: true,
});

const result = await agent.run('Create and validate an MCP workflow in this project.');
console.log(result);
```

Runnable examples:
- `examples/polyclaw_example.ts`
- `examples/polyclaw_mcp_workflow_example.ts`

```bash
npm run example:polyclaw
npm run example:polyclaw-mcp-workflow
```

## Skills (skills.sh)

PolyMCP delegates skills management to the skills.sh CLI.
PolyAgent and UnifiedPolyAgent automatically inject relevant skills into prompts.

```bash
npx skills --help

# Install in current project (./.agents/skills)
npx skills add vercel-labs/agent-skills

# Install globally (~/.agents/skills)
npx skills add vercel-labs/agent-skills -g

npx skills list
npx skills list -g
```

In Node, you can also run it via PolyMCP:

```ts
import { runSkillsCli } from 'polymcp-ts';

await runSkillsCli(['add', 'vercel-labs/agent-skills']);
```

TypeScript agents (`PolyAgent`, `UnifiedPolyAgent`) scan skills from:
- `./.agents/skills`
- `./.skills`
- `~/.agents/skills`

If project folders are empty, global skills still apply.

### Skills.sh Agent Example (TypeScript)

```bash
npm run example:test-tool-server
npx skills add vercel-labs/agent-skills
npm run example:skills-sh
```

## Runnable Use Cases (B2B + B2C)

TypeScript versions of the 3 business demos are available in:
- `polymcp-ts/use_cases/`

Quick start:

```bash
# B2B Support
npm run example:usecase:b2b-support-server
npm run example:usecase:b2b-support-smoke

# B2B Dispatch
npm run example:usecase:b2b-dispatch-server
npm run example:usecase:b2b-dispatch-smoke

# B2C Ecommerce
npm run example:usecase:b2c-ecommerce-server
npm run example:usecase:b2c-ecommerce-smoke
```

Each use case has its own README with endpoint details and tested tool flow.

## Main Exports

- servers: `exposeToolsHttp`, `exposeToolsStdio`, `InProcessMCPServer`
- clients: `MCPStdioClient`, `StdioClientPool`, `withStdioClient`
- agents: `PolyAgent`, `UnifiedPolyAgent`, `CodeModeAgent`, `PolyClawAgent`
- skills: `runSkillsCli`
- execution: `SandboxExecutor`, `DockerSandboxExecutor`

## Examples

```bash
npm run example:stdio-server
npm run example:stdio-client
npm run example:docker
```

## License

MIT
