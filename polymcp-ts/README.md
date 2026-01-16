<p align="center">
  <img src="poly-mcp-ts.png" alt="PolymCP-TS Logo" width="700"/>
</p>

# PolyMCP-TS

A TypeScript implementation of the Model Context Protocol (MCP) for building tool servers and AI agents. This library provides a comprehensive, type-safe API for creating MCP-compatible tools and orchestrating them with LLMs.

## Status

**Production Ready** ✅ - Complete TypeScript implementation of [PolyMCP](https://github.com/poly-mcp/polymcp) with cross-platform support for Windows, macOS, and Linux.

## Features

### 🔌 **Stdio MCP Server & Client**
Full JSON-RPC 2.0 implementation for creating stdio-based MCP servers compatible with Claude Desktop, npm packages, and any MCP client.

```typescript
import { StdioMCPServer } from 'polymcp-ts';
import { z } from 'zod';

const weatherTool = {
  name: 'get_weather',
  description: 'Get current weather for a city',
  parameters: z.object({
    city: z.string().describe('City name'),
    units: z.enum(['celsius', 'fahrenheit']).optional().default('celsius')
  }),
  execute: async ({ city, units }) => {
    return JSON.stringify({ city, temp: 22, conditions: 'Sunny', units });
  }
};

const server = new StdioMCPServer([weatherTool], {
  name: 'Weather Server',
  version: '1.0.0',
  verbose: true
});

server.run(); // Listens on stdin/stdout
```

**Features:**
- ✅ MCP Protocol 2024-11-05 compliant
- ✅ Cross-platform (Windows, Linux, macOS) with automatic path resolution
- ✅ Automatic process spawning for clients
- ✅ Compatible with Claude Desktop and npm packages
- ✅ Graceful shutdown and error handling

### 🌐 **Multiple Server Types**
Choose the best server type for your use case:

#### HTTP Server - RESTful API
```typescript
import { exposeToolsHttp } from 'polymcp-ts';

const app = await exposeToolsHttp(tools, {
  title: 'My MCP Server',
  description: 'Production MCP tools',
  version: '1.0.0',
  verbose: true
});

app.listen(3000);
```

**Endpoints:**
- `GET /mcp/list_tools` - List all available tools
- `POST /mcp/invoke` - Invoke a specific tool
- `GET /docs` - Swagger documentation

#### Stdio Server - JSON-RPC 2.0
```typescript
import { StdioMCPServer } from 'polymcp-ts';

const server = new StdioMCPServer(tools, {
  name: 'My Stdio Server',
  version: '1.0.0'
});

server.run(); // Compatible with Claude Desktop
```

#### In-Process Server - Direct Calls
```typescript
import { InProcessMCPServer } from 'polymcp-ts';

const server = new InProcessMCPServer(tools);
const result = await server.invokeTool('tool_name', { param: 'value' });
// Zero network overhead, perfect for embedded use
```

### 🐳 **Docker Sandbox Executor**
Execute untrusted code safely in isolated Docker containers with comprehensive security controls.

```typescript
import { DockerSandboxExecutor } from 'polymcp-ts';

const executor = new DockerSandboxExecutor({
  cpuLimit: 0.5,          // 50% CPU limit
  memoryLimit: 256,       // 256MB RAM
  networkIsolation: true, // Disable network
  timeout: 30000          // 30 second timeout
});

const result = await executor.execute(`
  console.log("Hello from Docker!");
  const data = [1, 2, 3, 4, 5];
  console.log("Sum:", data.reduce((a, b) => a + b, 0));
`);

console.log(result.output);
// Hello from Docker!
// Sum: 15
```

**Security Features:**
- ✅ Resource limits (CPU, memory, PIDs)
- ✅ Network isolation
- ✅ Filesystem restrictions
- ✅ Timeout protection
- ✅ Clean isolated environment

### 🧠 **Skills System**
Intelligent tool loading with semantic matching - dramatically reduce token usage by loading only relevant tools.

```typescript
import { MCPSkillGenerator, MCPSkillMatcher } from 'polymcp-ts';

// Generate skills from MCP server
const generator = new MCPSkillGenerator();
await generator.generateFromMCP({
  serverUrl: 'http://localhost:8000/mcp',
  outputPath: './skills/github_SKILL.md',
  skillName: 'GitHub Operations'
});

// Match skills to tasks
const matcher = new MCPSkillMatcher('./skills');
const matches = await matcher.matchSkills('send an email to John');
// Returns: email skill (5 tools) instead of all 200 tools!

console.log(`Token savings: ${matches.tokenSavings}%`); // 87%
console.log(`Matched skills: ${matches.skills.map(s => s.name).join(', ')}`);
```

**Benefits:**
- **87% token reduction** - Load 5 tools instead of 200
- **38% accuracy increase** - Less confusion from irrelevant tools
- **Automatic generation** - Create skills from existing MCP servers
- **Semantic matching** - Match tools to tasks intelligently
- **11 built-in categories** - Organized tool discovery

### ⚡ **Connection Pooling**
Round-robin client pools for load balancing and concurrent request handling.

```typescript
import { StdioClientPool } from 'polymcp-ts';

const pool = new StdioClientPool(
  {
    command: process.execPath,
    args: ['dist/server.js']
  },
  3 // Pool size: 3 clients
);

await pool.initialize();

// Requests automatically distributed across clients
const results = await Promise.all([
  pool.execute(client => client.callTool('tool1', params1)),
  pool.execute(client => client.callTool('tool2', params2)),
  pool.execute(client => client.callTool('tool3', params3)),
]);

await pool.shutdown();
```

### 🚀 **Parallel Tool Execution**
Execute multiple tools simultaneously for faster workflows.

```typescript
import { MCPStdioClient } from 'polymcp-ts';

const client = new MCPStdioClient({ command: '...', args: [...] });
await client.connect();

// Execute 3 tools in parallel
const [weather, calculation, dateInfo] = await Promise.all([
  client.callTool('get_weather', { city: 'Paris' }),
  client.callTool('calculate', { expression: '10 * 5' }),
  client.callTool('get_date_info', { format: 'iso' })
]);

console.log('All tools completed simultaneously!');
```

### 🤖 **AI Agent Framework**
Build intelligent agents that orchestrate multiple tools with LLMs.

```typescript
import { UnifiedPolyAgent, OpenAIProvider, OllamaProvider } from 'polymcp-ts';

// With OpenAI
const agent = new UnifiedPolyAgent({
  llmProvider: new OpenAIProvider({
    apiKey: process.env.OPENAI_API_KEY,
    model: 'gpt-4-turbo-preview'
  }),
  httpServers: [{ url: 'http://localhost:3000', name: 'tools' }],
  stdioServers: [{ command: 'npx', args: ['@playwright/mcp@latest'] }],
  memoryEnabled: true,
  verbose: true
});

await agent.start();

const response = await agent.runAsync(`
  Search for "TypeScript MCP" on GitHub,
  take a screenshot,
  and summarize the top 3 results
`);
```

**Supported LLM Providers:**
- ✅ **OpenAI** (GPT-4, GPT-3.5-turbo)
- ✅ **Anthropic** (Claude 3 Opus, Sonnet, Haiku)
- ✅ **Ollama** (Local models: Llama 2, Mistral, etc.)

**Agent Features:**
- ✅ Autonomous multi-step reasoning
- ✅ Persistent conversation memory
- ✅ Mixed server support (HTTP + stdio)
- ✅ Tool selection and orchestration
- ✅ Code generation mode

### UnifiedPolyAgent UPDATE

UnifiedPolyAgent now includes production-grade capabilities without changing the public API. Existing code keeps working as-is, but you can enable extra controls for cost, reliability, security, and observability.

What’s included in v2:
- Budget controls: wall-time, token cap (est.), tool-call limits, payload limits
- Observability: structured logs with trace IDs + runtime metrics (latency, success rate, server health)
- Security: automatic redaction + tool allowlist/denylist support
- Resilience: retries with exponential backoff, circuit breakers, per-tool/per-server rate limiting
- Performance knobs: caching + bounded memory history

Production configuration example:

```ts
import { UnifiedPolyAgent, OllamaProvider } from 'polymcp-ts';

const agent = new UnifiedPolyAgent({
  llmProvider: new OllamaProvider({
    model: 'llama2',
    baseUrl: 'http://localhost:11434',
  }),
  stdioServers: [{ command: 'npx', args: ['@playwright/mcp@latest'] }],

  // Budget / cost control
  maxWallTime: 300,
  maxTokens: 100000,
  maxToolCalls: 20,
  maxPayloadBytes: 10 * 1024 * 1024,

  // Observability
  enableStructuredLogs: true,
  logFile: 'agent.log',

  // Security
  redactLogs: true,
  // toolAllowlist: new Set(['safe_tool_1', 'safe_tool_2']),
  // toolDenylist: new Set(['dangerous_tool']),

  // Resilience
  maxRetries: 3,
  retryBackoff: 1.0,
  enableHealthChecks: true,
  circuitBreakerThreshold: 5,
  enableRateLimiting: true,
  defaultRateLimit: 10,
});

await agent.start();
const response = await agent.runAsync('Your query');
````

Export metrics and logs:

```ts
const metrics = agent.getMetrics();
const logsJson = agent.exportLogs('json');
```

### 🔒 **Built-in Authentication**
Production-ready JWT and API key authentication.

```typescript
import { createAuthManager, exposeToolsHttp } from 'polymcp-ts';

// JWT Authentication
const jwtAuth = createAuthManager({
  type: 'jwt',
  jwtSecret: 'your-secret-key-min-32-chars',
  jwtExpiration: '24h',
  issuer: 'my-server'
});

// API Key Authentication
const apiKeyAuth = createAuthManager({
  type: 'api_key',
  apiKey: 'sk-your-secret-api-key'
});

// Apply to server
const app = await exposeToolsHttp(tools, {
  title: 'Secure Server',
  auth: jwtAuth
});
```

### 🛠️ **CLI Tool**
Command-line interface for project scaffolding and testing.

```bash
# Initialize new project
polymcp init my-server --type stdio-server

# Test MCP server
polymcp test http://localhost:3000/mcp

# Show version
polymcp --version
```

**Available Templates:**
- `stdio-server` - Stdio-based MCP server
- `http-server` - HTTP-based MCP server
- `docker-server` - Server with Docker sandbox
- `skills-server` - Server with skills system

### ✅ **Full Type Safety**
Complete TypeScript support with Zod schema validation.

```typescript
import { z } from 'zod';
import { tool } from 'polymcp-ts';

const myTool = tool({
  name: 'process_data',
  description: 'Process data with validation',
  inputSchema: z.object({
    data: z.array(z.number()),
    operation: z.enum(['sum', 'average', 'max']),
    options: z.object({
      round: z.boolean().optional()
    }).optional()
  }),
  outputSchema: z.object({
    result: z.number(),
    operation: z.string()
  }),
  function: async (input) => {
    // Full type inference and validation!
    return { result: 42, operation: input.operation };
  }
});
```

### 💾 **Memory & State**
Built-in conversation memory and state management for AI agents.

```typescript
const agent = new UnifiedPolyAgent({
  llmProvider: /* ... */,
  memoryEnabled: true,
  memoryConfig: {
    maxMessages: 100,
    persistPath: './memory.json'
  }
});
```

### 🌍 **Cross-Platform**
Works seamlessly on Windows, macOS, and Linux.

- ✅ Automatic path resolution for all platforms
- ✅ Platform-specific process spawning
- ✅ Cross-platform command execution via `cross-spawn`
- ✅ Native OS signal handling

## Prerequisites

- **Node.js** 18.0.0 or higher
- **npm**, yarn, or pnpm
- **TypeScript** 5.0+
- **(Optional)** Docker for sandbox execution
- **(Optional)** Ollama for local LLM inference

## Getting Started

### Installation

```bash
# Clone the repository
git clone https://github.com/poly-mcp/polymcp.git
cd polymcp/polymcp-ts

# Install dependencies
npm install

# Build the project
npm run build

# (Optional) Install CLI globally
npm link
```

### Quick Example - HTTP Server

Create a simple HTTP MCP server:

```typescript
import { z } from 'zod';
import { tool, exposeToolsHttp } from 'polymcp-ts';

// Define tools with validation
const tools = [
  tool({
    name: 'add',
    description: 'Add two numbers',
    inputSchema: z.object({
      a: z.number().describe('First number'),
      b: z.number().describe('Second number')
    }),
    function: async ({ a, b }) => a + b
  }),
  
  tool({
    name: 'multiply',
    description: 'Multiply two numbers',
    inputSchema: z.object({
      x: z.number(),
      y: z.number()
    }),
    function: async ({ x, y }) => x * y
  })
];

// Start server
const app = await exposeToolsHttp(tools, {
  title: 'Math Tools',
  description: 'Basic math operations',
  verbose: true
});

app.listen(3000, () => {
  console.log('🚀 Server running on http://localhost:3000');
});
```

**Test the server:**
```bash
# List tools
curl http://localhost:3000/mcp/list_tools

# Call a tool
curl -X POST http://localhost:3000/mcp/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool": "add", "parameters": {"a": 5, "b": 3}}'
```

### Quick Example - Stdio Server

Create a stdio-based MCP server compatible with Claude Desktop:

```typescript
import { z } from 'zod';
import { StdioMCPServer } from 'polymcp-ts';

const tools = [
  {
    name: 'greet',
    description: 'Greet someone',
    parameters: z.object({
      name: z.string()
    }),
    execute: async ({ name }) => `Hello, ${name}!`
  }
];

const server = new StdioMCPServer(tools, {
  name: 'Greeting Server',
  version: '1.0.0'
});

server.run();
```

**Integration with Claude Desktop:**

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or equivalent on other platforms:

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "node",
      "args": ["/absolute/path/to/dist/server.js"]
    }
  }
}
```

### Quick Example - AI Agent with Ollama

Use a local LLM to orchestrate tools:

```typescript
import { UnifiedPolyAgent, OllamaProvider } from 'polymcp-ts';

const agent = new UnifiedPolyAgent({
  llmProvider: new OllamaProvider({
    model: 'llama2',
    baseUrl: 'http://localhost:11434'
  }),
  httpServers: [{
    url: 'http://localhost:3000',
    name: 'math-server'
  }],
  memoryEnabled: true,
  verbose: true
});

await agent.start();

const response = await agent.runAsync('What is 25 times 4, then add 15?');
console.log(response);
// Output: "25 times 4 equals 100, and adding 15 gives us 115."
```

## Examples

The `examples/` directory contains comprehensive examples from basic to advanced:

### 📚 Complete Examples

| Example | Description | Features | Command |
|---------|-------------|----------|---------|
| **stdio_complete_example.ts** | Stdio server/client | Connection pooling, parallel execution, cross-platform | `tsx examples/stdio_complete_example.ts client` |
| **docker_advanced_example.ts** | Docker sandbox | Resource limits, security, isolated execution | `tsx examples/docker_advanced_example.ts quick` |
| **skills_workflow_example.ts** | Skills system | Generation, matching, semantic workflow | `tsx examples/skills_workflow_example.ts workflow` |
| **simple_example.ts** | Basic HTTP server | Tool creation, server setup | `npm run example:simple` |
| **auth_example.ts** | Authentication | JWT, API keys, secure endpoints | `npm run example:auth` |
| **ollama_agent.ts** | Local LLM agent | Memory, tool orchestration, Ollama | `npm run example:ollama-agent` |
| **playwright_stdio.ts** | Browser automation | Playwright MCP integration via stdio | `tsx examples/playwright_stdio.ts` |
| **multi_server_agent.ts** | Multi-server orchestration | Coordinate multiple MCP servers | `npm run example:multi-server` |
| **advanced_workflow.ts** | E-commerce monitoring | Production-ready workflow | `npm run example:workflow` |

### Running Examples

```bash
# Stdio examples
tsx examples/stdio_complete_example.ts client    # Basic client
tsx examples/stdio_complete_example.ts advanced  # Parallel execution
tsx examples/stdio_complete_example.ts pool      # Connection pooling

# Docker examples
tsx examples/docker_advanced_example.ts quick    # Quick test
tsx examples/docker_advanced_example.ts docker   # Full Docker workflow
tsx examples/docker_advanced_example.ts tools    # Docker with tools

# Skills examples
tsx examples/skills_workflow_example.ts workflow # Full workflow
tsx examples/skills_workflow_example.ts mock     # Mock servers
tsx examples/skills_workflow_example.ts match "send email" # Match query

# Agent examples
npm run example:ollama-agent                     # Ollama agent
npm run example:ollama-interactive               # Interactive mode
npm run example:multi-server                     # Multi-server
npm run example:workflow                         # Advanced workflow
```

## Core Concepts

### 1. Tool Definition

Tools are the basic building blocks. Define them with Zod schemas for automatic validation:

```typescript
import { z } from 'zod';

// For HTTP servers - use 'tool()' helper
const httpTool = tool({
  name: 'analyze_sentiment',
  description: 'Analyze sentiment of text',
  inputSchema: z.object({
    text: z.string().min(1).max(1000),
    language: z.enum(['en', 'es', 'fr']).optional()
  }),
  outputSchema: z.object({
    sentiment: z.enum(['positive', 'negative', 'neutral']),
    confidence: z.number().min(0).max(1)
  }),
  function: async (input) => {
    return { sentiment: 'positive', confidence: 0.95 };
  }
});

// For Stdio servers - use direct object
const stdioTool = {
  name: 'analyze_sentiment',
  description: 'Analyze sentiment of text',
  parameters: z.object({
    text: z.string(),
    language: z.enum(['en', 'es', 'fr']).optional()
  }),
  execute: async ({ text, language }) => {
    return JSON.stringify({ sentiment: 'positive', confidence: 0.95 });
  }
};
```

### 2. Server Types

#### HTTP Server - RESTful API

```typescript
const app = await exposeToolsHttp(tools, {
  title: 'My Server',
  description: 'Server description',
  version: '1.0.0',
  auth: { type: 'api_key', apiKey: 'secret' },
  verbose: true
});

app.listen(3000);
```

**Endpoints:**
- `GET /mcp/list_tools` - List all tools
- `POST /mcp/invoke` - Invoke a tool
- `GET /docs` - Swagger documentation

#### Stdio Server - JSON-RPC 2.0

```typescript
const server = new StdioMCPServer(tools, {
  name: 'My Stdio Server',
  version: '1.0.0',
  verbose: true
});

server.run(); // Listens on stdin/stdout
```

**Protocol:**
- JSON-RPC 2.0 compliant
- MCP Protocol 2024-11-05
- Compatible with Claude Desktop

#### In-Process Server - Direct Calls

```typescript
const server = new InProcessMCPServer(tools);

// Direct function call, no network
const result = await server.invokeTool('tool_name', {
  param: 'value'
});
```

**Benefits:**
- Zero network overhead
- No serialization
- Perfect for embedded use

### 3. Stdio Client

Connect to stdio-based MCP servers:

```typescript
import { MCPStdioClient, withStdioClient } from 'polymcp-ts';

// Manual management
const client = new MCPStdioClient({
  command: process.execPath,
  args: ['dist/server.js'],
  timeout: 30000,
  verbose: true
});

await client.connect();
const tools = await client.listTools();
const result = await client.callTool('tool_name', params);
await client.disconnect();

// Automatic cleanup with helper
await withStdioClient(
  { command: process.execPath, args: ['dist/server.js'] },
  async (client) => {
    const result = await client.callTool('tool_name', params);
    return result;
  }
);
```

### 4. Docker Sandbox

Execute untrusted code safely:

```typescript
import { DockerSandboxExecutor } from 'polymcp-ts';

const executor = new DockerSandboxExecutor({
  image: 'node:18-alpine',  // Docker image
  cpuLimit: 0.5,            // 50% CPU
  memoryLimit: 256,         // 256MB RAM
  pidsLimit: 50,            // Max 50 processes
  networkIsolation: true,   // No network access
  timeout: 30000,           // 30 second timeout
  workDir: '/workspace'     // Working directory
});

const result = await executor.execute(`
  const fs = require('fs');
  const data = [1, 2, 3, 4, 5];
  const sum = data.reduce((a, b) => a + b, 0);
  console.log('Sum:', sum);
`);

console.log(result.output);        // Sum: 15
console.log(result.exitCode);      // 0
console.log(result.executionTime); // 234ms
```

### 5. Skills System

Generate and match skills:

```typescript
import { MCPSkillGenerator, MCPSkillMatcher, MCPSkillLoader } from 'polymcp-ts';

// 1. Generate skills from MCP server
const generator = new MCPSkillGenerator();
await generator.generateFromMCP({
  serverUrl: 'http://localhost:8000/mcp',
  outputPath: './skills/myserver_SKILL.md',
  skillName: 'My Server Tools',
  category: 'Productivity'
});

// 2. Load skills
const loader = new MCPSkillLoader();
const skills = await loader.loadSkills('./skills');

console.log(`Loaded ${skills.length} skills`);

// 3. Match skills to task
const matcher = new MCPSkillMatcher('./skills');
const matches = await matcher.matchSkills('send email to John');

console.log(`Matched ${matches.skills.length} skills`);
console.log(`Token savings: ${matches.tokenSavings}%`);

for (const match of matches.skills) {
  console.log(`- ${match.name} (score: ${match.score})`);
}
```

### 6. AI Agents

Build intelligent agents with LLMs:

```typescript
import { UnifiedPolyAgent, OpenAIProvider, OllamaProvider } from 'polymcp-ts';

// With OpenAI
const openaiAgent = new UnifiedPolyAgent({
  llmProvider: new OpenAIProvider({
    apiKey: process.env.OPENAI_API_KEY,
    model: 'gpt-4-turbo-preview'
  }),
  httpServers: [
    { url: 'http://localhost:3000', name: 'tools' }
  ],
  memoryEnabled: true,
  verbose: true
});

// With Ollama (local)
const ollamaAgent = new UnifiedPolyAgent({
  llmProvider: new OllamaProvider({
    model: 'llama2',
    baseUrl: 'http://localhost:11434'
  }),
  stdioServers: [
    { command: 'npx', args: ['@playwright/mcp@latest'] }
  ],
  memoryEnabled: true
});

await openaiAgent.start();
const response = await openaiAgent.runAsync('What is 2 + 2?');
```

### 7. Authentication

Secure your servers:

```typescript
import { createAuthManager, exposeToolsHttp } from 'polymcp-ts';

// JWT Authentication
const jwtAuth = createAuthManager({
  type: 'jwt',
  jwtSecret: 'your-secret-key-min-32-chars',
  jwtExpiration: '24h',
  issuer: 'my-server'
});

// API Key Authentication
const apiKeyAuth = createAuthManager({
  type: 'api_key',
  apiKey: 'sk-your-secret-api-key'
});

// Apply to server
const app = await exposeToolsHttp(tools, {
  title: 'Secure Server',
  auth: jwtAuth
});

// Client usage
const response = await fetch('http://localhost:3000/mcp/invoke', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your-jwt-token',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ tool: 'my_tool', parameters: {} })
});
```

## Playwright Integration

Connect to Playwright's official MCP server for browser automation:

```typescript
import { UnifiedPolyAgent, OllamaProvider } from 'polymcp-ts';

const agent = new UnifiedPolyAgent({
  llmProvider: new OllamaProvider({
    model: 'llama2',
    baseUrl: 'http://localhost:11434'
  }),
  stdioServers: [{
    command: 'npx',
    args: ['@playwright/mcp@latest']
  }],
  memoryEnabled: true,
  verbose: true
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

**Available Playwright Tools:**
- Web navigation
- Screenshots
- Page content extraction
- Form filling
- Click actions
- Element interaction
- And more browser automation features

## Architecture

```
polymcp-ts/
├── src/
│   ├── agent/                  # AI agent implementations
│   │   ├── agent.ts                # Base agent
│   │   ├── unified_agent.ts        # Unified agent with memory
│   │   ├── codemode_agent.ts       # Code generation agent
│   │   └── llm_providers.ts        # OpenAI, Anthropic, Ollama
│   ├── toolkit/                # Tool creation
│   │   ├── expose.ts               # HTTP, In-process servers
│   │   └── tool-helpers.ts         # Tool utilities
│   ├── stdio/                  # Stdio implementation
│   │   ├── client.ts               # Stdio client
│   │   ├── expose_tools_stdio.ts   # Stdio server
│   │   └── index.ts
│   ├── executor/               # Code execution
│   │   ├── executor.ts             # Base executor
│   │   ├── docker.ts               # Docker sandbox
│   │   └── tools_api.ts            # Tools API
│   ├── skills/                 # Skills system
│   │   ├── generator.ts            # Skill generation
│   │   ├── loader.ts               # Skill loading
│   │   └── matcher.ts              # Skill matching
│   ├── tools/                  # Built-in tools
│   │   └── advanced.ts             # Advanced tools
│   ├── cli/                    # CLI tool
│   │   ├── index.ts                # CLI entry
│   │   └── commands/               # Commands
│   ├── auth/                   # Authentication
│   ├── registry/               # Server registry
│   ├── validation/             # Schema validation
│   ├── config/                 # Configuration
│   ├── constants.ts            # Constants
│   ├── errors.ts               # Error types
│   ├── types.ts                # TypeScript types
│   └── index.ts                # Main export
├── examples/                   # Examples
└── package.json
```

## Development

### Scripts

```bash
# Development
npm run dev          # Watch mode (tsc -w)
npm run build        # Build project
npm run lint         # Run ESLint
npm run lint:fix     # Fix linting issues
npm run format       # Format with Prettier

# Testing
npm run test         # Run tests (Jest)
npm run test:watch   # Watch mode

# Examples
npm run example:simple
npm run example:auth
npm run example:ollama-agent
npm run example:multi-server
```

### Environment Variables

Create a `.env` file:

```bash
# Server
PORT=3000
HOST=0.0.0.0

# Authentication
JWT_SECRET=your-secret-key-min-32-characters
API_KEY=sk-your-api-key-here

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Ollama
OLLAMA_BASE_URL=http://localhost:11434

# Docker
DOCKER_HOST=unix:///var/run/docker.sock
```

## Testing

```bash
# Run all tests
npm test

# Run specific test file
npm test -- stdio.test.ts

# Watch mode
npm run test:watch

# Coverage
npm test -- --coverage
```

## Debugging

### Enable Verbose Logging

```typescript
// Servers
exposeToolsHttp(tools, { verbose: true });
new StdioMCPServer(tools, { verbose: true });

// Clients
new MCPStdioClient({ command: '...', verbose: true });

// Agents
new UnifiedPolyAgent({ verbose: true });

// Executors
new DockerSandboxExecutor({ verbose: true });
```

### Debug Logs

```bash
# Enable debug logs
DEBUG=polymcp:* tsx examples/stdio_complete_example.ts client

# Specific module
DEBUG=polymcp:stdio tsx examples/stdio_complete_example.ts client
```

## Deployment

### Docker Deployment

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --production

COPY dist ./dist

EXPOSE 3000

CMD ["node", "dist/index.js"]
```

### npm Package

```bash
# Build for distribution
npm run build

# Test package locally
npm pack
npm install polymcp-ts-1.0.0.tgz

# Publish to npm
npm publish
```

### Claude Desktop Integration

1. Build your server:
```bash
npm run build
```

2. Add to Claude Desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "node",
      "args": ["/absolute/path/to/polymcp-ts/dist/server.js"]
    }
  }
}
```

3. Restart Claude Desktop

## Performance

### Benchmarks

| Operation | HTTP Server | Stdio Server | In-Process |
|-----------|-------------|--------------|------------|
| Tool Call | ~50ms | ~20ms | ~1ms |
| List Tools | ~10ms | ~5ms | <1ms |
| Startup | ~100ms | ~50ms | <1ms |

### Optimization Tips

1. **Use In-Process for local tools** - Eliminate network overhead
2. **Enable connection pooling** - For concurrent stdio requests
3. **Use parallel execution** - When tools are independent
4. **Cache skill matches** - For repeated queries
5. **Enable compression** - For large payloads

## Troubleshooting

### Common Issues

**1. "spawn tsx ENOENT" - Client can't find tsx**

Solution: Use absolute paths:
```typescript
const client = new MCPStdioClient({
  command: process.execPath,
  args: [resolve(__dirname, '../node_modules/tsx/dist/cli.mjs'), 'server.ts', 'server']
});
```

**2. Docker not found**

Solution: Install Docker Desktop and ensure it's running:
```bash
docker ps  # Should work without errors
```

**3. Port already in use**

Solution: Change port or kill existing process:
```bash
lsof -i :3000
kill -9 <PID>
```

**4. Module not found**

Solution: Rebuild the project:
```bash
npm run clean
npm install
npm run build
```

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](../LICENSE) file

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) - MCP specification by Anthropic
- [PolyMCP](https://github.com/poly-mcp/polymcp) - Original Python implementation
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) - Official SDK
- [Playwright](https://github.com/microsoft/playwright) - Browser automation
- [Zod](https://github.com/colinhacks/zod) - Schema validation

## Links

- **Documentation**: [poly-mcp.com](https://poly-mcp.com)
- **Main Repository**: [github.com/poly-mcp/polymcp](https://github.com/poly-mcp/polymcp)
- **Python Version**: [polymcp/](../polymcp/)
- **Issues**: [github.com/poly-mcp/polymcp/issues](https://github.com/poly-mcp/polymcp/issues)
- **Discussions**: [github.com/poly-mcp/polymcp/discussions](https://github.com/poly-mcp/polymcp/discussions)

---

<p align="center">
  <strong>Part of the <a href="https://github.com/poly-mcp/polymcp">PolyMCP</a> project family</strong>
</p>

<p align="center">
  Built with ❤️ for the MCP community
</p>
