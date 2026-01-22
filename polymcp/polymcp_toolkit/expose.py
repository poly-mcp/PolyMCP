"""
MCP Tool Exposure Module
Production-ready framework for exposing Python functions as MCP tools.
Supports both HTTP (FastAPI) and in-process execution modes.
"""

import inspect
import asyncio
import json
from typing import Callable, List, Dict, Any, get_type_hints, Union, Optional
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, create_model, Field, ValidationError
from docstring_parser import parse


def _extract_function_metadata(func: Callable) -> Dict[str, Any]:
    """Extract metadata from a function using type hints and docstring."""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    docstring = parse(func.__doc__ or "")
    description = docstring.short_description or func.__name__

    input_fields = {}
    for param_name, param in sig.parameters.items():
        param_type = type_hints.get(param_name, str)
        param_doc = next(
            (p.description for p in docstring.params if p.arg_name == param_name),
            ""
        )

        if param.default != inspect.Parameter.empty:
            input_fields[param_name] = (
                param_type,
                Field(default=param.default, description=param_doc)
            )
        else:
            input_fields[param_name] = (param_type, Field(description=param_doc))

    return_type = type_hints.get("return", str)

    return {
        "name": func.__name__,
        "description": description,
        "input_fields": input_fields,
        "return_type": return_type,
        "is_async": asyncio.iscoroutinefunction(func),
    }


def _create_input_model(func_name: str, input_fields: Dict) -> type:
    """Create a Pydantic model for function input validation."""
    if not input_fields:
        return create_model(f"{func_name}_Input")
    return create_model(f"{func_name}_Input", **input_fields)


def _create_output_model(func_name: str, return_type: type) -> type:
    """Create a Pydantic model for function output."""
    return create_model(
        f"{func_name}_Output",
        result=(return_type, Field(description="Function result")),
    )


def _build_tool_registry(tools: List[Callable]) -> Dict[str, Dict[str, Any]]:
    """
    Build tool registry from functions.

    Shared logic for both HTTP and in-process modes.
    """
    tool_registry = {}

    for func in tools:
        metadata = _extract_function_metadata(func)
        input_model = _create_input_model(metadata["name"], metadata["input_fields"])
        output_model = _create_output_model(metadata["name"], metadata["return_type"])

        input_schema = input_model.model_json_schema()
        output_schema = output_model.model_json_schema()

        tool_registry[metadata["name"]] = {
            "metadata": {
                "name": metadata["name"],
                "description": metadata["description"],
                "input_schema": input_schema,
                "output_schema": output_schema,
            },
            "function": func,
            "input_model": input_model,
            "output_model": output_model,
            "is_async": metadata["is_async"],
        }

    return tool_registry


class InProcessMCPServer:
    """
    In-process MCP server for direct tool execution.
    """

    def __init__(self, tool_registry: Dict[str, Dict[str, Any]], verbose: bool = False):
        self.tool_registry = tool_registry
        self.verbose = verbose
        self._execution_count = 0
        self._error_count = 0

    async def list_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        tools_list = []
        for _, tool_info in self.tool_registry.items():
            tools_list.append(tool_info["metadata"])

        if self.verbose:
            print(f"[InProcessMCP] Listed {len(tools_list)} tools")

        return {"tools": tools_list}

    async def invoke(
        self, tool_name: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        self._execution_count += 1

        if tool_name not in self.tool_registry:
            self._error_count += 1
            available = list(self.tool_registry.keys())
            error_msg = f"Tool '{tool_name}' not found. Available: {available}"
            if self.verbose:
                print(f"[InProcessMCP] Error: {error_msg}")
            raise KeyError(error_msg)

        tool = self.tool_registry[tool_name]

        # Validate input
        try:
            validated_input = tool["input_model"](**(payload or {}))
            params = validated_input.model_dump()
        except ValidationError as e:
            self._error_count += 1
            error_msg = f"Invalid input for '{tool_name}': {str(e)}"
            if self.verbose:
                print(f"[InProcessMCP] Validation error: {error_msg}")
            return {
                "status": "error",
                "error": error_msg,
                "details": e.errors() if hasattr(e, "errors") else str(e),
            }
        except Exception as e:
            self._error_count += 1
            error_msg = f"Input processing error for '{tool_name}': {str(e)}"
            if self.verbose:
                print(f"[InProcessMCP] Error: {error_msg}")
            return {"status": "error", "error": error_msg}

        # Execute tool
        try:
            if self.verbose:
                print(f"[InProcessMCP] Executing '{tool_name}' with params: {params}")

            if tool["is_async"]:
                result = await tool["function"](**params)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, tool["function"], **params)

            if self.verbose:
                print(f"[InProcessMCP] '{tool_name}' executed successfully")

            # Handle different return types
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and "status" in parsed:
                        return parsed
                    return {"result": parsed, "status": "success"}
                except json.JSONDecodeError:
                    return {"result": result, "status": "success"}
            elif isinstance(result, dict):
                if "status" in result:
                    return result
                return {"result": result, "status": "success"}
            else:
                return {"result": result, "status": "success"}

        except Exception as e:
            self._error_count += 1
            error_msg = f"Tool execution failed for '{tool_name}': {str(e)}"
            if self.verbose:
                print(f"[InProcessMCP] Execution error: {error_msg}")
                import traceback

                traceback.print_exc()

            return {"status": "error", "error": error_msg, "tool": tool_name}

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_executions": self._execution_count,
            "total_errors": self._error_count,
            "success_rate": (
                ((self._execution_count - self._error_count) / self._execution_count * 100)
                if self._execution_count > 0
                else 0.0
            ),
        }

    def __repr__(self) -> str:
        tool_count = len(self.tool_registry)
        tool_names = ", ".join(list(self.tool_registry.keys())[:3])
        if tool_count > 3:
            tool_names += f", ... (+{tool_count - 3} more)"
        return f"InProcessMCPServer({tool_count} tools: {tool_names})"


