/**
 * Init Command - Initialize new PolyMCP projects
 * Creates production-ready MCP server projects in various formats
 */

import * as fs from 'fs-extra';
import * as path from 'path';
import chalk from 'chalk';
import ora from 'ora';
import { execSync } from 'child_process';

/**
 * Project types available
 */
type ProjectType = 'basic' | 'http-server' | 'stdio-server' | 'wasm-server' | 'agent' | 'mcp-app';

/**
 * Init command options
 */
interface InitOptions {
  type: ProjectType;
  withAuth: boolean;
  withExamples: boolean;
  skipInstall: boolean;
}

/**
 * Main init command handler
 */
export async function initCommand(projectName: string, options: InitOptions): Promise<void> {
  const projectPath = path.resolve(projectName);

  // Validate project name
  if (!isValidProjectName(projectName)) {
    throw new Error(
      'Invalid project name. Use lowercase letters, numbers, and hyphens only.'
    );
  }

  // Check if directory exists
  if (fs.existsSync(projectPath)) {
    throw new Error(`Directory '${projectName}' already exists`);
  }

  // Validate project type
  const validTypes: ProjectType[] = ['basic', 'http-server', 'stdio-server', 'wasm-server', 'agent', 'mcp-app'];
  if (!validTypes.includes(options.type)) {
    throw new Error(`Invalid project type. Must be one of: ${validTypes.join(', ')}`);
  }

  console.log(chalk.cyan('\n🚀 Creating PolyMCP project...\n'));
  console.log(chalk.gray(`   Name: ${projectName}`));
  console.log(chalk.gray(`   Type: ${options.type}`));
  if (options.withAuth) console.log(chalk.gray('   Auth: ✓'));
  if (options.withExamples) console.log(chalk.gray('   Examples: ✓'));
  console.log();

  // Create project directory
  fs.mkdirSync(projectPath, { recursive: true });

  // Generate based on type
  const spinner = ora('Generating project files...').start();

  try {
    switch (options.type) {
      case 'basic':
        await generateBasicProject(projectPath, options);
        break;
      case 'http-server':
        await generateHttpServer(projectPath, options);
        break;
      case 'stdio-server':
        await generateStdioServer(projectPath, options);
        break;
      case 'wasm-server':
        await generateWasmServer(projectPath, options);
        break;
      case 'agent':
        await generateAgentProject(projectPath, options);
        break;
      case 'mcp-app':
        await generateMCPAppProject(projectPath);
        break;
    }

    spinner.succeed('Project files generated');
  } catch (error: any) {
    spinner.fail('Failed to generate project');
    throw error;
  }

  // Install dependencies
  if (!options.skipInstall) {
    const installSpinner = ora('Installing dependencies...').start();
    
    try {
      execSync('npm install', {
        cwd: projectPath,
        stdio: 'pipe',
      });
      installSpinner.succeed('Dependencies installed');
    } catch (error: any) {
      installSpinner.fail('Failed to install dependencies');
      console.log(chalk.yellow('\n⚠️  You can install manually with: npm install\n'));
    }
  }

  // Show next steps
  showNextSteps(projectName, options.type);
}

/**
 * Generate basic HTTP server project
 */
