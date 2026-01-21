from __future__ import annotations

import asyncio
import codecs
import ipaddress
import json
import os
import random
import re
import shlex
import shutil
import socket
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import ParseResult, urlparse, urlunparse

import httpx

Json = Dict[str, Any]


# -----------------------------
# Policies / Limits
# -----------------------------

@dataclass(frozen=True)
class NetworkPolicy:
    """
    Production network safety controls.

    - allow_hosts: if set, only these hosts (exact or suffix match) are allowed
    - block_private_networks: blocks localhost/private/link-local/reserved/multicast
      for BOTH IP literals AND DNS-resolved A/AAAA (anti DNS-rebinding best-effort)
    - allow_ports: optional allowlist of ports; if None, any port is allowed
    - max_response_bytes: hard cap for any response stream read
    """
    block_private_networks: bool = True
    allow_hosts: Optional[Tuple[str, ...]] = None
    allow_ports: Optional[Tuple[int, ...]] = None
    max_response_bytes: int = 1_500_000


@dataclass(frozen=True)
class StdioPolicy:
    """
    Production stdio safety controls.

    - enable_stdio_fallback: allow URL-based detection mapping -> stdio execution
    - enable_stdio_commands: allow passing non-http strings as commands (disabled by default)
    - allowed_commands: REQUIRED if enabling stdio.
      You can allow by executable name (e.g. "npx") and/or by canonical absolute path.
      Resolution is always performed and compared too.
    """
    enable_stdio_fallback: bool = False
    enable_stdio_commands: bool = False
    allowed_commands: Optional[Set[str]] = None


@dataclass(frozen=True)
class ResourceLimits:
    """Production resource limits to prevent DoS and memory exhaustion."""
    max_servers: int = 50
    max_concurrency: int = 8
    max_tools_per_server: int = 500
    max_tools_total: int = 5000

    max_url_length: int = 500
    max_description_length: int = 5000
    max_json_depth: int = 20
    max_category_name_length: int = 100

    total_timeout_s: float = 300.0
    per_server_timeout_s: float = 25.0
    per_message_timeout_s: float = 7.0


@dataclass
class ToolInfo:
    name: str
    description: str
    input_schema: dict
    server_url: str


@dataclass
class SkillMetadata:
    category: str
    tool_count: int
    token_estimate: int
    generated_at: str


# -----------------------------
# Generator
# -----------------------------

