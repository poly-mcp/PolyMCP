"""
PolyMCP Inspector Server - ENHANCED Production Implementation
FastAPI server with WebSocket for real-time MCP server inspection.

NEW FEATURES:
- Resources Support (MCP resources/list + read)
- Prompts Support (MCP prompts/list + get)
- Test Suites (save/load/run test scenarios)
- Export Reports (JSON/Markdown/HTML)
"""

import asyncio
import json
import logging
import os
import re
import secrets
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict
from urllib.parse import quote

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ..mcp_stdio_client import MCPStdioClient, MCPStdioAdapter, MCPServerConfig


logger = logging.getLogger(__name__)


@dataclass
class ServerInfo:
    """Information about a connected MCP server."""
    id: str
    name: str
    url: str
    type: str  # 'http' or 'stdio'
    status: str  # 'connected', 'disconnected', 'error'
    tools_count: int
    connected_at: str
    last_request: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ToolMetrics:
    """Metrics for a specific tool."""
    name: str
    calls: int
    total_time: float
    avg_time: float
    success_count: int
    error_count: int
    last_called: Optional[str] = None


@dataclass
class ActivityLog:
    """Activity log entry."""
    timestamp: str
    server_id: str
    method: str
    tool_name: Optional[str]
    status: int
    duration: float
    error: Optional[str] = None


@dataclass
class TestCase:
    """Test case definition."""
    id: str
    name: str
    server_id: str
    tool_name: str
    parameters: Dict[str, Any]
    expected_status: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class TestSuite:
    """Test suite containing multiple test cases."""
    id: str
    name: str
    description: str
    test_cases: List[TestCase]
    created_at: str
    last_run: Optional[str] = None