async function generateBasicProject(projectPath: string, options: InitOptions): Promise<void> {
  const projectName = path.basename(projectPath);

  // 1. Package.json
  const packageJson: any = {
    name: projectName,
    version: '1.0.0',
    type: 'module',
    description: 'PolyMCP server project',
    main: 'dist/server.js',
    scripts: {
      build: 'tsc',
      dev: 'tsx src/server.ts',
      start: 'node dist/server.js',
      test: 'jest',
    },
    dependencies: {
      polymcp: '^1.3.6',
      express: '^4.18.0',
      zod: '^3.22.0',
      dotenv: '^16.0.0',
    },
    devDependencies: {
      '@types/node': '^20.0.0',
      '@types/express': '^4.17.0',
      typescript: '^5.0.0',
      tsx: '^4.0.0',
      jest: '^29.0.0',
      '@types/jest': '^29.0.0',
    },
  };

  if (options.withAuth) {
    packageJson.dependencies = {
      ...packageJson.dependencies,
      jsonwebtoken: '^9.0.0',
      bcryptjs: '^2.4.3',
    };
    (packageJson.devDependencies as any)['@types/jsonwebtoken'] = '^9.0.0';
  }

  fs.writeJsonSync(
    path.join(projectPath, 'package.json'),
    packageJson,
    { spaces: 2 }
  );

  // 2. tsconfig.json
  const tsconfig = {
    compilerOptions: {
      target: 'ES2020',
      module: 'ESNext',
      lib: ['ES2020'],
      outDir: './dist',
      rootDir: './src',
      strict: true,
      esModuleInterop: true,
      skipLibCheck: true,
      moduleResolution: 'node',
      resolveJsonModule: true,
      declaration: true,
    },
    include: ['src/**/*'],
    exclude: ['node_modules', 'dist'],
  };

  fs.writeJsonSync(
    path.join(projectPath, 'tsconfig.json'),
    tsconfig,
    { spaces: 2 }
  );

  // 3. Create src directory
  const srcDir = path.join(projectPath, 'src');
  fs.mkdirSync(srcDir);

  // 4. Server file
  let serverCode = `import { exposeToolsHttp } from 'polymcp';
import express from 'express';
import dotenv from 'dotenv';
${options.withExamples ? "import { greet, calculate } from './tools/example';" : ''}

dotenv.config();

const PORT = process.env.PORT || 8000;

${options.withExamples ? 'const tools = [greet, calculate];' : 'const tools = [];'}

const app = exposeToolsHttp(tools, {
  title: '${projectName}',
  description: 'MCP server created with PolyMCP',
  version: '1.0.0',
  verbose: true,
});

app.listen(PORT, () => {
  console.log(\`\\n🚀 Server running at http://localhost:\${PORT}\`);
  console.log(\`📚 Docs: http://localhost:\${PORT}/docs\`);
  console.log(\`🔧 Tools: http://localhost:\${PORT}/mcp/list_tools\\n\`);
});
`;

  if (options.withAuth) {
    serverCode = `import { exposeToolsHttp } from 'polymcp';
import { JWTAuthenticator, addAuthToMCP } from 'polymcp/auth';
import express from 'express';
import dotenv from 'dotenv';
${options.withExamples ? "import { greet, calculate } from './tools/example';" : ''}

dotenv.config();

const PORT = process.env.PORT || 8000;
const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-in-production';

${options.withExamples ? 'const tools = [greet, calculate];' : 'const tools = [];'}

let app = exposeToolsHttp(tools, {
  title: '${projectName}',
  description: 'MCP server with authentication',
  version: '1.0.0',
  verbose: true,
});

// Add authentication
const auth = new JWTAuthenticator(JWT_SECRET);
app = addAuthToMCP(app, auth);

app.listen(PORT, () => {
  console.log(\`\\n🚀 Server running at http://localhost:\${PORT}\`);
  console.log(\`🔒 Authentication enabled\`);
  console.log(\`📚 Docs: http://localhost:\${PORT}/docs\\n\`);
});
`;
  }

  fs.writeFileSync(path.join(srcDir, 'server.ts'), serverCode);

  // 5. Example tools (if requested)
  if (options.withExamples) {
    const toolsDir = path.join(srcDir, 'tools');
    fs.mkdirSync(toolsDir);

    const exampleTools = `import { tool } from 'polymcp';
import { z } from 'zod';

/**
 * Greet someone by name
 */
export const greet = tool({
  name: 'greet',
  description: 'Greet someone by name',
  parameters: z.object({
    name: z.string().describe('Name of the person to greet'),
  }),
  execute: async ({ name }) => {
    return \`Hello, \${name}! Welcome to PolyMCP.\`;
  },
});

/**
 * Perform arithmetic operations
 */
export const calculate = tool({
  name: 'calculate',
  description: 'Perform basic arithmetic operations',
  parameters: z.object({
    operation: z.enum(['add', 'subtract', 'multiply', 'divide'])
      .describe('Operation to perform'),
    a: z.number().describe('First number'),
    b: z.number().describe('Second number'),
  }),
  execute: async ({ operation, a, b }) => {
    let result: number;
    
    switch (operation) {
      case 'add':
        result = a + b;
        break;
      case 'subtract':
        result = a - b;
        break;
      case 'multiply':
        result = a * b;
        break;
      case 'divide':
        if (b === 0) {
          throw new Error('Division by zero');
        }
        result = a / b;
        break;
    }
    
    return \`\${a} \${operation} \${b} = \${result}\`;
  },
});
`;

    fs.writeFileSync(path.join(toolsDir, 'example.ts'), exampleTools);
  }

  // 6. .env template
  let envTemplate = `# Server Configuration
PORT=8000

# Environment
NODE_ENV=development
`;

  if (options.withAuth) {
    envTemplate += `
# Authentication
JWT_SECRET=change-this-in-production
JWT_EXPIRES_IN=24h
`;
  }

  fs.writeFileSync(path.join(projectPath, '.env.template'), envTemplate);
  fs.writeFileSync(path.join(projectPath, '.env'), envTemplate);

  // 7. .gitignore
  const gitignore = `node_modules/
dist/
*.log
.env
.DS_Store
coverage/
`;
  fs.writeFileSync(path.join(projectPath, '.gitignore'), gitignore);

  // 8. README.md
  const readme = `# ${projectName}

PolyMCP server project created with \`polymcp init\`

## Setup

\`\`\`bash
npm install
cp .env.template .env
# Edit .env with your configuration
\`\`\`

## Development

\`\`\`bash
npm run dev
\`\`\`

## Build

\`\`\`bash
npm run build
\`\`\`

## Production

\`\`\`bash
npm start
\`\`\`

## Test

\`\`\`bash
# List tools
curl http://localhost:8000/mcp/list_tools

# Invoke tool
curl -X POST http://localhost:8000/mcp/invoke \\
  -H "Content-Type: application/json" \\
  -d '{"tool": "greet", "parameters": {"name": "World"}}'
\`\`\`

## Adding Tools

1. Create new tool functions in \`src/tools/\`
2. Import in \`src/server.ts\`
3. Add to tools array
4. Restart server

## Documentation

- [PolyMCP Docs](https://github.com/yourusername/polymcp)
- [MCP Protocol](https://modelcontextprotocol.io)
`;

  fs.writeFileSync(path.join(projectPath, 'README.md'), readme);
}

