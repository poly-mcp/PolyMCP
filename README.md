<p align="center">
  <img src="poly-mcp.png" alt="PolymCP Logo" width="500"/>
</p>

<p align="center">
  <a href="https://pypi.org/project/polymcp/"><img src="https://img.shields.io/pypi/v/polymcp.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/polymcp/"><img src="https://img.shields.io/pypi/pyversions/polymcp.svg" alt="Python Versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/polymcp.svg" alt="License"></a>
  <a href="https://github.com/llm-use/polymcp/stargazers"><img src="https://img.shields.io/github/stars/llm-use/polymcp?style=social" alt="GitHub stars"></a>
  <a href="https://pepy.tech/project/polymcp"><img src="https://img.shields.io/pepy/dt/polymcp" alt="PyPI downloads"></a>
  <a href="https://www.poly-mcp.com"><img src="https://img.shields.io/badge/website-poly--mcp.com-blue" alt="Website"></a>
</p>

> Universal MCP toolkit and agent framework for Python and TypeScript.

## Overview

PolyMCP gives teams one consistent way to expose tools, connect MCP servers, and run agents that orchestrate those tools. It ships in Python and TypeScript, plus a standalone Inspector and an MCP Apps SDK.

Version: 1.3.6

## What You Can Build

- MCP servers from normal functions
- MCP clients over HTTP, stdio, or in-process transports
- Agents that orchestrate one or more MCP servers
- 🦞 Autonomous OpenClaw-style execution agent workflows with PolyClaw (Docker-first)
- Skills via skills.sh for tool selection and capability packaging
- UI-based MCP Apps with HTML resources and tool bridges

## Project Map

- `polymcp/` Python package (tools, agents, auth, sandbox, CLI)
- `polymcp-ts/` TypeScript implementation
- `polymcp-ts/use_cases/` TypeScript runnable B2B/B2C use cases
- `polymcp-inspector/` standalone Inspector app
- `polymcp_website/` marketing/docs website
- `use_cases/` Python runnable B2B/B2C use cases
- `polymcp_sdk_mcp_apps/` MCP Apps SDK
- `polymcp/cli/` CLI documentation
- `examples/` runnable examples
- `tests/` Python tests
- `registry/` sample registry files
- `my-project/` scaffold output from `polymcp init`

## Quick Start (Python)

Requirements: Python 3.8+

```bash
pip install polymcp
```

Create an MCP HTTP server from plain functions:

```python
from polymcp import expose_tools_http


def add(a: int, b: int) -> int:
    return a + b


app = expose_tools_http(
    tools=[add],
    title="Math Server",
    description="MCP tools over HTTP",
)
```

Run:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

## Quick Start (TypeScript)

Requirements: Node.js 18+

```bash
cd polymcp-ts
npm install
npm run build
```

## Skills (skills.sh)

PolyMCP delegates skills management to the skills.sh CLI.
PolyAgent and UnifiedPolyAgent automatically inject relevant skills into prompts
to improve tool selection and planning.

```bash
npx skills --help

# Install in current project (./.agents/skills)
npx skills add vercel-labs/agent-skills

# Install globally (~/.agents/skills)
npx skills add vercel-labs/agent-skills -g

npx skills list
npx skills list -g
```

Python helper:

```python
from polymcp import run_skills_cli

run_skills_cli(["add", "vercel-labs/agent-skills"])
```

Agents load skills from:
- `./.agents/skills`
- `./.skills`
- `~/.agents/skills`

If Python agents find no project skills, they print:

```text
[WARN] No project skills found in .agents/skills or .skills.
Use global skills: polymcp skills add vercel-labs/agent-skills -g
Or local skills: polymcp skills add vercel-labs/agent-skills
```

### Skills.sh Agent Example (Python)

```bash
python examples/simple_example.py
polymcp skills add vercel-labs/agent-skills
python examples/skills_sh_agent_example.py
```

Minimal server:

