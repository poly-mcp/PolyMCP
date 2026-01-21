"""
Authentication Base Classes
Production-ready auth provider interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class AuthProvider(ABC):
    """Abstract base class for authentication providers."""
    
    @abstractmethod
    def get_headers_sync(self) -> Dict[str, str]:
        """Get authentication headers synchronously."""
        raise NotImplementedError
    
    @abstractmethod
    async def get_headers_async(self) -> Dict[str, str]:
        """Get authentication headers asynchronously."""
        raise NotImplementedError
    
    def should_retry_on_unauthorized(self) -> bool:
        """Whether to retry after 401/403."""
        return True
    
    def handle_unauthorized_sync(self) -> None:
        """Handle 401/403 synchronously (e.g., refresh token)."""
        pass
    
    async def handle_unauthorized_async(self) -> None:
        """Handle 401/403 asynchronously (e.g., refresh token)."""
        pass


class StaticHeadersAuth(AuthProvider):
    """Static headers authentication (API keys)."""
    
    def __init__(self, headers: Optional[Dict[str, str]] = None):
        self._headers = dict(headers or {})
    
    def get_headers_sync(self) -> Dict[str, str]:
        return dict(self._headers)
    
    async def get_headers_async(self) -> Dict[str, str]:
        return dict(self._headers)
    
    def should_retry_on_unauthorized(self) -> bool:
        return False
