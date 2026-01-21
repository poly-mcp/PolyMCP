#!/usr/bin/env python3
"""
Docker Sandbox Executor - PRODUCTION IMPLEMENTATION

Security & production features:
- Docker hardening (non-root, cap_drop, read-only, tmpfs, no-new-privileges, resource limits, ulimits)
- Tool allowlist server-aware (supports both string and tuple (server, tool))
- Params validation (type, size, depth/nodes)
- Error sanitization (reduces path/ip/host leaks)
- TTY mode to avoid multiplexed stream issues on Windows/Linux
- Start container BEFORE attach_socket (fix hang on Docker Desktop/Windows npipe)
- Fail-closed image allowlist (optional but enabled by default)
"""

from __future__ import annotations

import json
import time
import tempfile
import shutil
import re
import logging
import threading
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, List, Union
from contextlib import contextmanager

try:
    import docker
    import docker.errors
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None  # type: ignore


logger = logging.getLogger(__name__)


@dataclass
class DockerExecutionResult:
    """Result of Docker sandbox execution."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0
    exit_code: int = 0
    container_id: Optional[str] = None
    resource_usage: Optional[Dict[str, Any]] = None
    tool_calls_count: int = 0


@dataclass
class ResourceLimits:
    """Container resource limits configuration."""
    cpu_quota: int = 50000  # microseconds per 100ms period
    cpu_period: int = 100000
    mem_limit: str = "256m"
    memswap_limit: str = "256m"
    pids_limit: int = 64
    tmpfs_size: str = "16m"
    ulimits: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"Name": "nofile", "Soft": 1024, "Hard": 2048},
        {"Name": "nproc", "Soft": 64, "Hard": 128},
    ])


ToolAllowlistEntry = Union[str, Tuple[Optional[str], str]]
ToolAllowlist = Set[ToolAllowlistEntry]


class DockerNotAvailableError(RuntimeError):
    """Raised when Docker is not available."""
    pass


class ExecutionTimeoutError(TimeoutError):
    """Raised when execution exceeds timeout."""
    pass


class ToolCallLimitExceededError(RuntimeError):
    """Raised when max tool calls exceeded."""
    pass


class DockerSandboxExecutor:
    """
    Production-grade Docker sandbox executor for running untrusted Python code.

    - Secure container configuration (non-root, capabilities dropped, read-only filesystem)
    - Tool call bridging via stdin/stdout
    - Resource limits enforcement
    - Server-aware tool allowlist
    - Comprehensive error handling and sanitization
    """

    DEFAULT_IMAGE = "python:3.11-slim"

    # Recommended safe baseline images (you can extend)
    ALLOWED_IMAGES_DEFAULT = frozenset({
        "python:3.11-slim",
        "python:3.11-alpine",
        "python:3.10-slim",
        "python:3.10-alpine",
        "python:3.12-slim",
        "python:3.12-alpine",
    })

    # Redaction patterns (best-effort)
    _PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\[^\s'\"<>|]+|/(?:home|usr|var|tmp|etc|opt)[^\s'\"<>|]*)")
    _IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    _HOSTNAME_PATTERN = re.compile(r"\b[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}\b")

    def __init__(
        self,
        tools_api: Any,
        timeout: float = 30.0,
        docker_image: str = DEFAULT_IMAGE,
        resource_limits: Optional[Union[Dict[str, Any], ResourceLimits]] = None,
        enable_network: bool = False,
        verbose: bool = False,
        *,
        max_tool_calls: int = 200,
        max_payload_bytes: int = 200_000,
        max_output_chars: int = 200_000,
        tool_allowlist: Optional[ToolAllowlist] = None,
        tool_denylist: Optional[Set[str]] = None,
        seccomp_profile: Optional[str] = None,
        apparmor_profile: Optional[str] = None,

        # Image policy
        allowed_images: Optional[Set[str]] = None,
        enforce_allowed_images: bool = True,
    ):
        if not DOCKER_AVAILABLE:
            raise DockerNotAvailableError("Docker SDK not installed. Run: pip install docker")

        self._validate_init_params(
            timeout=timeout,
            max_tool_calls=max_tool_calls,
            max_payload_bytes=max_payload_bytes,
            max_output_chars=max_output_chars,
        )

        self.tools_api = tools_api
        self.timeout = float(timeout)
        self.docker_image = docker_image
        self.enable_network = bool(enable_network)
        self.verbose = bool(verbose)

        # Resource limits
        if isinstance(resource_limits, ResourceLimits):
            self.resource_limits = resource_limits
        elif isinstance(resource_limits, dict):
            self.resource_limits = ResourceLimits(**resource_limits)
        else:
            self.resource_limits = ResourceLimits()

        # Safety limits
        self.max_tool_calls = int(max_tool_calls)
        self.max_payload_bytes = int(max_payload_bytes)
        self.max_output_chars = int(max_output_chars)
        self.tool_allowlist = tool_allowlist
        self.tool_denylist = tool_denylist or set()

        # Security profiles
        self.seccomp_profile = seccomp_profile
        self.apparmor_profile = apparmor_profile

        # Image validation
        self.allowed_images = allowed_images or set(self.ALLOWED_IMAGES_DEFAULT)
        self.enforce_allowed_images = bool(enforce_allowed_images)
        self._validate_docker_image(self.docker_image)

        # Runtime state
        self._tool_calls_used = 0
        self._lock = threading.Lock()

        # Docker client
        self.docker_client = self._create_docker_client()
        self._ensure_image_available()

    # ===================== Validation =====================

    def _validate_init_params(
        self,
        timeout: float,
        max_tool_calls: int,
        max_payload_bytes: int,
        max_output_chars: int,
    ) -> None:
        if timeout <= 0 or timeout > 3600:
            raise ValueError(f"timeout must be between 0 and 3600, got {timeout}")
        if max_tool_calls <= 0 or max_tool_calls > 10000:
            raise ValueError(f"max_tool_calls must be between 1 and 10000, got {max_tool_calls}")
        if max_payload_bytes <= 0 or max_payload_bytes > 10_000_000:
            raise ValueError(f"max_payload_bytes must be between 1 and 10MB, got {max_payload_bytes}")
        if max_output_chars <= 0 or max_output_chars > 10_000_000:
            raise ValueError(f"max_output_chars must be between 1 and 10M, got {max_output_chars}")

    def _validate_docker_image(self, image: str) -> None:
        if not image or not isinstance(image, str):
            raise ValueError("docker_image must be a non-empty string")

        if self.allowed_images and image not in self.allowed_images:
            msg = f"Docker image '{image}' is not in allowed list"
            if self.enforce_allowed_images:
                raise ValueError(msg)
            logger.warning(msg + " (enforce_allowed_images=False, proceeding)")

    def _create_docker_client(self) -> Any:
        try:
            client = docker.from_env()
            client.ping()
            logger.debug("Docker client initialized successfully")
            return client
        except docker.errors.DockerException as e:
            raise DockerNotAvailableError(f"Failed to connect to Docker: {e}") from e
        except Exception as e:
            raise DockerNotAvailableError(f"Docker initialization error: {e}") from e

    def _ensure_image_available(self) -> None:
        try:
            self.docker_client.images.get(self.docker_image)
            if self.verbose:
                logger.info(f"Docker image available: {self.docker_image}")
        except docker.errors.ImageNotFound:
            if self.verbose:
                logger.info(f"Pulling Docker image: {self.docker_image}")
            try:
                self.docker_client.images.pull(self.docker_image)
                if self.verbose:
                    logger.info(f"Docker image pulled: {self.docker_image}")
            except docker.errors.APIError as e:
                raise DockerNotAvailableError(f"Failed to pull image {self.docker_image}: {e}") from e

    # ===================== Socket helpers =====================

    def _get_raw_socket(self, sock_obj: Any) -> Any:
        return getattr(sock_obj, "_sock", sock_obj)

    def _socket_set_timeout(self, sock_obj: Any, timeout_s: float) -> None:
        raw = self._get_raw_socket(sock_obj)
        if hasattr(raw, "settimeout"):
            raw.settimeout(timeout_s)

    def _socket_send(self, sock_obj: Any, data: bytes) -> None:
        raw = self._get_raw_socket(sock_obj)
        if hasattr(raw, "sendall"):
            raw.sendall(data)
            return
        if hasattr(raw, "send"):
            view = memoryview(data)
            sent = 0
            while sent < len(data):
                n = raw.send(view[sent:])
                if n <= 0:
                    raise ConnectionError("Socket send returned 0 bytes")
                sent += n
            return
        raise RuntimeError("Socket has no send/sendall method")

    def _socket_recv(self, sock_obj: Any, bufsize: int) -> bytes:
        raw = self._get_raw_socket(sock_obj)
        if hasattr(raw, "recv"):
            return raw.recv(bufsize)
        raise RuntimeError("Socket has no recv method")

    def _socket_close(self, sock_obj: Any) -> None:
        try:
            raw = self._get_raw_socket(sock_obj)
            if hasattr(raw, "close"):
                raw.close()
        except Exception:
            pass

    # ===================== Error sanitization =====================

    def _sanitize_error_message(self, message: str) -> str:
        try:
            result = str(message)
            result = self._PATH_PATTERN.sub("<path>", result)
            result = self._IP_PATTERN.sub("<ip>", result)
            result = self._HOSTNAME_PATTERN.sub("<host>", result)
            if len(result) > 2000:
                result = result[:1997] + "..."
            return result
        except Exception:
            return "Execution error (details sanitized)"

    # ===================== Allowlist logic =====================

    def _parse_allowlist(self) -> Tuple[Set[str], Set[Tuple[Optional[str], str]]]:
        global_names: Set[str] = set()
        server_pairs: Set[Tuple[Optional[str], str]] = set()

        if self.tool_allowlist is None:
            return global_names, server_pairs

        for entry in self.tool_allowlist:
            if isinstance(entry, str):
                global_names.add(entry)
            elif isinstance(entry, tuple) and len(entry) == 2:
                server, tool = entry
                if (server is None or isinstance(server, str)) and isinstance(tool, str):
                    server_pairs.add((server, tool))

        return global_names, server_pairs

    def _is_tool_allowed(self, server: Optional[str], tool: str) -> bool:
        if tool in self.tool_denylist:
            return False

        if self.tool_allowlist is None:
            return True

        if server is not None:
            if not isinstance(server, str) or len(server) > 1024:
                return False

        global_names, server_pairs = self._parse_allowlist()

        if tool in global_names:
            return True

        if server is not None and (server, tool) in server_pairs:
            return True

        if (None, tool) in server_pairs:
            return True

        # allow unqualified tool if present somewhere in pairs
        return any(t == tool for (_, t) in server_pairs)

    # ===================== Params validation =====================

    def _validate_tool_params(self, params: Any) -> Tuple[bool, str, Dict[str, Any]]:
        if params is None:
            return True, "", {}

        if not isinstance(params, dict):
            return False, "params must be a dictionary", {}

        # Size guard
        try:
            encoded = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            byte_size = len(encoded.encode("utf-8", errors="replace"))
            if byte_size > self.max_payload_bytes:
                return False, f"params too large ({byte_size} > {self.max_payload_bytes} bytes)", {}
        except (TypeError, ValueError) as e:
            return False, f"params not JSON-serializable: {e}", {}

        # Depth/nodes guard
        if not self._check_params_complexity(params, max_depth=12, max_nodes=2500):
            return False, "params structure too complex (depth or node count exceeded)", {}

        return True, "", dict(params)

    def _check_params_complexity(self, obj: Any, max_depth: int, max_nodes: int) -> bool:
        stack: List[Tuple[Any, int]] = [(obj, 0)]
        nodes = 0

        while stack:
            current, depth = stack.pop()
            if depth > max_depth:
                return False
            nodes += 1
            if nodes > max_nodes:
                return False

            if isinstance(current, dict):
                for value in current.values():
                    stack.append((value, depth + 1))
            elif isinstance(current, list):
                for item in current:
                    stack.append((item, depth + 1))

        return True

    # ===================== Container config =====================

    def _build_container_config(self, code_dir: Path) -> Dict[str, Any]:
        limits = self.resource_limits

        security_opt = ["no-new-privileges"]
        if self.seccomp_profile:
            security_opt.append(f"seccomp={self.seccomp_profile}")
        if self.apparmor_profile:
            security_opt.append(f"apparmor={self.apparmor_profile}")

        return {
            "image": self.docker_image,
            "command": ["python", "-u", "/workspace/runner.py"],
            "stdin_open": True,

            # ✅ Important: tty avoids multiplex stream issues on many Docker setups
            "tty": True,

            "volumes": {str(code_dir.absolute()): {"bind": "/workspace", "mode": "ro"}},
            "working_dir": "/workspace",

            # CPU/mem/pids limits
            "cpu_quota": limits.cpu_quota,
            "cpu_period": limits.cpu_period,
            "mem_limit": limits.mem_limit,
            "memswap_limit": limits.memswap_limit,
            "pids_limit": limits.pids_limit,

            # ✅ Apply ulimits (previously defined but unused)
            "ulimits": limits.ulimits,

            "network_disabled": not self.enable_network,
            "read_only": True,
            "tmpfs": {"/tmp": f"size={limits.tmpfs_size},mode=1777"},
            "user": "nobody",
            "privileged": False,
            "cap_drop": ["ALL"],
            "security_opt": security_opt,
        }

    # ===================== Runner script =====================

    def _build_runner_script(self, user_code: str) -> str:
        # ✅ preserve lines, keep blanks, and indent consistently
        indented_code = "\n".join(
            ("    " + line) if line else ""
            for line in user_code.splitlines()
        )

        script = '''#!/usr/bin/env python3
# Auto-generated runner script - DO NOT EDIT
import sys
import json
import uuid


class ToolsProxy:
    """Proxy for calling host tools via stdin/stdout bridge."""

    def __getattr__(self, name: str):
        if name == "call":
            return self._call_with_server
        return self._make_tool_caller(name)

    def _call_with_server(self, *, server: str, tool: str, **kwargs):
        return self._execute_call(tool=tool, server=server, params=kwargs)

    def _make_tool_caller(self, tool_name: str):
        def caller(**kwargs):
            return self._execute_call(tool=tool_name, server=None, params=kwargs)
        return caller

    def _execute_call(self, tool: str, server, params: dict) -> str:
        call_id = str(uuid.uuid4())
        message = {"id": call_id, "tool": tool, "params": params}
        if server is not None:
            message["server"] = server

        # ✅ IMPORTANT: emit literal \\n (prevents unterminated string literal bugs)
        sys.stdout.write("__TOOL_CALL__ " + json.dumps(message, ensure_ascii=False) + "\\n")
        sys.stdout.flush()
        return self._wait_for_result(call_id)

    def _wait_for_result(self, call_id: str) -> str:
        while True:
            line = sys.stdin.readline()
            if not line:
                raise RuntimeError("Host disconnected while waiting for tool result")

            line = line.rstrip("\\n")
            if not line.startswith("__TOOL_RESULT__ "):
                continue

            payload = line[len("__TOOL_RESULT__ "):].strip()
            result = json.loads(payload)

            if result.get("id") != call_id:
                continue
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Tool call failed"))

            return result.get("result", "")


tools = ToolsProxy()


def _run_user_code():
    """Execute user-provided code."""
''' + indented_code + '''


if __name__ == "__main__":
    try:
        _run_user_code()
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write(f"ERROR: {type(e).__name__}: {e}\\n")
        sys.stderr.flush()
        sys.exit(1)
'''
        return script

    # ===================== Tool execution =====================

    def _execute_tool(self, server: Optional[str], tool_name: str, params: Dict[str, Any]) -> Any:
        # Namespaced invoke if available
        if server and hasattr(self.tools_api, "invoke"):
            result = self.tools_api.invoke(server, tool_name, params)
            if result is not None:
                return result

        tool_fn = getattr(self.tools_api, tool_name, None)
        if tool_fn is None:
            raise ValueError(f"Tool not found: {tool_name}")

        return tool_fn(**params)

    def _handle_tool_call(self, payload: str) -> Dict[str, Any]:
        call_id: Optional[str] = None

        try:
            with self._lock:
                if self._tool_calls_used >= self.max_tool_calls:
                    raise ToolCallLimitExceededError(
                        f"Maximum tool calls exceeded ({self.max_tool_calls})"
                    )

            try:
                message = json.loads(payload)
            except json.JSONDecodeError as e:
                return {"id": None, "ok": False, "error": f"Invalid JSON: {e}"}

            call_id = message.get("id")
            tool_name = message.get("tool")
            server = message.get("server")
            params = message.get("params")

            if not tool_name or not isinstance(tool_name, str):
                return {"id": call_id, "ok": False, "error": "Missing or invalid tool name"}

            if server is not None and not isinstance(server, str):
                return {"id": call_id, "ok": False, "error": "Invalid server identifier"}

            if not self._is_tool_allowed(server, tool_name):
                if server:
                    return {"id": call_id, "ok": False, "error": f"Tool not allowed: {server}::{tool_name}"}
                return {"id": call_id, "ok": False, "error": f"Tool not allowed: {tool_name}"}

            valid, error_msg, clean_params = self._validate_tool_params(params)
            if not valid:
                return {"id": call_id, "ok": False, "error": error_msg}

            with self._lock:
                self._tool_calls_used += 1

            result = self._execute_tool(server, tool_name, clean_params)

            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)

            return {"id": call_id, "ok": True, "result": result}

        except ToolCallLimitExceededError as e:
            return {"id": call_id, "ok": False, "error": str(e)}
        except Exception as e:
            return {"id": call_id, "ok": False, "error": self._sanitize_error_message(f"{type(e).__name__}: {e}")}

    # ===================== Bridge loop =====================

    def _run_bridge_loop(self, container: Any, sock_obj: Any, deadline: float) -> Tuple[str, Optional[str]]:
        buffer = b""
        output_lines: List[str] = []
        error: Optional[str] = None
        total_output_size = 0

        def send_response(line: str) -> None:
            data = (line.rstrip("\n") + "\n").encode("utf-8", errors="replace")
            self._socket_send(sock_obj, data)

        while True:
            if time.time() >= deadline:
                raise ExecutionTimeoutError(f"Execution exceeded {self.timeout}s timeout")

            # Stop if container exited
            try:
                container.reload()
                if container.status in ("exited", "dead"):
                    break
            except Exception:
                pass

            # Read
            try:
                chunk = self._socket_recv(sock_obj, 4096)
                if not chunk:
                    time.sleep(0.02)
                    continue
                buffer += chunk
            except (TimeoutError, socket.timeout, OSError):
                time.sleep(0.02)
                continue
            except Exception:
                time.sleep(0.02)
                continue

            # Process complete lines
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)

                if len(raw_line) > self.max_payload_bytes:
                    error = f"Line too large ({len(raw_line)} > {self.max_payload_bytes} bytes)"
                    self._try_kill_container(container)
                    break

                line = raw_line.decode("utf-8", errors="replace")

                if line.startswith("__TOOL_CALL__ "):
                    payload = line[len("__TOOL_CALL__ "):].strip()
                    reply = self._handle_tool_call(payload)
                    send_response("__TOOL_RESULT__ " + json.dumps(reply, ensure_ascii=False))
                    if not reply.get("ok"):
                        error = reply.get("error", "Tool call failed")
                    continue

                # Ignore accidental echoes
                if line.startswith("__TOOL_RESULT__ "):
                    continue

                if not line.strip():
                    continue

                output_lines.append(line)
                total_output_size += len(line)
                if total_output_size > self.max_output_chars:
                    error = f"Output exceeded {self.max_output_chars} characters"
                    self._try_kill_container(container)
                    break

            if error:
                break

        # Collect logs at end (best-effort)
        try:
            logs = container.logs(stdout=True, stderr=True)
            if logs:
                log_text = logs.decode("utf-8", errors="replace")
                for log_line in log_text.splitlines():
                    if log_line.startswith("__TOOL_CALL__ ") or log_line.startswith("__TOOL_RESULT__ "):
                        continue
                    if log_line.strip():
                        output_lines.append(log_line)
        except Exception:
            pass

        output = "\n".join(line for line in output_lines if line).strip()
        return output, error

    def _try_kill_container(self, container: Any) -> None:
        try:
            container.kill()
        except Exception:
            pass

    # ===================== Container lifecycle =====================

    def _wait_for_container(self, container: Any, max_wait: float = 2.0) -> int:
        start = time.time()
        while time.time() - start < max_wait:
            try:
                result = container.wait(timeout=0.5)
                return int(result.get("StatusCode", 1))
            except Exception:
                time.sleep(0.05)
        try:
            container.reload()
            return int(container.attrs.get("State", {}).get("ExitCode", 1))
        except Exception:
            return 1

    def _get_resource_usage(self, container: Any) -> Optional[Dict[str, Any]]:
        try:
            stats = container.stats(stream=False)
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            memory_stats = stats.get("memory_stats", {})

            cpu_delta = (
                cpu_stats.get("cpu_usage", {}).get("total_usage", 0) -
                precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            )
            system_delta = (
                cpu_stats.get("system_cpu_usage", 0) -
                precpu_stats.get("system_cpu_usage", 0)
            )
            cpu_percent = (cpu_delta / system_delta * 100.0) if system_delta > 0 else 0.0

            memory_usage = memory_stats.get("usage", 0)
            memory_limit = memory_stats.get("limit", 1)
            memory_percent = (memory_usage / memory_limit * 100.0) if memory_limit > 0 else 0.0

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_bytes": int(memory_usage),
                "memory_percent": round(memory_percent, 2),
            }
        except Exception:
            return None

    @contextmanager
    def _managed_temp_dir(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="docker_sandbox_"))
        try:
            yield temp_dir
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    # ===================== Main execution =====================

    def execute(self, code: str) -> DockerExecutionResult:
        start_time = time.time()
        container = None
        sock_obj = None

        with self._lock:
            self._tool_calls_used = 0

        if self.verbose:
            logger.info("=" * 60)
            logger.info("DOCKER SANDBOX EXECUTION")
            logger.info("=" * 60)
            logger.info(f"Code length: {len(code)} chars")
            logger.info(f"Timeout: {self.timeout}s")
            logger.info(f"Image: {self.docker_image}")

        try:
            with self._managed_temp_dir() as temp_dir:
                runner_path = temp_dir / "runner.py"
                runner_path.write_text(self._build_runner_script(code), encoding="utf-8")

                config = self._build_container_config(temp_dir)
                container = self.docker_client.containers.create(**config)

                if self.verbose:
                    logger.info(f"Created container: {container.short_id}")

                # ✅ IMPORTANT (Windows/Docker Desktop): start BEFORE attach_socket
                container.start()

                sock_obj = container.attach_socket(
                    params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1, "logs": 0}
                )
                self._socket_set_timeout(sock_obj, 0.2)

                deadline = start_time + self.timeout
                output, bridge_error = self._run_bridge_loop(container, sock_obj, deadline)

                exit_code = self._wait_for_container(container, max_wait=2.0)
                resource_usage = self._get_resource_usage(container)

                execution_time = time.time() - start_time
                success = (exit_code == 0) and (bridge_error is None)

                return DockerExecutionResult(
                    success=success,
                    output=output if success else "",
                    error=None if success else (bridge_error or output or f"exit_code={exit_code}"),
                    execution_time=execution_time,
                    exit_code=exit_code,
                    container_id=container.short_id,
                    resource_usage=resource_usage,
                    tool_calls_count=self._tool_calls_used,
                )

        except ExecutionTimeoutError as e:
            execution_time = time.time() - start_time
            if container:
                self._try_kill_container(container)
            return DockerExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time=execution_time,
                exit_code=124,
                container_id=container.short_id if container else None,
                tool_calls_count=self._tool_calls_used,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            if container:
                self._try_kill_container(container)
            return DockerExecutionResult(
                success=False,
                output="",
                error=self._sanitize_error_message(f"{type(e).__name__}: {e}"),
                execution_time=execution_time,
                exit_code=1,
                container_id=container.short_id if container else None,
                tool_calls_count=self._tool_calls_used,
            )

        finally:
            if sock_obj:
                self._socket_close(sock_obj)

            if container:
                try:
                    container.remove(force=True)
                    if self.verbose:
                        logger.info(f"Removed container: {container.short_id}")
                except Exception:
                    pass

    def __repr__(self) -> str:
        return (
            f"DockerSandboxExecutor("
            f"image={self.docker_image!r}, "
            f"timeout={self.timeout}, "
            f"network={'enabled' if self.enable_network else 'disabled'})"
        )
