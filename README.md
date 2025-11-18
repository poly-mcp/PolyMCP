<p align="center">
  <img src="logo.png" alt="PolymCP Logo" width="500"/>
</p>

[![PyPI version](https://img.shields.io/pypi/v/polymcp.svg)](https://pypi.org/project/polymcp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/polymcp.svg)](https://pypi.org/project/polymcp/)
[![License](https://img.shields.io/pypi/l/polymcp.svg)](https://github.com/llm-use/polymcp/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/llm-use/polymcp?style=social)](https://github.com/llm-use/polymcp/stargazers)
[![Featured Article](https://img.shields.io/badge/Read-Article-blue)](https://levelup.gitconnected.com/why-your-python-functions-arent-ai-tools-yet-and-how-polymcp-fixes-it-in-one-line-d8e62550ac53)
[![PyPI total downloads](https://img.shields.io/pepy/dt/polymcp)](https://pepy.tech/project/polymcp)

> **PolyMCP: A Universal MCP Agent & Toolkit for Intelligent Tool Orchestration**

---

## 🎉 What's New

### 🔒 **Production Authentication** - Secure Your MCP Servers
Built-in support for API Key and JWT authentication:

```python
#!/usr/bin/env python3
"""
Simple Auth Test - API Key & JWT with Ollama
Quick authentication example
"""

import os
import asyncio
import httpx
from dotenv import load_dotenv
load_dotenv()

from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider

async def test_api_key():
    """Test with API Key"""
    print("\n🔑 Test API Key Authentication")
    print("="*50)
    
    api_key = os.getenv("MCP_API_KEY_POLYMCP", "api_key")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    agent = UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"X-API-Key": api_key},
        verbose=True
    )
    
    await agent.start()
    result = await agent.run_async("Add 42 and 58", max_steps=3)
    await agent.stop()
    
    print(f"✅ Result: {result}")


async def test_jwt():
    """Test with JWT"""
    print("\n🎫 Test JWT Authentication")
    print("="*50)
    
    # Login to get JWT
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        token = response.json()["access_token"]
        print(f"✅ Logged in, token: {token[:30]}...")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    agent = UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"Authorization": f"Bearer {token}"},
        verbose=True
    )
    
    await agent.start()
    result = await agent.run_async("Multiply 7 by 9", max_steps=3)
    await agent.stop()
    
    print(f"✅ Result: {result}")


async def main():
    print("\n🔐 PolyMCP Auth Test with Ollama\n")
    
    # Check server
    try:
        async with httpx.AsyncClient() as client:
            await client.get("http://localhost:8000/mcp")
    except:
        print("❌ Server not running! Start with: python auth_server.py")
        return
    
    print("✅ Server is running\n")
    
    # Run tests
    await test_api_key()
    await test_jwt()
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
```

Features: JWT tokens, brute force protection, audit logs, rate limiting.

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

---

> _PolyMCP is designed to be extensible, interoperable, and production-ready!_
