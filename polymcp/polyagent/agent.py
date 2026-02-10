"""
PolyAgent - Simple Single-Shot Agent
For autonomous multi-step execution with enterprise features, use UnifiedPolyAgent.
"""

import json
from typing import List, Dict, Any, Optional, Iterable

import requests

from .llm_providers import LLMProvider
from .mcp_url import MCPBaseURL
from .tool_normalize import normalize_tool_metadata
from .auth_base import AuthProvider
from .skills_sh import build_skills_context, load_skills_sh


class PolyAgent:
    """
    Simple agent for single tool execution.
    
    Features:
    - Single tool selection + execution
    - Pluggable auth (OAuth2/JWT/API key)
    - Automatic retry on 401/403
    - Connection pooling
    
    For multi-step autonomous execution, use UnifiedPolyAgent instead.
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_servers: Optional[List[str]] = None,
        registry_path: Optional[str] = None,
        auth_provider: Optional[AuthProvider] = None,
        http_headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        verbose: bool = False,
        skills_sh_enabled: bool = True,
        skills_sh_dirs: Optional[Iterable[str]] = None,
        skills_sh_max_skills: int = 4,
        skills_sh_max_chars: int = 5000,
    ):
        """
        Initialize PolyAgent.
        
        Args:
            llm_provider: LLM for tool selection
            mcp_servers: List of MCP server URLs
            registry_path: Path to server registry JSON
            auth_provider: Authentication provider
            http_headers: Additional HTTP headers
            timeout: Request timeout (seconds)
            verbose: Enable logging
        """
        self.llm = llm_provider
        self.auth = auth_provider
        self.timeout = float(timeout)
        self.verbose = verbose

        # skills.sh integration
        self.skills_sh_enabled = bool(skills_sh_enabled)
        self.skills_sh_dirs = list(skills_sh_dirs) if skills_sh_dirs else None
        self.skills_sh_max_skills = int(skills_sh_max_skills)
        self.skills_sh_max_chars = int(skills_sh_max_chars)
        self._skills_sh_entries = load_skills_sh(self.skills_sh_dirs) if self.skills_sh_enabled else []
        self._skills_sh_warning_shown = False
        if self.skills_sh_enabled and not self._skills_sh_entries:
            self._warn_missing_project_skills()
        
        # HTTP session for connection pooling
        self.session = requests.Session()
        if http_headers:
            self.session.headers.update(http_headers)
        
        # Storage
        self.servers: List[str] = []
        self.tools: Dict[str, List[Dict[str, Any]]] = {}
        
        # Add servers
        if mcp_servers:
            for url in mcp_servers:
                self.add_server(url)
        
        if registry_path:
            self._load_registry(registry_path)
        
        # Discover tools
        self._discover_all()

    def _warn_missing_project_skills(self) -> None:
        if self._skills_sh_warning_shown:
            return
        print("[WARN] No project skills found in .agents/skills or .skills.")
        print("Use global skills: polymcp skills add vercel-labs/agent-skills -g")
        print("Or local skills: polymcp skills add vercel-labs/agent-skills")
        self._skills_sh_warning_shown = True
    
    def _load_registry(self, path: str) -> None:
        """Load servers from JSON registry."""
        try:
            with open(path) as f:
                data = json.load(f)
            for url in data.get("servers", []):
                self.add_server(url)
        except Exception as e:
            if self.verbose:
                print(f"Registry load failed: {e}")
    
    def _apply_auth(self) -> None:
        """Apply auth headers to session."""
        if not self.auth:
            return
        try:
            headers = self.auth.get_headers_sync()
            if headers:
                self.session.headers.update(headers)
        except Exception as e:
            if self.verbose:
                print(f"Auth failed: {e}")
    
    def _refresh_auth(self) -> None:
        """Refresh auth on 401/403."""
        if not self.auth or not self.auth.should_retry_on_unauthorized():
            return
        try:
            self.auth.handle_unauthorized_sync()
            headers = self.auth.get_headers_sync()
            if headers:
                self.session.headers.update(headers)
        except Exception as e:
            if self.verbose:
                print(f"Auth refresh failed: {e}")
    
    def _discover_all(self) -> None:
        """Discover tools from all servers."""
        self._apply_auth()
        
        for server_url in self.servers:
            try:
                base = MCPBaseURL.normalize(server_url)
                url = base.list_tools_url()
                
                # Request with retry on auth failure
                resp = self.session.get(url, timeout=5.0)
                if resp.status_code in (401, 403):
                    self._refresh_auth()
                    resp = self.session.get(url, timeout=5.0)
                
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
                tools = [normalize_tool_metadata(t) for t in data.get("tools", [])]
                
                self.tools[base.base] = tools
                
                if self.verbose:
                    print(f"Discovered {len(tools)} tools from {base.base}")
            
            except Exception as e:
                if self.verbose:
                    print(f"Discovery failed for {server_url}: {e}")
    
    def _all_tools(self) -> List[Dict[str, Any]]:
        """Get all tools with server metadata."""
        result = []
        for server, tools in self.tools.items():
            for t in tools:
                t = dict(t)
                t["_server"] = server
                result.append(t)
        return result
    
    def _select_tool(self, query: str) -> Optional[Dict[str, Any]]:
        """Select best tool for query using LLM."""
        all_tools = self._all_tools()
        if not all_tools:
            return None
        
        # Build tool list
        lines = []
        for i, t in enumerate(all_tools):
            lines.append(f"{i}. {t.get('name')}: {t.get('description', '')}")
            lines.append(f"   Schema: {json.dumps(t.get('input_schema', {}))}")
        
        skills_ctx = ""
        if self.skills_sh_enabled and self._skills_sh_entries:
            skills_ctx = build_skills_context(
                query,
                self._skills_sh_entries,
                max_skills=self.skills_sh_max_skills,
                max_total_chars=self.skills_sh_max_chars,
            )

        prompt = f"""Select the best tool for this request.

