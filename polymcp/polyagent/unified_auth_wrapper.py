"""UnifiedPolyAgent Auth Wrapper (Production)

Drop-in subclass of `UnifiedPolyAgent` that adds authentication support
without modifying UnifiedPolyAgent's source.

Features:
- AuthProvider integration (API key, JWT, OAuth2)
- Applies auth headers before HTTP tool discovery and invocation
- Retries once on 401/403 after refreshing auth

Requested import path:
    from polymcp.polyagent import UnifiedPolyAgent
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from polymcp.polyagent import UnifiedPolyAgent

from .auth_base import AuthProvider


class UnifiedPolyAgentWithAuth(UnifiedPolyAgent):
    """UnifiedPolyAgent + AuthProvider.

    Usage:
        from polymcp.polyagent import UnifiedPolyAgentWithAuth
        from polymcp.oauth2_auth import OAuth2Provider

        auth = OAuth2Provider(...)
        agent = UnifiedPolyAgentWithAuth(
            llm_provider=..., mcp_servers=[...], auth_provider=auth
        )
    """

    def __init__(self, *args, auth_provider: Optional[AuthProvider] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.auth_provider = auth_provider

    async def _apply_auth_headers(self) -> None:
        if not self.auth_provider:
            return
        headers = await self.auth_provider.get_headers_async()
        if not headers:
            return
        # Ensure both the stored headers and the live client headers are updated.
        self.http_headers.update(headers)
        if self.http_client:
            self.http_client.headers.update(headers)

    async def _refresh_on_unauthorized(self) -> None:
        if not self.auth_provider:
            return
        if not self.auth_provider.should_retry_on_unauthorized():
            return
        await self.auth_provider.handle_unauthorized_async()
        await self._apply_auth_headers()

    async def start(self) -> None:
        """Start agent and ensure auth headers are applied before discovery."""
        # Apply auth before UnifiedPolyAgent creates its http client and performs discovery.
        await self._apply_auth_headers()
        await super().start()
        # Re-apply in case super().start() created a new AsyncClient.
        await self._apply_auth_headers()

    async def _execute_tool_internal(self, tool: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool, adding auth for HTTP tools and retry on 401/403."""
        # Stdio tools: pass through to base implementation.
        if tool.get("_server_type") == "stdio":
            return await super()._execute_tool_internal(tool, parameters)

        # HTTP tools: inject auth headers and retry once on 401/403.
        await self._apply_auth_headers()

        server_url = tool.get("_server_url")
        tool_name = tool.get("name")
        invoke_url = f"{server_url}/invoke/{tool_name}"

        resp = await self.http_client.post(invoke_url, json=parameters, timeout=30.0)
        if resp.status_code in (401, 403):
            await self._refresh_on_unauthorized()
            resp = await self.http_client.post(invoke_url, json=parameters, timeout=30.0)

        resp.raise_for_status()
        return resp.json()
