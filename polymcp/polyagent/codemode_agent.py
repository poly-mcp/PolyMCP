#!/usr/bin/env python3
"""
CodeMode Agent - Production LLM Code Generation for Tool Orchestration (Hardened)

Changes applied ONLY for the issues observed:
1) Docker resource limits now match DockerSandboxExecutor.ResourceLimits fields
   (cpu_quota/cpu_period/mem_limit/memswap_limit/pids_limit/tmpfs_size/ulimits)
2) Tool-call validation is AST-based (supports aliases like `t = tools`)
   so it won't falsely fail when tools are called through an alias.

Everything else is kept in the same "production security" spirit:
- Docker-only execution
- Tool allowlist + denylist
- Strict ```python``` code extraction
- AST safety denylist for dangerous imports/calls
"""

from __future__ import annotations

import ast
import json
import re
import time
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import (
    List,
    Dict,
    Any,
    Optional,
    Set,
    Tuple,
    Union,
)

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .llm_providers import LLMProvider
from ..sandbox.tools_api import ToolsAPI
from ..sandbox.docker_executor import (
    DockerSandboxExecutor,
    DockerExecutionResult,
    DockerNotAvailableError,
)
from .mcp_url import MCPBaseURL

logger = logging.getLogger(__name__)

# Type aliases
ToolAllowlist = Set[Tuple[Optional[str], str]]
ServerConfig = Dict[str, Any]


# ============================
# Exceptions
# ============================
class ToolDiscoveryError(Exception):
    """Raised when tool discovery fails."""
    pass


class CodeGenerationError(Exception):
    """Raised when code generation fails."""
    pass


class CodeValidationError(Exception):
    """Raised when generated code fails validation."""
    pass


class CodeExecutionError(Exception):
    """Raised when code execution fails."""
    pass


