"""
Server Command - Manage MCP servers
"""

import click
import json
import requests
from pathlib import Path
from typing import Dict, List
from ..utils.config import Config
from ..utils.registry import ServerRegistry


@click.group()
def server():
    """Manage MCP servers."""
    pass


@server.command('add')
@click.argument('server_url')
@click.option('--name', help='Server name')
@click.option('--type', 'server_type', type=click.Choice(['http', 'stdio']), default='http')
@click.option('--command', help='Command for stdio server')
@click.option('--args', help='Arguments for stdio server (comma-separated)')
@click.option('--global', 'is_global', is_flag=True, help='Add to global config')
@click.pass_context
def add_server(ctx, server_url: str, name: str, server_type: str, command: str, args: str, is_global: bool):
    """
    Add a new MCP server.
    
    Examples:
      polymcp server add http://localhost:8000/mcp
      polymcp server add http://localhost:8000/mcp --name my-server
      polymcp server add stdio://playwright --type stdio --command npx --args @playwright/mcp@latest
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    registry = ServerRegistry(config_dir)
    
    if server_type == 'http':
        # Test HTTP server
        try:
            response = requests.get(f"{server_url}/list_tools", timeout=5)
            if response.status_code == 200:
                tools = response.json().get('tools', [])
                click.echo(f"Server is reachable ({len(tools)} tools found)")
            else:
                click.echo(f"Server responded with status {response.status_code}")
        except Exception as e:
            click.echo(f"Warning: Could not connect to server: {e}")
            if not click.confirm("Add server anyway?"):
                return
        
        server_config = {
            "url": server_url,
            "type": "http"
        }
        
        if name:
            server_config["name"] = name
        
        registry.add_http_server(server_url, server_config)
        click.echo(f"Added HTTP server: {server_url}")
    
    else:  # stdio
        if not command:
            click.echo("Error: --command is required for stdio servers", err=True)
            return
        
        server_args = args.split(',') if args else []
        
        server_config = {
            "command": command,
            "args": server_args,
            "env": {},
            "type": "stdio"
        }
        
        if name:
            server_config["name"] = name
        else:
            name = server_url.replace("stdio://", "")
        
        registry.add_stdio_server(name, server_config)
        click.echo(f"Added stdio server: {name}")
    
    click.echo(f"\nSaved to: {registry.registry_path}")


@server.command('list')
@click.option('--global', 'is_global', is_flag=True, help='List global servers')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def list_servers(ctx, is_global: bool, output_json: bool):
    """
    List all configured MCP servers.
    
    Examples:
      polymcp server list
      polymcp server list --global
      polymcp server list --json
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    registry = ServerRegistry(config_dir)
    
    http_servers = registry.get_http_servers()
    stdio_servers = registry.get_stdio_servers()
    
    if output_json:
        output = {
            "http_servers": http_servers,
            "stdio_servers": stdio_servers
        }
        click.echo(json.dumps(output, indent=2))
        return
    
    if not http_servers and not stdio_servers:
        click.echo("No servers configured.")
        click.echo("\nAdd a server with: polymcp server add <url>")
        return
    
    if http_servers:
        click.echo("\nHTTP Servers:")
        for url, config in http_servers.items():
            name = config.get('name', 'Unnamed')
            click.echo(f"  {name}")
            click.echo(f"    URL: {url}")
    
    if stdio_servers:
        click.echo("\n Stdio Servers:")
        for name, config in stdio_servers.items():
            command = config.get('command')
            args = ' '.join(config.get('args', []))
            click.echo(f"   {name}")
            click.echo(f"    Command: {command} {args}")
    
    click.echo(f"\n Config: {registry.registry_path}")


