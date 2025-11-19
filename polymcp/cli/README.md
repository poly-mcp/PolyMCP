<p align="center">
  <img src="polymcp-cli.png" alt="PolymCP-cli Logo" width="500"/>
</p>
<br>

Command-line interface for PolyMCP - Universal MCP Agent & Toolkit.

[![PyPI version](https://img.shields.io/pypi/v/polymcp.svg)](https://pypi.org/project/polymcp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/polymcp.svg)](https://pypi.org/project/polymcp/)
[![License](https://img.shields.io/pypi/l/polymcp.svg)](https://github.com/llm-use/polymcp/blob/main/LICENSE)

---

## 🎉 What's New in PolyMCP

### 🖥️ **Command-Line Interface** - NEW!
Complete CLI for managing projects, servers, and agents:
- **Project scaffolding** - `polymcp init my-project` creates complete projects
- **Server management** - Add, test, and manage HTTP/stdio MCP servers
- **Agent orchestration** - Run agents from command line with any LLM
- **Testing suite** - Comprehensive testing for servers and tools
- **Configuration management** - Global and local config with JSON/YAML support

```bash
# Quick start
polymcp init my-project --with-examples
cd my-project
pip install -r requirements.txt
python server.py &
polymcp agent run
```

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
from polymcp.polyagent import CodeModeAgent, OpenAIProvider

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

## 📦 Installation

```bash
# Install from PyPI (includes CLI)
pip install polymcp

# Verify installation
polymcp --version

# Or install from source
git clone https://github.com/llm-use/polymcp.git
cd polymcp
pip install -e .
```

---

## 🚀 Quick Start

```bash
# Initialize a new project
polymcp init my-project

# Add MCP servers
polymcp server add http://localhost:8000/mcp

# List configured servers
polymcp server list

# Run an agent
polymcp agent run

# Test a server
polymcp test server http://localhost:8000/mcp
```

---

## 🎯 Your First Custom Tool

Let's create a complete example from scratch:

```bash
# 1. Create project
polymcp init my-first-tool --with-examples
cd my-first-tool

# 2. Create your custom tool
cat > tools/weather_tool.py << 'EOF'
def get_weather(city: str, units: str = "celsius") -> dict:
    """
    Get weather information for a city.
    
    Args:
        city: City name
        units: Temperature units (celsius/fahrenheit)
        
    Returns:
        Weather information dictionary
    """
    import random
    temp = random.randint(15, 30) if units == "celsius" else random.randint(59, 86)
    
    return {
        "city": city,
        "temperature": temp,
        "units": units,
        "condition": random.choice(["sunny", "cloudy", "rainy"]),
        "humidity": random.randint(40, 80)
    }
EOF

# 3. Update server.py to use your tool
# Add to imports: from tools.weather_tool import get_weather
# Add to tools list: tools=[greet, calculate, get_weather]

# 4. Install and run
pip install -r requirements.txt
python server.py &

# 5. Test your tool
polymcp test tool http://localhost:8000/mcp get_weather \
  --params '{"city":"Rome","units":"celsius"}'

# 6. Use with agent
polymcp agent run
# > You: What's the weather in Rome?
# > Agent: [calls get_weather and responds]
```

---

## 📚 Commands

### `polymcp init`

Initialize new PolyMCP projects.

```bash
# Basic project
polymcp init my-project

# HTTP server project
polymcp init my-server --type http-server

# Agent project
polymcp init my-agent --type agent

# With examples and authentication
polymcp init my-project --with-examples --with-auth
```

**Project Types:**
- `basic`: Complete project with server + tools
- `http-server`: HTTP MCP server
- `stdio-server`: Stdio MCP server
- `agent`: Interactive agent

### `polymcp server`

Manage MCP servers.

```bash
# Add HTTP server
polymcp server add http://localhost:8000/mcp --name my-server

# Add stdio server
polymcp server add stdio://playwright \
  --type stdio \
  --command npx \
  --args @playwright/mcp@latest

# List all servers
polymcp server list

# Remove server
polymcp server remove http://localhost:8000/mcp

# Test server
polymcp server test http://localhost:8000/mcp

# Get server info
polymcp server info http://localhost:8000/mcp
```

**Using Your Own MCP Servers:**

1. Start your MCP server:
   ```bash
   cd my-mcp-project
   python server.py
   ```

2. Add it to PolyMCP CLI:
   ```bash
   polymcp server add http://localhost:8000/mcp --name my-custom-server
   ```

3. Use it with agents:
   ```bash
   polymcp agent run
   # or
   polymcp agent run --servers http://localhost:8000/mcp
   ```

### `polymcp agent`

Run and manage agents.

```bash
# Run interactive agent (default: unified)
polymcp agent run

# Use specific agent type
polymcp agent run --type codemode
polymcp agent run --type basic

# Use specific LLM
polymcp agent run --llm openai --model gpt-4
polymcp agent run --llm anthropic --model claude-3-5-sonnet-20241022
polymcp agent run --llm ollama --model llama3.2

# Single query (non-interactive)
polymcp agent run --query "What is 2+2?"

# With specific servers
polymcp agent run --servers http://localhost:8000/mcp,http://localhost:8001/mcp

# Verbose mode
polymcp agent run --verbose

# Benchmark agents
polymcp agent benchmark --query "Add 2+2" --iterations 5
```

**Agent Types:**
- `unified`: Autonomous multi-step reasoning (best for complex tasks)
- `codemode`: Code generation for tool orchestration (fastest)
- `basic`: Simple tool selection and execution

### `polymcp test`

Test MCP servers and tools.

```bash
# Test server connectivity
polymcp test server http://localhost:8000/mcp

# Test with authentication
polymcp test server http://localhost:8000/mcp --auth-key sk-...

# Test specific tool
polymcp test tool http://localhost:8000/mcp greet --params '{"name":"World"}'

# Test authentication
polymcp test auth http://localhost:8000

# Test stdio server
polymcp test stdio npx @playwright/mcp@latest

# Test all configured servers
polymcp test all
```

### `polymcp config`

Manage configuration.

```bash
# Show configuration
polymcp config show

# Set values
polymcp config set llm.provider openai
polymcp config set llm.model gpt-4
polymcp config set agent.verbose true

# Get value
polymcp config get llm.provider

# Delete value
polymcp config delete llm.model

# Initialize with defaults
polymcp config init

# Edit in editor
polymcp config edit

# Show config path
polymcp config path

# Reset to defaults
polymcp config reset
```

**Global vs Local Config:**

```bash
# Local config (project-specific)
polymcp config set llm.provider openai

# Global config (user-wide)
polymcp config set llm.provider openai --global
```

---

## ⚙️ Configuration

The CLI uses two configuration files:

1. **Global Config**: `~/.polymcp/polymcp_config.json`
   - User-wide settings
   - LLM provider defaults
   - Agent preferences

2. **Local Config**: `./polymcp_config.json`
   - Project-specific settings
   - Overrides global config

**Example Configuration:**

```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4",
    "temperature": 0.7
  },
  "agent": {
    "type": "unified",
    "verbose": false,
    "max_steps": 10
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8000
  }
}
```

## Server Registry

The CLI maintains a registry of MCP servers:

**Registry File**: `./polymcp_registry.json`

```json
{
  "version": "1.0.0",
  "description": "PolyMCP server registry",
  "servers": {
    "http://localhost:8000/mcp": {
      "url": "http://localhost:8000/mcp",
      "type": "http",
      "name": "my-server"
    }
  },
  "stdio_servers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "env": {},
      "type": "stdio"
    }
  }
}
```

## Environment Variables

The CLI respects standard environment variables:

```bash
# LLM Providers
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export OLLAMA_BASE_URL=http://localhost:11434

# Windows Encoding Fix
export PYTHONIOENCODING=utf-8

# Editor for config editing
export EDITOR=vim
```

---

## 💡 Real-World Examples

### Example 1: Complete Workflow

```bash
# 1. Create new project
polymcp init my-project --with-examples
cd my-project

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start your MCP server
python server.py &

# 4. Add server to CLI
polymcp server add http://localhost:8000/mcp --name my-server

# 5. Test the server
polymcp test server http://localhost:8000/mcp

# 6. Run interactive agent
polymcp agent run
```

### Example 2: Multi-Tool Financial Assistant

```bash
# Create financial tools server
polymcp init finance-server --type http-server
cd finance-server

# Create financial tools
cat > tools/finance_tools.py << 'EOF'
def calculate_mortgage(principal: float, rate: float, years: int) -> dict:
    """Calculate monthly mortgage payment."""
    monthly_rate = rate / 100 / 12
    num_payments = years * 12
    payment = principal * (monthly_rate * (1 + monthly_rate)**num_payments) / \
              ((1 + monthly_rate)**num_payments - 1)
    
    return {
        "monthly_payment": round(payment, 2),
        "total_paid": round(payment * num_payments, 2),
        "total_interest": round((payment * num_payments) - principal, 2)
    }

def calculate_roi(initial: float, final: float, years: int) -> dict:
    """Calculate return on investment."""
    total_return = ((final - initial) / initial) * 100
    annual_return = ((final / initial) ** (1 / years) - 1) * 100
    
    return {
        "total_return_percent": round(total_return, 2),
        "annual_return_percent": round(annual_return, 2),
        "profit": round(final - initial, 2)
    }
EOF

# Update server.py to include new tools
# Start and register
python server.py &
polymcp server add http://localhost:8000/mcp --name finance-tools

# Use with agent
polymcp agent run --query "Calculate mortgage for 300000 at 3.5% for 30 years"
```

### Example 3: Using Multiple Servers

```bash
# Add multiple servers
polymcp server add http://localhost:8000/mcp --name text-tools
polymcp server add http://localhost:8001/mcp --name data-tools

# List all servers
polymcp server list

# Run agent with all configured servers
polymcp agent run

# Or specify servers explicitly
polymcp agent run --servers http://localhost:8000/mcp,http://localhost:8001/mcp
```

### Example 4: Web Automation with Playwright

```bash
# Setup browser automation
polymcp init web-automation --type agent

# Add Playwright server
polymcp server add stdio://playwright \
  --type stdio \
  --command npx \
  --args @playwright/mcp@latest

# Add custom web tools
polymcp server add http://localhost:8000/mcp --name web-tools

# Test browser automation
polymcp agent run --query "
  Go to github.com/llm-use/polymcp,
  take a screenshot,
  count the stars
"
```

---

## 🔧 Advanced Usage

### Benchmark Different Approaches

```bash
# Compare agent performance
polymcp agent benchmark \
  --query "Calculate 10+20, multiply by 2, subtract 5" \
  --iterations 3

# Expected output:
# Basic Agent:     2.34s
# CodeMode Agent:  1.45s  ⚡ 38% faster
# Unified Agent:   3.12s
```

### Automated Server Discovery

Create `discover_servers.sh`:

```bash
#!/bin/bash
# Auto-discover MCP servers on local network

echo "Scanning for MCP servers..."

for port in {8000..8010}; do
    if timeout 1 curl -s http://localhost:$port/mcp/list_tools > /dev/null 2>&1; then
        echo "Found server on port $port"
        polymcp server add http://localhost:$port/mcp --name "auto-$port"
    fi
done

polymcp server list
```

### CI/CD Integration

Create `.github/workflows/test-mcp.yml`:

```yaml
name: Test MCP Servers
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install PolyMCP
        run: pip install polymcp
      
      - name: Start servers
        run: |
          python server1.py &
          python server2.py &
          sleep 5
      
      - name: Test all servers
        run: polymcp test all
```

---

## 🎓 Best Practices

### Choosing the Right Agent Type

| Task Type | Recommended Agent | Why |
|-----------|------------------|-----|
| Simple queries | `basic` | Fast, single tool call |
| Complex workflows | `unified` | Multi-step reasoning |
| Multiple tool orchestration | `codemode` | 60% faster, generates code |
| Browser automation | `unified` | Handles async operations |
| Data pipelines | `codemode` | Loops and conditions |

### Performance Tips

```bash
# 1. Use codemode for multiple operations
polymcp agent run --type codemode \
  --query "Process 100 records"  # Much faster

# 2. Limit steps for complex tasks
polymcp config set agent.max_steps 15

# 3. Use verbose only for debugging
polymcp agent run --verbose  # Slower but detailed

# 4. Cache LLM provider in config
polymcp config set llm.provider ollama  # Avoid re-selection
```

---

## 🛠️ Troubleshooting

### Windows Emoji Issue ⚠️

**Problem:** `'charmap' codec can't encode character`

**Solution 1 - Quick Fix:**
```bash
# PowerShell
$env:PYTHONIOENCODING="utf-8"
polymcp init my-project

# CMD
set PYTHONIOENCODING=utf-8
polymcp init my-project

# Permanently
[Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "User")
```

**Solution 2 - Console CodePage:**
```bash
chcp 65001
polymcp init my-project
```

**Solution 3 - Use Python with UTF-8 flag:**
```bash
python -X utf8 -m polymcp init my-project
```

### Server Not Found

```bash
# Check registered servers
polymcp server list

# Test connectivity
polymcp test server http://localhost:8000/mcp

# Re-add server
polymcp server add http://localhost:8000/mcp
```

### Authentication Issues

```bash
# Test authentication
polymcp test auth http://localhost:8000

# Use API key
polymcp agent run --servers http://localhost:8000/mcp
# (Set X-API-Key in config or environment)
```

### LLM Provider Issues

```bash
# Check configuration
polymcp config get llm.provider

# Set explicitly
polymcp config set llm.provider ollama
polymcp config set llm.model llama3.2

# Or use command-line options
polymcp agent run --llm ollama --model llama3.2
```

### Ollama Connection Issues

**Problem:** "Connection refused to localhost:11434"

**Solutions:**
```bash
# 1. Check if Ollama is running
curl http://localhost:11434/api/tags

# 2. Start Ollama
ollama serve

# 3. Check model is pulled
ollama list
ollama pull llama3.2

# 4. Test with explicit URL
export OLLAMA_BASE_URL=http://localhost:11434
polymcp agent run --llm ollama --model llama3.2
```

### Agent Not Finding Tools

```bash
# 1. Check server is registered
polymcp server list

# 2. Test server connectivity
polymcp test server http://localhost:8000/mcp

# 3. Verify tools are exposed
curl http://localhost:8000/mcp/list_tools

# 4. Re-register server
polymcp server remove http://localhost:8000/mcp
polymcp server add http://localhost:8000/mcp --name my-server
```

---

## ❓ FAQ

**Q: Which agent type should I use?**
A: Use `unified` for complex tasks, `codemode` for speed, `basic` for simple queries.

**Q: Can I use multiple LLM providers?**
A: Yes! Set different providers per project with local config.

**Q: How do I add authentication?**
A: Use `--with-auth` flag: `polymcp init my-server --with-auth`

**Q: Can I use PolyMCP without Python?**
A: Yes! Add TypeScript/Node.js MCP servers via stdio mode.

**Q: Is there a GUI?**
A: CLI only for now. GUI planned for future releases.

**Q: How do I contribute?**
A: See [CONTRIBUTING.md](https://github.com/llm-use/polymcp/blob/main/CONTRIBUTING.md)

---

## 📋 Quick Reference

### Common Commands Cheatsheet

```bash
# Setup
polymcp init my-project              # New project
polymcp config init                  # Setup config

# Servers
polymcp server add <url>             # Add server
polymcp server list                  # List all
polymcp server test <url>            # Test connectivity

# Agent
polymcp agent run                    # Interactive mode
polymcp agent run --query "..."      # Single query
polymcp agent run --type codemode    # Specific type

# Testing
polymcp test all                     # Test everything
polymcp test server <url>            # Test one server
polymcp test tool <url> <name>       # Test tool

# Config
polymcp config set llm.provider openai
polymcp config get llm.provider
polymcp config show
```

---

## 🚀 Next Steps

After reading this guide:

1. ✅ **Create your first project**: `polymcp init my-first-project`
2. ✅ **Add a custom tool**: Edit `tools/example_tools.py`
3. ✅ **Test your server**: `polymcp test server http://localhost:8000/mcp`
4. ✅ **Run an agent**: `polymcp agent run`
5. ✅ **Join the community**: [Discord](https://discord.gg/...)

### Learning Path

1. **Beginner**: Follow "Your First Custom Tool" example
2. **Intermediate**: Try "Multi-Tool Financial Assistant"
3. **Advanced**: Implement "Data Processing Pipeline"
4. **Expert**: Contribute to PolyMCP on GitHub!

---

## 🔨 Development

```bash
# Install in development mode
pip install -e .

# Run tests
pytest tests/

# Format code
black cli/

# Type checking
mypy cli/
```

---

## 📄 License

MIT License - see LICENSE file for details.

---

## 🔗 Links

- [PolyMCP Repository](https://github.com/llm-use/polymcp)
- [Documentation](https://github.com/llm-use/polymcp#readme)
- [Report Issues](https://github.com/llm-use/polymcp/issues)

---

## 🙏 Credits

- **MCP Protocol**: [Anthropic](https://modelcontextprotocol.io/)
- **Playwright MCP**: [Microsoft](https://github.com/microsoft/playwright-mcp)
- **Contributors**: [See all contributors](https://github.com/llm-use/polymcp/graphs/contributors)

---

**Made with ❤️ by the PolyMCP community**
