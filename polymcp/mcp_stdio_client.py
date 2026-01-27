#!/usr/bin/env python3
"""
MCP Stdio Client - Production Implementation (Fixed)
- Robust JSON-RPC line reading
- Correctly treats MCP tool-level errors (isError=true) as failures
- Windows-safe process + pipe cleanup (avoids Proactor "closed pipe" warnings)
- Works with stdio-based MCP servers like @playwright/mcp
"""

import asyncio
import json
import logging
import os
import sys
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)
JsonDict = Dict[str, Any]


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class MCPServerConfig:
    """Configuration for an MCP stdio server."""
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None


# =============================================================================
# STDIO CLIENT
# =============================================================================

class MCPStdioClient:
    """
    Client for stdio-based MCP servers.

    Communicates with MCP servers that use JSON-RPC over stdin/stdout,
    such as @playwright/mcp.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self._lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        """Start the MCP server process and initialize."""
        if self._running:
            return

        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)

        command = self.config.command
        args = list(self.config.args)

        # Windows: if command is "npx", prefer npx.cmd and execute through cmd /c
        if sys.platform == "win32":
            cmd_lower = (command or "").lower()
            if cmd_lower == "npx":
                npx_path = shutil.which("npx.cmd") or shutil.which("npx")
                if npx_path:
                    command = "cmd"
                    args = ["/c", npx_path] + args
            else:
                # If user passed absolute path to npx, ensure .cmd is used if exists
                if command.lower().endswith("\\npx") and os.path.exists(command + ".cmd"):
                    command = command + ".cmd"

        try:
            self.process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=50 * 1024 * 1024,  # 50MB (pick a value that fits your use-case)
        )
            self._running = True
            logger.info(f"Started MCP server: {self.config.command} {' '.join(self.config.args)}")

            # Give server a moment to boot
            await asyncio.sleep(0.5)
            await self._initialize()

        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            self._running = False
            self.process = None
            raise RuntimeError(f"Failed to start MCP server: {e}") from e

    async def _initialize(self) -> None:
        """Initialize the MCP connection."""
        response = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "polymcp", "version": "1.0.0"},
            },
            timeout=60.0,
        )

        if "error" in response:
            raise RuntimeError(f"Initialization failed: {response['error']}")

        logger.info("MCP connection initialized successfully")

    async def _read_jsonrpc_response(self, expected_id: int, timeout: float) -> JsonDict:
        """
        Read JSON-RPC responses line-by-line until we get the one with matching id.
        MCP JSON-RPC is newline delimited.
        """
        if not self.process or not self.process.stdout:
            raise RuntimeError("MCP server not running")

        loop = asyncio.get_event_loop()
        start = loop.time()

        while True:
            if loop.time() - start > timeout:
                raise asyncio.TimeoutError()

            try:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if not line:
                raise RuntimeError("MCP server closed stdout (no response)")

            s = line.decode("utf-8", errors="replace").strip()
            if not s:
                continue

            # Ignore non-JSON stdout lines safely
            try:
                msg = json.loads(s)
            except json.JSONDecodeError:
                continue

            if msg.get("id") == expected_id:
                return msg
            # else: ignore notifications or other ids

    async def _send_request(self, method: str, params: Optional[Dict] = None, timeout: float = 60.0) -> JsonDict:
        """Send JSON-RPC request to server and wait for matching response."""
        async with self._lock:
            if not self.process or not self._running or not self.process.stdin:
                raise RuntimeError("MCP server not running")

            self.request_id += 1
            rid = self.request_id

            request: JsonDict = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params is not None:
                request["params"] = params

            try:
                payload = (json.dumps(request) + "\n").encode("utf-8")
                self.process.stdin.write(payload)
                await self.process.stdin.drain()
            except Exception as e:
                raise RuntimeError(f"Failed sending request {method}: {e}") from e

            try:
                return await self._read_jsonrpc_response(expected_id=rid, timeout=timeout)
            except asyncio.TimeoutError as e:
                raise RuntimeError(f"Timeout waiting for response to {method}") from e

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server."""
        try:
            response = await self._send_request("tools/list", timeout=60.0)
            if "error" in response:
                raise RuntimeError(f"Error listing tools: {response['error']}")
            tools = response.get("result", {}).get("tools", []) or []
            logger.info(f"Listed {len(tools)} tools")
            return tools
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        response = await self._send_request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout=120.0,
        )

        if "error" in response:
            err = response["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Tool execution failed: {msg}")

        # Tool-level failures may be inside result as isError=true
        return response.get("result", {})

    async def stop(self) -> None:
        """Stop the MCP server process (Windows-safe cleanup)."""
        if not self._running:
            return

        self._running = False

        try:
            if not self.process:
                return

            # 1) Best-effort: signal EOF to stdin, then close pipes
            try:
                if self.process.stdin:
                    try:
                        self.process.stdin.write_eof()
                    except Exception:
                        pass
                    try:
                        await self.process.stdin.drain()
                    except Exception:
                        pass
                    try:
                        self.process.stdin.close()
                    except Exception:
                        pass
            except Exception:
                pass

            # Close stdout/stderr to release transports
            try:
                if self.process.stdout:
                    try:
                        self.process.stdout.close()
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                if self.process.stderr:
                    try:
                        self.process.stderr.close()
                    except Exception:
                        pass
            except Exception:
                pass

            # 2) Terminate, then kill if needed
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=8.0)
                logger.info("MCP server stopped gracefully")
            except asyncio.TimeoutError:
                try:
                    self.process.kill()
                    await self.process.wait()
                except Exception:
                    pass
                logger.warning("MCP server killed (timeout)")

        except Exception as e:
            logger.error(f"Error stopping MCP server: {e}")

        finally:
            self.process = None
            # Give asyncio time to finalize transports on Windows
            if sys.platform == "win32":
                await asyncio.sleep(0.3)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.stop()
        except Exception:
            pass
        return False


