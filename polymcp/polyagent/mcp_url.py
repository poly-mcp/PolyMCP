"""
MCP URL Normalization
Ensures consistent /mcp base path.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MCPBaseURL:
    """Immutable MCP base URL (always ends with /mcp)."""
    base: str
    
    @staticmethod
    def normalize(url: str) -> "MCPBaseURL":
        """Normalize URL to include /mcp suffix."""
        s = (url or "").strip()
        if not s:
            raise ValueError("URL cannot be empty")
        
        # Remove trailing slashes
        while s.endswith("/"):
            s = s[:-1]
        
        # Add /mcp if missing
        if not s.lower().endswith("/mcp"):
            s += "/mcp"
        
        return MCPBaseURL(base=s)
    
    def list_tools_url(self) -> str:
        """Get list_tools endpoint."""
        return f"{self.base}/list_tools"
    
    def invoke_url(self, tool_name: str) -> str:
        """Get tool invocation endpoint."""
        return f"{self.base}/invoke/{tool_name}"
