"""
PolyAgent - Intelligent LLM Agent
"""

# Agents
from .agent import PolyAgent
from .unified_agent import UnifiedPolyAgent
from .codemode_agent import CodeModeAgent, AsyncCodeModeAgent

# LLM Providers
from .llm_providers import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    KimiProvider,
    DeepSeekProvider,
)


# Auth (API Key / JWT / OAuth2)
from .auth_base import AuthProvider, StaticHeadersAuth
from .jwt_auth import JWTAuthProvider
from .oauth2_auth import OAuth2Provider

# Unified wrapper with Auth (does NOT modify UnifiedPolyAgent)
from .unified_auth_wrapper import UnifiedPolyAgentWithAuth

__all__ = [
    # Agents
    "PolyAgent",
    "UnifiedPolyAgent",
    "CodeModeAgent",
    "AsyncCodeModeAgent",
    "UnifiedPolyAgentWithAuth",

    # LLM Providers
    "LLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "OllamaProvider",
    "KimiProvider",
    "DeepSeekProvider",

    # Auth
    "AuthProvider",
    "StaticHeadersAuth",
    "JWTAuthProvider",
    "OAuth2Provider",

]
