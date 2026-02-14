"""
PolyMCP Inspector Server - ENHANCED Production Implementation
FastAPI server with WebSocket for real-time MCP server inspection.

FEATURES:
- Streamable HTTP MCP transport (SSE + Mcp-Session-Id)
- Persistent browser sessions for Playwright MCP (background keepalive)
- Capability-aware: only calls methods the server advertises
- Auto session recovery on 404 (session expired)
- Resources, Prompts, Test Suites, Export
"""

import asyncio
import json
import logging
import os
import re
import secrets
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from urllib.parse import quote

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx

from ..mcp_stdio_client import MCPStdioClient, MCPStdioAdapter, MCPServerConfig


logger = logging.getLogger(__name__)

JSONRPC_METHOD_NOT_FOUND = -32601

# How often to ping MCP servers to keep browser sessions alive (seconds)
SESSION_KEEPALIVE_INTERVAL = 8


@dataclass
class ServerInfo:
    id: str
    name: str
    url: str
    type: str
    status: str
    tools_count: int
    connected_at: str
    last_request: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ToolMetrics:
    name: str
    calls: int
    total_time: float
    avg_time: float
    success_count: int
    error_count: int
    last_called: Optional[str] = None


@dataclass
class ActivityLog:
    timestamp: str
    server_id: str
    method: str
    tool_name: Optional[str]
    status: int
    duration: float
    error: Optional[str] = None


@dataclass
class TestCase:
    id: str
    name: str
    server_id: str
    tool_name: str
    parameters: Dict[str, Any]
    expected_status: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class TestSuite:
    id: str
    name: str
    description: str
    test_cases: List[TestCase]
    created_at: str
    last_run: Optional[str] = None


class MethodNotSupportedError(Exception):
    pass


