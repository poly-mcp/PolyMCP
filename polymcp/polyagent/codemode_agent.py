"""
CodeMode Agent - LLM Code Generation for Tool Orchestration
Production implementation of "Code Mode" paradigm for efficient tool usage.
"""

import json
import re
import requests
import asyncio
from typing import List, Dict, Any, Optional
from .llm_providers import LLMProvider
from ..sandbox.executor import SandboxExecutor, ExecutionResult
from ..sandbox.tools_api import ToolsAPI


class CodeModeAgent:
    """
    Code Mode Agent - Generates code instead of calling tools directly.
    
    Instead of traditional tool calling (multiple LLM roundtrips),
    this agent generates a single Python code block that orchestrates
    all necessary tool calls. The code is executed in a secure sandbox.
    
    Benefits (from benchmarks):
    - 60% faster execution (fewer LLM calls)
    - 68% lower token usage
    - Better for multi-step workflows
    - Natural programming constructs (loops, variables, conditions)
    
    Example:
        >>> agent = CodeModeAgent(
        ...     llm_provider=OpenAIProvider(),
        ...     mcp_servers=["http://localhost:8000/mcp"]
        ... )
        >>> result = agent.run("Create 3 transactions and generate summary")
    """
    
    SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant that writes Python code to accomplish tasks.

You have access to tools through the `tools` object. Each tool is a method you can call.

AVAILABLE TOOLS:
{tools_documentation}

RULES:
1. Import json at the start
2. Call tools using: tools.tool_name(param1=value1, param2=value2)
3. Tools return JSON strings - parse with json.loads()
4. Print progress and results clearly
5. Handle errors with try-except
6. Use loops, conditions, variables as needed

Write ONLY Python code between ```python and ``` tags. No explanations.

Example pattern:
```python
import json

# Your code here
result_json = tools.some_tool(param1="value1", param2="value2")
result = json.loads(result_json)
print(f"Result: {{result}}")  # NOTA: doppie parentesi graffe!
```"""

    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_servers: Optional[List[str]] = None,
        stdio_servers: Optional[List[Dict[str, Any]]] = None,
        registry_path: Optional[str] = None,
        sandbox_timeout: float = 30.0,
        max_retries: int = 2,
        verbose: bool = False
    ):
        """
        Initialize Code Mode Agent.
        
        Args:
            llm_provider: LLM provider instance
            mcp_servers: List of HTTP MCP server URLs
            stdio_servers: List of stdio server configurations
            registry_path: Path to tool registry JSON
            sandbox_timeout: Code execution timeout in seconds
            max_retries: Maximum retries for failed executions
            verbose: Enable verbose logging
        """
        self.llm_provider = llm_provider
        self.mcp_servers = mcp_servers or []
        self.stdio_servers = stdio_servers or []
        self.sandbox_timeout = sandbox_timeout
        self.max_retries = max_retries
        self.verbose = verbose
        
        # Tool discovery
        self.http_tools_cache: Dict[str, List[Dict]] = {}
        self.stdio_clients: Dict[str, Any] = {}
        self.stdio_adapters: Dict[str, Any] = {}
        
        if registry_path:
            self._load_registry(registry_path)
        
        # Discover HTTP tools immediately
        self._discover_http_tools()
        
        # Stdio servers are started on demand (async)
        self._stdio_started = False
    
    def _load_registry(self, registry_path: str) -> None:
        """Load servers from registry file."""
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry = json.load(f)
                
                http_servers = registry.get('servers', [])
                self.mcp_servers.extend(http_servers)
                
                stdio_servers = registry.get('stdio_servers', [])
                self.stdio_servers.extend(stdio_servers)
                
                if self.verbose:
                    print(f"Loaded {len(http_servers)} HTTP and {len(stdio_servers)} stdio servers")
        
        except Exception as e:
            if self.verbose:
                print(f"Failed to load registry: {e}")
    
    def _discover_http_tools(self) -> None:
        """Discover tools from HTTP MCP servers."""
        for server_url in self.mcp_servers:
            try:
                list_url = f"{server_url}/list_tools"
                response = requests.get(list_url, timeout=5)
                response.raise_for_status()
                
                tools = response.json().get('tools', [])
                self.http_tools_cache[server_url] = tools
                
                if self.verbose:
                    print(f"Discovered {len(tools)} tools from {server_url}")
            
            except Exception as e:
                if self.verbose:
                    print(f"Failed to discover tools from {server_url}: {e}")
    
    async def _start_stdio_servers(self) -> None:
        """Start stdio MCP servers if configured."""
        if self._stdio_started or not self.stdio_servers:
            return
        
        from ..mcp_stdio_client import MCPStdioClient, MCPStdioAdapter, MCPServerConfig
        
        for config_dict in self.stdio_servers:
            try:
                config = MCPServerConfig(
                    command=config_dict['command'],
                    args=config_dict.get('args', []),
                    env=config_dict.get('env')
                )
                
                client = MCPStdioClient(config)
                await client.start()
                
                adapter = MCPStdioAdapter(client)
                
                server_id = f"stdio://{config.command}"
                self.stdio_clients[server_id] = client
                self.stdio_adapters[server_id] = adapter
                
                if self.verbose:
                    tools = await adapter.get_tools()
                    print(f"Started stdio server: {server_id} ({len(tools)} tools)")
            
            except Exception as e:
                if self.verbose:
                    print(f"Failed to start stdio server: {e}")
        
        self._stdio_started = True
        
        if self.stdio_clients:
            await asyncio.sleep(2)
    
    def _generate_tools_documentation(self) -> str:
        """
        Generate CLEAR and SIMPLE API documentation for all available tools.
        
        Returns:
            Formatted documentation string
        """
        docs = []
        
        # HTTP tools
        for server_url, tools in self.http_tools_cache.items():
            for tool in tools:
                tool_name = tool.get('name', 'unknown')
                description = tool.get('description', 'No description')
                input_schema = tool.get('input_schema', {})
                
                # Get EXACT parameters
                properties = input_schema.get('properties', {})
                required = input_schema.get('required', [])
                
                # Build EXACT parameter signature
                param_examples = []
                for param_name in required:
                    param_info = properties.get(param_name, {})
                    param_type = param_info.get('type', 'string')
                    
                    # Generate appropriate example value
                    if param_type == 'string':
                        if 'type' in param_name:
                            example_value = '"expense"'
                        elif 'category' in param_name:
                            example_value = '"rent"'
                        elif 'description' in param_name:
                            example_value = '"Monthly payment"'
                        elif 'name' in param_name:
                            example_value = '"Client Name"'
                        elif 'items' in param_name:
                            example_value = '"item1,item2"'
                        else:
                            example_value = f'"{param_name}_value"'
                    elif param_type in ['number', 'integer']:
                        example_value = '1000'
                    elif param_type == 'boolean':
                        example_value = 'True'
                    elif param_type == 'array':
                        example_value = '["item1", "item2"]'
                    else:
                        example_value = 'value'
                    
                    param_examples.append(f'{param_name}={example_value}')
                
                # Create EXACT call signature
                signature = f"tools.{tool_name}({', '.join(param_examples)})"
                
                # Simple documentation
                doc = f"""