/**
 * Generate HTTP server project (extended basic with config)
 */
async function generateHttpServer(projectPath: string, options: InitOptions): Promise<void> {
  await generateBasicProject(projectPath, options);

  // Add advanced HTTP config
  const configJson = {
    server: {
      host: '0.0.0.0',
      port: 8000,
      cors: {
        enabled: true,
        origins: ['*'],
      },
      rateLimit: {
        windowMs: 60000,
        max: 100,
      },
    },
    logging: {
      level: 'info',
      format: 'json',
    },
  };

  fs.writeJsonSync(
    path.join(projectPath, 'config.json'),
    configJson,
    { spaces: 2 }
  );
}

/**
 * Generate stdio server project (for npm publishing)
 */
async function generateStdioServer(projectPath: string, _options: InitOptions): Promise<void> {
  const projectName = path.basename(projectPath);

  // 1. Package.json
  const packageJson = {
    name: projectName,
    version: '1.0.0',
    type: 'module',
    description: 'MCP stdio server',
    main: 'dist/index.js',
    bin: {
      [projectName]: './dist/index.js',
    },
    scripts: {
      build: 'tsc',
      dev: 'tsx src/index.ts',
      prepublishOnly: 'npm run build',
    },
    dependencies: {
      polymcp: '^1.3.6',
      zod: '^3.22.0',
    },
    devDependencies: {
      '@types/node': '^20.0.0',
      typescript: '^5.0.0',
      tsx: '^4.0.0',
    },
    files: ['dist/', 'README.md', 'LICENSE'],
    keywords: ['mcp', 'mcp-server', 'model-context-protocol'],
  };

  fs.writeJsonSync(
    path.join(projectPath, 'package.json'),
    packageJson,
    { spaces: 2 }
  );

  // 2. tsconfig.json
  const tsconfig = {
    compilerOptions: {
      target: 'ES2020',
      module: 'ESNext',
      lib: ['ES2020'],
      outDir: './dist',
      rootDir: './src',
      strict: true,
      esModuleInterop: true,
      skipLibCheck: true,
      moduleResolution: 'node',
      declaration: true,
    },
    include: ['src/**/*'],
  };

  fs.writeJsonSync(
    path.join(projectPath, 'tsconfig.json'),
    tsconfig,
    { spaces: 2 }
  );

  // 3. Create src directory
  const srcDir = path.join(projectPath, 'src');
  fs.mkdirSync(srcDir);

  // 4. Main file with shebang
  const indexCode = `#!/usr/bin/env node
import { tool, exposeToolsStdio } from 'polymcp';
import { z } from 'zod';

// Define your tools
const greet = tool({
  name: 'greet',
  description: 'Greet someone by name',
  parameters: z.object({
    name: z.string().describe('Name to greet'),
  }),
  execute: async ({ name }) => {
    return \`Hello, \${name}! Welcome to PolyMCP.\`;
  },
});

const calculate = tool({
  name: 'calculate',
  description: 'Perform arithmetic operations',
  parameters: z.object({
    operation: z.enum(['add', 'subtract', 'multiply', 'divide']),
    a: z.number(),
    b: z.number(),
  }),
  execute: async ({ operation, a, b }) => {
    switch (operation) {
      case 'add': return \`\${a + b}\`;
      case 'subtract': return \`\${a - b}\`;
      case 'multiply': return \`\${a * b}\`;
      case 'divide': 
        if (b === 0) throw new Error('Division by zero');
        return \`\${a / b}\`;
    }
  },
});

// Create and run stdio server
const server = exposeToolsStdio([greet, calculate], {
  name: '${projectName}',
  version: '1.0.0',
  verbose: false,
});

server.run();
`;

  fs.writeFileSync(path.join(srcDir, 'index.ts'), indexCode);

  // 5. README for npm
  const readme = `# ${projectName}

MCP stdio server created with PolyMCP

## Installation

\`\`\`bash
npm install -g ${projectName}
\`\`\`

Or use with npx:

\`\`\`bash
npx ${projectName}
\`\`\`

## Usage

### With Claude Desktop

Add to your Claude Desktop configuration:

\`\`\`json
{
  "mcpServers": {
    "${projectName}": {
      "command": "npx",
      "args": ["${projectName}"]
    }
  }
}
\`\`\`

### Programmatically

\`\`\`typescript
import { MCPStdioClient } from 'polymcp';

const client = new MCPStdioClient({
  command: 'npx ${projectName}'
});

await client.connect();
const tools = await client.listTools();
const result = await client.callTool('greet', { name: 'World' });
await client.disconnect();
\`\`\`

## Development

\`\`\`bash
npm install
npm run dev
\`\`\`

## Publishing

\`\`\`bash
npm login
npm publish
\`\`\`

## License

MIT
`;

  fs.writeFileSync(path.join(projectPath, 'README.md'), readme);

  // 6. LICENSE
  const license = `MIT License

Copyright (c) ${new Date().getFullYear()}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
`;

  fs.writeFileSync(path.join(projectPath, 'LICENSE'), license);

  // 7. .gitignore
  fs.writeFileSync(
    path.join(projectPath, '.gitignore'),
    'node_modules/\ndist/\n*.log\n'
  );
}

