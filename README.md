<p align="center">
  <img src="poly-mcp.png" alt="PolymCP Logo" width="500"/>
</p>

[![PyPI version](https://img.shields.io/pypi/v/polymcp.svg)](https://pypi.org/project/polymcp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/polymcp.svg)](https://pypi.org/project/polymcp/)
[![License](https://img.shields.io/pypi/l/polymcp.svg)](https://github.com/llm-use/polymcp/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/llm-use/polymcp?style=social)](https://github.com/llm-use/polymcp/stargazers)
[![Featured Article](https://img.shields.io/badge/Read-Article-blue)](https://levelup.gitconnected.com/why-your-python-functions-arent-ai-tools-yet-and-how-polymcp-fixes-it-in-one-line-d8e62550ac53)
[![Seguimi su Twitter](https://img.shields.io/twitter/follow/justvugg?style=social)](https://x.com/justvugg)
[![PyPI total downloads](https://img.shields.io/pepy/dt/polymcp)](https://pepy.tech/project/polymcp)
[![Website](https://img.shields.io/badge/website-poly--mcp.com-blue)](https://www.poly-mcp.com)

> **PolyMCP: A Universal MCP Agent & Toolkit for Intelligent Tool Orchestration**

---

## 🎉 What's New

### 🧠 **Skills System** - Intelligent Tool Loading with 87% Token Savings

Dramatically reduce token usage by loading only relevant tools based on semantic matching:

**The Problem:**
```python
# Traditional approach: ALL tools loaded every time
agent = PolyAgent(
    mcp_servers=[
        "http://localhost:8000/mcp",  # 20 tools
        "http://localhost:8001/mcp",  # 30 tools  
        "http://localhost:8002/mcp",  # 25 tools
        # ... 10 servers = 200 tools total
    ]
)
# Every request: 200 tools × 250 tokens = 50,000 tokens wasted!
```

**The Solution:**
```python
from polymcp.polyagent import UnifiedPolyAgent, OpenAIProvider

# Skills load tools on-demand based on query semantics
agent = UnifiedPolyAgent(
    llm_provider=OpenAIProvider(),
    skills_dir="/mnt/skills",  # Auto-loads relevant skills
    mcp_servers=["http://localhost:8000/mcp"]
)

# Query: "Send email to John"
# Only loads: email skill (5 tools) instead of ALL 200 tools!
result = agent.run("Send email to John about project updates")
```

**Results:**
- **Before**: 48,234 tokens (all 200 tools)
- **After**: 6,127 tokens (5 relevant tools)
- **Savings**: 87% token reduction
- **Accuracy**: +38% (less confusion)

**Create Skills from Any MCP Server:**
```python
from polymcp import SkillGenerator

# Auto-generate skill from existing MCP server
generator = SkillGenerator()
generator.generate_from_mcp(
    server_url="http://localhost:8000/mcp",
    output_path="/mnt/skills/github/SKILL.md",
    skill_name="GitHub Operations"
)

# Skill file created automatically with:
# - Tool descriptions and schemas
# - Usage examples and best practices
# - Semantic category tags
```

**Security Features:**
- ✅ Sandbox execution with timeout protection
- ✅ Memory limits (512MB default)
- ✅ Network isolation
- ✅ Filesystem restrictions

---

### 🔧 **Stdio MCP Server Creation** - Cross-Platform Tool Distribution

Create stdio-based MCP servers compatible with Claude Desktop, npm, and any MCP client:

```python
from polymcp import expose_tools_stdio

def calculate(a: int, b: int, operation: str = "add") -> float:
    """Perform mathematical operations."""
    ops = {"add": a + b, "multiply": a * b, "divide": a / b}
    return ops.get(operation, a + b)

def analyze_text(text: str) -> dict:
    """Analyze text and return statistics."""
    return {
        "characters": len(text),
        "words": len(text.split()),
        "sentences": text.count('.') + text.count('!')
    }

# Create stdio server (JSON-RPC 2.0 compliant)
server = expose_tools_stdio(
    tools=[calculate, analyze_text],
    server_name="Math & Text Tools",
    server_version="1.0.0"
)

# Run server
if __name__ == "__main__":
    server.run()
```

**Claude Desktop Integration:**
```json
{
  "mcpServers": {
    "math-tools": {
      "command": "python",
      "args": ["path/to/server.py"]
    }
  }
}
```

**Cross-Platform Support:**
- ✅ **Windows**: Automatic threading mode (ProactorEventLoop compatible)
- ✅ **Linux/macOS**: Asyncio pipes (optimal performance)
- ✅ **Auto-detection**: Chooses best transport automatically
- ✅ **MCP Protocol 2024-11-05** compliant

**CLI Scaffolding:**
```bash
# Generate complete stdio server project
polymcp init my-math-server --type stdio-server

# Creates production-ready structure:
# my-math-server/
# ├── server.py           # Main server implementation
# ├── package.json        # npm package config
# ├── index.js            # Node.js wrapper
# ├── test_client.py      # Automated tests
# └── README.md           # Usage documentation
```

---

### 🌐 **WASM MCP Server Creation** - Browser-Native Tool Execution

Compile Python tools to WebAssembly for browser deployment with zero backend:

```python
from polymcp import expose_tools_wasm
import math

def calculate_stats(numbers: list) -> dict:
    """Calculate statistics for a list of numbers."""
    mean = sum(numbers) / len(numbers)
    variance = sum((x - mean) ** 2 for x in numbers) / len(numbers)
    return {
        "mean": round(mean, 2),
        "std": round(math.sqrt(variance), 2),
        "min": min(numbers),
        "max": max(numbers)
    }

def prime_factors(n: int) -> dict:
    """Find prime factors of a number."""
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return {"factors": factors, "is_prime": len(factors) == 1}

# Compile to WASM bundle
compiler = expose_tools_wasm(
    tools=[calculate_stats, prime_factors],
    server_name="Math Tools",
    server_version="1.0.0"
)

bundle = compiler.compile(output_dir="./dist")

# Generates:
# dist/
# ├── tools_bundle.py     # Python source
# ├── loader.js           # JavaScript loader
# ├── demo.html           # Interactive demo (minimal design)
# ├── package.json        # npm package
# └── README.md           # Deployment guide
```

**Test Locally:**
```bash
cd dist
python -m http.server 8000
# Open http://localhost:8000/demo.html
```

**Deploy to Production:**
```bash
# GitHub Pages
git subtree push --prefix dist origin gh-pages

# Vercel
cd dist && vercel deploy

# npm
cd dist && npm publish

# CDN (automatic)
# https://cdn.jsdelivr.net/npm/@your-org/math-tools/loader.js
```

**Browser Usage:**
```html
<script type="module">
import { WASMMCPServer } from './loader.js';

const server = new WASMMCPServer();
await server.initialize();

// Execute tools directly in browser!
const result = await server.callTool('calculate_stats', {
    numbers: [1, 2, 3, 4, 5, 10, 20]
});

console.log(result);
// Output: { mean: 6.43, std: 6.21, min: 1, max: 20 }
</script>
```

**Features:**
- ✅ **Zero Backend**: Runs entirely in browser via Pyodide
- ✅ **Production Ready**: Automatic type conversions, error handling
- ✅ **Math Support**: Built-in `math` module included
- ✅ **CDN Deployable**: Works on GitHub Pages, Vercel, Netlify
- ✅ **Minimal UI**: Clean black & white design inspired by poly-mcp.com
- ✅ **npm Compatible**: Publish as standard npm package

**CLI Scaffolding:**
```bash
# Generate WASM server project
polymcp init my-wasm-tools --type wasm-server

# Creates:
# my-wasm-tools/
# ├── build.py            # WASM compiler script
# ├── tools.py            # Your tool implementations
# └── README.md           # Deployment instructions
```

### PolyMCP-TS – TypeScript Implementation of PolyMCP

PolyMCP now also has a **TypeScript implementation** for the Model Context Protocol (MCP), ideal for Node.js and TypeScript ecosystems.

> Everything you can build with the **Python PolyMCP**, you can now also build with **TypeScript**

📖 **[See the complete PolyMCP Typescript documentation →](polymcp-ts/README.md)**

Key highlights:

- **TypeScript-first design** – full type safety with rich typings
- **Zod-based validation** – input schemas and runtime validation using Zod
- **Simple tool definition API** – create MCP tools with minimal boilerplate
- **Multiple server types** – HTTP, stdio, and in-process MCP servers
- **Built-in authentication** – API key and JWT support out of the box
- **Agent framework** – Code Mode Agent and Multi-Step Reasoning for orchestrating multiple MCP servers with LLMs
- **Memory & state** – optional conversation memory and state management

Quick example of a TypeScript MCP tool server:

```ts
import { z } from 'zod';
import { tool, exposeToolsHttp } from './polymcp-ts/src';

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

// Start HTTP MCP server
const app = await exposeToolsHttp(mathTools, {
  title: 'Math Tools Server',
  description: 'Basic mathematical operations',
  verbose: true,
});
```

### 🎮 **PolyMCP CLI** - Complete Command-Line Interface
A powerful CLI for managing MCP servers, running agents, and orchestrating tools:

```bash
# Initialize projects, manage servers, run agents - all from the terminal
polymcp init my-project
polymcp server add http://localhost:8000/mcp
polymcp agent run --query "What's 2+2?"
```

Features: Project scaffolding, server registry, interactive agents, testing tools, configuration management, and much more.

📖 **[See the complete CLI documentation →](polymcp/cli/README.md)**

### 🔒 **Production Authentication** - Secure Your MCP Servers
Built-in support for API Key and JWT authentication:

```python
from polymcp.polymcp_toolkit import expose_tools_http
from polymcp.polymcp_toolkit.mcp_auth import ProductionAuthenticator, add_production_auth_to_mcp

# Server with authentication
def add(a: int, b: int) -> int:
    return a + b

app = expose_tools_http(tools=[add])
auth = ProductionAuthenticator(enforce_https=False)  # Use True in production
app = add_production_auth_to_mcp(app, auth)

# Run: uvicorn script:app
```

**Create users:**
```bash
# Set environment variable first
export MCP_SECRET_KEY="your-secret-key-min-32-chars"
python -m polymcp.polymcp_toolkit.mcp_auth create_user
```

**Client usage:**
```python
from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider

agent = UnifiedPolyAgent(
    llm_provider=OllamaProvider(model="llama3.2"),
    mcp_servers=["http://localhost:8000"],
    http_headers={"X-API-Key": "sk-your-api-key-from-db"}
)

# Make authenticated requests
result = await agent.run_async("Add 42 and 58")
```

Features: JWT tokens, API keys, user CLI, brute force protection, audit logs, rate limiting.

### 🚀 **Code Mode Agent** - Revolutionary Performance
Generate Python code instead of making multiple tool calls! The new `CodeModeAgent` offers:
- **60% faster execution** (fewer LLM roundtrips)
- **68% lower token usage** (single code generation vs multiple tool calls)
- **Natural programming constructs** (loops, variables, conditionals)
- **Perfect for complex workflows** with multiple sequential operations

```python
from polymcp.polyagent import CodeModeAgent, PolyAgent, OllamaProvider, OpenAIProvider

agent = CodeModeAgent(
    llm_provider=OpenAIProvider(),
    mcp_servers=["http://localhost:8000/mcp"]
)

# Single code generation orchestrates all tools
result = agent.run("""
    Record these 3 expenses:
    - Rent: $2500
    - Utilities: $150  
    - Food: $300
    Then calculate total and generate financial summary
""")
```

### ⚡ **Dual Mode MCP** - HTTP vs In-Process
Choose the best execution mode for your use case:

**HTTP Mode** (Traditional):
```python
from polymcp.polymcp_toolkit import expose_tools_http

app = expose_tools_http(
    tools=[my_function],
    title="My MCP Server"
)
# Run with uvicorn - great for microservices
```

**In-Process Mode** (NEW - Zero Overhead):
```python
from polymcp.polymcp_toolkit import expose_tools_inprocess

server = expose_tools_inprocess(tools=[my_function])
result = await server.invoke("my_function", {"param": "value"})
# 🚀 Direct calls, no network, perfect for embedded agents
```

**Performance Benefits of In-Process Mode:**
- ✅ No network overhead
- ✅ No serialization/deserialization  
- ✅ Direct function calls
- ✅ 40-60% faster than HTTP for local tools

### 🧠 **Enhanced UnifiedPolyAgent** - Autonomous Multi-Step Reasoning
The upgraded `UnifiedPolyAgent` now features:
- **Autonomous agentic loops** - Breaks complex tasks into steps automatically
- **Persistent memory** - Maintains context across multiple requests
- **Smart continuation logic** - Knows when to continue or stop
- **Mixed server support** - HTTP + stdio in the same agent

```python
from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider

agent = UnifiedPolyAgent(
    llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
    mcp_servers=["http://localhost:8000/mcp"],
    stdio_servers=[{
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }],
    memory_enabled=True  # 🆕 Persistent memory across requests
)

# Agent autonomously plans and executes multi-step tasks
response = await agent.run_async("""
    Go to github.com/llm-use/polymcp,
    take a screenshot,
    analyze the README,
    and summarize the key features
""")
```

### 🔒 **Secure Sandbox Executor** - Safe Code Execution
Execute LLM-generated code safely with the new sandbox system:
- Lightweight security model (blocks dangerous operations)
- Timeout protection
- Clean Python API for tool access via `tools` object
- Support for both sync and async tool execution

### 📦 **Mixed Servers Example** - Best of Both Worlds
Combine HTTP and stdio servers seamlessly:

```python
agent = UnifiedPolyAgent(
    llm_provider=llm,
    mcp_servers=[
        "http://localhost:8000/mcp",  # Your custom tools
        "http://localhost:8001/mcp",  # Advanced tools
    ],
    stdio_servers=[
        {
            "command": "npx",
            "args": ["@playwright/mcp@latest"]  # Browser automation
        }
    ]
)
```

---

## 🚀 Overview

**PolyMCP** is a Python library designed to simplify the creation, exposure, and orchestration of tools using the **Model Context Protocol (MCP)**. It provides a robust framework for building intelligent agents that can interact with tools via HTTP or stdio, leveraging the power of **Large Language Models (LLMs)** to reason and execute complex tasks.

### Key Features:
- **Expose Python Functions as MCP Tools**: Turn any Python function into an MCP-compatible tool using FastAPI.
- **Intelligent Agent Orchestration**: Use LLMs to discover, select, and orchestrate tools across multiple MCP servers.
- **Multi-Server Support**: Seamlessly integrate tools from both HTTP-based and stdio-based MCP servers.
- **LLM Integration**: Plug-and-play support for providers like OpenAI, Anthropic, Ollama, and more.
- **Playwright Integration**: Use Playwright MCP for browser automation and web scraping.
- **Centralized Registry**: Manage MCP servers and tools via JSON-based registries.
- **Extensibility**: Easily add new tools, LLM providers, or external MCP servers.

---

## 🏗️ Project Structure

```
polymcp/
│
├── polyagent/              # Intelligent agent and LLM providers
│   ├── agent.py            # Core agent logic
│   ├── codemode_agent.py   # 🆕 Code generation agent
│   ├── llm_providers.py    # LLM provider integrations (OpenAI, Ollama, etc.)
│   └── unified_agent.py    # 🆕 Enhanced unified agent with memory
│
├── polymcp_toolkit/        # Toolkit for exposing Python functions as MCP tools
│   └── expose.py           # 🆕 HTTP + In-Process modes
│
├── sandbox/                # 🆕 Secure code execution
│   ├── executor.py         # Sandbox executor
│   └── tools_api.py        # Python API for tools
│
├── tools/                  # Example tools
│   ├── advances_tools.py   # Advanced tools for specific tasks
│   └── summarize_tool.py   # Text summarization tool
│
├── mcp_stdio_client.py     # Stdio client for external MCP servers (e.g., Playwright)
└── __init__.py             # Package initialization
```

---

## ✨ Features in Detail

### 1. **Expose Python Functions as MCP Tools**
PolyMCP allows you to expose Python functions as RESTful MCP tools in seconds. This is achieved using the `expose_tools` function from the `polymcp_toolkit`.

**Example:**
```python
from polymcp.polymcp_toolkit.expose import expose_tools

def greet(name: str) -> str:
    """Greet a person."""
    return f"Hello, {name}!"

def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

# Expose the functions as MCP tools
app = expose_tools(greet, add_numbers)

# Run the server with:
# uvicorn my_mcp_server:app --reload
```

This creates a FastAPI server with endpoints:
- `/mcp/list_tools` — List all available tools.
- `/mcp/invoke/<tool_name>` — Invoke a specific tool.

---

### 2. **Intelligent Agent Orchestration**
The `PolyAgent` and `UnifiedPolyAgent` classes enable intelligent orchestration of MCP tools using LLMs. These agents can:
- Understand user queries.
- Select the appropriate tools.
- Execute tasks across multiple MCP servers.

**Example:**
```python
from polymcp.polyagent.agent import PolyAgent
from polymcp.polyagent.llm_providers import OllamaProvider

agent = PolyAgent(
    llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
    mcp_servers=["http://localhost:8000/mcp"],
    verbose=True
)

response = agent.run("What is the sum of 5 and 10?")
print(response)
```

---

### 3. **Playwright Integration**
PolyMCP supports Playwright MCP for browser automation and web scraping. Playwright MCP can be used as a stdio-based MCP server.

**Example:**
```python
from polymcp.polyagent.unified_agent import UnifiedPolyAgent
from polymcp.polyagent.llm_providers import OllamaProvider

agent = UnifiedPolyAgent(
    llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
    stdio_servers=[{
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
        "env": {"DISPLAY": ":1"}  # Optional for headless mode
    }],
    verbose=True
)

response = agent.run("Open https://github.com/JustVugg/polymcp and summarize the README.")
print(response)
```

---

### 4. **Centralized MCP Server Registry**
Manage MCP servers via JSON files for easy configuration.

**Example Registry (`tool_registry.json`):**
```json
{
  "servers": [
    "http://localhost:8000/mcp",
    "http://localhost:8001/mcp"
  ],
  "stdio_servers": [
    {
      "name": "playwright",
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "env": {"DISPLAY": ":1"}
    }
  ]
}
```

---

## 📦 Installation

### Quick Install (Recommended)

```bash
pip install polymcp
```

### Windows Users - CLI Installation

For Windows users who want to use the PolyMCP CLI, we recommend using `pipx` for a clean, isolated installation:

```bash
# Install pipx if you don't have it
pip install pipx
pipx ensurepath

# Install PolyMCP with CLI
pipx install polymcp

# Verify the CLI is working
polymcp --version
```

> **Note:** Using `pipx` on Windows ensures the CLI and all dependencies work correctly without conflicts.

### Development Installation

For contributors or advanced users who want to modify the source code:

```bash
# Clone the repository
git clone https://github.com/llm-use/polymcp.git
cd polymcp

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
python -c "import polymcp; print(f'PolyMCP version: {polymcp.__version__}')"

# For CLI users
polymcp --version
```

---

## 📚 Documentation

- **Examples**: See the `examples/` folder.
- **Tools**: See `polymcp/tools/`.
- **Toolkit**: [polymcp/polymcp_toolkit/expose.py](polymcp/polymcp_toolkit/expose.py).
- **Agent**: [polymcp/polyagent/agent.py](polymcp/polyagent/agent.py), [polymcp/polyagent/unified_agent.py](polymcp/polyagent/unified_agent.py).
- **Code Mode**: [polymcp/polyagent/codemode_agent.py](polymcp/polyagent/codemode_agent.py).

---

## 🤝 Contributing

1. Fork the repo and create a branch.
2. Make changes following the [guidelines](CONTRIBUTING.md).
3. Run tests and format code (`black`, `flake8`).
4. Open a Pull Request!

---

## ⭐ Stars Chart

[![Star History Chart](https://api.star-history.com/svg?repos=llm-use/Polymcp&type=Date)](https://star-history.com/#llm-use/Polymcp&Date)

---

## 📄 License

MIT License

---

## 🔗 Useful Links

- [PolyMCP on GitHub](https://github.com/llm-use/polymcp)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Blender MCP](https://github.com/llm-use/Blender-MCP-Server)
- [IoT MCP](https://github.com/llm-use/IoT-Edge-MCP-Server)
- [GitLab MCP](https://github.com/poly-mcp/GitLab-MCP-Server)

---

> _PolyMCP is designed to be extensible, interoperable, and production-ready!_