# ============================
# AST Safety Validator
# ============================
class _CodeSafetyVisitor(ast.NodeVisitor):
    """
    Denylist-based validator + tool call detection (supports aliasing).

    Goal: keep the "production safety" posture while avoiding false negatives.
    Docker remains the primary isolation boundary.
    """

    # Imports we do not want inside generated code (keep conservative)
    DENY_IMPORTS = {
        "os",
        "sys",
        "subprocess",
        "shlex",
        "socket",
        "ssl",
        "http",
        "urllib",
        "requests",
        "ftplib",
        "telnetlib",
        "paramiko",
        "pickle",
        "marshal",
        "ctypes",
        "resource",
        "signal",
        "multiprocessing",
        "threading",
    }

    # Builtins / functions we do not want called
    DENY_CALL_NAMES = {
        "eval",
        "exec",
        "compile",
        "__import__",
        "input",
        "help",
        "globals",
        "locals",
        "vars",
        "breakpoint",
        # NOTE: 'open' intentionally not denied here because your Docker sandbox is read-only
        # and some tasks may legitimately need temp outputs; adjust if you want stricter.
    }

    # Attribute calls we do not want (module.func)
    DENY_ATTR_CALLS = {
        ("os", "system"),
        ("os", "popen"),
        ("subprocess", "run"),
        ("subprocess", "Popen"),
        ("subprocess", "call"),
        ("subprocess", "check_call"),
        ("subprocess", "check_output"),
    }

    def __init__(self) -> None:
        self.errors: List[str] = []
        # Tool alias tracking + tool call detection
        self.tool_aliases: Set[str] = {"tools"}
        self.has_tool_call: bool = False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name0 = (alias.name or "").split(".")[0]
            if name0 in self.DENY_IMPORTS:
                self.errors.append(f"Import denied: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod0 = (node.module or "").split(".")[0]
        if mod0 in self.DENY_IMPORTS:
            self.errors.append(f"Import denied: from {node.module} import ...")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Detect aliasing like: t = tools
        try:
            if isinstance(node.value, ast.Name) and node.value.id in self.tool_aliases:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        self.tool_aliases.add(tgt.id)
        except Exception:
            pass
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detect tools.<x>(...) or alias.<x>(...)
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id in self.tool_aliases:
                self.has_tool_call = True

        # Deny direct calls by name
        if isinstance(node.func, ast.Name):
            if node.func.id in self.DENY_CALL_NAMES:
                self.errors.append(f"Call denied: {node.func.id}()")

        # Deny specific attribute calls
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            base = node.func.value.id
            attr = node.func.attr
            if (base, attr) in self.DENY_ATTR_CALLS:
                self.errors.append(f"Call denied: {base}.{attr}()")

        self.generic_visit(node)


def validate_generated_code(code: str, *, max_chars: int) -> None:
    if not code or not code.strip():
        raise CodeValidationError("Empty generated code")
    if len(code) > max_chars:
        raise CodeValidationError(f"Generated code too large: {len(code)} > {max_chars}")

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise CodeValidationError(f"Generated code has syntax error: {e}") from e

    visitor = _CodeSafetyVisitor()
    visitor.visit(tree)

    if visitor.errors:
        raise CodeValidationError("Generated code rejected:\n- " + "\n- ".join(visitor.errors))

    # Require at least one tool call (supports aliasing)
    if not visitor.has_tool_call:
        raise CodeValidationError("Generated code must call at least one tool (tools.* or tools.call(...)).")

    # Enforce required import json (as per your original rules)
    if re.search(r"^\s*import\s+json\s*$", code, flags=re.MULTILINE) is None:
        raise CodeValidationError("Generated code must include: import json")


# ============================
# Config
# ============================
@dataclass
class CodeModeConfig:
    """Configuration for CodeModeAgent."""
    sandbox_timeout: float = 30.0
    max_retries: int = 2
    retry_delay: float = 0.5
    verbose: bool = False

    # Docker settings
    docker_image: str = "python:3.11-slim"
    docker_enable_network: bool = False

    # IMPORTANT: Must match DockerSandboxExecutor.ResourceLimits fields
    docker_limits: Dict[str, Any] = field(default_factory=lambda: {
        "cpu_quota": 50000,         # microseconds per 100ms period
        "cpu_period": 100000,
        "mem_limit": "512m",
        "memswap_limit": "512m",
        "pids_limit": 256,
        "tmpfs_size": "32m",
        # Optional: override ulimits if needed
        # "ulimits": [
        #     {"Name": "nofile", "Soft": 1024, "Hard": 2048},
        #     {"Name": "nproc", "Soft": 64, "Hard": 128},
        # ],
    })

    # Safety limits
    max_tool_calls: int = 200
    max_payload_bytes: int = 200_000
    max_output_chars: int = 200_000
    max_code_chars: int = 60_000
    tool_denylist: Set[str] = field(default_factory=set)

    # Security profiles (Linux)
    seccomp_profile: Optional[str] = None
    apparmor_profile: Optional[str] = None

    # HTTP settings
    http_timeout: Tuple[float, float] = (3.05, 30.0)  # (connect, read)
    http_retries: int = 3

    # Tool selection
    max_tools_in_prompt: int = 15

    def __post_init__(self) -> None:
        if self.sandbox_timeout <= 0:
            raise ValueError("sandbox_timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")


# ============================
# Agent
# ============================
class CodeModeAgent:
    """
    Production-grade CodeMode Agent for LLM-driven tool orchestration.

    Generates Python code that orchestrates tool calls, validates it,
    then executes the code in a Docker sandbox with tool calls bridged back to the host.
    """

    SYSTEM_PROMPT = """You are an AI assistant that writes Python code to accomplish tasks.

You have access to tools through the `tools` object. Each tool is a method you can call.

AVAILABLE TOOLS:
{tools_documentation}

RULES:
1. Always import json at the start: `import json`
2. Call tools using: `tools.tool_name(param1=value1, param2=value2)`
3. For server-specific tools: `tools.call(server="SERVER_ID", tool="TOOL_NAME", param1=value1)`
4. Tools return JSON strings - parse with: `result = json.loads(tools.tool_name(...))`
5. Print progress and results clearly using print()
6. Handle errors with try-except blocks
7. Use loops, conditions, and variables as needed for complex tasks
8. You MUST call at least one tool (either tools.<name>(...) or tools.call(...))

Write ONLY executable Python code between ```python and ``` tags.
Do NOT include explanations outside the code block.
"""

    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_servers: Optional[List[str]] = None,
        stdio_servers: Optional[List[ServerConfig]] = None,
        registry_path: Optional[str] = None,
        config: Optional[CodeModeConfig] = None,
        # Legacy parameters (for backwards compatibility)
        sandbox_timeout: float = 30.0,
        max_retries: int = 2,
        verbose: bool = False,
        http_headers: Optional[Dict[str, str]] = None,
        docker_image: str = "python:3.11-slim",
        docker_limits: Optional[Dict[str, Any]] = None,
        docker_enable_network: bool = False,
        max_tool_calls: int = 200,
        max_payload_bytes: int = 200_000,
        max_output_chars: int = 200_000,
        tool_denylist: Optional[Set[str]] = None,
        seccomp_profile: Optional[str] = None,
        apparmor_profile: Optional[str] = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.mcp_servers = list(mcp_servers or [])
        self.stdio_servers = list(stdio_servers or [])
        self.http_headers = dict(http_headers or {})

        # Build config from parameters or use provided config
        if config is not None:
            self.config = config
        else:
            self.config = CodeModeConfig(
                sandbox_timeout=sandbox_timeout,
                max_retries=max_retries,
                verbose=verbose,
                docker_image=docker_image,
                docker_limits=(docker_limits if docker_limits is not None else CodeModeConfig().docker_limits),
                docker_enable_network=docker_enable_network,
                max_tool_calls=max_tool_calls,
                max_payload_bytes=max_payload_bytes,
                max_output_chars=max_output_chars,
                tool_denylist=(tool_denylist or set()),
                seccomp_profile=seccomp_profile,
                apparmor_profile=apparmor_profile,
            )

        # Tool caches
        self._http_tools: Dict[str, List[Dict[str, Any]]] = {}
        self._stdio_tools: Dict[str, List[Dict[str, Any]]] = {}

        # Stdio client management
        self._stdio_clients: Dict[str, Any] = {}
        self._stdio_adapters: Dict[str, Any] = {}
        self._stdio_started = False
        self._stdio_lock = asyncio.Lock()

        # HTTP session with retry logic
        self._http_session = self._create_http_session()

        # Observability
        self.last_request_id: Optional[str] = None
        self.last_prompt: Optional[str] = None
        self.last_code: Optional[str] = None
        self.last_validation_error: Optional[str] = None

        # Load registry if provided
        if registry_path:
            self._load_registry(registry_path)

        # Discover HTTP tools
        self._discover_http_tools()

    # ===================== HTTP session =====================

    def _create_http_session(self) -> requests.Session:
        """Create HTTP session with retry logic."""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.http_retries,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    # ===================== Registry =====================

    def _load_registry(self, registry_path: str) -> None:
        """Load server registry from JSON file."""
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)

            # Add HTTP servers
            for server in registry.get("servers", []):
                if server not in self.mcp_servers:
                    self.mcp_servers.append(server)

            # Add stdio servers
            for server_config in registry.get("stdio_servers", []):
                if server_config not in self.stdio_servers:
                    self.stdio_servers.append(server_config)

            if self.config.verbose:
                logger.info("Loaded registry: %s", registry_path)

        except FileNotFoundError:
            logger.warning("Registry file not found: %s", registry_path)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in registry file: %s", e)
        except Exception as e:
            logger.error("Failed to load registry: %s", e)

    # ===================== Tool discovery =====================

    def _discover_http_tools(self) -> None:
        """Discover tools from all HTTP MCP servers."""
        for server_url in self.mcp_servers:
            try:
                tools = self._fetch_server_tools(server_url)
                self._http_tools[server_url] = tools
                if self.config.verbose:
                    logger.info("Discovered %d tools from %s", len(tools), server_url)
            except Exception as e:
                logger.warning("Failed to discover tools from %s: %s", server_url, e)
                self._http_tools[server_url] = []

    def _fetch_server_tools(self, server_url: str) -> List[Dict[str, Any]]:
        """Fetch tools list from an HTTP MCP server."""
        base = MCPBaseURL.normalize(server_url)
        list_url = base.list_tools_url()
        response = self._http_session.get(
            list_url,
            timeout=self.config.http_timeout,
            headers=self.http_headers,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("tools", [])

    # ===================== Async stdio servers =====================

    async def _start_stdio_servers(self) -> None:
        """Start stdio MCP servers (async)."""
        async with self._stdio_lock:
            if self._stdio_started or not self.stdio_servers:
                return

            from ..mcp_stdio_client import MCPStdioClient, MCPStdioAdapter, MCPServerConfig

            for config_dict in self.stdio_servers:
                server_id = None
                try:
                    server_config = MCPServerConfig(
                        command=config_dict["command"],
                        args=config_dict.get("args", []),
                        env=config_dict.get("env"),
                    )

                    client = MCPStdioClient(server_config)
                    await client.start()

                    adapter = MCPStdioAdapter(client)
                    server_id = f"stdio://{server_config.command}"

                    self._stdio_clients[server_id] = client
                    self._stdio_adapters[server_id] = adapter

                    # Discover tools
                    try:
                        tools = await adapter.get_tools()
                        self._stdio_tools[server_id] = tools
                    except Exception:
                        self._stdio_tools[server_id] = []

                    if self.config.verbose:
                        tool_count = len(self._stdio_tools.get(server_id, []))
                        logger.info("Started stdio server: %s (%d tools)", server_id, tool_count)

                except Exception as e:
                    logger.error("Failed to start stdio server: %s", e)
                    if server_id:
                        self._stdio_tools[server_id] = []

            self._stdio_started = True
            if self._stdio_clients:
                await asyncio.sleep(0.2)

    async def _stop_stdio_servers(self) -> None:
        """Stop all stdio servers."""
        async with self._stdio_lock:
            for server_id, client in list(self._stdio_clients.items()):
                try:
                    await client.stop()
                except Exception as e:
                    logger.debug("Error stopping stdio server %s: %s", server_id, e)

            self._stdio_clients.clear()
            self._stdio_adapters.clear()
            self._stdio_tools.clear()
            self._stdio_started = False

    # ===================== Tool docs =====================

    def _get_all_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        for server_url, server_tools in self._http_tools.items():
            for tool in server_tools:
                tool_copy = dict(tool)
                tool_copy["_server"] = server_url
                tools.append(tool_copy)

        for server_id, server_tools in self._stdio_tools.items():
            for tool in server_tools:
                tool_copy = dict(tool)
                tool_copy["_server"] = server_id
                tools.append(tool_copy)

        return tools

    def _select_relevant_tools(self, query: str, max_tools: int = 15) -> List[Dict[str, Any]]:
        all_tools = self._get_all_tools()
        return all_tools[:max_tools]

    def _generate_tools_documentation(self, query: Optional[str] = None) -> str:
        if query:
            tools = self._select_relevant_tools(query, max_tools=self.config.max_tools_in_prompt)
        else:
            tools = self._get_all_tools()

        if not tools:
            return "No tools available."

        docs: List[str] = []

        for tool in tools:
            name = tool.get("name", "unknown")
            description = (tool.get("description") or "No description").strip()
            description = description.replace("```", "` ` `")

            input_schema = tool.get("input_schema", {}) or {}
            properties = input_schema.get("properties", {}) or {}
            required = set(input_schema.get("required", []) or [])

            params: List[str] = []
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "any")
                is_required = param_name in required

                enum_values = param_info.get("enum")
                if enum_values and isinstance(enum_values, list) and enum_values:
                    example = json.dumps(enum_values[0])
                else:
                    example = {
                        "string": '"value"',
                        "number": "1.0",
                        "integer": "1",
                        "boolean": "True",
                        "array": '["item1", "item2"]',
                        "object": "{}",
                    }.get(param_type, '"value"')

                req_marker = "" if is_required else "?"
                params.append(f"{param_name}{req_marker}={example}")

            signature = f"tools.{name}({', '.join(params)})"

            doc = f"""
tools.{name}():
  Description: {description}
  Signature: {signature}
  Returns: JSON string (parse with json.loads())"""
            docs.append(doc)

        docs.append("""

For server-specific tools, use:
  tools.call(server="http://...", tool="tool_name", param1=value1, ...)""")

        return "\n".join(docs)

    # ===================== Code generation =====================

    def _extract_code_from_response(self, response: str) -> str:
        """Strictly extract Python code from a ```python ...``` block."""
        m = re.search(r"```python\s*(.*?)```", response, re.DOTALL | re.IGNORECASE)
        if not m:
            raise CodeGenerationError("Failed to find a ```python ...``` block in LLM response.")
        code = m.group(1).strip()
        if not code:
            raise CodeGenerationError("Empty ```python``` code block.")
        return code

    def _generate_code(self, user_message: str, previous_error: Optional[str] = None) -> str:
        """Generate Python code for the user's request."""
        tools_docs = self._generate_tools_documentation(query=user_message)
        system_prompt = self.SYSTEM_PROMPT.format(tools_documentation=tools_docs)

        user_prompt = f"USER REQUEST:\n{user_message}"
        if previous_error:
            user_prompt += f"\n\nPREVIOUS ERROR:\n{previous_error}\n\nPlease fix the error and generate corrected code."
        user_prompt += "\n\nWrite the Python code to accomplish this task:"

        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        self.last_prompt = full_prompt

        if self.config.verbose:
            logger.info("GENERATING CODE (prompt chars=%d)", len(full_prompt))

        try:
            response = self.llm_provider.generate(full_prompt)
            code = self._extract_code_from_response(response)

            self.last_code = code

            # Validate before execution
            validate_generated_code(code, max_chars=self.config.max_code_chars)
            self.last_validation_error = None

            if self.config.verbose:
                logger.info("Generated & validated code (%d chars)", len(code))

            return code

        except CodeValidationError as e:
            self.last_validation_error = str(e)
            raise
        except Exception as e:
            raise CodeGenerationError(f"Code generation failed: {e}") from e

    # ===================== Tool execution bridge =====================

    def _create_tools_api(self) -> ToolsAPI:
        http_headers = self.http_headers
        http_timeout = self.config.http_timeout

        def http_executor(server_url: str, tool_name: str, params: Dict) -> Dict:
            try:
                base = MCPBaseURL.normalize(server_url)
                invoke_url = base.invoke_url(tool_name)
                response = self._http_session.post(
                    invoke_url,
                    json=params,
                    timeout=http_timeout,
                    headers=http_headers,
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                return {"error": str(e), "status": "error"}

        async def stdio_executor(server_id: str, tool_name: str, params: Dict) -> Dict:
            adapter = self._stdio_adapters.get(server_id)
            if not adapter:
                return {"error": f"Stdio adapter not found: {server_id}", "status": "error"}
            try:
                return await adapter.invoke_tool(tool_name, params)
            except Exception as e:
                return {"error": str(e), "status": "error"}

        return ToolsAPI(
            http_tools=self._http_tools,
            stdio_adapters=self._stdio_adapters,
            http_executor=http_executor,
            stdio_executor=stdio_executor,
            verbose=self.config.verbose,
        )

    def _build_tool_allowlist(self) -> Optional[ToolAllowlist]:
        """Build server-aware tool allowlist."""
        allowlist: ToolAllowlist = set()

        # HTTP tools
        for server_url, tools in self._http_tools.items():
            for tool in tools:
                name = tool.get("name")
                if name:
                    allowlist.add((server_url, name))
                    allowlist.add((None, name))  # Allow unqualified calls (same as your original)

        # Stdio tools (do not add (None, name) to avoid collisions)
        for server_id, tools in self._stdio_tools.items():
            for tool in tools:
                name = tool.get("name")
                if name:
                    allowlist.add((server_id, name))

        return allowlist if allowlist else None

    def _execute_code(self, code: str) -> DockerExecutionResult:
        """Execute code in Docker sandbox."""
        tools_api = self._create_tools_api()
        allowlist = self._build_tool_allowlist()

        executor = DockerSandboxExecutor(
            tools_api=tools_api,
            timeout=self.config.sandbox_timeout,
            docker_image=self.config.docker_image,
            resource_limits=self.config.docker_limits,  # now matches ResourceLimits fields
            enable_network=self.config.docker_enable_network,
            verbose=self.config.verbose,
            max_tool_calls=self.config.max_tool_calls,
            max_payload_bytes=self.config.max_payload_bytes,
            max_output_chars=self.config.max_output_chars,
            tool_allowlist=allowlist,
            tool_denylist=self.config.tool_denylist,
            seccomp_profile=self.config.seccomp_profile,
            apparmor_profile=self.config.apparmor_profile,
        )

        return executor.execute(code)

    # ===================== Public API =====================

    def run(self, user_message: str) -> str:
        if not user_message or not user_message.strip():
            raise ValueError("user_message cannot be empty")

        request_id = str(uuid.uuid4())
        self.last_request_id = request_id

        if self.config.verbose:
            logger.info("=" * 60)
            logger.info("CODE MODE AGENT request_id=%s", request_id)
            logger.info("=" * 60)
            logger.info("Request: %s", user_message)

        previous_error: Optional[str] = None
        last_result: Optional[DockerExecutionResult] = None

        for attempt in range(self.config.max_retries + 1):
            if attempt > 0:
                if self.config.verbose:
                    logger.info("Retry %d/%d", attempt, self.config.max_retries)
                time.sleep(self.config.retry_delay * attempt)

            try:
                code = self._generate_code(user_message, previous_error)

                result = self._execute_code(code)
                last_result = result

                if result.success:
                    output = result.output.strip() if result.output else ""
                    return output if output else "Task completed successfully."

                previous_error = result.error or f"Execution failed with exit code {result.exit_code}"
                if self.config.verbose:
                    logger.warning(
                        "Execution failed request_id=%s attempt=%d error=%s",
                        request_id, attempt, previous_error
                    )

            except CodeValidationError as e:
                previous_error = f"CodeValidationError: {e}"
                if self.config.verbose:
                    logger.warning(
                        "Validation failed request_id=%s attempt=%d error=%s",
                        request_id, attempt, previous_error
                    )

            except CodeGenerationError as e:
                previous_error = f"CodeGenerationError: {e}"
                if self.config.verbose:
                    logger.warning(
                        "Code generation failed request_id=%s attempt=%d error=%s",
                        request_id, attempt, previous_error
                    )

            except DockerNotAvailableError:
                raise

            except Exception as e:
                previous_error = f"{type(e).__name__}: {e}"
                if self.config.verbose:
                    logger.warning(
                        "Unexpected error request_id=%s attempt=%d error=%s",
                        request_id, attempt, previous_error
                    )

        error_msg = previous_error or "Unknown error"

        if last_result and last_result.output:
            return f"Error: {error_msg}\n\nPartial output:\n{last_result.output}"

        return f"Failed to complete task: {error_msg}"

    async def run_async(self, user_message: str) -> str:
        await self._start_stdio_servers()
        return self.run(user_message)

    def add_server(self, server_url: str) -> int:
        if server_url in self.mcp_servers:
            return len(self._http_tools.get(server_url, []))

        self.mcp_servers.append(server_url)

        try:
            tools = self._fetch_server_tools(server_url)
            self._http_tools[server_url] = tools
            if self.config.verbose:
                logger.info("Added server %s with %d tools", server_url, len(tools))
            return len(tools)
        except Exception as e:
            logger.warning("Failed to discover tools from %s: %s", server_url, e)
            self._http_tools[server_url] = []
            return 0

    def remove_server(self, server_url: str) -> bool:
        if server_url not in self.mcp_servers:
            return False
        self.mcp_servers.remove(server_url)
        self._http_tools.pop(server_url, None)
        if self.config.verbose:
            logger.info("Removed server: %s", server_url)
        return True

    def get_available_tools(self) -> List[str]:
        tools = self._get_all_tools()
        return [t.get("name", "") for t in tools if t.get("name")]

    def close(self) -> None:
        self._http_session.close()

    def __enter__(self) -> "CodeModeAgent":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        server_count = len(self.mcp_servers) + len(self.stdio_servers)
        tool_count = sum(len(t) for t in self._http_tools.values())
        tool_count += sum(len(t) for t in self._stdio_tools.values())
        return f"CodeModeAgent(servers={server_count}, tools={tool_count})"


class AsyncCodeModeAgent(CodeModeAgent):
    """Async-first CodeMode Agent with full stdio server support."""

    async def run_async(self, user_message: str) -> str:
        await self._start_stdio_servers()
        return self.run(user_message)

    async def stop(self) -> None:
        await self._stop_stdio_servers()
        self.close()

    async def __aenter__(self) -> "AsyncCodeModeAgent":
        await self._start_stdio_servers()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
