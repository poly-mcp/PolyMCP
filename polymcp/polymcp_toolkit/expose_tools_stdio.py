"""
MCP Stdio Server - Production Implementation
Expose Python functions as MCP tools via stdio (JSON-RPC 2.0).

This allows creating npm-publishable MCP servers like @playwright/mcp.
"""

import sys
import json
import asyncio
import inspect
import signal
import logging
import platform
import threading
import queue
from typing import Callable, List, Dict, Any, Optional, Union, get_type_hints
from dataclasses import dataclass
from pydantic import BaseModel, create_model, Field, ValidationError
from docstring_parser import parse


# Configure logging
logger = logging.getLogger("polymcp.stdio")


@dataclass
class ServerCapabilities:
    """MCP Server capabilities."""
    tools: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {"tools": self.tools}


class StdioMCPServer:
    """
    Production MCP server using JSON-RPC 2.0 over stdio.
    
    Implements the full MCP protocol (2024-11-05) for stdio transport:
    - initialize: Protocol handshake
    - tools/list: List available tools
    - tools/call: Execute a tool
    - Proper error handling with JSON-RPC error codes
    - Graceful shutdown on SIGINT/SIGTERM
    
    Example:
        >>> def greet(name: str) -> str:
        ...     '''Greet someone by name.'''
        ...     return f"Hello, {name}!"
        >>> 
        >>> server = StdioMCPServer([greet])
        >>> server.run()  # Listens on stdin, responds on stdout
    """
    
    def __init__(
        self,
        tools: Union[Callable, List[Callable]],
        server_name: str = "PolyMCP Stdio Server",
        server_version: str = "1.0.0",
        verbose: bool = False
    ):
        """
        Initialize stdio MCP server.
        
        Args:
            tools: Single function or list of functions to expose
            server_name: Server name for identification
            server_version: Server version
            verbose: Enable verbose logging
        """
        if not isinstance(tools, list):
            tools = [tools]
        
        if not tools:
            raise ValueError("At least one tool must be provided")
        
        self.tools = tools
        self.server_name = server_name
        self.server_version = server_version
        self.verbose = verbose
        
        # Build tool registry
        self.tool_registry = self._build_tool_registry()
        
        # Server state
        self.initialized = False
        self.running = False
        self.request_id_counter = 0
        
        # Statistics
        self.stats = {
            "requests_received": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "tools_executed": 0
        }
        
        # Setup logging
        if verbose:
            logging.basicConfig(
                level=logging.DEBUG,
                format='[%(asctime)s] %(levelname)s: %(message)s',
                stream=sys.stderr  # Log to stderr, keep stdout for JSON-RPC
            )
        else:
            logging.basicConfig(
                level=logging.WARNING,
                stream=sys.stderr
            )
    
    def _extract_function_metadata(self, func: Callable) -> Dict[str, Any]:
        """Extract metadata from function using type hints and docstring."""
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
            
            # Convert Python type to JSON Schema type
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
        
        return {
            "name": func.__name__,
            "description": description,
            "inputSchema": input_schema,
            "is_async": asyncio.iscoroutinefunction(func)
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
        
        # Handle Union types (e.g., Optional[str])
        origin = getattr(python_type, '__origin__', None)
        if origin is Union:
            # Get first non-None type
            args = getattr(python_type, '__args__', ())
            for arg in args:
                if arg is not type(None):
                    return self._python_type_to_json_type(arg)
        
        return type_map.get(python_type, "string")
    
    def _build_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        """Build registry of tools with metadata and validation models."""
        registry = {}
        
        for func in self.tools:
            metadata = self._extract_function_metadata(func)
            
            # Create Pydantic model for input validation
            input_fields = {}
            schema = metadata["inputSchema"]
            
            for prop_name, prop_def in schema.get("properties", {}).items():
                # Map JSON type to Python type
                json_type = prop_def.get("type", "string")
                python_type = {
                    "string": str,
                    "integer": int,
                    "number": float,
                    "boolean": bool,
                    "array": list,
                    "object": dict
                }.get(json_type, str)
                
                is_required = prop_name in schema.get("required", [])
                
                if is_required:
                    input_fields[prop_name] = (
                        python_type,
                        Field(description=prop_def.get("description", ""))
                    )
                else:
                    input_fields[prop_name] = (
                        Optional[python_type],
                        Field(default=None, description=prop_def.get("description", ""))
                    )
            
            input_model = create_model(
                f"{metadata['name']}_Input",
                **input_fields
            ) if input_fields else None
            
            registry[metadata["name"]] = {
                "metadata": metadata,
                "function": func,
                "input_model": input_model,
                "is_async": metadata["is_async"]
            }
        
        return registry
    
    def _send_response(self, response: Dict[str, Any]) -> None:
        """Send JSON-RPC response to stdout."""
        response_json = json.dumps(response)
        sys.stdout.write(response_json + "\n")
        sys.stdout.flush()
        
        if self.verbose:
            logger.debug(f"Sent response: {response.get('id')}")
    
    def _send_error(
        self,
        request_id: Optional[int],
        code: int,
        message: str,
        data: Optional[Any] = None
    ) -> None:
        """Send JSON-RPC error response."""
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }
        
        if data is not None:
            error_response["error"]["data"] = data
        
        self._send_response(error_response)
        self.stats["requests_failed"] += 1
    
    async def _handle_initialize(
        self,
        request_id: int,
        params: Dict[str, Any]
    ) -> None:
        """Handle initialize request."""
        protocol_version = params.get("protocolVersion", "")
        client_info = params.get("clientInfo", {})
        
        logger.info(f"Initialize request from {client_info.get('name', 'unknown')}")
        
        # Validate protocol version
        if not protocol_version.startswith("2024-"):
            self._send_error(
                request_id,
                -32600,
                f"Unsupported protocol version: {protocol_version}"
            )
            return
        
        self.initialized = True
        
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": ServerCapabilities(
                    tools={}
                ).to_dict(),
                "serverInfo": {
                    "name": self.server_name,
                    "version": self.server_version
                }
            }
        }
        
        self._send_response(response)
        self.stats["requests_successful"] += 1
        
        logger.info("Server initialized successfully")
    
    async def _handle_tools_list(self, request_id: int) -> None:
        """Handle tools/list request."""
        if not self.initialized:
            self._send_error(
                request_id,
                -32002,
                "Server not initialized. Call 'initialize' first."
            )
            return
        
        tools_list = []
        for tool_name, tool_info in self.tool_registry.items():
            tools_list.append({
                "name": tool_info["metadata"]["name"],
                "description": tool_info["metadata"]["description"],
                "inputSchema": tool_info["metadata"]["inputSchema"]
            })
        
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools_list
            }
        }
        
        self._send_response(response)
        self.stats["requests_successful"] += 1
        
        logger.info(f"Listed {len(tools_list)} tools")
    
    async def _handle_tools_call(
        self,
        request_id: int,
        params: Dict[str, Any]
    ) -> None:
        """Handle tools/call request."""
        if not self.initialized:
            self._send_error(
                request_id,
                -32002,
                "Server not initialized. Call 'initialize' first."
            )
            return
        
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            self._send_error(
                request_id,
                -32602,
                "Missing required parameter: name"
            )
            return
        
        if tool_name not in self.tool_registry:
            self._send_error(
                request_id,
                -32601,
                f"Tool not found: {tool_name}",
                {"available_tools": list(self.tool_registry.keys())}
            )
            return
        
        tool = self.tool_registry[tool_name]
        
        # Validate input
        if tool["input_model"]:
            try:
                validated = tool["input_model"](**arguments)
                arguments = validated.model_dump(exclude_none=True)
            except ValidationError as e:
                self._send_error(
                    request_id,
                    -32602,
                    "Invalid arguments",
                    {"errors": e.errors()}
                )
                return
        
        # Execute tool
        try:
            logger.info(f"Executing tool: {tool_name}")
            
            if tool["is_async"]:
                result = await tool["function"](**arguments)
            else:
                # Run sync function in executor to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: tool["function"](**arguments)
                )
            
            # Format result according to MCP spec
            # Result should be an array of content items
            if isinstance(result, str):
                content = [{
                    "type": "text",
                    "text": result
                }]
            elif isinstance(result, dict):
                content = [{
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }]
            elif isinstance(result, list):
                content = [{
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }]
            else:
                content = [{
                    "type": "text",
                    "text": str(result)
                }]
            
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": content
                }
            }
            
            self._send_response(response)
            self.stats["requests_successful"] += 1
            self.stats["tools_executed"] += 1
            
            logger.info(f"Tool {tool_name} executed successfully")
        
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            self._send_error(
                request_id,
                -32603,
                f"Tool execution failed: {str(e)}"
            )
    
    async def _handle_request(self, request: Dict[str, Any]) -> None:
        """Handle incoming JSON-RPC request."""
        self.stats["requests_received"] += 1
        
        # Validate JSON-RPC structure
        if request.get("jsonrpc") != "2.0":
            self._send_error(
                request.get("id"),
                -32600,
                "Invalid JSON-RPC version"
            )
            return
        
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        
        if not method:
            self._send_error(
                request_id,
                -32600,
                "Missing method"
            )
            return
        
        # Route to appropriate handler
        if method == "initialize":
            await self._handle_initialize(request_id, params)
        elif method == "tools/list":
            await self._handle_tools_list(request_id)
        elif method == "tools/call":
            await self._handle_tools_call(request_id, params)
        else:
            self._send_error(
                request_id,
                -32601,
                f"Method not found: {method}"
            )
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.running = False
            
            # Send final stats to stderr
            if self.verbose:
                logger.info(f"Final stats: {self.stats}")
            
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _run_async(self) -> None:
        """Async main loop - read from stdin, process requests."""
        self.running = True
        
        logger.info(f"Starting {self.server_name} v{self.server_version}")
        logger.info(f"Registered {len(self.tool_registry)} tools")
        
        # Windows fix: Use threading for stdin instead of asyncio pipes
        # ProactorEventLoop on Windows doesn't support stdin pipes
        is_windows = platform.system() == 'Windows'
        
        if is_windows:
            # Windows: Use thread to read stdin synchronously
            input_queue = queue.Queue()
            
            def stdin_reader():
                """Read from stdin in thread (Windows workaround)."""
                try:
                    for line in sys.stdin:
                        input_queue.put(line.strip())
                except Exception as e:
                    logger.error(f"Stdin reader error: {e}")
                finally:
                    input_queue.put(None)  # Signal EOF
            
            # Start stdin reader thread
            thread = threading.Thread(target=stdin_reader, daemon=True)
            thread.start()
            
            # Process lines from queue
            loop = asyncio.get_event_loop()
            while self.running:
                try:
                    # Poll queue with timeout (non-blocking)
                    try:
                        line = await loop.run_in_executor(
                            None,
                            input_queue.get,
                            True,  # block
                            1.0    # timeout
                        )
                    except queue.Empty:
                        continue
                    
                    if line is None:
                        # EOF
                        logger.info("Client disconnected (EOF)")
                        break
                    
                    if not line:
                        continue
                    
                    # Parse JSON-RPC request
                    try:
                        request = json.loads(line)
                        await self._handle_request(request)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON: {e}")
                        self._send_error(None, -32700, f"Parse error: {str(e)}")
                
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    break
        
        else:
            # Unix/Linux: Use asyncio pipes (original implementation)
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            
            while self.running:
                try:
                    # Read one line (one JSON-RPC request)
                    line = await asyncio.wait_for(
                        reader.readline(),
                        timeout=1.0
                    )
                    
                    if not line:
                        # EOF - client disconnected
                        logger.info("Client disconnected (EOF)")
                        break
                    
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    
                    # Parse JSON-RPC request
                    try:
                        request = json.loads(line)
                        await self._handle_request(request)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON: {e}")
                        self._send_error(
                            None,
                            -32700,
                            f"Parse error: {str(e)}"
                        )
                
                except asyncio.TimeoutError:
                    # No data, continue loop
                    continue
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    break
        
        logger.info("Server stopped")
    
    def run(self) -> None:
        """
        Run the stdio MCP server.
        
        Blocks until server is stopped (SIGINT/SIGTERM or EOF on stdin).
        """
        self._setup_signal_handlers()
        
        try:
            asyncio.run(self._run_async())
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            sys.exit(1)


