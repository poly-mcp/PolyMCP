"""
Init Command - Initialize new PolyMCP projects
Crea progetti production-ready per server MCP in vari formati.
"""

import click
import json
from pathlib import Path


# ============================================================================
# COMANDO PRINCIPALE
# ============================================================================

@click.command('init')
@click.argument('project_name')
@click.option(
    '--type', 
    'project_type',
    type=click.Choice(['basic', 'http-server', 'stdio-server', 'wasm-server', 'agent']),
    default='basic',
    help='Tipo di progetto da creare'
)
@click.option('--with-auth', is_flag=True, help='Includere autenticazione (solo HTTP)')
@click.option('--with-examples', is_flag=True, help='Includere tools di esempio')
def init_cmd(project_name: str, project_type: str, with_auth: bool, with_examples: bool):
    """
    Inizializza un nuovo progetto PolyMCP.
    
    Esempi:
      polymcp init my-project
      polymcp init my-server --type http-server --with-examples
      polymcp init my-tools --type stdio-server --with-examples
      polymcp init my-wasm --type wasm-server --with-examples
      polymcp init my-agent --type agent
    """
    project_path = Path(project_name)
    
    # Verifica se directory esiste già
    if project_path.exists():
        click.echo(f"❌ Errore: La directory '{project_name}' esiste già", err=True)
        return
    
    click.echo(f"\n🚀 Creazione progetto PolyMCP: {project_name}")
    click.echo(f"   Tipo: {project_type}")
    if with_examples:
        click.echo(f"   Con esempi: ✓")
    if with_auth and project_type == 'http-server':
        click.echo(f"   Con autenticazione: ✓")
    
    # Crea directory progetto
    project_path.mkdir(parents=True)
    
    # Chiama la funzione appropriata per il tipo di progetto
    if project_type == 'basic':
        _create_basic_project(project_path, with_auth, with_examples)
    
    elif project_type == 'http-server':
        _create_http_server(project_path, with_auth, with_examples)
    
    elif project_type == 'stdio-server':
        _create_stdio_server(project_path, with_examples)
    
    elif project_type == 'wasm-server':
        _create_wasm_server(project_path, with_examples)
    
    elif project_type == 'agent':
        _create_agent_project(project_path, with_examples)
    
    # Messaggio finale con next steps
    _show_next_steps(project_name, project_type)


# ============================================================================
# TIPO 1: BASIC PROJECT
# ============================================================================