Request: {query}

Tools:
{chr(10).join(lines)}

{skills_ctx}

Respond with JSON only:
{{
  "index": <tool index 0-based>,
  "params": {{<parameters>}},
  "reason": "<why>"
}}

If no tool matches, respond: {{"index": -1, "reason": "no match"}}
"""
        
        try:
            resp = self.llm.generate(prompt).strip()
            
            # Extract JSON
            if "```json" in resp:
                resp = resp.split("```json")[1].split("```")[0].strip()
            elif "```" in resp:
                resp = resp.split("```")[1].split("```")[0].strip()
            
            sel = json.loads(resp)
            idx = int(sel.get("index", -1))
            
            if idx < 0 or idx >= len(all_tools):
                return None
            
            tool = dict(all_tools[idx])
            tool["_params"] = sel.get("params", {})
            tool["_reason"] = sel.get("reason", "")
            
            if self.verbose:
                print(f"Selected: {tool.get('name')} @ {tool.get('_server')}")
            
            return tool
        
        except Exception as e:
            if self.verbose:
                print(f"Selection failed: {e}")
            return None
    
    def _execute_tool(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Execute selected tool."""
        self._apply_auth()
        
        server = tool.get("_server")
        name = tool.get("name")
        params = tool.get("_params", {})
        
        if not server or not name:
            return {"error": "Invalid tool"}
        
        base = MCPBaseURL.normalize(server)
        url = base.invoke_url(name)
        
        try:
            # Request with retry on auth failure
            resp = self.session.post(url, json=params, timeout=self.timeout)
            if resp.status_code in (401, 403):
                self._refresh_auth()
                resp = self.session.post(url, json=params, timeout=self.timeout)
            
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        
        except Exception as e:
            return {"error": str(e)}
    
    def _generate_response(self, query: str, result: Dict[str, Any]) -> str:
        """Generate natural language response."""
        prompt = f"""User asked: "{query}"

Tool result:
{json.dumps(result, indent=2)}

Provide a natural, helpful response based on this result.
"""
        try:
            return self.llm.generate(prompt).strip()
        except:
            return f"Result: {json.dumps(result)}"
    
    def run(self, query: str) -> str:
        """
        Execute user query (single tool execution).
        
        Args:
            query: User request
        
        Returns:
            Natural language response
        """
        if self.verbose:
            print(f"\nQuery: {query}")
        
        # Select tool
        tool = self._select_tool(query)
        if not tool:
            return "No suitable tool found for your request."
        
        # Execute
        result = self._execute_tool(tool)
        
        # Generate response
        response = self._generate_response(query, result)
        
        if self.verbose:
            print(f"Response: {response}\n")
        
        return response
    
    def add_server(self, url: str) -> None:
        """Add MCP server and discover its tools."""
        base = MCPBaseURL.normalize(url).base
        if base not in self.servers:
            self.servers.append(base)
            self._discover_all()
    
    def close(self) -> None:
        """Close HTTP session."""
        if self.session:
            self.session.close()
