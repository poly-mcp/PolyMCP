"""
Init Command - Initialize new PolyMCP projects
"""

import click
import json
from pathlib import Path
from typing import Optional


@click.command('init')
@click.argument('project_name')
@click.option('--type', 'project_type', 
              type=click.Choice(['basic', 'http-server', 'stdio-server', 'agent'], case_sensitive=False),
              default='basic',
              help='Type of project to create')
@click.option('--with-auth', is_flag=True, help='Include authentication setup')
@click.option('--with-examples', is_flag=True, help='Include example tools')
@click.pass_context
def init_cmd(ctx, project_name: str, project_type: str, with_auth: bool, with_examples: bool):
    """
    Initialize a new PolyMCP project.
    
    Examples:
      polymcp init my-project
      polymcp init my-server --type http-server
      polymcp init my-agent --type agent --with-examples
    """
    project_path = Path(project_name)
    
    if project_path.exists():
        click.echo(f"Error: Directory '{project_name}' already exists", err=True)
        return
    
    click.echo(f"Creating PolyMCP project: {project_name}")
    click.echo(f"   Type: {project_type}")
    
    # Create project structure
    project_path.mkdir(parents=True)
    
    if project_type == 'basic':
        _create_basic_project(project_path, with_auth, with_examples)
    elif project_type == 'http-server':
        _create_http_server_project(project_path, with_auth, with_examples)
    elif project_type == 'stdio-server':
        _create_stdio_server_project(project_path, with_examples)
    elif project_type == 'agent':
        _create_agent_project(project_path, with_examples)
    
    click.echo(f"\nProject created successfully!")
    click.echo(f"\nNext steps:")
    click.echo(f"  cd {project_name}")
    click.echo(f"  pip install -r requirements.txt")
    
    if project_type in ['http-server', 'basic']:
        click.echo(f"  python server.py")
    elif project_type == 'agent':
        click.echo(f"  python agent.py")