def expose_tools_stdio(
    tools: Union[Callable, List[Callable]],
    server_name: str = "PolyMCP Stdio Server",
    server_version: str = "1.0.0",
    verbose: bool = False
) -> StdioMCPServer:
    """
    Expose Python functions as MCP tools via stdio (JSON-RPC 2.0).
    
    Creates a production-ready MCP server that can be published to npm
    and used with Claude Desktop, Cline, or any MCP client.
    
    Args:
        tools: Single function or list of functions to expose
        server_name: Server name for identification
        server_version: Server version (semver)
        verbose: Enable verbose logging
    
    Returns:
        StdioMCPServer instance (call .run() to start)
    
    Example:
        >>> def greet(name: str, title: str = "Friend") -> str:
        ...     '''Greet someone with their title.
        ...     
        ...     Args:
        ...         name: Person's name
        ...         title: Optional title (default: "Friend")
        ...     '''
        ...     return f"Hello, {title} {name}!"
        >>> 
        >>> server = expose_tools_stdio(greet, verbose=True)
        >>> server.run()  # Run server (blocks)
    
    NPM Publishing:
        1. Create package.json:
           {
             "name": "@myorg/my-mcp-server",
             "version": "1.0.0",
             "type": "module",
             "bin": {
               "my-mcp-server": "./dist/index.js"
             }
           }
        
        2. Create index.js wrapper:
           #!/usr/bin/env node
           import { spawn } from 'child_process';
           const server = spawn('python', ['server.py']);
           server.stdout.pipe(process.stdout);
           process.stdin.pipe(server.stdin);
        
        3. Publish: npm publish
        
        4. Use: npx @myorg/my-mcp-server
    """
    return StdioMCPServer(tools, server_name, server_version, verbose)
