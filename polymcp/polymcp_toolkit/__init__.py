"""PolyMCP Toolkit - Expose Python functions as MCP tools"""

from .expose import (
    expose_tools,           # Legacy, backward compatibility
    expose_tools_http,      # HTTP server mode
    expose_tools_inprocess, # In-process mode
    InProcessMCPServer,     # In-process server class
)

# NEW: Stdio and WASM server modes
from .expose_tools_stdio import expose_tools_stdio
from .expose_tools_wasm import expose_tools_wasm

__all__ = [
    # HTTP/In-process
    'expose_tools',
    'expose_tools_http', 
    'expose_tools_inprocess',
    'InProcessMCPServer',
    
    # NEW: Stdio and WASM
    'expose_tools_stdio',
    'expose_tools_wasm',
]