class MCPSkillGenerator:
    """
    Production-grade MCP skill generator:
    - REST endpoints
    - JSON-RPC over HTTP (Streamable HTTP transport)
    - JSON-RPC over SSE (/sse)
    - Protocol detection
    - Optional stdio support (gated by policy)
    - Safe file generation (atomic writes, markdown sanitization)
    """

    CATEGORIES = {
        "filesystem": {"keywords": ["file", "read", "write", "directory", "path", "folder", "save", "load", "delete"],
                       "weight": 1.0},
        "api": {"keywords": ["http", "request", "api", "fetch", "post", "get", "rest", "endpoint", "call"],
                "weight": 1.0},
        "data": {"keywords": ["json", "csv", "parse", "transform", "format", "convert", "serialize", "deserialize"],
                 "weight": 1.0},
        "database": {"keywords": ["sql", "query", "database", "table", "insert", "select", "update", "db"],
                     "weight": 1.0},
        "communication": {"keywords": ["email", "message", "send", "notify", "notification", "mail", "sms"],
                          "weight": 1.0},
        "automation": {"keywords": ["script", "execute", "run", "automate", "schedule", "task", "workflow"],
                       "weight": 1.0},
        "security": {"keywords": ["auth", "token", "password", "encrypt", "decrypt", "hash", "credential", "key"],
                     "weight": 1.0},
        "monitoring": {"keywords": ["log", "monitor", "alert", "metric", "status", "health", "check"], "weight": 1.0},
        "text": {"keywords": ["text", "string", "analyze", "summarize", "translate", "sentiment", "nlp"],
                 "weight": 1.0},
        "math": {"keywords": ["calculate", "compute", "math", "number", "statistic", "formula"], "weight": 1.0},
        "web": {"keywords": ["browser", "navigate", "click", "screenshot", "page", "web", "html", "playwright"],
                "weight": 1.0},
    }

    _HOST_RE = re.compile(r"^(?=.{1,253}\Z)(?!-)(?:[a-z0-9-]{1,63}(?<!-)\.)*[a-z0-9-]{1,63}(?<!-)\Z", re.IGNORECASE)

    def __init__(
            self,
            output_dir: str = "./mcp_skills",
            verbose: bool = False,
            include_examples: bool = True,
            network_policy: Optional[NetworkPolicy] = None,
            stdio_policy: Optional[StdioPolicy] = None,
            resource_limits: Optional[ResourceLimits] = None,
            max_retries: int = 2,
            retry_backoff_base_s: float = 0.35,
    ):
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self.include_examples = include_examples

        self.net = network_policy or NetworkPolicy()
        self.stdio = stdio_policy or StdioPolicy()
        self.limits = resource_limits or ResourceLimits()

        self.max_retries = max_retries
        self.retry_backoff_base_s = retry_backoff_base_s

        self.stats: Dict[str, Any] = {
            "total_tools": 0,
            "total_servers": 0,
            "categories": {},
            "generation_time": 0.0,
            "errors": [],
            "warnings": [],
        }
        self._stats_lock = asyncio.Lock()

    # -------------------------
    # Public API
    # -------------------------

    async def generate_from_servers(self, server_urls: List[str], timeout: float = 10.0) -> Dict[str, Any]:
        # Reset stats for each call
        self.stats = {
            "total_tools": 0,
            "total_servers": 0,
            "categories": {},
            "generation_time": 0.0,
            "errors": [],
            "warnings": [],
        }

        start_time = datetime.now()
        self._validate_server_urls(server_urls)

        if self.verbose:
            print(f"\n{'=' * 70}")
            print("🔎 MCP SKILL GENERATION")
            print(f"{'=' * 70}")
            print(f"Servers: {len(server_urls)}")
            print(f"Output: {self.output_dir}")
            print(f"Total timeout: {self.limits.total_timeout_s}s")
            print(f"Max concurrency: {self.limits.max_concurrency}")
            print(f"{'=' * 70}\n")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            return await asyncio.wait_for(
                self._generate_with_timeout(server_urls, timeout),
                timeout=self.limits.total_timeout_s
            )
        except asyncio.TimeoutError:
            self._finalize(start_time)
            raise RuntimeError(f"Generation timeout after {self.limits.total_timeout_s}s")
        except Exception:
            self._finalize(start_time)
            raise

    async def _generate_with_timeout(self, server_urls: List[str], timeout: float) -> Dict[str, Any]:
        start_time = datetime.now()

        all_tools = await self._discover_tools(server_urls, timeout)
        self.stats["total_tools"] = len(all_tools)
        self.stats["total_servers"] = len(server_urls)

        if not all_tools:
            if self.verbose:
                print("⚠️  No tools discovered!")
            self._finalize(start_time)
            return self.stats

        if self.verbose:
            print(f"✅ Discovered {len(all_tools)} tools\n")

        categorized = self._categorize_tools(all_tools)

        if self.verbose:
            print("📊 Categorization:")
            for category, tools in categorized.items():
                print(f"  • {category}: {len(tools)} tools")
            print()

        self._generate_index(categorized)

        for category, tools in categorized.items():
            self._generate_category_file(category, tools)
            self.stats["categories"][category] = len(tools)

        self._save_metadata()
        self._finalize(start_time)

        if self.verbose:
            print(f"\n{'=' * 70}")
            print("✅ GENERATION COMPLETE")
            print(f"{'=' * 70}")
            print(f"Generated: {len(categorized)} skill files")
            print(f"Time: {self.stats['generation_time']:.2f}s")
            print(f"Output: {self.output_dir}")
            if self.stats["warnings"]:
                print(f"Warnings: {len(self.stats['warnings'])}")
            if self.stats["errors"]:
                print(f"Errors: {len(self.stats['errors'])}")
            print(f"{'=' * 70}\n")

        return self.stats

    # -------------------------
    # Validation
    # -------------------------

    def _validate_server_urls(self, server_urls: List[str]) -> None:
        if not isinstance(server_urls, list) or not server_urls:
            raise ValueError("server_urls must be a non-empty list")

        if len(server_urls) > self.limits.max_servers:
            raise ValueError(f"Too many servers ({len(server_urls)}), max {self.limits.max_servers}")

        for url in server_urls:
            if not isinstance(url, str):
                raise ValueError(f"Invalid URL type: {type(url)}")
            if not url.strip():
                raise ValueError("Empty URL")
            if len(url) > self.limits.max_url_length:
                raise ValueError(f"URL too long (max {self.limits.max_url_length}): {url[:100]}...")

    # -------------------------
    # Discovery (concurrency controlled)
    # -------------------------

    async def _discover_tools(self, server_urls: List[str], timeout: float) -> List[Dict[str, Any]]:
        all_tools: List[Dict[str, Any]] = []

        http_timeout = httpx.Timeout(timeout, connect=min(5.0, timeout), read=timeout, write=timeout, pool=timeout)
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)

        sem = asyncio.Semaphore(self.limits.max_concurrency)

        async with httpx.AsyncClient(timeout=http_timeout, limits=limits, follow_redirects=False) as client:
            async def _one(url: str) -> List[Dict[str, Any]]:
                async with sem:
                    return await self._discover_one_server(client, url)

            tasks = [asyncio.create_task(_one(url)) for url in server_urls]

            try:
                for fut in asyncio.as_completed(tasks):
                    tools = await fut
                    if tools:
                        all_tools.extend(tools)

                    if len(all_tools) >= self.limits.max_tools_total:
                        async with self._stats_lock:
                            self.stats["warnings"].append(
                                f"Reached max total tools ({self.limits.max_tools_total}), stopping discovery"
                            )
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        break
            finally:
                # Properly await cancelled tasks
                await asyncio.gather(*tasks, return_exceptions=True)

        # De-dup tools by (server_url, name)
        dedup: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for tool in all_tools:
            server_url = str(tool.get("_server_url", ""))
            name = str(tool.get("name", ""))
            key = (server_url, name)
            if key not in dedup:
                dedup[key] = tool

        return list(dedup.values())[: self.limits.max_tools_total]

    async def _discover_one_server(self, client: httpx.AsyncClient, url: str) -> List[Dict[str, Any]]:
        per_server_budget = self.limits.per_server_timeout_s

        async def _inner() -> List[Dict[str, Any]]:
            if self.verbose:
                print(f"🔗 Connecting to {url}...\n")

            tools: Optional[List[Dict[str, Any]]] = None
            is_http = url.startswith("http://") or url.startswith("https://")

            if is_http:
                checked = await self._validate_http_url(url)

                if self.verbose:
                    print("  📡 STRATEGY 1: REST Endpoints")
                tools = await self._try_rest_endpoint(client, checked)

                if not tools:
                    if self.verbose:
                        print("\n  📡 STRATEGY 2: JSON-RPC over HTTP (Streamable HTTP)")
                    tools = await self._try_jsonrpc_http(client, checked)

                if not tools:
                    if self.verbose:
                        print("\n  📡 STRATEGY 3: JSON-RPC over SSE")
                    tools = await self._try_jsonrpc_sse(client, checked)

                if not tools and self.stdio.enable_stdio_fallback:
                    if self.verbose:
                        print("\n  📡 STRATEGY 4: Stdio Fallback")
                    tools = await self._try_stdio_fallback(url, timeout_s=per_server_budget)

                if not tools and self.verbose:
                    print("\n  🔬 DIAGNOSTIC: Checking server response")
                    await self._diagnostic_request(client, checked)

            else:
                if not self.stdio.enable_stdio_commands:
                    raise RuntimeError("Non-HTTP target rejected: stdio commands disabled by policy")
                if self.verbose:
                    print("  📡 STRATEGY: Stdio Command")
                tools = await self._try_stdio_command(url, timeout_s=per_server_budget)

            if not tools:
                async with self._stats_lock:
                    self.stats["errors"].append(f"No compatible protocol found for {url}")
                if self.verbose:
                    print(f"  ❌ No compatible protocol found for {url}\n")
                return []

            if len(tools) > self.limits.max_tools_per_server:
                async with self._stats_lock:
                    self.stats["warnings"].append(
                        f"Server {url} returned {len(tools)} tools, truncating to {self.limits.max_tools_per_server}"
                    )
                tools = tools[: self.limits.max_tools_per_server]

            server_name = self._extract_server_name(url)
            for tool in tools:
                tool["_server_url"] = url
                tool["_server_name"] = server_name

            if self.verbose:
                print(f"\n  ✅ SUCCESS: Found {len(tools)} tools\n")

            return tools

        try:
            return await asyncio.wait_for(_inner(), timeout=per_server_budget)
        except asyncio.TimeoutError:
            async with self._stats_lock:
                self.stats["errors"].append(f"Server timeout after {per_server_budget}s: {url}")
            if self.verbose:
                print(f"  ❌ Server timeout after {per_server_budget}s: {url}\n")
            return []
        except Exception as e:
            async with self._stats_lock:
                self.stats["errors"].append(f"Error with {url}: {str(e)}")
            if self.verbose:
                print(f"  ❌ Error with {url}: {str(e)}\n")
            return []

    # -------------------------
    # REST
    # -------------------------

    async def _try_rest_endpoint(self, client: httpx.AsyncClient, base_url: str) -> Optional[List[Dict[str, Any]]]:
        endpoints = [
            "/list_tools",
            "/tools",
            "/tools/list",
            "/mcp/tools",
            "/mcp",
            "/.well-known/mcp",
            "",
        ]
        for endpoint in endpoints:
            list_url = f"{base_url.rstrip('/')}{endpoint}"
            if self.verbose:
                print(f"  🔍 Trying REST: {list_url}")

            resp = await self._request_with_retries(client, "GET", list_url, headers={"Accept": "application/json"})
            if resp is None:
                continue

            try:
                if resp.status_code != 200:
                    continue

                data = await self._safe_read_json(resp)
                if data is None:
                    continue

                if isinstance(data, dict):
                    tools = data.get("tools", [])
                    if isinstance(tools, list) and tools:
                        return tools
                if isinstance(data, list) and data:
                    return data
            finally:
                await resp.aclose()

        return None

    # -------------------------
    # JSON-RPC over HTTP (Streamable HTTP - MCP 2024-11-05)
    # -------------------------

    async def _try_jsonrpc_http(self, client: httpx.AsyncClient, url: str) -> Optional[List[Dict[str, Any]]]:
        """
        JSON-RPC over HTTP for MCP Streamable HTTP transport (e.g., Playwright MCP).

        Flow:
        1. POST initialize -> receive sessionId in Mcp-Session-Id header
        2. POST notifications/initialized with Mcp-Session-Id header
        3. POST tools/list with Mcp-Session-Id header

        Responses can be plain JSON or SSE format (data: {...}).
        """
        base_url = url.rstrip("/")

        base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        # 1) INITIALIZE
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "PolyMCP", "version": "1.0.0"},
            },
            "id": 1,
        }

        if self.verbose:
            print(f"  🔧 JSON-RPC HTTP initialize: {base_url}")

        init_resp = await self._request_with_retries(
            client, "POST", base_url, headers=base_headers, json_body=init_payload
        )
        if init_resp is None:
            if self.verbose:
                print(f"     ❌ initialize request failed")
            return None

        try:
            # IMPORTANT: capture headers BEFORE reading body
            resp_headers_raw = dict(init_resp.headers)
            body = await self._safe_read_text(init_resp)
        finally:
            await init_resp.aclose()

        init_msg = self._parse_sse_or_json(body) if body else None

        if not init_msg:
            if self.verbose:
                print(f"     ❌ initialize returned no valid message")
            return None

        if "error" in init_msg:
            if self.verbose:
                print(f"     ❌ initialize error: {init_msg.get('error')}")
            return None

        # 2) EXTRACT SESSION ID FROM HEADER (correct method for MCP Streamable HTTP)
        session_id: Optional[str] = None

        # Normalize header keys to lowercase for comparison
        resp_headers = {k.lower(): v for k, v in resp_headers_raw.items()}

        # Check header first (this is the standard MCP method)
        for header_key in ("mcp-session-id", "x-mcp-session-id"):
            if header_key in resp_headers:
                val = resp_headers[header_key]
                if isinstance(val, str) and val.strip():
                    session_id = val.strip()
                    if self.verbose:
                        print(f"     📋 Found sessionId in header: {session_id}")
                    break

        # Fallback: check response body (some non-standard servers)
        if not session_id:
            result_obj = init_msg.get("result") or {}
            if isinstance(result_obj, dict):
                for key in ("sessionId", "session_id"):
                    sid = result_obj.get(key)
                    if isinstance(sid, str) and sid.strip():
                        session_id = sid.strip()
                        if self.verbose:
                            print(f"     📋 Found sessionId in body: {session_id}")
                        break

        if self.verbose:
            print(f"     ✅ initialize OK (sessionId={session_id!r})")

        if not session_id:
            if self.verbose:
                print(f"     ⚠️ No sessionId received - server may not require sessions")

        # 3) PREPARE HEADERS FOR SUBSEQUENT REQUESTS
        rpc_headers = dict(base_headers)
        if session_id:
            rpc_headers["Mcp-Session-Id"] = session_id

        # 4) NOTIFICATIONS/INITIALIZED (notification, no id)
        notif_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
            # Note: no "id" because it's a notification
        }

        if self.verbose:
            print(f"  🔧 Sending notifications/initialized...")

        notif_resp = await self._request_with_retries(
            client, "POST", base_url, headers=rpc_headers, json_body=notif_payload
        )

        if notif_resp is not None:
            try:
                # Notifications might not have a response, or empty response
                # Some servers respond with 202 Accepted without body
                if notif_resp.status_code in (200, 202, 204):
                    if self.verbose:
                        print(f"     ✅ notifications/initialized accepted (status {notif_resp.status_code})")
                else:
                    notif_body = await self._safe_read_text(notif_resp)
                    notif_msg = self._parse_sse_or_json(notif_body) if notif_body else None
                    if isinstance(notif_msg, dict) and "error" in notif_msg:
                        # Not fatal - some servers don't handle this notification
                        if self.verbose:
                            print(f"     ⚠️ notifications/initialized warning: {notif_msg.get('error')}")
            finally:
                await notif_resp.aclose()
        else:
            if self.verbose:
                print(f"     ⚠️ notifications/initialized request failed (continuing anyway)")

        # 5) TOOLS/LIST
        tools_payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 2,
        }

        if self.verbose:
            print(f"  🔧 Sending tools/list...")

        tools_resp = await self._request_with_retries(
            client, "POST", base_url, headers=rpc_headers, json_body=tools_payload
        )

        if tools_resp is None:
            if self.verbose:
                print(f"     ❌ tools/list request failed")
            return None

        try:
            tools_body = await self._safe_read_text(tools_resp)
        finally:
            await tools_resp.aclose()

        tools_msg = self._parse_sse_or_json(tools_body) if tools_body else None

        if not tools_msg:
            if self.verbose:
                print(f"     ❌ tools/list returned no valid message")
            return None

        if "error" in tools_msg:
            if self.verbose:
                print(f"     ❌ tools/list error: {tools_msg.get('error')}")
            return None

        # 6) EXTRACT TOOLS
        result = tools_msg.get("result", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []

        if isinstance(tools, list) and len(tools) > 0:
            if self.verbose:
                print(f"     ✅ Found {len(tools)} tools!")
            return tools

        if self.verbose:
            print(f"     ⚠️ tools/list returned empty list")
        return None

    def _parse_sse_or_json(self, body: str) -> Optional[Json]:
        """
        Parse a response body that can be either:
        - Plain JSON
        - SSE format (event: xxx\ndata: {...}\n\n)

        Returns the first valid JSON-RPC dict found.
        """
        if not body:
            return None

        body = body.strip()

        # Try plain JSON first
        try:
            obj = json.loads(body)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Try SSE format - look for "data:" lines
        data_parts: List[str] = []
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data_content = line[5:].strip()
                if data_content:
                    data_parts.append(data_content)

        # Try to parse collected data parts
        if data_parts:
            # First try each part individually
            for part in data_parts:
                try:
                    obj = json.loads(part)
                    if isinstance(obj, dict) and ("id" in obj or "result" in obj or "error" in obj or "method" in obj):
                        return obj
                except json.JSONDecodeError:
                    continue

            # Then try joining all parts (for multi-line JSON)
            try:
                combined = "".join(data_parts)
                obj = json.loads(combined)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass

        return None

    # -------------------------
    # JSON-RPC over SSE (/sse)
    # -------------------------

    async def _try_jsonrpc_sse(self, client: httpx.AsyncClient, url: str) -> Optional[List[Dict[str, Any]]]:
        """
        Proper MCP SSE transport:

        1) Open SSE stream via GET on /sse
        2) Parse early SSE events to discover sessionId and message endpoint
        3) POST JSON-RPC messages to message endpoint with sessionId
        4) Read JSON-RPC responses from SSE stream or POST response
        """
        base_url = url.rstrip("/")

        # Candidate SSE endpoints
        sse_candidates: List[str] = []
        if base_url.endswith("/sse"):
            sse_candidates.append(base_url)
        else:
            sse_candidates.append(f"{base_url}/sse")

        if base_url.endswith("/mcp"):
            root = base_url[:-4].rstrip("/")
            if root:
                sse_candidates.append(f"{root}/sse")

        for sse_url in sse_candidates:
            if self.verbose:
                print(f"  🔧 JSON-RPC SSE trying: {sse_url}")

            try:
                # Try opening SSE stream
                sse_resp = await client.get(
                    sse_url,
                    headers={"Accept": "text/event-stream"},
                )
            except Exception as e:
                if self.verbose:
                    print(f"     ⚠️ SSE connection failed: {str(e)[:60]}")
                continue

            content_type = sse_resp.headers.get("content-type", "")
            if sse_resp.status_code != 200 or "text/event-stream" not in content_type:
                await sse_resp.aclose()
                if self.verbose:
                    print(f"     ⚠️ Not SSE (status={sse_resp.status_code}, type={content_type[:50]})")
                continue

            session_id: Optional[str] = None
            message_url: Optional[str] = None

            # Read early SSE events to get session info
            try:
                body = await self._safe_read_text(sse_resp)
                if body:
                    for line in body.split("\n"):
                        line = line.strip()
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            try:
                                evt = json.loads(data_str)
                                if isinstance(evt, dict):
                                    # Look for session id
                                    sid = evt.get("sessionId") or evt.get("session_id")
                                    if isinstance(sid, str) and sid.strip():
                                        session_id = sid.strip()

                                    # Look for message endpoint
                                    for k in ("messageEndpoint", "messagesEndpoint", "endpoint", "postUrl", "messages",
                                              "messageUrl"):
                                        v = evt.get(k)
                                        if isinstance(v, str) and v.strip():
                                            message_url = v.strip()
                                            break
                            except json.JSONDecodeError:
                                continue
            except Exception:
                pass
            finally:
                await sse_resp.aclose()

            if self.verbose:
                print(f"     📋 SSE handshake: sessionId={session_id!r}, endpoint={message_url!r}")

            # Normalize message_url
            if message_url and message_url.startswith("/"):
                p = urlparse(sse_url)
                message_url = f"{p.scheme}://{p.netloc}{message_url}"

            # Build list of message endpoints to try
            msg_candidates: List[str] = []
            if message_url:
                msg_candidates.append(message_url)

            p = urlparse(sse_url)
            host_root = f"{p.scheme}://{p.netloc}"
            msg_candidates.extend([
                f"{host_root}/message",
                f"{host_root}/messages",
                f"{host_root}/mcp/message",
                f"{host_root}/mcp/messages",
                f"{host_root}/mcp",
            ])

            # Try MCP handshake over message endpoint
            base_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }

            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "PolyMCP", "version": "1.0.0"},
                },
                "id": 1,
            }
            notif_payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            tools_payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2}

            for msg_url in msg_candidates:
                if self.verbose:
                    print(f"     🔧 SSE message endpoint: {msg_url}")

                rpc_headers = dict(base_headers)
                if session_id:
                    rpc_headers["Mcp-Session-Id"] = session_id

                # Initialize
                init_resp = await self._request_with_retries(
                    client, "POST", msg_url, headers=rpc_headers, json_body=init_payload
                )
                if init_resp is None:
                    continue

                try:
                    init_body = await self._safe_read_text(init_resp)
                    # Try to get session from header
                    if not session_id:
                        hdr_session = init_resp.headers.get("mcp-session-id")
                        if hdr_session:
                            session_id = hdr_session
                            rpc_headers["Mcp-Session-Id"] = session_id
                finally:
                    await init_resp.aclose()

                init_msg = self._parse_sse_or_json(init_body) if init_body else None
                if not init_msg or "error" in init_msg:
                    continue

                # Notifications/initialized
                notif_resp = await self._request_with_retries(
                    client, "POST", msg_url, headers=rpc_headers, json_body=notif_payload
                )
                if notif_resp is not None:
                    await notif_resp.aclose()

                # Tools/list
                tools_resp = await self._request_with_retries(
                    client, "POST", msg_url, headers=rpc_headers, json_body=tools_payload
                )
                if tools_resp is None:
                    continue

                try:
                    tools_body = await self._safe_read_text(tools_resp)
                finally:
                    await tools_resp.aclose()

                tools_msg = self._parse_sse_or_json(tools_body) if tools_body else None
                if not tools_msg or "error" in tools_msg:
                    continue

                tools = tools_msg.get("result", {}).get("tools", [])
                if isinstance(tools, list) and tools:
                    if self.verbose:
                        print(f"     ✅ SSE tools/list OK: {len(tools)} tools")
                    return tools

        return None

    # -------------------------
    # Message readers (bounded)
    # -------------------------

    async def _read_one_sse_or_json_message(self, response: httpx.Response, timeout_s: float) -> Optional[Json]:
        """
        SSE-aware reader:
        - Supports multi-line SSE events
        - Tolerates SSE meta lines: event:, id:, retry:, comments (:)
        - Also supports plain JSON or JSON-lines
        - Also supports plain JSON body without newlines (parsed at EOF)

        Returns first valid JSON-RPC-ish dict found.
        """

        async def _inner() -> Optional[Json]:
            max_bytes = self.net.max_response_bytes
            total = 0
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            buf = ""

            # SSE assembly
            sse_data_lines: List[str] = []

            def try_emit_sse_event() -> Optional[Json]:
                if not sse_data_lines:
                    return None
                payload = "".join(sse_data_lines).strip()
                sse_data_lines.clear()
                if not payload:
                    return None
                return self._try_parse_json(payload)

            async for chunk in response.aiter_bytes():
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    return None

                buf += decoder.decode(chunk)

                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    raw = line.rstrip("\r")

                    # SSE blank line ends an event
                    if raw == "":
                        obj = try_emit_sse_event()
                        if obj is not None:
                            return obj
                        continue

                    # SSE comments
                    if raw.startswith(":"):
                        continue

                    s = raw.strip()
                    if not s:
                        continue

                    if s.startswith("data:"):
                        sse_data_lines.append(s[5:].lstrip())
                        continue

                    # Ignore SSE metadata lines
                    if s.startswith(("event:", "id:", "retry:")):
                        continue

                    # Not SSE data: attempt JSON-lines
                    obj = self._try_parse_json(s)
                    if obj is not None:
                        return obj

            # EOF: flush SSE event
            obj = try_emit_sse_event()
            if obj is not None:
                return obj

            # EOF: try parse remaining buffer as JSON (plain body)
            tail = buf.strip()
            if tail:
                obj = self._try_parse_json(tail)
                if obj is not None:
                    return obj

            return None

        try:
            return await asyncio.wait_for(_inner(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    def _try_parse_json(self, s: str) -> Optional[Json]:
        try:
            obj = self._safe_json_loads(s)
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(obj, dict) and ("id" in obj or "result" in obj or "error" in obj or "method" in obj):
            return obj
        return None

    # -------------------------
    # STDIO (gated)
    # -------------------------

    async def _try_stdio_fallback(self, url: str, timeout_s: float) -> Optional[List[Dict[str, Any]]]:
        server_commands = {
            "playwright": ["npx", "@playwright/mcp@latest"],
            "filesystem": ["npx", "@modelcontextprotocol/server-filesystem@latest"],
            "github": ["npx", "@modelcontextprotocol/server-github@latest"],
        }

        detected: Optional[List[str]] = None
        lower = url.lower()
        for name, cmd in server_commands.items():
            if name in lower:
                detected = cmd
                break

        if not detected:
            return None

        self._assert_stdio_policy()
        return await self._try_stdio_command_list(detected, timeout_s=timeout_s)

    async def _try_stdio_command(self, command_str: str, timeout_s: float) -> Optional[List[Dict[str, Any]]]:
        self._assert_stdio_policy()
        parts = shlex.split(command_str, posix=True)
        if not parts:
            return None
        return await self._try_stdio_command_list(parts, timeout_s=timeout_s)

    async def _try_stdio_command_list(self, command: List[str], timeout_s: float) -> Optional[List[Dict[str, Any]]]:
        self._assert_stdio_policy()
        exe = command[0]
        resolved = self._resolve_executable(exe)
        if not self._command_allowed(exe, resolved):
            raise RuntimeError(f"Stdio command not allowed by policy: {exe} ({resolved})")

        try:
            # 1) Prefer package import (normal in production installs)
            try:
                from polymcp.mcp_stdio_client import MCPStdioClient, MCPServerConfig  # type: ignore
            except ImportError:
                # 2) Fallback for running from repo root / standalone module
                from mcp_stdio_client import MCPStdioClient, MCPServerConfig  # type: ignore

            cfg = MCPServerConfig(command=resolved, args=command[1:], env=None)
            client = MCPStdioClient(cfg)

            try:
                await asyncio.wait_for(client.start(), timeout=timeout_s)
                tools = await asyncio.wait_for(client.list_tools(), timeout=timeout_s)
                return tools if tools else None
            finally:
                try:
                    await client.stop()
                except Exception:
                    pass

        except ImportError:
            return None

    def _assert_stdio_policy(self) -> None:
        if not (self.stdio.allowed_commands and len(self.stdio.allowed_commands) > 0):
            raise RuntimeError("Stdio enabled but allowed_commands is not configured (policy violation)")

    def _resolve_executable(self, exe: str) -> str:
        p = Path(exe)
        if p.is_absolute():
            resolved = p
        else:
            found = shutil.which(exe)
            if not found:
                raise RuntimeError(f"Executable not found: {exe}")
            resolved = Path(found)

        try:
            return str(resolved.resolve(strict=True))
        except Exception:
            return str(resolved.absolute())

    def _command_allowed(self, exe: str, resolved: str) -> bool:
        allow = self.stdio.allowed_commands
        if not allow:
            return False
        return exe in allow or resolved in allow

    # -------------------------
    # Diagnostic (bounded)
    # -------------------------

    async def _diagnostic_request(self, client: httpx.AsyncClient, url: str) -> None:
        base_url = url.rstrip("/")
        for method, target, payload in [
            ("GET", f"{base_url}/", None),
            ("POST", f"{base_url}/", {"test": "ping"}),
        ]:
            try:
                if method == "GET":
                    resp = await client.get(target, headers={"Accept": "*/*"})
                else:
                    resp = await client.post(target, json=payload, headers={"Content-Type": "application/json"})

                try:
                    text = await self._safe_read_text(resp)
                    if self.verbose:
                        print(f"     {method} {target} -> {resp.status_code}")
                        if text:
                            print(f"     Body preview: {text[:500]}")
                finally:
                    await resp.aclose()
            except Exception as e:
                if self.verbose:
                    print(f"     {method} {target} -> error: {str(e)[:120]}")

    # -------------------------
    # HTTP helpers (retry + bounded reads)
    # -------------------------

    async def _request_with_retries(
            self,
            client: httpx.AsyncClient,
            method: str,
            url: str,
            headers: Dict[str, str],
            json_body: Optional[Dict[str, Any]] = None,
    ) -> Optional[httpx.Response]:
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.request(method, url, headers=headers, json=json_body)

                if resp.status_code in (429, 500, 502, 503, 504):
                    retry_after = resp.headers.get("Retry-After")
                    await resp.aclose()

                    if retry_after and attempt < self.max_retries:
                        wait_s = self._parse_retry_after_seconds(retry_after)
                        if wait_s is not None:
                            await asyncio.sleep(min(wait_s, 5.0))

                    raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)

                return resp

            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError,
                    httpx.HTTPStatusError) as e:
                last_err = e
                if attempt >= self.max_retries:
                    break
                base = self.retry_backoff_base_s * (2 ** attempt)
                jitter = random.uniform(0.0, base * 0.25)
                await asyncio.sleep(base + jitter)

            except Exception as e:
                last_err = e
                break

        if self.verbose:
            print(f"  ⚠️  Request failed {method} {url}: {str(last_err)[:120]}")
        return None

    def _parse_retry_after_seconds(self, value: str) -> Optional[float]:
        # Retry-After can be seconds or HTTP-date
        value = value.strip()
        try:
            return float(value)
        except Exception:
            pass
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = (dt - now).total_seconds()
            return max(0.0, delta)
        except Exception:
            return None

    async def _safe_read_text(self, resp: httpx.Response) -> Optional[str]:
        max_bytes = self.net.max_response_bytes
        total = 0
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        out: List[str] = []

        async for chunk in resp.aiter_bytes():
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return None
            out.append(decoder.decode(chunk))

        return "".join(out).strip()

    async def _safe_read_json(self, resp: httpx.Response) -> Optional[Any]:
        text = await self._safe_read_text(resp)
        if text is None:
            return None
        try:
            return self._safe_json_loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    def _safe_json_loads(self, text: str) -> Any:
        obj = json.loads(text)
        self._validate_json_depth(obj, max_depth=self.limits.max_json_depth)
        return obj

    def _validate_json_depth(self, obj: Any, depth: int = 0, max_depth: int = 20) -> None:
        if depth > max_depth:
            raise ValueError(f"JSON depth exceeds limit ({max_depth})")
        if isinstance(obj, dict):
            for v in obj.values():
                self._validate_json_depth(v, depth + 1, max_depth)
        elif isinstance(obj, list):
            for v in obj:
                self._validate_json_depth(v, depth + 1, max_depth)

    # -------------------------
    # SSRF policy (DNS-resolve)
    # -------------------------

    async def _validate_http_url(self, url: str) -> str:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            raise ValueError("Only http/https URLs are allowed")
        if p.username or p.password:
            raise ValueError("Userinfo in URL is not allowed")

        host = p.hostname
        if not host:
            raise ValueError("Missing hostname")

        # Extra hardening: disallow '@' even if parsed
        if "@" in (p.netloc or ""):
            raise ValueError("Invalid netloc (userinfo)")

        host_norm = host.lower().rstrip(".")

        # Check for localhost allowance
        allow_localhost = os.getenv("POLYMCP_ALLOW_LOCALHOST", "0") == "1"

        # Check if it's localhost or loopback IP
        is_localhost = host_norm in ("localhost", "127.0.0.1", "::1")

        # Also check for 127.x.x.x range
        try:
            ip = ipaddress.ip_address(host)
            if isinstance(ip, ipaddress.IPv4Address):
                is_localhost = is_localhost or str(ip).startswith("127.")
            elif isinstance(ip, ipaddress.IPv6Address):
                is_localhost = is_localhost or ip.is_loopback
        except ValueError:
            pass

        if is_localhost and not allow_localhost:
            raise ValueError("localhost/loopback blocked by policy (set POLYMCP_ALLOW_LOCALHOST=1)")

        # best-effort: validate hostname syntax if it isn't an IP literal
        if "%" in host:
            raise ValueError("IPv6 zone identifiers are blocked by policy")

        is_ip_literal = False
        try:
            ipaddress.ip_address(host)
            is_ip_literal = True
        except ValueError:
            is_ip_literal = False

        if not is_ip_literal:
            # accept punycode (xn--) by allowing ASCII form; reject weird unicode in host
            try:
                host.encode("ascii")
            except UnicodeEncodeError:
                raise ValueError("Non-ASCII hostname blocked by policy (use punycode)")
            if not self._HOST_RE.match(host_norm):
                raise ValueError(f"Invalid hostname: {host}")

        if not self._host_allowed(host_norm):
            raise ValueError(f"Host not allowed by policy: {host}")

        port = p.port or (443 if p.scheme == "https" else 80)
        if self.net.allow_ports and port not in self.net.allow_ports:
            raise ValueError(f"Port not allowed by policy: {port}")

        # Skip private network blocking for localhost if allowed
        if self.net.block_private_networks and not (is_localhost and allow_localhost):
            await self._block_private_dns(host, port)

        normalized = ParseResult(
            scheme=p.scheme,
            netloc=p.netloc,
            path=p.path or "",
            params="",
            query=p.query or "",
            fragment="",
        )
        return urlunparse(normalized)

    def _host_allowed(self, host: str) -> bool:
        allow = self.net.allow_hosts
        if not allow:
            return True
        h = host.lower().rstrip(".")
        for entry in allow:
            e = entry.lower().rstrip(".")
            if h == e or h.endswith("." + e):
                return True
        return False

    async def _block_private_dns(self, host: str, port: int) -> None:
        # IP literal check
        try:
            ip = ipaddress.ip_address(host)
            if self._is_blocked_ip(ip):
                raise ValueError("Blocked IP (private/link-local/reserved/multicast)")
            return
        except ValueError:
            pass

        # DNS resolve and check ALL A/AAAA
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
        except Exception:
            raise ValueError(f"DNS resolution failed for host: {host}")

        seen: Set[str] = set()
        for _, _, _, _, sockaddr in infos:
            ip_str = sockaddr[0]
            if ip_str in seen:
                continue
            seen.add(ip_str)

            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            if isinstance(ip, ipaddress.IPv6Address):
                mapped = ip.ipv4_mapped
                if mapped is not None:
                    ip = mapped

            if self._is_blocked_ip(ip):
                raise ValueError("Host resolves to blocked IP ranges (SSRF protection)")

    def _is_blocked_ip(self, ip: ipaddress._BaseAddress) -> bool:
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)

    # -------------------------
    # Categorization
    # -------------------------

    def _categorize_tools(self, tools: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        categorized = defaultdict(list)
        for tool in tools:
            categorized[self._categorize_tool(tool)].append(tool)
        return dict(categorized)

    def _categorize_tool(self, tool: Dict[str, Any]) -> str:
        name = str(tool.get("name", "")).lower()
        desc = str(tool.get("description", "")).lower()
        text = f"{name} {desc}"

        best_category = "misc"
        best_score = 0.0

        for category, cfg in self.CATEGORIES.items():
            score = 0.0
            for kw in cfg["keywords"]:
                if kw in text:
                    score += 1.0
            score *= float(cfg.get("weight", 1.0))
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    # -------------------------
    # Markdown generation
    # -------------------------

    def _generate_index(self, categorized: Dict[str, List[Dict[str, Any]]]) -> None:
        lines = [
            "# MCP Skills Index",
            "",
            f"Generated: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "## Categories",
            "",
        ]
        for cat, items in sorted(categorized.items(), key=lambda x: x[0]):
            safe_cat = self._sanitize_filename(cat)
            lines.append(f"- **{cat}** ({len(items)} tools) → `{safe_cat}.md`")
        lines.append("")
        self._atomic_write(self.output_dir / "INDEX.md", "\n".join(lines))

    def _generate_category_file(self, category: str, tools: List[Dict[str, Any]]) -> None:
        safe_category = self._sanitize_filename(category)

        lines: List[str] = [
            f"# {category.title()} Skills",
            "",
            f"Tools: {len(tools)}",
            "",
            "## Tools",
            "",
        ]

        for tool in tools:
            name = self._sanitize_markdown(str(tool.get("name", "unknown")), max_len=200)
            desc = self._sanitize_markdown(
                str(tool.get("description") or "").strip() or "No description provided.",
                max_len=self.limits.max_description_length
            )
            server = self._sanitize_markdown(str(tool.get("_server_name", "unknown")), max_len=100)

            lines.append(f"### `{name}`")
            lines.append("")
            lines.append(desc)
            lines.append("")
            lines.append(f"- Server: `{server}`")
            lines.append(f"- Estimated tokens: `{self._estimate_tokens(desc)}`")

            if self.include_examples:
                lines.extend(self._example_block(tool))

            lines.extend(self._best_practices_block(tool))
            lines.append("")

        self._atomic_write(self.output_dir / f"{safe_category}.md", "\n".join(lines).rstrip() + "\n")

    def _example_block(self, tool: Dict[str, Any]) -> List[str]:
        name = tool.get("name", "unknown")
        schema = tool.get("inputSchema") or tool.get("input_schema") or tool.get("parameters") or {}
        example = {"tool": name, "args": self._example_args_from_schema(schema)}
        return [
            "",
            "#### Example",
            "",
            "```json",
            json.dumps(example, indent=2, ensure_ascii=False),
            "```",
        ]

    def _example_args_from_schema(self, schema: Any) -> Dict[str, Any]:
        if not isinstance(schema, dict):
            return {}
        props = schema.get("properties")
        if not isinstance(props, dict):
            return {}

        out: Dict[str, Any] = {}
        for i, (k, v) in enumerate(props.items()):
            if i >= 8:
                break
            if not isinstance(v, dict):
                out[k] = "<value>"
                continue

            t = v.get("type")
            ex = v.get("example")
            if t == "string":
                out[k] = ex if isinstance(ex, str) else "<string>"
            elif t == "integer":
                out[k] = ex if isinstance(ex, int) else 0
            elif t == "number":
                out[k] = ex if isinstance(ex, (int, float)) else 0.0
            elif t == "boolean":
                out[k] = ex if isinstance(ex, bool) else False
            elif t == "array":
                out[k] = []
            elif t == "object":
                out[k] = {}
            else:
                out[k] = "<value>"
        return out

    def _best_practices_block(self, tool: Dict[str, Any]) -> List[str]:
        name = self._sanitize_markdown(str(tool.get("name", "tool")), max_len=100)
        return [
            "",
            "#### Best practices",
            "",
            f"- Validate inputs before calling `{name}`.",
            f"- Handle errors and timeouts; do not assume the tool always succeeds.",
            "- Log requests/results safely (avoid leaking secrets).",
        ]

    def _save_metadata(self) -> None:
        payload = {
            **self.stats,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "version": "1.0.0-prod",
        }
        self._atomic_write(self.output_dir / "metadata.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    # -------------------------
    # Utilities
    # -------------------------

    def _extract_server_name(self, url: str) -> str:
        name = url.replace("http://", "").replace("https://", "")
        name = name.split(":")[0].split("/")[0].split(".")[0]
        return self._sanitize_filename(name) or "unknown"

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _sanitize_filename(self, name: str) -> str:
        safe = re.sub(r"[^\w\-]", "_", name)
        safe = safe[: self.limits.max_category_name_length]
        return safe if safe else "misc"

    def _sanitize_markdown(self, text: str, max_len: int = 5000) -> str:
        text = (text or "")[:max_len]
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
        text = text.replace("```", "'''")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text.strip()

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".tmp.{uuid.uuid4().hex[:8]}")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
        except Exception as e:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(f"Failed to write {path}: {e}") from e

    def _finalize(self, start_time: datetime) -> None:
        self.stats["generation_time"] = (datetime.now() - start_time).total_seconds()