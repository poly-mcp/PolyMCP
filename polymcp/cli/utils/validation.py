"""
Validation Utilities
Validate URLs, server configurations, and other inputs.
"""

import re
from typing import Dict, Any, Tuple
from urllib.parse import urlparse


def validate_url(url: str) -> Tuple[bool, str]:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL cannot be empty"
    
    try:
        result = urlparse(url)
        
        # Check scheme
        if result.scheme not in ['http', 'https', 'stdio']:
            return False, f"Invalid scheme: {result.scheme}. Must be http, https, or stdio"
        
        # Check netloc for http/https
        if result.scheme in ['http', 'https'] and not result.netloc:
            return False, "HTTP/HTTPS URLs must have a host"
        
        return True, ""
    
    except Exception as e:
        return False, f"Invalid URL: {e}"


def validate_server_config(config: Dict[str, Any], server_type: str) -> Tuple[bool, str]:
    """
    Validate server configuration.
    
    Args:
        config: Server configuration dictionary
        server_type: Type of server ('http' or 'stdio')
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if server_type == 'http':
        if 'url' not in config:
            return False, "HTTP server config must have 'url' field"
        
        is_valid, error = validate_url(config['url'])
        if not is_valid:
            return False, error
        
        return True, ""
    
    elif server_type == 'stdio':
        if 'command' not in config:
            return False, "Stdio server config must have 'command' field"
        
        if not isinstance(config.get('args', []), list):
            return False, "'args' must be a list"
        
        if not isinstance(config.get('env', {}), dict):
            return False, "'env' must be a dictionary"
        
        return True, ""
    
    else:
        return False, f"Unknown server type: {server_type}"


def validate_tool_name(name: str) -> Tuple[bool, str]:
    """
    Validate tool name format.
    
    Args:
        name: Tool name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Tool name cannot be empty"
    
    # Tool names should be alphanumeric with underscores
    pattern = r'^[a-zA-Z][a-zA-Z0-9_]*$'
    
    if not re.match(pattern, name):
        return False, "Tool name must start with a letter and contain only letters, numbers, and underscores"
    
    if len(name) > 100:
        return False, "Tool name too long (max 100 characters)"
    
    return True, ""


def validate_json_string(json_str: str) -> Tuple[bool, str, Any]:
    """
    Validate JSON string.
    
    Args:
        json_str: JSON string to validate
        
    Returns:
        Tuple of (is_valid, error_message, parsed_data)
    """
    import json
    
    try:
        data = json.loads(json_str)
        return True, "", data
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}", None
    except Exception as e:
        return False, f"Error parsing JSON: {e}", None


def validate_api_key(api_key: str) -> Tuple[bool, str]:
    """
    Validate API key format.
    
    Args:
        api_key: API key to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key:
        return False, "API key cannot be empty"
    
    if len(api_key) < 10:
        return False, "API key too short (minimum 10 characters)"
    
    if len(api_key) > 500:
        return False, "API key too long (maximum 500 characters)"
    
    # Check for suspicious patterns (spaces, newlines, etc.)
    if any(char in api_key for char in [' ', '\n', '\r', '\t']):
        return False, "API key contains invalid characters"
    
    return True, ""


def validate_port(port: Any) -> Tuple[bool, str]:
    """
    Validate port number.
    
    Args:
        port: Port number to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        port_num = int(port)
        
        if port_num < 1 or port_num > 65535:
            return False, "Port must be between 1 and 65535"
        
        return True, ""
    
    except (ValueError, TypeError):
        return False, "Port must be a valid integer"


def sanitize_server_name(name: str) -> str:
    """
    Sanitize server name for use as identifier.
    
    Args:
        name: Server name to sanitize
        
    Returns:
        Sanitized name
    """
    # Remove special characters
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    # Limit length
    if len(sanitized) > 50:
        sanitized = sanitized[:50]
    
    return sanitized.lower()
