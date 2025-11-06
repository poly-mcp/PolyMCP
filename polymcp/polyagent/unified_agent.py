"""
Unified PolyAgent - Supports both HTTP and Stdio MCP Servers
Production-ready agent that seamlessly works with both server types.
"""

import json
import asyncio
import requests
import sys
import re
from typing import List, Dict, Any, Optional, Tuple
from .llm_providers import LLMProvider
from ..mcp_stdio_client import MCPStdioClient, MCPStdioAdapter, MCPServerConfig


class UnifiedPolyAgent:
    """
    Enhanced PolyAgent with stdio support.
    
    Works with both HTTP-based and stdio-based MCP servers seamlessly.
    Provides autonomous agentic behavior with multi-step reasoning.
    """
    
    # System prompts templates
    TOOL_SELECTION_SYSTEM = """You are an autonomous AI agent with access to tools provided by MCP (Model Context Protocol) servers.

IMPORTANT CONCEPTS:
1. Tools are automatically available - you can use any tool listed below immediately
2. Some tools require data from other tools (e.g., to interact with elements, you need references from a snapshot first)
3. You work in steps - select ONE tool at a time that moves toward completing the user's goal
4. Available tools come from currently connected MCP servers and update dynamically

Your job: Select the NEXT BEST tool to execute based on:
- The user's original request
- What has already been done
- What information you have
- What information you still need

Available tools:
{tool_descriptions}"""

    CONTINUATION_DECISION_SYSTEM = """You are evaluating whether an autonomous agent should continue working or stop.

STOP when:
- The user's request is fully completed
- The task is impossible (requires login, external permissions, unavailable data)
- Multiple consecutive failures suggest the approach won't work
- No progress is being made

CONTINUE when:
- The request is partially completed and more steps are needed
- A clear next action exists that can make progress
- Previous failures were due to missing information that you can now obtain

Be decisive and realistic about what's achievable."""

    FINAL_RESPONSE_SYSTEM = """You are summarizing what an autonomous agent accomplished.

RULES:
1. Use ONLY information from the actual tool results provided
2. DO NOT invent, assume, or hallucinate details
3. Be factual and concise
4. If something failed, state it clearly
5. Don't mention technical details (tool names, JSON, APIs, etc.)
6. Speak naturally as if you did the actions yourself

Focus on what was accomplished, not how it was done."""
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_servers: Optional[List[str]] = None,
        stdio_servers: Optional[List[Dict[str, Any]]] = None,
        registry_path: Optional[str] = None,
        verbose: bool = False,
        memory_enabled: bool = True
    ):
        """
        Initialize unified agent.
        
        Args:
            llm_provider: LLM provider instance
            mcp_servers: List of HTTP MCP server URLs
            stdio_servers: List of stdio server configurations
            registry_path: Path to registry JSON
            verbose: Enable verbose logging
            memory_enabled: Enable persistent memory between requests
        """
        self.llm_provider = llm_provider
        self.mcp_servers = mcp_servers or []
        self.stdio_configs = stdio_servers or []
        self.verbose = verbose
        self.memory_enabled = memory_enabled
        
        self.http_tools_cache = {}
        self.stdio_clients: Dict[str, MCPStdioClient] = {}
        self.stdio_adapters: Dict[str, MCPStdioAdapter] = {}
        
        # Persistent memory (if enabled)
        self._persistent_history = [] if memory_enabled else None
        
        if registry_path:
            self._load_registry(registry_path)
    
    def _load_registry(self, registry_path: str) -> None:
        """Load servers from registry."""
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry = json.load(f)
                
                http_servers = registry.get('servers', [])
                self.mcp_servers.extend(http_servers)
                
                stdio_servers = registry.get('stdio_servers', [])
                self.stdio_configs.extend(stdio_servers)
                
                if self.verbose:
                    print(f"Loaded {len(http_servers)} HTTP and {len(stdio_servers)} stdio servers")
        
        except Exception as e:
            if self.verbose:
                print(f"Failed to load registry: {e}")
    
    async def start(self) -> None:
        """Start all stdio servers and discover tools."""
        for config_dict in self.stdio_configs:
            try:
                config = MCPServerConfig(
                    command=config_dict['command'],
                    args=config_dict.get('args', []),
                    env=config_dict.get('env')
                )
                
                client = MCPStdioClient(config)
                await client.start()
                
                adapter = MCPStdioAdapter(client)
                
                server_id = f"stdio://{config.command}"
                self.stdio_clients[server_id] = client
                self.stdio_adapters[server_id] = adapter
                
                if self.verbose:
                    tools = await adapter.get_tools()
                    print(f"Started stdio server: {server_id} ({len(tools)} tools)")
            
            except Exception as e:
                if self.verbose:
                    print(f"Failed to start stdio server: {e}")
        
        self._discover_http_tools()
        
        # Wait for stabilization
        if self.stdio_clients or self.mcp_servers:
            await asyncio.sleep(2)
    
    def _discover_http_tools(self) -> None:
        """Discover tools from HTTP servers."""
        for server_url in self.mcp_servers:
            try:
                list_url = f"{server_url}/list_tools"
                response = requests.get(list_url, timeout=5)
                response.raise_for_status()
                
                tools = response.json().get('tools', [])
                self.http_tools_cache[server_url] = tools
                
                if self.verbose:
                    print(f"Discovered {len(tools)} tools from {server_url}")
            
            except Exception as e:
                if self.verbose:
                    print(f"Failed to discover tools from {server_url}: {e}")
    
    async def _get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all tools from both HTTP and stdio servers."""
        all_tools = []
        
        for server_url, tools in self.http_tools_cache.items():
            for tool in tools:
                tool_with_server = tool.copy()
                tool_with_server['_server_url'] = server_url
                tool_with_server['_server_type'] = 'http'
                all_tools.append(tool_with_server)
        
        for server_id, adapter in self.stdio_adapters.items():
            try:
                tools = await adapter.get_tools()
                for tool in tools:
                    tool_with_server = tool.copy()
                    tool_with_server['_server_url'] = server_id
                    tool_with_server['_server_type'] = 'stdio'
                    all_tools.append(tool_with_server)
            except Exception as e:
                if self.verbose:
                    print(f"Failed to get tools from {server_id}: {e}")
        
        return all_tools
    
    async def _execute_tool(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool (HTTP or stdio) - GENERIC."""
        server_url = tool.get('_server_url')
        server_type = tool.get('_server_type')
        tool_name = tool.get('name')
        parameters = tool.get('_parameters', {})
        
        try:
            if server_type == 'http':
                invoke_url = f"{server_url}/invoke/{tool_name}"
                response = requests.post(invoke_url, json=parameters, timeout=30)
                response.raise_for_status()
                return response.json()
            
            elif server_type == 'stdio':
                adapter = self.stdio_adapters.get(server_url)
                if not adapter:
                    return {"error": "Stdio adapter not found", "status": "error"}
                
                result = await adapter.invoke_tool(tool_name, parameters)
                return result
            
            else:
                return {"error": f"Unknown server type: {server_type}", "status": "error"}
        
        except Exception as e:
            error_msg = f"Tool execution failed: {e}"
            if self.verbose:
                print(f"❌ {error_msg}")
            return {"error": error_msg, "status": "error"}
    
    def _extract_previous_results(self, action_history: List[Dict]) -> str:
        """Extract previous results in a generic way for LLM context."""
        if not action_history:
            return "No previous results available."
        
        results_text = []
        
        # Get last 5 successful results
        for action in reversed(action_history[-5:]):
            if action['result'].get('status') == 'success':
                tool_name = action['tool']
                result_data = action['result'].get('result', {})
                
                # Try to extract meaningful content generically
                content_parts = []
                
                # If it's a dict, look for common content patterns
                if isinstance(result_data, dict):
                    # Look for 'content' field (common pattern)
                    if 'content' in result_data:
                        content = result_data['content']
                        if isinstance(content, list):
                            for item in content[:3]:  # Limit items
                                if isinstance(item, dict) and 'text' in item:
                                    text = item['text']  # Limit length
                                    content_parts.append(text)
                                elif isinstance(item, str):
                                    content_parts.append(item)
                        elif isinstance(content, str):
                            content_parts.append(content)
                    
                    # Look for other common fields
                    for field in ['output', 'data', 'result', 'text', 'value', 'message']:
                        if field in result_data and field not in ['content']:
                            value = str(result_data[field])
                            content_parts.append(f"{field}: {value}")
                
                elif isinstance(result_data, str):
                    content_parts.append(result_data)
                
                elif isinstance(result_data, list) and result_data:
                    # Take first few items
                    for item in result_data[:3]:
                        content_parts.append(str(item))
                
                if content_parts:
                    result_text = f"\nResult from '{tool_name}':\n" + "\n".join(content_parts)
                    results_text.append(result_text)
        
        if results_text:
            return "PREVIOUS TOOL RESULTS (use any values/references from here):\n" + "\n---\n".join(results_text)
        else:
            return "Previous actions completed but no detailed output available."
    
    def _select_next_action(self, user_message: str, action_history: List[Dict], all_tools: List[Dict]) -> Optional[Dict[str, Any]]:
        """Select next action - COMPLETELY GENERIC."""
        if not all_tools:
            return None
        
        # Blocking logic for repetitions
        blocked_actions = set()
        warnings = []
        
        if action_history:
            last_action = action_history[-1]
            last_tool = last_action['tool']
            last_params = last_action['parameters']
            last_status = last_action['result'].get('status', 'unknown')
            
            # Count consecutive same actions
            consecutive_same = 0
            for action in reversed(action_history):
                if action['tool'] == last_tool and action['parameters'] == last_params:
                    consecutive_same += 1
                else:
                    break
            
            # Block repeated successful actions
            if last_status == 'success' and consecutive_same >= 2:
                blocked_key = f"{last_tool}:{json.dumps(last_params, sort_keys=True)}"
                blocked_actions.add(blocked_key)
                warnings.append(f"Already executed {last_tool} successfully {consecutive_same} times")
            
            # Block repeated failures
            if last_status != 'success' and consecutive_same >= 3:
                blocked_key = f"{last_tool}:{json.dumps(last_params, sort_keys=True)}"
                blocked_actions.add(blocked_key)
                warnings.append(f"{last_tool} failed {consecutive_same} times")
        
        # Build action history summary
        history_lines = []
        if not action_history:
            history_context = "No actions taken yet. This is your first action."
        else:
            for action in action_history[-5:]:  # Last 5 actions
                status = "✓" if action['result'].get('status') == 'success' else "✗"
                params_str = json.dumps(action['parameters']) if action['parameters'] else "no params"
                history_lines.append(f"  {status} {action['tool']} {params_str}")
            
            history_context = "Recent actions:\n" + "\n".join(history_lines)
            if warnings:
                history_context += "\n\nWarnings:\n" + "\n".join(f"  - {w}" for w in warnings)
        
        # Extract previous results
        previous_results = self._extract_previous_results(action_history)
        
        # Build tool descriptions
        tools_list = []
        for i, tool in enumerate(all_tools):
            schema = tool.get('input_schema', {})
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            # Build parameters description
            params_desc = []
            for param_name, param_info in properties.items():
                param_type = param_info.get('type', 'any')
                req_mark = "*" if param_name in required else ""
                param_desc = param_info.get('description', '')[:80]
                params_desc.append(f"    - {param_name}{req_mark} ({param_type}): {param_desc}")
            
            params_str = "\n".join(params_desc) if params_desc else "    No parameters"
            
            # Check if blocked
            blocked = " [BLOCKED]" if any(blocked_key.startswith(tool['name'] + ":") for blocked_key in blocked_actions) else ""
            
            tools_list.append(
                f"[{i}] {tool['name']}{blocked} - {tool['description']}\n{params_str}"
            )
        
        tool_descriptions = "\n\n".join(tools_list)
        
        # Build prompts
        system_prompt = self.TOOL_SELECTION_SYSTEM.format(tool_descriptions=tool_descriptions)
        
        user_prompt = f"""USER REQUEST: "{user_message}"

{history_context}

{previous_results}

TASK: Select the NEXT tool to make progress. Use actual values from previous results when needed.

RESPONSE FORMAT (JSON only):
{{
  "tool_index": <number from 0 to {len(all_tools)-1}>,
  "tool_name": "<exact tool name>",
  "parameters": {{"param1": "value1", "param2": "value2"}},
  "reasoning": "<why this tool and how it progresses the goal>"
}}

If no suitable tool or task is complete/impossible:
{{
  "tool_index": -1,
  "reasoning": "<explanation>"
}}

JSON only:"""
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            llm_response = self.llm_provider.generate(full_prompt).strip()
            
            # Extract JSON
            if "```json" in llm_response:
                llm_response = llm_response.split("```json")[1].split("```")[0].strip()
            elif "```" in llm_response:
                llm_response = llm_response.split("```")[1].split("```")[0].strip()
            
            start = llm_response.find('{')
            end = llm_response.rfind('}') + 1
            if start != -1 and end > start:
                llm_response = llm_response[start:end]
            
            if self.verbose:
                print(f"LLM response: {llm_response[:150]}...")
            
            selection = json.loads(llm_response)
            
            tool_index = selection.get('tool_index', -1)
            if tool_index < 0:
                if self.verbose:
                    print(f"⊘ No tool selected: {selection.get('reasoning', 'N/A')}")
                return None
            
            if tool_index >= len(all_tools):
                if self.verbose:
                    print(f"⚠ Invalid index {tool_index}")
                return None
            
            selected_tool = all_tools[tool_index].copy()
            
            # Validate tool name if provided
            claimed_name = selection.get('tool_name', '')
            if claimed_name and claimed_name != selected_tool['name']:
                # Try to find by name
                for i, t in enumerate(all_tools):
                    if t['name'] == claimed_name:
                        selected_tool = all_tools[i].copy()
                        if self.verbose:
                            print(f"📝 Corrected tool selection: {claimed_name}")
                        break
            
            selected_tool['_parameters'] = selection.get('parameters', {})
            selected_tool['_reasoning'] = selection.get('reasoning', '')
            
            if self.verbose:
                print(f"✓ Selected: {selected_tool['name']}")
                print(f"  Params: {selected_tool['_parameters']}")
                print(f"  Why: {selected_tool['_reasoning']}")
            
            return selected_tool
        
        except Exception as e:
            if self.verbose:
                print(f"✗ Selection failed: {e}")
            return None
    
    async def _should_continue(self, user_message: str, action_history: List[Dict]) -> Tuple[bool, str]:
        """Decide if should continue - GENERIC."""
        total_actions = len(action_history)
        consecutive_failures = 0
        
        for action in reversed(action_history):
            if action['result'].get('status') != 'success':
                consecutive_failures += 1
            else:
                break
        
        # Auto-stop on too many failures
        if consecutive_failures >= 3:
            return False, f"Stopped: {consecutive_failures} consecutive failures"
        
        # Build context
        recent_actions = action_history[-3:]
        history_summary = []
        for a in recent_actions:
            status = "✓" if a['result'].get('status') == 'success' else "✗"
            history_summary.append(f"  {status} Step {a['step']}: {a['tool']}")
        
        history_text = "\n".join(history_summary)
        
        prompt = f"""{self.CONTINUATION_DECISION_SYSTEM}

CONTEXT:
User request: "{user_message}"
Total actions taken: {total_actions}
Consecutive failures: {consecutive_failures}

Recent actions:
{history_text}

DECIDE: Should the agent continue or stop?

RESPONSE FORMAT (JSON only):
{{
  "continue": true/false,
  "reason": "<brief clear explanation>"
}}

JSON only:"""
        
        try:
            llm_response = self.llm_provider.generate(prompt).strip()
            
            # Extract JSON
            if "```json" in llm_response:
                llm_response = llm_response.split("```json")[1].split("```")[0].strip()
            elif "```" in llm_response:
                llm_response = llm_response.split("```")[1].split("```")[0].strip()
            
            start = llm_response.find('{')
            end = llm_response.rfind('}') + 1
            if start != -1 and end > start:
                llm_response = llm_response[start:end]
            
            decision = json.loads(llm_response)
            should_continue = decision.get('continue', False)
            reason = decision.get('reason', 'No reason provided')
            
            if self.verbose:
                print(f"🧠 {'→ Continue' if should_continue else '⊡ Stop'}: {reason}")
            
            return should_continue, reason
        
        except Exception as e:
            if self.verbose:
                print(f"✗ Decision failed: {e}")
            return False, "Decision error, stopping to be safe"
    
    def _generate_final_response(self, user_message: str, action_history: List[Dict]) -> str:
        """Generate final response - GENERIC."""
        if not action_history:
            return "I couldn't find any suitable tools to complete your request."
        
        # Extract results
        results_data = []
        for action in action_history:
            result = action['result']
            status = result.get('status', 'unknown')
            
            if status == 'success':
                result_content = result.get('result', {})
                # Try to extract meaningful content
                if isinstance(result_content, dict):
                    content = result_content.get('content', [])
                    if isinstance(content, list):
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and 'text' in item:
                                text_parts.append(item['text'])
                        if text_parts:
                            results_data.append(f"Step {action['step']}: {' '.join(text_parts)}")
                        else:
                            results_data.append(f"Step {action['step']}: Action completed")
                    else:
                        results_data.append(f"Step {action['step']}: {str(result_content)}")
                else:
                    results_data.append(f"Step {action['step']}: {str(result_content)}")
            else:
                error = result.get('error', 'Unknown error')
                results_data.append(f"Step {action['step']}: Failed - {error}")
        
        results_text = "\n".join(results_data) if results_data else "Actions completed"
        
        prompt = f"""{self.FINAL_RESPONSE_SYSTEM}

USER'S ORIGINAL REQUEST:
"{user_message}"

WHAT HAPPENED (tool execution results):
{results_text}

YOUR TASK: Write a natural, conversational response explaining what you accomplished.

Response:"""
        
        try:
            response = self.llm_provider.generate(prompt)
            return response.strip()
        except Exception as e:
            if self.verbose:
                print(f"✗ Response generation failed: {e}")
            success_count = sum(1 for a in action_history if a['result'].get('status') == 'success')
            return f"I completed {success_count} out of {len(action_history)} actions."
    
    async def run_async(self, user_message: str, max_steps: int = 10) -> str:
        """Process user request with agentic loop - COMPLETELY GENERIC."""
        if self.verbose:
            print(f"\n{'='*60}\nUser: {user_message}\n{'='*60}")
        
        # Use persistent history if enabled
        action_history = []
        if self.memory_enabled and self._persistent_history:
            action_history = self._persistent_history.copy()
            if self.verbose:
                print(f"📚 Loaded {len(action_history)} previous actions from memory")
        
        initial_length = len(action_history)
        
        for step in range(max_steps):
            current_step = len(action_history) + 1
            if self.verbose:
                print(f"\n🤖 Step {current_step} (iteration {step + 1}/{max_steps})")
            
            # Check if should continue (skip first iteration)
            if step > 0:
                should_continue, reason = await self._should_continue(user_message, action_history)
                if not should_continue:
                    if self.verbose:
                        print(f"✓ Stopping: {reason}")
                    break
            
            # Select next action
            all_tools = await self._get_all_tools()
            selected_tool = self._select_next_action(user_message, action_history, all_tools)
            
            if not selected_tool:
                if self.verbose:
                    print("⚠ No tool selected")
                break
            
            # Execute tool
            if self.verbose:
                print(f"🔧 Executing: {selected_tool['name']}")
                if selected_tool.get('_parameters'):
                    print(f"   Params: {selected_tool['_parameters']}")
            
            tool_result = await self._execute_tool(selected_tool)
            
            # Log result
            if self.verbose:
                status = tool_result.get('status', 'unknown')
                if status == 'success':
                    print(f"   ✅ Success")
                else:
                    error = tool_result.get('error', 'Unknown')
                    print(f"   ❌ Failed: {error}")
            
            # Save to history
            action_history.append({
                'step': current_step,
                'tool': selected_tool['name'],
                'parameters': selected_tool.get('_parameters', {}),
                'reasoning': selected_tool.get('_reasoning', ''),
                'result': tool_result
            })
            
            # Pause between actions
            await asyncio.sleep(1)
        
        # Update persistent history if enabled
        if self.memory_enabled:
            self._persistent_history = action_history
        
        # Generate response only for new actions
        new_actions = action_history[initial_length:]
        response = self._generate_final_response(user_message, new_actions)
        
        if self.verbose:
            print(f"\n{'='*60}\nAgent: {response}\n{'='*60}")
        
        return response
    
    def run(self, user_message: str) -> str:
        """Process user request (sync wrapper)."""
        return asyncio.run(self._run_sync_wrapper(user_message))
    
    async def _run_sync_wrapper(self, user_message: str) -> str:
        """Wrapper for sync run method."""
        if not self.stdio_clients:
            await self.start()
        return await self.run_async(user_message)
    
    def reset_memory(self):
        """Reset persistent memory."""
        if self.memory_enabled:
            self._persistent_history = []
            if self.verbose:
                print("🔄 Memory reset")
    
    async def stop(self) -> None:
        """Stop all stdio servers."""
        for client in self.stdio_clients.values():
            await client.stop()
        
        self.stdio_clients.clear()
        self.stdio_adapters.clear()
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.stop()
        if sys.platform == "win32":
            await asyncio.sleep(0.2)