def expose_tools_inprocess(
    tools: Union[Callable, List[Callable]],
    verbose: bool = False,
) -> InProcessMCPServer:
    if not isinstance(tools, list):
        tools = [tools]

    if not tools:
        raise ValueError("At least one tool must be provided")

    tool_registry = _build_tool_registry(tools)
    server = InProcessMCPServer(tool_registry, verbose=verbose)

    if verbose:
        print(f"Created in-process MCP server with {len(tool_registry)} tools")

    return server


def expose_tools_http(
    tools: Union[Callable, List[Callable]],
    title: str = "MCP Tool Server",
    description: str = "FastAPI server exposing Python functions as MCP tools",
    version: str = "1.0.0",
    verbose: bool = False,
) -> FastAPI:
    """
    Expose Python functions as MCP tools via FastAPI HTTP server.

    Canonical endpoints (existing):
    - GET  /mcp/list_tools
    - POST /mcp/invoke/{tool_name}

    Compatibility endpoints (added):
    - GET  /mcp/tools/list   (alias)
    - GET  /tools/list       (alias)
    - GET  /mcp/tools        (alias)
    - GET  /tools            (alias)
    - POST /mcp/tools/call   (name+arguments style)
    - POST /mcp             (JSON-RPC 2.0: initialize, tools/list, tools/call)
    - GET  /mcp             (alias to list tools)
    """
    if not isinstance(tools, list):
        tools = [tools]

    if not tools:
        raise ValueError("At least one tool must be provided")

    app = FastAPI(title=title, description=description, version=version)

    tool_registry = _build_tool_registry(tools)

    stats = {"total_requests": 0, "total_errors": 0}

    @app.get("/mcp/list_tools")
    async def list_tools():
        """List all available MCP tools."""
        stats["total_requests"] += 1
        try:
            tools_list = [tool["metadata"] for tool in tool_registry.values()]
            if verbose:
                print(f"[HTTP MCP] Listed {len(tools_list)} tools")
            return {"tools": tools_list}
        except Exception as e:
            stats["total_errors"] += 1
            if verbose:
                print(f"[HTTP MCP] Error listing tools: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/mcp/invoke/{tool_name}")
    async def invoke_tool(tool_name: str, payload: Dict[str, Any] = None):
        """Invoke a specific MCP tool."""
        stats["total_requests"] += 1

        if tool_name not in tool_registry:
            stats["total_errors"] += 1
            error_msg = f"Tool '{tool_name}' not found. Available: {list(tool_registry.keys())}"
            if verbose:
                print(f"[HTTP MCP] 404: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        tool = tool_registry[tool_name]

        # Validate input
        try:
            validated_input = tool["input_model"](**(payload or {}))
            params = validated_input.model_dump()
        except ValidationError as e:
            stats["total_errors"] += 1
            error_msg = f"Invalid input parameters: {str(e)}"
            if verbose:
                print(f"[HTTP MCP] 422: {error_msg}")
            raise HTTPException(status_code=422, detail=error_msg)
        except Exception as e:
            stats["total_errors"] += 1
            error_msg = f"Input processing error: {str(e)}"
            if verbose:
                print(f"[HTTP MCP] 400: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        # Execute tool
        try:
            if verbose:
                print(f"[HTTP MCP] Executing '{tool_name}' with params: {params}")

            if tool["is_async"]:
                result = await tool["function"](**params)
            else:
                result = tool["function"](**params)

            if verbose:
                print(f"[HTTP MCP] '{tool_name}' executed successfully")

            # Handle different return types
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and "status" in parsed:
                        return parsed
                    return {"result": parsed, "status": "success"}
                except json.JSONDecodeError:
                    return {"result": result, "status": "success"}
            elif isinstance(result, dict):
                if "status" in result:
                    return result
                return {"result": result, "status": "success"}
            else:
                return {"result": result, "status": "success"}

        except HTTPException:
            raise
        except Exception as e:
            stats["total_errors"] += 1
            error_msg = f"Tool execution failed: {str(e)}"
            if verbose:
                print(f"[HTTP MCP] 500: {error_msg}")
                import traceback

                traceback.print_exc()
            raise HTTPException(status_code=500, detail=error_msg)

    # -------------------------
    # Compatibility layer (HTTP)
    # -------------------------

    @app.get("/mcp/tools/list")
    async def compat_list_tools_1():
        return await list_tools()

    @app.get("/tools/list")
    async def compat_list_tools_2():
        return await list_tools()

    @app.get("/mcp/tools")
    async def compat_list_tools_3():
        return await list_tools()

    @app.get("/tools")
    async def compat_list_tools_4():
        return await list_tools()

    class ToolsCallRequest(BaseModel):
        name: str
        arguments: Dict[str, Any] = {}

    @app.post("/mcp/tools/call")
    async def compat_tools_call(req: ToolsCallRequest):
        # Map to canonical invoke endpoint
        return await invoke_tool(req.name, req.arguments)

    @app.get("/mcp")
    async def compat_mcp_get():
        # Some clients probe GET /mcp
        return await list_tools()

    @app.post("/mcp")
    async def compat_mcp_jsonrpc(payload: Dict[str, Any] = Body(...)):
        """
        JSON-RPC 2.0 over HTTP compatibility:
        - initialize
        - tools/list
        - tools/call
        """
        stats["total_requests"] += 1

        jsonrpc = payload.get("jsonrpc")
        method = payload.get("method")
        req_id = payload.get("id", None)
        params = payload.get("params") or {}

        def ok(result: Any):
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        def err(code: int, message: str, data: Any = None):
            e = {"code": code, "message": message}
            if data is not None:
                e["data"] = data
            return {"jsonrpc": "2.0", "id": req_id, "error": e}

        if jsonrpc != "2.0" or not method:
            stats["total_errors"] += 1
            raise HTTPException(status_code=400, detail=err(-32600, "Invalid Request"))

        if method == "initialize":
            # Minimal initialize response
            return ok(
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": title, "version": version},
                }
            )

        if method == "tools/list":
            lt = await list_tools()  # {"tools": [...]}
            return ok({"tools": lt["tools"]})

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not name:
                stats["total_errors"] += 1
                raise HTTPException(status_code=400, detail=err(-32602, "Missing required parameter: name"))

            try:
                res = await invoke_tool(name, arguments)
                # Return a MCP-ish "content" shape so most clients accept it.
                # If your tool already returns MCP content, you can swap this.
                return ok({"content": [{"type": "json", "json": res}]})
            except HTTPException as he:
                stats["total_errors"] += 1
                raise HTTPException(status_code=he.status_code, detail=err(-32603, "Tool call failed", data=he.detail))
            except Exception as e:
                stats["total_errors"] += 1
                raise HTTPException(status_code=500, detail=err(-32603, f"Internal error: {str(e)}"))

        stats["total_errors"] += 1
        raise HTTPException(status_code=404, detail=err(-32601, f"Method not found: {method}"))

    @app.get("/")
    async def root():
        return {
            "name": title,
            "description": description,
            "version": version,
            "endpoints": {
                "list_tools": "/mcp/list_tools",
                "invoke_tool": "/mcp/invoke/{tool_name}",
                "compat": {
                    "list_tools_aliases": ["/mcp/tools/list", "/tools/list", "/mcp/tools", "/tools", "/mcp"],
                    "tools_call": "/mcp/tools/call",
                    "jsonrpc": "/mcp (POST JSON-RPC 2.0)",
                },
            },
            "available_tools": list(tool_registry.keys()),
            "stats": {
                "total_requests": stats["total_requests"],
                "total_errors": stats["total_errors"],
                "error_rate": (
                    (stats["total_errors"] / stats["total_requests"] * 100)
                    if stats["total_requests"] > 0
                    else 0.0
                ),
            },
        }

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "tools_count": len(tool_registry),
            "stats": stats,
        }

    if verbose:
        print(f"Created HTTP MCP server with {len(tool_registry)} tools")

    return app


# Backward compatibility - alias to HTTP version
def expose_tools(
    tools: Union[Callable, List[Callable]],
    title: str = "MCP Tool Server",
    description: str = "FastAPI server exposing Python functions as MCP tools",
    version: str = "1.0.0",
) -> FastAPI:
    """Legacy function name - redirects to expose_tools_http."""
    return expose_tools_http(tools, title, description, version, verbose=False)


def expose_tools_http_with_auth(
    tools: Union[Callable, List[Callable]],
    api_keys: Dict[str, str] = None,
    title: str = "Authenticated MCP Tool Server",
    description: str = "MCP server with API key authentication",
    version: str = "1.0.0",
    verbose: bool = False,
) -> FastAPI:
    """
    Expose tools with API key authentication.
    """
    # Import here to avoid circular dependency
    from .mcp_auth_simple import SimpleAuthenticator, add_auth_to_mcp_server

    app = expose_tools_http(tools, title, description, version, verbose)

    authenticator = SimpleAuthenticator(api_keys)
    app = add_auth_to_mcp_server(app, authenticator)

    return app