class ServerManager:
    """
    Manages multiple MCP server connections.
    Handles both HTTP and stdio servers with real-time metrics.
    
    NEW: Added Resources, Prompts, Skills, Test Suites, Export
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.servers: Dict[str, ServerInfo] = {}
        self.stdio_clients: Dict[str, MCPStdioClient] = {}
        self.stdio_adapters: Dict[str, MCPStdioAdapter] = {}
        self.http_tools_cache: Dict[str, List[Dict]] = {}
        self.http_profiles: Dict[str, Dict[str, Any]] = {}
        self.http_request_ids: Dict[str, int] = defaultdict(int)
        
        # Metrics tracking
        self.tool_metrics: Dict[str, Dict[str, ToolMetrics]] = defaultdict(dict)
        self.activity_logs: List[ActivityLog] = []
        self.max_logs = 1000
        
        # WebSocket connections
        self.active_connections: Set[WebSocket] = set()
        
        # NEW: Test suites storage
        self.test_suites: Dict[str, TestSuite] = {}
        self.test_suites_dir = Path.home() / '.polymcp' / 'inspector' / 'test-suites'
        self.test_suites_dir.mkdir(parents=True, exist_ok=True)
        self._load_test_suites()
    
    def _load_test_suites(self):
        """Load test suites from disk."""
        try:
            for suite_file in self.test_suites_dir.glob('*.json'):
                with open(suite_file, 'r') as f:
                    data = json.load(f)
                    test_cases = [TestCase(**tc) for tc in data.get('test_cases', [])]
                    suite = TestSuite(
                        id=data['id'],
                        name=data['name'],
                        description=data.get('description', ''),
                        test_cases=test_cases,
                        created_at=data['created_at'],
                        last_run=data.get('last_run')
                    )
                    self.test_suites[suite.id] = suite
            
            if self.verbose:
                logger.info(f"Loaded {len(self.test_suites)} test suites")
        
        except Exception as e:
            logger.error(f"Failed to load test suites: {e}")
    
    def _save_test_suite(self, suite: TestSuite):
        """Save test suite to disk."""
        try:
            suite_file = self.test_suites_dir / f"{suite.id}.json"
            with open(suite_file, 'w') as f:
                json.dump({
                    'id': suite.id,
                    'name': suite.name,
                    'description': suite.description,
                    'test_cases': [asdict(tc) for tc in suite.test_cases],
                    'created_at': suite.created_at,
                    'last_run': suite.last_run
                }, f, indent=2)
            
            if self.verbose:
                logger.info(f"Saved test suite: {suite.name}")
        
        except Exception as e:
            logger.error(f"Failed to save test suite: {e}")
            raise
    
    async def add_http_server(self, server_id: str, name: str, url: str) -> Dict[str, Any]:
        """Add HTTP MCP server."""
        try:
            profile, tools = await self._discover_http_server(server_id, url)
            
            # Store server info
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=url,
                type='http',
                status='connected',
                tools_count=len(tools),
                connected_at=datetime.now().isoformat()
            )
            
            # Cache tools
            self.http_tools_cache[server_id] = tools
            self.http_profiles[server_id] = profile
            
            # Initialize metrics for each tool
            for tool in tools:
                tool_name = tool.get('name')
                if tool_name:
                    self.tool_metrics[server_id][tool_name] = ToolMetrics(
                        name=tool_name,
                        calls=0,
                        total_time=0.0,
                        avg_time=0.0,
                        success_count=0,
                        error_count=0
                    )
            
            if self.verbose:
                logger.info(f"Connected to HTTP server: {name} ({len(tools)} tools)")
            
            await self._broadcast_update('server_added', asdict(self.servers[server_id]))
            
            return {'status': 'success', 'server': asdict(self.servers[server_id])}
        
        except Exception as e:
            error_msg = f"Failed to connect to {url}: {str(e)}"
            logger.error(error_msg)
            
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=url,
                type='http',
                status='error',
                tools_count=0,
                connected_at=datetime.now().isoformat(),
                error=error_msg
            )
            
            await self._broadcast_update('server_error', {
                'server_id': server_id,
                'error': error_msg
            })
            
            return {'status': 'error', 'error': error_msg}

    def _get_http_candidates(self, raw_url: str) -> Dict[str, List[str]]:
        """Build candidate URLs for JSON-RPC MCP and legacy REST MCP."""
        normalized = (raw_url or "").strip()
        if not normalized:
            raise ValueError("Empty server URL")

        normalized = normalized.rstrip("/")
        rpc_candidates: List[str] = []
        legacy_candidates: List[str] = []

        def push_unique(values: List[str], value: str):
            if value and value not in values:
                values.append(value)

        push_unique(rpc_candidates, normalized)
        push_unique(legacy_candidates, normalized)

        if normalized.endswith("/mcp"):
            base = normalized[:-4].rstrip("/")
            push_unique(legacy_candidates, base)
        else:
            push_unique(rpc_candidates, f"{normalized}/mcp")

        if normalized.endswith("/list_tools"):
            base = normalized[:-11].rstrip("/")
            push_unique(legacy_candidates, base)
            push_unique(rpc_candidates, base)
            push_unique(rpc_candidates, f"{base}/mcp")

        if normalized.endswith("/invoke"):
            base = normalized[:-7].rstrip("/")
            push_unique(legacy_candidates, base)
            push_unique(rpc_candidates, f"{base}/mcp")

        return {"rpc": rpc_candidates, "legacy": legacy_candidates}

    def _next_http_request_id(self, server_id: str) -> int:
        self.http_request_ids[server_id] += 1
        return self.http_request_ids[server_id]

    def _http_jsonrpc_call(
        self,
        server_id: str,
        endpoint: str,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request to HTTP MCP endpoint and return result object."""
        import requests

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_http_request_id(server_id),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        response = requests.post(
            endpoint,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

        # Some servers return batch envelopes or wrapped shapes.
        if isinstance(data, list):
            data = data[0] if data else {}

        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid JSON-RPC response for {method}: {type(data)}")

        if "error" in data and data["error"]:
            err = data["error"]
            if isinstance(err, dict):
                msg = err.get("message", str(err))
                code = err.get("code")
                raise RuntimeError(f"{method} failed ({code}): {msg}")
            raise RuntimeError(f"{method} failed: {err}")

        result = data.get("result", {})
        if not isinstance(result, dict):
            return {"value": result}
        return result

    async def _discover_http_server(self, server_id: str, url: str) -> Any:
        """
        Detect best HTTP transport mode:
        - jsonrpc: Streamable HTTP MCP endpoint (tools/list, tools/call, resources/*, prompts/*)
        - legacy: REST PolyMCP style (/list_tools, /invoke/{tool}, /tools/{tool})
        """
        candidates = self._get_http_candidates(url)
        discovery_errors: List[str] = []

        # 1) Prefer MCP JSON-RPC endpoint.
        for endpoint in candidates["rpc"]:
            try:
                init_result = await asyncio.to_thread(
                    self._http_jsonrpc_call,
                    server_id,
                    endpoint,
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {},
                            "resources": {"subscribe": True},
                            "prompts": {},
                        },
                        "clientInfo": {"name": "polymcp-inspector", "version": "1.3.6"},
                    },
                    8.0,
                )

                # Optional initialized notification
                try:
                    await asyncio.to_thread(
                        self._http_jsonrpc_call,
                        server_id,
                        endpoint,
                        "notifications/initialized",
                        {},
                        5.0,
                    )
                except Exception:
                    pass

                tools_result = await asyncio.to_thread(
                    self._http_jsonrpc_call,
                    server_id,
                    endpoint,
                    "tools/list",
                    {},
                    10.0,
                )
                tools = tools_result.get("tools", [])
                if not isinstance(tools, list):
                    tools = []

                profile = {
                    "mode": "jsonrpc",
                    "rpc_endpoint": endpoint,
                    "base_url": endpoint[:-4].rstrip("/") if endpoint.endswith("/mcp") else endpoint.rstrip("/"),
                    "initialize": init_result,
                }
                return profile, tools
            except Exception as e:
                discovery_errors.append(f"JSON-RPC {endpoint}: {e}")

        # 2) Fallback to legacy REST.
        import requests
        for base_url in candidates["legacy"]:
            try:
                list_url = f"{base_url}/list_tools"
                response = requests.get(list_url, timeout=6)
                response.raise_for_status()
                body = response.json()
                tools = body.get("tools", []) if isinstance(body, dict) else []
                if not isinstance(tools, list):
                    tools = []
                profile = {"mode": "legacy", "base_url": base_url}
                return profile, tools
            except Exception as e:
                discovery_errors.append(f"Legacy {base_url}: {e}")

        raise RuntimeError("; ".join(discovery_errors[-5:]) or "Unknown HTTP discovery failure")
    
    async def add_stdio_server(
        self,
        server_id: str,
        name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Add stdio MCP server."""
        try:
            config = MCPServerConfig(command=command, args=args, env=env)
            client = MCPStdioClient(config)
            
            await client.start()
            
            adapter = MCPStdioAdapter(client)
            tools = await adapter.get_tools()
            
            self.stdio_clients[server_id] = client
            self.stdio_adapters[server_id] = adapter
            
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=f"stdio://{command}",
                type='stdio',
                status='connected',
                tools_count=len(tools),
                connected_at=datetime.now().isoformat()
            )
            
            # Initialize metrics
            for tool in tools:
                tool_name = tool.get('name')
                if tool_name:
                    self.tool_metrics[server_id][tool_name] = ToolMetrics(
                        name=tool_name,
                        calls=0,
                        total_time=0.0,
                        avg_time=0.0,
                        success_count=0,
                        error_count=0
                    )
            
            if self.verbose:
                logger.info(f"Connected to stdio server: {name} ({len(tools)} tools)")
            
            await self._broadcast_update('server_added', asdict(self.servers[server_id]))
            
            return {'status': 'success', 'server': asdict(self.servers[server_id])}
        
        except Exception as e:
            error_msg = f"Failed to start {command}: {str(e)}"
            logger.error(error_msg)
            
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=f"stdio://{command}",
                type='stdio',
                status='error',
                tools_count=0,
                connected_at=datetime.now().isoformat(),
                error=error_msg
            )
            
            await self._broadcast_update('server_error', {
                'server_id': server_id,
                'error': error_msg
            })
            
            return {'status': 'error', 'error': error_msg}
    
    async def remove_server(self, server_id: str) -> Dict[str, Any]:
        """Remove a server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        # Stop stdio client if exists
        if server_id in self.stdio_clients:
            try:
                await self.stdio_clients[server_id].stop()
            except:
                pass
            del self.stdio_clients[server_id]
            del self.stdio_adapters[server_id]
        
        # Remove from caches
        if server_id in self.http_tools_cache:
            del self.http_tools_cache[server_id]
        if server_id in self.http_profiles:
            del self.http_profiles[server_id]
        if server_id in self.http_request_ids:
            del self.http_request_ids[server_id]
        
        if server_id in self.tool_metrics:
            del self.tool_metrics[server_id]
        
        del self.servers[server_id]
        
        await self._broadcast_update('server_removed', {'server_id': server_id})
        
        return {'status': 'success'}
    
    async def get_tools(self, server_id: str) -> List[Dict[str, Any]]:
        """Get tools from a server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        
        if server.type == 'http':
            profile = self.http_profiles.get(server_id, {"mode": "legacy", "base_url": server.url})
            if profile.get("mode") == "jsonrpc":
                tools: List[Dict[str, Any]] = []
                cursor: Optional[str] = None
                for _ in range(50):
                    params = {"cursor": cursor} if cursor else {}
                    result = await asyncio.to_thread(
                        self._http_jsonrpc_call,
                        server_id,
                        profile["rpc_endpoint"],
                        "tools/list",
                        params,
                        15.0,
                    )
                    page_tools = result.get("tools", [])
                    if isinstance(page_tools, list):
                        tools.extend(page_tools)
                    next_cursor = result.get("nextCursor")
                    if not next_cursor:
                        break
                    cursor = str(next_cursor)
                self.http_tools_cache[server_id] = tools
                return tools
            return self.http_tools_cache.get(server_id, [])
        else:  # stdio
            if server_id in self.stdio_adapters:
                return await self.stdio_adapters[server_id].get_tools()
            return []
    
    async def execute_tool(
        self,
        server_id: str,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        start_time = datetime.now()
        
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy", "base_url": server.url})
                if profile.get("mode") == "jsonrpc":
                    result = await asyncio.to_thread(
                        self._http_jsonrpc_call,
                        server_id,
                        profile["rpc_endpoint"],
                        "tools/call",
                        {"name": tool_name, "arguments": parameters},
                        45.0,
                    )
                    if isinstance(result, dict) and result.get("isError") is True:
                        text = "Tool returned isError=true"
                        content = result.get("content")
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("text"):
                                    text = str(item["text"])
                                    break
                        raise RuntimeError(text)
                else:
                    import requests
                    base_url = profile.get("base_url", server.url).rstrip("/")

                    errors: List[str] = []
                    legacy_calls = [
                        ("POST", f"{base_url}/tools/{tool_name}", parameters),
                        ("POST", f"{base_url}/invoke/{tool_name}", parameters),
                        ("POST", f"{base_url}/invoke", {"tool": tool_name, "parameters": parameters}),
                    ]

                    result = None
                    for method, endpoint, payload in legacy_calls:
                        try:
                            response = requests.request(
                                method,
                                endpoint,
                                json=payload,
                                timeout=30,
                                headers={"Accept": "application/json"},
                            )
                            response.raise_for_status()
                            ctype = response.headers.get("content-type", "")
                            if "application/json" in ctype:
                                result = response.json()
                            else:
                                result = {"status": "success", "result": response.text}
                            break
                        except Exception as e:
                            errors.append(f"{endpoint}: {e}")
                    if result is None:
                        raise RuntimeError("; ".join(errors[-3:]))
            
            else:  # stdio
                adapter = self.stdio_adapters[server_id]
                result = await adapter.invoke_tool(tool_name, parameters)
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self._update_metrics(server_id, tool_name, duration, True)
            self._log_activity(
                server_id=server_id,
                method='execute_tool',
                tool_name=tool_name,
                status=200,
                duration=duration
            )
            
            server.last_request = datetime.now().isoformat()
            
            await self._broadcast_update('tool_executed', {
                'server_id': server_id,
                'tool_name': tool_name,
                'duration': duration
            })
            
            return {
                'status': 'success',
                'result': result,
                'duration': duration
            }
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self._update_metrics(server_id, tool_name, duration, False)
            self._log_activity(
                server_id=server_id,
                method='execute_tool',
                tool_name=tool_name,
                status=500,
                duration=duration,
                error=error_msg
            )
            
            await self._broadcast_update('tool_error', {
                'server_id': server_id,
                'tool_name': tool_name,
                'error': error_msg
            })
            
            return {
                'status': 'error',
                'error': error_msg,
                'duration': duration
            }
    
    # NEW: Resources Support
    async def list_resources(self, server_id: str) -> List[Dict[str, Any]]:
        """List resources from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy", "base_url": server.url})
                if profile.get("mode") == "jsonrpc":
                    resources: List[Dict[str, Any]] = []
                    cursor: Optional[str] = None
                    for _ in range(50):
                        params = {"cursor": cursor} if cursor else {}
                        result = await asyncio.to_thread(
                            self._http_jsonrpc_call,
                            server_id,
                            profile["rpc_endpoint"],
                            "resources/list",
                            params,
                            15.0,
                        )
                        page = result.get("resources", [])
                        if isinstance(page, list):
                            resources.extend(page)
                        next_cursor = result.get("nextCursor")
                        if not next_cursor:
                            break
                        cursor = str(next_cursor)
                    return resources
                # Legacy fallback for MCP Apps style endpoints
                import requests
                base_url = profile.get("base_url", server.url).rstrip("/")
                response = requests.get(f"{base_url}/list_resources", timeout=10)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload.get("resources", [])
                return []
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request("resources/list")
                return response.get('result', {}).get('resources', [])
        
        except Exception as e:
            logger.error(f"Failed to list resources from {server_id}: {e}")
            return []
    
    async def read_resource(self, server_id: str, uri: str) -> Dict[str, Any]:
        """Read a resource from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        start_time = datetime.now()
        
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy", "base_url": server.url})
                if profile.get("mode") == "jsonrpc":
                    result = await asyncio.to_thread(
                        self._http_jsonrpc_call,
                        server_id,
                        profile["rpc_endpoint"],
                        "resources/read",
                        {"uri": uri},
                        20.0,
                    )
                else:
                    import requests
                    base_url = profile.get("base_url", server.url).rstrip("/")
                    encoded_uri = quote(uri, safe="")
                    errors: List[str] = []
                    result = {}

                    try:
                        response = requests.get(f"{base_url}/resources/{encoded_uri}", timeout=15)
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "text/plain")
                        if "application/json" in content_type:
                            payload = response.json()
                            if isinstance(payload, dict) and "contents" in payload:
                                result = payload
                            else:
                                result = {
                                    "contents": [{
                                        "uri": uri,
                                        "mimeType": payload.get("mimeType", content_type) if isinstance(payload, dict) else "application/json",
                                        "text": json.dumps(payload, ensure_ascii=False, indent=2),
                                    }]
                                }
                        else:
                            result = {
                                "contents": [{
                                    "uri": uri,
                                    "mimeType": content_type,
                                    "text": response.text,
                                }]
                            }
                    except Exception as e:
                        errors.append(f"GET /resources/{{uri}}: {e}")
                        response = requests.post(
                            f"{base_url}/resources/read",
                            json={"uri": uri},
                            timeout=15,
                            headers={"Accept": "application/json"},
                        )
                        response.raise_for_status()
                        payload = response.json()
                        if isinstance(payload, dict):
                            result = payload if "contents" in payload else {"contents": [payload]}
                        else:
                            errors.append("Invalid /resources/read payload")
                            raise RuntimeError("; ".join(errors))
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request("resources/read", {"uri": uri})
                result = response.get('result', {})
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self._log_activity(
                server_id=server_id,
                method='read_resource',
                tool_name=uri,
                status=200,
                duration=duration
            )
            
            await self._broadcast_update('resource_read', {
                'server_id': server_id,
                'uri': uri,
                'duration': duration
            })
            
            return {
                'status': 'success',
                'contents': result.get('contents', []),
                'duration': duration
            }
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self._log_activity(
                server_id=server_id,
                method='read_resource',
                tool_name=uri,
                status=500,
                duration=duration,
                error=error_msg
            )
            
            return {
                'status': 'error',
                'error': error_msg,
                'duration': duration
            }
    
    # NEW: Prompts Support
    async def list_prompts(self, server_id: str) -> List[Dict[str, Any]]:
        """List prompts from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy", "base_url": server.url})
                if profile.get("mode") == "jsonrpc":
                    prompts: List[Dict[str, Any]] = []
                    cursor: Optional[str] = None
                    for _ in range(50):
                        params = {"cursor": cursor} if cursor else {}
                        result = await asyncio.to_thread(
                            self._http_jsonrpc_call,
                            server_id,
                            profile["rpc_endpoint"],
                            "prompts/list",
                            params,
                            15.0,
                        )
                        page = result.get("prompts", [])
                        if isinstance(page, list):
                            prompts.extend(page)
                        next_cursor = result.get("nextCursor")
                        if not next_cursor:
                            break
                        cursor = str(next_cursor)
                    return prompts
                return []
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request("prompts/list")
                return response.get('result', {}).get('prompts', [])
        
        except Exception as e:
            logger.error(f"Failed to list prompts from {server_id}: {e}")
            return []
    
    async def get_prompt(
        self,
        server_id: str,
        prompt_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get rendered prompt from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        start_time = datetime.now()
        
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy", "base_url": server.url})
                if profile.get("mode") != "jsonrpc":
                    raise RuntimeError("Prompt APIs are available only on JSON-RPC MCP endpoints")
                result = await asyncio.to_thread(
                    self._http_jsonrpc_call,
                    server_id,
                    profile["rpc_endpoint"],
                    "prompts/get",
                    {"name": prompt_name, "arguments": arguments},
                    20.0,
                )
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request(
                    "prompts/get",
                    {"name": prompt_name, "arguments": arguments}
                )
                result = response.get('result', {})
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self._log_activity(
                server_id=server_id,
                method='get_prompt',
                tool_name=prompt_name,
                status=200,
                duration=duration
            )
            
            return {
                'status': 'success',
                'messages': result.get('messages', []),
                'description': result.get('description', ''),
                'duration': duration
            }
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self._log_activity(
                server_id=server_id,
                method='get_prompt',
                tool_name=prompt_name,
                status=500,
                duration=duration,
                error=error_msg
            )
            
            return {
                'status': 'error',
                'error': error_msg,
                'duration': duration
            }

    async def proxy_mcp_request(
        self,
        server_id: str,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send an arbitrary MCP request through the selected transport."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        if not method:
            raise ValueError("method is required")

        server = self.servers[server_id]
        start_time = datetime.now()

        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy", "base_url": server.url})
                if profile.get("mode") != "jsonrpc":
                    raise RuntimeError("Generic MCP request requires a JSON-RPC MCP endpoint")
                result = await asyncio.to_thread(
                    self._http_jsonrpc_call,
                    server_id,
                    profile["rpc_endpoint"],
                    method,
                    params or {},
                    30.0,
                )
            else:
                client = self.stdio_clients[server_id]
                response = await client._send_request(method, params or {})
                if "error" in response and response["error"]:
                    raise RuntimeError(str(response["error"]))
                result = response.get("result", {})

            duration = (datetime.now() - start_time).total_seconds() * 1000
            self._log_activity(
                server_id=server_id,
                method=f"mcp:{method}",
                tool_name=None,
                status=200,
                duration=duration
            )
            return {"status": "success", "result": result, "duration": duration}
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            self._log_activity(
                server_id=server_id,
                method=f"mcp:{method}",
                tool_name=None,
                status=500,
                duration=duration,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "duration": duration}

    # LLM integration (Ollama + OpenAI + Anthropic)
    def _ollama_base_url(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    def _openai_base_url(self) -> str:
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def _anthropic_base_url(self) -> str:
        return os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")

    def list_ollama_models(self) -> Dict[str, Any]:
        """List locally available Ollama models."""
        import requests

        base_url = self._ollama_base_url()
        try:
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models", []) if isinstance(payload, dict) else []
            names: List[str] = []
            seen: set[str] = set()
            for item in models:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name or name in seen:
                    continue
                names.append(name)
                seen.add(name)
            return {
                "status": "success",
                "provider": "ollama",
                "base_url": base_url,
                "source": "ollama_api_tags",
                "fetched_at": datetime.now().isoformat(),
                "models": names,
            }
        except Exception as e:
            return {"status": "error", "provider": "ollama", "base_url": base_url, "error": str(e), "models": []}

    def list_openai_models(self, api_key_override: Optional[str] = None) -> Dict[str, Any]:
        import requests
        api_key = (api_key_override or os.getenv("OPENAI_API_KEY", "")).strip()
        if not api_key:
            return {
                "status": "error",
                "provider": "openai",
                "error": "Missing OPENAI_API_KEY",
                "models": [],
            }
        try:
            response = requests.get(
                f"{self._openai_base_url()}/models",
                timeout=10,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", []) if isinstance(payload, dict) else []
            names = sorted([m.get("id") for m in data if isinstance(m, dict) and m.get("id")])
            return {"status": "success", "provider": "openai", "models": names}
        except Exception as e:
            return {"status": "error", "provider": "openai", "error": str(e), "models": []}

    def list_anthropic_models(self, api_key_override: Optional[str] = None) -> Dict[str, Any]:
        api_key = (api_key_override or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        if not api_key:
            return {
                "status": "error",
                "provider": "anthropic",
                "error": "Missing ANTHROPIC_API_KEY",
                "models": [],
            }
        # Anthropic does not provide a public models list endpoint analogous to OpenAI.
        return {
            "status": "success",
            "provider": "anthropic",
            "models": [
                "claude-3-5-sonnet-latest",
                "claude-3-7-sonnet-latest",
                "claude-3-opus-latest",
            ],
            "note": "Configured defaults. Override with your own model id if needed.",
        }

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract first JSON object from text."""
        if not text:
            return None
        raw = text.strip()

        # Remove markdown fences if present.
        if "```" in raw:
            raw = raw.replace("```json", "```")
            chunks = [c.strip() for c in raw.split("```") if c.strip()]
            for chunk in chunks:
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    continue

        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    def _call_ollama_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 90.0,
    ) -> str:
        """Call Ollama /api/chat and return assistant text content."""
        import requests

        response = requests.post(
            f"{self._ollama_base_url()}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message", {}) if isinstance(payload, dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        return str(content or "")

    def _call_openai_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 90.0,
        api_key_override: Optional[str] = None,
    ) -> str:
        import requests
        api_key = (api_key_override or os.getenv("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")
        response = requests.post(
            f"{self._openai_base_url()}/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.1},
            timeout=timeout,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices", []) if isinstance(payload, dict) else []
        if not choices:
            return ""
        msg = choices[0].get("message", {})
        return str(msg.get("content", "") or "")

    def _call_anthropic_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 90.0,
        api_key_override: Optional[str] = None,
    ) -> str:
        import requests
        api_key = (api_key_override or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY")

        system_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        response = requests.post(
            f"{self._anthropic_base_url()}/messages",
            json={
                "model": model,
                "max_tokens": 1000,
                "temperature": 0.1,
                "system": "\n\n".join(system_parts),
                "messages": non_system,
            },
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content", []) if isinstance(payload, dict) else []
        chunks: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                chunks.append(str(part.get("text", "")))
        return "".join(chunks).strip()

    def _call_llm_chat(
        self,
        provider: str,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 90.0,
        api_key_override: Optional[str] = None,
    ) -> str:
        provider = provider.lower().strip()
        if provider == "ollama":
            return self._call_ollama_chat(model, messages, timeout)
        if provider == "openai":
            return self._call_openai_chat(model, messages, timeout, api_key_override=api_key_override)
        if provider == "anthropic":
            return self._call_anthropic_chat(model, messages, timeout, api_key_override=api_key_override)
        raise RuntimeError(f"Unsupported provider: {provider}")

    def _should_use_tools(
        self,
        provider: str,
        model: str,
        user_prompt: str,
        tool_catalog_json: str,
        api_key_override: Optional[str] = None,
    ) -> bool:
        router_system = (
            "You are a router that decides if tools are needed. "
            "Reply ONLY with YES or NO. No other words."
        )
        router_user = (
            f"User request:\n{user_prompt}\n\n"
            f"Available tools:\n{tool_catalog_json}\n\n"
            "Do you need to call tools to answer?"
        )
        raw = self._call_llm_chat(
            provider,
            model,
            [{"role": "system", "content": router_system}, {"role": "user", "content": router_user}],
            timeout=60.0,
            api_key_override=api_key_override,
        )
        verdict = str(raw or "").strip().lower()
        return verdict.startswith("y")

    async def llm_chat_with_tools(
        self,
        provider: str,
        server_id: str,
        model: str,
        user_prompt: str,
        max_steps: int = 6,
        auto_tools: bool = True,
        api_key_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run provider tool-use loop against selected MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        provider = provider.lower().strip()
        if not model:
            raise ValueError("model is required")
        if not user_prompt or not user_prompt.strip():
            raise ValueError("prompt is required")

        tools = await self.get_tools(server_id)
        compact_tools = [
            {
                "name": t.get("name"),
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema") or t.get("inputSchema") or {},
            }
            for t in tools
            if t.get("name")
        ]
        available_tool_names = {t["name"] for t in compact_tools}
        tool_catalog = json.dumps(compact_tools, ensure_ascii=False, indent=2)

        planner_system = (
            "You are a tool-using assistant for an MCP app. "
            "You MUST reply ONLY with JSON object and nothing else.\n"
            "Allowed JSON shapes:\n"
            "1) {\"type\":\"tool_call\",\"tool\":\"<name>\",\"arguments\":{...},\"reasoning\":\"...\"}\n"
            "2) {\"type\":\"final\",\"answer\":\"...\"}\n"
            "Use one tool call at a time. After receiving tool result, continue or finalize."
        )

        if auto_tools:
            try:
                use_tools = await asyncio.to_thread(
                    self._should_use_tools, provider, model, user_prompt, tool_catalog, api_key_override
                )
            except Exception:
                use_tools = True
            if not use_tools:
                try:
                    answer = await asyncio.to_thread(
                        self._call_llm_chat,
                        provider,
                        model,
                        [{"role": "system", "content": "You are a helpful assistant."},
                         {"role": "user", "content": user_prompt}],
                        90.0,
                        api_key_override,
                    )
                except Exception as e:
                    return {
                        "status": "error",
                        "provider": provider,
                        "model": model,
                        "error": f"{provider} call failed: {e}",
                        "steps": [],
                        "used_tools": False,
                    }
                return {
                    "status": "success",
                    "provider": provider,
                    "model": model,
                    "final_answer": str(answer).strip(),
                    "steps": [],
                    "used_tools": False,
                }

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": planner_system},
            {
                "role": "user",
                "content": (
                    f"User request:\n{user_prompt}\n\n"
                    f"Available tools:\n{tool_catalog}\n\n"
                    "Choose the next action now."
                ),
            },
        ]

        steps: List[Dict[str, Any]] = []

        for step_index in range(1, max(1, int(max_steps)) + 1):
            started_at = datetime.now()
            try:
                raw = await asyncio.to_thread(self._call_llm_chat, provider, model, messages, 120.0, api_key_override)
            except Exception as e:
                return {
                    "status": "error",
                    "provider": provider,
                    "model": model,
                    "error": f"{provider} call failed: {e}",
                    "steps": steps,
                }

            decision = self._extract_json_object(raw)
            if not decision:
                return {
                    "status": "error",
                    "provider": provider,
                    "model": model,
                    "error": "Model did not return valid JSON action",
                    "raw": raw,
                    "steps": steps,
                }

            decision_type = str(decision.get("type", "")).strip().lower()

            if decision_type == "final":
                answer = str(decision.get("answer", "")).strip() or "Done."
                return {
                    "status": "success",
                    "provider": provider,
                    "model": model,
                    "final_answer": answer,
                    "steps": steps,
                    "used_tools": True,
                }

            if decision_type != "tool_call":
                return {
                    "status": "error",
                    "provider": provider,
                    "model": model,
                    "error": f"Unsupported action type: {decision_type}",
                    "decision": decision,
                    "steps": steps,
                }

            tool_name = str(decision.get("tool", "")).strip()
            arguments = decision.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}

            if tool_name not in available_tool_names:
                return {
                    "status": "error",
                    "provider": provider,
                    "model": model,
                    "error": f"Model requested unknown tool: {tool_name}",
                    "decision": decision,
                    "steps": steps,
                }

            tool_result = await self.execute_tool(server_id, tool_name, arguments)
            duration = (datetime.now() - started_at).total_seconds() * 1000

            steps.append(
                {
                    "step": step_index,
                    "type": "tool_call",
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": tool_result,
                    "duration": duration,
                }
            )

            messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool result for `{tool_name}`:\n"
                        f"{json.dumps(tool_result, ensure_ascii=False)}\n\n"
                        "Now choose next action (tool_call or final)."
                    ),
                }
            )

        return {
            "status": "success",
            "provider": provider,
            "model": model,
            "final_answer": "Max steps reached. Partial execution completed.",
            "steps": steps,
            "used_tools": True,
        }
    
    
    # NEW: Test Suites
    def create_test_suite(
        self,
        name: str,
        description: str,
        test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create a new test suite."""
        try:
            import uuid
            
            suite_id = str(uuid.uuid4())[:8]
            
            cases = [
                TestCase(
                    id=tc.get('id', str(uuid.uuid4())[:8]),
                    name=tc.get('name', 'Unnamed Test'),
                    server_id=tc['server_id'],
                    tool_name=tc['tool_name'],
                    parameters=tc['parameters'],
                    expected_status=tc.get('expected_status'),
                    created_at=tc.get('created_at', datetime.now().isoformat())
                )
                for tc in test_cases
            ]
            
            suite = TestSuite(
                id=suite_id,
                name=name,
                description=description,
                test_cases=cases,
                created_at=datetime.now().isoformat()
            )
            
            self.test_suites[suite_id] = suite
            self._save_test_suite(suite)
            
            return {
                'status': 'success',
                'suite': asdict(suite)
            }
        
        except Exception as e:
            logger.error(f"Failed to create test suite: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def run_test_suite(self, suite_id: str) -> Dict[str, Any]:
        """Run a test suite."""
        if suite_id not in self.test_suites:
            raise ValueError(f"Test suite {suite_id} not found")
        
        suite = self.test_suites[suite_id]
        results = []
        
        for test_case in suite.test_cases:
            try:
                result = await self.execute_tool(
                    test_case.server_id,
                    test_case.tool_name,
                    test_case.parameters
                )
                
                passed = True
                if test_case.expected_status:
                    passed = result.get('status') == test_case.expected_status
                
                results.append({
                    'test_id': test_case.id,
                    'test_name': test_case.name,
                    'passed': passed,
                    'result': result,
                    'expected_status': test_case.expected_status
                })
            
            except Exception as e:
                results.append({
                    'test_id': test_case.id,
                    'test_name': test_case.name,
                    'passed': False,
                    'error': str(e),
                    'expected_status': test_case.expected_status
                })
        
        # Update last run
        suite.last_run = datetime.now().isoformat()
        self._save_test_suite(suite)
        
        total = len(results)
        passed = sum(1 for r in results if r.get('passed', False))
        
        return {
            'status': 'success',
            'suite_id': suite_id,
            'suite_name': suite.name,
            'total': total,
            'passed': passed,
            'failed': total - passed,
            'results': results,
            'run_at': suite.last_run
        }
    
    def delete_test_suite(self, suite_id: str) -> Dict[str, Any]:
        """Delete a test suite."""
        if suite_id not in self.test_suites:
            raise ValueError(f"Test suite {suite_id} not found")
        
        try:
            suite_file = self.test_suites_dir / f"{suite_id}.json"
            if suite_file.exists():
                suite_file.unlink()
            
            del self.test_suites[suite_id]
            
            return {'status': 'success'}
        
        except Exception as e:
            logger.error(f"Failed to delete test suite: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    # NEW: Export Reports
    def export_metrics(self, format: str = 'json') -> str:
        """Export metrics in various formats."""
        metrics = self.get_metrics_summary()
        logs = self.activity_logs[-100:]
        servers_data = [asdict(s) for s in self.servers.values()]
        
        timestamp = datetime.now().isoformat()
        
        if format == 'json':
            return json.dumps({
                'metrics': metrics,
                'servers': servers_data,
                'logs': [asdict(log) for log in logs],
                'exported_at': timestamp
            }, indent=2)
        
        elif format == 'markdown':
            md = f"""# PolyMCP Inspector Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

- **Total Requests:** {metrics['total_calls']}
- **Average Time:** {metrics['avg_time']:.2f}ms
- **Success Rate:** {metrics['success_rate']:.1f}%
- **Active Servers:** {metrics['active_servers']}/{metrics['total_servers']}
- **Total Tools:** {metrics['total_tools']}

## Servers

"""
            for server in servers_data:
                md += f"""### {server['name']}
- **Type:** {server['type']}
- **URL:** {server['url']}
- **Status:** {server['status']}
- **Tools:** {server['tools_count']}
- **Connected:** {server['connected_at']}

"""
            
            md += "## Recent Activity\n\n"
            for log in logs[-20:]:
                status_emoji = "✅" if log.status == 200 else "❌"
                md += f"- {status_emoji} `{log.timestamp}` - {log.method}"
                if log.tool_name:
                    md += f" ({log.tool_name})"
                md += f" - {log.duration:.0f}ms"
                if log.error:
                    md += f" - Error: {log.error}"
                md += "\n"
            
            md += f"\n---\n\n*Generated by PolyMCP Inspector*\n"
            
            return md
        
        elif format == 'html':
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>PolyMCP Inspector Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 2rem; }}
        h1, h2 {{ border-bottom: 2px solid #e5e5e5; padding-bottom: 0.5rem; }}
        .metric {{ display: inline-block; margin: 1rem; padding: 1rem; border: 1px solid #e5e5e5; border-radius: 4px; }}
        .metric-value {{ font-size: 2rem; font-weight: bold; }}
        .metric-label {{ color: #666; font-size: 0.875rem; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e5e5; }}
        .success {{ color: #22c55e; }}
        .error {{ color: #ef4444; }}
    </style>
</head>
<body>
    <h1>PolyMCP Inspector Report</h1>
    <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <h2>Summary</h2>
    <div class="metric">
        <div class="metric-value">{metrics['total_calls']}</div>
        <div class="metric-label">Total Requests</div>
    </div>
    <div class="metric">
        <div class="metric-value">{metrics['avg_time']:.1f}ms</div>
        <div class="metric-label">Avg Response Time</div>
    </div>
    <div class="metric">
        <div class="metric-value">{metrics['success_rate']:.1f}%</div>
        <div class="metric-label">Success Rate</div>
    </div>
    <div class="metric">
        <div class="metric-value">{metrics['active_servers']}/{metrics['total_servers']}</div>
        <div class="metric-label">Active Servers</div>
    </div>
    
    <h2>Servers</h2>
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Tools</th>
            </tr>
        </thead>
        <tbody>
"""
            for server in servers_data:
                status_class = 'success' if server['status'] == 'connected' else 'error'
                html += f"""
            <tr>
                <td>{server['name']}</td>
                <td>{server['type']}</td>
                <td class="{status_class}">{server['status']}</td>
                <td>{server['tools_count']}</td>
            </tr>
"""
            
            html += """
        </tbody>
    </table>
    
    <h2>Recent Activity</h2>
    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>Method</th>
                <th>Tool</th>
                <th>Status</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody>
"""
            for log in logs[-20:]:
                status_class = 'success' if log.status == 200 else 'error'
                html += f"""
            <tr>
                <td>{log.timestamp}</td>
                <td>{log.method}</td>
                <td>{log.tool_name or '-'}</td>
                <td class="{status_class}">{log.status}</td>
                <td>{log.duration:.0f}ms</td>
            </tr>
"""
            
            html += """
        </tbody>
    </table>
    
    <footer style="margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e5e5e5; color: #666;">
        <p>Generated by PolyMCP Inspector</p>
    </footer>
</body>
</html>
"""
            return html
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _update_metrics(self, server_id: str, tool_name: str, duration: float, success: bool):
        """Update tool metrics."""
        if tool_name not in self.tool_metrics[server_id]:
            self.tool_metrics[server_id][tool_name] = ToolMetrics(
                name=tool_name,
                calls=0,
                total_time=0.0,
                avg_time=0.0,
                success_count=0,
                error_count=0
            )
        
        metrics = self.tool_metrics[server_id][tool_name]
        metrics.calls += 1
        metrics.total_time += duration
        metrics.avg_time = metrics.total_time / metrics.calls
        metrics.last_called = datetime.now().isoformat()
        
        if success:
            metrics.success_count += 1
        else:
            metrics.error_count += 1
    
    def _log_activity(
        self,
        server_id: str,
        method: str,
        tool_name: Optional[str],
        status: int,
        duration: float,
        error: Optional[str] = None
    ):
        """Log activity entry."""
        log = ActivityLog(
            timestamp=datetime.now().isoformat(),
            server_id=server_id,
            method=method,
            tool_name=tool_name,
            status=status,
            duration=duration,
            error=error
        )
        
        self.activity_logs.append(log)
        
        if len(self.activity_logs) > self.max_logs:
            self.activity_logs = self.activity_logs[-self.max_logs:]
    
    async def _broadcast_update(self, event_type: str, data: Any):
        """Broadcast update to all WebSocket connections."""
        message = json.dumps({
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
        
        disconnected = set()
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except:
                disconnected.add(ws)
        
        self.active_connections -= disconnected
    
    async def register_websocket(self, websocket: WebSocket):
        """Register WebSocket connection."""
        self.active_connections.add(websocket)
    
    async def unregister_websocket(self, websocket: WebSocket):
        """Unregister WebSocket connection."""
        self.active_connections.discard(websocket)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get overall metrics summary."""
        total_calls = 0
        total_time = 0.0
        success_count = 0
        error_count = 0
        
        for server_metrics in self.tool_metrics.values():
            for metrics in server_metrics.values():
                total_calls += metrics.calls
                total_time += metrics.total_time
                success_count += metrics.success_count
                error_count += metrics.error_count
        
        avg_time = (total_time / total_calls) if total_calls > 0 else 0.0
        success_rate = (success_count / total_calls * 100) if total_calls > 0 else 0.0
        
        return {
            'total_calls': total_calls,
            'avg_time': avg_time,
            'success_rate': success_rate,
            'active_servers': len([s for s in self.servers.values() if s.status == 'connected']),
            'total_servers': len(self.servers),
            'total_tools': sum(s.tools_count for s in self.servers.values())
        }
    
    async def cleanup(self):
        """Cleanup all connections."""
        for client in self.stdio_clients.values():
            try:
                await client.stop()
            except:
                pass
        
        self.stdio_clients.clear()
        self.stdio_adapters.clear()
        self.active_connections.clear()


class InspectorServer:
    """
    Main Inspector Server.
    Serves web UI and handles API/WebSocket requests.
    
    ENHANCED with all 5 new features.
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6274,
        verbose: bool = False,
        secure_mode: bool = False,
        api_key: Optional[str] = None,
        allowed_origins: Optional[List[str]] = None,
        rate_limit_per_minute: int = 120,
        rate_limit_window_seconds: int = 60,
    ):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.secure_mode = secure_mode
        self.api_key = api_key
        self.rate_limit_per_minute = max(10, int(rate_limit_per_minute))
        self.rate_limit_window_seconds = max(10, int(rate_limit_window_seconds))
        self._rate_limit_buckets: Dict[str, List[float]] = defaultdict(list)
        self.app = FastAPI(title="PolyMCP Inspector")
        self.manager = ServerManager(verbose=verbose)

        if allowed_origins:
            cors_origins = allowed_origins
        else:
            cors_origins = [
                f"http://{host}:{port}",
                f"https://{host}:{port}",
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
            ]

        # CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Inspector-API-Key"],
        )

        @self.app.middleware("http")
        async def security_middleware(request: Request, call_next):
            if request.url.path.startswith("/api/"):
                now_ts = datetime.now().timestamp()
                ip = (request.client.host if request.client else "unknown")
                bucket = self._rate_limit_buckets[ip]
                cutoff = now_ts - self.rate_limit_window_seconds
                bucket[:] = [ts for ts in bucket if ts >= cutoff]
                if len(bucket) >= self.rate_limit_per_minute:
                    return PlainTextResponse("Rate limit exceeded", status_code=429)
                bucket.append(now_ts)

                if self.secure_mode and not self._is_http_request_authorized(request):
                    return PlainTextResponse("Unauthorized", status_code=401)

            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            # Allow Tauri WebView iframe embedding
            origin = (request.headers.get("origin") or "").lower()
            referer = (request.headers.get("referer") or "").lower()
            is_tauri = (
                origin.startswith("tauri://")
                or referer.startswith("tauri://")
                or origin.startswith("http://tauri.localhost")
                or origin.startswith("https://tauri.localhost")
                or referer.startswith("http://tauri.localhost")
                or referer.startswith("https://tauri.localhost")
            )
            if not is_tauri:
                response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["Referrer-Policy"] = "no-referrer"
            if self.secure_mode:
                response.headers["Cache-Control"] = "no-store"
            return response

        self._setup_routes()

    def _is_http_request_authorized(self, request: Request) -> bool:
        if not self.secure_mode:
            return True
        if not self.api_key:
            return False
        header_key = request.headers.get("x-inspector-api-key", "").strip()
        auth = request.headers.get("authorization", "").strip()
        bearer_key = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return (
            secrets.compare_digest(header_key or "", self.api_key)
            or secrets.compare_digest(bearer_key or "", self.api_key)
        )

    def _is_websocket_authorized(self, websocket: WebSocket) -> bool:
        if not self.secure_mode:
            return True
        if not self.api_key:
            return False
        query_key = websocket.query_params.get("api_key", "").strip()
        header_key = websocket.headers.get("x-inspector-api-key", "").strip()
        auth = websocket.headers.get("authorization", "").strip()
        bearer_key = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return (
            secrets.compare_digest(query_key or "", self.api_key)
            or secrets.compare_digest(header_key or "", self.api_key)
            or secrets.compare_digest(bearer_key or "", self.api_key)
        )
    
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def serve_ui():
            """Serve the inspector UI."""
            html_path = Path(__file__).parent / "static" / "index.html"
            if html_path.exists():
                return FileResponse(html_path)
            else:
                return HTMLResponse("<h1>PolyMCP Inspector</h1><p>UI file not found</p>")

        @self.app.get("/icon.png")
        async def serve_icon():
            """Serve inspector icon used by chat/avatar UI."""
            icon_path = Path(__file__).parent / "static" / "icon.png"
            if icon_path.exists():
                return FileResponse(icon_path)
            raise HTTPException(404, "Icon file not found")
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            if not self._is_websocket_authorized(websocket):
                await websocket.close(code=1008)
                return
            await websocket.accept()
            await self.manager.register_websocket(websocket)
            
            try:
                await websocket.send_json({
                    'type': 'initial_state',
                    'data': {
                        'servers': [asdict(s) for s in self.manager.servers.values()],
                        'metrics': self.manager.get_metrics_summary()
                    }
                })
                
                while True:
                    data = await websocket.receive_json()
                    await self._handle_ws_message(websocket, data)
            
            except WebSocketDisconnect:
                await self.manager.unregister_websocket(websocket)
        
        # Server Management
        @self.app.post("/api/servers/add")
        async def add_server(server_config: Dict[str, Any]):
            """Add a new server."""
            server_type = server_config.get('type', 'http')
            server_id = server_config.get('id', f"server_{len(self.manager.servers)}")
            name = server_config.get('name', 'Unnamed Server')
            
            if server_type == 'http':
                url = server_config.get('url')
                if not url:
                    raise HTTPException(400, "URL required for HTTP server")
                result = await self.manager.add_http_server(server_id, name, url)
            else:
                command = server_config.get('command')
                args = server_config.get('args', [])
                env = server_config.get('env')
                if not command:
                    raise HTTPException(400, "Command required for stdio server")
                result = await self.manager.add_stdio_server(server_id, name, command, args, env)
            
            return result
        
        @self.app.delete("/api/servers/{server_id}")
        async def remove_server(server_id: str):
            """Remove a server."""
            return await self.manager.remove_server(server_id)
        
        @self.app.get("/api/servers")
        async def list_servers():
            """List all servers."""
            return {'servers': [asdict(s) for s in self.manager.servers.values()]}
        
        # Tools
        @self.app.get("/api/servers/{server_id}/tools")
        async def get_tools(server_id: str):
            """Get tools from a server."""
            tools = await self.manager.get_tools(server_id)
            metrics = self.manager.tool_metrics.get(server_id, {})
            
            enriched_tools = []
            for tool in tools:
                tool_data = tool.copy()
                tool_name = tool.get('name')
                if tool_name in metrics:
                    tool_data['metrics'] = asdict(metrics[tool_name])
                enriched_tools.append(tool_data)
            
            return {'tools': enriched_tools}
        
        @self.app.post("/api/servers/{server_id}/tools/{tool_name}/execute")
        async def execute_tool(server_id: str, tool_name: str, parameters: Dict[str, Any]):
            """Execute a tool."""
            return await self.manager.execute_tool(server_id, tool_name, parameters)
        
        # NEW: Resources
        @self.app.get("/api/servers/{server_id}/resources")
        async def list_resources(server_id: str):
            """List resources from server."""
            resources = await self.manager.list_resources(server_id)
            return {'resources': resources}
        
        @self.app.post("/api/servers/{server_id}/resources/read")
        async def read_resource(server_id: str, uri: str = Body(..., embed=True)):
            """Read a resource."""
            return await self.manager.read_resource(server_id, uri)
        
        # NEW: Prompts
        @self.app.get("/api/servers/{server_id}/prompts")
        async def list_prompts(server_id: str):
            """List prompts from server."""
            prompts = await self.manager.list_prompts(server_id)
            return {'prompts': prompts}
        
        @self.app.post("/api/servers/{server_id}/prompts/get")
        async def get_prompt(
            server_id: str,
            prompt_name: str = Body(...),
            arguments: Dict[str, Any] = Body(...)
        ):
            """Get rendered prompt."""
            return await self.manager.get_prompt(server_id, prompt_name, arguments)

        @self.app.post("/api/servers/{server_id}/mcp/request")
        async def mcp_request(
            server_id: str,
            method: str = Body(...),
            params: Dict[str, Any] = Body(default_factory=dict),
        ):
            """Proxy arbitrary MCP method request (advanced inspector use)."""
            return await self.manager.proxy_mcp_request(server_id, method, params)

        # LLM integration
        @self.app.get("/api/llm/providers")
        async def list_llm_providers(request: Request):
            """List configured LLM providers and availability."""
            ollama = self.manager.list_ollama_models()
            openai_key = request.headers.get("X-OpenAI-API-Key", "").strip() or None
            anthropic_key = request.headers.get("X-Anthropic-API-Key", "").strip() or None
            openai = self.manager.list_openai_models(openai_key)
            anthropic = self.manager.list_anthropic_models(anthropic_key)
            return {
                "providers": [
                    {
                        "id": "ollama",
                        "name": "Ollama",
                        "status": ollama.get("status"),
                        "base_url": ollama.get("base_url"),
                        "models_count": len(ollama.get("models", [])),
                        "error": ollama.get("error"),
                    },
                    {
                        "id": "openai",
                        "name": "OpenAI",
                        "status": openai.get("status"),
                        "models_count": len(openai.get("models", [])),
                        "error": openai.get("error"),
                    },
                    {
                        "id": "anthropic",
                        "name": "Anthropic",
                        "status": anthropic.get("status"),
                        "models_count": len(anthropic.get("models", [])),
                        "error": anthropic.get("error"),
                    }
                ]
            }

        @self.app.get("/api/llm/ollama/models")
        async def list_ollama_models():
            """List local Ollama models."""
            return self.manager.list_ollama_models()

        @self.app.get("/api/llm/openai/models")
        async def list_openai_models(request: Request):
            """List OpenAI models."""
            openai_key = request.headers.get("X-OpenAI-API-Key", "").strip() or None
            return self.manager.list_openai_models(openai_key)

        @self.app.get("/api/llm/anthropic/models")
        async def list_anthropic_models(request: Request):
            """List Anthropic models."""
            anthropic_key = request.headers.get("X-Anthropic-API-Key", "").strip() or None
            return self.manager.list_anthropic_models(anthropic_key)

        @self.app.post("/api/servers/{server_id}/llm/chat")
        async def llm_chat(
            request: Request,
            server_id: str,
            provider: str = Body("ollama"),
            model: str = Body(...),
            prompt: str = Body(...),
            max_steps: int = Body(6),
            auto_tools: bool = Body(True),
            api_key: Optional[str] = Body(None),
        ):
            """Run LLM + MCP tool loop against selected server."""
            provider_id = provider.lower().strip()
            resolved_api_key = (api_key or "").strip() or None
            if provider_id == "openai":
                header_key = request.headers.get("X-OpenAI-API-Key", "").strip()
                if header_key:
                    resolved_api_key = header_key
            elif provider_id == "anthropic":
                header_key = request.headers.get("X-Anthropic-API-Key", "").strip()
                if header_key:
                    resolved_api_key = header_key

            return await self.manager.llm_chat_with_tools(
                provider=provider,
                server_id=server_id,
                model=model,
                user_prompt=prompt,
                max_steps=max_steps,
                auto_tools=auto_tools,
                api_key_override=resolved_api_key,
            )
        
        # NEW: Test Suites
        @self.app.get("/api/test-suites")
        async def list_test_suites():
            """List all test suites."""
            return {
                'suites': [asdict(suite) for suite in self.manager.test_suites.values()]
            }
        
        @self.app.post("/api/test-suites")
        async def create_test_suite(
            name: str = Body(...),
            description: str = Body(...),
            test_cases: List[Dict[str, Any]] = Body(...)
        ):
            """Create a test suite."""
            return self.manager.create_test_suite(name, description, test_cases)
        
        @self.app.post("/api/test-suites/{suite_id}/run")
        async def run_test_suite(suite_id: str):
            """Run a test suite."""
            return await self.manager.run_test_suite(suite_id)
        
        @self.app.delete("/api/test-suites/{suite_id}")
        async def delete_test_suite(suite_id: str):
            """Delete a test suite."""
            return self.manager.delete_test_suite(suite_id)
        
        # NEW: Export
        @self.app.get("/api/export/metrics")
        async def export_metrics(format: str = 'json'):
            """Export metrics in various formats."""
            content = self.manager.export_metrics(format)
            
            if format == 'json':
                return PlainTextResponse(content, media_type='application/json')
            elif format == 'markdown':
                return PlainTextResponse(content, media_type='text/markdown')
            elif format == 'html':
                return HTMLResponse(content)
            else:
                raise HTTPException(400, f"Unsupported format: {format}")
        
        # Metrics & Logs
        @self.app.get("/api/metrics")
        async def get_metrics():
            """Get overall metrics."""
            return self.manager.get_metrics_summary()
        
        @self.app.get("/api/metrics/{server_id}")
        async def get_server_metrics(server_id: str):
            """Get metrics for a specific server."""
            if server_id not in self.manager.tool_metrics:
                raise HTTPException(404, "Server not found")
            
            metrics = self.manager.tool_metrics[server_id]
            return {'metrics': {name: asdict(m) for name, m in metrics.items()}}
        
        @self.app.get("/api/logs")
        async def get_logs(limit: int = 100):
            """Get activity logs."""
            logs = self.manager.activity_logs[-limit:]
            return {'logs': [asdict(log) for log in logs]}
        
        @self.app.get("/api/health")
        async def health_check():
            """Health check endpoint."""
            return {'status': 'healthy', 'servers': len(self.manager.servers)}
    
    async def _handle_ws_message(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle incoming WebSocket messages."""
        msg_type = data.get('type')
        
        if msg_type == 'ping':
            await websocket.send_json({'type': 'pong'})
        elif msg_type == 'get_state':
            await websocket.send_json({
                'type': 'state_update',
                'data': {
                    'servers': [asdict(s) for s in self.manager.servers.values()],
                    'metrics': self.manager.get_metrics_summary()
                }
            })


async def run_inspector(
    host: str = "127.0.0.1",
    port: int = 6274,
    verbose: bool = False,
    open_browser: bool = True,
    servers: Optional[List[Dict[str, Any]]] = None,
    secure_mode: bool = False,
    api_key: Optional[str] = None,
    allowed_origins: Optional[List[str]] = None,
    rate_limit_per_minute: int = 120,
    rate_limit_window_seconds: int = 60,
):
    """
    Run the PolyMCP Inspector server.
    
    Args:
        host: Server host
        port: Server port
        verbose: Enable verbose logging
        open_browser: Automatically open browser
        servers: Initial servers to add
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    if secure_mode and not api_key:
        api_key = secrets.token_urlsafe(24)
        logger.warning("Inspector secure mode enabled with auto-generated API key")
        logger.warning("Use this key to access API/UI: %s", api_key)

    inspector = InspectorServer(
        host=host,
        port=port,
        verbose=verbose,
        secure_mode=secure_mode,
        api_key=api_key,
        allowed_origins=allowed_origins,
        rate_limit_per_minute=rate_limit_per_minute,
        rate_limit_window_seconds=rate_limit_window_seconds,
    )
    
    # Add initial servers
    if servers:
        for server_config in servers:
            try:
                server_type = server_config.get('type', 'http')
                server_id = server_config.get('id', f"server_{len(inspector.manager.servers)}")
                name = server_config.get('name', 'Unnamed Server')
                
                if server_type == 'http':
                    url = server_config.get('url')
                    await inspector.manager.add_http_server(server_id, name, url)
                else:
                    command = server_config.get('command')
                    args = server_config.get('args', [])
                    env = server_config.get('env')
                    await inspector.manager.add_stdio_server(
                        server_id, name, command, args, env
                    )
            except Exception as e:
                logger.error(f"Failed to add initial server: {e}")
    
    # Open browser
    if open_browser:
        await asyncio.sleep(1)
        url = f"http://{host}:{port}"
        if secure_mode and api_key:
            url = f"{url}/?api_key={api_key}"
        webbrowser.open(url)
    
    # Run server
    logger.warning("Inspector server running on http://%s:%s", host, port)
    config = uvicorn.Config(
        inspector.app,
        host=host,
        port=port,
        log_level="info" if verbose else "warning",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    finally:
        await inspector.manager.cleanup()
