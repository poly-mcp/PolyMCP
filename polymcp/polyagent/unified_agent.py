"""
Unified PolyAgent 
"""

import json
import asyncio
import sys
import re
import time
import uuid
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set, Callable
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import httpx

from .llm_providers import LLMProvider
from ..mcp_stdio_client import MCPStdioClient, MCPStdioAdapter, MCPServerConfig

# Skills System Integration
try:
    from .skill_loader import SkillLoader
    from .skill_matcher import SkillMatcher
    SKILLS_AVAILABLE = True
except ImportError:
    SKILLS_AVAILABLE = False


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class ErrorType(Enum):
    """Error taxonomy for intelligent retry"""
    TRANSIENT = "transient"  # Retry with backoff
    PERMANENT = "permanent"  # Don't retry
    AUTH = "auth"  # Stop immediately
    RATE_LIMIT = "rate_limit"  # Backoff and reduce aggressiveness
    TIMEOUT = "timeout"  # Retry with longer timeout
    SCHEMA = "schema"  # Parameter validation failed
    NOT_FOUND = "not_found"  # Resource doesn't exist
    UNKNOWN = "unknown"


class ToolConstraintType(Enum):
    """Tool constraint types"""
    REQUIRES_PREVIOUS = "requires_previous"  # Needs output from another tool
    MUTEX = "mutex"  # Cannot run with another tool
    SEQUENCE = "sequence"  # Must run in order
    RATE_LIMITED = "rate_limited"  # Has rate limit


class ServerHealth(Enum):
    """Server health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class Budget:
    """Budget limits for agent run"""
    max_wall_time: Optional[float] = 300.0  # 5 minutes
    max_tokens: Optional[int] = 100000
    max_tool_calls: Optional[int] = 20
    max_payload_bytes: Optional[int] = 10 * 1024 * 1024  # 10MB
    
    def __post_init__(self):
        self.start_time = time.time()
        self.tokens_used = 0
        self.tool_calls_made = 0
        self.payload_bytes = 0
    
    def is_exceeded(self) -> Tuple[bool, Optional[str]]:
        """Check if any budget limit is exceeded"""
        if self.max_wall_time and (time.time() - self.start_time) > self.max_wall_time:
            return True, "wall_time"
        if self.max_tokens and self.tokens_used > self.max_tokens:
            return True, "tokens"
        if self.max_tool_calls and self.tool_calls_made >= self.max_tool_calls:
            return True, "tool_calls"
        if self.max_payload_bytes and self.payload_bytes > self.max_payload_bytes:
            return True, "payload"
        return False, None
    
    def add_tokens(self, count: int):
        self.tokens_used += count
    
    def add_tool_call(self):
        self.tool_calls_made += 1
    
    def add_payload(self, size: int):
        self.payload_bytes += size


@dataclass
class ToolMetrics:
    """Metrics for tool execution"""
    tool_name: str
    server_id: str
    success_count: int = 0
    failure_count: int = 0
    total_latency: float = 0.0
    last_success: Optional[float] = None
    last_failure: Optional[float] = None
    consecutive_failures: int = 0
    
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    def avg_latency(self) -> float:
        total = self.success_count + self.failure_count
        return self.total_latency / total if total > 0 else 0.0
    
    def record_success(self, latency: float):
        self.success_count += 1
        self.total_latency += latency
        self.last_success = time.time()
        self.consecutive_failures = 0
    
    def record_failure(self, latency: float):
        self.failure_count += 1
        self.total_latency += latency
        self.last_failure = time.time()
        self.consecutive_failures += 1


@dataclass
class ServerHealthMetrics:
    """Health metrics for server"""
    server_id: str
    health: ServerHealth = ServerHealth.HEALTHY
    consecutive_failures: int = 0
    circuit_opened_at: Optional[float] = None
    circuit_reset_after: float = 300.0  # 5 minutes
    failure_threshold: int = 5
    
    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.health = ServerHealth.CIRCUIT_OPEN
            self.circuit_opened_at = time.time()
    
    def record_success(self):
        self.consecutive_failures = 0
        if self.health == ServerHealth.CIRCUIT_OPEN:
            self.health = ServerHealth.HEALTHY
            self.circuit_opened_at = None
        elif self.health == ServerHealth.UNHEALTHY:
            self.health = ServerHealth.DEGRADED
    
    def can_use(self) -> bool:
        """Check if server can be used"""
        if self.health != ServerHealth.CIRCUIT_OPEN:
            return True
        
        # Check if circuit should be reset
        if self.circuit_opened_at:
            elapsed = time.time() - self.circuit_opened_at
            if elapsed > self.circuit_reset_after:
                self.health = ServerHealth.DEGRADED
                self.circuit_opened_at = None
                return True
        
        return False


@dataclass
class RateLimiter:
    """Rate limiter for tools/servers"""
    max_calls: int
    window_seconds: float
    calls: List[float] = field(default_factory=list)
    
    def can_call(self) -> bool:
        """Check if call is allowed"""
        now = time.time()
        # Remove old calls outside window
        self.calls = [t for t in self.calls if now - t < self.window_seconds]
        return len(self.calls) < self.max_calls
    
    def record_call(self):
        """Record a call"""
        self.calls.append(time.time())
    
    def wait_time(self) -> float:
        """Get time to wait before next call"""
        if self.can_call():
            return 0.0
        
        if not self.calls:
            return 0.0
        
        oldest = min(self.calls)
        return self.window_seconds - (time.time() - oldest)


@dataclass
class AgentResult:
    """Normalized agent result"""
    status: str  # success, error, timeout, cancelled
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    latency: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_success(self) -> bool:
        return self.status == "success"
    
    def is_transient_error(self) -> bool:
        return self.error_type in [ErrorType.TRANSIENT, ErrorType.TIMEOUT, ErrorType.RATE_LIMIT]


@dataclass
class StructuredLog:
    """Structured log entry"""
    timestamp: str
    trace_id: str
    level: str
    event: str
    data: Dict[str, Any]
    
    def to_json(self) -> str:
        return json.dumps({
            'timestamp': self.timestamp,
            'trace_id': self.trace_id,
            'level': self.level,
            'event': self.event,
            'data': self.data
        })


# ============================================================================
# VALIDATORS & SECURITY
# ============================================================================

class SchemaValidator:
    """Schema validator for tool parameters"""
    
    @staticmethod
    def validate_parameters(parameters: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate parameters against schema.
        
        Returns:
            (is_valid, error_message, suggested_fix)
        """
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        
        # Check required parameters
        for req_param in required:
            if req_param not in parameters:
                return False, f"Missing required parameter: {req_param}", {req_param: None}
        
        # Validate each parameter
        for param_name, param_value in parameters.items():
            if param_name not in properties:
                continue
            
            param_schema = properties[param_name]
            expected_type = param_schema.get('type', 'any')
            
            # Type validation
            if expected_type == 'string' and not isinstance(param_value, str):
                return False, f"Parameter '{param_name}' should be string", {param_name: str(param_value)}
            elif expected_type == 'number' and not isinstance(param_value, (int, float)):
                return False, f"Parameter '{param_name}' should be number", {param_name: 0}
            elif expected_type == 'integer' and not isinstance(param_value, int):
                return False, f"Parameter '{param_name}' should be integer", {param_name: int(param_value) if isinstance(param_value, (int, float)) else 0}
            elif expected_type == 'boolean' and not isinstance(param_value, bool):
                return False, f"Parameter '{param_name}' should be boolean", {param_name: bool(param_value)}
            elif expected_type == 'array' and not isinstance(param_value, list):
                return False, f"Parameter '{param_name}' should be array", {param_name: [param_value]}
            elif expected_type == 'object' and not isinstance(param_value, dict):
                return False, f"Parameter '{param_name}' should be object", {param_name: {}}
            
            # Enum validation
            if 'enum' in param_schema:
                if param_value not in param_schema['enum']:
                    return False, f"Parameter '{param_name}' must be one of {param_schema['enum']}", {param_name: param_schema['enum'][0]}
            
            # Range validation for numbers
            if expected_type in ['number', 'integer']:
                if 'minimum' in param_schema and param_value < param_schema['minimum']:
                    return False, f"Parameter '{param_name}' must be >= {param_schema['minimum']}", {param_name: param_schema['minimum']}
                if 'maximum' in param_schema and param_value > param_schema['maximum']:
                    return False, f"Parameter '{param_name}' must be <= {param_schema['maximum']}", {param_name: param_schema['maximum']}
        
        return True, None, None