def _create_basic_project(project_path: Path, with_auth: bool, with_examples: bool):
    """Crea progetto basic con HTTP server."""
    
    # Crea struttura directory
    (project_path / "tools").mkdir()
    (project_path / "tests").mkdir()
    
    # 1. Requirements
    requirements = ["polymcp>=1.1.3", "python-dotenv>=1.0.0"]
    if with_auth:
        requirements.extend(["python-jose[cryptography]>=3.3.0", "passlib[bcrypt]>=1.7.4"])
    (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
    
    # 2. Environment template
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
        env_content += """
# Authentication
MCP_SECRET_KEY=development-secret-key-change-in-production
MCP_REQUIRE_HTTPS=false
"""
    (project_path / ".env.template").write_text(env_content)
    
    # 3. Server file
    if with_auth:
        server_code = '''#!/usr/bin/env python3
from polymcp import expose_tools_http
from polymcp.mcp_auth import ProductionAuthenticator, add_production_auth_to_mcp
import uvicorn
import os
from dotenv import load_dotenv
from tools.example_tools import greet, calculate

load_dotenv()

def main():
    app = expose_tools_http(
        tools=[greet, calculate],
        title="My Authenticated MCP Server",
        verbose=True
    )
    
    auth = ProductionAuthenticator(
        enforce_https=os.getenv("MCP_REQUIRE_HTTPS", "false").lower() == "true"
    )
    app = add_production_auth_to_mcp(app, auth)
    
    print("\\nServer: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
'''
    else:
        server_code = '''#!/usr/bin/env python3
from polymcp import expose_tools_http
import uvicorn
from tools.example_tools import greet, calculate

def main():
    app = expose_tools_http(
        tools=[greet, calculate],
        title="My MCP Server",
        verbose=True
    )
    
    print("\\nServer: http://localhost:8000")
    print("Docs: http://localhost:8000/docs")
    print("Tools: http://localhost:8000/mcp/list_tools\\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
'''
    (project_path / "server.py").write_text(server_code)
    (project_path / "server.py").chmod(0o755)
    
    # 4. Example tools
    if with_examples:
        tools_code = '''"""Example Tools"""

def greet(name: str) -> str:
    """
    Saluta qualcuno per nome.
    
    Args:
        name: Nome della persona
    
    Returns:
        Messaggio di saluto
    """
    return f"Hello, {name}! Welcome to PolyMCP."

def calculate(operation: str, a: float, b: float) -> float:
    """
    Esegue operazioni aritmetiche base.
    
    Args:
        operation: Operazione (add, subtract, multiply, divide)
        a: Primo numero
        b: Secondo numero
    
    Returns:
        Risultato dell'operazione
    """
    ops = {
        'add': lambda x, y: x + y,
        'subtract': lambda x, y: x - y,
        'multiply': lambda x, y: x * y,
        'divide': lambda x, y: x / y if y != 0 else float('inf')
    }
    
    if operation not in ops:
        raise ValueError(f"Unknown operation: {operation}")
    
    return ops[operation](a, b)
'''
        (project_path / "tools" / "example_tools.py").write_text(tools_code)
        (project_path / "tools" / "__init__.py").write_text("")
    
    # 5. README
    readme = f"""# {project_path.name}

Progetto PolyMCP creato con `polymcp init`

## Setup

```bash
pip install -r requirements.txt
cp .env.template .env
# Modifica .env con le tue configurazioni
```

## Run Server

```bash
python server.py
```

## Test

```bash
# List tools
curl http://localhost:8000/mcp/list_tools

# Invoke tool
curl -X POST http://localhost:8000/mcp/invoke/greet \\
  -H "Content-Type: application/json" \\
  -d '{{"name": "World"}}'
```

## Aggiungi Tools

1. Crea funzioni in `tools/`
2. Importa in `server.py`
3. Riavvia server
"""
    (project_path / "README.md").write_text(readme)
    
    # 6. .gitignore
    gitignore = """__pycache__/
*.py[cod]
.venv/
venv/
.env
*.log
"""
    (project_path / ".gitignore").write_text(gitignore)


# ============================================================================
# TIPO 2: HTTP SERVER
# ============================================================================

def _create_http_server(project_path: Path, with_auth: bool, with_examples: bool):
    """Crea HTTP server project (usa basic + config aggiuntive)."""
    
    # Crea basic project
    _create_basic_project(project_path, with_auth, with_examples)
    
    # Aggiungi config HTTP-specific
    config = {
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
    (project_path / "config.json").write_text(json.dumps(config, indent=2))


# ============================================================================
# TIPO 3: STDIO SERVER (Production con expose_tools_stdio)
# ============================================================================

def _create_stdio_server(project_path: Path, with_examples: bool):
    """Crea stdio server production-ready usando expose_tools_stdio."""
    
    # 1. Struttura directory
    (project_path / "tools").mkdir()
    
    # 2. Requirements
    requirements = [
        "polymcp>=1.1.3",
        "pydantic>=2.0.0",
        "docstring-parser>=0.16"
    ]
    (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
    
    # 3. Server Python usando expose_tools_stdio
    server_code = '''#!/usr/bin/env python3
"""
Stdio MCP Server - Production Ready
Usa expose_tools_stdio di PolyMCP.
"""

from polymcp import expose_tools_stdio
from tools.example_tools import process_text, analyze
import sys


def main():
    # Crea server stdio con protocollo MCP completo
    server = expose_tools_stdio(
        tools=[process_text, analyze],
        server_name="My Stdio MCP Server",
        server_version="1.0.0",
        verbose=False  # True per debugging
    )
    
    # Log su stderr (stdout è per JSON-RPC)
    print("✓ Stdio MCP Server ready", file=sys.stderr)
    print(f"  Tools: process_text, analyze", file=sys.stderr)
    
    # Avvia server (blocca finché non viene fermato)
    server.run()


if __name__ == "__main__":
    main()
'''
    (project_path / "server.py").write_text(server_code)
    (project_path / "server.py").chmod(0o755)
    
    # 4. Node.js wrapper per npm
    index_js = '''#!/usr/bin/env node
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const server = spawn('python3', [join(__dirname, 'server.py')], {
  stdio: ['pipe', 'pipe', 'inherit']
});

process.stdin.pipe(server.stdin);
server.stdout.pipe(process.stdout);

server.on('error', (err) => {
  console.error('Failed to start:', err);
  process.exit(1);
});

process.on('SIGTERM', () => server.kill('SIGTERM'));
process.on('SIGINT', () => server.kill('SIGINT'));
'''
    (project_path / "index.js").write_text(index_js)
    (project_path / "index.js").chmod(0o755)
    
    # 5. package.json per npm
    package_json = {
        "name": f"@yourusername/{project_path.name}",
        "version": "1.0.0",
        "description": f"{project_path.name} - MCP stdio server",
        "type": "module",
        "bin": {project_path.name: "./index.js"},
        "files": ["server.py", "index.js", "tools/", "requirements.txt"],
        "keywords": ["mcp", "model-context-protocol", "stdio"],
        "license": "MIT"
    }
    (project_path / "package.json").write_text(json.dumps(package_json, indent=2))
    
    # 6. Example tools
    if with_examples:
        tools_code = '''"""Example Tools per Stdio Server"""
from typing import Dict, Any


def process_text(text: str, operation: str = "uppercase") -> str:
    """
    Processa testo con operazione specificata.
    
    Args:
        text: Testo da processare
        operation: Operazione (uppercase, lowercase, reverse)
    
    Returns:
        Testo processato
    """
    if operation == "uppercase":
        return text.upper()
    elif operation == "lowercase":
        return text.lower()
    elif operation == "reverse":
        return text[::-1]
    return text


def analyze(data: str) -> Dict[str, Any]:
    """
    Analizza testo e ritorna statistiche.
    
    Args:
        data: Testo da analizzare
    
    Returns:
        Dizionario con statistiche
    """
    words = data.split()
    return {
        "length": len(data),
        "words": len(words),
        "unique_words": len(set(words)),
        "lines": len(data.split("\\n"))
    }
'''
        (project_path / "tools" / "example_tools.py").write_text(tools_code)
        (project_path / "tools" / "__init__.py").write_text("")
    
    # 7. README
    readme = f"""# {project_path.name}

Stdio MCP Server production-ready con PolyMCP.

## Quick Start

### Python
```bash
pip install -r requirements.txt
python server.py
```

### NPM
```bash
npm install
npx @yourusername/{project_path.name}
```

## Claude Desktop

Aggiungi a `claude_desktop_config.json`:

```json
{{
  "mcpServers": {{
    "{project_path.name}": {{
      "command": "npx",
      "args": ["@yourusername/{project_path.name}"]
    }}
  }}
}}
```

## Pubblicare su NPM

1. Modifica `package.json` con il tuo username
2. `npm login`
3. `npm publish --access public`
4. Usa con: `npx @yourusername/{project_path.name}`

## Test

```bash
# Initialize
echo '{{"jsonrpc":"2.0","id":1,"method":"initialize","params":{{"protocolVersion":"2024-11-05"}}}}' | python server.py

# List tools
echo '{{"jsonrpc":"2.0","id":2,"method":"tools/list"}}' | python server.py

# Call tool
echo '{{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{{"name":"process_text","arguments":{{"text":"hello"}}}}}}' | python server.py
```
"""
    (project_path / "README.md").write_text(readme)
    
    # 8. .gitignore
    (project_path / ".gitignore").write_text("__pycache__/\n*.py[cod]\n.venv/\nvenv/\nnode_modules/\n")


# ============================================================================
# TIPO 4: WASM SERVER (Production con expose_tools_wasm)
# ============================================================================

def _create_wasm_server(project_path: Path, with_examples: bool):
    """Crea WASM server production-ready usando expose_tools_wasm."""
    
    # 1. Struttura directory
    (project_path / "tools").mkdir()
    
    # 2. Requirements
    requirements = [
        "polymcp>=1.1.3",
        "pydantic>=2.0.0",
        "docstring-parser>=0.16"
    ]
    (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
    
    # 3. Build script usando expose_tools_wasm
    build_code = f'''#!/usr/bin/env python3
"""
Build WASM MCP Server
Compila tools Python in WebAssembly.
"""

from polymcp import expose_tools_wasm

# Import tools
try:
    from tools.example_tools import calculate_stats, format_text
    tools = [calculate_stats, format_text]
except ImportError:
    # Fallback se non ci sono tools
    def greet(name: str) -> str:
        """Saluta."""
        return f"Hello, {{name}}!"
    tools = [greet]


def main():
    print("\\n🚀 Building WASM MCP Server...")
    print(f"   Tools: {{len(tools)}}")
    
    # Crea compiler
    compiler = expose_tools_wasm(
        tools=tools,
        server_name="{project_path.name}",
        server_version="1.0.0",
        pyodide_version="0.26.4",
        verbose=True
    )
    
    # Compila in dist/
    bundle = compiler.compile(output_dir="./dist")
    
    print("\\n✅ Build completato!")
    print("\\nFile generati:")
    for name, path in bundle.items():
        print(f"  • {{name}}: {{path.name}}")
    
    print("\\n📖 Next Steps:")
    print("  1. cd dist && python -m http.server 8000")
    print("  2. Apri: http://localhost:8000/demo.html")
    print("  3. Deploy: npm publish (da dist/)")


if __name__ == "__main__":
    main()
'''
    (project_path / "build.py").write_text(build_code)
    (project_path / "build.py").chmod(0o755)
    
    # 4. Example tools
    if with_examples:
        tools_code = '''"""Example Tools per WASM Server"""
from typing import List, Dict, Any


def calculate_stats(numbers: List[float]) -> Dict[str, float]:
    """
    Calcola statistiche per lista di numeri.
    
    Args:
        numbers: Lista di numeri
    
    Returns:
        Dizionario con statistiche
    """
    if not numbers:
        return {"error": "Lista vuota"}
    
    n = len(numbers)
    mean = sum(numbers) / n
    sorted_nums = sorted(numbers)
    median = sorted_nums[n // 2] if n % 2 else (sorted_nums[n//2-1] + sorted_nums[n//2]) / 2
    
    return {
        "count": n,
        "mean": round(mean, 3),
        "median": median,
        "min": min(numbers),
        "max": max(numbers)
    }


def format_text(text: str, format_type: str = "title") -> str:
    """
    Formatta testo in vari stili.
    
    Args:
        text: Testo da formattare
        format_type: Tipo (title, upper, lower, capitalize)
    
    Returns:
        Testo formattato
    """
    formats = {
        "title": text.title,
        "upper": text.upper,
        "lower": text.lower,
        "capitalize": text.capitalize
    }
    return formats.get(format_type, lambda: text)()
'''
        (project_path / "tools" / "example_tools.py").write_text(tools_code)
        (project_path / "tools" / "__init__.py").write_text("")
    
    # 5. README
    readme = f"""# {project_path.name}

WASM MCP Server production-ready con PolyMCP.

## Build

```bash
pip install -r requirements.txt
python build.py
```

## Test Locale

```bash
cd dist
python -m http.server 8000
```

Apri: http://localhost:8000/demo.html

## Deploy

### GitHub Pages
1. Push `dist/` su branch `gh-pages`
2. Abilita GitHub Pages
3. Accedi a: `https://username.github.io/repo/`

### Vercel/Netlify
1. Punta a folder `dist/`
2. Build command: `python build.py`
3. Deploy!

### NPM
```bash
cd dist
npm publish
```

Usa via CDN:
```html
<script type="module">
  import {{ WASMMCPServer }} from 'https://unpkg.com/@username/{project_path.name}/loader.js';
  
  const server = new WASMMCPServer();
  await server.initialize();
  
  const result = await server.callTool('calculate_stats', {{
    numbers: [1, 2, 3, 4, 5]
  }});
  
  console.log(result);
</script>
```

## Uso Browser

```html
<script type="module">
  import {{ WASMMCPServer }} from './dist/loader.js';
  
  const server = new WASMMCPServer();
  await server.initialize();
  
  const {{ tools }} = await server.listTools();
  const result = await server.callTool('format_text', {{
    text: 'hello',
    format_type: 'title'
  }});
</script>
```
"""
    (project_path / "README.md").write_text(readme)
    
    # 6. .gitignore
    (project_path / ".gitignore").write_text("__pycache__/\n*.py[cod]\n.venv/\nvenv/\ndist/\n")


# ============================================================================
# TIPO 5: AGENT PROJECT
# ============================================================================

def _create_agent_project(project_path: Path, with_examples: bool):
    """Crea progetto agent."""
    
    # 1. Requirements
    requirements = ["polymcp>=1.1.3", "python-dotenv>=1.0.0"]
    (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
    
    # 2. .env template
    env_content = """# LLM Provider (scegline uno)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# OLLAMA_BASE_URL=http://localhost:11434

# MCP Servers (separati da virgola)
MCP_SERVERS=http://localhost:8000/mcp

# Agent Config
AGENT_TYPE=unified
AGENT_VERBOSE=true
AGENT_MAX_STEPS=10
"""
    (project_path / ".env.template").write_text(env_content)
    
    # 3. Agent code
    agent_code = '''#!/usr/bin/env python3
"""PolyMCP Agent"""

import os
import asyncio
from dotenv import load_dotenv
from polymcp import UnifiedAgent, CodeModeAgent, PolyAgent
from polymcp.llm_providers import OpenAIProvider, AnthropicProvider, OllamaProvider

load_dotenv()


def create_llm():
    """Crea LLM provider da env."""
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider(model="gpt-4")
    elif os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider(model="claude-3-5-sonnet-20241022")
    else:
        return OllamaProvider(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))


async def run():
    """Run agent."""
    llm = create_llm()
    servers = [s.strip() for s in os.getenv("MCP_SERVERS", "").split(",") if s.strip()]
    
    if not servers:
        print("❌ Nessun MCP server configurato in .env")
        return
    
    agent_type = os.getenv("AGENT_TYPE", "unified")
    verbose = os.getenv("AGENT_VERBOSE", "true").lower() == "true"
    
    print(f"\\n🤖 Agent: {agent_type}")
    print(f"   Servers: {len(servers)}")
    print(f"   Verbose: {verbose}\\n")
    
    if agent_type == "unified":
        agent = UnifiedAgent(llm_provider=llm, mcp_servers=servers, verbose=verbose)
        async with agent:
            print("Agent ready! (quit per uscire)\\n")
            while True:
                try:
                    prompt = input("You: ").strip()
                    if prompt.lower() in ['quit', 'exit', 'q']:
                        break
                    if not prompt:
                        continue
                    
                    response = await agent.run_async(prompt)
                    print(f"\\nAgent: {response}\\n")
                
                except KeyboardInterrupt:
                    break
    
    print("\\n👋 Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\\n👋 Interrupted")
'''
    (project_path / "agent.py").write_text(agent_code)
    (project_path / "agent.py").chmod(0o755)
    
    # 4. README
    readme = f"""# {project_path.name}

PolyMCP Agent Project

## Setup

```bash
pip install -r requirements.txt
cp .env.template .env
# Modifica .env con le tue impostazioni
```

## Run

```bash
python agent.py
```

## Configurazione

Edit `.env`:

```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-...

# MCP Servers
MCP_SERVERS=http://localhost:8000/mcp,http://localhost:8001/mcp

# Agent type: unified, codemode, basic
AGENT_TYPE=unified
```
"""
    (project_path / "README.md").write_text(readme)
    
    # 5. .gitignore
    (project_path / ".gitignore").write_text("__pycache__/\n*.py[cod]\n.env\n*.log\nvenv/\n")


# ============================================================================
# HELPER: NEXT STEPS
# ============================================================================

def _show_next_steps(project_name: str, project_type: str):
    """Mostra next steps basati sul tipo di progetto."""
    
    click.echo(f"\n✅ Progetto creato con successo!")
    click.echo(f"\n📖 Next steps:")
    click.echo(f"  cd {project_name}")
    click.echo(f"  pip install -r requirements.txt")
    
    if project_type in ['basic', 'http-server']:
        click.echo(f"  python server.py")
        click.echo(f"\n  → Server: http://localhost:8000")
    
    elif project_type == 'stdio-server':
        click.echo(f"  python server.py")
        click.echo(f"\n  Oppure pubblica su npm:")
        click.echo(f"  npm publish")
    
    elif project_type == 'wasm-server':
        click.echo(f"  python build.py")
        click.echo(f"  cd dist && python -m http.server")
        click.echo(f"\n  → Demo: http://localhost:8000/demo.html")
    
    elif project_type == 'agent':
        click.echo(f"  cp .env.template .env")
        click.echo(f"  # Modifica .env")
        click.echo(f"  python agent.py")
    
    click.echo(f"\n📚 Leggi README.md per dettagli completi\n")