@server.command('remove')
@click.argument('server_id')
@click.option('--type', 'server_type', type=click.Choice(['http', 'stdio']), default='http')
@click.option('--global', 'is_global', is_flag=True, help='Remove from global config')
@click.pass_context
def remove_server(ctx, server_id: str, server_type: str, is_global: bool):
    """
    Remove a configured MCP server.
    
    Examples:
      polymcp server remove http://localhost:8000/mcp
      polymcp server remove playwright --type stdio
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    registry = ServerRegistry(config_dir)
    
    if server_type == 'http':
        if registry.remove_http_server(server_id):
            click.echo(f" Removed HTTP server: {server_id}")
        else:
            click.echo(f" Server not found: {server_id}", err=True)
    else:
        if registry.remove_stdio_server(server_id):
            click.echo(f" Removed stdio server: {server_id}")
        else:
            click.echo(f" Server not found: {server_id}", err=True)


@server.command('test')
@click.argument('server_url')
@click.option('--tool', help='Test specific tool')
@click.pass_context
def test_server(ctx, server_url: str, tool: str):
    """
    Test connection to an MCP server.
    
    Examples:
      polymcp server test http://localhost:8000/mcp
      polymcp server test http://localhost:8000/mcp --tool greet
    """
    click.echo(f" Testing server: {server_url}")
    
    # Test list_tools
    try:
        list_url = f"{server_url}/list_tools"
        click.echo(f"\n Testing list_tools endpoint...")
        
        response = requests.get(list_url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        tools = data.get('tools', [])
        
        click.echo(f"    Success! Found {len(tools)} tools:")
        for t in tools[:5]:  # Show first 5
            click.echo(f"       {t.get('name')}: {t.get('description', 'No description')[:50]}")
        
        if len(tools) > 5:
            click.echo(f"      ... and {len(tools) - 5} more")
        
        # Test specific tool if requested
        if tool:
            click.echo(f"\n Testing tool: {tool}")
            
            tool_obj = next((t for t in tools if t['name'] == tool), None)
            if not tool_obj:
                click.echo(f"    Tool '{tool}' not found", err=True)
                return
            
            click.echo(f"   Tool found: {tool_obj.get('description', 'No description')}")
            click.echo(f"   Input schema: {json.dumps(tool_obj.get('input_schema', {}), indent=2)}")
            
            # Ask for parameters
            if click.confirm("   Do you want to invoke this tool?"):
                params_str = click.prompt("   Enter parameters as JSON", default="{}")
                try:
                    params = json.loads(params_str)
                    
                    invoke_url = f"{server_url}/invoke/{tool}"
                    response = requests.post(invoke_url, json=params, timeout=10)
                    response.raise_for_status()
                    
                    result = response.json()
                    click.echo(f"\n    Tool executed successfully:")
                    click.echo(f"   {json.dumps(result, indent=2)}")
                
                except json.JSONDecodeError:
                    click.echo("    Invalid JSON parameters", err=True)
                except requests.RequestException as e:
                    click.echo(f"    Request failed: {e}", err=True)
    
    except requests.Timeout:
        click.echo(f" Connection timeout", err=True)
    except requests.RequestException as e:
        click.echo(f" Request failed: {e}", err=True)
    except Exception as e:
        click.echo(f" Error: {e}", err=True)


@server.command('info')
@click.argument('server_url')
@click.pass_context
def server_info(ctx, server_url: str):
    """
    Get detailed information about an MCP server.
    
    Examples:
      polymcp server info http://localhost:8000/mcp
    """
    try:
        # Try root endpoint
        root_url = server_url.replace('/mcp', '')
        response = requests.get(root_url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            click.echo(f"\n Server Info:")
            click.echo(f"   Name: {data.get('name', 'Unknown')}")
            click.echo(f"   Description: {data.get('description', 'N/A')}")
            click.echo(f"   Version: {data.get('version', 'N/A')}")
            
            if 'available_tools' in data:
                click.echo(f"   Tools: {len(data['available_tools'])}")
            
            if 'stats' in data:
                stats = data['stats']
                click.echo(f"\n Stats:")
                for key, value in stats.items():
                    click.echo(f"   {key}: {value}")
        
        # Get tools list
        list_url = f"{server_url}/list_tools"
        response = requests.get(list_url, timeout=5)
        
        if response.status_code == 200:
            tools = response.json().get('tools', [])
            click.echo(f"\n Tools ({len(tools)}):")
            for tool in tools:
                click.echo(f"\n   {tool.get('name')}:")
                click.echo(f"     Description: {tool.get('description', 'N/A')}")
                
                schema = tool.get('input_schema', {})
                if schema.get('properties'):
                    click.echo(f"     Parameters:")
                    for param, info in schema['properties'].items():
                        param_type = info.get('type', 'any')
                        required = param in schema.get('required', [])
                        req_mark = "*" if required else ""
                        click.echo(f"       - {param}{req_mark} ({param_type})")
    
    except Exception as e:
        click.echo(f" Error: {e}", err=True)
