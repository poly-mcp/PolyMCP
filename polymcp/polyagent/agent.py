"""
PolyAgent - Core Agent Implementation
Production-ready intelligent agent for MCP tool discovery and execution.
"""

import json
import requests
from typing import List, Dict, Any, Optional
from .llm_providers import LLMProvider


class PolyAgent:
    """
    Intelligent agent that discovers and executes MCP tools.
    
    The agent automatically connects to MCP servers, discovers available tools,
    uses an LLM to understand user intent, and executes the appropriate tools.
    
    Example:
        >>> from polymcp import PolyAgent, OpenAIProvider
        >>> agent = PolyAgent(
        ...     llm_provider=OpenAIProvider(api_key="sk-..."),
        ...     mcp_servers=["http://localhost:8000/mcp"]
        ... )
        >>> response = agent.run("Summarize this text...")
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_servers: Optional[List[str]] = None,
        registry_path: Optional[str] = None,
        verbose: bool = False
    ):
        """
        Initialize PolyAgent.
        
        Args:
            llm_provider: LLM provider instance (OpenAI, Anthropic, etc.)
            mcp_servers: List of MCP server URLs
            registry_path: Path to tool_registry.json file
            verbose: Enable detailed logging
        """
        self.llm_provider = llm_provider
        self.mcp_servers = mcp_servers or []
        self.verbose = verbose
        self.tools_cache = {}
        
        if registry_path:
            self._load_registry(registry_path)
        
        self._discover_tools()
    
    def _load_registry(self, registry_path: str) -> None:
        """Load MCP servers from registry JSON file."""
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry = json.load(f)
                servers = registry.get('servers', [])
                self.mcp_servers.extend(servers)
                if self.verbose:
                    print(f"Loaded {len(servers)} servers from registry")
        except FileNotFoundError:
            if self.verbose:
                print(f"Registry file not found: {registry_path}")
        except json.JSONDecodeError as e:
            if self.verbose:
                print(f"Invalid JSON in registry: {e}")
        except Exception as e:
            if self.verbose:
                print(f"Failed to load registry: {e}")
    
    def _discover_tools(self) -> None:
        """Discover tools from all configured MCP servers."""
        for server_url in self.mcp_servers:
            try:
                list_url = f"{server_url}/list_tools"
                response = requests.get(list_url, timeout=5)
                response.raise_for_status()
                
                data = response.json()
                tools = data.get('tools', [])
                self.tools_cache[server_url] = tools
                
                if self.verbose:
                    print(f"Discovered {len(tools)} tools from {server_url}")
            
            except requests.RequestException as e:
                if self.verbose:
                    print(f"Failed to discover tools from {server_url}: {e}")
            except Exception as e:
                if self.verbose:
                    print(f"Unexpected error discovering tools: {e}")
    
    def _get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all discovered tools with server information."""
        all_tools = []
        for server_url, tools in self.tools_cache.items():
            for tool in tools:
                tool_with_server = tool.copy()
                tool_with_server['_server_url'] = server_url
                all_tools.append(tool_with_server)
        return all_tools
    
    def _select_tool(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        Use LLM to select the most appropriate tool.
        
        Args:
            user_message: User's input message
            
        Returns:
            Selected tool with parameters, or None if no suitable tool found
        """
        all_tools = self._get_all_tools()
        
        if not all_tools:
            return None
        
        tools_description = "\n".join([
            f"{i+1}. {tool['name']}: {tool['description']}\n   Input: {json.dumps(tool['input_schema'], indent=2)}"
            for i, tool in enumerate(all_tools)
        ])
        
        prompt = f"""You are a tool selection assistant. Analyze the user request and select the most appropriate tool.

User request: {user_message}

Available tools:
{tools_description}

Respond with valid JSON only:
{{
    "tool_index": <index of selected tool (0-based)>,
    "tool_name": "<name of the tool>",
    "parameters": {{<input parameters for the tool>}},
    "reasoning": "<brief explanation>"
}}

If no tool is suitable, respond with: {{"tool_index": -1, "reasoning": "No suitable tool found"}}

Respond ONLY with JSON, no additional text."""
        
        try:
            llm_response = self.llm_provider.generate(prompt)
            response_text = llm_response.strip()
            
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            selection = json.loads(response_text)
            
            if selection.get('tool_index', -1) < 0:
                return None
            
            tool_index = selection['tool_index']
            if tool_index >= len(all_tools):
                return None
            
            selected_tool = all_tools[tool_index].copy()
            selected_tool['_parameters'] = selection.get('parameters', {})
            selected_tool['_reasoning'] = selection.get('reasoning', '')
            
            if self.verbose:
                print(f"Selected tool: {selected_tool['name']}")
                print(f"Reasoning: {selected_tool['_reasoning']}")
            
            return selected_tool
        
        except json.JSONDecodeError:
            if self.verbose:
                print("Failed to parse LLM response as JSON")
            return None
        except Exception as e:
            if self.verbose:
                print(f"Tool selection failed: {e}")
            return None
    
    def _execute_tool(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by calling the MCP server.
        
        Args:
            tool: Tool dictionary with _server_url and _parameters
            
        Returns:
            Tool execution result
        """
        server_url = tool.get('_server_url')
        tool_name = tool.get('name')
        parameters = tool.get('_parameters', {})
        
        try:
            invoke_url = f"{server_url}/invoke/{tool_name}"
            response = requests.post(invoke_url, json=parameters, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if self.verbose:
                print("Tool executed successfully")
            
            return result
        
        except requests.RequestException as e:
            error_msg = f"Tool execution failed: {e}"
            if self.verbose:
                print(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            if self.verbose:
                print(error_msg)
            return {"error": error_msg}
    
    def _generate_response(self, user_message: str, tool_result: Dict[str, Any]) -> str:
        """
        Generate natural language response based on tool result.
        
        Args:
            user_message: Original user message
            tool_result: Result from tool execution
            
        Returns:
            Natural language response
        """
        prompt = f"""You are a helpful assistant. The user asked: "{user_message}"

A tool was executed and returned:
{json.dumps(tool_result, indent=2)}

Provide a clear, natural language response to the user based on this result.
Answer the user's question naturally without mentioning technical details."""
        
        try:
            response = self.llm_provider.generate(prompt)
            return response
        except Exception as e:
            if self.verbose:
                print(f"Failed to generate response: {e}")
            return f"Tool executed. Result: {json.dumps(tool_result)}"
    
    def run(self, user_message: str) -> str:
        """
        Process user request and return response.
        
        Args:
            user_message: User's input message
            
        Returns:
            Agent's response string
        """
        if self.verbose:
            print(f"\nUser: {user_message}\n")
        
        selected_tool = self._select_tool(user_message)
        
        if not selected_tool:
            return "I couldn't find a suitable tool for your request. Please try rephrasing or ask something else."
        
        tool_result = self._execute_tool(selected_tool)
        
        response = self._generate_response(user_message, tool_result)
        
        if self.verbose:
            print(f"\nAgent: {response}\n")
        
        return response
    
    def add_server(self, server_url: str) -> None:
        """
        Add a new MCP server and discover its tools.
        
        Args:
            server_url: URL of the MCP server
        """
        if server_url not in self.mcp_servers:
            self.mcp_servers.append(server_url)
            
            try:
                list_url = f"{server_url}/list_tools"
                response = requests.get(list_url, timeout=5)
                response.raise_for_status()
                
                tools = response.json().get('tools', [])
                self.tools_cache[server_url] = tools
                
                if self.verbose:
                    print(f"Added server {server_url} with {len(tools)} tools")
            
            except Exception as e:
                if self.verbose:
                    print(f"Failed to add server {server_url}: {e}")