# =============================================================================
# ADAPTER
# =============================================================================

class MCPStdioAdapter:
    """
    Adapter to expose stdio MCP server in a PolyMCP-friendly interface.
    """

    def __init__(self, client: MCPStdioClient):
        self.client = client
        self._tools_cache: Optional[List[Dict[str, Any]]] = None

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get tools in PolyMCP HTTP-like format."""
        if self._tools_cache is not None:
            return self._tools_cache

        stdio_tools = await self.client.list_tools()

        http_tools: List[Dict[str, Any]] = []
        for tool in stdio_tools:
            http_tools.append(
                {
                    "name": tool.get("name"),
                    "description": tool.get("description", "") or "",
                    "input_schema": tool.get("inputSchema", {}) or {},
                }
            )

        self._tools_cache = http_tools
        return http_tools

    @staticmethod
    def _extract_mcp_error_text(tool_result: Dict[str, Any]) -> str:
        """
        MCP tool-level errors commonly return:
          { "content": [{"type":"text","text":"..."}], "isError": true }
        """
        content = tool_result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    txt = item.get("text")
                    if isinstance(txt, str) and txt.strip():
                        return txt.strip()[:1500]
        return "Tool returned isError=true but no readable error text was found."

    async def invoke_tool(self, tool_name: str, parameters: Dict[str, Any]) -> JsonDict:
        """
        Invoke a tool and return:
          - {"result": <tool_result>, "status": "success"} on success
          - {"error": <message>, "status": "execution_failed", "result": <raw>} on tool-level failure
        """
        try:
            tool_result = await self.client.call_tool(tool_name, parameters)

            if isinstance(tool_result, dict) and tool_result.get("isError") is True:
                msg = self._extract_mcp_error_text(tool_result)
                return {"error": msg, "status": "execution_failed", "result": tool_result}

            return {"result": tool_result, "status": "success"}

        except Exception as e:
            return {"error": str(e), "status": "error"}