def _create_basic_project(project_path: Path, with_auth: bool, with_examples: bool):
    """Create a basic PolyMCP project."""
    
    # Create directories
    (project_path / "tools").mkdir()
    (project_path / "tests").mkdir()
    
    # Create requirements.txt
    requirements = [
        "polymcp>=1.1.3",
        "python-dotenv>=1.0.0"
    ]
    
    if with_auth:
        requirements.extend([
            "python-jose[cryptography]>=3.3.0",
            "passlib[bcrypt]>=1.7.4"
        ])
    
    (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
    
    # Create .env template
    env_content = """# PolyMCP Configuration
POLYMCP_ENV=development
POLYMCP_LOG_LEVEL=INFO

# LLM Provider (uncomment one)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# OLLAMA_BASE_URL=http://localhost:11434

# MCP Servers
MCP_SERVERS=http://localhost:8000/mcp
"""
    
    if with_auth:
        env_content += """\n# Authentication (generate strong key for production)
MCP_SECRET_KEY=development-secret-key-change-in-production-min-32-chars
MCP_REQUIRE_HTTPS=false
"""
    
    (project_path / ".env.template").write_text(env_content)
    
    # Create main server.py
    server_code = '''#!/usr/bin/env python3
"""
MCP Server - Expose your tools as MCP endpoints
"""

from polymcp.polymcp_toolkit import expose_tools_http
import uvicorn

# Import your tools
from tools.example_tools import greet, calculate


def main():
    """Run the MCP server."""
    app = expose_tools_http(
        tools=[greet, calculate],
        title="My MCP Server",
        description="Custom MCP tools server",
        verbose=True
    )
    
    print("\\nMCP Server starting...")
    print("URL: http://localhost:8000")
    print("Docs: http://localhost:8000/docs")
    print("Tools: http://localhost:8000/mcp/list_tools\\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
'''
    
    if with_auth:
        server_code = '''#!/usr/bin/env python3
"""
MCP Server with Authentication
"""

from polymcp.polymcp_toolkit import expose_tools_http
from polymcp.polymcp_toolkit.mcp_auth import ProductionAuthenticator, add_production_auth_to_mcp
import uvicorn
import os
from dotenv import load_dotenv

load_dotenv()

# Import your tools
from tools.example_tools import greet, calculate


def main():
    """Run the authenticated MCP server."""
    # Create base app
    app = expose_tools_http(
        tools=[greet, calculate],
        title="My Authenticated MCP Server",
        verbose=True
    )
    
    # Add authentication
    auth = ProductionAuthenticator(
        enforce_https=os.getenv("MCP_REQUIRE_HTTPS", "false").lower() == "true"
    )
    app = add_production_auth_to_mcp(app, auth)
    
    print("\\nAuthenticated MCP Server starting...")
    print("URL: http://localhost:8000")
    print("Auth: http://localhost:8000/auth/info")
    print("Docs: http://localhost:8000/docs\\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
'''
    
    (project_path / "server.py").write_text(server_code)
    (project_path / "server.py").chmod(0o755)
    
    # Create example tools
    if with_examples:
        example_tools = '''"""
Example Tools for MCP Server
"""


def greet(name: str) -> str:
    """
    Greet someone by name.
    
    Args:
        name: The person's name
        
    Returns:
        A greeting message
    """
    return f"Hello, {name}! Welcome to PolyMCP."


def calculate(operation: str, a: float, b: float) -> float:
    """
    Perform basic arithmetic operations.
    
    Args:
        operation: Operation to perform (add, subtract, multiply, divide)
        a: First number
        b: Second number
        
    Returns:
        Result of the operation
    """
    operations = {
        'add': lambda x, y: x + y,
        'subtract': lambda x, y: x - y,
        'multiply': lambda x, y: x * y,
        'divide': lambda x, y: x / y if y != 0 else float('inf')
    }
    
    if operation not in operations:
        raise ValueError(f"Unknown operation: {operation}")
    
    return operations[operation](a, b)
'''
        (project_path / "tools" / "example_tools.py").write_text(example_tools)
        (project_path / "tools" / "__init__.py").write_text("")
    
    # Create README
    readme = f"""# {project_path.name}

PolyMCP project created with `polymcp init`

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.template .env
# Edit .env with your settings
```

## Run Server

```bash
python server.py
```

## Add Your Tools

1. Create new functions in `tools/`
2. Add them to `server.py`
3. Restart the server

## Test Your Server

```bash
# List tools
curl http://localhost:8000/mcp/list_tools

# Invoke a tool
curl -X POST http://localhost:8000/mcp/invoke/greet \\
  -H "Content-Type: application/json" \\
  -d '{{"name": "World"}}'
```

{'## Authentication\n\n```bash\n# Create user\nexport MCP_SECRET_KEY="your-secret-key"\npython -m polymcp.polymcp_toolkit.mcp_auth create_user\n\n# Login\ncurl -X POST http://localhost:8000/auth/login \\\n  -H "Content-Type: application/json" \\\n  -d \'{"username": "user", "password": "password"}\'\n```\n' if with_auth else ''}
## Resources

- [PolyMCP Documentation](https://github.com/llm-use/polymcp)
- [MCP Protocol](https://modelcontextprotocol.io/)
"""
    
    (project_path / "README.md").write_text(readme)
    
    # Create .gitignore
    gitignore = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# PolyMCP
.env
*.db
*.log

# IDE
.vscode/
.idea/
*.swp
"""
    (project_path / ".gitignore").write_text(gitignore)


def _create_http_server_project(project_path: Path, with_auth: bool, with_examples: bool):
    """Create an HTTP server project - uses basic project with server focus."""
    _create_basic_project(project_path, with_auth, with_examples)
    
    # Add additional HTTP-specific files
    config_content = {
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
            "workers": 1,
            "log_level": "info"
        },
        "cors": {
            "enabled": True,
            "origins": ["*"]
        }
    }
    
    (project_path / "config.json").write_text(json.dumps(config_content, indent=2))


def _create_stdio_server_project(project_path: Path, with_examples: bool):
    """Create a stdio server project template."""
    
    (project_path / "tools").mkdir()
    
    # Requirements
    requirements = [
        "polymcp>=1.1.3",
    ]
    (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
    
    # Create stdio server wrapper
    server_code = '''#!/usr/bin/env python3
"""
Stdio MCP Server
"""

import sys
import json
from typing import Dict, Any

# Import your tools
from tools.example_tools import process_text, analyze


class StdioMCPServer:
    """Simple stdio MCP server implementation."""
    
    def __init__(self):
        self.tools = {
            'process_text': process_text,
            'analyze': analyze
        }
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JSON-RPC request."""
        method = request.get('method')
        params = request.get('params', {})
        request_id = request.get('id')
        
        if method == 'initialize':
            return {
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'protocolVersion': '2024-11-05',
                    'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'stdio-mcp', 'version': '1.0.0'}
                }
            }
        
        elif method == 'tools/list':
            tools_list = []
            for name, func in self.tools.items():
                tools_list.append({
                    'name': name,
                    'description': func.__doc__ or '',
                    'inputSchema': {'type': 'object'}
                })
            
            return {
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {'tools': tools_list}
            }
        
        elif method == 'tools/call':
            tool_name = params.get('name')
            arguments = params.get('arguments', {})
            
            if tool_name in self.tools:
                try:
                    result = self.tools[tool_name](**arguments)
                    return {
                        'jsonrpc': '2.0',
                        'id': request_id,
                        'result': {'content': [{'type': 'text', 'text': str(result)}]}
                    }
                except Exception as e:
                    return {
                        'jsonrpc': '2.0',
                        'id': request_id,
                        'error': {'code': -32000, 'message': str(e)}
                    }
            else:
                return {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'error': {'code': -32601, 'message': f'Tool not found: {tool_name}'}
                }
        
        return {
            'jsonrpc': '2.0',
            'id': request_id,
            'error': {'code': -32601, 'message': f'Unknown method: {method}'}
        }
    
    def run(self):
        """Run the stdio server."""
        for line in sys.stdin:
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps(response), flush=True)
            except Exception as e:
                print(json.dumps({
                    'jsonrpc': '2.0',
                    'error': {'code': -32700, 'message': str(e)}
                }), flush=True)


