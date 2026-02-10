"""
PolyMCP - Universal MCP Agent & Toolkit
Production-ready framework for intelligent LLM tool orchestration.
"""

from .version import __version__

# Skills CLI (skills.sh)
from .skills_cli import run_skills_cli

# Agents
from .polyagent import (
    PolyAgent,
    UnifiedPolyAgent,
    CodeModeAgent,
    AsyncCodeModeAgent
)

# LLM Providers
from .polyagent import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    KimiProvider,
    DeepSeekProvider
)


# Toolkit - Server Creation APIs
from .polymcp_toolkit import (
    expose_tools,           # Legacy
    expose_tools_http,      # HTTP server
    expose_tools_inprocess, # In-process
    expose_tools_stdio,     # NEW: Stdio server
    expose_tools_wasm,      # NEW: WASM compiler
    InProcessMCPServer
)

__all__ = [
    # Version
    '__version__',
    
    # Agents
    'PolyAgent',
    'UnifiedPolyAgent',
    'CodeModeAgent',
    'AsyncCodeModeAgent',
    
    # LLM Providers
    'LLMProvider',
    'OpenAIProvider',
    'AnthropicProvider',
    'OllamaProvider',
    'KimiProvider',
    'DeepSeekProvider',
    
    # Toolkit APIs
    'expose_tools',
    'expose_tools_http',
    'expose_tools_inprocess',
    'expose_tools_stdio',      # NEW
    'expose_tools_wasm',       # NEW
    'InProcessMCPServer',

    # Skills CLI
    'run_skills_cli',
]
