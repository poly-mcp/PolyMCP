"""
Server Registry Management
Handles MCP server registration and configuration.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class ServerRegistry:
    """
    Manage MCP server registry.
    
    Handles both HTTP and stdio server configurations.
    Compatible with PolyMCP's tool_registry.json and stdio_registry.json formats.
    """
    
    def __init__(self, registry_dir: Path):
        """
        Initialize server registry.
        
        Args:
            registry_dir: Directory containing registry files
        """
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.registry_dir / 'polymcp_registry.json'
        self._data: Dict = {
            "version": "1.0.0",
            "description": "PolyMCP server registry",
            "servers": {},
            "stdio_servers": {}
        }
        self._load()
    
    def _load(self) -> None:
        """Load registry from file."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r') as f:
                    loaded_data = json.load(f)
                    
                    # Ensure structure
                    self._data.update({
                        "servers": loaded_data.get("servers", {}),
                        "stdio_servers": loaded_data.get("stdio_servers", {})
                    })
            except Exception as e:
                print(f"Warning: Could not load registry: {e}")
    
    def _save(self) -> None:
        """Save registry to file."""
        try:
            with open(self.registry_path, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"Error saving registry: {e}")
    
    def add_http_server(self, url: str, config: Dict[str, Any]) -> None:
        """
        Add HTTP MCP server.
        
        Args:
            url: Server URL
            config: Server configuration
        """
        self._data["servers"][url] = config
        self._save()
    
    def remove_http_server(self, url: str) -> bool:
        """
        Remove HTTP server.
        
        Args:
            url: Server URL
            
        Returns:
            True if removed, False if not found
        """
        if url in self._data["servers"]:
            del self._data["servers"][url]
            self._save()
            return True
        return False
    
    def get_http_servers(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all HTTP servers.
        
        Returns:
            Dictionary of URL -> config
        """
        return self._data["servers"].copy()
    
    def add_stdio_server(self, name: str, config: Dict[str, Any]) -> None:
        """
        Add stdio MCP server.
        
        Args:
            name: Server name
            config: Server configuration (command, args, env)
        """
        self._data["stdio_servers"][name] = config
        self._save()
    
    def remove_stdio_server(self, name: str) -> bool:
        """
        Remove stdio server.
        
        Args:
            name: Server name
            
        Returns:
            True if removed, False if not found
        """
        if name in self._data["stdio_servers"]:
            del self._data["stdio_servers"][name]
            self._save()
            return True
        return False
    
    def get_stdio_servers(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all stdio servers.
        
        Returns:
            Dictionary of name -> config
        """
        return self._data["stdio_servers"].copy()
    
    def export_to_polymcp_format(self, output_path: Optional[Path] = None) -> Dict:
        """
        Export registry in PolyMCP-compatible format.
        
        Args:
            output_path: Optional path to save exported file
            
        Returns:
            Registry in PolyMCP format
        """
        polymcp_format = {
            "version": "1.0.0",
            "description": "Registry for HTTP and stdio MCP servers",
            "servers": list(self._data["servers"].keys()),
            "stdio_servers": []
        }
        
        # Convert stdio servers to list format
        for name, config in self._data["stdio_servers"].items():
            stdio_config = {
                "name": name,
                "command": config.get("command"),
                "args": config.get("args", []),
                "env": config.get("env", {}),
                "description": config.get("description", ""),
                "tags": config.get("tags", [])
            }
            polymcp_format["stdio_servers"].append(stdio_config)
        
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(polymcp_format, f, indent=2)
        
        return polymcp_format
    
    def import_from_polymcp_format(self, registry_data: Dict) -> None:
        """
        Import registry from PolyMCP format.
        
        Args:
            registry_data: Registry in PolyMCP format
        """
        # Import HTTP servers
        if "servers" in registry_data:
            for url in registry_data["servers"]:
                if url not in self._data["servers"]:
                    self._data["servers"][url] = {
                        "url": url,
                        "type": "http"
                    }
        
        # Import stdio servers
        if "stdio_servers" in registry_data:
            for server in registry_data["stdio_servers"]:
                name = server.get("name")
                if name and name not in self._data["stdio_servers"]:
                    self._data["stdio_servers"][name] = {
                        "command": server.get("command"),
                        "args": server.get("args", []),
                        "env": server.get("env", {}),
                        "description": server.get("description", ""),
                        "tags": server.get("tags", [])
                    }
        
        self._save()
    
    def get_all_servers(self) -> Dict[str, Any]:
        """
        Get all servers (HTTP and stdio).
        
        Returns:
            Complete server configuration
        """
        return {
            "http_servers": self.get_http_servers(),
            "stdio_servers": self.get_stdio_servers()
        }
