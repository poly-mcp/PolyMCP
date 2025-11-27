<p align="center">
  <img src="poly-mcp-ts.png" alt="PolymCP-TS Logo" width="700"/>
</p>

A TypeScript implementation of the Model Context Protocol (MCP) for building tool servers and AI agents. This library provides a simplified, type-safe API for creating MCP-compatible tools and orchestrating them with LLMs.

## Status

**Work in Progress** - This is the TypeScript implementation of [PolyMCP](https://github.com/poly-mcp/polymcp). Currently in active development.

## Features

- **Simple Tool Creation** - Define tools with minimal boilerplate using decorators
- **Multiple Server Types** - HTTP, stdio, and in-process server implementations  
- **Built-in Authentication** - JWT and API key authentication out of the box
- **Full Type Safety** - Complete TypeScript support with Zod schema validation
- **AI Agent Framework** - Build intelligent agents that can orchestrate multiple tools
- **Multi-Server Support** - Connect to and orchestrate multiple MCP servers
- **Memory & State** - Built-in conversation memory and state management
- **Cross-Platform** - Works on Windows, macOS, and Linux thanks to cross-spawn

## Prerequisites

- Node.js 18.0.0 or higher
- npm, yarn, or pnpm
- TypeScript 5.0+
- (Optional) Ollama for local LLM inference

## Getting Started

### Installation

```bash
# Clone the monorepo
git clone https://github.com/poly-mcp/polymcp.git
cd polymcp/polymcp-ts

# Install dependencies
npm install

# Build the project
npm run build
```

### Quick Example

Create a simple MCP tool server:

```typescript
import { z } from 'zod';
import { tool, exposeToolsHttp } from './src';

// Define tools with schema validation
const mathTools = [
  tool({
    name: 'add',
    description: 'Add two numbers',
    inputSchema: z.object({
      a: z.number().describe('First number'),
      b: z.number().describe('Second number'),
    }),
    function: async ({ a, b }) => a + b,
  }),
  
  tool({
    name: 'multiply',
    description: 'Multiply two numbers',
    inputSchema: z.object({
      x: z.number().describe('First number'),
      y: z.number().describe('Second number'),
    }),
    function: async ({ x, y }) => x * y,
  }),
];

// Start HTTP server
const app = await exposeToolsHttp(mathTools, {
  title: 'Math Tools Server',
  description: 'Basic mathematical operations',
  verbose: true,
});

app.listen(3000, () => {
  console.log('MCP Server running on http://localhost:3000');
});
```

### Test the Server

```bash
# List available tools
curl http://localhost:3000/mcp/list_tools

# Call a tool
curl -X POST http://localhost:3000/mcp/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool": "add", "parameters": {"a": 5, "b": 3}}'
```

## AI Agents

### Using Ollama (Local LLM)

```typescript
import { UnifiedPolyAgent, OllamaProvider } from './src';

// Create an agent with Ollama
const agent = new UnifiedPolyAgent({
  llmProvider: new OllamaProvider({
    model: 'gpt-oss:120b-cloud',  // Large open-source GPT model
    baseUrl: 'http://localhost:11434',
  }),
  httpServers: [{
    url: 'http://localhost:3000',
    name: 'math-server',
  }],
  memoryEnabled: true,
  verbose: true,
});

// Start the agent
await agent.start();

// Use the agent
const response = await agent.runAsync('What is 25 times 4, then add 15?');
console.log(response);
// Output: "25 times 4 equals 100, and adding 15 gives us 115."
```

### Using OpenAI

```typescript
import { UnifiedPolyAgent, OpenAIProvider } from './src';

const agent = new UnifiedPolyAgent({
  llmProvider: new OpenAIProvider({
    apiKey: process.env.OPENAI_API_KEY,
    model: 'gpt-4-turbo-preview',
  }),
  httpServers: [/* your servers */],
});
```

## Playwright Integration

### Using Playwright MCP Server via Stdio

The `playwright_stdio.ts` example shows how to connect to Playwright's MCP server for browser automation:

```typescript
import { UnifiedPolyAgent, OllamaProvider } from './src';

const agent = new UnifiedPolyAgent({
  llmProvider: new OllamaProvider({
    model: 'gpt-oss:120b-cloud',
    baseUrl: 'http://localhost:11434',
  }),
  stdioServers: [{
    command: 'npx',
    args: ['@playwright/mcp@latest'],
  }],
  memoryEnabled: true,
  verbose: true,
});

await agent.start();

// Use Playwright tools through the agent
const response = await agent.runAsync(`
  Go to github.com/poly-mcp/polymcp,
  take a screenshot,
  analyze the README,
  and summarize the key features
`);
```

This connects to Playwright's official MCP server which provides tools for:
- Web navigation
- Screenshots
- Page content extraction
- Form filling
- Click actions
- And more browser automation features

## Examples

The `examples/` directory contains practical examples from basic to advanced:

### Basic Examples

| Example | Description | Command |
|---------|-------------|---------|
| `simple_example.ts` | Basic tool creation and HTTP server | `npm run example:simple` |
| `auth_example.ts` | JWT and API key authentication | `npm run example:auth` |
| `test_tool_server.ts` | Example MCP tool server | `npm run test:tool-server` |

### Advanced Examples

| Example | Description | Features |
|---------|-------------|----------|
| `playwright_server.ts` | Browser automation server | 11 Playwright tools for web scraping |
| `playwright_stdio.ts` | Playwright MCP client via stdio | Connect to official Playwright MCP |
| `ollama_agent.ts` | Local LLM agent | Interactive mode, memory, tool usage |
| `multi_server_agent.ts` | Multi-server orchestration | Coordinate multiple MCP servers |
| `advanced_workflow.ts` | E-commerce monitoring | Production-ready workflow example |

### Running Examples

```bash
# Basic examples
npm run example:simple
npm run example:auth

# Advanced examples  
npm run example:playwright-server   # Start Playwright server
npm run example:ollama-agent        # Run Ollama agent
npm run example:ollama-interactive  # Interactive chat mode
npm run example:multi-server        # Multi-server orchestration

# Playwright via stdio (requires npx)
ts-node examples/playwright_stdio.ts
```

## Core Concepts

### 1. Tool Definition

Tools are the basic building blocks:

```typescript
const myTool = tool({
  name: 'unique_tool_name',
  description: 'What this tool does',
  inputSchema: z.object({
    param1: z.string().describe('Parameter description'),
    param2: z.number().optional(),
  }),
  outputSchema: z.object({  // Optional output validation
    result: z.string(),
  }),
  function: async (input) => {
    // Tool implementation
    return { result: 'output' };
  },
});
```

### 2. Server Types

#### HTTP Server
```typescript
const app = await exposeToolsHttp(tools, {
  title: 'My Server',
  auth: { type: 'api_key', apiKey: 'secret' },
});
```

#### Stdio Server
```typescript
const client = new MCPStdioClient({
  command: 'npx',
  args: ['@modelcontextprotocol/server-everything'],
});
await client.connect();
```

#### In-Process Server
```typescript
const server = new InProcessMCPServer(tools);
const result = await server.invokeTool('tool_name', params);
```

### 3. Authentication

```typescript
// JWT Authentication
const authManager = createAuthManager({
  type: 'jwt',
  jwtSecret: process.env.JWT_SECRET,
  jwtExpiration: '24h',
});

// API Key Authentication  
const authManager = createAuthManager({
  type: 'api_key',
  apiKey: process.env.API_KEY,
});

// Apply to server
app.use('/mcp/invoke', authManager.middleware());
```

### 4. Agent Memory

```typescript
const agent = new UnifiedPolyAgent({
  llmProvider: /* ... */,
  memoryEnabled: true,  // Enable conversation memory
  memoryConfig: {
    maxMessages: 100,   // Keep last 100 messages
    persistPath: './memory.json',  // Optional persistence
  },
});
```

## Architecture

```
polymcp-ts/
├── src/
│   ├── agent/              # AI agent implementations
│   │   ├── agent.ts            # Base agent class
│   │   ├── unified_agent.ts    # Main unified agent
│   │   ├── codemode_agent.ts   # Code-focused agent
│   │   ├── llm_providers.ts    # LLM integrations
│   │   └── index.ts
│   ├── toolkit/            # Tool creation and management
│   │   ├── expose.ts           # Server exposure utilities
│   │   ├── tool-helpers.ts     # Tool helper functions
│   │   └── index.ts
│   ├── stdio/              # Stdio client/server
│   │   ├── client.ts           # Stdio client implementation
│   │   └── index.ts
│   ├── executor/           # Tool execution
│   │   ├── executor.ts         # Main executor
│   │   ├── tools_api.ts        # Tools API
│   │   └── index.ts
│   ├── auth/               # Authentication
│   │   └── index.ts            # Auth implementations
│   ├── registry/           # Server registry
│   │   └── index.ts
│   ├── validation/         # Schema validation
│   │   └── index.ts
│   ├── config/             # Configuration
│   │   └── index.ts
│   ├── constants.ts        # Global constants
│   ├── errors.ts           # Error definitions
│   ├── types.ts            # TypeScript types
│   ├── version.ts          # Version info
│   └── index.ts            # Main entry point
├── examples/               # Usage examples
├── tests/                  # Test suite
└── dist/                   # Compiled JavaScript (generated)
```

## Development

### Scripts

```bash
# Development
npm run dev          # Watch mode
npm run build        # Build project
npm run lint         # Run ESLint
npm run format       # Format with Prettier

# Testing
npm run test         # Run tests
npm run test:watch   # Watch mode

# Examples
npm run example:simple              # Basic example
npm run example:playwright-server   # Browser automation
npm run example:ollama-agent       # AI agent
```

### Environment Variables

Create a `.env` file in the project root:

```bash
# Server Configuration
PORT=3000
HOST=0.0.0.0

# Authentication
JWT_SECRET=your-secret-key-here
API_KEY=your-api-key-here

# LLM Providers (optional)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
```

## Debugging

### Enable Verbose Logging

```typescript
// For servers
exposeToolsHttp(tools, { verbose: true });

// For agents
new UnifiedPolyAgent({ verbose: true });

// For stdio clients
new MCPStdioClient({ verbose: true });
```

## 🙏 Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) - The MCP specification by Anthropic
- [PolyMCP](https://github.com/poly-mcp/polymcp) - The original Python implementation
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) - Official TypeScript SDK
- [Playwright MCP](https://github.com/microsoft/playwright) - Browser automation tools

## Links

- **Main Repository**: [github.com/poly-mcp/polymcp](https://github.com/poly-mcp/polymcp)
- **Python Version**: See the `polymcp/` directory in the monorepo
- **Issues**: [github.com/poly-mcp/polymcp/issues](https://github.com/poly-mcp/polymcp/issues)

---

<p align="center">
  Part of the <a href="https://github.com/poly-mcp/polymcp">PolyMCP</a> project family
</p>
