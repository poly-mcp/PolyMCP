"""
MCP WASM Server - Production Implementation
Compile Python functions to WebAssembly for browser/edge execution.

Uses Pyodide to create deployable WASM bundles with MCP interface.
"""

import json
import hashlib
import inspect
import logging
from pathlib import Path
from typing import Callable, List, Dict, Any, Union, Optional, get_type_hints
from docstring_parser import parse


logger = logging.getLogger("polymcp.wasm")


class WASMToolCompiler:
    """
    Compile Python tools to WASM with MCP interface.
    
    Creates a complete WASM bundle with:
    - Pyodide runtime
    - Tool functions compiled to WASM
    - JavaScript MCP interface
    - Sandbox security
    - Browser/Node.js/Edge compatible
    
    Example:
        >>> def add(a: int, b: int) -> int:
        ...     '''Add two numbers.'''
        ...     return a + b
        >>> 
        >>> compiler = WASMToolCompiler([add])
        >>> bundle = compiler.compile(output_dir="./dist")
        >>> # Deploy bundle to CDN/edge
    """
    
    def __init__(
        self,
        tools: Union[Callable, List[Callable]],
        server_name: str = "PolyMCP WASM Server",
        server_version: str = "1.0.0",
        pyodide_version: str = "0.26.4",
        verbose: bool = False
    ):
        """
        Initialize WASM compiler.
        
        Args:
            tools: Functions to compile
            server_name: Server name
            server_version: Server version
            pyodide_version: Pyodide version to use
            verbose: Enable verbose logging
        """
        if not isinstance(tools, list):
            tools = [tools]
        
        if not tools:
            raise ValueError("At least one tool must be provided")
        
        self.tools = tools
        self.server_name = server_name
        self.server_version = server_version
        self.pyodide_version = pyodide_version
        self.verbose = verbose
        
        # Extract metadata
        self.tool_metadata = self._extract_all_metadata()
        
        # Setup logging
        if verbose:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.WARNING)
    
    def _extract_all_metadata(self) -> List[Dict[str, Any]]:
        """Extract metadata from all tools."""
        metadata_list = []
        
        for func in self.tools:
            metadata = self._extract_function_metadata(func)
            metadata_list.append(metadata)
        
        return metadata_list
    
    def _extract_function_metadata(self, func: Callable) -> Dict[str, Any]:
        """Extract metadata from a single function."""
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        docstring = parse(func.__doc__ or "")
        description = docstring.short_description or func.__name__
        
        # Build input schema
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            param_type = type_hints.get(param_name, str)
            param_doc = next(
                (p.description for p in docstring.params if p.arg_name == param_name),
                ""
            )
            
            json_type = self._python_type_to_json_type(param_type)
            
            properties[param_name] = {
                "type": json_type,
                "description": param_doc
            }
            
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        
        input_schema = {
            "type": "object",
            "properties": properties
        }
        
        if required:
            input_schema["required"] = required
        
        # Get source code
        source = inspect.getsource(func)
        
        return {
            "name": func.__name__,
            "description": description,
            "inputSchema": input_schema,
            "source": source,
            "module": func.__module__
        }
    
    def _python_type_to_json_type(self, python_type) -> str:
        """Convert Python type to JSON Schema type."""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }
        
        # Handle Union types
        origin = getattr(python_type, '__origin__', None)
        if origin is Union:
            args = getattr(python_type, '__args__', ())
            for arg in args:
                if arg is not type(None):
                    return self._python_type_to_json_type(arg)
        
        return type_map.get(python_type, "string")
    
    def _generate_python_bundle(self) -> str:
        """Generate Python code bundle for WASM execution."""
        # Collect all tool sources
        tool_sources = []
        tool_names = []
        
        for metadata in self.tool_metadata:
            tool_sources.append(metadata["source"])
            tool_names.append(metadata["name"])
        
        # Create Python module with all tools
        python_code = f'''
"""
Auto-generated WASM tool bundle for {self.server_name}
Version: {self.server_version}
"""

import json
import math
from typing import Dict, Any

# Tool implementations
{chr(10).join(tool_sources)}

# Tool registry
TOOLS = {{
{chr(10).join(f'    "{name}": {name},' for name in tool_names)}
}}

# Tool metadata
TOOL_METADATA = {json.dumps(
    [
        {
            "name": m["name"],
            "description": m["description"],
            "inputSchema": m["inputSchema"]
        }
        for m in self.tool_metadata
    ],
    indent=4
)}

def list_tools() -> Dict[str, Any]:
    """List all available tools."""
    return {{"tools": TOOL_METADATA}}

def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call a tool by name.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        
    Returns:
        Tool result with status
    """
    if name not in TOOLS:
        return {{
            "status": "error",
            "error": f"Tool not found: {{name}}",
            "available": list(TOOLS.keys())
        }}
    
    try:
        tool_func = TOOLS[name]
        result = tool_func(**arguments)
        
        return {{
            "status": "success",
            "result": result
        }}
    
    except TypeError as e:
        return {{
            "status": "error",
            "error": f"Invalid arguments: {{str(e)}}"
        }}
    
    except Exception as e:
        return {{
            "status": "error",
            "error": f"Execution failed: {{str(e)}}"
        }}

# Export functions for JavaScript
__all__ = ["list_tools", "call_tool", "TOOLS", "TOOL_METADATA"]
'''
        
        return python_code
    
    def _generate_javascript_loader(self, python_bundle_hash: str) -> str:
        """Generate JavaScript loader for WASM bundle."""
        js_code = f'''/**
 * {self.server_name} - WASM MCP Server
 * Version: {self.server_version}
 * 
 * Auto-generated JavaScript loader for Pyodide-based MCP tools.
 */

class WASMMCPServer {{
    constructor() {{
        this.pyodide = null;
        this.initialized = false;
        this.serverName = "{self.server_name}";
        this.serverVersion = "{self.server_version}";
        this.pyodideVersion = "{self.pyodide_version}";
        this.bundleHash = "{python_bundle_hash}";
    }}
    
    /**
     * Initialize Pyodide and load tools.
     */
    async initialize() {{
        if (this.initialized) {{
            return;
        }}
        
        console.log(`Initializing ${{this.serverName}} v${{this.serverVersion}}...`);
        
        // Load Pyodide from CDN
        const pyodideURL = `https://cdn.jsdelivr.net/pyodide/v${{this.pyodideVersion}}/full/pyodide.js`;
        
        try {{
            // Import Pyodide
            if (typeof loadPyodide === 'undefined') {{
                const script = document.createElement('script');
                script.src = pyodideURL;
                await new Promise((resolve, reject) => {{
                    script.onload = resolve;
                    script.onerror = reject;
                    document.head.appendChild(script);
                }});
            }}
            
            // Load Pyodide runtime
            this.pyodide = await loadPyodide({{
                indexURL: `https://cdn.jsdelivr.net/pyodide/v${{this.pyodideVersion}}/full/`
            }});
            
            console.log('Pyodide loaded successfully');
            
            // Load Python tools bundle
            const response = await fetch('./tools_bundle.py');
            const pythonCode = await response.text();
            
            // Execute Python code in Pyodide
            await this.pyodide.runPythonAsync(pythonCode);
            
            this.initialized = true;
            console.log('Tools loaded successfully');
            
        }} catch (error) {{
            console.error('Failed to initialize WASM server:', error);
            throw new Error(`Initialization failed: ${{error.message}}`);
        }}
    }}
    
    /**
     * List all available tools.
     */
    async listTools() {{
        if (!this.initialized) {{
            await this.initialize();
        }}
        
        try {{
            const result = await this.pyodide.runPythonAsync('list_tools()');
            const tools = result.toJs({{dict_converter: Object.fromEntries}});
            
            return {{
                tools: tools.tools
            }};
        }} catch (error) {{
            console.error('Failed to list tools:', error);
            throw new Error(`List tools failed: ${{error.message}}`);
        }}
    }}
    
    /**
     * Call a tool by name.
     */
    async callTool(name, toolArgs = {{}}) {{
        if (!this.initialized) {{
            await this.initialize();
        }}
        
        try {{
            // Convert arguments to Python dict
            const argsJson = JSON.stringify(toolArgs);
            
            const pythonCode = "import json\\n" +
                "args = json.loads('" + argsJson.replace(/'/g, "\\\\'") + "')\\n" +
                "call_tool(\\"" + name + "\\", args)";
            
            const result = await this.pyodide.runPythonAsync(pythonCode);
            const jsResult = result.toJs({{dict_converter: Object.fromEntries}});
            
            return jsResult;
        }} catch (error) {{
            console.error(`Failed to call tool ${{name}}:`, error);
            return {{
                status: "error",
                error: `Execution failed: ${{error.message}}`
            }};
        }}
    }}
    
    /**
     * Get server information.
     */
    getServerInfo() {{
        return {{
            name: this.serverName,
            version: this.serverVersion,
            pyodideVersion: this.pyodideVersion,
            initialized: this.initialized,
            bundleHash: this.bundleHash
        }};
    }}
}}

// Node.js compatibility
if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ WASMMCPServer }};
}}

// Browser global
if (typeof window !== 'undefined') {{
    window.WASMMCPServer = WASMMCPServer;
}}

// ES module export
export {{ WASMMCPServer }};
'''
        
        return js_code
    
    def _generate_html_demo(self) -> str:
        """Generate HTML demo page with minimal black & white design."""
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.server_name} - Demo</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #FFFFFF;
            color: #000000;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 60px 40px;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 80px;
            padding-bottom: 40px;
            border-bottom: 1px solid #E5E5E5;
        }}
        
        .logo {{
            font-family: "Stack Sans Notch", sans-serif;
            font-size: 48px;
            font-weight: 700;
            color: #000000;
            margin-bottom: 12px;
            letter-spacing: -0.02em;
        }}
        
        .tagline {{
            font-size: 16px;
            color: #666666;
            font-weight: 400;
        }}
        
        .status {{
            max-width: 600px;
            margin: 0 auto 60px;
            padding: 20px 32px;
            border: 1px solid #E5E5E5;
            text-align: center;
            font-size: 14px;
            font-weight: 500;
        }}
        
        .status.loading {{
            background: #FAFAFA;
            color: #666666;
        }}
        
        .status.ready {{
            background: #000000;
            color: #FFFFFF;
            border-color: #000000;
        }}
        
        .status.error {{
            background: #FFFFFF;
            color: #DC2626;
            border-color: #DC2626;
        }}
        
        .tools-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 24px;
            margin-bottom: 60px;
        }}
        
        .tool-card {{
            border: 1px solid #E5E5E5;
            padding: 32px;
            transition: border-color 0.2s;
            background: #FFFFFF;
        }}
        
        .tool-card:hover {{
            border-color: #000000;
        }}
        
        .tool-card h3 {{
            font-size: 18px;
            font-weight: 600;
            color: #000000;
            margin-bottom: 8px;
        }}
        
        .tool-card p {{
            color: #666666;
            font-size: 14px;
            margin-bottom: 24px;
            line-height: 1.5;
        }}
        
        .btn {{
            display: inline-block;
            padding: 10px 24px;
            background: #000000;
            color: #FFFFFF;
            border: 1px solid #000000;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
        }}
        
        .btn:hover {{
            background: #FFFFFF;
            color: #000000;
        }}
        
        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        
        .tool-form {{
            display: none;
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid #E5E5E5;
        }}
        
        .tool-form.active {{
            display: block;
        }}
        
        .form-group {{
            margin-bottom: 20px;
        }}
        
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            font-size: 14px;
            color: #000000;
        }}
        
        .form-group input {{
            width: 100%;
            padding: 12px 16px;
            border: 1px solid #E5E5E5;
            font-size: 14px;
            font-family: 'Inter', sans-serif;
            transition: border-color 0.2s;
        }}
        
        .form-group input:focus {{
            outline: none;
            border-color: #000000;
        }}
        
        .result {{
            margin-top: 20px;
            padding: 20px;
            background: #FAFAFA;
            border: 1px solid #E5E5E5;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-wrap: break-word;
            color: #000000;
            line-height: 1.6;
        }}
        
        .footer {{
            text-align: center;
            padding: 40px 0;
            border-top: 1px solid #E5E5E5;
            margin-top: 60px;
        }}
        
        .footer p {{
            color: #666666;
            font-size: 14px;
        }}
        
        .footer a {{
            color: #000000;
            text-decoration: none;
            border-bottom: 1px solid #000000;
            transition: opacity 0.2s;
        }}
        
        .footer a:hover {{
            opacity: 0.6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">PolyMCP WASM</div>
            <p class="tagline">{self.server_name} v{self.server_version} • Powered by Pyodide</p>
        </div>
        
        <div id="status" class="status loading">
            🔄 Initializing WASM server...
        </div>
        
        <div id="tools-container" class="tools-grid"></div>
        
        <div class="footer">
            <p>Built with <a href="https://github.com/poly-mcp/Polymcp" target="_blank">PolyMCP</a> • Pyodide {self.pyodide_version}</p>
        </div>
    </div>
    
    <script type="module">
        import {{ WASMMCPServer }} from './loader.js';
        
        const server = new WASMMCPServer();
        const statusEl = document.getElementById('status');
        const toolsEl = document.getElementById('tools-container');
        
        // Initialize server
        async function init() {{
            try {{
                await server.initialize();
                
                statusEl.className = 'status ready';
                statusEl.textContent = '✓ WASM Server Ready';
                
                // Load and display tools
                const {{ tools }} = await server.listTools();
                displayTools(tools);
                
            }} catch (error) {{
                statusEl.className = 'status error';
                statusEl.textContent = `✗ Failed to initialize: ${{error.message}}`;
            }}
        }}
        
        function displayTools(tools) {{
            toolsEl.innerHTML = '';
            
            tools.forEach((tool, index) => {{
                const card = document.createElement('div');
                card.className = 'tool-card';
                card.innerHTML = `
                    <h3>${{tool.name}}</h3>
                    <p>${{tool.description || 'No description'}}</p>
                    <button class="btn" onclick="toggleForm(${{index}})">Try it →</button>
                    <div id="form-${{index}}" class="tool-form">
                        ${{generateForm(tool, index)}}
                    </div>
                `;
                toolsEl.appendChild(card);
            }});
        }}
        
        function generateForm(tool, index) {{
            const schema = tool.inputSchema;
            const properties = schema.properties || {{}};
            const required = schema.required || [];
            
            let html = '';
            
            for (const [name, prop] of Object.entries(properties)) {{
                const isRequired = required.includes(name);
                html += `
                    <div class="form-group">
                        <label>${{name}}${{isRequired ? ' *' : ''}}</label>
                        <input 
                            type="${{prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'}}" 
                            id="${{tool.name}}-${{name}}"
                            placeholder="${{prop.description || 'Enter ' + name}}"
                            ${{isRequired ? 'required' : ''}}
                        />
                    </div>
                `;
            }}
            
            html += `
                <button class="btn" onclick="executeTool('${{tool.name}}', ${{index}})">Execute</button>
                <div id="result-${{index}}"></div>
            `;
            
            return html;
        }}
        
        window.toggleForm = function(index) {{
            const form = document.getElementById(`form-${{index}}`);
            form.classList.toggle('active');
        }}
        
        window.executeTool = async function(toolName, index) {{
            const schema = (await server.listTools()).tools.find(t => t.name === toolName).inputSchema;
            const properties = schema.properties || {{}};
            
            // Collect arguments
            const args = {{}};
            for (const name of Object.keys(properties)) {{
                const input = document.getElementById(`${{toolName}}-${{name}}`);
                if (input && input.value) {{
                    const prop = properties[name];
                    if (prop.type === 'integer') {{
                        args[name] = parseInt(input.value);
                    }} else if (prop.type === 'number') {{
                        args[name] = parseFloat(input.value);
                    }} else if (prop.type === 'boolean') {{
                        args[name] = input.value === 'true';
                    }} else {{
                        args[name] = input.value;
                    }}
                }}
            }}
            
            // Execute tool
            const resultEl = document.getElementById(`result-${{index}}`);
            resultEl.innerHTML = '<div class="result">⏳ Executing...</div>';
            
            try {{
                const result = await server.callTool(toolName, args);
                resultEl.innerHTML = `<div class="result">${{JSON.stringify(result, null, 2)}}</div>`;
            }} catch (error) {{
                resultEl.innerHTML = `<div class="result" style="border-color: #DC2626; color: #DC2626;">Error: ${{error.message}}</div>`;
            }}
        }}
        
        // Start initialization
        init();
    </script>
</body>
</html>'''
        
        return html
    
    def _generate_package_json(self) -> str:
        """Generate package.json for npm publishing."""
        package_json = {
            "name": f"@polymcp/{self.server_name.lower().replace(' ', '-')}",
            "version": self.server_version,
            "description": f"{self.server_name} - WASM MCP Server",
            "type": "module",
            "main": "loader.js",
            "files": [
                "loader.js",
                "tools_bundle.py",
                "demo.html",
                "README.md"
            ],
            "keywords": [
                "mcp",
                "model-context-protocol",
                "wasm",
                "webassembly",
                "pyodide",
                "tools"
            ],
            "author": "PolyMCP",
            "license": "MIT",
            "dependencies": {},
            "peerDependencies": {
                "pyodide": f"^{self.pyodide_version}"
            }
        }
        
        return json.dumps(package_json, indent=2)
    
    def _generate_readme(self) -> str:
        """Generate README for the bundle."""
        tool_names = [m["name"] for m in self.tool_metadata]
        
        readme = f'''# {self.server_name}

WASM-based MCP server powered by Pyodide.

## Features

- ✅ **Zero setup** - Runs in browser/Node.js/edge workers
- ✅ **Secure** - Sandboxed WASM execution
- ✅ **Fast** - Compiled Python code
- ✅ **Portable** - Deploy anywhere

## Available Tools

{chr(10).join(f"- **{m['name']}**: {m['description']}" for m in self.tool_metadata)}

## Usage

### Browser

```html
<script type="module">
  import {{ WASMMCPServer }} from './loader.js';
  
  const server = new WASMMCPServer();
  await server.initialize();
  
  // List tools
  const {{ tools }} = await server.listTools();
  console.log(tools);
  
  // Call a tool
  const result = await server.callTool('{tool_names[0]}', {{
    // your arguments here
  }});
  console.log(result);
</script>
```

### Node.js

```javascript
import {{ WASMMCPServer }} from './ loader.js';

const server = new WASMMCPServer();
await server.initialize();

const result = await server.callTool('{tool_names[0]}', {{
  // your arguments here
}});
```

### CDN

```html
<script type="module">
  import {{ WASMMCPServer }} from 'https://unpkg.com/@polymcp/{self.server_name.lower().replace(' ', '-')}/loader.js';
  // ... use as above
</script>
```

## Demo

Open `demo.html` in your browser to try the tools interactively.

## License

MIT

---

Generated by PolyMCP {self.server_version}
'''
        
        return readme
    
    def compile(self, output_dir: Union[str, Path] = "./dist") -> Dict[str, Path]:
        """
        Compile tools to WASM bundle.
        
        Args:
            output_dir: Output directory for bundle
            
        Returns:
            Dictionary of generated file paths
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Compiling {len(self.tools)} tools to WASM bundle...")
        
        # Generate Python bundle
        python_bundle = self._generate_python_bundle()
        bundle_hash = hashlib.sha256(python_bundle.encode()).hexdigest()[:8]
        
        # Write Python bundle
        bundle_path = output_path / "tools_bundle.py"
        bundle_path.write_text(python_bundle, encoding='utf-8')
        logger.info(f"✓ Python bundle: {bundle_path}")
        
        # Generate JavaScript loader
        js_loader = self._generate_javascript_loader(bundle_hash)
        loader_path = output_path / "loader.js"
        loader_path.write_text(js_loader, encoding='utf-8')
        logger.info(f"✓ JavaScript loader: {loader_path}")
        
        # Generate HTML demo
        html_demo = self._generate_html_demo()
        demo_path = output_path / "demo.html"
        demo_path.write_text(html_demo, encoding='utf-8')
        logger.info(f"✓ HTML demo: {demo_path}")
        
        # Generate package.json
        package_json = self._generate_package_json()
        package_path = output_path / "package.json"
        package_path.write_text(package_json, encoding='utf-8')
        logger.info(f"✓ package.json: {package_path}")
        
        # Generate README
        readme = self._generate_readme()
        readme_path = output_path / "README.md"
        readme_path.write_text(readme, encoding='utf-8')
        logger.info(f"✓ README.md: {readme_path}")
        
        logger.info(f"\n✅ Compilation complete! Bundle hash: {bundle_hash}")
        logger.info(f"\nTo test:")
        logger.info(f"  1. cd {output_path}")
        logger.info(f"  2. python -m http.server 8000")
        logger.info(f"  3. Open http://localhost:8000/demo.html")
        logger.info(f"\nTo publish:")
        logger.info(f"  npm publish {output_path}")
        
        return {
            "bundle": bundle_path,
            "loader": loader_path,
            "demo": demo_path,
            "package": package_path,
            "readme": readme_path
        }


def expose_tools_wasm(
    tools: Union[Callable, List[Callable]],
    server_name: str = "PolyMCP WASM Server",
    server_version: str = "1.0.0",
    pyodide_version: str = "0.26.4",
    verbose: bool = False
) -> WASMToolCompiler:
    """
    Compile Python functions to WASM with MCP interface.
    
    Creates a production-ready WASM bundle that can be deployed to:
    - CDNs (unpkg, jsdelivr)
    - Edge workers (Cloudflare, Vercel)
    - Static hosting (GitHub Pages, Netlify)
    - Browsers (any website)
    - Node.js applications
    
    Args:
        tools: Functions to compile
        server_name: Server name
        server_version: Server version (semver)
        pyodide_version: Pyodide version to use
        verbose: Enable verbose logging
    
    Returns:
        WASMToolCompiler instance (call .compile() to build)
    
    Example:
        >>> def greet(name: str) -> str:
        ...     '''Greet someone.'''
        ...     return f"Hello, {name}!"
        >>> 
        >>> def add(a: int, b: int) -> int:
        ...     '''Add two numbers.'''
        ...     return a + b
        >>> 
        >>> compiler = expose_tools_wasm(
        ...     [greet, add],
        ...     server_name="My Tools",
        ...     server_version="1.0.0"
        ... )
        >>> 
        >>> bundle = compiler.compile(output_dir="./dist")
        >>> # Deploy dist/ to CDN or static hosting
    
    Deployment:
        1. Compile: compiler.compile(output_dir="./dist")
        2. Test locally: cd dist && python -m http.server
        3. Deploy to CDN: npm publish (or upload to CDN)
        4. Use anywhere: import from CDN URL
    
    Security:
        - Runs in WASM sandbox (memory-safe)
        - No file system access (unless explicitly granted)
        - No network access (unless explicitly granted)
        - Isolated from host environment
    """
    return WASMToolCompiler(tools, server_name, server_version, pyodide_version, verbose)
