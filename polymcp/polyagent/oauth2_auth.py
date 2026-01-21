"""
OAuth 2.0 Authentication Provider
RFC 6749 compliant implementation with thread-safe token management.
"""

import time
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests
import httpx

from .auth_base import AuthProvider


@dataclass
class OAuth2Token:
    """OAuth 2.0 token state."""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    obtained_at: float = 0.0


class OAuth2Provider(AuthProvider):
    """
    OAuth 2.0 provider following RFC 6749.

    Supports:
    - client_credentials (§4.4)
    - authorization_code (§4.1)
    - refresh_token (§6)

    Thread-safe with automatic token refresh.

    Notes:
    - Some IdPs require client authentication via HTTP Basic (RFC 6749 §2.3.1)
    - Others require client_id/client_secret in body (or both).
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        grant_type: str = "client_credentials",
        scope: Optional[str] = None,
        audience: Optional[str] = None,
        code: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        refresh_token: Optional[str] = None,
        use_basic_auth: bool = True,
        send_client_secret_in_body: bool = False,
        timeout: float = 10.0,
        early_refresh_seconds: int = 30,
        extra_token_params: Optional[Dict[str, Any]] = None,
    ):
        self.token_url = str(token_url)
        self.client_id = str(client_id)
        self.client_secret = str(client_secret)
        self.initial_grant_type = str(grant_type)
        self.scope = scope
        self.audience = audience
        self.code = code
        self.redirect_uri = redirect_uri

        self.use_basic_auth = bool(use_basic_auth)
        self.send_client_secret_in_body = bool(send_client_secret_in_body)

        self.timeout = float(timeout)
        self.early_refresh_seconds = int(early_refresh_seconds)
        self.extra_token_params = dict(extra_token_params or {})

        self._token = OAuth2Token()
        if refresh_token:
            self._token.refresh_token = str(refresh_token)

        self._lock = threading.Lock()

    def _needs_refresh_locked(self) -> bool:
        """Check if token needs refresh (lock must already be held)."""
        if not self._token.access_token:
            return True

        age = time.time() - float(self._token.obtained_at or 0.0)
        expires = int(self._token.expires_in or 3600)
        # refresh early to avoid edge expiry
        return age >= max(0, expires - self.early_refresh_seconds)

    def _client_auth_for_http(self) -> Optional[Tuple[str, str]]:
        """Return auth tuple for requests/httpx when using Basic Auth."""
        if self.use_basic_auth:
            return (self.client_id, self.client_secret)
        return None

    def _maybe_add_client_creds_to_body(self, payload: Dict[str, Any]) -> None:
        """
        When not using HTTP Basic, many IdPs expect client_id (and sometimes client_secret)
        in the request body.
        """
        if self.use_basic_auth:
            return

        payload["client_id"] = self.client_id
        if self.send_client_secret_in_body:
            payload["client_secret"] = self.client_secret

    def _build_payload_locked(self, grant_type: str) -> Dict[str, Any]:
        """Build token request payload. (lock should be held)"""
        payload: Dict[str, Any] = {"grant_type": grant_type}

        # optional common params
        if self.scope:
            payload["scope"] = self.scope
        if self.audience:
            payload["audience"] = self.audience

        # grant-specific params
        if grant_type == "client_credentials":
            self._maybe_add_client_creds_to_body(payload)

        elif grant_type == "authorization_code":
            if not self.code or not self.redirect_uri:
                raise ValueError("authorization_code requires code and redirect_uri")
            payload["code"] = self.code
            payload["redirect_uri"] = self.redirect_uri
            self._maybe_add_client_creds_to_body(payload)

        elif grant_type == "refresh_token":
            if not self._token.refresh_token:
                raise ValueError("No refresh_token available")
            payload["refresh_token"] = self._token.refresh_token
            # Some IdPs require client auth on refresh too.
            self._maybe_add_client_creds_to_body(payload)

        else:
            raise ValueError(f"Unsupported grant_type: {grant_type}")

        # allow caller-defined extra params (e.g. resource, audience, custom fields)
        for k, v in (self.extra_token_params or {}).items():
            if v is None:
                continue
            payload[k] = v

        return payload

    def _update_token_locked(self, data: Dict[str, Any]) -> None:
        """Update token from response. (lock should be held)"""
        if not isinstance(data, dict):
            raise RuntimeError("Token endpoint returned non-JSON object")

        access = data.get("access_token")
        if not access or not isinstance(access, str):
            raise RuntimeError("Response missing access_token")

        self._token.access_token = access
        self._token.token_type = str(data.get("token_type", "Bearer") or "Bearer")

        rt = data.get("refresh_token")
        if rt:
            self._token.refresh_token = str(rt)

        exp = data.get("expires_in")
        if exp is not None:
            try:
                self._token.expires_in = int(exp)
            except Exception:
                # if provider returns weird expires_in, fall back to 3600
                self._token.expires_in = 3600

        self._token.obtained_at = time.time()

    def _pick_grant_locked(self) -> str:
        """
        Decide whether to use refresh_token grant or initial grant.
        (lock should be held)
        """
        if self._token.refresh_token and self._needs_refresh_locked():
            return "refresh_token"
        return self.initial_grant_type

    def _fetch_token_sync(self) -> None:
        """Fetch/refresh token synchronously."""
        with self._lock:
            grant = self._pick_grant_locked()
            payload = self._build_payload_locked(grant)
            auth = self._client_auth_for_http()

        resp = requests.post(
            self.token_url,
            data=payload,
            auth=auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        # raise with good context
        try:
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"OAuth2 token request failed: {resp.status_code} {resp.text}") from e

        data = resp.json()
        with self._lock:
            self._update_token_locked(data)

    async def _fetch_token_async(self) -> None:
        """Fetch/refresh token asynchronously."""
        with self._lock:
            grant = self._pick_grant_locked()
            payload = self._build_payload_locked(grant)
            auth = self._client_auth_for_http()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.token_url,
                data=payload,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code >= 400:
            raise RuntimeError(f"OAuth2 token request failed: {resp.status_code} {resp.text}")

        data = resp.json()
        with self._lock:
            self._update_token_locked(data)

    def get_headers_sync(self) -> Dict[str, str]:
        """Get Authorization headers (sync) with automatic refresh."""
        with self._lock:
            needs = self._needs_refresh_locked()

        if needs:
            self._fetch_token_sync()

        with self._lock:
            if not self._token.access_token:
                return {}
            return {"Authorization": f"{self._token.token_type} {self._token.access_token}"}

    async def get_headers_async(self) -> Dict[str, str]:
        """Get Authorization headers (async) with automatic refresh."""
        with self._lock:
            needs = self._needs_refresh_locked()

        if needs:
            await self._fetch_token_async()

        with self._lock:
            if not self._token.access_token:
                return {}
            return {"Authorization": f"{self._token.token_type} {self._token.access_token}"}

    def handle_unauthorized_sync(self) -> None:
        """
        Called when a request returned 401/403.
        Force refresh on next call and refresh immediately.
        """
        with self._lock:
            self._token.obtained_at = 0.0
            # Keep refresh_token if we have it; otherwise it will re-run initial grant.
        self._fetch_token_sync()

    async def handle_unauthorized_async(self) -> None:
        """
        Called when a request returned 401/403.
        Force refresh on next call and refresh immediately.
        """
        with self._lock:
            self._token.obtained_at = 0.0
        await self._fetch_token_async()