class SecurityPolicy:
    """Security policy for agent"""
    
    SENSITIVE_PATTERNS = [
        r'password',
        r'token',
        r'secret',
        r'api[_-]?key',
        r'auth',
        r'bearer',
        r'credentials?',
        r'private[_-]?key',
    ]
    
    @staticmethod
    def redact_sensitive_data(data: Any, max_depth: int = 10) -> Any:
        """Redact sensitive data from logs/outputs"""
        if max_depth <= 0:
            return "[MAX_DEPTH_REACHED]"
        
        if isinstance(data, dict):
            redacted = {}
            for key, value in data.items():
                key_lower = str(key).lower()
                # Check if key contains sensitive pattern
                is_sensitive = any(re.search(pattern, key_lower) for pattern in SecurityPolicy.SENSITIVE_PATTERNS)
                
                if is_sensitive:
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = SecurityPolicy.redact_sensitive_data(value, max_depth - 1)
            return redacted
        elif isinstance(data, list):
            return [SecurityPolicy.redact_sensitive_data(item, max_depth - 1) for item in data]
        elif isinstance(data, str):
            # Check for potential tokens (long alphanumeric strings)
            if len(data) > 50 and re.match(r'^[A-Za-z0-9+/=_-]+$', data):
                return "[REDACTED_TOKEN]"
            return data
        else:
            return data
    
    @staticmethod
    def is_tool_allowed(tool_name: str, allowlist: Optional[Set[str]] = None, denylist: Optional[Set[str]] = None) -> bool:
        """Check if tool is allowed by policy"""
        if denylist and tool_name in denylist:
            return False
        if allowlist and tool_name not in allowlist:
            return False
        return True


# ============================================================================
# MAIN AGENT CLASS - Part 1
# ============================================================================