class SessionKeepAlive:
    """
    Background thread that pings MCP servers to keep their sessions alive.

    Playwright MCP closes the browser when the session goes idle.
    This sends a lightweight ping (tools/list) every N seconds to
    prevent that during multi-step LLM tool loops.
    """

    def __init__(self, manager: 'ServerManager', interval: float = SESSION_KEEPALIVE_INTERVAL):
        self._manager = manager
        self._interval = interval
        self._active_servers: Dict[str, float] = {}  # server_id -> last_activity_time
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def mark_active(self, server_id: str):
        """Mark a server as actively being used (resets keepalive timer)."""
        with self._lock:
            self._active_servers[server_id] = time.time()

    def mark_idle(self, server_id: str):
        """Mark server as idle — stop sending keepalives."""
        with self._lock:
            self._active_servers.pop(server_id, None)

    def start(self):
        """Start the keepalive background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="mcp-keepalive")
        self._thread.start()

    def stop(self):
        """Stop the keepalive background thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self):
        """Background loop: ping active servers periodically."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                break

            with self._lock:
                servers_to_ping = dict(self._active_servers)

            now = time.time()
            for server_id, last_activity in servers_to_ping.items():
                # Only ping if there's been recent activity (within 5 minutes)
                if now - last_activity > 300:
                    with self._lock:
                        self._active_servers.pop(server_id, None)
                    continue

                try:
                    self._ping_server(server_id)
                except Exception as e:
                    logger.debug(f"Keepalive ping failed for {server_id}: {e}")

    def _ping_server(self, server_id: str):
        """Send a lightweight ping to keep the MCP session alive."""
        profile = self._manager.http_profiles.get(server_id)
        if not profile or profile.get("mode") != "jsonrpc":
            return

        endpoint = profile.get("rpc_endpoint")
        if not endpoint:
            return

        try:
            # Use notifications/ping or a lightweight tools/list
            # notifications/ doesn't require a response and is very cheap
            client = self._manager._get_http_client(server_id)
            session_id = self._manager._http_session_ids.get(server_id)

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Connection": "keep-alive",
            }
            if session_id:
                headers["Mcp-Session-Id"] = session_id

            # Send a JSON-RPC notification (no id = no response expected)
            # "notifications/progress" is a standard MCP notification
            payload = {
                "jsonrpc": "2.0",
                "method": "notifications/ping",
            }

            response = client.post(endpoint, json=payload, headers=headers, timeout=5.0)

            # Track new session id if returned
            new_sid = response.headers.get("mcp-session-id")
            if new_sid:
                self._manager._http_session_ids[server_id] = new_sid

            # If server doesn't support notifications/ping, try a lightweight call
            if response.status_code == 404:
                # Session expired — mark idle, manager will reinit on next real call
                with self._lock:
                    self._active_servers.pop(server_id, None)

        except Exception:
            pass  # Best effort


class ServerManager:
    """
    Manages multiple MCP server connections with persistent HTTP sessions
    and background keepalive for browser-based MCP servers (Playwright).
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.servers: Dict[str, ServerInfo] = {}
        self.stdio_clients: Dict[str, MCPStdioClient] = {}
        self.stdio_adapters: Dict[str, MCPStdioAdapter] = {}
        self.http_tools_cache: Dict[str, List[Dict]] = {}
        self.http_profiles: Dict[str, Dict[str, Any]] = {}
        self.http_request_ids: Dict[str, int] = defaultdict(int)
        self._http_session_ids: Dict[str, str] = {}
        self._server_capabilities: Dict[str, Dict[str, Any]] = {}
        self._http_clients: Dict[str, httpx.Client] = {}

        # Session keepalive for browser-based MCP servers
        self._keepalive = SessionKeepAlive(self)
        self._keepalive.start()

        self.tool_metrics: Dict[str, Dict[str, ToolMetrics]] = defaultdict(dict)
        self.activity_logs: deque[ActivityLog] = deque(maxlen=1000)
        self.active_connections: Set[WebSocket] = set()

        self.test_suites: Dict[str, TestSuite] = {}
        self.test_suites_dir = Path.home() / '.polymcp' / 'inspector' / 'test-suites'
        self.test_suites_dir.mkdir(parents=True, exist_ok=True)
        self._load_test_suites()

    # ------------------------------------------------------------------ #
    #  HTTP client management                                             #
    # ------------------------------------------------------------------ #

    def _get_http_client(self, server_id: str) -> httpx.Client:
        if server_id not in self._http_clients:
            self._http_clients[server_id] = httpx.Client(
                timeout=httpx.Timeout(120.0, connect=10.0),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                    keepalive_expiry=600,  # 10 minutes
                ),
                follow_redirects=True,
                http2=False,  # Stick to HTTP/1.1 for better keepalive compatibility
            )
        return self._http_clients[server_id]

    def _close_http_client(self, server_id: str):
        client = self._http_clients.pop(server_id, None)
        if client:
            try:
                client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  Capabilities                                                       #
    # ------------------------------------------------------------------ #

    def _has_capability(self, server_id: str, capability: str) -> bool:
        caps = self._server_capabilities.get(server_id)
        if caps is None:
            server = self.servers.get(server_id)
            if not server:
                return False
            if server.type == 'stdio':
                return True
            profile = self.http_profiles.get(server_id, {})
            if profile.get("mode") == "legacy":
                return capability == "tools"
            return True
        return capability in caps and caps[capability] is not None

    def _store_capabilities(self, server_id: str, init_result: Dict[str, Any]):
        caps = init_result.get("capabilities")
        if isinstance(caps, dict):
            self._server_capabilities[server_id] = caps
        else:
            self._server_capabilities[server_id] = {"tools": {}}
        if self.verbose:
            supported = [k for k, v in self._server_capabilities[server_id].items() if v is not None]
            logger.info(f"Server {server_id} capabilities: {supported}")

    # ------------------------------------------------------------------ #
    #  Test suites                                                        #
    # ------------------------------------------------------------------ #

    def _load_test_suites(self):
        try:
            for f in self.test_suites_dir.glob('*.json'):
                with open(f, 'r') as fh:
                    data = json.load(fh)
                    tcs = [TestCase(**tc) for tc in data.get('test_cases', [])]
                    suite = TestSuite(
                        id=data['id'], name=data['name'],
                        description=data.get('description', ''),
                        test_cases=tcs, created_at=data['created_at'],
                        last_run=data.get('last_run')
                    )
                    self.test_suites[suite.id] = suite
        except Exception as e:
            logger.error(f"Failed to load test suites: {e}")

    def _save_test_suite(self, suite: TestSuite):
        suite_file = self.test_suites_dir / f"{suite.id}.json"
        with open(suite_file, 'w') as f:
            json.dump({
                'id': suite.id, 'name': suite.name,
                'description': suite.description,
                'test_cases': [asdict(tc) for tc in suite.test_cases],
                'created_at': suite.created_at, 'last_run': suite.last_run
            }, f, indent=2)

    # ------------------------------------------------------------------ #
    #  HTTP transport                                                     #
    # ------------------------------------------------------------------ #

    def _get_http_candidates(self, raw_url: str) -> Dict[str, List[str]]:
        normalized = (raw_url or "").strip().rstrip("/")
        if not normalized:
            raise ValueError("Empty server URL")
        rpc: List[str] = []
        legacy: List[str] = []

        def push(lst: List[str], val: str):
            if val and val not in lst:
                lst.append(val)

        push(rpc, normalized)
        push(legacy, normalized)
        if normalized.endswith("/mcp"):
            push(legacy, normalized[:-4].rstrip("/"))
        else:
            push(rpc, f"{normalized}/mcp")
        if normalized.endswith("/list_tools"):
            base = normalized[:-11].rstrip("/")
            push(legacy, base)
            push(rpc, base)
            push(rpc, f"{base}/mcp")
        if normalized.endswith("/invoke"):
            base = normalized[:-7].rstrip("/")
            push(legacy, base)
            push(rpc, f"{base}/mcp")
        return {"rpc": rpc, "legacy": legacy}

    def _next_http_request_id(self, server_id: str) -> int:
        self.http_request_ids[server_id] += 1
        return self.http_request_ids[server_id]

    def _parse_sse_jsonrpc(self, sse_text: str, request_id: Any) -> Dict[str, Any]:
        events: List[str] = []
        data_lines: List[str] = []
        for raw_line in sse_text.split('\n'):
            line = raw_line.rstrip('\r')
            if line == '':
                if data_lines:
                    events.append('\n'.join(data_lines))
                    data_lines = []
                continue
            if line.startswith('data:'):
                val = line[5:]
                if val.startswith(' '):
                    val = val[1:]
                data_lines.append(val)
        if data_lines:
            events.append('\n'.join(data_lines))
        for ps in events:
            try:
                obj = json.loads(ps)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get('id') == request_id:
                return obj
        for ps in events:
            try:
                obj = json.loads(ps)
            except Exception:
                continue
            if isinstance(obj, dict) and ('result' in obj or 'error' in obj):
                return obj
        raise RuntimeError(f"No JSON-RPC response (id={request_id}) in {len(events)} SSE events")

    def _reinitialize_http_session(self, server_id: str, endpoint: str, timeout: float = 10.0):
        logger.info(f"Re-initializing MCP session for {server_id}")
        self._http_session_ids.pop(server_id, None)
        init_result = self._http_jsonrpc_call(
            server_id, endpoint, "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {"subscribe": True}, "prompts": {}},
                "clientInfo": {"name": "polymcp-inspector", "version": "1.3.6"},
            }, timeout, _allow_reinit=False,
        )
        self._store_capabilities(server_id, init_result)
        if server_id in self.http_profiles:
            self.http_profiles[server_id]["initialize"] = init_result
        try:
            self._http_jsonrpc_call(
                server_id, endpoint, "notifications/initialized", {}, 5.0,
                _allow_reinit=False,
            )
        except Exception:
            pass
        logger.info(f"Session re-initialized for {server_id}")

    def _http_jsonrpc_call(
        self, server_id: str, endpoint: str, method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
        _allow_reinit: bool = True,
    ) -> Dict[str, Any]:
        """
        JSON-RPC over Streamable HTTP with persistent connection.
        
        Uses httpx connection pooling + Connection: keep-alive
        to maintain the TCP session between calls.
        """
        client = self._get_http_client(server_id)
        is_notification = method.startswith("notifications/")

        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        request_id = None
        if not is_notification:
            request_id = self._next_http_request_id(server_id)
            payload["id"] = request_id
        if params is not None:
            payload["params"] = params

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Connection": "keep-alive",
        }
        session_id = self._http_session_ids.get(server_id)
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        response = client.post(endpoint, json=payload, headers=headers, timeout=timeout)

        # 404 = session expired
        if response.status_code == 404 and _allow_reinit and not is_notification and method != "initialize":
            logger.warning(f"Session expired for {server_id}, re-initializing")
            self._reinitialize_http_session(server_id, endpoint, timeout)
            return self._http_jsonrpc_call(server_id, endpoint, method, params, timeout, False)

        response.raise_for_status()

        new_sid = response.headers.get("mcp-session-id")
        if new_sid:
            self._http_session_ids[server_id] = new_sid

        if is_notification:
            return {}

        content_type = response.headers.get("content-type", "")
        body_text = response.text.strip()
        if not body_text:
            raise RuntimeError(f"Empty response for {method}")

        if "text/event-stream" in content_type:
            data = self._parse_sse_jsonrpc(body_text, request_id)
        else:
            data = response.json()

        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid response for {method}")

        if "error" in data and data["error"]:
            err = data["error"]
            if isinstance(err, dict):
                code = err.get("code")
                msg = err.get("message", str(err))
                if code == JSONRPC_METHOD_NOT_FOUND:
                    raise MethodNotSupportedError(f"{method} not supported ({code})")
                raise RuntimeError(f"{method} failed ({code}): {msg}")
            raise RuntimeError(f"{method} failed: {err}")

        result = data.get("result", {})
        return result if isinstance(result, dict) else {"value": result}

    # ------------------------------------------------------------------ #
    #  Server lifecycle                                                   #
    # ------------------------------------------------------------------ #

    async def add_http_server(self, server_id: str, name: str, url: str) -> Dict[str, Any]:
        try:
            profile, tools = await self._discover_http_server(server_id, url)
            self.servers[server_id] = ServerInfo(
                id=server_id, name=name, url=url, type='http',
                status='connected', tools_count=len(tools),
                connected_at=datetime.now().isoformat()
            )
            self.http_tools_cache[server_id] = tools
            self.http_profiles[server_id] = profile
            for tool in tools:
                tn = tool.get('name')
                if tn:
                    self.tool_metrics[server_id][tn] = ToolMetrics(
                        name=tn, calls=0, total_time=0.0, avg_time=0.0,
                        success_count=0, error_count=0)
            if self.verbose:
                logger.info(f"Connected to {name} ({len(tools)} tools)")
            await self._broadcast_update('server_added', asdict(self.servers[server_id]))
            return {'status': 'success', 'server': asdict(self.servers[server_id])}
        except Exception as e:
            error_msg = f"Failed to connect to {url}: {e}"
            logger.error(error_msg)
            self.servers[server_id] = ServerInfo(
                id=server_id, name=name, url=url, type='http',
                status='error', tools_count=0,
                connected_at=datetime.now().isoformat(), error=error_msg)
            await self._broadcast_update('server_error', {'server_id': server_id, 'error': error_msg})
            return {'status': 'error', 'error': error_msg}

    async def _discover_http_server(
        self, server_id: str, url: str
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        candidates = self._get_http_candidates(url)
        errors: List[str] = []

        for ep in candidates["rpc"]:
            try:
                init = await asyncio.to_thread(
                    self._http_jsonrpc_call, server_id, ep, "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}, "resources": {"subscribe": True}, "prompts": {}},
                        "clientInfo": {"name": "polymcp-inspector", "version": "1.3.6"},
                    }, 10.0, False)
                self._store_capabilities(server_id, init)
                try:
                    await asyncio.to_thread(
                        self._http_jsonrpc_call, server_id, ep,
                        "notifications/initialized", {}, 5.0, False)
                except Exception:
                    pass
                tr = await asyncio.to_thread(
                    self._http_jsonrpc_call, server_id, ep, "tools/list", {}, 10.0, False)
                tools = tr.get("tools", [])
                if not isinstance(tools, list):
                    tools = []
                return {
                    "mode": "jsonrpc", "rpc_endpoint": ep,
                    "base_url": ep[:-4].rstrip("/") if ep.endswith("/mcp") else ep.rstrip("/"),
                    "initialize": init,
                }, tools
            except Exception as e:
                errors.append(f"JSON-RPC {ep}: {e}")

        client = self._get_http_client(server_id)
        for base in candidates["legacy"]:
            try:
                r = client.get(f"{base}/list_tools", timeout=6)
                r.raise_for_status()
                body = r.json()
                tools = body.get("tools", []) if isinstance(body, dict) else []
                self._server_capabilities[server_id] = {"tools": {}}
                return {"mode": "legacy", "base_url": base}, tools
            except Exception as e:
                errors.append(f"Legacy {base}: {e}")

        raise RuntimeError("; ".join(errors[-5:]))

    async def add_stdio_server(
        self, server_id: str, name: str, command: str,
        args: List[str], env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        try:
            config = MCPServerConfig(command=command, args=args, env=env)
            client = MCPStdioClient(config)
            await client.start()
            adapter = MCPStdioAdapter(client)
            tools = await adapter.get_tools()
            self.stdio_clients[server_id] = client
            self.stdio_adapters[server_id] = adapter
            self.servers[server_id] = ServerInfo(
                id=server_id, name=name, url=f"stdio://{command}",
                type='stdio', status='connected', tools_count=len(tools),
                connected_at=datetime.now().isoformat())
            try:
                init_result = getattr(client, '_init_result', None)
                if init_result and isinstance(init_result, dict):
                    self._store_capabilities(server_id, init_result)
                else:
                    await self._probe_stdio_capabilities(server_id, client)
            except Exception:
                self._server_capabilities[server_id] = {"tools": {}}
            for tool in tools:
                tn = tool.get('name')
                if tn:
                    self.tool_metrics[server_id][tn] = ToolMetrics(
                        name=tn, calls=0, total_time=0.0, avg_time=0.0,
                        success_count=0, error_count=0)
            await self._broadcast_update('server_added', asdict(self.servers[server_id]))
            return {'status': 'success', 'server': asdict(self.servers[server_id])}
        except Exception as e:
            error_msg = f"Failed to start {command}: {e}"
            logger.error(error_msg)
            self.servers[server_id] = ServerInfo(
                id=server_id, name=name, url=f"stdio://{command}",
                type='stdio', status='error', tools_count=0,
                connected_at=datetime.now().isoformat(), error=error_msg)
            await self._broadcast_update('server_error', {'server_id': server_id, 'error': error_msg})
            return {'status': 'error', 'error': error_msg}

    async def _probe_stdio_capabilities(self, server_id: str, client: MCPStdioClient):
        caps: Dict[str, Any] = {"tools": {}}
        for method, cap_name in [("resources/list", "resources"), ("prompts/list", "prompts")]:
            try:
                resp = await client._send_request(method)
                err = resp.get("error")
                if err and isinstance(err, dict) and err.get("code") == JSONRPC_METHOD_NOT_FOUND:
                    continue
                if "error" not in resp or not resp["error"]:
                    caps[cap_name] = {}
            except Exception:
                pass
        self._server_capabilities[server_id] = caps

    async def remove_server(self, server_id: str) -> Dict[str, Any]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")

        # Stop keepalive for this server
        self._keepalive.mark_idle(server_id)

        if server_id in self.stdio_clients:
            try:
                await self.stdio_clients[server_id].stop()
            except Exception:
                pass
            del self.stdio_clients[server_id]
            del self.stdio_adapters[server_id]
        self._close_http_client(server_id)
        self.http_tools_cache.pop(server_id, None)
        self.http_profiles.pop(server_id, None)
        self.http_request_ids.pop(server_id, None)
        self._http_session_ids.pop(server_id, None)
        self._server_capabilities.pop(server_id, None)
        self.tool_metrics.pop(server_id, None)
        del self.servers[server_id]
        await self._broadcast_update('server_removed', {'server_id': server_id})
        return {'status': 'success'}

    # ------------------------------------------------------------------ #
    #  Tools                                                              #
    # ------------------------------------------------------------------ #

    async def get_tools(self, server_id: str) -> List[Dict[str, Any]]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        server = self.servers[server_id]
        if server.type == 'http':
            profile = self.http_profiles.get(server_id, {"mode": "legacy"})
            if profile.get("mode") == "jsonrpc":
                tools: List[Dict[str, Any]] = []
                cursor: Optional[str] = None
                for _ in range(50):
                    p: Dict[str, Any] = {"cursor": cursor} if cursor else {}
                    r = await asyncio.to_thread(
                        self._http_jsonrpc_call, server_id,
                        profile["rpc_endpoint"], "tools/list", p, 15.0, True)
                    page = r.get("tools", [])
                    if isinstance(page, list):
                        tools.extend(page)
                    nc = r.get("nextCursor")
                    if not nc:
                        break
                    cursor = str(nc)
                self.http_tools_cache[server_id] = tools
                return tools
            return self.http_tools_cache.get(server_id, [])
        else:
            if server_id in self.stdio_adapters:
                return await self.stdio_adapters[server_id].get_tools()
            return []

    async def execute_tool(
        self, server_id: str, tool_name: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")

        # Mark server as active for keepalive
        self._keepalive.mark_active(server_id)

        server = self.servers[server_id]
        start_time = datetime.now()
        result: Dict[str, Any] = {}
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy"})
                if profile.get("mode") == "jsonrpc":
                    result = await asyncio.to_thread(
                        self._http_jsonrpc_call, server_id,
                        profile["rpc_endpoint"], "tools/call",
                        {"name": tool_name, "arguments": parameters},
                        120.0, True)
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
                    client = self._get_http_client(server_id)
                    base_url = profile.get("base_url", server.url).rstrip("/")
                    errs: List[str] = []
                    calls = [
                        ("POST", f"{base_url}/tools/{tool_name}", parameters),
                        ("POST", f"{base_url}/invoke/{tool_name}", parameters),
                        ("POST", f"{base_url}/invoke", {"tool": tool_name, "parameters": parameters}),
                    ]
                    found = False
                    for method, ep, pl in calls:
                        try:
                            resp = client.request(method, ep, json=pl, timeout=30,
                                                   headers={"Accept": "application/json"})
                            resp.raise_for_status()
                            ct = resp.headers.get("content-type", "")
                            result = resp.json() if "application/json" in ct else {"result": resp.text}
                            found = True
                            break
                        except Exception as e:
                            errs.append(f"{ep}: {e}")
                    if not found:
                        raise RuntimeError("; ".join(errs[-3:]))
            else:
                adapter = self.stdio_adapters[server_id]
                result = await adapter.invoke_tool(tool_name, parameters)

            duration = (datetime.now() - start_time).total_seconds() * 1000
            self._update_metrics(server_id, tool_name, duration, True)
            self._log_activity(server_id, 'execute_tool', tool_name, 200, duration)
            server.last_request = datetime.now().isoformat()
            await self._broadcast_update('tool_executed', {
                'server_id': server_id, 'tool_name': tool_name, 'duration': duration})
            return {'status': 'success', 'result': result, 'duration': duration}

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            self._update_metrics(server_id, tool_name, duration, False)
            self._log_activity(server_id, 'execute_tool', tool_name, 500, duration, str(e))
            await self._broadcast_update('tool_error', {
                'server_id': server_id, 'tool_name': tool_name, 'error': str(e)})
            return {'status': 'error', 'error': str(e), 'duration': duration}

    # ------------------------------------------------------------------ #
    #  Resources                                                          #
    # ------------------------------------------------------------------ #

    async def list_resources(self, server_id: str) -> List[Dict[str, Any]]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        if not self._has_capability(server_id, "resources"):
            return []
        server = self.servers[server_id]
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy"})
                if profile.get("mode") == "jsonrpc":
                    resources: List[Dict[str, Any]] = []
                    cursor: Optional[str] = None
                    for _ in range(50):
                        p: Dict[str, Any] = {"cursor": cursor} if cursor else {}
                        r = await asyncio.to_thread(
                            self._http_jsonrpc_call, server_id,
                            profile["rpc_endpoint"], "resources/list", p, 15.0, True)
                        page = r.get("resources", [])
                        if isinstance(page, list):
                            resources.extend(page)
                        nc = r.get("nextCursor")
                        if not nc:
                            break
                        cursor = str(nc)
                    return resources
                client = self._get_http_client(server_id)
                base = profile.get("base_url", server.url).rstrip("/")
                resp = client.get(f"{base}/list_resources", timeout=10)
                resp.raise_for_status()
                pl = resp.json()
                return pl.get("resources", []) if isinstance(pl, dict) else []
            else:
                c = self.stdio_clients[server_id]
                resp = await c._send_request("resources/list")
                return resp.get('result', {}).get('resources', [])
        except MethodNotSupportedError:
            caps = self._server_capabilities.get(server_id, {})
            caps.pop("resources", None)
            return []
        except Exception as e:
            if "-32601" in str(e) or "Method not found" in str(e):
                caps = self._server_capabilities.get(server_id, {})
                caps.pop("resources", None)
                return []
            logger.error(f"list_resources failed for {server_id}: {e}")
            return []

    async def read_resource(self, server_id: str, uri: str) -> Dict[str, Any]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        if not self._has_capability(server_id, "resources"):
            return {'status': 'error', 'error': 'No resources support', 'duration': 0}
        server = self.servers[server_id]
        start = datetime.now()
        try:
            result: Dict[str, Any] = {}
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy"})
                if profile.get("mode") == "jsonrpc":
                    result = await asyncio.to_thread(
                        self._http_jsonrpc_call, server_id,
                        profile["rpc_endpoint"], "resources/read",
                        {"uri": uri}, 20.0, True)
                else:
                    client = self._get_http_client(server_id)
                    base = profile.get("base_url", server.url).rstrip("/")
                    encoded = quote(uri, safe="")
                    try:
                        resp = client.get(f"{base}/resources/{encoded}", timeout=15)
                        resp.raise_for_status()
                        ct = resp.headers.get("content-type", "text/plain")
                        if "application/json" in ct:
                            pl = resp.json()
                            result = pl if isinstance(pl, dict) and "contents" in pl else {
                                "contents": [{"uri": uri, "mimeType": "application/json",
                                              "text": json.dumps(pl, ensure_ascii=False, indent=2)}]}
                        else:
                            result = {"contents": [{"uri": uri, "mimeType": ct, "text": resp.text}]}
                    except Exception:
                        resp = client.post(f"{base}/resources/read", json={"uri": uri}, timeout=15)
                        resp.raise_for_status()
                        pl = resp.json()
                        result = pl if isinstance(pl, dict) and "contents" in pl else {"contents": [pl]}
            else:
                c = self.stdio_clients[server_id]
                resp = await c._send_request("resources/read", {"uri": uri})
                result = resp.get('result', {})
            dur = (datetime.now() - start).total_seconds() * 1000
            self._log_activity(server_id, 'read_resource', uri, 200, dur)
            return {'status': 'success', 'contents': result.get('contents', []), 'duration': dur}
        except Exception as e:
            dur = (datetime.now() - start).total_seconds() * 1000
            self._log_activity(server_id, 'read_resource', uri, 500, dur, str(e))
            return {'status': 'error', 'error': str(e), 'duration': dur}

    # ------------------------------------------------------------------ #
    #  Prompts                                                            #
    # ------------------------------------------------------------------ #

    async def list_prompts(self, server_id: str) -> List[Dict[str, Any]]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        if not self._has_capability(server_id, "prompts"):
            return []
        server = self.servers[server_id]
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy"})
                if profile.get("mode") == "jsonrpc":
                    prompts: List[Dict[str, Any]] = []
                    cursor: Optional[str] = None
                    for _ in range(50):
                        p: Dict[str, Any] = {"cursor": cursor} if cursor else {}
                        r = await asyncio.to_thread(
                            self._http_jsonrpc_call, server_id,
                            profile["rpc_endpoint"], "prompts/list", p, 15.0, True)
                        page = r.get("prompts", [])
                        if isinstance(page, list):
                            prompts.extend(page)
                        nc = r.get("nextCursor")
                        if not nc:
                            break
                        cursor = str(nc)
                    return prompts
                return []
            else:
                c = self.stdio_clients[server_id]
                resp = await c._send_request("prompts/list")
                return resp.get('result', {}).get('prompts', [])
        except MethodNotSupportedError:
            caps = self._server_capabilities.get(server_id, {})
            caps.pop("prompts", None)
            return []
        except Exception as e:
            if "-32601" in str(e) or "Method not found" in str(e):
                caps = self._server_capabilities.get(server_id, {})
                caps.pop("prompts", None)
                return []
            logger.error(f"list_prompts failed for {server_id}: {e}")
            return []

    async def get_prompt(
        self, server_id: str, prompt_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        if not self._has_capability(server_id, "prompts"):
            return {'status': 'error', 'error': 'No prompts support', 'duration': 0}
        server = self.servers[server_id]
        start = datetime.now()
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy"})
                if profile.get("mode") != "jsonrpc":
                    raise RuntimeError("Prompts require JSON-RPC endpoint")
                result = await asyncio.to_thread(
                    self._http_jsonrpc_call, server_id,
                    profile["rpc_endpoint"], "prompts/get",
                    {"name": prompt_name, "arguments": arguments}, 20.0, True)
            else:
                c = self.stdio_clients[server_id]
                resp = await c._send_request("prompts/get",
                                              {"name": prompt_name, "arguments": arguments})
                result = resp.get('result', {})
            dur = (datetime.now() - start).total_seconds() * 1000
            self._log_activity(server_id, 'get_prompt', prompt_name, 200, dur)
            return {'status': 'success', 'messages': result.get('messages', []),
                    'description': result.get('description', ''), 'duration': dur}
        except Exception as e:
            dur = (datetime.now() - start).total_seconds() * 1000
            self._log_activity(server_id, 'get_prompt', prompt_name, 500, dur, str(e))
            return {'status': 'error', 'error': str(e), 'duration': dur}

    async def proxy_mcp_request(
        self, server_id: str, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        server = self.servers[server_id]
        start = datetime.now()
        try:
            if server.type == 'http':
                profile = self.http_profiles.get(server_id, {"mode": "legacy"})
                if profile.get("mode") != "jsonrpc":
                    raise RuntimeError("Requires JSON-RPC endpoint")
                result = await asyncio.to_thread(
                    self._http_jsonrpc_call, server_id,
                    profile["rpc_endpoint"], method, params or {}, 30.0, True)
            else:
                c = self.stdio_clients[server_id]
                resp = await c._send_request(method, params or {})
                if "error" in resp and resp["error"]:
                    raise RuntimeError(str(resp["error"]))
                result = resp.get("result", {})
            dur = (datetime.now() - start).total_seconds() * 1000
            self._log_activity(server_id, f"mcp:{method}", None, 200, dur)
            return {"status": "success", "result": result, "duration": dur}
        except Exception as e:
            dur = (datetime.now() - start).total_seconds() * 1000
            self._log_activity(server_id, f"mcp:{method}", None, 500, dur, str(e))
            return {"status": "error", "error": str(e), "duration": dur}

    def get_server_capabilities(self, server_id: str) -> Dict[str, Any]:
        caps = self._server_capabilities.get(server_id, {})
        return {
            "server_id": server_id,
            "capabilities": {"tools": "tools" in caps, "resources": "resources" in caps,
                             "prompts": "prompts" in caps},
            "raw": caps,
        }

    # ------------------------------------------------------------------ #
    #  LLM                                                                #
    # ------------------------------------------------------------------ #

    def _ollama_base_url(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    def _openai_base_url(self) -> str:
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def _anthropic_base_url(self) -> str:
        return os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")

    def list_ollama_models(self) -> Dict[str, Any]:
        base = self._ollama_base_url()
        try:
            r = httpx.get(f"{base}/api/tags", timeout=5)
            r.raise_for_status()
            models = r.json().get("models", [])
            names = list(dict.fromkeys(
                str(m.get("name", "")).strip() for m in models
                if isinstance(m, dict) and str(m.get("name", "")).strip()
            ))
            return {"status": "success", "provider": "ollama", "base_url": base, "models": names}
        except Exception as e:
            return {"status": "error", "provider": "ollama", "base_url": base, "error": str(e), "models": []}

    def list_openai_models(self, api_key_override: Optional[str] = None) -> Dict[str, Any]:
        key = (api_key_override or os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            return {"status": "error", "provider": "openai", "error": "Missing OPENAI_API_KEY", "models": []}
        try:
            r = httpx.get(f"{self._openai_base_url()}/models", timeout=10,
                          headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            data = r.json().get("data", [])
            return {"status": "success", "provider": "openai",
                    "models": sorted(m["id"] for m in data if isinstance(m, dict) and m.get("id"))}
        except Exception as e:
            return {"status": "error", "provider": "openai", "error": str(e), "models": []}

    def list_anthropic_models(self, api_key_override: Optional[str] = None) -> Dict[str, Any]:
        key = (api_key_override or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        if not key:
            return {"status": "error", "provider": "anthropic", "error": "Missing key", "models": []}
        return {"status": "success", "provider": "anthropic",
                "models": ["claude-3-5-sonnet-latest", "claude-3-7-sonnet-latest", "claude-3-opus-latest"]}

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        raw = text.strip()
        if "```" in raw:
            for chunk in [c.strip() for c in raw.replace("```json", "```").split("```") if c.strip()]:
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        for i, ch in enumerate(raw):
            if ch == '{':
                for j in range(len(raw), i, -1):
                    try:
                        obj = json.loads(raw[i:j])
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
        return None

    def _call_ollama_chat(self, model: str, messages: List[Dict[str, str]], timeout: float = 120.0) -> str:
        r = httpx.post(f"{self._ollama_base_url()}/api/chat",
                       json={"model": model, "messages": messages, "stream": False,
                             "options": {"temperature": 0.1}},
                       timeout=timeout)
        r.raise_for_status()
        return str(r.json().get("message", {}).get("content", "") or "")

    def _call_openai_chat(self, model: str, messages: List[Dict[str, str]],
                          timeout: float = 120.0, api_key_override: Optional[str] = None) -> str:
        key = (api_key_override or os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            raise RuntimeError("Missing OPENAI_API_KEY")
        r = httpx.post(f"{self._openai_base_url()}/chat/completions",
                       json={"model": model, "messages": messages, "temperature": 0.1},
                       timeout=timeout, headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        choices = r.json().get("choices", [])
        return str(choices[0].get("message", {}).get("content", "")) if choices else ""

    def _call_anthropic_chat(self, model: str, messages: List[Dict[str, str]],
                             timeout: float = 120.0, api_key_override: Optional[str] = None) -> str:
        key = (api_key_override or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        if not key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY")
        sys_parts = [m["content"] for m in messages if m.get("role") == "system"]
        non_sys = [m for m in messages if m.get("role") != "system"]
        r = httpx.post(f"{self._anthropic_base_url()}/messages",
                       json={"model": model, "max_tokens": 1000, "temperature": 0.1,
                             "system": "\n\n".join(sys_parts), "messages": non_sys},
                       timeout=timeout,
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
        r.raise_for_status()
        return "".join(
            str(p.get("text", "")) for p in r.json().get("content", [])
            if isinstance(p, dict) and p.get("type") == "text"
        ).strip()

    def _call_llm_chat(self, provider: str, model: str, messages: List[Dict[str, str]],
                       timeout: float = 120.0, api_key_override: Optional[str] = None) -> str:
        p = provider.lower().strip()
        if p == "ollama":
            return self._call_ollama_chat(model, messages, timeout)
        if p == "openai":
            return self._call_openai_chat(model, messages, timeout, api_key_override)
        if p == "anthropic":
            return self._call_anthropic_chat(model, messages, timeout, api_key_override)
        raise RuntimeError(f"Unsupported: {provider}")

    def _should_use_tools(self, provider: str, model: str, prompt: str,
                          catalog: str, api_key_override: Optional[str] = None) -> bool:
        raw = self._call_llm_chat(provider, model,
                                   [{"role": "system", "content": "Reply ONLY YES or NO."},
                                    {"role": "user", "content": f"Request:\n{prompt}\n\nTools:\n{catalog}\n\nNeed tools?"}],
                                   60.0, api_key_override)
        return str(raw or "").strip().lower().startswith("y")

    async def llm_chat_with_tools(
        self, provider: str, server_id: str, model: str, user_prompt: str,
        max_steps: int = 6, auto_tools: bool = True, api_key_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        provider = provider.lower().strip()
        if not model:
            raise ValueError("model required")
        if not user_prompt or not user_prompt.strip():
            raise ValueError("prompt required")

        # Activate keepalive for the duration of the LLM loop
        self._keepalive.mark_active(server_id)

        try:
            tools = await self.get_tools(server_id)
        except Exception as e:
            self._keepalive.mark_idle(server_id)
            return {"status": "error", "provider": provider, "model": model,
                    "error": f"Failed to get tools: {e}", "steps": [], "used_tools": False}

        compact = [{"name": t.get("name"), "description": t.get("description", ""),
                     "input_schema": t.get("input_schema") or t.get("inputSchema") or {}}
                    for t in tools if t.get("name")]
        names_set = {t["name"] for t in compact}
        catalog = json.dumps(compact, ensure_ascii=False, indent=2)

        system_prompt = (
            "You are a tool-using assistant. Reply ONLY with a JSON object.\n"
            "Shapes:\n"
            '1) {"type":"tool_call","tool":"<name>","arguments":{...},"reasoning":"..."}\n'
            '2) {"type":"final","answer":"..."}\n\n'
            "RULES:\n"
            "- One tool_call per response\n"
            "- For multi-step tasks (e.g. 'open X and search Y'), chain multiple tool_calls\n"
            "- browser_navigate opens a page — you MUST follow up with additional tools\n"
            "  (like browser_type, browser_click) to complete the full request\n"
            "- ONLY use type 'final' when the ENTIRE user request is fully completed\n"
            "- If a tool returns a page snapshot, analyze it and decide the next action"
        )

        if auto_tools:
            try:
                use = await asyncio.to_thread(
                    self._should_use_tools, provider, model, user_prompt, catalog, api_key_override)
            except Exception:
                use = True
            if not use:
                try:
                    ans = await asyncio.to_thread(
                        self._call_llm_chat, provider, model,
                        [{"role": "system", "content": "You are a helpful assistant."},
                         {"role": "user", "content": user_prompt}], 90.0, api_key_override)
                except Exception as e:
                    self._keepalive.mark_idle(server_id)
                    return {"status": "error", "provider": provider, "model": model,
                            "error": str(e), "steps": [], "used_tools": False}
                self._keepalive.mark_idle(server_id)
                return {"status": "success", "provider": provider, "model": model,
                        "final_answer": str(ans).strip(), "steps": [], "used_tools": False}

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Request:\n{user_prompt}\n\nTools:\n{catalog}\n\nChoose action:"},
        ]
        steps: List[Dict[str, Any]] = []

        try:
            for step_idx in range(1, max(1, int(max_steps)) + 1):
                # Refresh keepalive timestamp before each LLM call
                self._keepalive.mark_active(server_id)

                started = datetime.now()
                try:
                    raw = await asyncio.to_thread(
                        self._call_llm_chat, provider, model, messages, 120.0, api_key_override)
                except Exception as e:
                    return {"status": "error", "provider": provider, "model": model,
                            "error": f"LLM failed: {e}", "steps": steps}

                decision = self._extract_json_object(raw)
                if not decision:
                    return {"status": "error", "provider": provider, "model": model,
                            "error": "No valid JSON from model", "raw": raw, "steps": steps}

                dtype = str(decision.get("type", "")).strip().lower()

                if dtype == "final":
                    return {"status": "success", "provider": provider, "model": model,
                            "final_answer": str(decision.get("answer", "Done.")).strip(),
                            "steps": steps, "used_tools": True}

                if dtype != "tool_call":
                    return {"status": "error", "provider": provider, "model": model,
                            "error": f"Bad action type: {dtype}", "steps": steps}

                tool_name = str(decision.get("tool", "")).strip()
                args = decision.get("arguments", {})
                if not isinstance(args, dict):
                    args = {}
                if tool_name not in names_set:
                    return {"status": "error", "provider": provider, "model": model,
                            "error": f"Unknown tool: {tool_name}", "steps": steps}

                # Refresh keepalive before tool execution
                self._keepalive.mark_active(server_id)

                tool_result = await self.execute_tool(server_id, tool_name, args)
                dur = (datetime.now() - started).total_seconds() * 1000

                steps.append({"step": step_idx, "type": "tool_call", "tool": tool_name,
                              "arguments": args, "result": tool_result, "duration": dur})

                messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
                messages.append({"role": "user", "content": (
                    f"Tool `{tool_name}` result:\n{json.dumps(tool_result, ensure_ascii=False)}\n\n"
                    f"Original request: {user_prompt}\n\n"
                    "Is the FULL request completed? If not, make the next tool_call. "
                    "Only respond with type 'final' when everything is done."
                )})

            return {"status": "success", "provider": provider, "model": model,
                    "final_answer": "Max steps reached.", "steps": steps, "used_tools": True}

        finally:
            # Stop keepalive when LLM loop ends
            self._keepalive.mark_idle(server_id)

    # ------------------------------------------------------------------ #
    #  Test Suites                                                        #
    # ------------------------------------------------------------------ #

    def create_test_suite(self, name: str, description: str,
                          test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            import uuid
            sid = str(uuid.uuid4())[:8]
            cases = [TestCase(
                id=tc.get('id', str(uuid.uuid4())[:8]),
                name=tc.get('name', 'Test'), server_id=tc['server_id'],
                tool_name=tc['tool_name'], parameters=tc['parameters'],
                expected_status=tc.get('expected_status'),
                created_at=datetime.now().isoformat()
            ) for tc in test_cases]
            suite = TestSuite(id=sid, name=name, description=description,
                              test_cases=cases, created_at=datetime.now().isoformat())
            self.test_suites[sid] = suite
            self._save_test_suite(suite)
            return {'status': 'success', 'suite': asdict(suite)}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    async def run_test_suite(self, suite_id: str) -> Dict[str, Any]:
        if suite_id not in self.test_suites:
            raise ValueError(f"Suite {suite_id} not found")
        suite = self.test_suites[suite_id]
        results = []
        for tc in suite.test_cases:
            try:
                r = await self.execute_tool(tc.server_id, tc.tool_name, tc.parameters)
                passed = r.get('status') == tc.expected_status if tc.expected_status else True
                results.append({'test_id': tc.id, 'test_name': tc.name, 'passed': passed, 'result': r})
            except Exception as e:
                results.append({'test_id': tc.id, 'test_name': tc.name, 'passed': False, 'error': str(e)})
        suite.last_run = datetime.now().isoformat()
        self._save_test_suite(suite)
        total = len(results)
        ok = sum(1 for r in results if r.get('passed'))
        return {'status': 'success', 'suite_id': suite_id, 'suite_name': suite.name,
                'total': total, 'passed': ok, 'failed': total - ok,
                'results': results, 'run_at': suite.last_run}

    def delete_test_suite(self, suite_id: str) -> Dict[str, Any]:
        if suite_id not in self.test_suites:
            raise ValueError(f"Suite {suite_id} not found")
        f = self.test_suites_dir / f"{suite_id}.json"
        if f.exists():
            f.unlink()
        del self.test_suites[suite_id]
        return {'status': 'success'}

    # ------------------------------------------------------------------ #
    #  Export                                                              #
    # ------------------------------------------------------------------ #

    def export_metrics(self, format: str = 'json') -> str:
        m = self.get_metrics_summary()
        logs = list(self.activity_logs)[-100:]
        svrs = [asdict(s) for s in self.servers.values()]
        if format == 'json':
            return json.dumps({'metrics': m, 'servers': svrs,
                               'logs': [asdict(l) for l in logs],
                               'exported_at': datetime.now().isoformat()}, indent=2)
        elif format == 'markdown':
            return (f"# Report\n\nTotal: {m['total_calls']}, "
                    f"Avg: {m['avg_time']:.1f}ms, Success: {m['success_rate']:.1f}%\n")
        elif format == 'html':
            return f"<html><body><h1>Report</h1><pre>{json.dumps(m, indent=2)}</pre></body></html>"
        raise ValueError(f"Bad format: {format}")

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _update_metrics(self, server_id: str, tool_name: str, duration: float, success: bool):
        if tool_name not in self.tool_metrics[server_id]:
            self.tool_metrics[server_id][tool_name] = ToolMetrics(
                name=tool_name, calls=0, total_time=0.0, avg_time=0.0,
                success_count=0, error_count=0)
        m = self.tool_metrics[server_id][tool_name]
        m.calls += 1
        m.total_time += duration
        m.avg_time = m.total_time / m.calls
        m.last_called = datetime.now().isoformat()
        if success:
            m.success_count += 1
        else:
            m.error_count += 1

    def _log_activity(self, server_id: str, method: str, tool_name: Optional[str],
                      status: int, duration: float, error: Optional[str] = None):
        self.activity_logs.append(ActivityLog(
            timestamp=datetime.now().isoformat(), server_id=server_id,
            method=method, tool_name=tool_name, status=status,
            duration=duration, error=error))

    async def _broadcast_update(self, event_type: str, data: Any):
        if not self.active_connections:
            return
        msg = json.dumps({'type': event_type, 'data': data, 'timestamp': datetime.now().isoformat()})

        async def _send(ws):
            try:
                await asyncio.wait_for(ws.send_text(msg), timeout=5.0)
            except Exception:
                return ws
            return None

        results = await asyncio.gather(*[_send(ws) for ws in self.active_connections])
        self.active_connections -= {ws for ws in results if ws is not None}

    async def register_websocket(self, ws: WebSocket):
        self.active_connections.add(ws)

    async def unregister_websocket(self, ws: WebSocket):
        self.active_connections.discard(ws)

    def get_metrics_summary(self) -> Dict[str, Any]:
        tc = tt = sc = ec = 0
        for sm in self.tool_metrics.values():
            for m in sm.values():
                tc += m.calls
                tt += m.total_time
                sc += m.success_count
                ec += m.error_count
        return {
            'total_calls': tc,
            'avg_time': (tt / tc) if tc else 0.0,
            'success_rate': (sc / tc * 100) if tc else 0.0,
            'active_servers': len([s for s in self.servers.values() if s.status == 'connected']),
            'total_servers': len(self.servers),
            'total_tools': sum(s.tools_count for s in self.servers.values())
        }

    async def cleanup(self):
        self._keepalive.stop()
        for c in self.stdio_clients.values():
            try:
                await c.stop()
            except Exception:
                pass
        self.stdio_clients.clear()
        self.stdio_adapters.clear()
        self.active_connections.clear()
        self._http_session_ids.clear()
        self._server_capabilities.clear()
        for sid in list(self._http_clients):
            self._close_http_client(sid)


# ===================================================================== #
#  Inspector Server (FastAPI)                                            #
# ===================================================================== #

class InspectorServer:

    def __init__(
        self, host: str = "127.0.0.1", port: int = 6274, verbose: bool = False,
        secure_mode: bool = False, api_key: Optional[str] = None,
        allowed_origins: Optional[List[str]] = None,
        rate_limit_per_minute: int = 120, rate_limit_window_seconds: int = 60,
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

        origins = allowed_origins or [
            f"http://{host}:{port}", f"https://{host}:{port}",
            f"http://localhost:{port}", f"http://127.0.0.1:{port}",
        ]
        self.app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Inspector-API-Key"],
        )

        @self.app.middleware("http")
        async def security_middleware(request: Request, call_next):
            if request.url.path.startswith("/api/"):
                now = datetime.now().timestamp()
                ip = request.client.host if request.client else "unknown"
                bucket = self._rate_limit_buckets[ip]
                cutoff = now - self.rate_limit_window_seconds
                bucket[:] = [t for t in bucket if t >= cutoff]
                if len(bucket) >= self.rate_limit_per_minute:
                    return PlainTextResponse("Rate limit", status_code=429)
                bucket.append(now)
                if len(self._rate_limit_buckets) > 10_000:
                    for k in [k for k, v in self._rate_limit_buckets.items() if not v or v[-1] < cutoff]:
                        del self._rate_limit_buckets[k]
                if self.secure_mode and not self._is_authorized(request):
                    return PlainTextResponse("Unauthorized", status_code=401)
            resp = await call_next(request)
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["Referrer-Policy"] = "no-referrer"
            o = (request.headers.get("origin") or "").lower()
            r = (request.headers.get("referer") or "").lower()
            if not any(x in o or x in r for x in ["tauri://", "tauri.localhost"]):
                resp.headers["X-Frame-Options"] = "SAMEORIGIN"
            if self.secure_mode:
                resp.headers["Cache-Control"] = "no-store"
            return resp

        self._setup_routes()

    def _is_authorized(self, request: Request) -> bool:
        if not self.secure_mode or not self.api_key:
            return not self.secure_mode
        hk = request.headers.get("x-inspector-api-key", "").strip()
        auth = request.headers.get("authorization", "").strip()
        bk = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return secrets.compare_digest(hk or "", self.api_key) or secrets.compare_digest(bk or "", self.api_key)

    def _is_ws_authorized(self, ws: WebSocket) -> bool:
        if not self.secure_mode or not self.api_key:
            return not self.secure_mode
        for k in [ws.query_params.get("api_key", "").strip(),
                   ws.headers.get("x-inspector-api-key", "").strip(),
                   (ws.headers.get("authorization", "")[7:].strip()
                    if ws.headers.get("authorization", "").lower().startswith("bearer ") else "")]:
            if k and secrets.compare_digest(k, self.api_key):
                return True
        return False

    def _setup_routes(self):

        @self.app.get("/", response_class=HTMLResponse)
        async def serve_ui():
            p = Path(__file__).parent / "static" / "index.html"
            return FileResponse(p) if p.exists() else HTMLResponse("<h1>PolyMCP Inspector</h1>")

        @self.app.get("/icon.png")
        async def serve_icon():
            p = Path(__file__).parent / "static" / "icon.png"
            if p.exists():
                return FileResponse(p)
            raise HTTPException(404)

        @self.app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            if not self._is_ws_authorized(ws):
                await ws.close(code=1008)
                return
            await ws.accept()
            await self.manager.register_websocket(ws)
            try:
                await ws.send_json({
                    'type': 'initial_state',
                    'data': {'servers': [asdict(s) for s in self.manager.servers.values()],
                             'metrics': self.manager.get_metrics_summary()}})
                while True:
                    data = await ws.receive_json()
                    if data.get('type') == 'ping':
                        await ws.send_json({'type': 'pong'})
                    elif data.get('type') == 'get_state':
                        await ws.send_json({
                            'type': 'state_update',
                            'data': {'servers': [asdict(s) for s in self.manager.servers.values()],
                                     'metrics': self.manager.get_metrics_summary()}})
            except WebSocketDisconnect:
                await self.manager.unregister_websocket(ws)

        @self.app.post("/api/servers/add")
        async def add_server(cfg: Dict[str, Any]):
            t = cfg.get('type', 'http')
            sid = cfg.get('id', f"server_{len(self.manager.servers)}")
            name = cfg.get('name', 'Unnamed')
            if t == 'http':
                if not cfg.get('url'):
                    raise HTTPException(400, "URL required")
                return await self.manager.add_http_server(sid, name, cfg['url'])
            if not cfg.get('command'):
                raise HTTPException(400, "Command required")
            return await self.manager.add_stdio_server(sid, name, cfg['command'], cfg.get('args', []), cfg.get('env'))

        @self.app.delete("/api/servers/{server_id}")
        async def remove_server(server_id: str):
            return await self.manager.remove_server(server_id)

        @self.app.get("/api/servers")
        async def list_servers():
            return {'servers': [asdict(s) for s in self.manager.servers.values()]}

        @self.app.get("/api/servers/{server_id}/capabilities")
        async def get_caps(server_id: str):
            if server_id not in self.manager.servers:
                raise HTTPException(404)
            return self.manager.get_server_capabilities(server_id)

        @self.app.get("/api/servers/{server_id}/tools")
        async def get_tools(server_id: str):
            try:
                tools = await self.manager.get_tools(server_id)
            except Exception as e:
                return {'tools': [], 'error': str(e)}
            metrics = self.manager.tool_metrics.get(server_id, {})
            return {'tools': [{**t, **({"metrics": asdict(metrics[t["name"]])} if t.get("name") in metrics else {})} for t in tools]}

        @self.app.post("/api/servers/{server_id}/tools/{tool_name}/execute")
        async def exec_tool(server_id: str, tool_name: str, parameters: Dict[str, Any]):
            return await self.manager.execute_tool(server_id, tool_name, parameters)

        @self.app.get("/api/servers/{server_id}/resources")
        async def list_res(server_id: str):
            return {'resources': await self.manager.list_resources(server_id)}

        @self.app.post("/api/servers/{server_id}/resources/read")
        async def read_res(server_id: str, uri: str = Body(..., embed=True)):
            return await self.manager.read_resource(server_id, uri)

        @self.app.get("/api/servers/{server_id}/prompts")
        async def list_prompts(server_id: str):
            return {'prompts': await self.manager.list_prompts(server_id)}

        @self.app.post("/api/servers/{server_id}/prompts/get")
        async def get_prompt(server_id: str, prompt_name: str = Body(...),
                             arguments: Dict[str, Any] = Body(...)):
            return await self.manager.get_prompt(server_id, prompt_name, arguments)

        @self.app.post("/api/servers/{server_id}/mcp/request")
        async def mcp_req(server_id: str, method: str = Body(...),
                          params: Dict[str, Any] = Body(default_factory=dict)):
            return await self.manager.proxy_mcp_request(server_id, method, params)

        @self.app.get("/api/llm/providers")
        async def llm_providers(request: Request):
            ol = self.manager.list_ollama_models()
            oa = self.manager.list_openai_models(request.headers.get("X-OpenAI-API-Key", "").strip() or None)
            an = self.manager.list_anthropic_models(request.headers.get("X-Anthropic-API-Key", "").strip() or None)
            return {"providers": [
                {"id": "ollama", "name": "Ollama", "status": ol.get("status"),
                 "models_count": len(ol.get("models", [])), "error": ol.get("error")},
                {"id": "openai", "name": "OpenAI", "status": oa.get("status"),
                 "models_count": len(oa.get("models", [])), "error": oa.get("error")},
                {"id": "anthropic", "name": "Anthropic", "status": an.get("status"),
                 "models_count": len(an.get("models", [])), "error": an.get("error")},
            ]}

        @self.app.get("/api/llm/ollama/models")
        async def ol_models():
            return self.manager.list_ollama_models()

        @self.app.get("/api/llm/openai/models")
        async def oa_models(request: Request):
            return self.manager.list_openai_models(request.headers.get("X-OpenAI-API-Key", "").strip() or None)

        @self.app.get("/api/llm/anthropic/models")
        async def an_models(request: Request):
            return self.manager.list_anthropic_models(request.headers.get("X-Anthropic-API-Key", "").strip() or None)

        @self.app.post("/api/servers/{server_id}/llm/chat")
        async def llm_chat(
            request: Request, server_id: str,
            provider: str = Body("ollama"), model: str = Body(...),
            prompt: str = Body(...), max_steps: int = Body(6),
            auto_tools: bool = Body(True), api_key: Optional[str] = Body(None),
        ):
            pid = provider.lower().strip()
            rk = (api_key or "").strip() or None
            if pid == "openai":
                hk = request.headers.get("X-OpenAI-API-Key", "").strip()
                if hk:
                    rk = hk
            elif pid == "anthropic":
                hk = request.headers.get("X-Anthropic-API-Key", "").strip()
                if hk:
                    rk = hk
            return await self.manager.llm_chat_with_tools(
                provider, server_id, model, prompt, max_steps, auto_tools, rk)

        @self.app.get("/api/test-suites")
        async def list_suites():
            return {'suites': [asdict(s) for s in self.manager.test_suites.values()]}

        @self.app.post("/api/test-suites")
        async def create_suite(name: str = Body(...), description: str = Body(...),
                               test_cases: List[Dict[str, Any]] = Body(...)):
            return self.manager.create_test_suite(name, description, test_cases)

        @self.app.post("/api/test-suites/{suite_id}/run")
        async def run_suite(suite_id: str):
            return await self.manager.run_test_suite(suite_id)

        @self.app.delete("/api/test-suites/{suite_id}")
        async def del_suite(suite_id: str):
            return self.manager.delete_test_suite(suite_id)

        @self.app.get("/api/export/metrics")
        async def export(format: str = 'json'):
            c = self.manager.export_metrics(format)
            if format == 'json':
                return PlainTextResponse(c, media_type='application/json')
            if format == 'markdown':
                return PlainTextResponse(c, media_type='text/markdown')
            if format == 'html':
                return HTMLResponse(c)
            raise HTTPException(400, f"Bad format: {format}")

        @self.app.get("/api/metrics")
        async def metrics():
            return self.manager.get_metrics_summary()

        @self.app.get("/api/metrics/{server_id}")
        async def server_metrics(server_id: str):
            if server_id not in self.manager.tool_metrics:
                raise HTTPException(404)
            return {'metrics': {n: asdict(m) for n, m in self.manager.tool_metrics[server_id].items()}}

        @self.app.get("/api/logs")
        async def logs(limit: int = 100):
            return {'logs': [asdict(l) for l in list(self.manager.activity_logs)[-limit:]]}

        @self.app.get("/api/health")
        async def health():
            return {'status': 'healthy', 'servers': len(self.manager.servers)}


async def run_inspector(
    host: str = "127.0.0.1", port: int = 6274, verbose: bool = False,
    open_browser: bool = True, servers: Optional[List[Dict[str, Any]]] = None,
    secure_mode: bool = False, api_key: Optional[str] = None,
    allowed_origins: Optional[List[str]] = None,
    rate_limit_per_minute: int = 120, rate_limit_window_seconds: int = 60,
):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    if secure_mode and not api_key:
        api_key = secrets.token_urlsafe(24)
        logger.warning("Auto-generated API key: %s", api_key)

    inspector = InspectorServer(
        host, port, verbose, secure_mode, api_key, allowed_origins,
        rate_limit_per_minute, rate_limit_window_seconds)

    if servers:
        for sc in servers:
            try:
                t = sc.get('type', 'http')
                sid = sc.get('id', f"server_{len(inspector.manager.servers)}")
                name = sc.get('name', 'Unnamed')
                if t == 'http':
                    await inspector.manager.add_http_server(sid, name, sc.get('url'))
                else:
                    await inspector.manager.add_stdio_server(
                        sid, name, sc.get('command'), sc.get('args', []), sc.get('env'))
            except Exception as e:
                logger.error(f"Failed to add server: {e}")

    if open_browser:
        await asyncio.sleep(1)
        url = f"http://{host}:{port}"
        if secure_mode and api_key:
            url += f"/?api_key={api_key}"
        webbrowser.open(url)

    logger.warning("Inspector on http://%s:%s", host, port)
    config = uvicorn.Config(inspector.app, host=host, port=port,
                            log_level="info" if verbose else "warning",
                            log_config=None, access_log=False)
    srv = uvicorn.Server(config)
    try:
        await srv.serve()
    finally:
        await inspector.manager.cleanup()