```ts
import { tool, exposeToolsHttp } from 'polymcp-ts';
import { z } from 'zod';

const add = tool({
  name: 'add',
  description: 'Add two numbers',
  parameters: z.object({ a: z.number(), b: z.number() }),
  execute: async ({ a, b }) => a + b,
});

const app = await exposeToolsHttp([add], {
  title: 'Math Server',
  description: 'MCP tools over HTTP',
  version: '1.0.0',
});

app.listen(3000);
```

## Inspector

The Inspector is the fastest way to test MCP servers, tools, prompts, and UI resources.

Run standalone Inspector:

```bash
cd polymcp-inspector
python -m polymcp_inspector --host 127.0.0.1 --port 6274 --no-browser
```

Open:

```
http://127.0.0.1:6274/
```

Features:
- chat playground with independent multi-tab sessions (per-tab provider, model, servers, and history)
- tool, resource, and prompt explorers
- MCP Apps UI preview with tool-call bridge
- LLM orchestration (Ollama, OpenAI, Anthropic)
- settings page for Inspector/OpenAI/Claude API keys
- auto-tools routing (LLM decides if tools are needed)
- secure mode with API key and rate limits

## MCP Apps SDK

Use `polymcp_sdk_mcp_apps/` to build UI-first MCP Apps quickly.

```bash
cd polymcp_sdk_mcp_apps
npm install
npm run example:quickstart
```

Connect Inspector to your app server and open the `app://...` resource in Resources.

## Agent Orchestration Examples

Python, multiple MCP servers:

```python
from polymcp.polyagent import UnifiedPolyAgent, OpenAIProvider

agent = UnifiedPolyAgent(
    llm_provider=OpenAIProvider(model="gpt-4o-mini"),
    mcp_servers=[
        "http://localhost:8000/mcp",
        "http://localhost:8001/mcp",
    ],
    verbose=True,
)

answer = agent.run("Read sales data, compute totals, then summarize.")
print(answer)
```

TypeScript, HTTP + stdio:

```ts
import { UnifiedPolyAgent, OpenAIProvider } from 'polymcp-ts';

const agent = new UnifiedPolyAgent({
  llmProvider: new OpenAIProvider({
    apiKey: process.env.OPENAI_API_KEY!,
    model: 'gpt-4o-mini',
  }),
  mcpServers: ['http://localhost:3000/mcp'],
  stdioServers: [{ command: 'npx', args: ['@playwright/mcp@latest'] }],
  verbose: true,
});

await agent.start();
const answer = await agent.run('Collect data and summarize.');
console.log(answer);
```

## 🦞 PolyClaw (Autonomous OpenClaw-Style Agent)

PolyClaw is an autonomous agent inspired by OpenClaw, designed for end-to-end execution in PolyMCP workflows.

What it does:
- Understands a goal and executes the workflow autonomously
- Runs real shell actions inside Docker with the project mounted at `/workspace`
- Can create, configure, register, and test MCP servers via `polymcp` CLI when useful
- Adapts strategy from command output and continues until completion
- Produces a final report with completed actions, failures, and next concrete step

Safety defaults:
- Delete/remove commands require confirmation by default (`--confirm-delete`)
- If destructive commands are denied, PolyClaw reports that no removal was executed
- Recommended usage: isolated Docker environments for autonomous runs

Python examples:
- `examples/polyclaw_example.py`
- `examples/polyclaw_mcp_workflow_example.py`

## CLI

```bash
polymcp init my-project --type http-server
polymcp server add http://localhost:8000/mcp
polymcp agent run
polymcp agent run --type polyclaw --query "Create and validate a local MCP workflow"
polymcp inspector
```

See `polymcp/cli/README.md` for full commands.

## Development

Python:

```bash
pip install -e .[dev]
python -m pytest
```

TypeScript:

```bash
cd polymcp-ts
npm run build
npm test
npm run lint
```

## License

MIT
