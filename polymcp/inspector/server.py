"""
PolyMCP Inspector Server - ENHANCED Production Implementation
FastAPI server with WebSocket for real-time MCP server inspection.

NEW FEATURES:
- Skills Generator (generate Claude Skills from MCP servers)
- Resources Support (MCP resources/list + read)
- Prompts Support (MCP prompts/list + get)
- Test Suites (save/load/run test scenarios)
- Export Reports (JSON/Markdown/HTML)
"""

import asyncio
import json
import logging
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ..mcp_stdio_client import MCPStdioClient, MCPStdioAdapter, MCPServerConfig


logger = logging.getLogger(__name__)


@dataclass
class ServerInfo:
    """Information about a connected MCP server."""
    id: str
    name: str
    url: str
    type: str  # 'http' or 'stdio'
    status: str  # 'connected', 'disconnected', 'error'
    tools_count: int
    connected_at: str
    last_request: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ToolMetrics:
    """Metrics for a specific tool."""
    name: str
    calls: int
    total_time: float
    avg_time: float
    success_count: int
    error_count: int
    last_called: Optional[str] = None


@dataclass
class ActivityLog:
    """Activity log entry."""
    timestamp: str
    server_id: str
    method: str
    tool_name: Optional[str]
    status: int
    duration: float
    error: Optional[str] = None


@dataclass
class TestCase:
    """Test case definition."""
    id: str
    name: str
    server_id: str
    tool_name: str
    parameters: Dict[str, Any]
    expected_status: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class TestSuite:
    """Test suite containing multiple test cases."""
    id: str
    name: str
    description: str
    test_cases: List[TestCase]
    created_at: str
    last_run: Optional[str] = None