if __name__ == '__main__':
    server = StdioMCPServer()
    server.run()
'''
    
    (project_path / "server.py").write_text(server_code)
    (project_path / "server.py").chmod(0o755)
    
    if with_examples:
        example_tools = '''"""
Example Tools for Stdio Server
"""


def process_text(text: str, operation: str = "uppercase") -> str:
    """Process text with specified operation."""
    if operation == "uppercase":
        return text.upper()
    elif operation == "lowercase":
        return text.lower()
    elif operation == "reverse":
        return text[::-1]
    return text


def analyze(data: str) -> dict:
    """Analyze input data."""
    return {
        "length": len(data),
        "words": len(data.split()),
        "lines": len(data.split("\\n"))
    }
'''
        (project_path / "tools" / "example_tools.py").write_text(example_tools)
        (project_path / "tools" / "__init__.py").write_text("")
    
    # README
    readme = f"""# {project_path.name}

Stdio MCP Server

## Run

```bash
python server.py
```

## Test with npx

```bash
echo '{{"jsonrpc":"2.0","id":1,"method":"tools/list"}}' | python server.py
```

## Use with PolyMCP Agent

```python
agent = UnifiedPolyAgent(
    stdio_servers=[{{
        "command": "python",
        "args": ["{project_path.absolute()}/server.py"]
    }}]
)
```
"""
    (project_path / "README.md").write_text(readme)


def _create_agent_project(project_path: Path, with_examples: bool):
    """Create an agent project."""
    
    # Requirements
    requirements = [
        "polymcp>=1.1.3",
        "python-dotenv>=1.0.0"
    ]
    (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
    
    # .env template
    env_content = """# LLM Provider (choose one)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# OLLAMA_BASE_URL=http://localhost:11434

# MCP Servers (comma-separated)
MCP_SERVERS=http://localhost:8000/mcp,http://localhost:8001/mcp

# Agent Configuration
AGENT_TYPE=unified
AGENT_VERBOSE=true
AGENT_MAX_STEPS=10
"""
    (project_path / ".env.template").write_text(env_content)
    
    # Agent code
    agent_code = '''#!/usr/bin/env python3
"""
PolyMCP Agent
"""

import os
import asyncio
from dotenv import load_dotenv
from polymcp.polyagent import UnifiedPolyAgent, CodeModeAgent, PolyAgent
from polymcp.polyagent.llm_providers import (
    OpenAIProvider, AnthropicProvider, OllamaProvider
)

