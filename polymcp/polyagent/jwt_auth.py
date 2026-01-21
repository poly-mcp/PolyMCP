"""
JWT Authentication Provider
Custom JWT auth with login/refresh endpoints.

Production-hardened:
- thread-safe token state
- safe exception handling (no bare except)
- transient retry with exponential backoff + jitter
- response validation
- avoids leaking secrets in errors
"""

import time
import threading
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests
import httpx

from .auth_base import AuthProvider


@dataclass
class JWTToken:
    """JWT token state."""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    obtained_at: float = 0.0


class JWTAuthProvider(AuthProvider):
    """
    JWT authentication provider.

    Expected API:
        POST /auth/login
            {"username": "...", "password": "..."}
            → {"access_token": "...", "refresh_token": "...", "expires_in": 600}

        POST /auth/refresh
            {"refresh_token": "..."}
            → {"access_token": "...", "refresh_token": "...", "expires_in": 600}
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        login_path: str = "/auth/login",
        refresh_path: str = "/auth/refresh",
        timeout: float = 10.0,
        early_refresh_seconds: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.login_url = self.base_url + login_path
        self.refresh_url = self.base_url + refresh_path
        self.timeout = float(timeout)
        self.early_refresh_seconds = int(early_refresh_seconds)

        self._token = JWTToken()
        self._lock = threading.Lock()

        # Internal tuning (does NOT change external API)
        self._max_retries = 2  # total attempts = 1 + retries
        self._backoff_base = 0.4
        self._backoff_cap = 4.0

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _now(self) -> float:
        return time.time()

    def _needs_refresh_locked(self) -> bool:
        """Check if token needs refresh (lock must be held)."""
        if not self._token.access_token:
            return True
        age = self._now() - float(self._token.obtained_at or 0.0)
        expires = int(self._token.expires_in or 600)
        # refresh early to avoid edge expiry
        return age >= max(0, expires - self.early_refresh_seconds)

    def _validate_token_response(self, data: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[int]]:
        """
        Validate & normalize token response.
        Returns (access_token, refresh_token, expires_in)
        """
        if not isinstance(data, dict):
            raise RuntimeError("Auth response is not a JSON object")

        access = data.get("access_token")
        if not access or not isinstance(access, str):
            raise RuntimeError("Response missing access_token")

        refresh = data.get("refresh_token")
        if refresh is not None and not isinstance(refresh, str):
            # If present, must be str
            refresh = None

        exp = data.get("expires_in")
        expires_in: Optional[int]
        if exp is None:
            expires_in = None
        else:
            try:
                expires_in = int(exp)
            except Exception:
                expires_in = None

        return access, refresh, expires_in

    def _update_token_locked(self, data: Dict[str, Any]) -> None:
        """Update token from response (lock must be held)."""
        access, refresh, expires_in = self._validate_token_response(data)
        self._token.access_token = access

        if refresh:
            self._token.refresh_token = refresh
        if expires_in is not None:
            self._token.expires_in = expires_in

        self._token.obtained_at = self._now()

    def _is_transient_sync(self, exc: Exception, status_code: Optional[int] = None) -> bool:
        # network errors / timeouts
        if isinstance(exc, requests.Timeout):
            return True
        if isinstance(exc, requests.ConnectionError):
            return True
        if status_code is not None and status_code >= 500:
            return True
        return False

    def _is_transient_async(self, exc: Exception, status_code: Optional[int] = None) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
            return True
        if status_code is not None and status_code >= 500:
            return True
        return False

    def _sleep_backoff(self, attempt: int) -> None:
        # attempt starts at 0
        base = min(self._backoff_cap, self._backoff_base * (2 ** attempt))
        jitter = base * random.uniform(-0.15, 0.15)
        time.sleep(max(0.0, base + jitter))

    async def _sleep_backoff_async(self, attempt: int) -> None:
        base = min(self._backoff_cap, self._backoff_base * (2 ** attempt))
        jitter = base * random.uniform(-0.15, 0.15)
        await httpx.AsyncClient().aclose()  # no-op-ish safety; will be optimized away by interpreter
        # Above line is harmless but unnecessary; remove if you prefer.
        # Use asyncio.sleep without importing asyncio to avoid extra dependency changes.
        import asyncio
        await asyncio.sleep(max(0.0, base + jitter))

    # ---------------------------------------------------------------------
    # Sync login/refresh
    # ---------------------------------------------------------------------

    def _login_sync(self) -> None:
        """Login synchronously (with safe retries on transient failures)."""
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                resp = requests.post(
                    self.login_url,
                    json={"username": self.username, "password": self.password},
                    timeout=self.timeout,
                )
                # Hard failures: 4xx (except 429) should not be retried blindly
                if resp.status_code == 429:
                    # rate limit treated as transient
                    raise RuntimeError(f"Rate limited on login (429): {resp.text}")
                resp.raise_for_status()

                data = resp.json()
                with self._lock:
                    self._update_token_locked(data)
                return

            except Exception as e:
                last_exc = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if isinstance(e, requests.HTTPError) and hasattr(e, "response"):
                    status = e.response.status_code

                transient = self._is_transient_sync(e, status) or (status == 429)
                if not transient or attempt >= self._max_retries:
                    # do not leak credentials
                    raise RuntimeError(f"JWT login failed: {type(e).__name__}: {str(e)}") from e

                self._sleep_backoff(attempt)

        # should not reach
        raise RuntimeError(f"JWT login failed: {last_exc}")  # pragma: no cover

    def _refresh_sync(self) -> bool:
        """Try refresh synchronously. Returns True if success."""
        with self._lock:
            refresh = self._token.refresh_token

        if not refresh:
            return False

        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                resp = requests.post(
                    self.refresh_url,
                    json={"refresh_token": refresh},
                    timeout=self.timeout,
                )

                if resp.status_code == 401 or resp.status_code == 403:
                    # refresh token invalid/expired
                    return False

                if resp.status_code == 429:
                    raise RuntimeError(f"Rate limited on refresh (429): {resp.text}")

                if resp.status_code >= 400:
                    # retry only if transient server error
                    if resp.status_code >= 500 and attempt < self._max_retries:
                        self._sleep_backoff(attempt)
                        continue
                    return False

                data = resp.json()
                with self._lock:
                    self._update_token_locked(data)
                return True

            except Exception as e:
                last_exc = e
                status = None
                if isinstance(e, requests.HTTPError) and hasattr(e, "response"):
                    status = e.response.status_code

                transient = self._is_transient_sync(e, status)
                if not transient or attempt >= self._max_retries:
                    return False
                self._sleep_backoff(attempt)

        return False

    # ---------------------------------------------------------------------
    # Async login/refresh
    # ---------------------------------------------------------------------

    async def _login_async(self) -> None:
        """Login asynchronously (with safe retries on transient failures)."""
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self.login_url,
                        json={"username": self.username, "password": self.password},
                    )

                if resp.status_code == 429:
                    raise RuntimeError(f"Rate limited on login (429): {resp.text}")

                resp.raise_for_status()

                data = resp.json()
                with self._lock:
                    self._update_token_locked(data)
                return

            except Exception as e:
                last_exc = e
                status = getattr(e, "status_code", None)
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code

                transient = self._is_transient_async(e, status) or (status == 429)
                if not transient or attempt >= self._max_retries:
                    raise RuntimeError(f"JWT login failed: {type(e).__name__}: {str(e)}") from e

                import asyncio
                base = min(self._backoff_cap, self._backoff_base * (2 ** attempt))
                jitter = base * random.uniform(-0.15, 0.15)
                await asyncio.sleep(max(0.0, base + jitter))

        raise RuntimeError(f"JWT login failed: {last_exc}")  # pragma: no cover

    async def _refresh_async(self) -> bool:
        """Try refresh asynchronously. Returns True if success."""
        with self._lock:
            refresh = self._token.refresh_token

        if not refresh:
            return False

        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self.refresh_url,
                        json={"refresh_token": refresh},
                    )

                if resp.status_code in (401, 403):
                    return False

                if resp.status_code == 429:
                    raise RuntimeError(f"Rate limited on refresh (429): {resp.text}")

                if resp.status_code >= 400:
                    if resp.status_code >= 500 and attempt < self._max_retries:
                        import asyncio
                        base = min(self._backoff_cap, self._backoff_base * (2 ** attempt))
                        jitter = base * random.uniform(-0.15, 0.15)
                        await asyncio.sleep(max(0.0, base + jitter))
                        continue
                    return False

                data = resp.json()
                with self._lock:
                    self._update_token_locked(data)
                return True

            except Exception as e:
                last_exc = e
                status = getattr(e, "status_code", None)
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code

                transient = self._is_transient_async(e, status)
                if not transient or attempt >= self._max_retries:
                    return False

                import asyncio
                base = min(self._backoff_cap, self._backoff_base * (2 ** attempt))
                jitter = base * random.uniform(-0.15, 0.15)
                await asyncio.sleep(max(0.0, base + jitter))

        return False

    # ---------------------------------------------------------------------
    # Public API (UNCHANGED)
    # ---------------------------------------------------------------------

    def get_headers_sync(self) -> Dict[str, str]:
        """Get auth headers with automatic refresh."""
        with self._lock:
            needs = self._needs_refresh_locked()

        if needs:
            # try refresh first, then login
            if not self._refresh_sync():
                self._login_sync()

        with self._lock:
            if not self._token.access_token:
                return {}
            return {"Authorization": f"Bearer {self._token.access_token}"}

    async def get_headers_async(self) -> Dict[str, str]:
        """Get auth headers with automatic refresh."""
        with self._lock:
            needs = self._needs_refresh_locked()

        if needs:
            if not await self._refresh_async():
                await self._login_async()

        with self._lock:
            if not self._token.access_token:
                return {}
            return {"Authorization": f"Bearer {self._token.access_token}"}

    def handle_unauthorized_sync(self) -> None:
        """Force refresh on 401/403."""
        with self._lock:
            self._token.obtained_at = 0.0

        if not self._refresh_sync():
            self._login_sync()

    async def handle_unauthorized_async(self) -> None:
        """Force refresh on 401/403."""
        with self._lock:
            self._token.obtained_at = 0.0

        if not await self._refresh_async():
            await self._login_async()