tools.{tool_name}():
  Description: {description}
  Signature: {signature}
  Returns: JSON string"""
                docs.append(doc)
        
        return "\n".join(docs) if docs else "No tools available"
    
    def _extract_code_from_response(self, response: str) -> Optional[str]:
        """
        Extract Python code from LLM response.
        
        Args:
            response: LLM response text
            
        Returns:
            Extracted code or None
        """
        # Look for ```python code blocks
        patterns = [
            r'```python\s*(.*?)```',
            r'```py\s*(.*?)```',
            r'```\s*(.*?)```'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
            if matches:
                code = matches[0].strip()
                # Verify it looks like Python code
                if 'import json' in code or 'tools.' in code:
                    return code
        
        # Last resort: check if response is code
        if 'import json' in response and 'tools.' in response:
            # Clean up response
            lines = response.strip().split('\n')
            # Remove non-code lines
            code_lines = []
            in_code = False
            for line in lines:
                if 'import json' in line or in_code:
                    in_code = True
                    code_lines.append(line)
            return '\n'.join(code_lines) if code_lines else None
        
        return None
    
    def _create_tools_api(self) -> ToolsAPI:
        """
        Create ToolsAPI instance with current tool state.
        
        Returns:
            ToolsAPI instance
        """
        def http_executor(server_url: str, tool_name: str, parameters: Dict) -> Dict:
            """Execute HTTP tool."""
            try:
                invoke_url = f"{server_url}/invoke/{tool_name}"
                response = requests.post(invoke_url, json=parameters, timeout=30)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {"error": str(e), "status": "error"}
        
        async def stdio_executor(server_id: str, tool_name: str, parameters: Dict) -> Dict:
            """Execute stdio tool."""
            adapter = self.stdio_adapters.get(server_id)
            if not adapter:
                return {"error": "Stdio adapter not found", "status": "error"}
            return await adapter.invoke_tool(tool_name, parameters)
        
        return ToolsAPI(
            http_tools=self.http_tools_cache,
            stdio_adapters=self.stdio_adapters,
            http_executor=http_executor,
            stdio_executor=stdio_executor,
            verbose=self.verbose
        )
    
    def _generate_code(self, user_message: str, previous_error: Optional[str] = None) -> Optional[str]:
        """
        Use LLM to generate code for the task - SIMPLE like UnifiedPolyAgent.
        
        Args:
            user_message: User's request
            previous_error: Previous error if retrying
            
        Returns:
            Generated Python code or None
        """
        tools_docs = self._generate_tools_documentation()
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            tools_documentation=tools_docs
        )
        
        # Build user prompt
        user_prompt = f"USER REQUEST: {user_message}"
        
        if previous_error:
            user_prompt += f"\n\nPREVIOUS ERROR: {previous_error}\nPlease fix the error and generate corrected code."
        
        user_prompt += "\n\nWrite Python code:"
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            if self.verbose:
                print(f"\n{'='*60}")
                print("GENERATING CODE")
                print(f"{'='*60}")
                print(f"User request: {user_message}")
                print(f"Available tools: {sum(len(t) for t in self.http_tools_cache.values())}")
            
            response = self.llm_provider.generate(full_prompt)
            
            code = self._extract_code_from_response(response)
            
            if code:
                if self.verbose:
                    print(f"\n✅ Code generated ({len(code)} chars)")
                    print(f"\nGenerated code:")
                    print("="*60)
                    print(code)
                    print("="*60)
                return code
            else:
                if self.verbose:
                    print(f"\n❌ No valid code found in LLM response")
                    print(f"Response preview: {response[:200]}...")
                return None
        
        except Exception as e:
            if self.verbose:
                print(f"\n❌ Code generation failed: {e}")
            return None
    
    def _execute_code(self, code: str) -> ExecutionResult:
        """
        Execute generated code in sandbox.
        
        Args:
            code: Python code to execute
            
        Returns:
            ExecutionResult
        """
        tools_api = self._create_tools_api()
        
        executor = SandboxExecutor(
            tools_api=tools_api,
            timeout=self.sandbox_timeout,
            verbose=self.verbose
        )
        
        return executor.execute(code)
    
    def run(self, user_message: str) -> str:
        """
        Process user request with code generation approach.
        
        Args:
            user_message: User's request
            
        Returns:
            Response string
        """
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"CODE MODE AGENT")
            print(f"{'='*60}")
            print(f"User: {user_message}\n")
        
        previous_error = None
        
        for attempt in range(self.max_retries + 1):
            if attempt > 0 and self.verbose:
                print(f"\n🔄 Retry {attempt}/{self.max_retries}")
            
            # Generate code
            code = self._generate_code(user_message, previous_error)
            
            if not code:
                if attempt < self.max_retries:
                    previous_error = "Failed to generate valid Python code"
                    continue
                return "I couldn't generate appropriate code for your request. Please try rephrasing."
            
            # Execute code
            result = self._execute_code(code)
            
            if result.success:
                if self.verbose:
                    print(f"\n✅ Execution successful ({result.execution_time:.2f}s)")
                    if result.output:
                        print(f"Output preview: {result.output[:200]}...")
                
                # Return the output from code execution
                if result.output:
                    return result.output
                else:
                    return "Task completed successfully."
            
            else:
                if self.verbose:
                    print(f"\n❌ Execution failed: {result.error}")
                
                previous_error = result.error
                
                # On last attempt, return error
                if attempt >= self.max_retries:
                    return f"I encountered an error: {result.error}"
        
        return "Failed to complete the task."
    
    async def run_async(self, user_message: str) -> str:
        """
        Async version of run() with stdio server support.
        
        Args:
            user_message: User's request
            
        Returns:
            Response string
        """
        # Start stdio servers if needed
        await self._start_stdio_servers()
        
        # Rest is same as sync version
        return self.run(user_message)
    
    def add_server(self, server_url: str) -> None:
        """
        Add new HTTP MCP server.
        
        Args:
            server_url: URL of MCP server
        """
        if server_url not in self.mcp_servers:
            self.mcp_servers.append(server_url)
            
            try:
                list_url = f"{server_url}/list_tools"
                response = requests.get(list_url, timeout=5)
                response.raise_for_status()
                
                tools = response.json().get('tools', [])
                self.http_tools_cache[server_url] = tools
                
                if self.verbose:
                    print(f"Added server {server_url} with {len(tools)} tools")
            
            except Exception as e:
                if self.verbose:
                    print(f"Failed to add server {server_url}: {e}")


class AsyncCodeModeAgent(CodeModeAgent):
    """
    Async-first Code Mode Agent with full stdio support.
    
    Use this version when working with stdio MCP servers.
    """
    
    async def run_async(self, user_message: str) -> str:
        """
        Process user request asynchronously.
        
        Args:
            user_message: User's request
            
        Returns:
            Response string
        """
        # Start stdio servers
        await self._start_stdio_servers()
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"ASYNC CODE MODE AGENT")
            print(f"{'='*60}")
            print(f"User: {user_message}\n")
        
        # Add stdio tools to documentation
        for server_id, adapter in self.stdio_adapters.items():
            try:
                tools = await adapter.get_tools()
                # Temporarily add to cache for documentation generation
                self.http_tools_cache[server_id] = tools
            except Exception as e:
                if self.verbose:
                    print(f"Failed to get stdio tools from {server_id}: {e}")
        
        # Use parent's run() which is now sync-safe
        return self.run(user_message)
    
    async def stop(self) -> None:
        """Stop all stdio servers."""
        for client in self.stdio_clients.values():
            await client.stop()
        
        self.stdio_clients.clear()
        self.stdio_adapters.clear()
        self._stdio_started = False
    
    async def __aenter__(self):
        """Context manager entry."""
        await self._start_stdio_servers()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.stop()