class UnifiedPolyAgent:
    """
    Ultimate PolyAgent with ALL production features.
    
    Features:
    - Async HTTP with httpx
    - stdio tools caching + indexed registry
    - Bounded memory with separation
    - Robust JSON parser
    - Proper base64 detection
    - Readiness check with retry/backoff
    - Smart blocking with idempotent policy
    - Schema validation
    - Budget controller
    - Retry/backoff + error taxonomy
    - Structured observability
    - Planner/Executor/Validator
    - Security & redaction
    - Rate limiting
    - Health checks + circuit breaker
    - And much more!
    """
    
    # System prompts
    PLANNER_SYSTEM = """You are a strategic planner for an AI agent.

Your job: Create a SHORT plan (2-4 steps) to accomplish the user's goal.

RULES:
1. Keep plans SHORT - 2-4 steps maximum
2. Each step should be a clear, atomic action
3. Consider dependencies between steps
4. Be realistic about what's achievable

OUTPUT FORMAT (JSON only):
{
  "plan": [
    {"step": 1, "action": "action description", "tool_hint": "tool_name or null"},
    {"step": 2, "action": "action description", "tool_hint": "tool_name or null"}
  ],
  "reasoning": "why this plan will work"
}"""

    EXECUTOR_SYSTEM = """You are an action executor for an AI agent.

Your job: Select the NEXT BEST tool to execute the current step of the plan.

Available tools:
{tool_descriptions}"""

    VALIDATOR_SYSTEM = """You are a goal validator for an AI agent.

Your job: Determine if the user's goal has been achieved based on the results.

RULES:
1. Be strict - only say "achieved" if the goal is truly complete
2. Consider partial completion
3. Identify what's missing if not achieved

OUTPUT FORMAT (JSON only):
{
  "achieved": true/false,
  "confidence": 0.0-1.0,
  "reason": "explanation",
  "missing": ["what's still needed"] or null
}"""

    FINAL_RESPONSE_SYSTEM = """You are summarizing what an autonomous agent accomplished.

RULES:
1. Use ONLY information from actual tool results
2. DO NOT invent or assume details
3. Be factual and concise
4. If something failed, state it clearly
5. Don't mention technical details
6. Speak naturally

Focus on WHAT was accomplished, not HOW."""
    
    @staticmethod
    def _parse_json_response(llm_response: str) -> Optional[Dict[str, Any]]:
        """Robust JSON parser with fallback"""
        original = llm_response.strip()
        
        # Remove markdown fences
        if "```json" in original:
            parts = original.split("```json")
            if len(parts) > 1:
                original = parts[1].split("```")[0].strip()
        elif "```" in original:
            parts = original.split("```")
            if len(parts) > 1:
                original = parts[1].split("```")[0].strip()
        
        # Find JSON bounds
        start = original.find('{')
        end = original.rfind('}') + 1
        
        if start == -1 or end <= start:
            return None
        
        json_str = original[start:end]
        
        # Try to parse
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Attempt repair: remove trailing commas
            try:
                repaired = re.sub(r',(\s*[}\]])', r'\1', json_str)
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None
    
    @staticmethod
    def _is_likely_base64(text: str, min_length: int = 100) -> bool:
        """Detect if text is likely base64"""
        if len(text) < min_length:
            return False
        base64_pattern = r'^[A-Za-z0-9+/]+=*$'
        return bool(re.match(base64_pattern, text))
    
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (rough approximation)"""
        return len(text) // 4
    
    @staticmethod
    def _generate_trace_id() -> str:
        """Generate unique trace ID"""
        return str(uuid.uuid4())
    
    @staticmethod
    def _generate_server_id(config: Dict[str, Any]) -> str:
        """Generate unique server ID"""
        # Include command + args + env hash for uniqueness
        components = [
            config.get('command', ''),
            str(config.get('args', [])),
            str(sorted((config.get('env', {}) or {}).items()))
        ]
        hash_input = '|'.join(components)
        hash_digest = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"stdio://{config.get('command', 'unknown')}@{hash_digest}"
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_servers: Optional[List[str]] = None,
        stdio_servers: Optional[List[Dict[str, Any]]] = None,
        registry_path: Optional[str] = None,
        verbose: bool = False,
        memory_enabled: bool = True,
        http_headers: Optional[Dict[str, str]] = None,
        skills_enabled: bool = True,
        skills_dir: Optional[Path] = None,
        # Budget settings
        max_wall_time: float = 300.0,
        max_tokens: int = 100000,
        max_tool_calls: int = 20,
        max_payload_bytes: int = 10 * 1024 * 1024,
        # Security settings
        tool_allowlist: Optional[Set[str]] = None,
        tool_denylist: Optional[Set[str]] = None,
        redact_logs: bool = True,
        # Performance settings
        tools_cache_ttl: float = 60.0,
        max_memory_size: int = 50,
        # Retry settings
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        # Rate limiting 
        enable_rate_limiting: bool = True,
        default_rate_limit: int = 10,  # calls per minute
        # Health checks
        enable_health_checks: bool = True,
        circuit_breaker_threshold: int = 5,
        # Observability
        enable_structured_logs: bool = True,
        log_file: Optional[str] = None,
        # Architecture
        use_planner: bool = True,
        use_validator: bool = True,
    ):
        """Initialize ultimate agent with ALL features"""
        self.llm_provider = llm_provider
        self.mcp_servers = mcp_servers or []
        self.stdio_configs = stdio_servers or []
        self.verbose = verbose
        self.memory_enabled = memory_enabled
        self.http_headers = http_headers or {}
        
        # Core components
        self.http_tools_cache = {}
        self.stdio_clients: Dict[str, MCPStdioClient] = {}
        self.stdio_adapters: Dict[str, MCPStdioAdapter] = {}
        
        # Async HTTP client
        self.http_client: Optional[httpx.AsyncClient] = None
        
        # Cache for stdio tools
        self.stdio_tools_cache: Dict[str, Tuple[List[Dict], float]] = {}
        self.tools_cache_ttl = tools_cache_ttl
        
        # Tool registry for fast lookup
        self.tool_registry: Dict[str, List[Dict]] = defaultdict(list)
        
        # Persistent memory with bounds
        self._persistent_history = [] if memory_enabled else None
        self.max_memory_size = max_memory_size
        self._long_term_summary = None
        
        # Budget controller
        self.budget = Budget(
            max_wall_time=max_wall_time,
            max_tokens=max_tokens,
            max_tool_calls=max_tool_calls,
            max_payload_bytes=max_payload_bytes
        )
        
        # Metrics & Health
        self.tool_metrics: Dict[str, ToolMetrics] = {}
        self.server_health: Dict[str, ServerHealthMetrics] = {}
        self.enable_health_checks = enable_health_checks
        self.circuit_breaker_threshold = circuit_breaker_threshold
        
        # Rate limiting
        self.enable_rate_limiting = enable_rate_limiting
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.default_rate_limit = default_rate_limit
        
        # Retry configuration
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        
        # Security
        self.tool_allowlist = tool_allowlist
        self.tool_denylist = tool_denylist
        self.redact_logs = redact_logs
        
        # Observability
        self.enable_structured_logs = enable_structured_logs
        self.log_file = log_file
        self.trace_id = self._generate_trace_id()
        self.structured_logs: List[StructuredLog] = []
        
        if self.log_file:
            logging.basicConfig(
                filename=self.log_file,
                level=logging.INFO,
                format='%(message)s'
            )
        
        # Architecture flags
        self.use_planner = use_planner
        self.use_validator = use_validator
        self.current_plan: Optional[List[Dict]] = None
        
        # Skills System
        self.skills_enabled = skills_enabled and SKILLS_AVAILABLE
        self.skill_loader: Optional[SkillLoader] = None
        self.skill_matcher: Optional[SkillMatcher] = None
        
        if self.skills_enabled:
            try:
                self.skill_loader = SkillLoader(
                    skills_dir=skills_dir or Path.home() / ".polymcp" / "skills",
                    lazy_load=True,
                    verbose=verbose
                )
                
                self.skill_matcher = SkillMatcher(
                    skill_loader=self.skill_loader,
                    use_fuzzy_matching=True,
                    verbose=verbose
                )
                
                if self.verbose:
                    print(f"Skills System enabled ({self.skill_loader.get_total_skills()} skills)")
            except Exception as e:
                if self.verbose:
                    print(f"Skills System initialization failed: {e}")
                self.skills_enabled = False
        
        if registry_path:
            self._load_registry(registry_path)
    
    def _log(self, level: str, event: str, data: Dict[str, Any]):
        """Structured logging"""
        if not self.enable_structured_logs:
            return
        
        # Redact sensitive data if enabled
        if self.redact_logs:
            data = SecurityPolicy.redact_sensitive_data(data)
        
        log_entry = StructuredLog(
            timestamp=datetime.utcnow().isoformat(),
            trace_id=self.trace_id,
            level=level,
            event=event,
            data=data
        )
        
        self.structured_logs.append(log_entry)
        
        if self.log_file:
            logging.info(log_entry.to_json())
        
        if self.verbose and level in ['ERROR', 'WARNING']:
            print(f"[{level}] {event}: {data}")
    
    def _load_registry(self, registry_path: str) -> None:
        """Load servers from registry"""
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry = json.load(f)
                
                http_servers = registry.get('servers', [])
                self.mcp_servers.extend(http_servers)
                
                stdio_servers = registry.get('stdio_servers', [])
                self.stdio_configs.extend(stdio_servers)
                
                self._log('INFO', 'registry_loaded', {
                    'http_servers': len(http_servers),
                    'stdio_servers': len(stdio_servers)
                })
        except Exception as e:
            self._log('ERROR', 'registry_load_failed', {'error': str(e)})
    
    async def start(self) -> None:
        """Start all servers with health checks"""
        # Initialize async HTTP client
        if not self.http_client:
            self.http_client = httpx.AsyncClient(
                timeout=30.0,
                headers=self.http_headers,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
        
        # Start stdio servers
        for config_dict in self.stdio_configs:
            try:
                config = MCPServerConfig(
                    command=config_dict['command'],
                    args=config_dict.get('args', []),
                    env=config_dict.get('env')
                )
                
                client = MCPStdioClient(config)
                await client.start()
                
                adapter = MCPStdioAdapter(client)
                
                # Generate unique server ID
                server_id = self._generate_server_id(config_dict)
                self.stdio_clients[server_id] = client
                self.stdio_adapters[server_id] = adapter
                
                # Initialize health metrics
                if self.enable_health_checks:
                    self.server_health[server_id] = ServerHealthMetrics(
                        server_id=server_id,
                        failure_threshold=self.circuit_breaker_threshold
                    )
                
                # Initialize rate limiter
                if self.enable_rate_limiting:
                    self.rate_limiters[server_id] = RateLimiter(
                        max_calls=self.default_rate_limit,
                        window_seconds=60.0
                    )
                
                tools = await adapter.get_tools()
                self._log('INFO', 'stdio_server_started', {
                    'server_id': server_id,
                    'tools_count': len(tools)
                })
            
            except Exception as e:
                self._log('ERROR', 'stdio_server_start_failed', {
                    'command': config_dict.get('command'),
                    'error': str(e)
                })
        
        # Discover HTTP tools
        await self._discover_http_tools()
        
        # Readiness check with retry/backoff
        if self.stdio_clients or self.mcp_servers:
            await self._wait_for_readiness()
    
    async def _wait_for_readiness(self, max_retries: int = 3, backoff: float = 0.5) -> None:
        """Wait for servers to be ready with exponential backoff"""
        for attempt in range(max_retries):
            all_ready = True
            
            # Check HTTP servers
            for server_url in self.mcp_servers:
                try:
                    list_url = f"{server_url}/list_tools"
                    response = await self.http_client.get(list_url, timeout=5.0)
                    response.raise_for_status()
                except Exception as e:
                    all_ready = False
                    self._log('WARNING', 'http_server_not_ready', {
                        'server_url': server_url,
                        'attempt': attempt + 1,
                        'error': str(e)
                    })
                    break
            
            # Check stdio servers
            for server_id, adapter in self.stdio_adapters.items():
                try:
                    await adapter.get_tools()
                except Exception as e:
                    all_ready = False
                    self._log('WARNING', 'stdio_server_not_ready', {
                        'server_id': server_id,
                        'attempt': attempt + 1,
                        'error': str(e)
                    })
                    break
            
            if all_ready:
                self._log('INFO', 'all_servers_ready', {'attempts': attempt + 1})
                return
            
            if attempt < max_retries - 1:
                wait_time = backoff * (2 ** attempt)
                self._log('INFO', 'readiness_retry', {
                    'attempt': attempt + 1,
                    'wait_time': wait_time
                })
                await asyncio.sleep(wait_time)
        
        self._log('WARNING', 'readiness_timeout', {
            'max_retries': max_retries
        })
    
    async def _discover_http_tools(self) -> None:
        """Discover tools from HTTP servers"""
        for server_url in self.mcp_servers:
            try:
                list_url = f"{server_url}/list_tools"
                response = await self.http_client.get(list_url, timeout=5.0)
                response.raise_for_status()
                
                tools = response.json().get('tools', [])
                self.http_tools_cache[server_url] = tools
                
                # Initialize health metrics
                if self.enable_health_checks and server_url not in self.server_health:
                    self.server_health[server_url] = ServerHealthMetrics(
                        server_id=server_url,
                        failure_threshold=self.circuit_breaker_threshold
                    )
                
                # Initialize rate limiter
                if self.enable_rate_limiting and server_url not in self.rate_limiters:
                    self.rate_limiters[server_url] = RateLimiter(
                        max_calls=self.default_rate_limit,
                        window_seconds=60.0
                    )
                
                # Build tool registry
                for tool in tools:
                    tool_with_meta = tool.copy()
                    tool_with_meta['_server_url'] = server_url
                    tool_with_meta['_server_type'] = 'http'
                    self.tool_registry[tool['name']].append(tool_with_meta)
                    
                    # Initialize tool metrics
                    metric_key = f"{server_url}:{tool['name']}"
                    if metric_key not in self.tool_metrics:
                        self.tool_metrics[metric_key] = ToolMetrics(
                            tool_name=tool['name'],
                            server_id=server_url
                        )
                
                self._log('INFO', 'http_tools_discovered', {
                    'server_url': server_url,
                    'tools_count': len(tools)
                })
            
            except Exception as e:
                self._log('ERROR', 'http_discovery_failed', {
                    'server_url': server_url,
                    'error': str(e)
                })
    
    def _classify_error(self, error: Exception, status_code: Optional[int] = None) -> ErrorType:
        """Classify error for retry strategy"""
        error_str = str(error).lower()
        
        # Timeout errors
        if 'timeout' in error_str or isinstance(error, asyncio.TimeoutError):
            return ErrorType.TIMEOUT
        
        # Rate limit errors
        if status_code == 429 or 'rate limit' in error_str:
            return ErrorType.RATE_LIMIT
        
        # Auth errors
        if status_code in [401, 403] or 'auth' in error_str or 'unauthorized' in error_str:
            return ErrorType.AUTH
        
        # Not found / schema errors
        if status_code == 404 or 'not found' in error_str:
            return ErrorType.NOT_FOUND
        if status_code == 400 or 'schema' in error_str or 'validation' in error_str:
            return ErrorType.SCHEMA
        
        # Transient errors (5xx, connection issues)
        if status_code and status_code >= 500:
            return ErrorType.TRANSIENT
        if any(x in error_str for x in ['connection', 'network', 'refused']):
            return ErrorType.TRANSIENT
        
        return ErrorType.UNKNOWN

    
    async def _execute_tool_with_retry(
        self,
        tool: Dict[str, Any],
        max_retries: Optional[int] = None
    ) -> AgentResult:
        """
        Execute tool with retry logic and error taxonomy.
        """
        if max_retries is None:
            max_retries = self.max_retries
        
        server_url = tool.get('_server_url')
        tool_name = tool.get('name')
        parameters = tool.get('_parameters', {})
        metric_key = f"{server_url}:{tool_name}"
        
        # Check budget
        exceeded, limit_type = self.budget.is_exceeded()
        if exceeded:
            self._log('WARNING', 'budget_exceeded', {
                'limit_type': limit_type,
                'tool': tool_name
            })
            return AgentResult(
                status="error",
                error=f"Budget exceeded: {limit_type}",
                error_type=ErrorType.PERMANENT
            )
        
        # Check security policy
        if not SecurityPolicy.is_tool_allowed(tool_name, self.tool_allowlist, self.tool_denylist):
            self._log('WARNING', 'tool_blocked_by_policy', {
                'tool': tool_name
            })
            return AgentResult(
                status="error",
                error=f"Tool blocked by security policy",
                error_type=ErrorType.PERMANENT
            )
        
        # Check health
        if self.enable_health_checks and server_url in self.server_health:
            health = self.server_health[server_url]
            if not health.can_use():
                self._log('WARNING', 'server_circuit_open', {
                    'server': server_url,
                    'tool': tool_name
                })
                return AgentResult(
                    status="error",
                    error="Server circuit breaker open",
                    error_type=ErrorType.TRANSIENT
                )
        
        # Check rate limit
        if self.enable_rate_limiting and server_url in self.rate_limiters:
            limiter = self.rate_limiters[server_url]
            if not limiter.can_call():
                wait_time = limiter.wait_time()
                self._log('WARNING', 'rate_limit_hit', {
                    'server': server_url,
                    'tool': tool_name,
                    'wait_time': wait_time
                })
                return AgentResult(
                    status="error",
                    error=f"Rate limit exceeded, wait {wait_time:.1f}s",
                    error_type=ErrorType.RATE_LIMIT
                )
        
        # Schema validation
        schema = tool.get('input_schema', {})
        is_valid, error_msg, suggested_fix = SchemaValidator.validate_parameters(parameters, schema)
        
        if not is_valid:
            self._log('WARNING', 'schema_validation_failed', {
                'tool': tool_name,
                'error': error_msg,
                'parameters': parameters,
                'suggested_fix': suggested_fix
            })
            
            # Try to repair parameters
            if suggested_fix:
                self._log('INFO', 'attempting_parameter_repair', {
                    'tool': tool_name,
                    'original': parameters,
                    'fix': suggested_fix
                })
                parameters.update(suggested_fix)
                # Re-validate
                is_valid, error_msg, _ = SchemaValidator.validate_parameters(parameters, schema)
                if not is_valid:
                    return AgentResult(
                        status="error",
                        error=f"Schema validation failed: {error_msg}",
                        error_type=ErrorType.SCHEMA
                    )
        
        # Retry loop
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                
                # Execute based on server type
                result = await self._execute_tool_internal(tool, parameters)
                
                latency = time.time() - start_time
                
                # Record success metrics
                if metric_key in self.tool_metrics:
                    self.tool_metrics[metric_key].record_success(latency)
                
                if self.enable_health_checks and server_url in self.server_health:
                    self.server_health[server_url].record_success()
                
                if self.enable_rate_limiting and server_url in self.rate_limiters:
                    self.rate_limiters[server_url].record_call()
                
                # Update budget
                self.budget.add_tool_call()
                result_size = len(json.dumps(result, default=str))
                self.budget.add_payload(result_size)
                
                self._log('INFO', 'tool_execution_success', {
                    'tool': tool_name,
                    'server': server_url,
                    'latency': latency,
                    'attempt': attempt + 1
                })
                
                return AgentResult(
                    status="success",
                    result=result,
                    latency=latency,
                    metadata={'attempt': attempt + 1}
                )
            
            except Exception as e:
                latency = time.time() - start_time
                last_error = e
                
                # Classify error
                status_code = getattr(e, 'status_code', None) if hasattr(e, 'status_code') else None
                error_type = self._classify_error(e, status_code)
                
                # Record failure metrics
                if metric_key in self.tool_metrics:
                    self.tool_metrics[metric_key].record_failure(latency)
                
                if self.enable_health_checks and server_url in self.server_health:
                    self.server_health[server_url].record_failure()
                
                self._log('ERROR', 'tool_execution_failed', {
                    'tool': tool_name,
                    'server': server_url,
                    'error': str(e),
                    'error_type': error_type.value,
                    'attempt': attempt + 1,
                    'latency': latency
                })
                
                # Don't retry on permanent errors
                if error_type in [ErrorType.PERMANENT, ErrorType.AUTH, ErrorType.SCHEMA]:
                    return AgentResult(
                        status="error",
                        error=str(e),
                        error_type=error_type,
                        latency=latency
                    )
                
                # Retry on transient errors
                if attempt < max_retries:
                    # Calculate backoff with jitter
                    wait_time = self.retry_backoff * (2 ** attempt)
                    jitter = wait_time * 0.1 * (2 * (hash(str(e)) % 100) / 100 - 1)
                    wait_time += jitter
                    
                    self._log('INFO', 'tool_execution_retry', {
                        'tool': tool_name,
                        'attempt': attempt + 2,
                        'wait_time': wait_time
                    })
                    
                    await asyncio.sleep(wait_time)
                    continue
        
        # All retries exhausted
        return AgentResult(
            status="error",
            error=str(last_error),
            error_type=self._classify_error(last_error),
            latency=latency
        )
    
    async def _execute_tool_internal(self, tool: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Internal tool execution"""
        server_url = tool.get('_server_url')
        server_type = tool.get('_server_type')
        tool_name = tool.get('name')
        
        if server_type == 'http':
            invoke_url = f"{server_url}/invoke/{tool_name}"
            response = await self.http_client.post(
                invoke_url,
                json=parameters,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        
        elif server_type == 'stdio':
            adapter = self.stdio_adapters.get(server_url)
            if not adapter:
                raise ValueError(f"Stdio adapter not found: {server_url}")
            
            result = await adapter.invoke_tool(tool_name, parameters)
            return result
        
        else:
            raise ValueError(f"Unknown server type: {server_type}")
    
    def _compress_tool_output(self, result: Dict[str, Any], max_size: int = 2000) -> Dict[str, Any]:
        """
        Compress/summarize tool output.
        
        Pipeline:
        1. Hard truncation for large payloads
        2. Extract key fields
        3. Summarization (if needed)
        """
        result_str = json.dumps(result, default=str)
        
        if len(result_str) <= max_size:
            return result
        
        compressed = {}
        
        # Extract key fields
        if isinstance(result, dict):
            # Priority fields to keep
            priority_fields = ['status', 'success', 'error', 'message', 'data', 'result']
            
            for field in priority_fields:
                if field in result:
                    value = result[field]
                    
                    if isinstance(value, str):
                        # Detect and truncate base64
                        if self._is_likely_base64(value):
                            compressed[field] = "[base64_data_truncated]"
                        elif len(value) > 500:
                            compressed[field] = value[:500] + "..."
                        else:
                            compressed[field] = value
                    elif isinstance(value, list):
                        if len(value) > 10:
                            compressed[field] = value[:10] + [f"... +{len(value)-10} more"]
                        else:
                            compressed[field] = value
                    elif isinstance(value, dict):
                        nested_str = json.dumps(value, default=str)
                        if len(nested_str) > 500:
                            compressed[field] = "[object_truncated]"
                        else:
                            compressed[field] = value
                    else:
                        compressed[field] = value
            
            # Add truncation marker
            compressed['_compressed'] = True
            compressed['_original_size'] = len(result_str)
            
            return compressed
        
        return result
    
    async def _refresh_stdio_tools_cache(self) -> None:
        """Refresh stdio tools cache if stale"""
        current_time = time.time()
        
        for server_id, adapter in self.stdio_adapters.items():
            # Check if cache is stale
            if server_id in self.stdio_tools_cache:
                cached_tools, timestamp = self.stdio_tools_cache[server_id]
                if current_time - timestamp < self.tools_cache_ttl:
                    continue
            
            # Fetch and cache tools
            try:
                tools = await adapter.get_tools()
                self.stdio_tools_cache[server_id] = (tools, current_time)
                
                # Update tool registry
                for tool in tools:
                    tool_with_meta = tool.copy()
                    tool_with_meta['_server_url'] = server_id
                    tool_with_meta['_server_type'] = 'stdio'
                    
                    if tool_with_meta not in self.tool_registry[tool['name']]:
                        self.tool_registry[tool['name']].append(tool_with_meta)
                    
                    # Initialize tool metrics
                    metric_key = f"{server_id}:{tool['name']}"
                    if metric_key not in self.tool_metrics:
                        self.tool_metrics[metric_key] = ToolMetrics(
                            tool_name=tool['name'],
                            server_id=server_id
                        )
            except Exception as e:
                self._log('ERROR', 'stdio_cache_refresh_failed', {
                    'server_id': server_id,
                    'error': str(e)
                })
    
    async def _get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all tools from both HTTP and stdio servers"""
        all_tools = []
        tools_seen: Set[Tuple[str, str]] = set()
        
        # HTTP tools from cache
        for server_url, tools in self.http_tools_cache.items():
            # Check health before including
            if self.enable_health_checks and server_url in self.server_health:
                if not self.server_health[server_url].can_use():
                    continue
            
            for tool in tools:
                dedup_key = (server_url, tool['name'])
                if dedup_key in tools_seen:
                    continue
                tools_seen.add(dedup_key)
                
                tool_with_server = tool.copy()
                tool_with_server['_server_url'] = server_url
                tool_with_server['_server_type'] = 'http'
                
                # Add metrics info
                metric_key = f"{server_url}:{tool['name']}"
                if metric_key in self.tool_metrics:
                    metrics = self.tool_metrics[metric_key]
                    tool_with_server['_success_rate'] = metrics.success_rate()
                    tool_with_server['_avg_latency'] = metrics.avg_latency()
                
                all_tools.append(tool_with_server)
        
        # Stdio tools from cache
        await self._refresh_stdio_tools_cache()
        
        for server_id, (tools, _) in self.stdio_tools_cache.items():
            # Check health before including
            if self.enable_health_checks and server_id in self.server_health:
                if not self.server_health[server_id].can_use():
                    continue
            
            for tool in tools:
                dedup_key = (server_id, tool['name'])
                if dedup_key in tools_seen:
                    continue
                tools_seen.add(dedup_key)
                
                tool_with_server = tool.copy()
                tool_with_server['_server_url'] = server_id
                tool_with_server['_server_type'] = 'stdio'
                
                # Add metrics info
                metric_key = f"{server_id}:{tool['name']}"
                if metric_key in self.tool_metrics:
                    metrics = self.tool_metrics[metric_key]
                    tool_with_server['_success_rate'] = metrics.success_rate()
                    tool_with_server['_avg_latency'] = metrics.avg_latency()
                
                all_tools.append(tool_with_server)
        
        # Sort by success rate and latency
        all_tools.sort(
            key=lambda t: (t.get('_success_rate', 0.5), -t.get('_avg_latency', 999)),
            reverse=True
        )
        
        return all_tools

    
    async def _create_plan(self, user_message: str) -> Optional[List[Dict]]:
        """Create execution plan"""
        if not self.use_planner:
            return None
        
        prompt = f"""{self.PLANNER_SYSTEM}

USER REQUEST: "{user_message}"

Create a SHORT plan (2-4 steps) to accomplish this goal.

JSON only:"""
        
        try:
            llm_response = self.llm_provider.generate(prompt).strip()
            parsed = self._parse_json_response(llm_response)
            
            if parsed and 'plan' in parsed:
                plan = parsed['plan']
                self._log('INFO', 'plan_created', {
                    'steps': len(plan),
                    'plan': plan
                })
                return plan
            
            return None
        except Exception as e:
            self._log('ERROR', 'planning_failed', {'error': str(e)})
            return None
    
    async def _validate_goal_achieved(
        self,
        user_message: str,
        action_history: List[Dict]
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Validate if goal is achieved.
        
        Returns:
            (achieved, confidence, reason)
        """
        if not self.use_validator or not action_history:
            return False, 0.0, None
        
        # Extract recent results
        results_summary = []
        for action in action_history[-5:]:
            result = action['result']
            status = "success" if result.status == "success" else "failed"
            tool = action['tool']
            results_summary.append(f"- {tool}: {status}")
        
        results_text = "\n".join(results_summary)
        
        prompt = f"""{self.VALIDATOR_SYSTEM}

USER'S GOAL: "{user_message}"

WHAT WAS DONE:
{results_text}

DECISION: Has the goal been achieved?

JSON only:"""
        
        try:
            llm_response = self.llm_provider.generate(prompt).strip()
            parsed = self._parse_json_response(llm_response)
            
            if not parsed:
                return False, 0.0, None
            
            achieved = parsed.get('achieved', False)
            confidence = parsed.get('confidence', 0.5)
            reason = parsed.get('reason', '')
            
            self._log('INFO', 'validation_result', {
                'achieved': achieved,
                'confidence': confidence,
                'reason': reason
            })
            
            return achieved, confidence, reason
        
        except Exception as e:
            self._log('ERROR', 'validation_failed', {'error': str(e)})
            return False, 0.0, None
    
    def _should_stop(
        self,
        action_history: List[Dict],
        user_message: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Smart stop conditions.
        
        Stop when:
        - Budget exceeded
        - Goal achieved (validator)
        - Stalled (no progress)
        - Semantic repetition
        - Consecutive failures
        """
        # Budget check
        exceeded, limit_type = self.budget.is_exceeded()
        if exceeded:
            return True, f"Budget exceeded: {limit_type}"
        
        if not action_history:
            return False, None
        
        # Consecutive failures
        consecutive_failures = 0
        for action in reversed(action_history):
            if not action['result'].is_success():
                consecutive_failures += 1
            else:
                break
        
        if consecutive_failures >= 3:
            return True, f"{consecutive_failures} consecutive failures"
        
        # Stall detection (no state change)
        if len(action_history) >= 3:
            last_three_results = [
                json.dumps(a['result'].result, default=str, sort_keys=True)
                for a in action_history[-3:]
                if a['result'].is_success()
            ]
            
            if len(last_three_results) == 3 and len(set(last_three_results)) == 1:
                return True, "Stalled: no state change in last 3 steps"
        
        # Semantic repetition (same info obtained)
        if len(action_history) >= 4:
            last_four_tools = [a['tool'] for a in action_history[-4:]]
            # Check if same tool repeated with different params but similar results
            tool_counts = {}
            for tool in last_four_tools:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
            
            if any(count >= 3 for count in tool_counts.values()):
                return True, "Semantic repetition: same tool repeated excessively"
        
        return False, None
    
    def _select_tool_with_constraints(
        self,
        all_tools: List[Dict],
        action_history: List[Dict],
        plan_step: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Select tool with constraint checking.
        
        Constraints:
        - Requires previous tool output
        - Mutex (cannot run with another tool)
        - Rate limiting
        - Health status
        """
        # Tool constraints mapping (can be extended)
        tool_constraints = {
            # Example: click requires snapshot first
            'playwright_click': {
                'requires': ['playwright_snapshot'],
                'description': 'Needs element references from snapshot'
            },
            'playwright_fill': {
                'requires': ['playwright_snapshot'],
                'description': 'Needs element references from snapshot'
            }
        }
        
        # Filter tools based on constraints
        valid_tools = []
        
        for tool in all_tools:
            tool_name = tool['name']
            
            # Check if tool has constraints
            if tool_name in tool_constraints:
                constraints = tool_constraints[tool_name]
                requires = constraints.get('requires', [])
                
                # Check if required tools have been executed
                executed_tools = {a['tool'] for a in action_history}
                if not all(req in executed_tools for req in requires):
                    continue
            
            # Check rate limiting
            server_url = tool.get('_server_url')
            if self.enable_rate_limiting and server_url in self.rate_limiters:
                limiter = self.rate_limiters[server_url]
                if not limiter.can_call():
                    continue
            
            # Check health
            if self.enable_health_checks and server_url in self.server_health:
                if not self.server_health[server_url].can_use():
                    continue
            
            valid_tools.append(tool)
        
        if not valid_tools:
            return None
        
        # If we have a plan step with tool hint, prefer that tool
        if plan_step and plan_step.get('tool_hint'):
            hint = plan_step['tool_hint']
            for tool in valid_tools:
                if tool['name'] == hint:
                    return tool
        
        # Otherwise, select best tool based on metrics
        # Already sorted by success rate and latency
        return valid_tools[0] if valid_tools else None
    
    def _extract_previous_results(self, action_history: List[Dict]) -> str:
        """Extract previous results"""
        if not action_history:
            return "No previous results available."
        
        results_text = []
        
        for action in reversed(action_history[-5:]):
            if not action['result'].is_success():
                continue
            
            tool_name = action['tool']
            result_data = action['result'].result or {}
            
            # Compress result
            compressed = self._compress_tool_output(result_data, max_size=500)
            
            result_str = json.dumps(compressed, default=str)
            results_text.append(f"\nResult from '{tool_name}':\n  {result_str}")
        
        if results_text:
            return "PREVIOUS TOOL RESULTS:\n" + "\n---\n".join(results_text)
        else:
            return "Previous actions completed but no detailed output available."
    
    def _generate_final_response(self, user_message: str, action_history: List[Dict]) -> str:
        """Generate final response"""
        if not action_history:
            return "I couldn't find any suitable tools to complete your request."
        
        results_data = []
        
        for action in action_history:
            result = action['result']
            step_num = action['step']
            tool_name = action['tool']
            
            if result.is_success():
                # Compress result for summary
                compressed = self._compress_tool_output(result.result or {}, max_size=300)
                result_str = json.dumps(compressed, default=str)
                results_data.append(f"Step {step_num} ({tool_name}): {result_str}")
            else:
                error = result.error or 'Unknown error'
                results_data.append(f"Step {step_num} ({tool_name}): FAILED - {error}")
        
        results_text = "\n\n".join(results_data)
        success_count = sum(1 for a in action_history if a['result'].is_success())
        
        prompt = f"""{self.FINAL_RESPONSE_SYSTEM}

USER'S REQUEST: "{user_message}"

WHAT HAPPENED:
{results_text}

Summary: {success_count}/{len(action_history)} actions successful.

Write a natural response about what was accomplished.

Response:"""
        
        try:
            response = self.llm_provider.generate(prompt)
            return response.strip()
        except Exception as e:
            self._log('ERROR', 'response_generation_failed', {'error': str(e)})
            return f"Completed {success_count}/{len(action_history)} actions."
    
    async def run_async(
        self,
        user_message: str,
        max_steps: int = 10,
        stream_callback: Optional[Callable[[Dict], None]] = None
    ) -> str:
        """
        Main execution loop with ALL features.
        
        Args:
            user_message: User's request
            max_steps: Maximum number of steps
            stream_callback: Optional callback for streaming progress
        
        Returns:
            Final response
        """
        # Reset trace ID for new run
        self.trace_id = self._generate_trace_id()
        
        # Reset budget
        self.budget = Budget(
            max_wall_time=self.budget.max_wall_time,
            max_tokens=self.budget.max_tokens,
            max_tool_calls=max_steps,  # Use max_steps as limit
            max_payload_bytes=self.budget.max_payload_bytes
        )
        
        self._log('INFO', 'run_started', {
            'user_message': user_message,
            'max_steps': max_steps
        })
        
        # Stream initial status
        if stream_callback:
            stream_callback({'event': 'start', 'message': user_message})
        
        # Load persistent history
        action_history = []
        if self.memory_enabled and self._persistent_history:
            action_history = self._persistent_history.copy()
            self._log('INFO', 'memory_loaded', {
                'actions_count': len(action_history)
            })
        
        initial_length = len(action_history)
        
        # Create plan
        if self.use_planner:
            self.current_plan = await self._create_plan(user_message)
            if self.current_plan and stream_callback:
                stream_callback({
                    'event': 'plan_created',
                    'plan': self.current_plan
                })
        
        # Main execution loop
        for step in range(max_steps):
            current_step = len(action_history) + 1
            
            self._log('INFO', 'step_started', {
                'step': current_step,
                'iteration': step + 1
            })
            
            if stream_callback:
                stream_callback({
                    'event': 'step_start',
                    'step': current_step
                })
            
            # Check if should stop
            should_stop, stop_reason = self._should_stop(action_history, user_message)
            if should_stop:
                self._log('INFO', 'execution_stopped', {
                    'reason': stop_reason,
                    'step': current_step
                })
                if stream_callback:
                    stream_callback({
                        'event': 'stopped',
                        'reason': stop_reason
                    })
                break
            
            # Validate goal
            if self.use_validator and step > 0:
                achieved, confidence, reason = await self._validate_goal_achieved(
                    user_message,
                    action_history
                )
                
                if achieved and confidence > 0.7:
                    self._log('INFO', 'goal_achieved', {
                        'confidence': confidence,
                        'reason': reason
                    })
                    if stream_callback:
                        stream_callback({
                            'event': 'goal_achieved',
                            'confidence': confidence
                        })
                    break
            
            # Get relevant tools
            if self.skills_enabled:
                all_tools = await self._get_relevant_tools(user_message, max_tools=15)
            else:
                all_tools = await self._get_all_tools()
            
            if not all_tools:
                self._log('WARNING', 'no_tools_available', {})
                break
            
            # Get plan step if available
            plan_step = None
            if self.current_plan and step < len(self.current_plan):
                plan_step = self.current_plan[step]
            
            # Select tool with constraints
            selected_tool = self._select_tool_with_constraints(
                all_tools,
                action_history,
                plan_step
            )
            
            if not selected_tool:
                self._log('WARNING', 'no_tool_selected', {})
                break
            
            # Add placeholder parameters (will be filled by LLM)
            # For now, use empty dict - in full implementation, use LLM to generate params
            selected_tool['_parameters'] = {}
            
            self._log('INFO', 'tool_selected', {
                'tool': selected_tool['name'],
                'server': selected_tool['_server_url']
            })
            
            if stream_callback:
                stream_callback({
                    'event': 'tool_selected',
                    'tool': selected_tool['name']
                })
            
            # Execute tool with retry
            result = await self._execute_tool_with_retry(selected_tool)
            
            if stream_callback:
                stream_callback({
                    'event': 'tool_executed',
                    'tool': selected_tool['name'],
                    'status': result.status
                })
            
            # Save to history
            action_history.append({
                'step': current_step,
                'tool': selected_tool['name'],
                'parameters': selected_tool.get('_parameters', {}),
                'result': result
            })
            
            # Pause between actions
            await asyncio.sleep(0.5)
        
        # Update persistent memory with bounds
        if self.memory_enabled:
            if len(action_history) > self.max_memory_size:
                old_actions = action_history[:-self.max_memory_size]
                if self._long_term_summary is None and old_actions:
                    self._long_term_summary = f"Previous {len(old_actions)} actions completed"
                
                self._persistent_history = action_history[-self.max_memory_size:]
            else:
                self._persistent_history = action_history
        
        # Generate final response
        new_actions = action_history[initial_length:]
        response = self._generate_final_response(user_message, new_actions)
        
        self._log('INFO', 'run_completed', {
            'actions_executed': len(new_actions),
            'success_rate': sum(1 for a in new_actions if a['result'].is_success()) / len(new_actions) if new_actions else 0
        })
        
        if stream_callback:
            stream_callback({
                'event': 'completed',
                'response': response
            })
        
        return response

    
    async def _get_relevant_tools(self, query: str, max_tools: int = 10) -> List[Dict[str, Any]]:
        """Get relevant tools using Skills System"""
        if not self.skills_enabled or not self.skill_matcher:
            return await self._get_all_tools()
        
        try:
            relevant_skills = self.skill_matcher.match_query(query, top_k=max_tools)
            
            self._log('INFO', 'skills_matched', {
                'count': len(relevant_skills)
            })
            
            # Refresh stdio cache
            await self._refresh_stdio_tools_cache()
            
            relevant_tools = []
            tools_seen: Set[Tuple[str, str]] = set()
            
            for skill, confidence in relevant_skills:
                try:
                    full_skill = self.skill_loader.load_skill(skill.category)
                    
                    if full_skill and full_skill.tools:
                        for tool_info in full_skill.tools:
                            tool_name = tool_info.get('name') if isinstance(tool_info, dict) else str(tool_info)
                            
                            if tool_name in self.tool_registry:
                                for tool_instance in self.tool_registry[tool_name]:
                                    server_id = tool_instance['_server_url']
                                    dedup_key = (server_id, tool_name)
                                    
                                    if dedup_key in tools_seen:
                                        continue
                                    tools_seen.add(dedup_key)
                                    
                                    tool_with_conf = tool_instance.copy()
                                    tool_with_conf['_skill_confidence'] = confidence
                                    relevant_tools.append(tool_with_conf)
                
                except Exception as e:
                    self._log('ERROR', 'skill_load_failed', {
                        'skill': skill.name,
                        'error': str(e)
                    })
            
            if relevant_tools:
                return relevant_tools
            else:
                return await self._get_all_tools()
        
        except Exception as e:
            self._log('ERROR', 'skills_matching_failed', {'error': str(e)})
            return await self._get_all_tools()
    
    def run(self, user_message: str) -> str:
        """Sync wrapper for run_async"""
        return asyncio.run(self._run_sync_wrapper(user_message))
    
    async def _run_sync_wrapper(self, user_message: str) -> str:
        """Internal sync wrapper"""
        if not self.stdio_clients:
            await self.start()
        return await self.run_async(user_message)
    
    def reset_memory(self):
        """Reset persistent memory"""
        if self.memory_enabled:
            self._persistent_history = []
            self._long_term_summary = None
            self._log('INFO', 'memory_reset', {})
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive metrics.
        
        Returns:
            Dictionary with all metrics
        """
        # Tool metrics
        tool_stats = []
        for metric_key, metrics in self.tool_metrics.items():
            tool_stats.append({
                'key': metric_key,
                'tool': metrics.tool_name,
                'server': metrics.server_id,
                'success_count': metrics.success_count,
                'failure_count': metrics.failure_count,
                'success_rate': metrics.success_rate(),
                'avg_latency': metrics.avg_latency(),
                'consecutive_failures': metrics.consecutive_failures
            })
        
        # Server health
        health_stats = []
        for server_id, health in self.server_health.items():
            health_stats.append({
                'server_id': server_id,
                'health': health.health.value,
                'consecutive_failures': health.consecutive_failures,
                'circuit_open': health.health == ServerHealth.CIRCUIT_OPEN
            })
        
        # Budget stats
        budget_stats = {
            'tokens_used': self.budget.tokens_used,
            'tool_calls_made': self.budget.tool_calls_made,
            'payload_bytes': self.budget.payload_bytes,
            'elapsed_time': time.time() - self.budget.start_time if hasattr(self.budget, 'start_time') else 0
        }
        
        return {
            'tools': tool_stats,
            'servers': health_stats,
            'budget': budget_stats,
            'trace_id': self.trace_id
        }
    
    def export_logs(self, format: str = 'json') -> str:
        """
        Export structured logs.
        
        Args:
            format: 'json' or 'text'
        
        Returns:
            Formatted logs
        """
        if format == 'json':
            logs_data = [asdict(log) for log in self.structured_logs]
            return json.dumps(logs_data, indent=2)
        elif format == 'text':
            lines = []
            for log in self.structured_logs:
                lines.append(f"[{log.timestamp}] [{log.level}] {log.event}: {log.data}")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def save_test_trace(self, filepath: str):
        """
        Save test trace for replay.
        
        Saves:
        - User message
        - Tool calls
        - Results
        - Trace ID
        """
        trace_data = {
            'trace_id': self.trace_id,
            'logs': [asdict(log) for log in self.structured_logs],
            'metrics': self.get_metrics()
        }
        
        with open(filepath, 'w') as f:
            json.dump(trace_data, f, indent=2)
        
        self._log('INFO', 'trace_saved', {'filepath': filepath})
    
    async def stop(self) -> None:
        """Stop all servers and cleanup"""
        self._log('INFO', 'agent_stopping', {})
        
        # Stop stdio servers
        for client in self.stdio_clients.values():
            try:
                await client.stop()
            except Exception as e:
                self._log('ERROR', 'stdio_stop_failed', {'error': str(e)})
        
        # Close HTTP client
        if self.http_client:
            try:
                await self.http_client.aclose()
            except Exception as e:
                self._log('ERROR', 'http_client_close_failed', {'error': str(e)})
            finally:
                self.http_client = None
        
        # Clear caches
        self.stdio_clients.clear()
        self.stdio_adapters.clear()
        self.stdio_tools_cache.clear()
        self.tool_registry.clear()
        
        self._log('INFO', 'agent_stopped', {})
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with proper cleanup"""
        try:
            await self.stop()
        except Exception as e:
            self._log('ERROR', 'context_exit_failed', {'error': str(e)})
        
        if sys.platform == "win32":
            await asyncio.sleep(0.2)
        
        # Don't suppress exceptions
        return False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_test_harness(agent: UnifiedPolyAgentUltimate):
    """
    Create test harness for agent.
    
    Usage:
        harness = create_test_harness(agent)
        result = await harness.run_test({
            'input': 'test query',
            'expected_tools': ['tool1', 'tool2'],
            'expected_status': 'success'
        })
    """
    class TestHarness:
        def __init__(self, agent):
            self.agent = agent
            self.test_results = []
        
        async def run_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
            """Run a single test case"""
            input_msg = test_case['input']
            expected_tools = test_case.get('expected_tools', [])
            expected_status = test_case.get('expected_status', 'success')
            
            # Run agent
            try:
                response = await self.agent.run_async(input_msg)
                
                # Check if expected tools were used
                history = self.agent._persistent_history or []
                used_tools = [a['tool'] for a in history]
                
                tools_match = all(tool in used_tools for tool in expected_tools)
                
                result = {
                    'input': input_msg,
                    'response': response,
                    'used_tools': used_tools,
                    'expected_tools': expected_tools,
                    'tools_match': tools_match,
                    'status': 'pass' if tools_match else 'fail'
                }
                
                self.test_results.append(result)
                return result
            
            except Exception as e:
                result = {
                    'input': input_msg,
                    'error': str(e),
                    'status': 'error'
                }
                self.test_results.append(result)
                return result
        
        def get_summary(self) -> Dict[str, Any]:
            """Get test summary"""
            total = len(self.test_results)
            passed = sum(1 for r in self.test_results if r['status'] == 'pass')
            failed = sum(1 for r in self.test_results if r['status'] == 'fail')
            errors = sum(1 for r in self.test_results if r['status'] == 'error')
            
            return {
                'total': total,
                'passed': passed,
                'failed': failed,
                'errors': errors,
                'success_rate': passed / total if total > 0 else 0
            }
    
    return TestHarness(agent)