/**
 * Generate WASM server project (for edge/browser)
 */
async function generateWasmServer(projectPath: string, options: InitOptions): Promise<void> {
  const projectName = path.basename(projectPath);

  // Similar to stdio but with different setup
  await generateStdioServer(projectPath, options);

  // Add WASM-specific files
  const readmeAddition = `
## Browser Usage

\`\`\`html
<script type="module">
  import { WASMMCPServer } from './${projectName}/loader.js';
  
  const server = new WASMMCPServer();
  await server.initialize();
  
  const tools = await server.listTools();
  const result = await server.callTool('greet', { name: 'Browser' });
</script>
\`\`\`
`;

  const readme = fs.readFileSync(path.join(projectPath, 'README.md'), 'utf-8');
  fs.writeFileSync(
    path.join(projectPath, 'README.md'),
    readme + readmeAddition
  );
}

/**
 * Generate agent project
 */
async function generateAgentProject(projectPath: string, _options: InitOptions): Promise<void> {
  const projectName = path.basename(projectPath);

  // Package.json
  const packageJson = {
    name: projectName,
    version: '1.0.0',
    type: 'module',
    description: 'PolyMCP agent project',
    main: 'dist/agent.js',
    scripts: {
      build: 'tsc',
      dev: 'tsx src/agent.ts',
      start: 'node dist/agent.js',
    },
    dependencies: {
      polymcp: '^1.3.6',
      dotenv: '^16.0.0',
      openai: '^4.0.0',
      '@anthropic-ai/sdk': '^0.24.0',
    },
    devDependencies: {
      '@types/node': '^20.0.0',
      typescript: '^5.0.0',
      tsx: '^4.0.0',
    },
  };

  fs.writeJsonSync(
    path.join(projectPath, 'package.json'),
    packageJson,
    { spaces: 2 }
  );

  // tsconfig.json
  const tsconfig = {
    compilerOptions: {
      target: 'ES2020',
      module: 'ESNext',
      lib: ['ES2020'],
      outDir: './dist',
      rootDir: './src',
      strict: true,
      esModuleInterop: true,
      skipLibCheck: true,
      moduleResolution: 'node',
    },
    include: ['src/**/*'],
  };

  fs.writeJsonSync(
    path.join(projectPath, 'tsconfig.json'),
    tsconfig,
    { spaces: 2 }
  );

  // Create src directory
  const srcDir = path.join(projectPath, 'src');
  fs.mkdirSync(srcDir);

  // Agent code
  const agentCode = `import { UnifiedAgent, OpenAIProvider, AnthropicProvider } from 'polymcp';
import dotenv from 'dotenv';
import * as readline from 'readline';

dotenv.config();

async function main() {
  // Create LLM provider
  const llmProvider = process.env.OPENAI_API_KEY
    ? new OpenAIProvider({ apiKey: process.env.OPENAI_API_KEY })
    : new AnthropicProvider({ apiKey: process.env.ANTHROPIC_API_KEY! });

  // MCP servers to connect to
  const mcpServers = process.env.MCP_SERVERS
    ? process.env.MCP_SERVERS.split(',').map(s => s.trim())
    : [];

  if (mcpServers.length === 0) {
    console.error('❌ No MCP servers configured in .env');
    console.error('   Add MCP_SERVERS=http://localhost:8000/mcp');
    process.exit(1);
  }

  console.log('\\n🤖 PolyMCP Agent');
  console.log(\`   Provider: \${llmProvider.constructor.name}\`);
  console.log(\`   Servers: \${mcpServers.length}\\n\`);

  // Create agent
  const agent = new UnifiedAgent({
    llmProvider,
    mcpServers,
    verbose: true,
  });

  // Interactive loop
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log('Agent ready! (type "quit" to exit)\\n');

  const question = (prompt: string): Promise<string> => {
    return new Promise((resolve) => {
      rl.question(prompt, resolve);
    });
  };

  while (true) {
    try {
      const input = await question('You: ');
      
      if (input.toLowerCase().trim() === 'quit') {
        break;
      }

      if (!input.trim()) {
        continue;
      }

      const response = await agent.run(input);
      console.log(\`\\nAgent: \${response}\\n\`);

    } catch (error: any) {
      console.error(\`\\n❌ Error: \${error.message}\\n\`);
    }
  }

  rl.close();
  console.log('\\n👋 Goodbye!\\n');
}

main().catch(console.error);
`;

  fs.writeFileSync(path.join(srcDir, 'agent.ts'), agentCode);

  // .env template
  const envTemplate = `# LLM Provider (choose one)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...

# MCP Servers (comma-separated)
MCP_SERVERS=http://localhost:8000/mcp

# Agent Configuration
AGENT_VERBOSE=true
AGENT_MAX_STEPS=10
`;

  fs.writeFileSync(path.join(projectPath, '.env.template'), envTemplate);
  fs.writeFileSync(path.join(projectPath, '.env'), envTemplate);

  // README
  const readme = `# ${projectName}

PolyMCP agent project

## Setup

\`\`\`bash
npm install
cp .env.template .env
# Edit .env with your API keys and MCP servers
\`\`\`

## Run

\`\`\`bash
npm run dev
\`\`\`

## Configuration

Edit \`.env\`:

- Add your LLM API key (OpenAI or Anthropic)
- Configure MCP servers (comma-separated URLs)
- Set agent parameters

## Usage

The agent will connect to configured MCP servers and use their tools
to accomplish tasks. Just type your requests in natural language.

Example:
\`\`\`
You: Search for recent news about AI
Agent: [Uses web search tool to find news...]
\`\`\`
`;

  fs.writeFileSync(path.join(projectPath, 'README.md'), readme);

  // .gitignore
  fs.writeFileSync(
    path.join(projectPath, '.gitignore'),
    'node_modules/\ndist/\n.env\n*.log\n'
  );
}

