"""
Tools API - Python Wrapper for MCP Tools
Provides clean Python interface for LLM-generated code to call MCP tools.
"""

import json
import asyncio
from typing import Dict, Any, List, Optional, Union


class ToolsAPI:
    """
    Python API wrapper for MCP tools.
    
    Provides a clean interface for code to call MCP tools without
    worrying about HTTP/stdio differences or JSON serialization.
    
    Example:
        # In LLM-generated code:
        result = tools.create_transaction("expense", "rent", 2500.0, "Monthly rent")
        data = json.loads(result)
        print(data["new_balance"])
    """
    
    def __init__(
        self,
        http_tools: Dict[str, List[Dict[str, Any]]],
        stdio_adapters: Dict[str, Any],
        http_executor: callable,
        stdio_executor: callable,
        verbose: bool = False
    ):
        """
        Initialize Tools API.
        
        Args:
            http_tools: Dictionary of HTTP server URL -> tools list
            stdio_adapters: Dictionary of stdio server ID -> adapter
            http_executor: Function to execute HTTP tools
            stdio_executor: Async function to execute stdio tools
            verbose: Enable verbose logging
        """
        self.http_tools = http_tools
        self.stdio_adapters = stdio_adapters
        self.http_executor = http_executor
        self.stdio_executor = stdio_executor
        self.verbose = verbose
        
        # Build tool name -> (server, tool_info) mapping
        self._tool_registry: Dict[str, tuple[str, Dict, str]] = {}
        self._build_registry()
        
        # Dynamically create methods for each tool
        self._create_tool_methods()
    
    def _build_registry(self) -> None:
        """Build internal registry of all available tools."""
        # Register HTTP tools
        for server_url, tools in self.http_tools.items():
            for tool in tools:
                tool_name = tool['name']
                self._tool_registry[tool_name] = (server_url, tool, 'http')
        
        # Register stdio tools (would need to be passed in)
        # For now, we'll handle this via the adapters
        if self.verbose:
            print(f"Registered {len(self._tool_registry)} tools")
    
    def _create_tool_methods(self) -> None:
        """Dynamically create methods for each tool."""
        for tool_name in self._tool_registry.keys():
            # Create a closure to capture tool_name
            def make_method(name):
                def method(**kwargs):
                    return self._call_tool(name, kwargs)
                return method
            
            # Set as attribute with proper name
            setattr(self, tool_name, make_method(tool_name))
    
    def _call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Call a tool by name with parameters.
        
        Args:
            tool_name: Name of tool to call
            parameters: Tool parameters
            
        Returns:
            JSON string with tool result
            
        Raises:
            ValueError: If tool not found
            RuntimeError: If tool execution fails
        """
        if tool_name not in self._tool_registry:
            available = ", ".join(sorted(self._tool_registry.keys()))
            raise ValueError(
                f"Tool '{tool_name}' not found. Available tools: {available}"
            )
        
        server, tool_info, server_type = self._tool_registry[tool_name]
        
        if self.verbose:
            print(f"Calling tool: {tool_name} with params: {parameters}")
        
        try:
            if server_type == 'http':
                result = self.http_executor(server, tool_name, parameters)
            else:
                # stdio tools need async execution
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're already in async context
                    raise RuntimeError(
                        "Cannot call stdio tools from sync context within async loop"
                    )
                result = asyncio.run(self.stdio_executor(server, tool_name, parameters))
            
            # Always return JSON string for consistency
            if isinstance(result, str):
                # Verify it's valid JSON
                json.loads(result)
                return result
            else:
                return json.dumps(result)
        
        except Exception as e:
            error_result = {
                "status": "error",
                "error": str(e),
                "tool": tool_name
            }
            return json.dumps(error_result)
    
    def list_tools(self) -> List[str]:
        """
        List all available tool names.
        
        Returns:
            List of tool names
        """
        return sorted(self._tool_registry.keys())
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific tool.
        
        Args:
            tool_name: Name of tool
            
        Returns:
            Tool information dictionary or None
        """
        if tool_name not in self._tool_registry:
            return None
        
        _, tool_info, _ = self._tool_registry[tool_name]
        return tool_info
    
    def __getattr__(self, name: str):
        """
        Fallback for dynamic tool access.
        
        Args:
            name: Tool name
            
        Returns:
            Callable for tool
            
        Raises:
            AttributeError: If tool doesn't exist
        """
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        if name in self._tool_registry:
            def tool_method(**kwargs):
                return self._call_tool(name, kwargs)
            return tool_method
        
        raise AttributeError(
            f"Tool '{name}' not found. Available: {', '.join(self.list_tools())}"
        )
    
    def __repr__(self) -> str:
        """String representation."""
        tools_count = len(self._tool_registry)
        tools_preview = ", ".join(list(self._tool_registry.keys())[:5])
        if tools_count > 5:
            tools_preview += f", ... (+{tools_count - 5} more)"
        return f"ToolsAPI({tools_count} tools: {tools_preview})"


class AsyncToolsAPI(ToolsAPI):
    """
    Async version of ToolsAPI for use with stdio servers.
    
    Supports async tool calls without blocking.
    """
    
    async def _call_tool_async(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> str:
        """
        Call a tool asynchronously.
        
        Args:
            tool_name: Name of tool
            parameters: Tool parameters
            
        Returns:
            JSON string with result
        """
        if tool_name not in self._tool_registry:
            available = ", ".join(sorted(self._tool_registry.keys()))
            raise ValueError(
                f"Tool '{tool_name}' not found. Available tools: {available}"
            )
        
        server, tool_info, server_type = self._tool_registry[tool_name]
        
        if self.verbose:
            print(f"Calling tool (async): {tool_name} with params: {parameters}")
        
        try:
            if server_type == 'http':
                # HTTP can be called sync
                result = self.http_executor(server, tool_name, parameters)
            else:
                # stdio needs async
                result = await self.stdio_executor(server, tool_name, parameters)
            
            if isinstance(result, str):
                json.loads(result)
                return result
            else:
                return json.dumps(result)
        
        except Exception as e:
            error_result = {
                "status": "error",
                "error": str(e),
                "tool": tool_name
            }
            return json.dumps(error_result)