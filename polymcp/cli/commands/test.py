"""
Test Command - Test MCP servers and tools
"""

import click
import requests
import json
import asyncio
from pathlib import Path
from typing import Optional


@click.group()
def test():
    """Test MCP servers and tools."""
    pass


@test.command('server')
@click.argument('server_url')
@click.option('--auth-key', help='API key for authentication')
@click.option('--timeout', default=5, help='Request timeout in seconds')
@click.pass_context
def test_server(ctx, server_url: str, auth_key: Optional[str], timeout: int):
    """
    Test MCP server connectivity and endpoints.
    
    Examples:
      polymcp test server http://localhost:8000/mcp
      polymcp test server http://localhost:8000/mcp --auth-key sk-...
    """
    headers = {}
    if auth_key:
        headers['X-API-Key'] = auth_key
    
    click.echo(f" Testing MCP Server: {server_url}\n")
    
    # Test 1: Root endpoint
    click.echo(" Testing root endpoint...")
    try:
        root_url = server_url.replace('/mcp', '')
        response = requests.get(root_url, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            click.echo("    Root endpoint accessible")
            try:
                data = response.json()
                if 'name' in data:
                    click.echo(f"   Server: {data['name']}")
            except:
                pass
        else:
            click.echo(f"     Status: {response.status_code}")
    except Exception as e:
        click.echo(f"    Failed: {e}")
    
    # Test 2: List tools
    click.echo("\n Testing list_tools endpoint...")
    try:
        list_url = f"{server_url}/list_tools"
        response = requests.get(list_url, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            data = response.json()
            tools = data.get('tools', [])
            click.echo(f"    Found {len(tools)} tools")
            
            if tools:
                click.echo("\n   Available tools:")
                for i, tool in enumerate(tools[:5], 1):
                    name = tool.get('name', 'Unknown')
                    desc = tool.get('description', 'No description')[:50]
                    click.echo(f"   {i}. {name}: {desc}")
                
                if len(tools) > 5:
                    click.echo(f"   ... and {len(tools) - 5} more")
            
            return tools
        else:
            click.echo(f"    Status: {response.status_code}")
            return []
    except Exception as e:
        click.echo(f"    Failed: {e}")
        return []


@test.command('tool')
@click.argument('server_url')
@click.argument('tool_name')
@click.option('--params', help='JSON parameters for the tool')
@click.option('--auth-key', help='API key for authentication')
@click.pass_context
def test_tool(ctx, server_url: str, tool_name: str, params: Optional[str], auth_key: Optional[str]):
    """
    Test a specific MCP tool.
    
    Examples:
      polymcp test tool http://localhost:8000/mcp greet --params '{"name":"World"}'
      polymcp test tool http://localhost:8000/mcp add --params '{"a":2,"b":3}'
    """
    headers = {}
    if auth_key:
        headers['X-API-Key'] = auth_key
    
    click.echo(f" Testing tool: {tool_name}\n")
    
    # Parse parameters
    tool_params = {}
    if params:
        try:
            tool_params = json.loads(params)
        except json.JSONDecodeError as e:
            click.echo(f" Invalid JSON parameters: {e}", err=True)
            return
    
    # Get tool info
    try:
        list_url = f"{server_url}/list_tools"
        response = requests.get(list_url, headers=headers, timeout=5)
        response.raise_for_status()
        
        tools = response.json().get('tools', [])
        tool_info = next((t for t in tools if t['name'] == tool_name), None)
        
        if not tool_info:
            click.echo(f" Tool '{tool_name}' not found", err=True)
            click.echo("\nAvailable tools:")
            for t in tools:
                click.echo(f"  • {t['name']}")
            return
        
        click.echo(f" Tool Info:")
        click.echo(f"   Name: {tool_info['name']}")
        click.echo(f"   Description: {tool_info.get('description', 'N/A')}")
        
        schema = tool_info.get('input_schema', {})
        if schema.get('properties'):
            click.echo(f"\n   Parameters:")
            for param, info in schema['properties'].items():
                param_type = info.get('type', 'any')
                required = param in schema.get('required', [])
                req_mark = " (required)" if required else " (optional)"
                click.echo(f"     • {param}: {param_type}{req_mark}")
        
        # Invoke tool
        click.echo(f"\n Invoking tool with params: {json.dumps(tool_params)}")
        
        invoke_url = f"{server_url}/invoke/{tool_name}"
        response = requests.post(invoke_url, json=tool_params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            click.echo(f"\n Success!")
            click.echo(f"\nResult:")
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"\n Failed with status {response.status_code}")
            click.echo(f"Response: {response.text}")
    
    except requests.RequestException as e:
        click.echo(f" Request failed: {e}", err=True)
    except Exception as e:
        click.echo(f" Error: {e}", err=True)


@test.command('auth')
@click.argument('server_url')
@click.option('--username', prompt=True, help='Username')
@click.option('--password', prompt=True, hide_input=True, help='Password')
@click.pass_context
def test_auth(ctx, server_url: str, username: str, password: str):
    """
    Test authentication on an MCP server.
    
    Examples:
      polymcp test auth http://localhost:8000
    """
    click.echo(f" Testing authentication...\n")
    
    # Try login
    try:
        login_url = f"{server_url}/auth/login"
        response = requests.post(
            login_url,
            json={"username": username, "password": password},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            access_token = data.get('access_token')
            
            click.echo(" Login successful!")
            click.echo(f"\nAccess Token: {access_token[:30]}...")
            click.echo(f"Token Type: {data.get('token_type')}")
            click.echo(f"Expires In: {data.get('expires_in')}s")
            
            # Try authenticated request
            click.echo("\n Testing authenticated request...")
            
            list_url = f"{server_url}/mcp/list_tools"
            response = requests.get(
                list_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5
            )
            
            if response.status_code == 200:
                tools = response.json().get('tools', [])
                click.echo(f" Authenticated request successful! ({len(tools)} tools)")
            else:
                click.echo(f"  Authenticated request failed: {response.status_code}")
        
        else:
            click.echo(f" Login failed: {response.status_code}")
            click.echo(f"Response: {response.text}")
    
    except Exception as e:
        click.echo(f" Error: {e}", err=True)


@test.command('stdio')
@click.argument('command')
@click.argument('args', nargs=-1)
@click.pass_context
def test_stdio(ctx, command: str, args: tuple):
    """
    Test stdio MCP server.
    
    Examples:
      polymcp test stdio npx @playwright/mcp@latest
      polymcp test stdio python my_server.py
    """
    click.echo(f" Testing stdio server: {command} {' '.join(args)}\n")
    
    async def run_test():
        try:
            from polymcp.mcp_stdio_client import MCPStdioClient, MCPServerConfig
        except ImportError:
            click.echo(" Error: PolyMCP not installed", err=True)
            return
        
        config = MCPServerConfig(
            command=command,
            args=list(args),
            env={}
        )
        
        client = MCPStdioClient(config)
        
        try:
            click.echo(" Starting server...")
            await client.start()
            click.echo("    Server started")
            
            click.echo("\n Listing tools...")
            tools = await client.list_tools()
            click.echo(f"    Found {len(tools)} tools")
            
            if tools:
                click.echo("\n   Available tools:")
                for i, tool in enumerate(tools[:5], 1):
                    name = tool.get('name', 'Unknown')
                    desc = tool.get('description', 'No description')[:50]
                    click.echo(f"   {i}. {name}: {desc}")
                
                if len(tools) > 5:
                    click.echo(f"   ... and {len(tools) - 5} more")
            
            click.echo("\n Stdio server test successful!")
        
        finally:
            click.echo("\n Stopping server...")
            await client.stop()
            click.echo("    Server stopped")
    
    try:
        asyncio.run(run_test())
    except Exception as e:
        click.echo(f"\n Test failed: {e}", err=True)


@test.command('all')
@click.pass_context
def test_all(ctx):
    """
    Test all configured MCP servers.
    
    Examples:
      polymcp test all
    """
    from ..utils.registry import ServerRegistry
    
    registry = ServerRegistry(Path.cwd())
    http_servers = registry.get_http_servers()
    
    if not http_servers:
        click.echo("No servers configured to test.", err=True)
        return
    
    click.echo(f" Testing {len(http_servers)} configured servers\n")
    
    results = []
    
    for i, (url, config) in enumerate(http_servers.items(), 1):
        name = config.get('name', 'Unnamed')
        click.echo(f"{i}. Testing {name} ({url})...")
        
        try:
            response = requests.get(f"{url}/list_tools", timeout=5)
            
            if response.status_code == 200:
                tools = response.json().get('tools', [])
                click.echo(f"    Online ({len(tools)} tools)")
                results.append((name, True, len(tools)))
            else:
                click.echo(f"    Status {response.status_code}")
                results.append((name, False, 0))
        
        except Exception as e:
            click.echo(f"    Failed: {e}")
            results.append((name, False, 0))
    
    # Summary
    click.echo(f"\n{'='*50}")
    click.echo("SUMMARY")
    click.echo(f"{'='*50}")
    
    online = sum(1 for _, status, _ in results if status)
    total_tools = sum(tools for _, status, tools in results if status)
    
    click.echo(f"Servers Online: {online}/{len(results)}")
    click.echo(f"Total Tools: {total_tools}")
