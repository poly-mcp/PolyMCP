# PolyMCP

[![GitHub stars](https://img.shields.io/github/stars/JustVugg/polymcp?style=social)](https://github.com/JustVugg/polymcp/stargazers)

> **PolyMCP: A Universal MCP Agent & Toolkit for Intelligent Tool Orchestration**

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
│   ├── llm_providers.py    # LLM provider integrations (OpenAI, Ollama, etc.)
│   └── unified_agent.py    # Unified agent for multi-server orchestration
│
├── polymcp_toolkit/        # Toolkit for exposing Python functions as MCP tools
│   ├── expose.py           # Core logic for tool exposure via FastAPI
│
├── tools/                  # Example tools
│   ├── advances_tools.py   # Advanced tools for specific tasks
│   └── summarize_tool.py   # Text summarization tool
│
├── mcp_stdio_client.py     # Stdio client for external MCP servers (e.g., Playwright)
├── summarize_tool.py       # Example summarization tool
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

1. **Clone the repository**
   ```sh
   git clone https://github.com/JustVugg/polymcp.git
   cd polymcp
   ```

2. **Create a virtual environment**
   ```sh
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   pip install -e ".[dev]"
   ```

---

## 🧪 Testing

Run all tests:
```sh
pytest tests/ -v
```

---

## 📚 Documentation

- **Examples**: See the `examples/` folder.
- **Tools**: See `polymcp/tools/`.
- **Toolkit**: [polymcp/polymcp_toolkit/expose.py](polymcp/polymcp_toolkit/expose.py).
- **Agent**: [polymcp/polyagent/agent.py](polymcp/polyagent/agent.py), [polymcp/polyagent/unified_agent.py](polymcp/polyagent/unified_agent.py).

---

## 🤝 Contributing

1. Fork the repo and create a branch.
2. Make changes following the [guidelines](CONTRIBUTING.md).
3. Run tests and format code (`black`, `flake8`).
4. Open a Pull Request!

---

## ⭐ Stars Chart

[![Stargazers over time](https://starchart.cc/JustVugg/polymcp.svg)](https://starchart.cc/JustVugg/polymcp)

---

## 📄 License

MIT License

---

## 🔗 Useful Links

- [MCP Specification](https://github.com/modelcontextprotocol/spec)
- [PolyMCP on GitHub](https://github.com/JustVugg/polymcp)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)

---

> _PolyMCP is designed to be extensible, interoperable, and production-ready!_
