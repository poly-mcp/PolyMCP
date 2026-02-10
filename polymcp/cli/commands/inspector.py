"""
Inspector Command - Launch PolyMCP Inspector
Interactive MCP server testing and debugging tool.
"""

import click
import asyncio
import json
import secrets
import sys
from pathlib import Path


@click.command('inspector')
@click.option('--host', default='127.0.0.1', help='Server host')
@click.option('--port', default=6274, type=int, help='Server port')
@click.option('--no-browser', is_flag=True, help='Do not open browser automatically')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
@click.option('--config', type=click.Path(exists=True), help='Path to config file with servers')
@click.option('--server', 'servers', multiple=True, help='Add server (format: http://url or stdio:command)')
@click.option('--secure', is_flag=True, help='Enable secure mode (API key required)')
@click.option('--api-key', default=None, help='API key for secure mode (auto-generated if omitted)')
@click.option('--allow-origin', 'allow_origins', multiple=True, help='Allowed CORS origin (repeatable)')
@click.option('--rate-limit', default=120, type=int, help='API requests allowed per window')
@click.option('--rate-window', default=60, type=int, help='Rate limit window in seconds')
def inspector(host, port, no_browser, verbose, config, servers, secure, api_key, allow_origins, rate_limit, rate_window):
    """
    Launch PolyMCP Inspector - Interactive MCP Server Testing Tool.
    
    The inspector provides a web-based interface for testing and debugging
    MCP servers with real-time metrics, activity logs, and multi-server support.
    
    \b
    Examples:
      polymcp inspector
      polymcp inspector --port 8080
      polymcp inspector --secure
      polymcp inspector --secure --api-key my-strong-key
      polymcp inspector --server http://localhost:8000/mcp
      polymcp inspector --server "stdio:npx @playwright/mcp@latest"
      polymcp inspector --config servers.json
    """
    try:
        from polymcp.inspector.server import run_inspector
    except ImportError:
        click.echo("Error: Inspector module not found", err=True)
        click.echo("Make sure inspector module is properly installed", err=True)
        sys.exit(1)
    
    # Display startup banner
    click.echo()
    click.echo("=" * 70)
    click.echo("PolyMCP Inspector - MCP Server Testing Tool".center(70))
    click.echo("=" * 70)
    click.echo()
    
    # Parse servers from CLI
    server_configs = []
    for server_str in servers:
        server_configs.append(_parse_server_string(server_str))
    
    # Load servers from config file
    if config:
        try:
            with open(config, 'r') as f:
                config_data = json.load(f)
                
                # Support both PolyMCP config and MCP standard config
                if 'mcpServers' in config_data:
                    # MCP standard format
                    for name, cfg in config_data['mcpServers'].items():
                        server_configs.append({
                            'id': name.lower().replace(' ', '_'),
                            'name': name,
                            'type': cfg.get('type', 'stdio'),
                            'command': cfg.get('command'),
                            'args': cfg.get('args', []),
                            'env': cfg.get('env'),
                            'url': cfg.get('url')
                        })
                
                elif 'servers' in config_data:
                    # PolyMCP format
                    for server in config_data['servers']:
                        server_configs.append(server)
            
            click.echo(f"Loaded {len(server_configs)} servers from config")
        
        except Exception as e:
            click.echo(f"Warning: Failed to load config: {e}", err=True)
    
    if secure and not api_key:
        api_key = secrets.token_urlsafe(24)

    # Display configuration
    click.echo(f"Server: http://{host}:{port}")
    click.echo(f"Secure mode: {'ON' if secure else 'OFF'}")
    if secure:
        click.echo(f"Inspector API key: {api_key}")
    if allow_origins:
        click.echo(f"Allowed origins: {', '.join(allow_origins)}")
    if server_configs:
        click.echo(f"Initial servers: {len(server_configs)}")
        for cfg in server_configs:
            server_desc = cfg.get('url') or f"{cfg.get('command')} {' '.join(cfg.get('args', []))}"
            click.echo(f"  - {cfg.get('name', 'Unnamed')}: {server_desc}")
    click.echo()
    
    if not no_browser:
        click.echo("Opening browser...")
    
    click.echo("Press Ctrl+C to stop")
    click.echo("=" * 70)
    click.echo()
    
    # Run inspector
    try:
        asyncio.run(run_inspector(
            host=host,
            port=port,
            verbose=verbose,
            open_browser=not no_browser,
            servers=server_configs if server_configs else None,
            secure_mode=secure,
            api_key=api_key,
            allowed_origins=list(allow_origins) if allow_origins else None,
            rate_limit_per_minute=rate_limit,
            rate_limit_window_seconds=rate_window,
        ))
    except KeyboardInterrupt:
        click.echo("\n\nShutting down inspector...")
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _parse_server_string(server_str):
    """Parse server string into config dict."""
    if server_str.startswith('http://') or server_str.startswith('https://'):
        server_id = server_str.split('/')[-1] or 'http_server'
        return {
            'id': server_id,
            'name': server_id.replace('_', ' ').title(),
            'type': 'http',
            'url': server_str
        }
    
    elif server_str.startswith('stdio:'):
        command_str = server_str[6:].strip()
        parts = command_str.split()
        
        if not parts:
            raise ValueError(f"Invalid stdio server format: {server_str}")
        
        command = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        server_id = command.replace('/', '_').replace('.', '_')
        
        return {
            'id': server_id,
            'name': f"{command} {' '.join(args[:2])}..." if len(args) > 2 else f"{command} {' '.join(args)}",
            'type': 'stdio',
            'command': command,
            'args': args
        }
    
    else:
        return {
            'id': 'server',
            'name': 'Server',
            'type': 'http',
            'url': server_str
        }