load_dotenv()


def create_llm_provider():
    """Create LLM provider based on environment."""
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider(model="gpt-4")
    elif os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider(model="claude-3-5-sonnet-20241022")
    else:
        print("Using Ollama (make sure it's running)")
        return OllamaProvider(
            model="llama3.2",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )


def get_mcp_servers():
    """Get MCP servers from environment."""
    servers_str = os.getenv("MCP_SERVERS", "")
    return [s.strip() for s in servers_str.split(",") if s.strip()]


async def run_agent():
    """Run the agent interactively."""
    llm = create_llm_provider()
    servers = get_mcp_servers()
    
    if not servers:
        print("No MCP servers configured in .env")
        print("Add: MCP_SERVERS=http://localhost:8000/mcp")
        return
    
    agent_type = os.getenv("AGENT_TYPE", "unified")
    verbose = os.getenv("AGENT_VERBOSE", "true").lower() == "true"
    
    print(f"\\nStarting {agent_type.upper()} Agent")
    print(f"MCP Servers: {len(servers)}")
    print(f"Verbose: {verbose}\\n")
    
    if agent_type == "unified":
        agent = UnifiedPolyAgent(
            llm_provider=llm,
            mcp_servers=servers,
            verbose=verbose
        )
        
        async with agent:
            print("Agent ready! Type 'quit' to exit.\\n")
            
            while True:
                try:
                    user_input = input("You: ").strip()
                    
                    if user_input.lower() in ['quit', 'exit', 'q']:
                        print("\\nGoodbye!")
                        break
                    
                    if not user_input:
                        continue
                    
                    response = await agent.run_async(user_input)
                    print(f"\\nAgent: {response}\\n")
                
                except KeyboardInterrupt:
                    print("\\n\\nGoodbye!")
                    break
                except Exception as e:
                    print(f"\\nError: {e}\\n")
    
    elif agent_type == "codemode":
        agent = CodeModeAgent(
            llm_provider=llm,
            mcp_servers=servers,
            verbose=verbose
        )
        
        print("Agent ready! Type 'quit' to exit.\\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\\nGoodbye!")
                    break
                
                if not user_input:
                    continue
                
                response = agent.run(user_input)
                print(f"\\nAgent: {response}\\n")
            
            except KeyboardInterrupt:
                print("\\n\\nGoodbye!")
                break
            except Exception as e:
                print(f"\\nError: {e}\\n")
    
    else:  # basic agent
        agent = PolyAgent(
            llm_provider=llm,
            mcp_servers=servers,
            verbose=verbose
        )
        
        print("Agent ready! Type 'quit' to exit.\\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\\nGoodbye!")
                    break
                
                if not user_input:
                    continue
                
                response = agent.run(user_input)
                print(f"\\nAgent: {response}\\n")
            
            except KeyboardInterrupt:
                print("\\n\\nGoodbye!")
                break
            except Exception as e:
                print(f"\\nError: {e}\\n")


def main():
    """Main entry point."""
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\\n\\nInterrupted by user")


if __name__ == "__main__":
    main()
'''
    
    (project_path / "agent.py").write_text(agent_code)
    (project_path / "agent.py").chmod(0o755)
    
    # README
    readme = f"""# {project_path.name}

PolyMCP Agent Project

## Setup

```bash
pip install -r requirements.txt
cp .env.template .env
# Edit .env with your settings
```

## Configure MCP Servers

Edit `.env` and add your MCP servers:

```bash
MCP_SERVERS=http://localhost:8000/mcp,http://localhost:8001/mcp
```

## Run Agent

```bash
python agent.py
```

## Agent Types

- `unified`: Autonomous multi-step reasoning (default)
- `codemode`: Generate code to orchestrate tools
- `basic`: Simple tool selection and execution

Change in `.env`:

```bash
AGENT_TYPE=unified  # or codemode, basic
```
"""
    (project_path / "README.md").write_text(readme)
    
    # .gitignore
    gitignore = """__pycache__/
*.py[cod]
.env
*.log
venv/
"""
    (project_path / ".gitignore").write_text(gitignore)