/**
 * Generate MCP App project (UI + MCP tools + local live server)
 */
async function generateMCPAppProject(projectPath: string): Promise<void> {
  const projectName = path.basename(projectPath);

  const packageJson = {
    name: projectName,
    version: '1.0.0',
    type: 'module',
    description: 'PolyMCP MCP App project (UI + tools)',
    main: 'dist/server.js',
    scripts: {
      build: 'tsc',
      dev: 'tsx src/server.ts',
      start: 'node dist/server.js',
    },
    dependencies: {
      polymcp: '^1.3.6',
      express: '^4.18.0',
    },
    devDependencies: {
      '@types/node': '^20.0.0',
      '@types/express': '^4.17.0',
      typescript: '^5.0.0',
      tsx: '^4.0.0',
    },
  };

  fs.writeJsonSync(path.join(projectPath, 'package.json'), packageJson, { spaces: 2 });

  const tsconfig = {
    compilerOptions: {
      target: 'ES2020',
      module: 'ESNext',
      lib: ['ES2020'],
      outDir: './dist',
      rootDir: './src',
      strict: true,
      esModuleInterop: true,
      skipLibCheck: true,
      moduleResolution: 'node',
      resolveJsonModule: true,
      declaration: true,
    },
    include: ['src/**/*'],
    exclude: ['node_modules', 'dist'],
  };

  fs.writeJsonSync(path.join(projectPath, 'tsconfig.json'), tsconfig, { spaces: 2 });

  const srcDir = path.join(projectPath, 'src');
  fs.mkdirSync(srcDir);

  const serverCode = `import express from 'express';
import { MCPAppsBuilder, MCPAppsServer } from 'polymcp';

const PORT = Number(process.env.PORT || 3100);

function createApp() {
  const builder = new MCPAppsBuilder();
  let clicks = 0;

  return builder
    .createApp({
      id: 'hello-app',
      name: 'Hello App',
      description: 'My first MCP App with UI and tools',
    })
    .addTool({
      name: 'hello_user',
      description: 'Return a greeting',
      inputSchema: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'User name' },
        },
      },
      handler: async (params: any) => {
        const name = params?.name || 'friend';
        return { message: \`Hello, \${name}!\` };
      },
    })
    .addTool({
      name: 'increment_counter',
      description: 'Increment local counter',
      inputSchema: { type: 'object', properties: {} },
      handler: async () => {
        clicks += 1;
        return { clicks };
      },
    })
    .addHTMLResource({
      name: 'Main UI',
      html: \`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Hello MCP App</title>
    <style>
      body { font-family: Arial, sans-serif; max-width: 760px; margin: 0 auto; padding: 24px; }
      .row { display: flex; gap: 8px; margin: 10px 0; }
      input { padding: 8px; flex: 1; }
      button { padding: 8px 12px; cursor: pointer; }
      #out { white-space: pre-wrap; margin-top: 12px; background: #f5f7fb; border-radius: 8px; padding: 10px; }
    </style>
  </head>
  <body>
    <h2>Hello MCP App</h2>
    <div class="row">
      <input id="name" placeholder="Your name" />
      <button onclick="callHello()">Say Hello</button>
      <button onclick="callCounter()">Counter</button>
    </div>
    <div id="out">Ready.</div>
    <script>
      async function call(tool, params) {
        const r = await fetch('/tools/' + tool, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params || {})
        });
        const data = await r.json();
        document.getElementById('out').textContent = JSON.stringify(data, null, 2);
      }
      function callHello() {
        const name = document.getElementById('name').value || 'friend';
        call('hello_user', { name });
      }
      function callCounter() {
        call('increment_counter', {});
      }
    </script>
  </body>
</html>\`,
    })
    .build();
}

async function main() {
  const mcp = new MCPAppsServer({ port: PORT, enableCORS: true });
  const appDef = createApp();
  mcp.registerApp(appDef);
  await mcp.start();

  const uiUri = appDef.resources[0]?.uri;
  const encodedUi = encodeURIComponent(uiUri);

  const app = express();
  app.use(express.json({ limit: '1mb' }));

  app.get('/', (_req, res) => {
    res.type('html').send(\`
      <h3>\${appDef.name}</h3>
      <ul>
        <li><a href="/resources/\${encodedUi}">Open UI</a></li>
        <li><a href="/list_tools">List tools</a></li>
        <li><a href="/list_resources">List resources</a></li>
      </ul>\`);
  });

  app.get('/list_tools', async (_req, res) => {
    const r = await mcp.handleRequest('GET', '/list_tools');
    res.status(r.status).set(r.headers).json(r.body);
  });

  app.get('/list_resources', async (_req, res) => {
    const r = await mcp.handleRequest('GET', '/list_resources');
    res.status(r.status).set(r.headers).json(r.body);
  });

  app.get('/resources/*', async (req, res) => {
    const suffix = req.originalUrl.replace('/resources/', '');
    const r = await mcp.handleRequest('GET', '/resources/' + suffix);
    res.status(r.status).set(r.headers).send(r.body);
  });

  app.post('/tools/:toolName', async (req, res) => {
    const r = await mcp.handleRequest('POST', '/tools/' + req.params.toolName, req.body);
    res.status(r.status).set(r.headers).json(r.body);
  });

  app.listen(PORT, () => {
    console.log(\`Live MCP App running at http://localhost:\${PORT}\`);
    console.log(\`Open UI: http://localhost:\${PORT}/resources/\${encodedUi}\`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
`;

  fs.writeFileSync(path.join(srcDir, 'server.ts'), serverCode);

  const readme = `# ${projectName}

MCP App project created with \`polymcp init --type mcp-app\`.

## Run

\`\`\`bash
npm install
npm run dev
\`\`\`

Then open:

- \`http://localhost:3100/\`
- \`http://localhost:3100/list_tools\`
- \`http://localhost:3100/list_resources\`

This project gives you:
- a local MCP Apps server
- a browsable UI resource
- MCP tool endpoints for orchestration from GPT/agents
`;

  fs.writeFileSync(path.join(projectPath, 'README.md'), readme);
  fs.writeFileSync(path.join(projectPath, '.gitignore'), 'node_modules/\ndist/\n*.log\n');
}