class ServerManager:
    """
    Manages multiple MCP server connections.
    Handles both HTTP and stdio servers with real-time metrics.
    
    NEW: Added Resources, Prompts, Skills, Test Suites, Export
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.servers: Dict[str, ServerInfo] = {}
        self.stdio_clients: Dict[str, MCPStdioClient] = {}
        self.stdio_adapters: Dict[str, MCPStdioAdapter] = {}
        self.http_tools_cache: Dict[str, List[Dict]] = {}
        
        # Metrics tracking
        self.tool_metrics: Dict[str, Dict[str, ToolMetrics]] = defaultdict(dict)
        self.activity_logs: List[ActivityLog] = []
        self.max_logs = 1000
        
        # WebSocket connections
        self.active_connections: Set[WebSocket] = set()
        
        # NEW: Test suites storage
        self.test_suites: Dict[str, TestSuite] = {}
        self.test_suites_dir = Path.home() / '.polymcp' / 'inspector' / 'test-suites'
        self.test_suites_dir.mkdir(parents=True, exist_ok=True)
        self._load_test_suites()
    
    def _load_test_suites(self):
        """Load test suites from disk."""
        try:
            for suite_file in self.test_suites_dir.glob('*.json'):
                with open(suite_file, 'r') as f:
                    data = json.load(f)
                    test_cases = [TestCase(**tc) for tc in data.get('test_cases', [])]
                    suite = TestSuite(
                        id=data['id'],
                        name=data['name'],
                        description=data.get('description', ''),
                        test_cases=test_cases,
                        created_at=data['created_at'],
                        last_run=data.get('last_run')
                    )
                    self.test_suites[suite.id] = suite
            
            if self.verbose:
                logger.info(f"Loaded {len(self.test_suites)} test suites")
        
        except Exception as e:
            logger.error(f"Failed to load test suites: {e}")
    
    def _save_test_suite(self, suite: TestSuite):
        """Save test suite to disk."""
        try:
            suite_file = self.test_suites_dir / f"{suite.id}.json"
            with open(suite_file, 'w') as f:
                json.dump({
                    'id': suite.id,
                    'name': suite.name,
                    'description': suite.description,
                    'test_cases': [asdict(tc) for tc in suite.test_cases],
                    'created_at': suite.created_at,
                    'last_run': suite.last_run
                }, f, indent=2)
            
            if self.verbose:
                logger.info(f"Saved test suite: {suite.name}")
        
        except Exception as e:
            logger.error(f"Failed to save test suite: {e}")
            raise
    
    async def add_http_server(self, server_id: str, name: str, url: str) -> Dict[str, Any]:
        """Add HTTP MCP server."""
        try:
            import requests
            
            # Test connection and discover tools
            list_url = f"{url}/list_tools"
            response = requests.get(list_url, timeout=5)
            response.raise_for_status()
            
            tools = response.json().get('tools', [])
            
            # Store server info
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=url,
                type='http',
                status='connected',
                tools_count=len(tools),
                connected_at=datetime.now().isoformat()
            )
            
            # Cache tools
            self.http_tools_cache[server_id] = tools
            
            # Initialize metrics for each tool
            for tool in tools:
                tool_name = tool.get('name')
                if tool_name:
                    self.tool_metrics[server_id][tool_name] = ToolMetrics(
                        name=tool_name,
                        calls=0,
                        total_time=0.0,
                        avg_time=0.0,
                        success_count=0,
                        error_count=0
                    )
            
            if self.verbose:
                logger.info(f"Connected to HTTP server: {name} ({len(tools)} tools)")
            
            await self._broadcast_update('server_added', asdict(self.servers[server_id]))
            
            return {'status': 'success', 'server': asdict(self.servers[server_id])}
        
        except Exception as e:
            error_msg = f"Failed to connect to {url}: {str(e)}"
            logger.error(error_msg)
            
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=url,
                type='http',
                status='error',
                tools_count=0,
                connected_at=datetime.now().isoformat(),
                error=error_msg
            )
            
            await self._broadcast_update('server_error', {
                'server_id': server_id,
                'error': error_msg
            })
            
            return {'status': 'error', 'error': error_msg}
    
    async def add_stdio_server(
        self,
        server_id: str,
        name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Add stdio MCP server."""
        try:
            config = MCPServerConfig(command=command, args=args, env=env)
            client = MCPStdioClient(config)
            
            await client.start()
            
            adapter = MCPStdioAdapter(client)
            tools = await adapter.get_tools()
            
            self.stdio_clients[server_id] = client
            self.stdio_adapters[server_id] = adapter
            
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=f"stdio://{command}",
                type='stdio',
                status='connected',
                tools_count=len(tools),
                connected_at=datetime.now().isoformat()
            )
            
            # Initialize metrics
            for tool in tools:
                tool_name = tool.get('name')
                if tool_name:
                    self.tool_metrics[server_id][tool_name] = ToolMetrics(
                        name=tool_name,
                        calls=0,
                        total_time=0.0,
                        avg_time=0.0,
                        success_count=0,
                        error_count=0
                    )
            
            if self.verbose:
                logger.info(f"Connected to stdio server: {name} ({len(tools)} tools)")
            
            await self._broadcast_update('server_added', asdict(self.servers[server_id]))
            
            return {'status': 'success', 'server': asdict(self.servers[server_id])}
        
        except Exception as e:
            error_msg = f"Failed to start {command}: {str(e)}"
            logger.error(error_msg)
            
            self.servers[server_id] = ServerInfo(
                id=server_id,
                name=name,
                url=f"stdio://{command}",
                type='stdio',
                status='error',
                tools_count=0,
                connected_at=datetime.now().isoformat(),
                error=error_msg
            )
            
            await self._broadcast_update('server_error', {
                'server_id': server_id,
                'error': error_msg
            })
            
            return {'status': 'error', 'error': error_msg}
    
    async def remove_server(self, server_id: str) -> Dict[str, Any]:
        """Remove a server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        # Stop stdio client if exists
        if server_id in self.stdio_clients:
            try:
                await self.stdio_clients[server_id].stop()
            except:
                pass
            del self.stdio_clients[server_id]
            del self.stdio_adapters[server_id]
        
        # Remove from caches
        if server_id in self.http_tools_cache:
            del self.http_tools_cache[server_id]
        
        if server_id in self.tool_metrics:
            del self.tool_metrics[server_id]
        
        del self.servers[server_id]
        
        await self._broadcast_update('server_removed', {'server_id': server_id})
        
        return {'status': 'success'}
    
    async def get_tools(self, server_id: str) -> List[Dict[str, Any]]:
        """Get tools from a server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        
        if server.type == 'http':
            return self.http_tools_cache.get(server_id, [])
        else:  # stdio
            if server_id in self.stdio_adapters:
                return await self.stdio_adapters[server_id].get_tools()
            return []
    
    async def execute_tool(
        self,
        server_id: str,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        start_time = datetime.now()
        
        try:
            if server.type == 'http':
                import requests
                invoke_url = f"{server.url}/invoke/{tool_name}"
                response = requests.post(
                    invoke_url,
                    json=parameters,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
            
            else:  # stdio
                adapter = self.stdio_adapters[server_id]
                result = await adapter.invoke_tool(tool_name, parameters)
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self._update_metrics(server_id, tool_name, duration, True)
            self._log_activity(
                server_id=server_id,
                method='execute_tool',
                tool_name=tool_name,
                status=200,
                duration=duration
            )
            
            server.last_request = datetime.now().isoformat()
            
            await self._broadcast_update('tool_executed', {
                'server_id': server_id,
                'tool_name': tool_name,
                'duration': duration
            })
            
            return {
                'status': 'success',
                'result': result,
                'duration': duration
            }
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self._update_metrics(server_id, tool_name, duration, False)
            self._log_activity(
                server_id=server_id,
                method='execute_tool',
                tool_name=tool_name,
                status=500,
                duration=duration,
                error=error_msg
            )
            
            await self._broadcast_update('tool_error', {
                'server_id': server_id,
                'tool_name': tool_name,
                'error': error_msg
            })
            
            return {
                'status': 'error',
                'error': error_msg,
                'duration': duration
            }
    
    # NEW: Resources Support
    async def list_resources(self, server_id: str) -> List[Dict[str, Any]]:
        """List resources from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        
        try:
            if server.type == 'http':
                import requests
                response = requests.post(
                    server.url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "resources/list",
                        "id": 1
                    },
                    timeout=10
                )
                response.raise_for_status()
                result = response.json().get('result', {})
                return result.get('resources', [])
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request("resources/list")
                return response.get('result', {}).get('resources', [])
        
        except Exception as e:
            logger.error(f"Failed to list resources from {server_id}: {e}")
            return []
    
    async def read_resource(self, server_id: str, uri: str) -> Dict[str, Any]:
        """Read a resource from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        start_time = datetime.now()
        
        try:
            if server.type == 'http':
                import requests
                response = requests.post(
                    server.url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "resources/read",
                        "params": {"uri": uri},
                        "id": 1
                    },
                    timeout=10
                )
                response.raise_for_status()
                result = response.json().get('result', {})
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request("resources/read", {"uri": uri})
                result = response.get('result', {})
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self._log_activity(
                server_id=server_id,
                method='read_resource',
                tool_name=uri,
                status=200,
                duration=duration
            )
            
            await self._broadcast_update('resource_read', {
                'server_id': server_id,
                'uri': uri,
                'duration': duration
            })
            
            return {
                'status': 'success',
                'contents': result.get('contents', []),
                'duration': duration
            }
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self._log_activity(
                server_id=server_id,
                method='read_resource',
                tool_name=uri,
                status=500,
                duration=duration,
                error=error_msg
            )
            
            return {
                'status': 'error',
                'error': error_msg,
                'duration': duration
            }
    
    # NEW: Prompts Support
    async def list_prompts(self, server_id: str) -> List[Dict[str, Any]]:
        """List prompts from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        
        try:
            if server.type == 'http':
                import requests
                response = requests.post(
                    server.url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "prompts/list",
                        "id": 1
                    },
                    timeout=10
                )
                response.raise_for_status()
                result = response.json().get('result', {})
                return result.get('prompts', [])
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request("prompts/list")
                return response.get('result', {}).get('prompts', [])
        
        except Exception as e:
            logger.error(f"Failed to list prompts from {server_id}: {e}")
            return []
    
    async def get_prompt(
        self,
        server_id: str,
        prompt_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get rendered prompt from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        start_time = datetime.now()
        
        try:
            if server.type == 'http':
                import requests
                response = requests.post(
                    server.url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "prompts/get",
                        "params": {
                            "name": prompt_name,
                            "arguments": arguments
                        },
                        "id": 1
                    },
                    timeout=10
                )
                response.raise_for_status()
                result = response.json().get('result', {})
            
            else:  # stdio
                client = self.stdio_clients[server_id]
                response = await client._send_request(
                    "prompts/get",
                    {"name": prompt_name, "arguments": arguments}
                )
                result = response.get('result', {})
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self._log_activity(
                server_id=server_id,
                method='get_prompt',
                tool_name=prompt_name,
                status=200,
                duration=duration
            )
            
            return {
                'status': 'success',
                'messages': result.get('messages', []),
                'description': result.get('description', ''),
                'duration': duration
            }
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self._log_activity(
                server_id=server_id,
                method='get_prompt',
                tool_name=prompt_name,
                status=500,
                duration=duration,
                error=error_msg
            )
            
            return {
                'status': 'error',
                'error': error_msg,
                'duration': duration
            }
    
    # NEW: Skills Generator
    async def generate_skill(self, server_id: str) -> Dict[str, Any]:
        """Generate Claude Skill from MCP server."""
        if server_id not in self.servers:
            raise ValueError(f"Server {server_id} not found")
        
        server = self.servers[server_id]
        tools = await self.get_tools(server_id)
        
        try:
            # Try to import skill generator
            try:
                from ..skill_generator import MCPSkillGenerator
                generator = MCPSkillGenerator()
                has_generator = True
            except ImportError:
                has_generator = False
            
            if has_generator:
                # Use production skill generator
                if server.type == 'http':
                    skill_content = await asyncio.to_thread(
                        generator.generate_from_url,
                        server.url,
                        server_name=server.name
                    )
                else:
                    # For stdio, generate from tools list
                    skill_content = self._generate_skill_from_tools(server, tools)
            else:
                # Fallback: simple skill generation
                skill_content = self._generate_skill_from_tools(server, tools)
            
            filename = f"{server.name.lower().replace(' ', '_')}_skill.md"
            
            return {
                'status': 'success',
                'skill': skill_content,
                'filename': filename,
                'server_name': server.name
            }
        
        except Exception as e:
            logger.error(f"Failed to generate skill: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _generate_skill_from_tools(self, server: ServerInfo, tools: List[Dict]) -> str:
        """Generate skill content from tools list."""
        skill_md = f"""# {server.name} - MCP Tools Skill

## Overview
Auto-generated skill for {server.name} MCP server.

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Server Information
- **Type:** {server.type}
- **URL:** {server.url}
- **Tools:** {len(tools)}
- **Status:** {server.status}

## Available Tools

"""
        
        # Add each tool
        for tool in tools:
            tool_name = tool.get('name', 'unknown')
            tool_desc = tool.get('description', 'No description')
            input_schema = tool.get('inputSchema') or tool.get('input_schema', {})
            
            skill_md += f"""### {tool_name}

**Description:** {tool_desc}

**Input Schema:**
```json
{json.dumps(input_schema, indent=2)}
```

---

"""
        
        # Add usage section
        skill_md += f"""## Usage Examples

When Claude needs to use these tools:

```
Available tools: {', '.join(t.get('name', '') for t in tools)}
```

## Best Practices

1. Always validate input parameters against the schema
2. Check tool responses for errors
3. Use appropriate error handling
4. Consider rate limits and timeouts

---

*Generated by PolyMCP Inspector*
*{datetime.now().isoformat()}*
"""
        
        return skill_md
    
    # NEW: Test Suites
    def create_test_suite(
        self,
        name: str,
        description: str,
        test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create a new test suite."""
        try:
            import uuid
            
            suite_id = str(uuid.uuid4())[:8]
            
            cases = [
                TestCase(
                    id=tc.get('id', str(uuid.uuid4())[:8]),
                    name=tc.get('name', 'Unnamed Test'),
                    server_id=tc['server_id'],
                    tool_name=tc['tool_name'],
                    parameters=tc['parameters'],
                    expected_status=tc.get('expected_status'),
                    created_at=tc.get('created_at', datetime.now().isoformat())
                )
                for tc in test_cases
            ]
            
            suite = TestSuite(
                id=suite_id,
                name=name,
                description=description,
                test_cases=cases,
                created_at=datetime.now().isoformat()
            )
            
            self.test_suites[suite_id] = suite
            self._save_test_suite(suite)
            
            return {
                'status': 'success',
                'suite': asdict(suite)
            }
        
        except Exception as e:
            logger.error(f"Failed to create test suite: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def run_test_suite(self, suite_id: str) -> Dict[str, Any]:
        """Run a test suite."""
        if suite_id not in self.test_suites:
            raise ValueError(f"Test suite {suite_id} not found")
        
        suite = self.test_suites[suite_id]
        results = []
        
        for test_case in suite.test_cases:
            try:
                result = await self.execute_tool(
                    test_case.server_id,
                    test_case.tool_name,
                    test_case.parameters
                )
                
                passed = True
                if test_case.expected_status:
                    passed = result.get('status') == test_case.expected_status
                
                results.append({
                    'test_id': test_case.id,
                    'test_name': test_case.name,
                    'passed': passed,
                    'result': result,
                    'expected_status': test_case.expected_status
                })
            
            except Exception as e:
                results.append({
                    'test_id': test_case.id,
                    'test_name': test_case.name,
                    'passed': False,
                    'error': str(e),
                    'expected_status': test_case.expected_status
                })
        
        # Update last run
        suite.last_run = datetime.now().isoformat()
        self._save_test_suite(suite)
        
        total = len(results)
        passed = sum(1 for r in results if r.get('passed', False))
        
        return {
            'status': 'success',
            'suite_id': suite_id,
            'suite_name': suite.name,
            'total': total,
            'passed': passed,
            'failed': total - passed,
            'results': results,
            'run_at': suite.last_run
        }
    
    def delete_test_suite(self, suite_id: str) -> Dict[str, Any]:
        """Delete a test suite."""
        if suite_id not in self.test_suites:
            raise ValueError(f"Test suite {suite_id} not found")
        
        try:
            suite_file = self.test_suites_dir / f"{suite_id}.json"
            if suite_file.exists():
                suite_file.unlink()
            
            del self.test_suites[suite_id]
            
            return {'status': 'success'}
        
        except Exception as e:
            logger.error(f"Failed to delete test suite: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    # NEW: Export Reports
    def export_metrics(self, format: str = 'json') -> str:
        """Export metrics in various formats."""
        metrics = self.get_metrics_summary()
        logs = self.activity_logs[-100:]
        servers_data = [asdict(s) for s in self.servers.values()]
        
        timestamp = datetime.now().isoformat()
        
        if format == 'json':
            return json.dumps({
                'metrics': metrics,
                'servers': servers_data,
                'logs': [asdict(log) for log in logs],
                'exported_at': timestamp
            }, indent=2)
        
        elif format == 'markdown':
            md = f"""# PolyMCP Inspector Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

- **Total Requests:** {metrics['total_calls']}
- **Average Time:** {metrics['avg_time']:.2f}ms
- **Success Rate:** {metrics['success_rate']:.1f}%
- **Active Servers:** {metrics['active_servers']}/{metrics['total_servers']}
- **Total Tools:** {metrics['total_tools']}

## Servers

"""
            for server in servers_data:
                md += f"""### {server['name']}
- **Type:** {server['type']}
- **URL:** {server['url']}
- **Status:** {server['status']}
- **Tools:** {server['tools_count']}
- **Connected:** {server['connected_at']}

"""
            
            md += "## Recent Activity\n\n"
            for log in logs[-20:]:
                status_emoji = "✅" if log.status == 200 else "❌"
                md += f"- {status_emoji} `{log.timestamp}` - {log.method}"
                if log.tool_name:
                    md += f" ({log.tool_name})"
                md += f" - {log.duration:.0f}ms"
                if log.error:
                    md += f" - Error: {log.error}"
                md += "\n"
            
            md += f"\n---\n\n*Generated by PolyMCP Inspector*\n"
            
            return md
        
        elif format == 'html':
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>PolyMCP Inspector Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 2rem; }}
        h1, h2 {{ border-bottom: 2px solid #e5e5e5; padding-bottom: 0.5rem; }}
        .metric {{ display: inline-block; margin: 1rem; padding: 1rem; border: 1px solid #e5e5e5; border-radius: 4px; }}
        .metric-value {{ font-size: 2rem; font-weight: bold; }}
        .metric-label {{ color: #666; font-size: 0.875rem; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e5e5; }}
        .success {{ color: #22c55e; }}
        .error {{ color: #ef4444; }}
    </style>
</head>
<body>
    <h1>PolyMCP Inspector Report</h1>
    <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <h2>Summary</h2>
    <div class="metric">
        <div class="metric-value">{metrics['total_calls']}</div>
        <div class="metric-label">Total Requests</div>
    </div>
    <div class="metric">
        <div class="metric-value">{metrics['avg_time']:.1f}ms</div>
        <div class="metric-label">Avg Response Time</div>
    </div>
    <div class="metric">
        <div class="metric-value">{metrics['success_rate']:.1f}%</div>
        <div class="metric-label">Success Rate</div>
    </div>
    <div class="metric">
        <div class="metric-value">{metrics['active_servers']}/{metrics['total_servers']}</div>
        <div class="metric-label">Active Servers</div>
    </div>
    
    <h2>Servers</h2>
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Tools</th>
            </tr>
        </thead>
        <tbody>
"""
            for server in servers_data:
                status_class = 'success' if server['status'] == 'connected' else 'error'
                html += f"""
            <tr>
                <td>{server['name']}</td>
                <td>{server['type']}</td>
                <td class="{status_class}">{server['status']}</td>
                <td>{server['tools_count']}</td>
            </tr>
"""
            
            html += """
        </tbody>
    </table>
    
    <h2>Recent Activity</h2>
    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>Method</th>
                <th>Tool</th>
                <th>Status</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody>
"""
            for log in logs[-20:]:
                status_class = 'success' if log.status == 200 else 'error'
                html += f"""
            <tr>
                <td>{log.timestamp}</td>
                <td>{log.method}</td>
                <td>{log.tool_name or '-'}</td>
                <td class="{status_class}">{log.status}</td>
                <td>{log.duration:.0f}ms</td>
            </tr>
"""
            
            html += """
        </tbody>
    </table>
    
    <footer style="margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e5e5e5; color: #666;">
        <p>Generated by PolyMCP Inspector</p>
    </footer>
</body>
</html>
"""
            return html
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _update_metrics(self, server_id: str, tool_name: str, duration: float, success: bool):
        """Update tool metrics."""
        if tool_name not in self.tool_metrics[server_id]:
            self.tool_metrics[server_id][tool_name] = ToolMetrics(
                name=tool_name,
                calls=0,
                total_time=0.0,
                avg_time=0.0,
                success_count=0,
                error_count=0
            )
        
        metrics = self.tool_metrics[server_id][tool_name]
        metrics.calls += 1
        metrics.total_time += duration
        metrics.avg_time = metrics.total_time / metrics.calls
        metrics.last_called = datetime.now().isoformat()
        
        if success:
            metrics.success_count += 1
        else:
            metrics.error_count += 1
    
    def _log_activity(
        self,
        server_id: str,
        method: str,
        tool_name: Optional[str],
        status: int,
        duration: float,
        error: Optional[str] = None
    ):
        """Log activity entry."""
        log = ActivityLog(
            timestamp=datetime.now().isoformat(),
            server_id=server_id,
            method=method,
            tool_name=tool_name,
            status=status,
            duration=duration,
            error=error
        )
        
        self.activity_logs.append(log)
        
        if len(self.activity_logs) > self.max_logs:
            self.activity_logs = self.activity_logs[-self.max_logs:]
    
    async def _broadcast_update(self, event_type: str, data: Any):
        """Broadcast update to all WebSocket connections."""
        message = json.dumps({
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
        
        disconnected = set()
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except:
                disconnected.add(ws)
        
        self.active_connections -= disconnected
    
    async def register_websocket(self, websocket: WebSocket):
        """Register WebSocket connection."""
        self.active_connections.add(websocket)
    
    async def unregister_websocket(self, websocket: WebSocket):
        """Unregister WebSocket connection."""
        self.active_connections.discard(websocket)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get overall metrics summary."""
        total_calls = 0
        total_time = 0.0
        success_count = 0
        error_count = 0
        
        for server_metrics in self.tool_metrics.values():
            for metrics in server_metrics.values():
                total_calls += metrics.calls
                total_time += metrics.total_time
                success_count += metrics.success_count
                error_count += metrics.error_count
        
        avg_time = (total_time / total_calls) if total_calls > 0 else 0.0
        success_rate = (success_count / total_calls * 100) if total_calls > 0 else 0.0
        
        return {
            'total_calls': total_calls,
            'avg_time': avg_time,
            'success_rate': success_rate,
            'active_servers': len([s for s in self.servers.values() if s.status == 'connected']),
            'total_servers': len(self.servers),
            'total_tools': sum(s.tools_count for s in self.servers.values())
        }
    
    async def cleanup(self):
        """Cleanup all connections."""
        for client in self.stdio_clients.values():
            try:
                await client.stop()
            except:
                pass
        
        self.stdio_clients.clear()
        self.stdio_adapters.clear()
        self.active_connections.clear()


class InspectorServer:
    """
    Main Inspector Server.
    Serves web UI and handles API/WebSocket requests.
    
    ENHANCED with all 5 new features.
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 6274, verbose: bool = False):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.app = FastAPI(title="PolyMCP Inspector")
        self.manager = ServerManager(verbose=verbose)
        
        # CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def serve_ui():
            """Serve the inspector UI."""
            html_path = Path(__file__).parent / "static" / "index.html"
            if html_path.exists():
                return FileResponse(html_path)
            else:
                return HTMLResponse("<h1>PolyMCP Inspector</h1><p>UI file not found</p>")
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()
            await self.manager.register_websocket(websocket)
            
            try:
                await websocket.send_json({
                    'type': 'initial_state',
                    'data': {
                        'servers': [asdict(s) for s in self.manager.servers.values()],
                        'metrics': self.manager.get_metrics_summary()
                    }
                })
                
                while True:
                    data = await websocket.receive_json()
                    await self._handle_ws_message(websocket, data)
            
            except WebSocketDisconnect:
                await self.manager.unregister_websocket(websocket)
        
        # Server Management
        @self.app.post("/api/servers/add")
        async def add_server(server_config: Dict[str, Any]):
            """Add a new server."""
            server_type = server_config.get('type', 'http')
            server_id = server_config.get('id', f"server_{len(self.manager.servers)}")
            name = server_config.get('name', 'Unnamed Server')
            
            if server_type == 'http':
                url = server_config.get('url')
                if not url:
                    raise HTTPException(400, "URL required for HTTP server")
                result = await self.manager.add_http_server(server_id, name, url)
            else:
                command = server_config.get('command')
                args = server_config.get('args', [])
                env = server_config.get('env')
                if not command:
                    raise HTTPException(400, "Command required for stdio server")
                result = await self.manager.add_stdio_server(server_id, name, command, args, env)
            
            return result
        
        @self.app.delete("/api/servers/{server_id}")
        async def remove_server(server_id: str):
            """Remove a server."""
            return await self.manager.remove_server(server_id)
        
        @self.app.get("/api/servers")
        async def list_servers():
            """List all servers."""
            return {'servers': [asdict(s) for s in self.manager.servers.values()]}
        
        # Tools
        @self.app.get("/api/servers/{server_id}/tools")
        async def get_tools(server_id: str):
            """Get tools from a server."""
            tools = await self.manager.get_tools(server_id)
            metrics = self.manager.tool_metrics.get(server_id, {})
            
            enriched_tools = []
            for tool in tools:
                tool_data = tool.copy()
                tool_name = tool.get('name')
                if tool_name in metrics:
                    tool_data['metrics'] = asdict(metrics[tool_name])
                enriched_tools.append(tool_data)
            
            return {'tools': enriched_tools}
        
        @self.app.post("/api/servers/{server_id}/tools/{tool_name}/execute")
        async def execute_tool(server_id: str, tool_name: str, parameters: Dict[str, Any]):
            """Execute a tool."""
            return await self.manager.execute_tool(server_id, tool_name, parameters)
        
        # NEW: Resources
        @self.app.get("/api/servers/{server_id}/resources")
        async def list_resources(server_id: str):
            """List resources from server."""
            resources = await self.manager.list_resources(server_id)
            return {'resources': resources}
        
        @self.app.post("/api/servers/{server_id}/resources/read")
        async def read_resource(server_id: str, uri: str = Body(..., embed=True)):
            """Read a resource."""
            return await self.manager.read_resource(server_id, uri)
        
        # NEW: Prompts
        @self.app.get("/api/servers/{server_id}/prompts")
        async def list_prompts(server_id: str):
            """List prompts from server."""
            prompts = await self.manager.list_prompts(server_id)
            return {'prompts': prompts}
        
        @self.app.post("/api/servers/{server_id}/prompts/get")
        async def get_prompt(
            server_id: str,
            prompt_name: str = Body(...),
            arguments: Dict[str, Any] = Body(...)
        ):
            """Get rendered prompt."""
            return await self.manager.get_prompt(server_id, prompt_name, arguments)
        
        # NEW: Skills Generator
        @self.app.post("/api/servers/{server_id}/generate-skill")
        async def generate_skill(server_id: str):
            """Generate Claude Skill from server."""
            return await self.manager.generate_skill(server_id)
        
        # NEW: Test Suites
        @self.app.get("/api/test-suites")
        async def list_test_suites():
            """List all test suites."""
            return {
                'suites': [asdict(suite) for suite in self.manager.test_suites.values()]
            }
        
        @self.app.post("/api/test-suites")
        async def create_test_suite(
            name: str = Body(...),
            description: str = Body(...),
            test_cases: List[Dict[str, Any]] = Body(...)
        ):
            """Create a test suite."""
            return self.manager.create_test_suite(name, description, test_cases)
        
        @self.app.post("/api/test-suites/{suite_id}/run")
        async def run_test_suite(suite_id: str):
            """Run a test suite."""
            return await self.manager.run_test_suite(suite_id)
        
        @self.app.delete("/api/test-suites/{suite_id}")
        async def delete_test_suite(suite_id: str):
            """Delete a test suite."""
            return self.manager.delete_test_suite(suite_id)
        
        # NEW: Export
        @self.app.get("/api/export/metrics")
        async def export_metrics(format: str = 'json'):
            """Export metrics in various formats."""
            content = self.manager.export_metrics(format)
            
            if format == 'json':
                return PlainTextResponse(content, media_type='application/json')
            elif format == 'markdown':
                return PlainTextResponse(content, media_type='text/markdown')
            elif format == 'html':
                return HTMLResponse(content)
            else:
                raise HTTPException(400, f"Unsupported format: {format}")
        
        # Metrics & Logs
        @self.app.get("/api/metrics")
        async def get_metrics():
            """Get overall metrics."""
            return self.manager.get_metrics_summary()
        
        @self.app.get("/api/metrics/{server_id}")
        async def get_server_metrics(server_id: str):
            """Get metrics for a specific server."""
            if server_id not in self.manager.tool_metrics:
                raise HTTPException(404, "Server not found")
            
            metrics = self.manager.tool_metrics[server_id]
            return {'metrics': {name: asdict(m) for name, m in metrics.items()}}
        
        @self.app.get("/api/logs")
        async def get_logs(limit: int = 100):
            """Get activity logs."""
            logs = self.manager.activity_logs[-limit:]
            return {'logs': [asdict(log) for log in logs]}
        
        @self.app.get("/api/health")
        async def health_check():
            """Health check endpoint."""
            return {'status': 'healthy', 'servers': len(self.manager.servers)}
    
    async def _handle_ws_message(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle incoming WebSocket messages."""
        msg_type = data.get('type')
        
        if msg_type == 'ping':
            await websocket.send_json({'type': 'pong'})
        elif msg_type == 'get_state':
            await websocket.send_json({
                'type': 'state_update',
                'data': {
                    'servers': [asdict(s) for s in self.manager.servers.values()],
                    'metrics': self.manager.get_metrics_summary()
                }
            })


async def run_inspector(
    host: str = "127.0.0.1",
    port: int = 6274,
    verbose: bool = False,
    open_browser: bool = True,
    servers: Optional[List[Dict[str, Any]]] = None
):
    """
    Run the PolyMCP Inspector server.
    
    Args:
        host: Server host
        port: Server port
        verbose: Enable verbose logging
        open_browser: Automatically open browser
        servers: Initial servers to add
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    inspector = InspectorServer(host=host, port=port, verbose=verbose)
    
    # Add initial servers
    if servers:
        for server_config in servers:
            try:
                server_type = server_config.get('type', 'http')
                server_id = server_config.get('id', f"server_{len(inspector.manager.servers)}")
                name = server_config.get('name', 'Unnamed Server')
                
                if server_type == 'http':
                    url = server_config.get('url')
                    await inspector.manager.add_http_server(server_id, name, url)
                else:
                    command = server_config.get('command')
                    args = server_config.get('args', [])
                    env = server_config.get('env')
                    await inspector.manager.add_stdio_server(
                        server_id, name, command, args, env
                    )
            except Exception as e:
                logger.error(f"Failed to add initial server: {e}")
    
    # Open browser
    if open_browser:
        await asyncio.sleep(1)
        webbrowser.open(f"http://{host}:{port}")
    
    # Run server
    config = uvicorn.Config(
        inspector.app,
        host=host,
        port=port,
        log_level="info" if verbose else "warning"
    )
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    finally:
        await inspector.manager.cleanup()