/**
 * Validate project name
 */
function isValidProjectName(name: string): boolean {
  return /^[a-z0-9-]+$/.test(name);
}

/**
 * Show next steps after project creation
 */
function showNextSteps(projectName: string, projectType: ProjectType): void {
  console.log(chalk.green('\n✅ Project created successfully!\n'));
  console.log(chalk.cyan('📖 Next steps:\n'));
  console.log(chalk.gray(`   cd ${projectName}`));

  switch (projectType) {
    case 'basic':
    case 'http-server':
      console.log(chalk.gray('   npm run dev'));
      console.log(chalk.gray('\n   → Server: http://localhost:8000'));
      break;

    case 'stdio-server':
      console.log(chalk.gray('   npm run dev'));
      console.log(chalk.gray('\n   Or publish to npm:'));
      console.log(chalk.gray('   npm publish'));
      break;

    case 'wasm-server':
      console.log(chalk.gray('   npm run build'));
      console.log(chalk.gray('   cd dist && npx serve'));
      break;

    case 'agent':
      console.log(chalk.gray('   # Edit .env with your API keys'));
      console.log(chalk.gray('   npm run dev'));
      break;

    case 'mcp-app':
      console.log(chalk.gray('   npm run dev'));
      console.log(chalk.gray('\n   → Open: http://localhost:3100/'));
      break;
  }

  console.log(chalk.gray('\n📚 Read README.md for details\n'));
}
